"""Führt vollständige Episoden unabhängig in getrennten CPU-Prozessen aus."""

from __future__ import annotations

import multiprocessing
import os
import queue
from time import perf_counter
import traceback

import numpy as np


def _actor_learning_rate(progress):
    return 0.0


def _send_result(results, message, abort):
    # Ein voller Speicher bremst die Erzeuger, statt beliebig viele Episoden anzuhäufen.
    while not abort.is_set():
        try:
            results.put(message, timeout=0.2)
            return True
        except queue.Full:
            pass
    return False


def _run_episode_worker(
    worker_id, factory, observation_space, action_space, policy_kwargs,
    seed, snapshots, results, stop, abort,
):
    environment = None
    failure = None
    try:
        import torch as th
        from .CandidateMonteCarlo import CandidateMonteCarloPolicy

        th.set_num_threads(1)
        # Die Aktionsauswahl verändert nicht die Zufallsfolge der Salabim-Simulation.
        rng = np.random.default_rng(seed + worker_id)
        environment = factory()
        policy = CandidateMonteCarloPolicy(
            observation_space, action_space, _actor_learning_rate,
            **policy_kwargs,
        ).to("cpu")
        policy.set_training_mode(False)
        episode_index = 0
        while not stop.is_set() and not abort.is_set():
            # Genau ein veröffentlichter Netzstand gilt für die gesamte Episode.
            version, epsilon, saved_parameters = snapshots["latest"]
            parameters = {}
            for name, values in saved_parameters.items():
                parameters[name] = th.from_numpy(values)
            policy.load_state_dict(parameters)
            started_at = perf_counter()
            observation, reset_info = environment.reset()
            observations = []
            actions = []
            rewards = []
            probabilities = []
            terminated = False
            truncated = False
            info = reset_info

            while not terminated and not truncated:
                if abort.is_set():
                    return
                mask = np.asarray(observation["action_mask"], dtype=bool)
                valid_actions = np.flatnonzero(mask)
                if not len(valid_actions):
                    raise ValueError("Eine laufende Episode benötigt einen gültigen Kandidaten.")
                selected, _ = policy.predict(observation, deterministic=True)
                greedy_action = int(np.asarray(selected).item())
                action = greedy_action
                if rng.random() < epsilon:
                    action = int(rng.choice(valid_actions))
                probability = epsilon / len(valid_actions)
                if action == greedy_action:
                    probability += 1.0 - epsilon

                saved_observation = {}
                for name, values in observation.items():
                    saved_observation[name] = values.copy()
                observations.append(saved_observation)
                actions.append(action)
                probabilities.append(float(probability))
                observation, reward, terminated, truncated, info = environment.step(action)
                rewards.append(float(reward))

            episode_index += 1
            episode_seed = info.get("episode_seed", reset_info.get("episode_seed"))
            episode = {
                "observations": observations,
                "actions": actions,
                "rewards": rewards,
                "behavior_probabilities": probabilities,
                "policy_version": int(version),
                "epsilon": float(epsilon),
                "seed": episode_seed,
                "info": info,
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "worker_id": worker_id,
                "worker_pid": os.getpid(),
                "episode_index": episode_index,
                "elapsed_seconds": perf_counter() - started_at,
            }
            if not _send_result(results, ("episode", worker_id, episode), abort):
                return
            # Kein Warten auf andere Episoden oder auf die nächste Lernphase.
    except BaseException:
        failure = traceback.format_exc()
    finally:
        if environment is not None:
            try:
                environment.close()
            except BaseException:
                failure = traceback.format_exc()
        # Fehler und Endmeldung nutzen dieselbe Reihenfolge wie die Episoden.
        if failure is not None:
            _send_result(results, ("error", worker_id, failure), abort)
        _send_result(results, ("done", worker_id, None), abort)
        if abort.is_set():
            results.cancel_join_thread()


