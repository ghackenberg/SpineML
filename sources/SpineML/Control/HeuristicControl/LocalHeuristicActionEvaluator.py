from typing import Any

from ..GeneralControl.ActionGenerators import SpineActionGenerator
from ..Interface.InterfaceTypes import ActionEvaluator, PolicyObservation
from .HeuristicWeights import HeuristicWeights

class LocalHeuristicActionEvaluator(ActionEvaluator):
    """Bereitet Aktionskandidaten vor und bewertet sie mit Gewichten."""

    WAIT_SCORE_MIN = 0.01
    WAIT_SCORE_MAX = 0.99

    # Speichert den konfigurierbaren Gewichtssatz für alle Bewertungsmethoden.
    # Beispiel: HeuristicWeights(queue_priority_gewicht=0.4) wird in self.weights gespeichert.
    def __init__(
        self,
        weights: HeuristicWeights,
        action_generator: SpineActionGenerator | None = None,
    ):
        self.weights = weights
        self.action_generator = (
            action_generator
            if action_generator is not None
            else SpineActionGenerator()
        )

    # Wandelt einen nichtnegativen Rohwert in einen abfallenden, dimensionslosen
    # Vorteilswert um: 0 ergibt 1; mit wachsendem Wert nähert sich das Ergebnis 0.
    # Beispiel: kehrwert_scale(1.0) ergibt 0.5.
    @staticmethod
    def kehrwert_scale(value: float) -> float:
        nonnegative_value = max(float(value), 0.0)
        return 1.0 / (1.0 + nonnegative_value)

    # Wandelt einen nichtnegativen Rohwert in einen wachsenden,
    # dimensionslosen Vorteilswert um: 0 ergibt 0; mit wachsendem Wert
    # nähert sich das Ergebnis 1. Diese Funktion ist die direkte Ergänzung
    # zur Kehrwertskalierung und wird für "je größer, desto besser" verwendet.
    # Beispiel: direkte_scale(1.0) ergibt 0.5.
    @staticmethod
    def direkte_scale(value: float) -> float:
        nonnegative_value = max(float(value), 0.0)
        return nonnegative_value / (1.0 + nonnegative_value)

    # Normiert einen Wert relativ zu einem konfigurierten Maximum auf [0, 1].
    # Ein nichtpositives Maximum liefert keinen verwertbaren Anteil.
    @staticmethod
    def normalize_ratio(value: float, maximum: float) -> float:
        maximum_value = float(maximum)
        if maximum_value <= 0.0:
            return 0.0
        ratio = float(value) / maximum_value
        return max(0.0, min(ratio, 1.0))

    # Führt Teilbewertungen und ihre Gewichte zum Gesamtscore einer Aktion zusammen.
    # Wenn alle Teilwerte in [0, 1] liegen und die Gewichte positiv sind,
    # liegt auch der Aktionsscore in [0, 1].
    @staticmethod
    def calculate_action_score(
        weighted_parts: list[tuple[float, float]],
    ) -> float:
        weighted_sum = 0.0
        weight_sum = 0.0
        for value, weight in weighted_parts:
            score_weight = float(weight)
            if score_weight <= 0.0:
                raise ValueError(
                    "Aktive Heuristikgewichte müssen größer als 0 sein."
                )
            score_value = float(value)
            weighted_sum += score_value * score_weight
            weight_sum += score_weight

        if weight_sum <= 0.0:
            raise ValueError(
                "Mindestens ein positives Heuristikgewicht ist erforderlich."
            )
        return weighted_sum / weight_sum

    # Gibt den Zustand des aktuell von der Policy betrachteten Objekts zurück.
    # Beispiel: current_object_id="Main robot" liefert dessen Zustands-Dictionary.
    def current_state(self, observation: PolicyObservation) -> dict[str, object]:
        snapshot = observation.simulation_configuration_snapshot
        return snapshot["simulation_object_states_by_id"][
            observation.current_object_id
        ]


    # Kopiert einen Aktionskandidaten und ergänzt Pick-Aktionen um queue_priority.
    # Beispiel: pick_main_robot für Job A erhält zusätzlich queue_priority=0.42.
    def prepare_action_candidate(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> dict[str, Any]:
        action_type = str(action["action_type"])
        prepared_action = dict(action)
        prepared_action["payload"] = dict(action["payload"])

        # Jede Pick-Aktion betrifft genau einen Job; dafür wird die aktuelle EDD-Priorität berechnet.
        if action_type.startswith("pick_"):
            prepared_action["payload"]["queue_priority"] = (
                self.calculate_pick_edd_priority(
                    prepared_action,
                    observation,
                )
            )

        return prepared_action

    # Liest den ausgewählten Job und berechnet daraus seine aktuelle EDD-Priorität.
    # Beispiel: Deadline 10 und aktuelle Zeit 8 ergeben die Priorität 0.1667.
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

    # Wandelt Deadline und aktuelle Zeit in eine Dringlichkeit zwischen 0 und 1 um.
    # Beispiel: latest_end_time=10 und current_time=8 ergeben 0.5/(1+2)=0.1667.
    def calculate_edd_priority(
        self,
        latest_end_time: float,
        current_time: float,
    ) -> float:
        time_until_deadline = latest_end_time - current_time
        if time_until_deadline >= 0:
            # Je weniger Restzeit vorhanden ist, desto höher ist der Druck.
            return 0.5 * self.kehrwert_scale(time_until_deadline)

        overdue_time = -time_until_deadline
        # Bei einer Überschreitung steigt der Druck mit der Überfälligkeit.
        return 0.5 + 0.5 * self.direkte_scale(overdue_time)


    # Sucht einen Store rekursiv im Snapshot und gibt sein Zustands-Dictionary zurück.
    # Beispiel: store_id="Machine 1 in" liefert count, capacity und job_summaries.
    def find_store_state(
        self,
        value: object,
        store_id: str,
    ) -> dict:
        stores_by_id: dict[str, dict] = {}

        # Beispiel: Ein verschachteltes Dictionary mit store_id wird in stores_by_id gespeichert.
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

    # Sucht einen Maschinenzustand rekursiv anhand seiner ID oder seines Namens.
    # Beispiel: machine_id="Fräsmaschine A" liefert den Zustand dieser Maschine.
    def find_machine_state(
        self,
        value: object,
        machine_id: str,
    ) -> dict:
        machines_by_id: dict[str, dict] = {}

        # Beispiel: Ein machine-Dictionary wird unter object_id und machine_name abgelegt.
        def collect_machine_states(nested_value: object) -> None:
            if isinstance(nested_value, dict):
                if nested_value.get("object_type") == "machine":
                    machines_by_id[str(nested_value["object_id"])] = nested_value
                    machine_name = nested_value.get("machine_name")
                    if machine_name is not None:
                        machines_by_id[str(machine_name)] = nested_value
                for child_value in nested_value.values():
                    collect_machine_states(child_value)
            elif isinstance(nested_value, list):
                for child_value in nested_value:
                    collect_machine_states(child_value)

        collect_machine_states(value)
        return machines_by_id[machine_id]

    # Sucht im vollständigen Beobachtungssnapshot die räumliche Position eines Stores.
    # Beispiel: store_id="Machine 1 in" ergibt z. B. {"x": 5.0, "y": 3.0, "z": 1.5}.
    def find_store_position(
        self,
        value: object,
        store_id: str,
    ) -> dict:
        store_positions_by_id: dict[str, dict] = {}

        # Beispiel: Gefundene Positionen werden unter ihrer Store-ID gesammelt.
        def collect_store_positions(nested_value: object) -> None:
            if isinstance(nested_value, dict):
                positions = nested_value.get("store_positions_by_id")
                if positions is not None:
                    for position_store_id, position in positions.items():
                        store_positions_by_id[str(position_store_id)] = position
                for child_value in nested_value.values():
                    collect_store_positions(child_value)
            elif isinstance(nested_value, list):
                for child_value in nested_value:
                    collect_store_positions(child_value)

        collect_store_positions(value)
        return store_positions_by_id[store_id]

    # Sucht anhand von selected_job_id und target_store_id den ausgewählten Jobzustand.
    # Beispiel: Job A im Start-Store liefert dessen latest_end_time und selected_operation_id.
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

    # Liest die gültige Queue-Priorität aus einer Pick-Aktion oder dem aktuellen Objektzustand.
    # Beispiel: Pick-Payload queue_priority=0.42 ergibt die Zahl 0.42.
    def read_queue_priority(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        action_type = str(action["action_type"])

        if action_type.startswith("pick_"):
            return float(action["payload"]["queue_priority"])

        current_state = self.current_state(observation)
        return float(current_state["current_job_queue_priority"])


    # Leitet jede Aktionsart an die passende Bewertungsmethode weiter.
    # Beispiel: action_type="pick_machine_job" wird durch evaluate_machine_pick_action bewertet.
    def evaluate_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        action_type = str(action["action_type"])

        if action_type == "complete_job":
            return self.calculate_action_score([(1.0, self.weights.complete_job_gewicht)])

        current_state = self.current_state(observation)

        if action_type == "release_job":
            return self.evaluate_release_action(observation)

        if (
            current_state["object_type"] == "order_job"
            and current_state["general_state"] == "defect"
        ):
            return self.evaluate_defect_action(
                action_type,
                action,
                current_state,
                observation,
            )

        if action_type.startswith("wait_"):
            return self.evaluate_wait_action(observation)

        if action_type.startswith("pick_"):
            return self.evaluate_pick_action(action, observation)

        if action_type.startswith("place_"):
            return self.evaluate_place_action(action, observation)

        if action_type == "process_machine_job":
            return self.evaluate_process_action(action, observation)

        return 0.0


    # Bewertet eine normale Warteaktion anhand des Termindrucks des wartenden Jobs.
    # Ein leerer Roboter oder eine leere Maschine erhält den unteren Wartewert,
    # damit Warten bei einer verfügbaren Pick-Aktion nicht pauschal mit 1
    # bewertet wird. Die Wartewerte bleiben bewusst innerhalb von 0 und 1.
    def evaluate_wait_action(
        self,
        observation: PolicyObservation,
    ) -> float:
        current_state = self.current_state(observation)
        if current_state["object_type"] == "order_job":
            job_summary = current_state
        else:
            job_summary = current_state.get("current_job_summary")

        if not job_summary:
            wait_value = self.WAIT_SCORE_MIN
        else:
            latest_end_time = job_summary.get("latest_end_time")
            if latest_end_time is None:
                wait_value = self.WAIT_SCORE_MIN
            else:
                current_time = float(
                    observation.simulation_configuration_snapshot["time"]
                )
                edd_priority = self.calculate_edd_priority(
                    float(latest_end_time),
                    current_time,
                )
                wait_value = self.WAIT_SCORE_MIN + (
                    self.WAIT_SCORE_MAX - self.WAIT_SCORE_MIN
                ) * (1.0 - edd_priority)

        return self.calculate_action_score([
            (wait_value, self.weights.wait_action_gewicht),
        ])


    # Bewertet eine Freigabe mit EDD und der durchschnittlichen Bearbeitungszeit
    # der möglichen Operationsrouten.
    # Beispiel: EDD=0.2, release_edd_gewicht=0.7, erwartete Bearbeitungszeit=4 und
    # release_average_route_duration_gewicht=0.3 ergeben 0.2*0.7 + 1/(1+4)*0.3=0.20.
    def evaluate_release_action(
        self,
        observation: PolicyObservation,
    ) -> float:
        current_state = self.current_state(observation)
        current_time = float(
            observation.simulation_configuration_snapshot["time"]
        )
        latest_end_time = float(current_state["latest_end_time"])
        edd_priority = self.calculate_edd_priority(
            latest_end_time,
            current_time,
        )
        # Schätzt die erwartete Gesamtbearbeitungszeit der möglichen Routen.
        estimated_processing_time = self.estimate_release_processing_time(
            current_state,
            observation,
        )
        # Kürzere erwartete Bearbeitungszeiten erhalten einen höheren Score.
        processing_time_score = self.kehrwert_scale(estimated_processing_time)
        return self.calculate_action_score([
            (edd_priority, self.weights.release_edd_gewicht),
            (
                processing_time_score,
                self.weights.release_average_route_duration_gewicht,
            ),
        ])

    # Ermittelt die erwartete Bearbeitungszeit aus allen möglichen Routen.
    # Dafür wird die durchschnittliche Gesamtzeit der Routen verwendet.
    # Beispiel: Routen mit 8 und 12 Zeiteinheiten ergeben den Wert 10.
    def estimate_release_processing_time(
        self,
        current_state: dict,
        observation: PolicyObservation,
    ) -> float:
        model = observation.simulation_configuration_snapshot[
            "configuration_model"
        ]
        target_product_type_id = current_state["target_product_type_id"]
        operation_sequences = self.action_generator.calculate_operation_sequences(
            target_product_type_id,
            model,
        )
        if not operation_sequences:
            return 0.0

        route_processing_times = []
        for sequence in operation_sequences:
            # "sequence" enthält alle Operations-IDs einer einzelnen Route.
            total_processing_time = 0.0
            for operation_id in sequence:
                # Liest die Konfigurationsdaten der aktuellen Operation.
                operation = model["operations_by_id"][operation_id]
                # Addiert die Dauer zur Gesamtzeit dieser einen Route.
                total_processing_time += float(operation["duration"])

            # Speichert die Gesamtzeit der aktuellen Route für die spätere
            # Berechnung der erwarteten Bearbeitungszeit.
            route_processing_times.append(total_processing_time)

        if not route_processing_times:
            return 0.0

        # Die SPT-Regel verwendet die durchschnittliche Gesamtbearbeitungszeit
        # als erwartete Bearbeitungszeit.
        return sum(route_processing_times) / len(route_processing_times)

    # Berechnet die verbleibende Zeit bis zur Deadline des Jobs.
    # Beispiel: latest_end_time=10 und time=7 ergeben remaining_time=3.
    def estimate_remaining_time(self, current_state: dict) -> float:
        return current_state["latest_end_time"] - current_state["time"]

    # Prüft, ob für Nacharbeit noch Zeit bis zur Deadline vorhanden ist.
    # Beispiel: remaining_time=3 ergibt True; remaining_time=0 ergibt False.
    def is_nacharbeit_allowed(
        self,
        current_state: dict,
        observation: PolicyObservation,
    ) -> bool:
        remaining_time = self.estimate_remaining_time(current_state)
        if remaining_time <= 0:
            return False

        return True

    # Bewertet Ausschuss, Warten, Herabstufung oder eine der Nacharbeitsoptionen.
    # Beispiel: action_type="produkt_herabstufen" liefert den Herabstufungs-Score.
    def evaluate_defect_action(
        self,
        action_type: str,
        action: dict[str, Any],
        current_state: dict,
        observation: PolicyObservation,
    ) -> float:
        remaining_time = self.estimate_remaining_time(current_state)
        deadline_missed = remaining_time <= 0
        current_time = float(
            observation.simulation_configuration_snapshot["time"]
        )
        # Berechnet die EDD-Priorität des defekten Jobs für die Aktionsbewertung.
        defect_edd_priority = self.calculate_edd_priority(
            float(current_state["latest_end_time"]),
            current_time,
        )

        if action_type == "job_ausschuss":
            return self.calculate_action_score([
                (1.0, self.weights.job_ausschuss_gewicht),
                (
                    defect_edd_priority,
                    self.weights.deadline_pressure_ausschuss_bonus_gewicht,
                ),
            ])

        if action_type == "wait_job":
            # Ein defekter Job darf warten; je dringender seine Deadline ist,
            # desto kleiner wird die Bewertung dieser Warteaktion.
            score = self.calculate_action_score([
                (1.0 - defect_edd_priority, self.weights.wait_defect_job_gewicht),
            ])
            # Nach Ablauf der Deadline wird zusätzlich eine Warte-Strafe abgezogen.
            if deadline_missed:
                score -= self.weights.deadline_missed_wait_penalty_gewicht
            # Gibt den fertigen Score der Warteaktion zurück.
            return max(0.0, score)

        nacharbeit_allowed = self.is_nacharbeit_allowed(
            current_state,
            observation,
        )

        if action_type == "produkt_herabstufen":
            # Ein höherer Schweregrad macht die Herabstufung gegenüber einer
            # Nacharbeit attraktiver.
            defect_severity = max(
                0.0,
                min(float(current_state.get("defekt_schwergrad", 0.0)), 1.0),
            )
            parts = [
                (
                    defect_severity,
                    self.weights.produkt_herabstufen_defect_severity_gewicht,
                ),
            ]

            # Wenn Nacharbeit zeitlich nicht mehr möglich ist, erhält die
            # Herabstufung einen zusätzlichen Bonus.
            if not nacharbeit_allowed:
                parts.append((1.0, self.weights.nacharbeit_not_allowed_downgrade_bonus_gewicht))
            # Gibt den fertigen Score der Herabstufungsaktion zurück.
            return self.calculate_action_score(parts)

        if action_type in {
            "job_nacharbeiten_auf_defektmaschine",
            "job_nacharbeiten_auf_alternativer_maschine",
        }:
            return self.evaluate_defect_recovery_action(
                action_type,
                action,
                observation,
                deadline_missed,
            )

        return 0.0

    # Bewertet eine Nacharbeitsaktion ausschließlich anhand der ausgewählten
    # Maschine und der zugehörigen Operation.
    def evaluate_defect_recovery_action(
        self,
        action_type: str,
        action: dict[str, Any],
        observation: PolicyObservation,
        deadline_missed: bool,
    ) -> float:
        payload = action["payload"]
        machine_id = payload.get("selected_machine_id")
        operation_id = payload.get("selected_operation_id")
        if machine_id is None or operation_id is None:
            return 0.0

        snapshot = observation.simulation_configuration_snapshot
        model = snapshot["configuration_model"]
        try:
            machine_state = self.find_machine_state(snapshot, str(machine_id))
            operation = model["operations_by_id"][str(operation_id)]
        except (KeyError, TypeError):
            return 0.0

        parts = [
            (
                self.kehrwert_scale(
                    float(machine_state["input_storage"]["count"])
                ),
                self.weights.defect_recovery_machine_queue_length_gewicht,
            ),
        ]

        if action_type == "job_nacharbeiten_auf_alternativer_maschine":
            transport_time_value = self.defect_recovery_transport_time_value(
                action,
                observation,
                machine_state,
            )
            if transport_time_value is not None:
                parts.append(
                    (
                        transport_time_value,
                        self.weights.defect_recovery_transport_time_gewicht,
                    )
                )

        required_tool_id = operation.get("tool_type_id")
        if required_tool_id is not None:
            mounted_tool_id = machine_state.get("mounted_tool_type_id")
            parts.append(
                (
                    1.0 if mounted_tool_id == required_tool_id else 0.0,
                    self.weights.defect_recovery_tool_match_gewicht,
                )
            )

            consumed_life = float(operation.get("consumes_life_units", 0.0))
            if consumed_life > 0.0:
                remaining_life = max(
                    float(
                        machine_state.get("remaining_life_units_by_tool", {})
                        .get(required_tool_id, 0.0)
                    ),
                    0.0,
                )
                parts.append(
                    (
                        self.direkte_scale(remaining_life / consumed_life),
                        self.weights.defect_recovery_tool_reserve_gewicht,
                    )
                )

        score = self.calculate_action_score(parts)
        if deadline_missed:
            if action_type == "job_nacharbeiten_auf_defektmaschine":
                penalty = self.weights.nacharbeit_defektmaschine_deadline_penalty_gewicht
            else:
                penalty = self.weights.nacharbeit_alternative_maschine_deadline_penalty_gewicht
            score -= penalty
        return max(0.0, score)

    # Schätzt die Transportzeit vom aktuellen Jobstandort zum Eingangsstore
    # der ausgewählten Nacharbeitsmaschine.
    def defect_recovery_transport_time_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
        target_machine_state: dict[str, object],
    ) -> float | None:
        current_state = self.current_state(observation)
        source_store_id = current_state.get("location")
        target_machine_id = action["payload"].get("selected_machine_id")
        if source_store_id is None or target_machine_id is None:
            return None
        if str(source_store_id).endswith(":loaded"):
            return None

        snapshot = observation.simulation_configuration_snapshot
        target_store_id = f"{target_machine_id} in"
        try:
            source_position = self.find_store_position(
                snapshot,
                str(source_store_id),
            )
            target_position = self.find_store_position(
                snapshot,
                target_store_id,
            )
        except KeyError:
            return None

        # Die Simulation bewegt den Roboter achsenweise; daher entspricht die
        # relevante Wegstrecke der Manhattan- beziehungsweise L1-Distanz.
        axis_aligned_distance = sum(
            abs(float(target_position[axis]) - float(source_position[axis]))
            for axis in ("x", "y", "z")
        )
        movement_speed = self.recovery_transport_speed(
            snapshot,
            target_machine_state,
        )
        if movement_speed <= 0.0:
            return None
        return self.kehrwert_scale(axis_aligned_distance / movement_speed)

    # Verwendet für die Schätzung die konfigurierte Geschwindigkeit eines
    # Korridorarms im Zielkorridor; falls dieser nicht im Snapshot steht,
    # dient die Geschwindigkeit eines Main-Roboters als Fallback.
    @staticmethod
    def recovery_transport_speed(
        snapshot: dict[str, object],
        target_machine_state: dict[str, object],
    ) -> float:
        corridor_id = target_machine_state.get("corridor_id")
        states = snapshot.get("simulation_object_states_by_id", {})
        corridor_arm_speeds = [
            float(state["movement_speed"])
            for state in states.values()
            if state.get("object_type") == "corridor_arm_robot"
            and state.get("corridor_id") == corridor_id
            and float(state.get("movement_speed", 0.0)) > 0.0
        ]
        if corridor_arm_speeds:
            return corridor_arm_speeds[0]

        main_robot_speeds = [
            float(state["movement_speed"])
            for state in states.values()
            if state.get("object_type") == "main_robot"
            and float(state.get("movement_speed", 0.0)) > 0.0
        ]
        if main_robot_speeds:
            return main_robot_speeds[0]
        return 0.0



    # Wählt die passende Bewertungsmethode für einen Roboter- oder Maschinen-Pick aus.
    # Beispiel: pick_main_robot wird an evaluate_robot_pick_action weitergeleitet.
    def evaluate_pick_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        if action["action_type"] == "pick_machine_job":
            return self.evaluate_machine_pick_action(action, observation)
        if action["action_type"] in {
            "pick_main_robot",
            "pick_corridor_arm_robot",
        }:
            return self.evaluate_robot_pick_action(action, observation)


    # Berechnet beim Roboter-Pick den gewichteten Durchschnitt aus EDD-,
    # Entnahmezeit- und Transportzeit-Teilwerten.
    def evaluate_robot_pick_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        parts = [
            (
                self.queue_priority_value(action, observation),
                self.weights.queue_priority_gewicht,
            ),
        ]
        source_storage_value = self.pick_source_storage_time_value(action)
        if source_storage_value is not None:
            parts.append(
                (
                    source_storage_value,
                    self.weights.pick_source_storage_time_gewicht,
                )
            )
        parts.append(
            (
                self.transport_time_value(action, observation),
                self.weights.pick_short_transport_time_gewicht,
            )
        )
        return self.calculate_action_score(parts)

    # Bewertet einen Maschinen-Pick nach EDD, kurzer Operationsdauer und Werkzeugzustand.
    # Beispiel: Passendes Werkzeug erhöht den Score um machine_pick_tool_match_gewicht.
    def evaluate_machine_pick_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        # Startwert aus der EDD-/Queue-Priorität des ausgewählten Jobs.
        parts = [
            (
                self.queue_priority_value(action, observation),
                self.weights.queue_priority_gewicht,
            ),
        ]
        job_state = self.selected_job_state(action, observation)
        operation_id = job_state["selected_operation_id"]

        model = observation.simulation_configuration_snapshot["configuration_model"]
        operation = model["operations_by_id"][operation_id]
        duration = float(operation["duration"])
        # Fügt den normierten Vorteil einer kurzen Operation als Teilwert hinzu.
        parts.append(
            (
                self.kehrwert_scale(duration),
                self.weights.machine_pick_operation_duration_gewicht,
            )
        )

        required_tool_id = operation.get("tool_type_id")
        machine_state = self.current_state(observation)
        mounted_tool_id = machine_state.get("mounted_tool_type_id")
        if required_tool_id is not None:
            # Eine Werkzeugpassung ist ein normierter Teilwert: passend=1,
            # nicht passend=0.
            tool_match_value = (
                1.0 if mounted_tool_id == required_tool_id else 0.0
            )
            parts.append(
                (tool_match_value, self.weights.machine_pick_tool_match_gewicht)
            )

        consumed_life = float(operation.get("consumes_life_units", 0.0))
        if required_tool_id is not None and consumed_life > 0.0:
            remaining_life = max(float(
                machine_state.get("remaining_life_units_by_tool", {})
                .get(required_tool_id, 0.0)
            ), 0.0)
            # Eine größere Lebensdauerreserve ist besser. Das Verhältnis
            # zur benötigten Lebensdauer wird deshalb direkt skaliert.
            tool_life_score = self.direkte_scale(
                remaining_life / consumed_life
            )
            parts.append((tool_life_score, self.weights.machine_pick_tool_reserve_gewicht))
        # Gibt den gewichteten Durchschnitt der Maschinen-Pick-Teilwerte zurück.
        return self.calculate_action_score(parts)

    # Wandelt die storage_out_time des Quell-Stores in einen Pick-Score um.
    # Beispiel: storage_out_time=2 ergibt den Faktor 1/(1+2)=0.3333.
    def evaluate_pick_source_storage_time(
        self,
        action: dict[str, Any],
    ) -> float:
        storage_time_score = self.pick_source_storage_time_value(action)
        if storage_time_score is None:
            return 0.0
        return storage_time_score * self.weights.pick_source_storage_time_gewicht

    # Gibt den ungewichteten Vorteil der Entnahmezeit zurück.
    def pick_source_storage_time_value(
        self,
        action: dict[str, Any],
    ) -> float | None:
        if "storage_out_time" not in action["payload"]:
            return None
        storage_out_time = float(action["payload"]["storage_out_time"])
        return self.kehrwert_scale(storage_out_time)


    # Berechnet beim Place-Ziel den gewichteten Durchschnitt aus Kapazitäts-,
    # Einlagerungs-, Transport-, Queue- und Operations-Teilwerten.
    def evaluate_place_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        parts = [
            (
                self.target_store_capacity_value(action, observation),
                self.weights.target_store_free_capacity_gewicht,
            ),
            (
                self.transport_time_value(action, observation),
                self.weights.place_short_transport_time_gewicht,
            ),
        ]

        storage_time_value = self.place_target_storage_time_value(action)
        if storage_time_value is not None:
            parts.append(
                (
                    storage_time_value,
                    self.weights.place_target_storage_time_gewicht,
                )
            )

        machine_queue_value = self.place_machine_queue_value(
            action,
            observation,
        )
        if machine_queue_value is not None:
            parts.append(
                (
                    machine_queue_value,
                    self.weights.place_machine_queue_length_gewicht,
                )
            )

        processing_time_value = self.place_processing_time_value(
            action,
            observation,
        )
        if processing_time_value is not None:
            parts.append(
                (
                    processing_time_value,
                    self.weights.place_operation_duration_gewicht,
                )
            )

        return self.calculate_action_score(parts)

    # Berechnet aus Store-Position, Objektposition und Bewegungsgeschwindigkeit einen Transport-Score.
    # Beispiel: Distanz 3 und Geschwindigkeit 1 ergeben 1/(1+3)=0.25 vor der Gewichtung.
    def evaluate_transport_time(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
        weight: float,
    ) -> float:
        return self.transport_time_value(action, observation) * weight

    # Gibt den ungewichteten Vorteil einer kurzen Transportzeit zurück.
    def transport_time_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        target_store_id = str(action["payload"]["target_store_id"])
        current_state = self.current_state(observation)
        target = self.find_store_position(
            observation.simulation_configuration_snapshot,
            target_store_id,
        )
        travel_distance = (
            abs(float(target["x"]) - float(current_state["x"]))
            + abs(float(target["y"]) - float(current_state["y"]))
            + abs(float(target["z"]) - float(current_state["z"]))
        )
        movement_speed = float(self.current_state(observation)["movement_speed"])
        if movement_speed <= 0.0:
            return 0.0
        estimated_transport_time = travel_distance / movement_speed
        return self.kehrwert_scale(estimated_transport_time)

    # Leitet ältere Aufrufe unverändert an evaluate_transport_time weiter.
    # Beispiel: evaluate_short_transport_time(...) liefert exakt denselben Wert wie die Zielmethode.
    def evaluate_short_transport_time(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
        weight: float,
    ) -> float:
        return self.evaluate_transport_time(action, observation, weight)

    # Bewertet die storage_in_time des Place-Ziel-Stores; ein fehlendes Feld ergibt 0.
    # Beispiel: storage_in_time=1 ergibt den Faktor 1/(1+1)=0.5 vor der Gewichtung.
    def evaluate_place_target_storage_time(
        self,
        action: dict[str, Any],
    ) -> float:
        storage_time_score = self.place_target_storage_time_value(action)
        if storage_time_score is None:
            return 0.0
        return storage_time_score * self.weights.place_target_storage_time_gewicht

    # Gibt den ungewichteten Vorteil der Einlagerungszeit zurück.
    def place_target_storage_time_value(
        self,
        action: dict[str, Any],
    ) -> float | None:
        if "storage_in_time" not in action["payload"]:
            return None
        storage_in_time = float(action["payload"]["storage_in_time"])
        return self.kehrwert_scale(storage_in_time)

    # Bewertet die Länge der Input-Warteschlange der Zielmaschine beim Place.
    # Beispiel: queue_length=2 ergibt den Faktor 1/(1+2)=0.3333 vor der Gewichtung.
    def evaluate_place_machine_queue(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        queue_value = self.place_machine_queue_value(action, observation)
        if queue_value is None:
            return 0.0
        return queue_value * self.weights.place_machine_queue_length_gewicht

    # Gibt den ungewichteten Vorteil einer kurzen Maschinenwarteschlange zurück.
    def place_machine_queue_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float | None:
        # Liest die Maschine, in deren Eingangspuffer der Job abgelegt werden soll.
        machine_id = action["payload"].get("selected_machine_id")
        # Ohne ausgewählte Zielmaschine kann keine Maschinenwarteschlange bewertet werden.
        if machine_id is None:
            return None
        try:
            # Sucht den aktuellen Zustand der Zielmaschine im Beobachtungssnapshot.
            machine_state = self.find_machine_state(
                observation.simulation_configuration_snapshot,
                str(machine_id),
            )
        except KeyError:
            # Eine unbekannte Maschine erhält keinen zusätzlichen Queue-Score.
            return None
        # Ermittelt die Anzahl der Jobs im Eingangspuffer der Zielmaschine.
        queue_length = float(machine_state["input_storage"]["count"])
        # Je kürzer die Warteschlange, desto höher ist der Score: 1/(1+Anzahl).
        return self.kehrwert_scale(queue_length)

    # Bewertet die Dauer der beim Place ausgewählten nächsten Operation.
    # Beispiel: duration=4 ergibt den Faktor 1/(1+4)=0.2 vor der Gewichtung.
    def evaluate_place_processing_time(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        processing_time_score = self.place_processing_time_value(
            action,
            observation,
        )
        if processing_time_score is None:
            return 0.0
        return processing_time_score * self.weights.place_operation_duration_gewicht

    # Gibt den ungewichteten Vorteil einer kurzen Bearbeitungszeit zurück.
    def place_processing_time_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float | None:
        operation_id = action["payload"].get("selected_operation_id")
        if operation_id is None:
            return None
        model = observation.simulation_configuration_snapshot["configuration_model"]
        duration = float(model["operations_by_id"][operation_id]["duration"])
        return self.kehrwert_scale(duration)


    # Gibt für eine technisch bereits zugelassene Process-Aktion den neutralen Score 0 zurück.
    # Beispiel: process_machine_job wird nicht zusätzlich heuristisch bevorzugt.
    def evaluate_process_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.calculate_action_score([(0.0, 1.0)])


    # Multipliziert die Queue-Priorität mit dem dafür konfigurierten Heuristikgewicht.
    # Beispiel: queue_priority=0.4 und queue_priority_gewicht=0.5 ergeben den Score 0.2.
    def evaluate_queue_priority(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.queue_priority_value(action, observation) * self.weights.queue_priority_gewicht

    # Gibt den ungewichteten Queue-/EDD-Teilwert zurück.
    def queue_priority_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.read_queue_priority(action, observation)

    # Bewertet den freien Kapazitätsanteil eines Ziel- oder Output-Stores.
    # Beispiel: 4 freie Plätze bei Kapazität 10 ergeben den Faktor 0.4 vor der Gewichtung.
    def evaluate_target_store_capacity(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.target_store_capacity_value(action, observation) * self.weights.target_store_free_capacity_gewicht

    # Gibt den ungewichteten Anteil der freien Zielkapazität zurück.
    def target_store_capacity_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        target_store_id = str(action["payload"]["target_store_id"])
        store_state = self.find_store_state(
            observation.simulation_configuration_snapshot,
            target_store_id,
        )
        return self.normalize_ratio(
            store_state["available_capacity"],
            store_state["capacity"],
        )
