"""Trainiert Dreamer zentral mit vollständigen Episoden unabhängiger CPU-Worker."""

from __future__ import annotations

from collections import deque
import math
from pathlib import Path
import pickle
from time import time_ns

import numpy as np
from gymnasium import spaces
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.utils import configure_logger

from ..Shared.CandidateQNetwork import _positive_size
from .DreamerEpisodeRunner import DreamerEpisodeRunner
from .DreamerNetworks import CandidateDreamerPolicy
from .SequenceReplay import SequenceReplay


class CandidateDreamer(BaseAlgorithm):
    """Das Weltmodell lernt reale Verläufe; Actor und Critic lernen in seiner Vorstellung."""

    policy_aliases = {"CandidateDreamerPolicy": CandidateDreamerPolicy}

    def __init__(
        self,
        policy=CandidateDreamerPolicy,
        env=None,
        learning_rate=0.0003,
        batch_size=8,
        sequence_length=32,
        imagination_horizon=15,
        updates_per_episode=1,
        replay_episodes=8,
        replay_transitions=10_000,
        gamma=1.0,
        policy_kwargs=None,
        episode_factories=None,
        seed=None,
        device="auto",
        verbose=0,
        tensorboard_log=None,
        _init_setup_model=True,
    ):
        selected_policy_kwargs = dict(policy_kwargs or {})
        selected_policy_kwargs["imagination_horizon"] = _positive_size(
            "imagination_horizon", imagination_horizon,
        )
        if not math.isfinite(gamma) or not 0 < gamma <= 1:
            raise ValueError("gamma muss größer als 0 und höchstens 1 sein.")
        selected_policy_kwargs["gamma"] = float(gamma)
        super().__init__(
            policy, env, learning_rate, policy_kwargs=selected_policy_kwargs,
            seed=seed, device=device, verbose=verbose, tensorboard_log=tensorboard_log,
            support_multi_env=True, supported_action_spaces=(spaces.Discrete,),
        )
        self.batch_size = _positive_size("batch_size", batch_size)
        self.sequence_length = _positive_size("sequence_length", sequence_length)
        self.imagination_horizon = int(imagination_horizon)
        self.updates_per_episode = _positive_size("updates_per_episode", updates_per_episode)
        self.replay_episodes = _positive_size("replay_episodes", replay_episodes)
        self.replay_transitions = _positive_size("replay_transitions", replay_transitions)
        self.gamma = float(gamma)
        self.episode_factories = episode_factories
        self.replay_buffer = None
        self._replay_rng = np.random.default_rng(seed)
        self._episode_runner = None
        self.total_episodes = 0
        self.episodes_collected = 0
        self.collected_transitions = 0
        self.completed_batches = 0
        self.policy_version = 0
        self.worker_pids = []
        self.last_loss = None
        self.last_train_metrics = {}
        if _init_setup_model:
            self._setup_model()

    def _setup_model(self):
        if not issubclass(self.policy_class, CandidateDreamerPolicy):
            raise ValueError("CandidateDreamer benötigt CandidateDreamerPolicy.")
        self._setup_lr_schedule()
        self.set_random_seed(self.seed)
        self.policy = self.policy_class(
            self.observation_space, self.action_space, self.lr_schedule,
            **self.policy_kwargs,
        ).to(self.device)
        self.replay_buffer = SequenceReplay(self.replay_episodes, self.replay_transitions)

    def _get_torch_save_params(self):
        return ["policy", "policy.optimizer"], []

    def _excluded_save_params(self):
        excluded = super()._excluded_save_params()
        excluded.extend(("episode_factories", "_episode_runner", "replay_buffer"))
        return excluded

    def save_replay_buffer(self, path):
        """Speichert den Sequenzspeicher separat; nur eigenen Pickle-Dateien vertrauen."""
        with Path(path).open("wb") as stream:
            pickle.dump(self.replay_buffer, stream, protocol=pickle.HIGHEST_PROTOCOL)

    def predict(self, observation, state=None, episode_start=None, deterministic=False):
        return self.policy.predict(
            observation, state=state, episode_start=episode_start, deterministic=deterministic,
        )

    def _prepare_training(self, total_episodes, callback):
        # Keine Salabim-Episode im Hauptprozess starten: nur Zähler und Anzeige vorbereiten.
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
            self._logger = configure_logger(self.verbose, self.tensorboard_log, "CandidateDreamer", True)
        return self._init_callback(callback)

    def _record_episode(self, episode, callback):
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
            "worker_pid": episode["worker_pid"],
            "worker_id": episode["worker_id"],
            "episode_elapsed_seconds": episode["elapsed_seconds"],
        })
        dones = np.array([True])
        self._update_info_buffer([info], dones)
        callback.update_locals({"infos": [info], "dones": dones})
        return callback.on_step()

    def _train_and_publish(self, callback):
        callback.on_rollout_end()
        self._current_progress_remaining = max(1 - self.episodes_collected / self.total_episodes, 0)
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)
        for _ in range(self.updates_per_episode):
            windows = self.replay_buffer.sample_sequences(
                self.batch_size, self.sequence_length, self._replay_rng,
            )
            metrics = self.policy.train_sequences(windows)
            self.last_train_metrics = {}
            for name, value in metrics.items():
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError(f"Dreamer lieferte eine nichtendliche Trainingskennzahl: {name}.")
                self.last_train_metrics[name] = value
                self.logger.record(f"train/{name}", value)
            self.last_loss = self.last_train_metrics.get("loss")
            self._n_updates += 1
        self.completed_batches += 1
        self.policy_version += 1
        self._episode_runner.publish(self.policy.state_dict(), self.policy_version)
        self.logger.record("time/total_timesteps", self.num_timesteps, exclude="tensorboard")
        self.logger.record("rollout/episodes", self.episodes_collected)
        self.logger.record("rollout/policy_version", self.policy_version)
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("replay/episodes", len(self.replay_buffer))
        self.logger.record("replay/transitions", self.replay_buffer.transition_count)
        self.logger.dump(step=self.num_timesteps)
        callback.on_rollout_start()

    def learn(self, total_episodes: int, callback=None):
        """Sammelt genau dieses Episodenbudget; fertige Episoden lösen Lernschritte aus."""
        if not self.episode_factories:
            raise ValueError("Dreamer benötigt episode_factories für unabhängige Simulations-Worker.")
        callback = self._prepare_training(total_episodes, callback)
        callback.on_training_start(locals(), globals())
        self._episode_runner = DreamerEpisodeRunner(
            self.episode_factories, self.observation_space, self.action_space,
            self.policy_kwargs, self.seed or 0,
        )
        try:
            self._episode_runner.start(
                self.policy.state_dict(), self.policy_version, total_episodes=self.total_episodes,
            )
            callback.on_rollout_start()
            while not self._episode_runner.finished:
                episode = self._episode_runner.get_completed()
                if episode is None:
                    continue
                if not self._record_episode(episode, callback):
                    break
                self._train_and_publish(callback)
            callback.on_rollout_end()
        finally:
            self._episode_runner.close()
            self._episode_runner = None
            callback.on_training_end()
        return self
