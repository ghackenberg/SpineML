from typing import Any

from ..ActionGeneration.ActionGenerator import SpineActionGenerator
from ...SimulationInterface.InterfaceTypes import ActionEvaluator, PolicyObservation
from .HeuristicWeights import HeuristicWeights

class LocalHeuristicActionEvaluator(ActionEvaluator):
    """Bewertet die vollständigen Kandidaten des Generators mit lokalen Gewichten."""

    DEFAULT_WAIT_SCORE = 0.01

    # Store the configurable weight set used by all evaluation methods.
    # Example: HeuristicWeights(queue_priority_weight=0.4) is stored in self.weights.
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

    @staticmethod
    def inverse_scale(value: float) -> float:
        return 1.0 / (1.0 + float(value))

    @staticmethod
    def direct_scale(value: float) -> float:
        value = float(value)
        return value / (1.0 + value)

    @staticmethod
    def calculate_edd_priority(latest_end_time: float, current_time: float) -> float:
        return SpineActionGenerator.calculate_edd_priority(latest_end_time, current_time)

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
        self, action: dict[str, Any], observation: PolicyObservation
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

    # Berechnet das Verhältnis value/maximum ohne Begrenzung oder Ersatzwert.
    @staticmethod
    def normalize_ratio(value: float, maximum: float) -> float:
        return float(value) / float(maximum)

    # Berechnet den gewichteten Durchschnitt der Teilwerte vor etwaigen Strafabzügen.
    # Bei Teilwerten in [0, 1] und positiven Gewichten liegt dieser Durchschnitt ebenfalls in [0, 1].
    @staticmethod
    def calculate_action_score(
        weighted_parts: list[tuple[float, float]],
    ) -> float:
        weighted_sum = 0.0
        weight_sum = 0.0
        for value, weight in weighted_parts:
            score_weight = float(weight)
            score_value = float(value)
            weighted_sum += score_value * score_weight
            weight_sum += score_weight

        return weighted_sum / weight_sum

    # Gibt den Zustand des aktuell von der Policy betrachteten Objekts zurück.
    # Beispiel: current_object_id="Main robot" liefert dessen Zustands-Dictionary.
    def current_state(self, observation: PolicyObservation) -> dict[str, object]:
        snapshot = observation.simulation_configuration_snapshot
        return snapshot["simulation_object_states_by_id"][
            observation.current_object_id
        ]


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
            return self.calculate_action_score([(1.0, self.weights.complete_job_weight)])

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


    # Bewertet Warten mit 1 - EDD: Je dringender der Job, desto niedriger der Score.
    # Ohne zugehörigen Job oder dessen Deadline gilt der feste Ersatzwert.
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
            wait_value = self.DEFAULT_WAIT_SCORE
        else:
            latest_end_time = job_summary.get("latest_end_time")
            if latest_end_time is None:
                wait_value = self.DEFAULT_WAIT_SCORE
            else:
                current_time = float(
                    observation.simulation_configuration_snapshot["time"]
                )
                edd_priority = self.calculate_edd_priority(
                    float(latest_end_time),
                    current_time,
                )
                wait_value = 1.0 - edd_priority

        return self.calculate_action_score([
            (wait_value, self.weights.wait_action_weight),
        ])


    # Bewertet eine Freigabe mit EDD und der durchschnittlichen Bearbeitungszeit
    # der möglichen Operationsrouten.
    # Beispiel: EDD=0.2, release_edd_weight=0.7, erwartete Bearbeitungszeit=4 und
    # release_average_route_duration_weight=0.3 ergeben 0.2*0.7 + 1/(1+4)*0.3=0.20.
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
        # Estimate the expected total processing time of the possible routes.
        estimated_processing_time = self.estimate_release_processing_time(
            current_state,
            observation,
        )
        # Kürzere erwartete Bearbeitungszeiten erhalten einen höheren Score.
        processing_time_score = self.inverse_scale(estimated_processing_time)
        return self.calculate_action_score([
            (edd_priority, self.weights.release_edd_weight),
            (
                processing_time_score,
                self.weights.release_average_route_duration_weight,
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

        # The SPT rule uses the average total processing time
        # as the expected processing time.
        return sum(route_processing_times) / len(route_processing_times)

    # Berechnet die verbleibende Zeit bis zur Deadline des Jobs.
    # Beispiel: latest_end_time=10 und time=7 ergeben remaining_time=3.
    def estimate_remaining_time(self, current_state: dict) -> float:
        return current_state["latest_end_time"] - current_state["time"]

    # Prüft, ob die Deadline des Auftrags erreicht oder überschritten ist.
    # Beispiel: remaining_time=3 ergibt False; remaining_time=0 ergibt True.
    def is_deadline_reached(
        self,
        current_state: dict,
    ) -> bool:
        return self.estimate_remaining_time(current_state) <= 0

    # Evaluates scrap, waiting, downgrade, or one of the rework options.
    # Example: action_type="downgrade_product" returns the downgrade score.
    def evaluate_defect_action(
        self,
        action_type: str,
        action: dict[str, Any],
        current_state: dict,
        observation: PolicyObservation,
    ) -> float:
        # Ausschuss ist der einzige Kandidat; EDD und Gewichte sind nicht nötig.
        if action_type == "job_scrap":
            return 1.0

        deadline_reached = self.is_deadline_reached(current_state)
        current_time = float(
            observation.simulation_configuration_snapshot["time"]
        )
        # Calculates the EDD priority of the defective job for action scoring.
        defect_edd_priority = self.calculate_edd_priority(
            float(current_state["latest_end_time"]),
            current_time,
        )

        if action_type == "wait_job":
            # A defective job may wait; the more urgent its deadline,
            # the lower the score of this wait action.
            score = self.calculate_action_score([
                (1.0 - defect_edd_priority, self.weights.wait_defect_job_weight),
            ])
            # Ab der Deadline ergibt die Standardstrafe 0.5 - 0.3 einen Score <= 0.3.
            if deadline_reached:
                score -= self.weights.deadline_missed_wait_penalty_weight
            # Negative Endscores bleiben für den Vergleich der Aktionen erhalten.
            return score

        if action_type == "downgrade_product":
            # A higher severity makes downgrading more attractive than rework.
            defect_severity = float(current_state.get("defect_severity", 0.0))
            parts = [
                (
                    defect_severity,
                    self.weights.product_downgrade_defect_severity_weight,
                ),
            ]

            # Standardgewichte 0.5 : 0.5 ergeben s + 0.5 * (1 - s).
            # Der Bonus hebt Herabstufung damit ab der Deadline in [0.5, 1].
            if deadline_reached:
                parts.append((1.0, self.weights.deadline_reached_downgrade_bonus_weight))
            # Returns the final score of the downgrade action.
            return self.calculate_action_score(parts)

        if action_type in {
            "job_rework_on_defect_machine",
            "job_rework_on_alternative_machine",
        }:
            return self.evaluate_defect_recovery_action(
                action_type,
                action,
                observation,
                deadline_reached,
            )

        return 0.0

    # Bewertet beide Nacharbeitsarten mit denselben Kriterien.
    def evaluate_defect_recovery_action(
        self,
        action_type: str,
        action: dict[str, Any],
        observation: PolicyObservation,
        deadline_reached: bool,
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
                self.inverse_scale(
                    float(machine_state["input_storage"]["count"])
                ),
                self.weights.defect_recovery_machine_queue_length_weight,
            ),
        ]

        transport_time_value = self.defect_recovery_transport_time_value(
            action,
            observation,
            machine_state,
        )
        if transport_time_value is not None:
            parts.append(
                (
                    transport_time_value,
                    self.weights.defect_recovery_transport_time_weight,
                )
            )

        # Jede Operation legt einen benötigten Werkzeugtyp fest.
        required_tool_id = operation["tool_type_id"]
        mounted_tool_id = machine_state.get("mounted_tool_type_id")
        parts.append(
            (
                1.0 if mounted_tool_id == required_tool_id else 0.0,
                self.weights.defect_recovery_tool_match_weight,
            )
        )

        consumed_life = float(operation.get("consumed_life_units", 0.0))
        if consumed_life > 0.0:
            remaining_life = float(
                machine_state.get("remaining_life_units_by_tool", {})
                .get(required_tool_id, 0.0)
            )
            parts.append(
                (
                    self.direct_scale(remaining_life / consumed_life),
                    self.weights.defect_recovery_tool_reserve_weight,
                )
            )

        score = self.calculate_action_score(parts)
        if deadline_reached:
            # Die Standardstrafe 1 - 0.5 begrenzt den Endscore auf höchstens 0.5.
            if action_type == "job_rework_on_defect_machine":
                penalty = self.weights.rework_defect_machine_deadline_penalty_weight
            else:
                penalty = self.weights.rework_alternative_machine_deadline_penalty_weight
            score -= penalty
        # Negative Endscores bleiben für den Vergleich der Aktionen erhalten.
        return score

    # Schätzt die Transportzeit vom aktuellen Jobstandort zum Eingangsstore
    # der ausgewählten rework machine.
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
        return self.inverse_scale(axis_aligned_distance / movement_speed)

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


    # Calculate the weighted average of EDD-,
    # Entnahmezeit- und Transportzeit-Teilwerten.
    def evaluate_robot_pick_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        parts = [
            (
                self.queue_priority_value(action, observation),
                self.weights.queue_priority_weight,
            ),
        ]
        source_storage_value = self.pick_source_storage_time_value(action)
        if source_storage_value is not None:
            parts.append(
                (
                    source_storage_value,
                    self.weights.pick_source_storage_time_weight,
                )
            )
        parts.append(
            (
                self.transport_time_value(action, observation),
                self.weights.pick_short_transport_time_weight,
            )
        )
        return self.calculate_action_score(parts)

    # Bewertet einen Maschinen-Pick nach EDD, kurzer Operationsdauer und Werkzeugzustand.
    # Beispiel: Ein bereits passendes Werkzeug erhält den Teilwert 1, sonst 0.
    def evaluate_machine_pick_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        # Startwert aus der EDD-/Queue-Priorität des ausgewählten Jobs.
        parts = [
            (
                self.queue_priority_value(action, observation),
                self.weights.queue_priority_weight,
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
                self.inverse_scale(duration),
                self.weights.machine_pick_operation_duration_weight,
            )
        )

        # Jede Operation legt einen benötigten Werkzeugtyp fest.
        required_tool_id = operation["tool_type_id"]
        machine_state = self.current_state(observation)
        mounted_tool_id = machine_state.get("mounted_tool_type_id")
        # Die Werkzeugpassung geht immer ein, auch wenn kein Werkzeug montiert ist.
        tool_match_value = 1.0 if mounted_tool_id == required_tool_id else 0.0
        parts.append(
            (tool_match_value, self.weights.machine_pick_tool_match_weight)
        )

        consumed_life = float(operation.get("consumed_life_units", 0.0))
        if consumed_life > 0.0:
            remaining_life = float(
                machine_state.get("remaining_life_units_by_tool", {})
                .get(required_tool_id, 0.0)
            )
            # Eine größere Lebensdauerreserve ist besser. Das Verhältnis
            # zur benötigten Lebensdauer wird deshalb direkt skaliert.
            tool_life_score = self.direct_scale(
                remaining_life / consumed_life
            )
            parts.append((tool_life_score, self.weights.machine_pick_tool_reserve_weight))
        # Verbindet die Teilwerte zu ihrem gewichteten Durchschnitt.
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
        return storage_time_score * self.weights.pick_source_storage_time_weight

    # Gibt den unweighted Vorteil der Entnahmezeit zurück.
    def pick_source_storage_time_value(
        self,
        action: dict[str, Any],
    ) -> float | None:
        if "storage_out_time" not in action["payload"]:
            return None
        storage_out_time = float(action["payload"]["storage_out_time"])
        return self.inverse_scale(storage_out_time)


    # Calculate the weighted average of capacity-,
    # Einlagerungs-, Transport-, Queue- und Operations-Teilwerten.
    def evaluate_place_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        parts = [
            (
                self.target_store_capacity_value(action, observation),
                self.weights.target_store_free_capacity_weight,
            ),
            (
                self.transport_time_value(action, observation),
                self.weights.place_short_transport_time_weight,
            ),
        ]

        storage_time_value = self.place_target_storage_time_value(action)
        if storage_time_value is not None:
            parts.append(
                (
                    storage_time_value,
                    self.weights.place_target_storage_time_weight,
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
                    self.weights.place_machine_queue_length_weight,
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
                    self.weights.place_operation_duration_weight,
                )
            )

        return self.calculate_action_score(parts)

    # Berechnet aus Store-Position, Objektposition und Bewegungsgeschwindigkeit einen Transport-Score.
    # Beispiel: Distanz 3 und Geschwindigkeit 1 ergeben 1/(1+3)=0.25 vor der Weightung.
    def evaluate_transport_time(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
        weight: float,
    ) -> float:
        return self.transport_time_value(action, observation) * weight

    # Gibt den unweighted Vorteil einer kurzen Transportzeit zurück.
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
        return self.inverse_scale(estimated_transport_time)

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
    # Beispiel: storage_in_time=1 ergibt den Faktor 1/(1+1)=0.5 vor der Weightung.
    def evaluate_place_target_storage_time(
        self,
        action: dict[str, Any],
    ) -> float:
        storage_time_score = self.place_target_storage_time_value(action)
        if storage_time_score is None:
            return 0.0
        return storage_time_score * self.weights.place_target_storage_time_weight

    # Gibt den unweighted Vorteil der Einlagerungszeit zurück.
    def place_target_storage_time_value(
        self,
        action: dict[str, Any],
    ) -> float | None:
        if "storage_in_time" not in action["payload"]:
            return None
        storage_in_time = float(action["payload"]["storage_in_time"])
        return self.inverse_scale(storage_in_time)

    # Bewertet die Länge der Input-Warteschlange der Zielmaschine beim Place.
    # Beispiel: queue_length=2 ergibt den Faktor 1/(1+2)=0.3333 vor der Weightung.
    def evaluate_place_machine_queue(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        queue_value = self.place_machine_queue_value(action, observation)
        if queue_value is None:
            return 0.0
        return queue_value * self.weights.place_machine_queue_length_weight

    # Gibt den unweighted Vorteil einer kurzen Maschinenwarteschlange zurück.
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
        return self.inverse_scale(queue_length)

    # Bewertet die Dauer der beim Place ausgewählten nächsten Operation.
    # Beispiel: duration=4 ergibt den Faktor 1/(1+4)=0.2 vor der Weightung.
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
        return processing_time_score * self.weights.place_operation_duration_weight

    # Gibt den unweighted Vorteil einer kurzen Bearbeitungszeit zurück.
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
        return self.inverse_scale(duration)


    # Gibt für eine technisch bereits zugelassene Process-Aktion den neutralen Score 0 zurück.
    # Beispiel: process_machine_job wird nicht zusätzlich heuristisch bevorzugt.
    def evaluate_process_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.calculate_action_score([(0.0, 1.0)])


    # Multiply the queue priority by its configured heuristic weight.
    # Beispiel: queue_priority=0.4 und queue_priority_weight=0.5 ergeben den Score 0.2.
    def evaluate_queue_priority(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.queue_priority_value(action, observation) * self.weights.queue_priority_weight

    # Gibt den unweighted Queue-/EDD-Teilwert zurück.
    def queue_priority_value(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.read_queue_priority(action, observation)

    # Bewertet den freien Kapazitätsanteil eines Ziel- oder Output-Stores.
    # Beispiel: 4 freie Plätze bei Kapazität 10 ergeben den Faktor 0.4 vor der Weightung.
    def evaluate_target_store_capacity(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        return self.target_store_capacity_value(action, observation) * self.weights.target_store_free_capacity_weight

    # Gibt den unweighted Anteil der freien Zielkapazität zurück.
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
