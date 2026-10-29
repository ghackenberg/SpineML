"""Gemeinsame Payload-Vorbereitung ohne gewichtete Aktionsbewertung."""

from typing import Any

from ...SimulationInterface.InterfaceTypes import PolicyObservation


# Gemeinsame Skala der EDD-Priorität, auch für die heuristische Bewertung.
SCORE_MAX = 1.0
EDD_AT_DEADLINE = 0.5

__all__ = ["ActionPreparation"]


class ActionPreparation:
    """Kopiert Kandidaten und ergänzt Pick-Payloads um die bestehende EDD-Priorität.

    Diese Vorbereitung ist unabhängig von einer Auswahlstrategie und berechnet
    keine Aktionsscores. Die Store-Suche und die Reihenfolge gleicher IDs bleiben
    identisch zur bisher im Heuristikevaluator enthaltenen Implementierung.
    """

    @staticmethod
    def inverse_scale(value: float) -> float:
        return 1.0 / (1.0 + float(value))

    @staticmethod
    def direct_scale(value: float) -> float:
        value = float(value)
        return value / (1.0 + value)

    def prepare_action_candidate(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> dict[str, Any]:
        action_type = str(action["action_type"])
        prepared_action = dict(action)
        prepared_action["payload"] = dict(action["payload"])
        if action_type.startswith("pick_"):
            prepared_action["payload"]["queue_priority"] = (
                self.calculate_pick_edd_priority(prepared_action, observation)
            )
        return prepared_action

    def calculate_pick_edd_priority(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        job_state = self.selected_job_state(action, observation)
        return self.calculate_edd_priority(
            float(job_state["latest_end_time"]),
            float(observation.simulation_configuration_snapshot["time"]),
        )

    def calculate_edd_priority(
        self,
        latest_end_time: float,
        current_time: float,
    ) -> float:
        time_until_deadline = latest_end_time - current_time
        if time_until_deadline >= 0:
            return EDD_AT_DEADLINE * self.inverse_scale(time_until_deadline)
        overdue_time = -time_until_deadline
        return EDD_AT_DEADLINE + (
            SCORE_MAX - EDD_AT_DEADLINE
        ) * self.direct_scale(overdue_time)

    def find_store_state(self, value: object, store_id: str) -> dict:
        stores_by_id: dict[str, dict] = {}

        def collect_store_states(nested_value):
            if isinstance(nested_value, dict):
                if "store_id" in nested_value:
                    stores_by_id[nested_value["store_id"]] = nested_value
                for child_value in nested_value.values():
                    collect_store_states(child_value)
            elif isinstance(nested_value, list):
                for child_value in nested_value:
                    collect_store_states(child_value)

        collect_store_states(value)
        return stores_by_id[store_id]

    def selected_job_state(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> dict:
        payload = action["payload"]
        selected_job_id = payload["selected_job_id"]
        target_store_id = payload["target_store_id"]
        snapshot = observation.simulation_configuration_snapshot
        store_state = self.find_store_state(snapshot, str(target_store_id))
        for job_state in store_state["job_summaries"]:
            if job_state["job_id"] == selected_job_id:
                return job_state
        raise KeyError(selected_job_id)
