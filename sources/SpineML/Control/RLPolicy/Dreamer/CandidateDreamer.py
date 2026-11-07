"""Trainiert Weltmodell und Steuerung in getrennten Phasen."""

from __future__ import annotations

from collections import deque
import math
from pathlib import Path
import pickle
import sys
from time import perf_counter, time_ns

import numpy as np
from gymnasium import spaces
from stable_baselines3.common.base_class import BaseAlgorithm
from stable_baselines3.common.utils import configure_logger

from ..Shared.CandidateQNetwork import _positive_size
from .DreamerEpisodeRunner import DreamerEpisodeRunner
from .DreamerNetworks import CandidateDreamerPolicy
from .EpisodeDataset import EpisodeDataset
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
        self.last_validation_metrics = {}
        self.training_phase = "not_started"
        self.phase_progress = {}
        self.phase_elapsed_seconds = {}
        self.world_model_updates_completed = 0
        self.imagination_updates_completed = 0
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
        self.last_validation_metrics = {}
        self.phase_elapsed_seconds = {}
        self.world_model_updates_completed = 0
        self.imagination_updates_completed = 0
        self.ep_info_buffer = deque(maxlen=self._stats_window_size)
        self.ep_success_buffer = deque(maxlen=self._stats_window_size)
        if not self._custom_logger:
            self._logger = configure_logger(self.verbose, self.tensorboard_log, "CandidateDreamer", True)
        return self._init_callback(callback)

    def _record_episode(self, episode, callback, store_in_replay=True):
        decisions = len(episode["actions"])
        self.num_timesteps += decisions
        self.collected_transitions += decisions
        self.episodes_collected += 1
        self._episode_num += 1
        if store_in_replay:
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

    def _report_phase(self, phase, completed, total, phase_callback, metrics=None):
        self.training_phase = phase
        self.phase_progress = {"completed": completed, "total": total}
        if phase_callback is not None:
            phase_callback(phase, completed, total, dict(metrics or {}))

    def _learn_offline_updates(self, phase, updates, phase_callback):
        # Hier sind sämtliche Simulations-Worker bereits beendet.
        started_at = perf_counter()
        self._report_phase(phase, 0, updates, phase_callback)
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)
        try:
            for update in range(updates):
                windows = self.replay_buffer.sample_sequences(
                    self.batch_size, self.sequence_length, self._replay_rng,
                )
                if phase == "world_model":
                    metrics = self.policy.train_world_model(windows)
                    self.world_model_updates_completed += 1
                else:
                    metrics = self.policy.train_imagination(windows)
                    self.imagination_updates_completed += 1
                self.last_train_metrics = {}
                for name, value in metrics.items():
                    value = float(value)
                    if not math.isfinite(value):
                        raise ValueError(f"Dreamer lieferte eine nichtendliche Trainingskennzahl: {name}.")
                    self.last_train_metrics[name] = value
                    self.logger.record(f"{phase}/{name}", value)
                self.last_loss = self.last_train_metrics.get("loss")
                self._n_updates += 1
                self.completed_batches += 1
                self.logger.record(f"{phase}/updates", update + 1)
                self.logger.dump(step=self._n_updates)
                self._report_phase(phase, update + 1, updates, phase_callback, self.last_train_metrics)
        finally:
            self.phase_elapsed_seconds[phase] = perf_counter() - started_at

    def learn(
        self, total_episodes, callback=None, *, world_model_updates=10,
        imagination_updates=10, phase_callback=None, data_directory=None,
    ):
        """Sammelt zuerst Daten und trainiert danach ohne weitere Salabim-Aufrufe."""
        total_episodes = _positive_size("total_episodes", total_episodes)
        if total_episodes < 2:
            raise ValueError("Die getrennten Dreamer-Phasen benötigen mindestens zwei Episoden: Lernen und Prüfung.")
        world_model_updates = _positive_size("world_model_updates", world_model_updates)
        imagination_updates = _positive_size("imagination_updates", imagination_updates)
        if not self.episode_factories:
            raise ValueError("Dreamer benötigt episode_factories für unabhängige Simulations-Worker.")
        callback = self._prepare_training(total_episodes, callback)
        callback.on_training_start(locals(), globals())
        validation_replay = SequenceReplay(1, self.replay_transitions)
        if data_directory is None:
            self.replay_buffer = SequenceReplay(total_episodes, sys.maxsize)
        else:
            self.replay_buffer = EpisodeDataset(data_directory)
        try:
            started_at = perf_counter()
            self._report_phase("collection", 0, total_episodes, phase_callback)
            self._episode_runner = DreamerEpisodeRunner(
                self.episode_factories, self.observation_space, self.action_space,
                self.policy_kwargs, self.seed or 0,
            )
            callback.on_rollout_start()
            try:
                self._episode_runner.start(
                    self.policy.state_dict(), self.policy_version, total_episodes=total_episodes,
                )
                while not self._episode_runner.finished:
                    episode = self._episode_runner.get_completed()
                    if episode is None:
                        continue
                    # Diese vollständige Episode wird nie für Parameteränderungen verwendet.
                    validation_episode = episode["collection_ticket"] == total_episodes
                    if validation_episode:
                        validation_replay.add(episode)
                        if data_directory is not None:
                            path = Path(data_directory) / "validation_episode.pkl"
                            with path.open("xb") as stream:
                                pickle.dump(episode, stream, protocol=pickle.HIGHEST_PROTOCOL)
                    if not self._record_episode(episode, callback, store_in_replay=not validation_episode):
                        self.training_phase = "cancelled"
                        return self
                    self._report_phase("collection", self.episodes_collected, total_episodes, phase_callback)
            finally:
                self._episode_runner.close()
                self._episode_runner = None
                self.phase_elapsed_seconds["collection"] = perf_counter() - started_at
            callback.on_rollout_end()

            self._learn_offline_updates("world_model", world_model_updates, phase_callback)

            started_at = perf_counter()
            self._report_phase("validation", 0, 1, phase_callback)
            validation_rng = np.random.default_rng(self.seed)
            windows = validation_replay.sample_sequences(
                self.batch_size, self.sequence_length, validation_rng,
            )
            self.last_validation_metrics = self.policy.validate_sequences(windows)
            self.last_validation_metrics["held_out_episodes"] = len(validation_replay)
            validation_seed = validation_replay.episodes[0].get("seed")
            if validation_seed is not None:
                self.last_validation_metrics["held_out_seed"] = int(validation_seed)
            self.phase_elapsed_seconds["validation"] = perf_counter() - started_at
            self._report_phase("validation", 1, 1, phase_callback, self.last_validation_metrics)
            # Ab hier bleiben Encoder, Dynamik, Decoder und Vorhersageköpfe unverändert.
            self._learn_offline_updates("imagination", imagination_updates, phase_callback)
            self.policy_version += 1
            self._report_phase("finished", 1, 1, phase_callback)
        finally:
            callback.on_training_end()
        return self
