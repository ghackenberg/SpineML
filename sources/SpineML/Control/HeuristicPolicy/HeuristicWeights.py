from __future__ import annotations

from dataclasses import dataclass, fields

from ..ActionGeneration.ActionGenerator import EDD_AT_DEADLINE, SCORE_MAX


# Bewusst gewählte Zielgrenzen für die Standardparametrierung ab der Deadline.
DEFAULT_DEADLINE_REWORK_SCORE_MAX = 0.5
DEFAULT_DEADLINE_WAIT_SCORE_MAX = 0.3
DEFAULT_DEADLINE_DOWNGRADE_SCORE_MIN = DEFAULT_DEADLINE_REWORK_SCORE_MAX


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

    # Normierte Gewichte: Score = s + b * (1 - s), mit b = 0.5.
    # Damit liegt Herabstufung für s in [0, 1] ab der Deadline in [0.5, 1].
    product_downgrade_defect_severity_weight: float = (
        SCORE_MAX - DEFAULT_DEADLINE_DOWNGRADE_SCORE_MIN
    ) / SCORE_MAX

    wait_defect_job_weight: float = 0.2

    # Der Deadline-Anteil b legt die Untergrenze des Herabstufungsscores fest.
    deadline_reached_downgrade_bonus_weight: float = (
        DEFAULT_DEADLINE_DOWNGRADE_SCORE_MIN / SCORE_MAX
    )

    # Warten: 1 - EDD <= 0.5; für Score <= 0.3 folgt Strafe = 0.5 - 0.3.
    deadline_missed_wait_penalty_weight: float = (
        SCORE_MAX - EDD_AT_DEADLINE - DEFAULT_DEADLINE_WAIT_SCORE_MAX
    )

    # Nacharbeit: Grundscore <= 1; für Score <= 0.5 folgt Strafe = 1 - 0.5.
    rework_defect_machine_deadline_penalty_weight: float = (
        SCORE_MAX - DEFAULT_DEADLINE_REWORK_SCORE_MAX
    )

    rework_alternative_machine_deadline_penalty_weight: float = (
        SCORE_MAX - DEFAULT_DEADLINE_REWORK_SCORE_MAX
    )

    def __post_init__(self) -> None:
        # Alle lokalen weights sind normiert, damit kein Weight allein wegen
        # seiner Größenordnung andere Teilbewertungen übersteuert.
        for weight_field in fields(self):
            value = float(getattr(self, weight_field.name))
            if not 0.0 < value <= 1.0:
                raise ValueError(
                    f"Heuristic weight '{weight_field.name}' must be greater than 0 and at most 1"
                )
