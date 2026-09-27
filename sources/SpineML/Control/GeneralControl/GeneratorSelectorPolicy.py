from .ActionGenerators import SpineActionGenerator
from .ActionSelectors import BaselineActionSelector
from ..Interface.InterfaceTypes import (
    ActionEvaluator,
    ActionGenerator,
    ActionSelector,
    Policy,
    PolicyObservation,
    PolicyDecision,
    SelectedObjectAction,
)


class GeneratorSelectorPolicy(Policy):
    """Verbindet einen ActionGenerator mit einem austauschbaren ActionSelector."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        action_selector: ActionSelector | None = None,
        action_generator: ActionGenerator | None = None,
        action_evaluator: ActionEvaluator | None = None,
    ):
        self.action_selector = action_selector if action_selector is not None else BaselineActionSelector()
        self.action_generator = action_generator if action_generator is not None else SpineActionGenerator()
        self.action_evaluator = (
            action_evaluator
            if action_evaluator is not None
            else self._create_default_action_evaluator()
        )

    def _create_default_action_evaluator(self) -> ActionEvaluator:
        # Der Import erfolgt erst bei der Policy-Erzeugung, damit
        # GeneralControl und HeuristicControl keinen zirkulären Import bilden.
        from ..HeuristicControl.HeuristicWeights import HeuristicWeights
        from ..HeuristicControl.LocalHeuristicActionEvaluator import (
            LocalHeuristicActionEvaluator,
        )

        return LocalHeuristicActionEvaluator(
            HeuristicWeights(),
            action_generator=self.action_generator,
        )

    # Führt die Funktion mit den übergebenen Werten aus.
    def make_decision(self, observation: PolicyObservation) -> PolicyDecision:
        snapshot = observation.simulation_configuration_snapshot
        selected_actions: list[SelectedObjectAction] = []

        for object_id, object_state in snapshot[
            "simulation_object_states_by_id"
        ].items():
            if not object_state["is_waiting_for_action"]:
                continue

            # Erstellt aus dem globalen Snapshot die Observation für dieses wartende Objekt.
            object_observation = PolicyObservation(
                simulation_configuration_snapshot=snapshot,
                current_object_id=object_id,
            )


            # Wählt die beste verfügbare Aktion für dieses einzelne Objekt aus.
            object_decision = self.select_single_action(object_observation)
            for selected_action in object_decision.actions:
                selected_actions.append(selected_action)

        valid_selected_actions: list[SelectedObjectAction] = []
        selected_job_ids: set[str] = set()

        for selected_action in selected_actions:
            if selected_action.action_type.startswith("pick_"):
                selected_job_id = selected_action.payload["selected_job_id"]

                # Verwirft einen weiteren Pick für einen Job, der bereits ausgewählt wurde.
                if selected_job_id in selected_job_ids:
                    continue

                selected_job_ids.add(selected_job_id)

            valid_selected_actions.append(selected_action)

        return PolicyDecision(valid_selected_actions)

    # Wählt ein passendes Objekt oder eine passende Aktion aus.
    def select_single_action(self, observation: PolicyObservation) -> PolicyDecision:
        actions = self.action_generator.generate_actions(observation)
        decision = self.action_selector.select_action(
            actions,
            evaluator=self.action_evaluator,
            observation=observation,
            target_id=observation.current_object_id,
        )
        return decision
