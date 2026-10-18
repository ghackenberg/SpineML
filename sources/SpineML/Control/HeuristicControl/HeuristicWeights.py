from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class HeuristicWeights:
    """Weights used by the local heuristic action evaluation."""

    complete_job_weight: float = 1.0

    # Auch Warteaktionen bleiben als Bewertungsaspekt aktiv.
    wait_action_weight: float = 0.1

    queue_priority_weight: float = 0.4

    pick_source_storage_time_weight: float = 0.1

    pick_short_transport_time_weight: float = 0.3

    machine_pick_operation_duration_weight: float = 0.15

    machine_pick_tool_match_weight: float = 0.15

    machine_pick_tool_reserve_weight: float = 0.1

    target_store_free_capacity_weight: float = 0.2

    place_target_storage_time_weight: float = 0.15

    place_short_transport_time_weight: float = 0.25

    place_machine_queue_length_weight: float = 0.25

    place_operation_duration_weight: float = 0.15

    release_edd_weight: float = 0.7
    release_average_route_duration_weight: float = 0.3

    defect_recovery_machine_queue_length_weight: float = 0.3

    defect_recovery_transport_time_weight: float = 0.2

    defect_recovery_tool_match_weight: float = 0.2

    defect_recovery_tool_reserve_weight: float = 0.2

    product_downgrade_defect_severity_weight: float = 0.4

    wait_defect_job_weight: float = 0.2

    rework_not_allowed_downgrade_bonus_weight: float = 0.4

    deadline_missed_wait_penalty_weight: float = 0.2

    rework_defect_machine_deadline_penalty_weight: float = 0.5

    rework_alternative_machine_deadline_penalty_weight: float = 0.5

    def __post_init__(self) -> None:
        # Alle lokalen weights sind normiert, damit kein Weight allein wegen
        # seiner Größenordnung andere Teilbewertungen übersteuert.
        for weight_field in fields(self):
            value = float(getattr(self, weight_field.name))
            if not 0.0 < value <= 1.0:
                raise ValueError(
                    f"Heuristic weight '{weight_field.name}' must be greater than 0 and at most 1"
                )
