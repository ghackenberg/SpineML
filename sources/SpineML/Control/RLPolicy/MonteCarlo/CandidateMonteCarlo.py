from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    import torch as th
    from gymnasium import spaces
    from stable_baselines3.common.base_class import BaseAlgorithm
    from stable_baselines3.common.policies import BasePolicy
    from stable_baselines3.common.type_aliases import Schedule
    from torch import nn
    from torch.nn import functional as F
except ImportError as error:
    raise ImportError(
        'Kandidaten-Monte-Carlo benötigt die Trainingspakete: python -m pip install ".[rl-training]"'
    ) from error

from ..Shared.CandidateQNetwork import (
    CandidateFeaturesExtractor, CandidateQNetwork, _positive_size, candidate_action_mask,
)


def discounted_returns(rewards: list[float], gamma: float) -> list[float]:
    """Berechnet die tatsächliche Restbelohnung ab jeder besuchten Entscheidung."""
    returns = [0.0] * len(rewards)
    remaining_return = 0.0
    for index in range(len(rewards) - 1, -1, -1):
        remaining_return = float(rewards[index]) + gamma * remaining_return
        returns[index] = remaining_return
    return returns


def _stack_observations(observations: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    batch = {}
    for name in observations[0]:
        values = []
        for observation in observations:
            values.append(observation[name])
        batch[name] = np.stack(values)
    return batch


class CandidateMonteCarloPolicy(BasePolicy):
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


class CandidateMonteCarlo(BaseAlgorithm):
    """Trainiert Kandidaten-Q-Werte auf vollständige, frisch beobachtete Returns."""

    policy_aliases = {
        "CandidateMonteCarloPolicy": CandidateMonteCarloPolicy,
        "MultiInputPolicy": CandidateMonteCarloPolicy,
    }

    def __init__(
        self,
        policy: str | type[CandidateMonteCarloPolicy] = CandidateMonteCarloPolicy,
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
        self.episodes_collected = 0
        self.collected_transitions = 0
        self.last_return_min = None
        self.last_return_max = None
        self.last_loss = None
        if _init_setup_model:
            self._setup_model()

    def _setup_model(self) -> None:
        if not issubclass(self.policy_class, CandidateMonteCarloPolicy):
            raise ValueError("CandidateMonteCarlo benötigt CandidateMonteCarloPolicy.")
        self._setup_lr_schedule()
        self.set_random_seed(self.seed)
        self.policy = self.policy_class(
            self.observation_space, self.action_space, self.lr_schedule,
            **self.policy_kwargs,
        ).to(self.device)

    def _get_torch_save_params(self) -> tuple[list[str], list[str]]:
        return ["policy", "policy.optimizer"], []

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
        fraction = self.num_timesteps / max(self._total_timesteps, 1)
        fraction = min(fraction / self.exploration_fraction, 1.0)
        self.exploration_rate = self.exploration_initial_eps + fraction * (
            self.exploration_final_eps - self.exploration_initial_eps
        )

    def _select_actions_for_active_workers(self, observations, active_indices) -> np.ndarray:
        """Wählt Aktionen für laufende Episoden; fertige Worker erhalten den Platzhalter 0."""
        active_observations = {}
        for name, values in observations.items():
            active_observations[name] = values[active_indices]
        selected_actions, _ = self.predict(active_observations, deterministic=False)
        # Der wartende Worker ignoriert den Platzhalter und startet keine neue Simulation.
        actions = np.zeros(self.n_envs, dtype=np.int64)
        actions[active_indices] = selected_actions.reshape(-1)
        return actions

    def _collect_episode_batch(self, callback) -> tuple[list[dict], list[int], list[float], bool]:
        # Jeder Worker startet genau eine Episode mit denselben eingefrorenen Netzgewichten.
        starts = self.env.env_method("start_episode_batch")
        observations = []
        for observation, info in starts:
            observations.append(observation)
        self._last_obs = _stack_observations(observations)
        active = np.ones(self.n_envs, dtype=bool)
        episode_observations = []
        episode_actions = []
        episode_rewards = []
        for _ in range(self.n_envs):
            episode_observations.append([])
            episode_actions.append([])
            episode_rewards.append([])
        callback.on_rollout_start()
        self.policy.set_training_mode(False)
        while active.any():
            active_indices = np.flatnonzero(active)
            actions = self._select_actions_for_active_workers(self._last_obs, active_indices)
            for worker_index in active_indices:
                observation = {}
                for name, values in self._last_obs.items():
                    observation[name] = values[worker_index].copy()
                episode_observations[worker_index].append(observation)
                episode_actions[worker_index].append(int(actions[worker_index]))
            new_observations, rewards, dones, infos = self.env.step(actions)
            self.num_timesteps += len(active_indices)
            self.collected_transitions += len(active_indices)
            for worker_index in active_indices:
                episode_rewards[worker_index].append(float(rewards[worker_index]))
                if dones[worker_index]:
                    active[worker_index] = False
                    self._episode_num += 1
                    self.episodes_collected += 1
            self._last_obs = new_observations
            self._update_info_buffer(infos, dones)
            callback.update_locals({
                "infos": infos, "dones": dones, "rewards": rewards,
                "actions": actions, "new_obs": new_observations,
            })
            if not callback.on_step():
                callback.on_rollout_end()
                return [], [], [], False
        callback.on_rollout_end()
        observations = []
        actions = []
        returns = []
        for worker_index in range(self.n_envs):
            observations.extend(episode_observations[worker_index])
            actions.extend(episode_actions[worker_index])
            returns.extend(discounted_returns(episode_rewards[worker_index], self.gamma))
        return observations, actions, returns, True

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

    def _train_episode_batch(self, observations: list[dict], actions: list[int], returns: list[float]) -> None:
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
                # Nur tatsächliche Returns: kein nächster Q-Wert und kein Target-Netz.
                loss = F.mse_loss(predictions, return_tensor)
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

    def learn(
        self,
        total_timesteps: int,
        callback=None,
        log_interval: int = 1,
        tb_log_name: str = "CandidateMonteCarlo",
        reset_num_timesteps: bool = True,
        progress_bar: bool = False,
    ) -> CandidateMonteCarlo:
        total_timesteps, callback = self._setup_learn(
            total_timesteps, callback, reset_num_timesteps, tb_log_name, progress_bar,
        )
        callback.on_training_start(locals(), globals())
        try:
            while self.num_timesteps < total_timesteps:
                self._update_exploration()
                observations, actions, returns, keep_training = self._collect_episode_batch(callback)
                if not keep_training:
                    break
                self._current_progress_remaining = max(1 - self.num_timesteps / total_timesteps, 0)
                self._train_episode_batch(observations, actions, returns)
                self.completed_batches += 1
                # Die nächste Episode benötigt keine Daten der vorherigen Strategie mehr.
                del observations, actions, returns
                if log_interval is not None and self.completed_batches % log_interval == 0:
                    self.logger.record("time/total_timesteps", self.num_timesteps, exclude="tensorboard")
                    self.logger.record("rollout/episodes", self._episode_num)
                    self.logger.record("rollout/exploration_rate", self.exploration_rate)
                    self.logger.dump(step=self.num_timesteps)
            self._update_exploration()
        finally:
            # Ein späterer learn()-Aufruf beginnt wieder mit vollständigen Episoden.
            self._last_obs = None
            callback.on_training_end()
        return self