class AsyncEpisodeRunner:
    """Startet Worker, veröffentlicht Netzstände und liefert fertige Episoden."""

    def __init__(self, factories, observation_space, action_space, policy_kwargs, seed=0):
        self.factories = tuple(factories)
        if not self.factories:
            raise ValueError("Mindestens ein Simulations-Worker ist erforderlich.")
        self.observation_space = observation_space
        self.action_space = action_space
        self.policy_kwargs = dict(policy_kwargs)
        self.seed = int(seed)
        self._context = multiprocessing.get_context("spawn")
        self._manager = None
        self._snapshots = None
        self._results = None
        self._stop = self._context.Event()
        self._abort = self._context.Event()
        self._processes = []
        self._finished_workers = set()
        self._started = False
        self._closed = False

    def start(self, policy_state, epsilon, version=0):
        if self._started or self._closed:
            raise RuntimeError("Dieser Episoden-Runner kann nur einmal gestartet werden.")
        self._started = True
        try:
            self._manager = self._context.Manager()
            self._snapshots = self._manager.dict()
            self._results = self._context.Queue(maxsize=max(2, len(self.factories)))
            self.publish(policy_state, epsilon, version)
            for worker_id, factory in enumerate(self.factories):
                process = self._context.Process(
                    target=_run_episode_worker,
                    args=(
                        worker_id, factory, self.observation_space, self.action_space,
                        self.policy_kwargs, self.seed, self._snapshots, self._results,
                        self._stop, self._abort,
                    ),
                )
                process.start()
                self._processes.append(process)
        except BaseException:
            self.close()
            raise

    def publish(self, policy_state, epsilon, version):
        if self._snapshots is None or self._closed:
            raise RuntimeError("Der Episoden-Runner ist nicht aktiv.")
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("Epsilon muss zwischen 0 und 1 liegen.")
        # Kopien verhindern, dass laufende Gradientenupdates einen veröffentlichten Stand ändern.
        parameters = {}
        for name, tensor in policy_state.items():
            parameters[name] = tensor.detach().cpu().numpy().copy()
        self._snapshots["latest"] = (int(version), float(epsilon), parameters)

    def request_stop(self):
        """Startet keine neuen Episoden; bereits laufende Episoden werden noch geliefert."""
        self._stop.set()

    @property
    def finished(self):
        # Endmeldungen kommen hinter den Episoden desselben Workers in die Ergebniswarteschlange.
        return self._started and len(self._finished_workers) == len(self.factories)

    def _check_processes(self):
        for worker_id, process in enumerate(self._processes):
            if process.exitcode is not None and process.exitcode != 0:
                raise RuntimeError(f"Simulations-Worker {worker_id} endete mit Code {process.exitcode}.")

    def get_completed(self, timeout=0.2):
        """Liefert die nächste fertige Episode, ohne auf eine bestimmte Worker-Reihenfolge zu warten."""
        if not self._started or self._closed:
            raise RuntimeError("Der Episoden-Runner ist nicht aktiv.")
        deadline = perf_counter() + timeout
        while not self.finished:
            self._check_processes()
            remaining = max(deadline - perf_counter(), 0.0)
            try:
                kind, worker_id, episode = self._results.get(timeout=remaining)
            except queue.Empty:
                self._check_processes()
                for worker_id, process in enumerate(self._processes):
                    if process.exitcode == 0 and worker_id not in self._finished_workers:
                        raise RuntimeError(f"Simulations-Worker {worker_id} endete ohne Endmeldung.")
                return None
            if kind == "episode":
                return episode
            if kind == "error":
                raise RuntimeError(f"Simulations-Worker {worker_id} ist fehlgeschlagen:\n{episode}")
            self._finished_workers.add(worker_id)
        self._check_processes()
        return None

    def close(self):
        """Beendet nur die von diesem Runner gestarteten Prozesse und Verbindungen."""
        if self._closed:
            return
        self._closed = True
        self._stop.set()
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
        if self._manager is not None:
            self._manager.shutdown()
