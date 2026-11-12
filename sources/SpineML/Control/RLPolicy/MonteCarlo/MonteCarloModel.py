"""Bindet Tianshous Monte-Carlo-Verfahren REINFORCE an die Fabrikumgebung an."""

from __future__ import annotations

import json
import math
from pathlib import Path
import random

from gymnasium import spaces
import numpy as np
import torch

from .MonteCarloPolicy import MonteCarloPolicy, positive_integer


class MonteCarloModel:
    """Unsere Ein-/Ausgabeanbindung; die Lernregel kommt unverändert aus Tianshou."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        environment_creators=(),
        *,
        learning_rate: float = 0.0001,
        batch_size: int = 64,
        episodes_per_update: int = 4,
        buffer_capacity: int | None = None,
        max_decisions: int = 10_000,
        device: str = "cuda",
        seed: int | None = 0,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
    ):
        self.observation_space = observation_space
        self.action_space = action_space
        self.environment_creators = tuple(environment_creators)
        self.batch_size = positive_integer("batch_size", batch_size)
        self.episodes_per_update = positive_integer("episodes_per_update", episodes_per_update)
        self.max_decisions = positive_integer("max_decisions", max_decisions)
        if not math.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("learning_rate muss endlich und positiv sein.")
        self.learning_rate = float(learning_rate)
        if buffer_capacity is None:
            workers = max(1, min(len(self.environment_creators), self.episodes_per_update))
            # Jeder Worker hat einen eigenen Puffer. Ein schneller Worker kann
            # mehrere Episoden sammeln, während die anderen noch ihre erste beenden.
            episodes_per_worker = self.episodes_per_update - workers + 1
            buffer_capacity = self.max_decisions * workers * episodes_per_worker
        self.buffer_capacity = positive_integer("buffer_capacity", buffer_capacity)
        self.device = torch.device(device)
        if self.device.type not in ("cpu", "cuda"):
            raise ValueError("Das Netz unterstützt CPU und CUDA; trainiert wird nur mit CUDA.")
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA ist in dieser PyTorch-Installation nicht verfügbar.")
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
                raise ValueError("seed muss eine ganze Zahl zwischen 0 und 2**32-1 sein.")
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
        self.seed = seed
        self.policy = MonteCarloPolicy(
            observation_space, action_space, embedding_dim, hidden_dim,
        ).to(self.device)
        self.algorithm = None
        self.episodes_collected = 0
        self.num_timesteps = 0
        self.gradient_updates = 0
        self.last_loss = None
        self.worker_pids = set()
        self._on_episode = None

    def predict(self, observation, state=None, deterministic=True):
        self.policy.eval()
        with torch.inference_mode():
            logits = self.policy.logits(observation)
            if deterministic:
                actions = logits.argmax(dim=1)
            else:
                actions = torch.distributions.Categorical(logits=logits).sample()
        result = actions.cpu().numpy()
        if np.ndim(observation["context"]) == 1:
            result = result.reshape(())
        return result, state

    def learn(self, total_episodes: int, *, on_episode=None, on_update=None):
        """Sammelt neue Episoden und lässt Tianshou daraus lernen."""
        if self.device.type != "cuda":
            raise ValueError("Das Training benötigt eine CUDA-GPU. CPU ist nur für die Auswertung vorgesehen.")
        # Nur beim Training importieren: Vorhersagen benötigen Tianshou nicht.
        from .MonteCarloTraining import create_algorithm, create_collector, create_trainer

        total_episodes = positive_integer("total_episodes", total_episodes)
        if not self.environment_creators:
            raise ValueError("Zum Training werden Simulationsumgebungen benötigt.")
        if self.episodes_collected:
            raise ValueError("Ein neues Training benötigt ein neues MonteCarloModel.")

        self.algorithm = create_algorithm(self)
        self._on_episode = on_episode
        collector = None
        try:
            collector = create_collector(self, total_episodes)
            trainer = create_trainer(self, collector, total_episodes)

            while self.episodes_collected < total_episodes:
                # Die letzte Sammlung kann weniger Episoden enthalten.
                remaining_episodes = total_episodes - self.episodes_collected
                trainer.params.collection_step_num_episodes = min(
                    self.episodes_per_update, remaining_episodes,
                )

                statistics = trainer.execute_epoch()
                self._update_training_statistics(statistics)

                if on_update is not None:
                    on_update(self, {
                        "episodes": self.episodes_collected,
                        "timesteps": self.num_timesteps,
                        "gradient_updates": self.gradient_updates,
                        "last_loss": self.last_loss,
                    })
            return self
        finally:
            self._on_episode = None
            if collector is not None:
                collector.close()

    def _record_episode(self, episode_batch):
        """Prüft eine beendete Episode, zählt sie und meldet ihre Kennzahlen."""
        if len(episode_batch) == 0:
            raise RuntimeError("--buffer-size ist zu klein für eine vollständige Episode; bitte erhöhen.")
        summary = str(episode_batch.info.episode_summary[-1])
        if not summary:
            raise RuntimeError("Die abgeschlossene Episode enthält keine Produktionskennzahlen.")
        info = json.loads(summary)
        length = len(episode_batch)
        if length != int(info["decision_count"]):
            raise RuntimeError("Der Sammelpuffer hat Episodenteile verdrängt. --buffer-size erhöhen; es wurde nicht trainiert.")

        self.episodes_collected += 1
        self.num_timesteps += length
        self.worker_pids.add(int(info["worker_pid"]))
        info["reward"] = float(np.sum(episode_batch.rew))
        info["timesteps"] = self.num_timesteps
        if self._on_episode is not None:
            self._on_episode(info)
        return None

    def _update_training_statistics(self, statistics):
        """Übernimmt den Loss und zählt Adams bisherige Gewichtsänderungen."""
        self.last_loss = float(statistics.training_stat.loss.mean)
        self.gradient_updates = 0
        for state in self.algorithm.optim.state_dict()["state"].values():
            self.gradient_updates = max(self.gradient_updates, int(state.get("step", 0)))
        if not math.isfinite(self.last_loss):
            raise RuntimeError("Das REINFORCE-Training lieferte keinen endlichen Loss.")

    def save(self, path: str | Path) -> None:
        shapes = {}
        for name, space in self.observation_space.spaces.items():
            shapes[name] = list(space.shape)
        torch.save({
            "format_version": 1, "algorithm": "TianshouREINFORCE",
            "observation_shapes": shapes, "action_count": int(self.action_space.n),
            "embedding_dim": self.policy.embedding_dim, "hidden_dim": self.policy.hidden_dim,
            "policy_state": self.policy.state_dict(),
        }, Path(path))

    @classmethod
    def load(cls, path: str | Path, *, device="cpu", seed=None):
        # Ausschließlich Tensoren und einfache Metadaten laden, keine Python-Objekte.
        checkpoint = torch.load(Path(path), map_location="cpu", weights_only=True)
        if checkpoint.get("format_version") != 1 or checkpoint.get("algorithm") != "TianshouREINFORCE":
            raise ValueError("Kein unterstützter Tianshou-REINFORCE-Checkpoint.")
        observation_spaces = {}
        for name, shape in checkpoint["observation_shapes"].items():
            if name.endswith("_mask"):
                observation_spaces[name] = spaces.MultiBinary(shape[0])
            else:
                observation_spaces[name] = spaces.Box(-1.0, 1.0, tuple(shape), np.float32)
        model = cls(
            spaces.Dict(observation_spaces), spaces.Discrete(checkpoint["action_count"]),
            device=str(device), seed=seed,
            embedding_dim=checkpoint["embedding_dim"], hidden_dim=checkpoint["hidden_dim"],
        )
        model.policy.load_state_dict(checkpoint["policy_state"], strict=True)
        model.policy.eval()
        return model
