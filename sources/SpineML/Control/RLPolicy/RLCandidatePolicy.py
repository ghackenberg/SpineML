from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from numbers import Integral
from typing import Callable

from ..ActionGeneration.ActionGenerator import SpineActionGenerator
from ...SimulationInterface.InterfaceTypes import (
    ActionGenerator,
    Policy,
    PolicyDecision,
    PolicyObservation,
    SelectedObjectAction,
)


@dataclass(frozen=True)
class DecisionRequest:
    """Kopierter Zustand, Kandidaten und bisher gewählte Aktionen einer Entscheidung."""

    observation: PolicyObservation
    candidates: tuple[dict, ...]
    selected_actions: tuple[SelectedObjectAction, ...] = ()


class RLCandidatePolicy(Policy):
    """Lässt eine Entscheidungsfunktion den Index eines erzeugten Kandidaten wählen.

    Bei nur einem Kandidaten wird dieser ohne Rückfrage gewählt, außer bei expose_forced_actions.
    """

    def __init__(
        self,
        decision_callback: Callable[[DecisionRequest], int],
        action_generator: ActionGenerator | None = None,
        *,
        expose_forced_actions: bool = False,
        cancellation_check: Callable[[], None] | None = None,
    ):
        if not callable(decision_callback):
            raise TypeError("decision_callback must be callable")
        if not isinstance(expose_forced_actions, bool):
            raise TypeError("expose_forced_actions must be a bool")
        if cancellation_check is not None and not callable(cancellation_check):
            raise TypeError("cancellation_check must be callable or None")
        self.decision_callback = decision_callback
        self.expose_forced_actions = expose_forced_actions
        self.cancellation_check = cancellation_check
        self.action_generator = (
            action_generator if action_generator is not None else SpineActionGenerator()
        )

    def make_decision(self, observation: PolicyObservation) -> PolicyDecision:
        # Auch lange Folgen erzwungener Aktionen müssen von außen abbrechbar sein.
        if self.cancellation_check is not None:
            self.cancellation_check()
        snapshot = observation.simulation_configuration_snapshot
        selected_actions: list[SelectedObjectAction] = []
        selected_pick_jobs: set[str] = set()

        for object_id, state in snapshot["simulation_object_states_by_id"].items():
            if not state["is_waiting_for_action"]:
                continue
            object_observation = PolicyObservation(snapshot, object_id)
            available_actions = []
            for action in self.action_generator.generate_actions(object_observation):
                # Derselbe Job darf in dieser Auswahl nur einmal aufgenommen werden.
                if (
                    action["action_type"].startswith("pick_")
                    and str(action["payload"]["selected_job_id"]) in selected_pick_jobs
                ):
                    continue
                available_actions.append(action)
            if not available_actions:
                raise ValueError(f"No feasible RL action for waiting object {object_id!r}")

            index = 0
            if len(available_actions) > 1 or self.expose_forced_actions:
                # Der Callback erhält keine Referenz auf die privaten Kandidaten.
                request = DecisionRequest(
                    observation=deepcopy(object_observation),
                    candidates=deepcopy(tuple(available_actions)),
                    selected_actions=deepcopy(tuple(selected_actions)),
                )
                index = self.decision_callback(request)
            if isinstance(index, bool) or not isinstance(index, Integral):
                raise ValueError("The RL action must be an integer candidate index")
            index = int(index)
            if not 0 <= index < len(available_actions):
                raise ValueError(
                    f"RL candidate index {index} outside [0, {len(available_actions)}) "
                    f"for object {object_id!r}"
                )
            chosen = deepcopy(available_actions[index])
            selected_actions.append(
                SelectedObjectAction(object_id, chosen["action_type"], chosen["payload"])
            )
            if chosen["action_type"].startswith("pick_"):
                selected_pick_jobs.add(str(chosen["payload"]["selected_job_id"]))

        return PolicyDecision(selected_actions)
