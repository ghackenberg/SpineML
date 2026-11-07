"""Sammelt unabhängige Salabim-Episoden für den zentralen Dreamer-Lerner."""

from __future__ import annotations

from io import BytesIO
import multiprocessing
import os
import queue
from time import perf_counter
import traceback

import numpy as np


def _actor_learning_rate(progress):
    return 0.0


def _copy_observation(observation):
    copied = {}
    for name, values in observation.items():
        copied[name] = values.copy()
    return copied


def _send_result(results, message, abort):
    # Eine begrenzte Warteschlange verhindert unbegrenzten RAM-Verbrauch.
    while not abort.is_set():
        try:
            results.put(message, timeout=0.2)
            return
        except queue.Full:
            pass


def _run_dreamer_worker(
    worker_id, factory, observation_space, action_space, policy_kwargs,
    seed, saved_parameters, version, results, abort, remaining_episodes,
):
    environment = None
    failure = None
    try:
        import torch as th
        from .DreamerNetworks import CandidateDreamerPolicy

        th.set_num_threads(1)
        # Nur das Netz erhält einen eigenen Torch-Seed; Salabims Zufallsfolge bleibt getrennt.
        th.manual_seed(seed + worker_id)
        environment = factory()
        policy = CandidateDreamerPolicy(
            observation_space, action_space, _actor_learning_rate, **policy_kwargs,
        ).to("cpu")
        # Alle Sammel-Episoden verwenden denselben unveränderten Netzstand.
        parameters = th.load(BytesIO(saved_parameters), map_location="cpu", weights_only=True)
        policy.load_state_dict(parameters, strict=True)
        del parameters, saved_parameters
        policy.set_training_mode(False)
        episode_index = 0
        while not abort.is_set():
            with remaining_episodes.get_lock():
                if abort.is_set() or remaining_episodes.value == 0:
                    break
                # Eindeutige Nummer vor dem Start, unabhängig von der späteren Laufdauer.
                collection_ticket = remaining_episodes.value
                remaining_episodes.value -= 1
            # Das rekurrente Gedächtnis beginnt für jede Episode wieder leer.
            recurrent_state = None
            started_at = perf_counter()
            observation, reset_info = environment.reset()
            observations = [_copy_observation(observation)]
            actions = []
            rewards = []
            terminals = []
            truncations = []
            terminated = False
            truncated = False
            info = reset_info

            while not terminated and not truncated:
                if abort.is_set():
                    return
                with th.no_grad():
                    selected, recurrent_state = policy.predict(
                        observation, state=recurrent_state, deterministic=False,
                    )
                action = int(np.asarray(selected).item())
                if not 0 <= action < action_space.n or not observation["action_mask"][action]:
                    raise ValueError("Dreamer hat keinen gültigen Aktionskandidaten gewählt.")
                observation, reward, terminated, truncated, info = environment.step(action)
                actions.append(action)
                rewards.append(float(reward))
                terminals.append(bool(terminated))
                truncations.append(bool(truncated))
                # Auch die letzte Folgebeobachtung gehört zum Verlauf: T Aktionen, T+1 Zustände.
                observations.append(_copy_observation(observation))

            episode_index += 1
            episode = {
                "observations": observations,
                "actions": actions,
                "rewards": rewards,
                "terminals": terminals,
                "truncations": truncations,
                "policy_version": int(version),
                "seed": info.get("episode_seed", reset_info.get("episode_seed")),
                "info": info,
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "worker_id": worker_id,
                "worker_pid": os.getpid(),
                "episode_index": episode_index,
                "collection_ticket": collection_ticket,
                "elapsed_seconds": perf_counter() - started_at,
            }
            _send_result(results, ("episode", worker_id, episode), abort)
            # Ohne gemeinsame Episodenbarriere die nächste Sammel-Episode beginnen.
    except BaseException:
        failure = traceback.format_exc()
    finally:
        if environment is not None:
            try:
                environment.close()
            except BaseException:
                failure = traceback.format_exc()
        if failure is not None:
            _send_result(results, ("error", worker_id, failure), abort)
        _send_result(results, ("done", worker_id, None), abort)
        if abort.is_set():
            results.cancel_join_thread()


