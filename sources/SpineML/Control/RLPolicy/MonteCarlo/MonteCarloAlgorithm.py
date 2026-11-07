from __future__ import annotations

import math
import pickle
from collections import deque
from pathlib import Path
from time import time_ns
from typing import Any

import numpy as np

try:
    import torch as th
    from gymnasium import spaces
    from stable_baselines3.common.base_class import BaseAlgorithm
    from stable_baselines3.common.policies import BasePolicy
    from stable_baselines3.common.type_aliases import Schedule
    from stable_baselines3.common.utils import configure_logger
    from torch import nn
    from torch.nn import functional as F
except ImportError as error:
    raise ImportError(
        'Kandidaten-Monte-Carlo benötigt die Trainingspakete: python -m pip install ".[rl-training]"'
    ) from error

from ..Shared.CandidateQNetwork import (
    CandidateFeaturesExtractor, CandidateQNetwork, _positive_size, candidate_action_mask,
)
from .AsyncEpisodeRunner import AsyncEpisodeRunner
from .EpisodeReplayBuffer import (
    EpisodeReplayBuffer, discounted_returns, effective_sample_size,
    normalise_log_weights, suffix_log_importance_weights,
)


def _stack_observations(observations: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    batch = {}
    for name in observations[0]:
        values = []
        for observation in observations:
            values.append(observation[name])
        batch[name] = np.stack(values)
    return batch


class MonteCarloPolicy(BasePolicy):
    """Ein Kandidaten-Q-Netz; Monte Carlo benötigt kein Target-Netz."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        lr_schedule: Schedule,
        *,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
        activation_fn: type[nn.Module] = nn.Tanh,
        normalize_images: bool = False,
        optimizer_class: type[th.optim.Optimizer] = th.optim.Adam,
        optimizer_kwargs: dict[str, Any] | None = None,
    ):
        self.embedding_dim = _positive_size("embedding_dim", embedding_dim)
        self.hidden_dim = _positive_size("hidden_dim", hidden_dim)
        if not isinstance(action_space, spaces.Discrete) or action_space.start != 0:
            raise ValueError("Die Kandidaten-Policy benötigt Discrete-Aktionen ab Index 0.")
        if not isinstance(observation_space, spaces.Dict):
            raise ValueError("Die Kandidaten-Policy benötigt einen Dict-Beobachtungsraum.")
        if observation_space["candidates"].shape[0] != action_space.n:
            raise ValueError("Aktionsraum und Kandidatenzahl müssen übereinstimmen.")
        super().__init__(
            observation_space, action_space,
            features_extractor_class=CandidateFeaturesExtractor,
            features_extractor_kwargs={"embedding_dim": self.embedding_dim, "activation_fn": activation_fn},
            normalize_images=normalize_images,
            optimizer_class=optimizer_class, optimizer_kwargs=optimizer_kwargs,
        )
        self.activation_fn = activation_fn
        features_extractor = self.make_features_extractor()
        self.q_net = CandidateQNetwork(
            observation_space, action_space, features_extractor,
            features_dim=features_extractor.features_dim,
            activation_fn=activation_fn, normalize_images=normalize_images,
            hidden_dim=self.hidden_dim,
        )
        self.optimizer = optimizer_class(self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs)

    def forward(self, observation: dict[str, th.Tensor], deterministic: bool = True) -> th.Tensor:
        return self._predict(observation, deterministic)

    def _predict(self, observation: dict[str, th.Tensor], deterministic: bool = True) -> th.Tensor:
        return self.q_net._predict(observation, deterministic)

    def _get_constructor_parameters(self) -> dict[str, Any]:
        data = super()._get_constructor_parameters()
        data.update(
            lr_schedule=self._dummy_schedule,
            embedding_dim=self.embedding_dim, hidden_dim=self.hidden_dim,
            activation_fn=self.activation_fn,
            optimizer_class=self.optimizer_class, optimizer_kwargs=self.optimizer_kwargs,
        )
        return data


class MonteCarloAlgorithm(BaseAlgorithm):
    """Lernt aus vollständigen asynchronen Episoden mit korrigierter Wiederverwendung."""

    policy_aliases = {
        "MonteCarloPolicy": MonteCarloPolicy,
        "MultiInputPolicy": MonteCarloPolicy,
    }

    def __init__(
        self,
        policy: str | type[MonteCarloPolicy] = MonteCarloPolicy,
        env=None,
        learning_rate: float | Schedule = 0.0001,
        batch_size: int = 64,
        epochs: int = 4,
        gamma: float = 1.0,
        exploration_fraction: float = 0.3,
        exploration_initial_eps: float = 1.0,
        exploration_final_eps: float = 0.05,
        max_grad_norm: float = 10.0,
        policy_kwargs: dict[str, Any] | None = None,
        seed: int | None = None,
        device: str | th.device = "auto",
        verbose: int = 0,
        tensorboard_log: str | None = None,
        episode_factories=None,
        replay_episodes: int = 8,
        replay_transitions: int = 10_000,
        train_every_episodes: int = 4,
        replay_sample_episodes: int = 4,
        _init_setup_model: bool = True,
    ):
        super().__init__(
            policy, env, learning_rate, policy_kwargs=policy_kwargs,
            seed=seed, device=device, verbose=verbose, tensorboard_log=tensorboard_log,
            support_multi_env=True, supported_action_spaces=(spaces.Discrete,),
        )
        self.batch_size = _positive_size("batch_size", batch_size)
        self.epochs = _positive_size("epochs", epochs)
        if not 0 <= gamma <= 1:
            raise ValueError("gamma muss zwischen 0 und 1 liegen.")
        if not 0 < exploration_fraction <= 1:
            raise ValueError("exploration_fraction muss größer als 0 und höchstens 1 sein.")
        if not 0 <= exploration_initial_eps <= 1 or not 0 <= exploration_final_eps <= 1:
            raise ValueError("Epsilon muss zwischen 0 und 1 liegen.")
        if not math.isfinite(max_grad_norm) or max_grad_norm <= 0:
            raise ValueError("max_grad_norm muss endlich und positiv sein.")
        self.gamma = gamma
        self.exploration_fraction = exploration_fraction
        self.exploration_initial_eps = exploration_initial_eps
        self.exploration_final_eps = exploration_final_eps
        self.exploration_rate = exploration_initial_eps
        self.max_grad_norm = max_grad_norm
        self.completed_batches = 0
        self.total_episodes = 0
        self.episodes_collected = 0
        self.collected_transitions = 0
        self.last_return_min = None
        self.last_return_max = None
        self.last_loss = None
        self.episode_factories = episode_factories
        self.replay_episodes = _positive_size("replay_episodes", replay_episodes)
        self.replay_transitions = _positive_size("replay_transitions", replay_transitions)
        self.train_every_episodes = _positive_size("train_every_episodes", train_every_episodes)
        self.replay_sample_episodes = _positive_size("replay_sample_episodes", replay_sample_episodes)
        self.replay_buffer = EpisodeReplayBuffer(self.replay_episodes, self.replay_transitions)
        self.policy_version = 0
        self.worker_pids = []
        self.last_importance_ess = None
        self.last_importance_max_weight = None
        self._episode_runner = None
        if _init_setup_model:
            self._setup_model()

    def _setup_model(self) -> None:
        if not issubclass(self.policy_class, MonteCarloPolicy):
            raise ValueError("MonteCarloAlgorithm benötigt MonteCarloPolicy.")
        self._setup_lr_schedule()
        self.set_random_seed(self.seed)
        self.policy = self.policy_class(
            self.observation_space, self.action_space, self.lr_schedule,
            **self.policy_kwargs,
        ).to(self.device)

    def _get_torch_save_params(self) -> tuple[list[str], list[str]]:
        return ["policy", "policy.optimizer"], []

    def _excluded_save_params(self) -> list[str]:
        excluded = super()._excluded_save_params()
        excluded.extend(("episode_factories", "_episode_runner", "replay_buffer"))
        return excluded

    def save_replay_buffer(self, path) -> None:
        """Speichert vollständige Episoden separat; nur eigene Pickle-Dateien vertrauen."""
        with Path(path).open("wb") as stream:
            pickle.dump(self.replay_buffer, stream, protocol=pickle.HIGHEST_PROTOCOL)

    def predict(
        self,
        observation: np.ndarray | dict[str, np.ndarray],
        state: tuple[np.ndarray, ...] | None = None,
        episode_start: np.ndarray | None = None,
        deterministic: bool = False,
    ) -> tuple[np.ndarray, tuple[np.ndarray, ...] | None]:
        mask = np.asarray(observation["action_mask"], dtype=bool)
        if mask.ndim == 1:
            mask = mask[np.newaxis, :]
        if mask.ndim != 2 or mask.shape[1] != self.action_space.n or not mask.any(axis=1).all():
            raise ValueError("Eine Aktionsauswahl benötigt gültige Kandidatenmasken.")
        actions, state = self.policy.predict(observation, state, episode_start, deterministic=True)
        if not deterministic and self.exploration_rate > 0:
            original_shape = actions.shape
            actions = actions.reshape(-1).copy()
            for index in range(mask.shape[0]):
                if np.random.random() < self.exploration_rate:
                    actions[index] = np.random.choice(np.flatnonzero(mask[index]))
            actions = actions.reshape(original_shape)
        return actions, state

    def _update_exploration(self) -> None:
        fraction = self.episodes_collected / max(self.total_episodes, 1)
        fraction = min(fraction / self.exploration_fraction, 1.0)
        self.exploration_rate = self.exploration_initial_eps + fraction * (
            self.exploration_final_eps - self.exploration_initial_eps
        )

    def _target_action_probabilities(self, observations, actions):
        """Bewertet damalige Aktionen unter der vor dieser Lernphase gültigen Policy."""
        probabilities = []
        for start in range(0, len(actions), self.batch_size):
            stop = min(start + self.batch_size, len(actions))
            tensors, _ = self.policy.obs_to_tensor(_stack_observations(observations[start:stop]))
            with th.no_grad():
                greedy_actions = self.policy.q_net._predict(tensors).cpu().numpy()
            for offset, greedy_action in enumerate(greedy_actions):
                index = start + offset
                valid_count = int(np.count_nonzero(observations[index]["action_mask"]))
                probability = self.exploration_rate / valid_count
                if int(actions[index]) == int(greedy_action):
                    probability += 1.0 - self.exploration_rate
                probabilities.append(float(probability))
        return probabilities

    def _prepare_replay_data(self):
        """Berechnet volle Returns und Korrekturgewichte, bevor Netzparameter geändert werden."""
        self.policy.set_training_mode(False)
        episodes = self.replay_buffer.sample_episodes(self.replay_sample_episodes, np.random)
        observations = []
        actions = []
        returns = []
        log_weights = []
        for episode in episodes:
            target_probabilities = self._target_action_probabilities(
                episode["observations"], episode["actions"],
            )
            episode_log_weights = suffix_log_importance_weights(
                target_probabilities, episode["behavior_probabilities"],
            )
            observations.extend(episode["observations"])
            actions.extend(episode["actions"])
            returns.extend(discounted_returns(episode["rewards"], self.gamma))
            log_weights.extend(episode_log_weights)
        weights = normalise_log_weights(log_weights)
        self.last_importance_ess = effective_sample_size(weights)
        self.last_importance_max_weight = float(weights.max())
        return observations, actions, returns, weights

    def _prepare_training_minibatch(self, observations, actions, returns, indices):
        """Wandelt ausgewählte Zustände, Aktionen und Returns in Eingaben für das Netz um."""
        batch_observations = []
        batch_actions = []
        batch_returns = []
        for index in indices:
            batch_observations.append(observations[index])
            batch_actions.append(actions[index])
            batch_returns.append(returns[index])
        observation_tensors, _ = self.policy.obs_to_tensor(_stack_observations(batch_observations))
        action_tensor = th.as_tensor(batch_actions, dtype=th.long, device=self.device).reshape(-1, 1)
        return_tensor = th.as_tensor(batch_returns, dtype=th.float32, device=self.device).reshape(-1, 1)
        return observation_tensors, action_tensor, return_tensor

    def _train_replay(self) -> None:
        observations, actions, returns, weights = self._prepare_replay_data()
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)
        self.last_return_min = float(min(returns))
        self.last_return_max = float(max(returns))
        losses = []
        for _ in range(self.epochs):
            order = np.random.permutation(len(actions))
            for start in range(0, len(order), self.batch_size):
                indices = order[start:start + self.batch_size]
                observation_tensors, action_tensor, return_tensor = self._prepare_training_minibatch(
                    observations, actions, returns, indices,
                )
                masks = candidate_action_mask(observation_tensors, self.action_space.n)
                if not bool(th.gather(masks, dim=1, index=action_tensor).all()):
                    raise ValueError("Eine gespeicherte Monte-Carlo-Aktion ist ungültig.")
                predictions = self.policy.q_net(observation_tensors).gather(dim=1, index=action_tensor)
                # Das Lernziel bleibt der tatsächliche Return; korrigiert wird der Einfluss.
                weight_tensor = th.as_tensor(weights[indices], dtype=th.float32, device=self.device).reshape(-1, 1)
                squared_errors = F.mse_loss(predictions, return_tensor, reduction="none")
                loss = (weight_tensor * squared_errors).sum() * len(actions) / len(indices)
                self.policy.optimizer.zero_grad()
                loss.backward()
                th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                self.policy.optimizer.step()
                self._n_updates += 1
                losses.append(float(loss.item()))
        self.last_loss = float(np.mean(losses))
        self.logger.record("train/loss", self.last_loss)
        self.logger.record("train/return_min", self.last_return_min)
        self.logger.record("train/return_max", self.last_return_max)
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/batch_transitions", len(actions))
        self.logger.record("train/importance_ess", self.last_importance_ess)
        self.logger.record("train/importance_max_weight", self.last_importance_max_weight)
        self.logger.record("replay/episodes", len(self.replay_buffer))
        self.logger.record("replay/transitions", self.replay_buffer.transition_count)
        self.logger.record("replay/oversized_episode", self.replay_buffer.oversized_episode)

    def _record_episode(self, episode, callback):
        """Übernimmt einen fertigen Verlauf, ohne auf die anderen Worker zu warten."""
        decisions = len(episode["actions"])
        self.num_timesteps += decisions
        self.collected_transitions += decisions
        self.episodes_collected += 1
        self._episode_num += 1
        self.replay_buffer.add(episode)
        if episode["worker_pid"] not in self.worker_pids:
            self.worker_pids.append(episode["worker_pid"])
        info = dict(episode["info"])
        info.update({
            "policy_version": episode["policy_version"],
            "worker_pid": episode["worker_pid"], "worker_id": episode["worker_id"],
            "episode_epsilon": episode["epsilon"],
            "episode_elapsed_seconds": episode["elapsed_seconds"],
        })
        dones = np.array([True])
        self._update_info_buffer([info], dones)
        callback.update_locals({"infos": [info], "dones": dones})
        return callback.on_step()

    def _learn_and_publish(self, callback):
        callback.on_rollout_end()
        self._current_progress_remaining = max(1 - self.episodes_collected / self.total_episodes, 0)
        self._update_exploration()
        self._train_replay()
        self.completed_batches += 1
        self.policy_version += 1
        self._episode_runner.publish(self.policy.state_dict(), self.exploration_rate, self.policy_version)
        self.logger.record("time/total_timesteps", self.num_timesteps, exclude="tensorboard")
        self.logger.record("rollout/episodes", self._episode_num)
        self.logger.record("rollout/exploration_rate", self.exploration_rate)
        self.logger.record("rollout/policy_version", self.policy_version)
        self.logger.dump(step=self.num_timesteps)
        callback.on_rollout_start()

    def _prepare_training(self, total_episodes, callback):
        """Bereitet einen Trainingslauf mit eigenem Episodenbudget vor, ohne eine Simulation zu starten."""
        self.total_episodes = _positive_size("total_episodes", total_episodes)
        self.episodes_collected = 0
        self.num_timesteps = 0
        self.collected_transitions = 0
        self.completed_batches = 0
        self._episode_num = 0
        self._num_timesteps_at_start = 0
        self._current_progress_remaining = 1.0
        self.start_time = time_ns()
        self.worker_pids = []
        self.ep_info_buffer = deque(maxlen=self._stats_window_size)
        self.ep_success_buffer = deque(maxlen=self._stats_window_size)
        if not self._custom_logger:
            self._logger = configure_logger(self.verbose, self.tensorboard_log, "MonteCarloAlgorithm", True)
        return self._init_callback(callback)

    def learn(self, total_episodes: int, callback=None) -> MonteCarloAlgorithm:
        """Sammelt die angegebene Anzahl vollständiger Episoden und trainiert mit dem Replay Buffer."""
        if not self.episode_factories:
            raise ValueError("Asynchrones Training benötigt episode_factories für die Worker.")
        if self.exploration_initial_eps <= 0 or self.exploration_final_eps <= 0:
            raise ValueError("Off-Policy-Monte-Carlo benötigt positive Explorationswahrscheinlichkeiten.")
        callback = self._prepare_training(total_episodes, callback)
        callback.on_training_start(locals(), globals())
        pending_episodes = 0
        keep_training = True
        self._update_exploration()
        self._episode_runner = AsyncEpisodeRunner(
            self.episode_factories, self.observation_space, self.action_space,
            self.policy_kwargs, self.seed or 0,
        )
        try:
            self._episode_runner.start(
                self.policy.state_dict(), self.exploration_rate, self.policy_version,
                total_episodes=self.total_episodes,
            )
            callback.on_rollout_start()
            while not self._episode_runner.finished:
                episode = self._episode_runner.get_completed()
                if episode is None:
                    continue
                keep_training = self._record_episode(episode, callback)
                if not keep_training:
                    break
                pending_episodes += 1
                if pending_episodes >= self.train_every_episodes:
                    self._learn_and_publish(callback)
                    pending_episodes = 0
            if pending_episodes and keep_training:
                self._learn_and_publish(callback)
            callback.on_rollout_end()
        finally:
            self._episode_runner.close()
            self._episode_runner = None
            callback.on_training_end()
        return self
