"""Bindet Tianshous Monte-Carlo-Verfahren REINFORCE an die Fabrikumgebung an."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import random
from time import perf_counter

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import torch

from .MonteCarloPolicy import MonteCarloPolicy, positive_integer


class _EpisodeInfo(gym.Wrapper):
    """Überträgt Abschlusskennzahlen mit gleichbleibender info-Struktur."""

    def reset(self, **kwargs):
        self.started_at = perf_counter()
        observation, _ = self.env.reset(**kwargs)
        return observation, {"episode_summary": ""}

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)
        summary = ""
        if terminated or truncated:
            info = dict(info)
            info["worker_pid"] = os.getpid()
            info["episode_elapsed_seconds"] = perf_counter() - self.started_at
            summary = json.dumps(info, allow_nan=False)
        return observation, reward, terminated, truncated, {"episode_summary": summary}


@dataclass(frozen=True)
class _ProcessEnvironment:
    factory: object

    def __call__(self):
        torch.set_num_threads(1)
        return _EpisodeInfo(self.factory())


class MonteCarloModel:
    """Unsere Ein-/Ausgabeanbindung; die Lernregel kommt unverändert aus Tianshou."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        episode_factories=(),
        *,
        learning_rate: float = 0.0001,
        batch_size: int = 64,
        episodes_per_update: int = 4,
        buffer_capacity: int | None = None,
        max_decisions: int = 10_000,
        device: str = "cpu",
        seed: int | None = 0,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
    ):
        self.observation_space = observation_space
        self.action_space = action_space
        self.episode_factories = tuple(episode_factories)
        self.batch_size = positive_integer("batch_size", batch_size)
        self.episodes_per_update = positive_integer("episodes_per_update", episodes_per_update)
        self.max_decisions = positive_integer("max_decisions", max_decisions)
        if not math.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("learning_rate muss endlich und positiv sein.")
        self.learning_rate = float(learning_rate)
        if buffer_capacity is None:
            workers = max(1, min(len(self.episode_factories), self.episodes_per_update))
            # Jeder Worker hat einen eigenen Puffer. Ein schneller Worker kann
            # mehrere Episoden sammeln, während die anderen noch ihre erste beenden.
            episodes_per_worker = self.episodes_per_update - workers + 1
            buffer_capacity = self.max_decisions * workers * episodes_per_worker
        self.buffer_capacity = positive_integer("buffer_capacity", buffer_capacity)
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        if self.device.type not in ("cpu", "cuda"):
            raise ValueError("Für REINFORCE sind CPU und CUDA vorgesehen.")
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
        # Keine eigene Loss- oder Return-Berechnung: beides übernimmt Reinforce.
        from tianshou.algorithm.modelfree.reinforce import DiscreteActorPolicy, Reinforce
        from tianshou.algorithm.optim import AdamOptimizerFactory
        from tianshou.data import Collector, VectorReplayBuffer
        from tianshou.env import SubprocVectorEnv
        from tianshou.trainer import OnPolicyTrainer, OnPolicyTrainerParams

        total_episodes = positive_integer("total_episodes", total_episodes)
        if not self.episode_factories:
            raise ValueError("Zum Training werden Simulationsumgebungen benötigt.")
        if self.episodes_collected:
            raise ValueError("Ein neues Training benötigt ein neues MonteCarloModel.")
        actor_policy = DiscreteActorPolicy(
            actor=self.policy, action_space=self.action_space,
            observation_space=self.observation_space,
        )
        self.algorithm = Reinforce(
            policy=actor_policy, gamma=1.0, return_standardization=False,
            optim=AdamOptimizerFactory(lr=self.learning_rate),
        )
        factories = []
        for factory in self.episode_factories:
            factories.append(_ProcessEnvironment(factory))
        if len(factories) > min(total_episodes, self.episodes_per_update):
            factories = factories[:min(total_episodes, self.episodes_per_update)]
        workers = len(factories)
        if self.buffer_capacity < workers:
            raise ValueError("--buffer-size benötigt mindestens einen Platz pro Worker.")

        class CompleteEpisodeCollector(Collector):
            def collect(collector, *args, **kwargs):
                result = super().collect(*args, **kwargs)
                # Ringpuffer dürfen keine alten Teile der aktuellen MC-Episoden verdrängen.
                if len(collector.buffer) != result.n_collected_steps:
                    raise RuntimeError(
                        "Der Sammelpuffer ist zu klein für die vollständigen Episoden. "
                        "--buffer-size erhöhen oder --episodes-per-update verringern. "
                        "Mit diesen unvollständigen Daten wurde nicht trainiert."
                    )
                if len(collector.buffer.unfinished_index()):
                    raise RuntimeError("REINFORCE darf hier nur aus vollständigen Episoden lernen.")
                return result

        def record_episode(episode_batch):
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
            if on_episode is not None:
                on_episode(info)
            return None

        environments = SubprocVectorEnv(factories, context="spawn")
        collector = None
        try:
            buffer = VectorReplayBuffer(
                self.buffer_capacity, workers, ignore_obs_next=True,
            )
            collector = CompleteEpisodeCollector(
                self.algorithm, environments, buffer,
                on_episode_done_hook=record_episode,
            )
            params = OnPolicyTrainerParams(
                training_collector=collector,
                collection_step_num_env_steps=None,
                collection_step_num_episodes=min(self.episodes_per_update, total_episodes),
                max_epochs=math.ceil(total_episodes / self.episodes_per_update),
                epoch_num_steps=1, batch_size=self.batch_size,
                update_step_num_repetitions=1, verbose=False, show_progress=False,
            )

            def prepare_collection(epoch, step):
                params.collection_step_num_episodes = min(
                    self.episodes_per_update, total_episodes - self.episodes_collected,
                )

            params.training_fn = prepare_collection
            trainer = OnPolicyTrainer(self.algorithm, params)
            trainer.reset()
            while self.episodes_collected < total_episodes:
                statistics = trainer.execute_epoch()
                losses = statistics.training_stat.loss
                self.last_loss = float(losses.mean)
                # Adams gespeicherter Schrittzähler zählt die echten Gewichtsänderungen.
                self.gradient_updates = 0
                for state in self.algorithm.optim.state_dict()["state"].values():
                    self.gradient_updates = max(self.gradient_updates, int(state.get("step", 0)))
                if not math.isfinite(self.last_loss):
                    raise RuntimeError("Das REINFORCE-Training lieferte keinen endlichen Loss.")
                if on_update is not None:
                    on_update(self, {
                        "episodes": self.episodes_collected, "timesteps": self.num_timesteps,
                        "gradient_updates": self.gradient_updates, "last_loss": self.last_loss,
                    })
            return self
        finally:
            if collector is not None:
                collector.close()
            else:
                environments.close()

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