class DreamerEpisodeRunner:
    """CPU-Worker sammeln Episoden mit einem festen Netzstand."""

    def __init__(self, factories, observation_space, action_space, policy_kwargs, seed=0):
        self.factories = tuple(factories)
        if not self.factories:
            raise ValueError("Mindestens ein Simulations-Worker ist erforderlich.")
        self.observation_space = observation_space
        self.action_space = action_space
        self.policy_kwargs = dict(policy_kwargs)
        self.seed = int(seed)
        self._context = multiprocessing.get_context("spawn")
        self._results = None
        self._abort = self._context.Event()
        self._remaining_episodes = None
        self._processes = []
        self._worker_count = 0
        self._finished_workers = set()
        self._started = False
        self._closed = False

    def start(self, policy_state, version=0, *, total_episodes: int):
        if self._started or self._closed:
            raise RuntimeError("Dieser Episoden-Runner kann nur einmal gestartet werden.")
        if not isinstance(total_episodes, int) or isinstance(total_episodes, bool) or total_episodes < 1:
            raise ValueError("total_episodes muss eine positive ganze Zahl sein.")
        self._started = True
        self._worker_count = min(len(self.factories), total_episodes)
        try:
            import torch as th

            # Den festen Netzstand nur einmal serialisieren, nicht nach jeder Episode.
            with BytesIO() as stream:
                th.save(policy_state, stream)
                saved_parameters = stream.getvalue()
            self._results = self._context.Queue(maxsize=max(2, self._worker_count))
            self._remaining_episodes = self._context.Value("q", total_episodes)
            for worker_id in range(self._worker_count):
                process = self._context.Process(
                    target=_run_dreamer_worker,
                    args=(
                        worker_id, self.factories[worker_id], self.observation_space,
                        self.action_space, self.policy_kwargs, self.seed, saved_parameters, int(version),
                        self._results, self._abort, self._remaining_episodes,
                    ),
                )
                process.start()
                self._processes.append(process)
        except BaseException:
            self.close()
            raise

    @property
    def finished(self):
        return self._started and len(self._finished_workers) == self._worker_count

    def _check_processes(self):
        for worker_id, process in enumerate(self._processes):
            if process.exitcode is not None and process.exitcode != 0:
                raise RuntimeError(f"Dreamer-Worker {worker_id} endete mit Code {process.exitcode}.")

    def get_completed(self, timeout=0.2):
        """Liefert die nächste fertige Episode, nicht eine feste Worker-Reihenfolge."""
        if not self._started or self._closed:
            raise RuntimeError("Der Episoden-Runner ist nicht aktiv.")
        deadline = perf_counter() + timeout
        while not self.finished:
            self._check_processes()
            try:
                kind, worker_id, episode = self._results.get(timeout=max(deadline - perf_counter(), 0.0))
            except queue.Empty:
                self._check_processes()
                for worker_id, process in enumerate(self._processes):
                    if process.exitcode == 0 and worker_id not in self._finished_workers:
                        raise RuntimeError(f"Dreamer-Worker {worker_id} endete ohne Endmeldung.")
                return None
            if kind == "episode":
                return episode
            if kind == "error":
                raise RuntimeError(f"Dreamer-Worker {worker_id} ist fehlgeschlagen:\n{episode}")
            self._finished_workers.add(worker_id)
        self._check_processes()
        return None

    def close(self):
        """Beendet nur die eigenen Worker und ihre Verbindungen, auch bei Abbruch."""
        if self._closed:
            return
        self._closed = True
        self._abort.set()
        deadline = perf_counter() + 5.0
        for process in self._processes:
            process.join(timeout=max(deadline - perf_counter(), 0.0))
        for process in self._processes:
            if process.is_alive():
                process.terminate()
        for process in self._processes:
            process.join(timeout=2.0)
        if self._results is not None:
            self._results.cancel_join_thread()
            self._results.close()
