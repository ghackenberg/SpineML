from __future__ import annotations

import copy
import math
import operator
import queue
import random
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import salabim as sim

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as error:
    raise ImportError('RL-Control benötigt Gymnasium: python -m pip install ".[rl]"') from error

from ...Simulation import SimLayout, SimScenario
from ...Simulation.SimMachine import SimMachine
from ...GlobalEvaluation.GlobalSimulationEvaluation import GlobalSimulationEvaluation
from ...SimulationExecution.ModelLoader import _resolve_model_path, load_layout_and_scenario
from ...SimulationExecution.SimulationRunner import SimulationRunner
from ...SimulationInterface.SimulationBridge import SimulationBridge
from .RLCandidatePolicy import DecisionRequest, RLCandidatePolicy
from .RLObservationEncoder import RLObservationEncoder
from .RLReward import RLReward


# Salabim und Python-Random haben prozessglobale Zustände. Parallele Umgebungen
# gehören deshalb in getrennte Prozesse, nicht in mehrere Threads desselben Prozesses.
_ACTIVE_SIMULATION = threading.Lock()


class _EpisodeAbort(Exception):
    pass


@dataclass
class _Episode:
    seed: int
    messages: queue.Queue = field(default_factory=queue.Queue)
    answers: queue.Queue = field(default_factory=queue.Queue)
    cancelled: threading.Event = field(default_factory=threading.Event)
    abort_reason: str = "closed"
    thread: threading.Thread | None = None


