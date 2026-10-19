from __future__ import annotations

import random

from .ActionGenerators import SpineActionGenerator
from ..Interface.InterfaceTypes import (
    ActionGenerator,
    Policy,
    PolicyDecision,
    PolicyObservation,
    SelectedObjectAction,
    is_wait_action,
)


__all__ = ["RandomPolicy"]


class RandomPolicy(Policy):
    """Wählt zufällig unter Nicht-Warteaktionen; wartet nur als Fallback."""

    def __init__(
        self,
        seed: int | None = None,
        action_generator: ActionGenerator | None = None,
    ):
        self.random = random.Random(seed)
        self.action_generator = (
            action_generator if action_generator is not None else SpineActionGenerator()
        )

    def make_decision(self, observation: PolicyObservation) -> PolicyDecision:
        snapshot = observation.simulation_configuration_snapshot
        selected_actions: list[SelectedObjectAction] = []
        selected_job_ids: set[str] = set()

        for object_id, object_state in snapshot["simulation_object_states_by_id"].items():
            if not object_state["is_waiting_for_action"]:
                continue

            object_observation = PolicyObservation(snapshot, object_id)
            actions = self.action_generator.generate_actions(object_observation)
            # Derselbe Job darf innerhalb einer Entscheidung nur einmal gepickt werden.
            available_actions = [
                action for action in actions
                if not (
                    action["action_type"].startswith("pick_")
                    and action["payload"]["selected_job_id"] in selected_job_ids
                )
            ]
            productive_actions = [
                action for action in available_actions
                if not is_wait_action(action["action_type"])
            ]
            candidates = productive_actions or available_actions
            if not candidates:
                continue

            # Jeder verbleibende Kandidat hat dieselbe Auswahlwahrscheinlichkeit.
            action = self.random.choice(candidates)
            payload = dict(action["payload"])
            if action["action_type"].startswith("pick_"):
                # Neutrale Store-Priorität statt einer EDD-Dispatchingregel.
                payload["queue_priority"] = 0.0
                selected_job_ids.add(payload["selected_job_id"])

            selected_actions.append(
                SelectedObjectAction(object_id, action["action_type"], payload)
            )

        return PolicyDecision(selected_actions)
