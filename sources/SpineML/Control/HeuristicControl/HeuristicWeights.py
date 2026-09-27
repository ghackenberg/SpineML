from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class HeuristicWeights:
    """Gewichte der lokalen heuristischen Aktionsbewertung."""

    complete_job_gewicht: float = 1.0

    # Auch Warteaktionen bleiben als Bewertungsaspekt aktiv.
    wait_action_gewicht: float = 0.1

    queue_priority_gewicht: float = 0.4

    pick_source_storage_time_gewicht: float = 0.1

    pick_short_transport_time_gewicht: float = 0.3

    machine_pick_operation_duration_gewicht: float = 0.15

    machine_pick_tool_match_gewicht: float = 0.15

    machine_pick_tool_reserve_gewicht: float = 0.1

    target_store_free_capacity_gewicht: float = 0.2

    place_target_storage_time_gewicht: float = 0.15

    place_short_transport_time_gewicht: float = 0.25

    place_machine_queue_length_gewicht: float = 0.25

    place_operation_duration_gewicht: float = 0.15

    release_edd_gewicht: float = 0.7
    release_average_route_duration_gewicht: float = 0.3

    defect_recovery_machine_queue_length_gewicht: float = 0.3

    defect_recovery_transport_time_gewicht: float = 0.2

    defect_recovery_tool_match_gewicht: float = 0.2

    defect_recovery_tool_reserve_gewicht: float = 0.2

    produkt_herabstufen_defect_severity_gewicht: float = 0.4

    wait_defect_job_gewicht: float = 0.2

    # Auch der Grundwert der Ausschussaktion bleibt als Bewertungsaspekt aktiv.
    job_ausschuss_gewicht: float = 0.1

    nacharbeit_not_allowed_downgrade_bonus_gewicht: float = 0.4

    deadline_pressure_ausschuss_bonus_gewicht: float = 0.5

    deadline_missed_wait_penalty_gewicht: float = 0.2

    nacharbeit_defektmaschine_deadline_penalty_gewicht: float = 0.5

    nacharbeit_alternative_maschine_deadline_penalty_gewicht: float = 0.5

    def __post_init__(self) -> None:
        # Alle lokalen Gewichte sind normiert, damit kein Gewicht allein wegen
        # seiner Größenordnung andere Teilbewertungen übersteuert.
        for weight_field in fields(self):
            value = float(getattr(self, weight_field.name))
            if not 0.0 < value <= 1.0:
                raise ValueError(
                    f"Heuristic weight '{weight_field.name}' must be greater than 0 and at most 1"
                )