class SpineRLEnv(gym.Env):
    """Schrittweise RL-Schnittstelle vor derselben Bridge und Salabim-Simulation.

    Ein Schritt wählt zwischen mehreren Kandidaten eines wartenden Objekts.
    Erzwungene Einzelaktionen benötigen keine Entscheidung des Agenten. Entscheidungen
    derselben Bridge-Gruppe werden zuerst gesammelt und danach zusammen zugestellt.
    Mehrere Schritte können deshalb dieselbe Simulationszeit haben.
    """

    metadata = {"render_modes": []}
    reward_range = (-1.0, 1.0)

    def __init__(
        self,
        model_file: str | Path,
        global_evaluation: GlobalSimulationEvaluation,
        *,
        max_actions: int = 256,
        max_entities: int = 256,
        max_decisions: int = 100_000,
        max_simulation_time: float = 10_000.0,
        response_timeout: float = 120.0,
    ):
        super().__init__()
        if isinstance(max_decisions, bool) or not isinstance(max_decisions, int) or max_decisions < 1:
            raise ValueError("max_decisions muss eine positive ganze Zahl sein.")
        for name, value in (("max_simulation_time", max_simulation_time), ("response_timeout", response_timeout)):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} muss endlich und positiv sein.")
        self.model_file = _resolve_model_path(model_file)
        self.reward_model = RLReward(global_evaluation)
        self.encoder = RLObservationEncoder(max_actions=max_actions, max_entities=max_entities)
        self.max_decisions = max_decisions
        self.max_simulation_time = float(max_simulation_time)
        self.response_timeout = float(response_timeout)
        self.action_space = spaces.Discrete(max_actions)
        self.observation_space = spaces.Dict({
            "context": spaces.Box(-1.0, 1.0, (self.encoder.context_size,), np.float32),
            "entities": spaces.Box(-1.0, 1.0, (max_entities, self.encoder.entity_feature_size), np.float32),
            "entity_mask": spaces.MultiBinary(max_entities),
            "candidates": spaces.Box(-1.0, 1.0, (max_actions, self.encoder.candidate_feature_size), np.float32),
            "action_mask": spaces.MultiBinary(max_actions),
        })
        self._episode: _Episode | None = None
        self._model = None
        self._request: DecisionRequest | None = None
        self._observation = self.encoder.empty_observation()
        self._steps = 0
        self._finished = True
        self._closed = False

    def reset(self, *, seed=None, options=None):
        if self._closed:
            raise RuntimeError("Die Umgebung wurde geschlossen; bitte eine neue Instanz erstellen.")
        if options:
            raise ValueError("Für diese Umgebung sind noch keine reset-Optionen definiert.")
        super().reset(seed=seed)
        self._stop_episode("reset")
        if not _ACTIVE_SIMULATION.acquire(blocking=False):
            raise RuntimeError("Nur eine aktive Salabim-RL-Umgebung pro Prozess; für Parallelität getrennte Prozesse nutzen.")
        episode_seed = int(seed) if seed is not None else int(self.np_random.integers(0, 2**31 - 1))
        episode = _Episode(episode_seed)
        self._episode = episode
        self._steps = 0
        self._finished = False
        self._request = None
        self._observation = self.encoder.empty_observation()
        episode.thread = threading.Thread(target=self._simulate, args=(episode,), daemon=True)
        try:
            episode.thread.start()
        except BaseException:
            self._episode = None
            self._finished = True
            _ACTIVE_SIMULATION.release()
            raise
        observation, reward, terminated, truncated, info = self._next_transition()
        if terminated or truncated:
            raise RuntimeError("Die Episode endete vor der ersten Entscheidung: " + str(info.get("truncation_reason", "")))
        return observation, info

    def step(self, action):
        if self._closed or self._finished or self._episode is None or self._request is None:
            raise RuntimeError("Vor step() muss eine laufende Episode mit reset() gestartet werden.")
        if isinstance(action, (bool, np.bool_)):
            raise ValueError("Eine ganze Kandidatennummer ist erforderlich, kein boolescher Wert.")
        try:
            index = operator.index(action)
        except TypeError as error:
            raise ValueError("Eine ganze Kandidatennummer ist erforderlich.") from error
        if not self.action_space.contains(index) or not self._observation["action_mask"][index]:
            raise ValueError("Dieser Kandidatenindex ist für die aktuelle Entscheidung ungültig.")
        self._steps += 1
        self._request = None
        self._episode.answers.put(index)
        return self._next_transition()

    def action_masks(self):
        """True kennzeichnet die in genau diesem Zustand wählbaren Kandidaten."""
        return np.asarray(self._observation["action_mask"], dtype=bool).copy()

    def close(self):
        self._stop_episode("closed")
        self._closed = True

    def _stop_episode(self, reason):
        episode = self._episode
        if episode is None:
            return
        episode.abort_reason = reason
        episode.cancelled.set()
        episode.answers.put(_EpisodeAbort(reason))
        self._join_episode(episode)
        self._episode = None
        self._request = None
        self._finished = True
        self._observation = self.encoder.empty_observation()

    def _join_episode(self, episode):
        if episode.thread is not None:
            episode.thread.join(timeout=self.response_timeout)
            if episode.thread.is_alive():
                # Der Worker gibt die Prozesssperre selbst frei, sobald er wirklich endet.
                raise TimeoutError("Die Simulation reagiert nicht auf den Abbruch; keine weitere Umgebung im selben Prozess starten.")

    def _next_transition(self):
        episode = self._episode
        try:
            while True:
                kind, value = episode.messages.get(timeout=self.response_timeout)
                if kind == "decision":
                    if self._steps >= self.max_decisions:
                        # Der Zustand an der externen Abbruchgrenze bleibt für
                        # späteres RL-Bootstrapping erhalten, statt Nullzustand.
                        self._observation = self.encoder.encode(value)
                        episode.abort_reason = "max_decisions"
                        episode.cancelled.set()
                        episode.answers.put(_EpisodeAbort("max_decisions"))
                        continue
                    self._request = value
                    self._observation = self.encoder.encode(value)
                    info = {
                        "episode_seed": episode.seed,
                        "decision_count": self._steps,
                        "simulation_time": float(value.observation.simulation_configuration_snapshot["time"]),
                        "current_object_id": value.observation.current_object_id,
                        "candidates": copy.deepcopy(list(value.candidates)),
                        "policy_observation": copy.deepcopy(value.observation),
                        "pending_actions": copy.deepcopy(value.selected_actions),
                    }
                    return self._observation_copy(), 0.0, False, False, info
                if kind == "error":
                    raise RuntimeError("Salabim-RL-Episode fehlgeschlagen: " + value)
                if kind == "done":
                    self._join_episode(episode)
                    self._request = None
                    self._finished = True
                    if value["terminated"]:
                        self._observation = self.encoder.empty_observation()
                    elif value["info"]["truncation_reason"] != "max_decisions":
                        self._observation = self.encoder.encode_snapshot(value["snapshot"])
                    value["info"].update(episode_seed=episode.seed, decision_count=self._steps)
                    return self._observation_copy(), value["reward"], value["terminated"], value["truncated"], copy.deepcopy(value["info"])
                raise RuntimeError("Unbekannte Nachricht der RL-Simulation.")
        except queue.Empty as error:
            self._stop_episode("response_timeout")
            raise TimeoutError("Keine neue RL-Entscheidung innerhalb des Zeitlimits erhalten.") from error
        except BaseException:
            self._stop_episode("error")
            raise

    def _observation_copy(self):
        return {name: value.copy() for name, value in self._observation.items()}

    def _simulate(self, episode):
        try:
            if self._model is None:
                self._model = load_layout_and_scenario(self.model_file)
            layout, scenario = self._model
            if sum(order.quantity for order in scenario.orders) < 1:
                raise ValueError("Eine RL-Episode benötigt mindestens einen Job.")

            def check_cancelled():
                if episode.cancelled.is_set():
                    raise _EpisodeAbort(episode.abort_reason)

            def request_decision(request):
                check_cancelled()
                episode.messages.put(("decision", request))
                answer = episode.answers.get()
                if isinstance(answer, _EpisodeAbort):
                    raise answer
                if episode.cancelled.is_set():
                    raise _EpisodeAbort(episode.abort_reason)
                return answer

            sim.yieldless(False)
            random.seed(episode.seed)
            SimMachine.QUALITY_SEED = episode.seed
            env = sim.Environment(time_unit="hours", random_seed=episode.seed)
            policy = RLCandidatePolicy(request_decision, cancellation_check=check_cancelled)
            bridge = SimulationBridge(policy, env=env)
            sim_layout = SimLayout(layout, scenario, bridge, env=env)
            sim_scenario = SimScenario(layout, scenario, sim_layout.store_start, bridge, env=env)
            truncation_reason = None
            try:
                env.run(till=self.max_simulation_time)
            except sim.SimulationStopped:
                pass
            except _EpisodeAbort as abort:
                if str(abort) != "max_decisions":
                    return
                truncation_reason = str(abort)
            jobs = [job for order in sim_scenario.sim_orders for job in order.sim_jobs]
            terminated = all(job.process_finished for job in jobs)
            truncated = not terminated
            if truncated and truncation_reason is None:
                truncation_reason = "max_simulation_time"
            metrics = SimulationRunner(layout, scenario).collect_global_metrics(
                sim_layout, sim_scenario, env.now(),
            )
            reward, reward_info = self.reward_model.evaluate(metrics, terminated=terminated, truncated=truncated)
            episode.messages.put(("done", {
                "reward": reward, "terminated": terminated, "truncated": truncated,
                "snapshot": bridge.build_policy_simulation_snapshot() if truncated else None,
                "info": {
                    **reward_info, "metrics": asdict(metrics), "simulation_time": float(env.now()),
                    "truncation_reason": truncation_reason,
                    "pending_batch_discarded": truncation_reason == "max_decisions",
                    "candidates": [], "current_object_id": None,
                },
            }))
        except BaseException as error:
            episode.messages.put(("error", f"{type(error).__name__}: {error}"))
        finally:
            _ACTIVE_SIMULATION.release()
