from ..Interface.InterfaceTypes import ActionGenerator, PolicyObservation


class SpineActionGenerator(ActionGenerator):
    """Erzeugt technisch mögliche Aktionen aus einer Policy-Beobachtung."""

    MIN_NACHARBEIT_DEFEKT_SCHWERGRAD = 0.001
    MAX_NACHARBEIT_DEFEKT_SCHWERGRAD = 0.6


    # Erzeugt Aktionskandidaten und entfernt exakt doppelte Aktionen.
    # Beispiel: Zwei gleiche wait_job-Aktionen werden zu einer einzigen Aktion.
    def generate_actions(self, observation: PolicyObservation) -> list[dict]:
        """Erzeugt technisch mögliche Aktionen und entfernt identische Duplikate."""
        actions = self._generate_actions(observation)
        unique_actions = []
        seen = set()
        for action in actions:
            # Vergleichsschlüssel aus Aktionstyp und Payload zum Erkennen von Duplikaten.
            key = (action.get("action_type"), repr(sorted(action.get("payload", {}).items())))
            if key not in seen:
                seen.add(key)
                unique_actions.append(action)
        return unique_actions

    # Erzeugt anhand des Objektzustands die rohen Aktionskandidaten.
    # Beispiel: Ein Maschinenzustand ohne aktuellen Job erzeugt Pick-Kandidaten.
    def _generate_actions(self, observation: PolicyObservation) -> list[dict]:
        """Erzeugt technisch mögliche Aktionen je nach Typ und Zustand des Objekts."""
        current_state = self.current_state(observation)
        if current_state["object_type"] == "main_robot":
            if current_state["current_job_id"] is None:
                return self.create_main_robot_pick_actions(observation)
            return self.create_main_robot_place_actions(observation)
        if current_state["object_type"] == "corridor_arm_robot":
            if current_state["current_job_id"] is None:
                return self.create_corridor_arm_robot_pick_actions(observation)
            return self.create_corridor_arm_robot_place_actions(observation)
        if current_state["object_type"] == "machine":
            if current_state["current_job_id"] is None:
                return self.create_machine_pick_actions(observation)
            return self.create_machine_process_actions(observation)
        actions = []

        # Ein fertiger Job erhält einmalig die Aktion zum Setzen seines Terminstatus.
        if current_state["completed_time"] is not None and current_state["due_state"] is None:
            return self.create_completion_actions_for_job(observation)

        # Ein defekter Job erhält die möglichen Aktionen für Nacharbeit oder Ausschuss.
        if current_state["general_state"] == "defect":
            return self.create_defect_actions_for_job(observation)

        # Ein noch nicht freigegebener Job erhält eine Freigabeaktion.
        if not current_state["released"]:
            actions.append(self.create_release_job_action(observation))

        # Für den Job wird zusätzlich eine Warteaktion angeboten.
        actions.extend(self.create_wait_actions_for_job(observation))
        return actions



    # Gibt den Zustands-Datensatz des aktuell beobachteten Objekts zurück.
    # Beispiel: current_object_id="job_1" liefert den Zustand von "job_1".
    def current_state(self, observation: PolicyObservation) -> dict[str, object]:
        states_by_id = observation.simulation_configuration_snapshot[
            "simulation_object_states_by_id"
        ]
        return states_by_id[observation.current_object_id]

    # Filtert die Zustands-Datensätze nach dem gewünschten Objekttyp.
    # Beispiel: object_type="machine" liefert nur Maschinenzustände.
    def states_of_type(self, snapshot: dict, object_type: str) -> list[dict]:
        states_by_id = snapshot.get("simulation_object_states_by_id", {})
        return [
            state
            for state in states_by_id.values()
            if state.get("object_type") == object_type
        ]

    # Gibt das Konfigurationsmodell aus der Beobachtung zurück.
    # Beispiel: model(observation) liefert snapshot["configuration_model"].
    def model(self, observation: PolicyObservation) -> dict:
        return observation.simulation_configuration_snapshot["configuration_model"]

    # Gibt die Konfigurationsdaten eines Produkttyps anhand seiner ID zurück.
    # Beispiel: product_type(observation, "p1") liefert die Daten von Produkttyp "p1".
    def product_type(self, observation: PolicyObservation, product_type_id: str) -> dict:
        return self.model(observation)["product_types_by_id"][product_type_id]


    # Gibt die Konfigurationsdaten einer Operation anhand ihrer ID zurück.
    # Beispiel: operation(observation, "op1") liefert die Daten der Operation "op1".
    def operation(self, observation: PolicyObservation, operation_id: str) -> dict:
        return self.model(observation)["operations_by_id"][operation_id]


    # Gibt die Konfigurationsdaten einer Maschine anhand ihrer ID zurück.
    # Beispiel: machine(observation, "m1") liefert die Daten der Maschine "m1".
    def machine(self, observation: PolicyObservation, machine_id: str) -> dict:
        return self.model(observation)["machines_by_id"][machine_id]


    # Prüft, ob der Store mindestens einen Job enthält.
    # Beispiel: store={"has_items": True} ergibt True.
    def store_has_items(self, store: dict) -> bool:
        return store["has_items"]

    # Prüft, ob der Store noch freie Kapazität besitzt.
    # Beispiel: store={"has_capacity": False} ergibt False.
    def store_has_free_capacity(self, store: dict) -> bool:
        return store["has_capacity"]
    # Gibt die im Store beobachteten Job-Zusammenfassungen als Liste zurück.
    # Beispiel: store={"job_summaries": [job_a, job_b]} liefert [job_a, job_b].
    def store_jobs(self, store: dict) -> list[dict]:
        return list(store["job_summaries"])

    # Gibt die ID eines Jobs als String zurück.
    # Beispiel: job={"job_id": 7} liefert "7".
    def job_id(self, job: dict) -> str:
        return str(job["job_id"])

    # Erzeugt für jeden Job im Store eine Pick-Aktion.
    # Beispiel: Ein Store mit J1 und J2 erzeugt zwei Pick-Aktionen.
    def create_pick_actions_for_store(
        self,
        action_type: str,
        target_type: str,
        target_store: dict,
        extra_payload: dict | None = None,
    ) -> list[dict]:
        actions = []
        extra_payload = {} if extra_payload is None else extra_payload
        for job in self.store_jobs(target_store):
            payload = {
                "target_type": target_type,
                "target_store_id": target_store["store_id"],
                "selected_job_id": self.job_id(job),
            }
            payload.update(extra_payload)
            actions.append({
                "action_type": action_type,
                "payload": payload,
            })
        return actions


    # Prüft, ob die Maschine frei ist und beide Puffer Platz haben.
    # Beispiel: Wartende Maschine ohne Job und mit Platz in beiden Puffern ergibt True.
    def machine_available_for_nacharbeit(self, machine_observation: dict) -> bool:
        if machine_observation["current_job_id"] is not None:
            return False
        if machine_observation["state"] != "waiting":
            return False
        if machine_observation["input_storage"]["available_capacity"] <= 0:
            return False
        if machine_observation["output_storage"]["available_capacity"] <= 0:
            return False
        return True

    # Sucht den Zustands-Datensatz der Maschine, die den Defekt verursacht hat.
    # Beispiel: defect_machine_id="m1" liefert den beobachteten Zustand von "m1".
    def defect_machine_observation(self, current_state: dict, snapshot: dict) -> dict:
        # Liest aus dem defekten Job die ID der Maschine, die den Defekt verursacht hat.
        defect_machine_id = current_state["defect_machine_id"]

        machine_observations_by_id = {}
        machine_observations = self.states_of_type(snapshot, "machine")

        for machine_observation in machine_observations:
            machine_id = machine_observation["machine_name"]
            machine_observations_by_id[machine_id] = machine_observation

        return machine_observations_by_id[defect_machine_id]

    # Ermittelt Nacharbeitsrouten mit einer anderen Maschine als der Defektmaschine.
    # Beispiel: Defekt auf m1 lässt nur Routen zu, die mit einer anderen Maschine beginnen.
    def find_nacharbeit_routes_with_alternative_machine(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        model = self.model(observation)
        # Liest aus dem Job die ID der Operation, bei der der Defekt entstanden ist.
        defect_operation_id = current_state["defect_operation_id"]
        # Liest aus dem Job die ID der Maschine, auf der der Defekt entstanden ist.
        defect_machine_id = current_state["defect_machine_id"]
        return self.find_alternative_nacharbeit_routes(
            defect_operation_id,
            defect_machine_id,
            current_state["target_product_type_id"],
            current_state["layout_id"],
            model,
        )

    # Ermittelt alternative Maschinen für die Wiederholung der Defektoperation.
    # Beispiel: Eine Defektoperation auf m1 kann als nächste Route m2 statt m1 liefern.
    def find_alternative_nacharbeit_routes(
        self,
        defect_operation_id: str | None,
        defect_machine_id: str | None,
        target_product_type_id: str | None,
        layout_id: str,
        model: dict,
    ) -> list[dict]:
        if not defect_operation_id or not defect_machine_id or not target_product_type_id:
            return []

        defect_operation = model["operations_by_id"].get(defect_operation_id)
        if defect_operation is None:
            return []

        # Berechnet den weiteren Weg nach der wiederholten Defektoperation bis zum Zielprodukt.
        remaining_operation_sequences = self.calculate_operation_sequences_between(
            defect_operation["produces_product_type_id"],
            target_product_type_id,
            model,
        )

        route_options = []
        for remaining_operation_sequence in remaining_operation_sequences:
            # Setzt die Defektoperation vor die Restfolge; die Liste enthält nur Operations-IDs.
            operation_sequence = [defect_operation_id, *remaining_operation_sequence]
            machine_sequences = self.calculate_machine_sequences_from_operation_sequence(
                list(operation_sequence),
                layout_id,
                model,
            )
            for machine_sequence in machine_sequences:
                if not machine_sequence or machine_sequence[0] == defect_machine_id:
                    continue
                route_options.append({
                    "operation_sequence": list(operation_sequence),
                    "machine_sequence": list(machine_sequence),
                    "next_operation_id": operation_sequence[0],
                    "next_machine_id": machine_sequence[0],
                })
        return route_options


    # Prüft, ob ein Job die normale Produktionsroute nicht verwenden darf.
    # Normaler Job:
    # general_state == "intakt"
    # downgraded == False
    # bearbeitungs_state != "unconfigured"
    # bearbeitungs_state != "defect"
    def job_cannot_use_normal_production_route(self, job: dict) -> bool:
        if job["general_state"] == "defect":
            return True

        if job["general_state"] == "ausschuss":
            return True

        if job["downgraded"]:
            return True

        if job["bearbeitungs_state"] == "unconfigured":
            return True

        if job["bearbeitungs_state"] == "defect":
            return True

        return False
    
    # Ein normaler Job ist intakt, nicht herabgestuft und weder unconfigured noch defect.
    # Für diesen Job gibt die Methode alle technisch möglichen Operations- und Maschinenfolgen zurück.
    # Bei festgelegter Nacharbeit wird nur die ausgewählte einzelne Route zurückgegeben; sonst ggf. [].
    def selectable_routes_for_job(self, job: dict, layout_id: str, model: dict) -> list[dict]:
        # Prüft, ob für den defekten Job bereits eine Nacharbeitsstrategie festgelegt wurde.
        if (
            job.get("defect_recovery_strategy") in {
                "nacharbeiten_auf_defektmaschine",
                "nacharbeiten_auf_alternativer_maschine",
            }
            and job.get("selected_operation_id") is not None
            and job.get("selected_machine_id") is not None
        ):
            # Gibt die festgelegte einzelne Nacharbeitsoperation und Nacharbeitsmaschine zurück.
            return [
                {
                    "operation_sequence": [job["selected_operation_id"]],
                    "machine_sequence": [job["selected_machine_id"]],
                    "next_operation_id": job["selected_operation_id"],
                    "next_machine_id": job["selected_machine_id"],
                }
            ]

        if self.job_cannot_use_normal_production_route(job):
            return []

        current_product_type_id = job["bearbeitungs_state"]
        target_product_type_id = job["target_product_type_name"]
        if current_product_type_id == target_product_type_id:
            return []

        route_options = []
        operation_sequences = self.calculate_operation_sequences_between(
            current_product_type_id,
            target_product_type_id,
            model,
        )
        for operation_sequence in operation_sequences:
            machine_sequences = self.calculate_machine_sequences_from_operation_sequence(
                list(operation_sequence),
                layout_id,
                model,
            )
            for machine_sequence in machine_sequences:
                route_options.append({
                    "operation_sequence": list(operation_sequence),
                    "machine_sequence": list(machine_sequence),
                    "next_operation_id": operation_sequence[0],
                    "next_machine_id": machine_sequence[0],
                })
        return route_options


    # Prüft, ob der Defektgrad im technisch nacharbeitbaren Bereich liegt.
    # Bereich: 0.001 <= defekt_schwergrad < 0.6; Beispiel: 0.2 ergibt True.
    def nacharbeit_is_technically_possible(self, current_state: dict) -> bool:
        defekt_schwergrad = current_state["defekt_schwergrad"]
        return (
            self.MIN_NACHARBEIT_DEFEKT_SCHWERGRAD
            <= defekt_schwergrad
            < self.MAX_NACHARBEIT_DEFEKT_SCHWERGRAD
        )

    # Erzeugt je nach Zustand mögliche Recovery-Aktionen; die Policy wählt später eine davon aus.
    # Beispiel: Nacharbeitbarkeit bietet Nacharbeit, Herabstufung und Warten; sonst wird Ausschuss angeboten.
    def create_defect_actions_for_job(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        snapshot = observation.simulation_configuration_snapshot
        # True bedeutet: Recovery läuft noch; False prüft neue Defektaktionen.
        if current_state.get("recovery_in_progress"):
            return self.create_wait_actions_for_job(observation)
        product_state_before_defect = current_state["defect_product_state_before"]

        # Ohne technisch möglichen Defektgrad wird nur die Ausschussaktion angeboten.
        if not self.nacharbeit_is_technically_possible(current_state):
            return self.create_ausschuss_actions_for_job(observation)

        # Sammelt Nacharbeit, Herabstufung und Warten gemeinsam; 
        actions = []

        alternative_routes = self.find_nacharbeit_routes_with_alternative_machine(
            observation,
        )
        for alternative_route in alternative_routes:
            actions.append({
                "action_type": "job_nacharbeiten_auf_alternativer_maschine",
                "payload": {
                    "selected_operation_id": alternative_route["next_operation_id"],
                    "selected_machine_id": alternative_route["next_machine_id"],
                    "bearbeitungs_state": product_state_before_defect,
                    "defect_recovery_strategy": "nacharbeiten_auf_alternativer_maschine",
                },
            })

        defect_machine_is_available = self.machine_available_for_nacharbeit(
            self.defect_machine_observation(current_state, snapshot)
        )
        if defect_machine_is_available:
            actions.append({
                "action_type": "job_nacharbeiten_auf_defektmaschine",
                "payload": {
                    "selected_operation_id": current_state["defect_operation_id"],
                    "selected_machine_id": current_state["defect_machine_id"],
                    "bearbeitungs_state": product_state_before_defect,
                    "defect_recovery_strategy": "nacharbeiten_auf_defektmaschine",
                },
            })

        downgraded_product_type_id = current_state["defect_product_state_target"]
        actions.append({
            "action_type": "produkt_herabstufen",
            "payload": {
                "selected_operation_id": None,
                "selected_machine_id": None,
                "bearbeitungs_state": downgraded_product_type_id,
                "general_state": "intakt",
                "downgraded": True,
                "downgrade_product_type_id": downgraded_product_type_id,
                "defect_recovery_strategy": "herabstufen",
            },
        })

        actions.append({
            "action_type": "wait_job",
            "payload": {},
        })

        return actions

    # Erzeugt die Ausschussaktion für einen Job.
    # Beispiel: Das Ergebnis ist eine job_ausschuss-Aktion mit general_state="ausschuss".
    def create_ausschuss_actions_for_job(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        return [
            {
                "action_type": "job_ausschuss",
                "payload": {
                    "selected_operation_id": None,
                    "selected_machine_id": None,
                    "general_state": "ausschuss",
                    "defect_recovery_strategy": "ausschuss",
                },
            }
        ]

    # Erzeugt die Abschlussaktion und bestimmt den Terminstatus des Jobs.
    # Beispiel: completed_time=12 und latest_end_time=10 ergeben due_state="late".
    def create_completion_actions_for_job(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        if current_state["completed_time"] > current_state["latest_end_time"]:
            due_state = "late"
        else:
            due_state = "on-time"

        return [
            {
                "action_type": "complete_job",
                "payload": {
                    "due_state": due_state,
                    "finish_process": True,
                },
            }
        ]

    # Erzeugt die Freigabeaktion mit Bearbeitungszustand, Freigabezeit und Startstore.
    # Beispiel: Ein nicht freigegebener Job erhält eine release_job-Aktion für den Startstore.
    def create_release_job_action(self, observation: PolicyObservation) -> dict:
        current_state = self.current_state(observation)
        model = self.model(observation)
        operation_sequences = self.calculate_operation_sequences(current_state["target_product_type_id"], model)

        if len(operation_sequences) == 0:
            bearbeitungs_state = current_state["target_product_type_id"]
        else:
            first_operation_sequence = operation_sequences[0]
            first_operation_id = first_operation_sequence[0]
            bearbeitungs_state = model["operations_by_id"][first_operation_id][
                "consumes_product_type_id"
            ]

        release_time = max(
            current_state["time"],
            current_state["earliest_start_time"],
        )
        return {
            "action_type": "release_job",
            "payload": {
                "bearbeitungs_state": bearbeitungs_state,
                "release_time": release_time,
                "target_store_id": current_state["start_store_id"],
                "released": True,
            },
        }

    # Erzeugt die Warteaktion für einen Job.
    # Beispiel: Das Ergebnis ist {"action_type": "wait_job", "payload": {}}.
    def create_wait_actions_for_job(self, observation: PolicyObservation) -> list[dict]:
        return [
            {
                "action_type": "wait_job",
                "payload": {},
            }
        ]


    # Erzeugt Pick-Aktionen für Start- und Korridorstores sowie eine Warteaktion.
    # Beispiel: Jobs in Start- oder Korridorstores werden zu pick_main_robot-Aktionen.
    def create_main_robot_pick_actions(self, observation: PolicyObservation) -> list[dict]:

        current_state = self.current_state(observation)
        actions = []

        actions.extend(self.create_pick_actions_for_store(
            "pick_main_robot",
            "start_storage",
            current_state["start_storage"],
            {
                "storage_out_time": current_state["storage_out_time"],
            },
        ))

        for corridor_index, corridor_storage in enumerate(current_state["corridor_storages"]):
            actions.extend(self.create_pick_actions_for_store(
                "pick_main_robot",
                "sim_corridor_store_main",
                corridor_storage["main"],
                {
                    "sim_corridor_id": corridor_storage["corridor_id"],
                    "corridor_index": corridor_index,
                    "storage_out_time": self.model(observation)["corridors_by_id"][corridor_storage["corridor_id"]]["storage_out_time"],
                },
            ))

        actions.extend(self.create_main_robot_wait_actions(observation))
        return actions

    # Erzeugt Place-Aktionen für den transportierten Job und eine Wartealternative.
    # Beispiel: Ein geladener Job erhält mögliche Zielstores und zusätzlich wait_main_robot.
    def create_main_robot_place_actions(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        job = current_state["current_job_summary"]
        layout_id = current_state["layout_id"]
        model = self.model(observation)
        actions = []

        if job["general_state"] == "defect":
            # Sammelt für einen defekten Job die Defektmaschine und mögliche alternative Nacharbeitsmaschinen.
            defect_machine_id = (
                job.get("defect_machine_id")
                or current_state.get("current_job_defect_machine_id")
            )
            # Historische ID der Operation, in der der Defekt entstanden wurde.
            defect_operation_id = (
                job.get("defect_operation_id")
                or current_state.get("current_job_defect_operation_id")
            )
            # Liest die zuvor festgelegte Nacharbeitsstrategie und die ausgewählten IDs.
            recovery_strategy = job.get("defect_recovery_strategy")
            # ID der als Nächstes ausgewählten Operation; sie kann bei Nacharbeit der Defektoperation entsprechen.
            selected_operation_id = job.get("selected_operation_id")
            selected_machine_id = job.get("selected_machine_id")



            # Definiert die beiden erlaubten Arten der Nacharbeit.
            recovery_strategies = {
                "nacharbeiten_auf_defektmaschine",
                "nacharbeiten_auf_alternativer_maschine",
            }

            repair_targets = []


            # Beide IDs bedeuten: Die Policy hat bereits die Nacharbeitsroute ausgewählt.
            if selected_operation_id and selected_machine_id:
                
                # Prüft, ob die gespeicherte Strategie eine erlaubte Nacharbeitsstrategie ist.
                if recovery_strategy not in recovery_strategies:
                    recovery_strategy = (
                        "nacharbeiten_auf_defektmaschine"
                        if selected_machine_id == defect_machine_id
                        else "nacharbeiten_auf_alternativer_maschine"
                    )
                # Verwendet die bereits durch die Policy festgelegte Nacharbeitsoperation und -maschine.
                repair_targets.append((
                    selected_operation_id,
                    selected_machine_id,
                    recovery_strategy,
                ))
            # Ohne ausgewählte Route werden Defektoperation und Defektmaschine als Ausgangspunkt verwendet.
            elif defect_machine_id and defect_operation_id:
                # Ohne vorherige Festlegung werden die Defektmaschine und Alternativen als Kandidaten erzeugt.
                repair_targets.append((
                    defect_operation_id,
                    defect_machine_id,
                    "nacharbeiten_auf_defektmaschine",
                ))
                target_product_type_id = job.get("target_product_type_name")
                for route in self.find_alternative_nacharbeit_routes(
                    defect_operation_id,
                    defect_machine_id,
                    target_product_type_id,
                    layout_id,
                    model,
                ):
                    repair_targets.append((
                        route["next_operation_id"],
                        route["next_machine_id"],
                        "nacharbeiten_auf_alternativer_maschine",
                    ))

            added_targets = set()
            for operation_id, machine_id, strategy in repair_targets:
                target_key = (operation_id, machine_id)
                if target_key in added_targets:
                    continue
                added_targets.add(target_key)

                target_machine = model["machines_by_id"].get(machine_id)
                if target_machine is None:
                    continue
                corridor_ids = model["layouts_by_id"][layout_id]["corridor_ids"]
                if target_machine["corridor_id"] not in corridor_ids:
                    continue
                corridor_index = corridor_ids.index(target_machine["corridor_id"])
                corridor_storage = current_state["corridor_storages"][corridor_index]
                target_store = (
                    corridor_storage["left"]
                    if target_machine["left"]
                    else corridor_storage["right"]
                )
                if self.store_has_free_capacity(target_store):
                    actions.append({
                        "action_type": "place_main_robot",
                        "payload": {
                            "target_type": "sim_corridor_store_arm_input",
                            "selected_operation_id": operation_id,
                            "selected_machine_id": machine_id,
                            "defect_recovery_strategy": strategy,
                            "sim_corridor_id": corridor_storage["corridor_id"],
                            "target_store_id": target_store["store_id"],
                            "storage_in_time": model["corridors_by_id"][target_machine["corridor_id"]]["storage_in_time"],
                        },
                    })
            actions.extend(self.create_main_robot_wait_actions(observation))
            return actions

        if job["general_state"] == "ausschuss" or job["downgraded"] or job["bearbeitungs_state"] == job["target_product_type_name"]:
            target_store = current_state["end_storage"]
            payload = {
                "target_type": "end_storage",
                "target_store_id": target_store["store_id"],
                "storage_in_time": current_state["storage_in_time"],
            }
            if self.store_has_free_capacity(target_store):
                actions.append({
                    "action_type": "place_main_robot",
                    "payload": payload,
                })
            actions.extend(self.create_main_robot_wait_actions(observation))
            return actions

        # Für einen normalen Job (intakt, nicht herabgestuft, kein Ausschuss und noch nicht fertig)
        # werden hier alle technisch möglichen nächsten Operations- und Maschinenrouten durchlaufen.
        for route_option in self.selectable_routes_for_job(job, layout_id, model):
            next_operation_id = route_option["next_operation_id"]
            next_machine_id = route_option["next_machine_id"]
            next_machine = model["machines_by_id"][next_machine_id]

            corridor_ids = model["layouts_by_id"][layout_id]["corridor_ids"]

            corridor_index = corridor_ids.index(next_machine["corridor_id"])

            corridor_storage = current_state["corridor_storages"][corridor_index]

            target_store = corridor_storage["left"] if next_machine["left"] else corridor_storage["right"]

            if self.store_has_free_capacity(target_store):
                actions.append({
                    "action_type": "place_main_robot",
                    "payload": {
                        "target_type": "sim_corridor_store_arm_input",
                        "selected_operation_id": next_operation_id,
                        "selected_machine_id": next_machine_id,
                        "sim_corridor_id": corridor_storage["corridor_id"],
                        "target_store_id": target_store["store_id"],
                        "storage_in_time": model["corridors_by_id"][next_machine["corridor_id"]]["storage_in_time"],
                    },
                })

        actions.extend(self.create_main_robot_wait_actions(observation))
        return actions

    # Erzeugt die Warteaktion für den Main-Roboter.
    # Beispiel: Das Ergebnis ist {"action_type": "wait_main_robot", "payload": {}}.
    def create_main_robot_wait_actions(self, observation: PolicyObservation) -> list[dict]:
        return [
            {
                "action_type": "wait_main_robot",
                "payload": {},
            }
        ]


    # Erzeugt Pick-Aktionen für Korridorstores und Maschinenausgangspuffer sowie eine Warteaktion.
    # Beispiel: Jobs in diesen Puffern werden zu pick_corridor_arm_robot-Aktionen.
    def create_corridor_arm_robot_pick_actions(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        actions = []

        actions.extend(self.create_pick_actions_for_store(
            "pick_corridor_arm_robot",
            "sim_corridor_store_arm_input",
            current_state["sim_corridor_store_arm_input"],
            {
                "storage_out_time": current_state["storage_out_time"],
            },
        ))

        for machine_index, machine_storage in enumerate(current_state["machine_storages"]):
            actions.extend(self.create_pick_actions_for_store(
                "pick_corridor_arm_robot",
                "machine_output_storage",
                machine_storage["output"],
                {
                    "sim_machine_id": machine_storage["sim_machine_id"],
                    "machine_index": machine_index,
                },
            ))

        actions.extend(self.create_corridor_arm_robot_wait_actions(observation))
        return actions

    # Erzeugt Place-Aktionen für den transportierten Job und eine Warteaktion des Korridorarms.
    # Beispiel: Ein geladener Korridorarm platziert in einen Maschinen- oder Korridorstore.
    def create_corridor_arm_robot_place_actions(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        job = current_state["current_job_summary"]
        corridor_id = current_state["corridor_id"]
        model = self.model(observation)
        actions = []

        if (
            job["general_state"] == "ausschuss"
            or job["downgraded"]
            or job["bearbeitungs_state"] == job["target_product_type_name"]
        ):
            target_store = current_state["sim_corridor_store_main"]
            if self.store_has_free_capacity(target_store):
                actions.append({
                    "action_type": "place_corridor_arm_robot",
                    "payload": {
                        "target_type": "sim_corridor_store_main",
                        "target_store_id": target_store["store_id"],
                        "storage_in_time": current_state["storage_in_time"],
                    },
                })
            actions.extend(self.create_corridor_arm_robot_wait_actions(observation))
            return actions

        if job["general_state"] != "ausschuss" and not job["downgraded"] and job["bearbeitungs_state"] != job["target_product_type_name"]:
            layout_id = model["corridors_by_id"][corridor_id]["layout_id"]

            # Liest die von der Policy bereits gespeicherte nächste Operation und Maschine.
            selected_operation_id = job.get("selected_operation_id")
            selected_machine_id = job.get("selected_machine_id")
            # Wenn beide IDs vorhanden sind, wird nur diese vorab ausgewählte Route verwendet.
            if selected_operation_id is not None and selected_machine_id is not None:
                route_options = [{
                    "next_operation_id": selected_operation_id,
                    "next_machine_id": selected_machine_id,
                }]
            else:
                # Ohne Policy-Auswahl werden keine Defekt-IDs als Ersatzroute verwendet.
                route_options = self.selectable_routes_for_job(job, layout_id, model)

            for route_option in route_options:
                next_operation_id = route_option["next_operation_id"]
                next_machine_id = route_option["next_machine_id"]
                next_machine = model["machines_by_id"][next_machine_id]

                # Zielmaschine liegt im aktuellen Korridor; direkt ihren Eingangspuffer verwenden.
                if next_machine_id in current_state["machine_names"]:
                    machine_index = current_state["machine_names"].index(next_machine_id)
                    machine_storage = current_state["machine_storages"][machine_index]
                    target_store = machine_storage["input"]
                    payload = {
                        "target_type": "machine_input_storage",
                        "selected_operation_id": next_operation_id,
                        "selected_machine_id": next_machine_id,
                        "sim_machine_id": machine_storage["sim_machine_id"],
                        "target_store_id": target_store["store_id"],
                    }
                # Zielmaschine liegt im selben Korridor, wird aber vom anderen Korridorarm bedient.
                elif next_machine["corridor_id"] == corridor_id:
                    target_store = current_state["sim_corridor_store_other_arm_input"]
                    payload = {
                        "target_type": "sim_corridor_store_other_arm_input",
                        "selected_operation_id": next_operation_id,
                        "selected_machine_id": next_machine_id,
                        "target_store_id": target_store["store_id"],
                        "storage_in_time": current_state["storage_in_time"],
                    }
                # Zielmaschine liegt in einem anderen Korridor; zuerst in den Main-Store dieses Korridors legen.
                else:
                    target_store = current_state["sim_corridor_store_main"]
                    payload = {
                        "target_type": "sim_corridor_store_main",
                        "selected_operation_id": next_operation_id,
                        "selected_machine_id": next_machine_id,
                        "target_store_id": target_store["store_id"],
                        "storage_in_time": current_state["storage_in_time"],
                    }

                if self.store_has_free_capacity(target_store):
                    actions.append({
                        "action_type": "place_corridor_arm_robot",
                        "payload": payload,
                    })
        # Ausschuss-, herabgestufte oder bereits fertige Jobs benötigen keine weitere Maschine.
        # Der Korridorarm legt sie deshalb in den Main-Store für den Weitertransport.
        else:
            target_store = current_state["sim_corridor_store_main"]
            if self.store_has_free_capacity(target_store):
                actions.append({
                    "action_type": "place_corridor_arm_robot",
                    "payload": {
                        "target_type": "sim_corridor_store_main",
                        "target_store_id": target_store["store_id"],
                        "storage_in_time": current_state["storage_in_time"],
                    },
                })

        actions.extend(self.create_corridor_arm_robot_wait_actions(observation))
        return actions

    # Erzeugt die Warteaktion für den Korridorarmroboter.
    # Beispiel: Das Ergebnis ist {"action_type": "wait_corridor_arm_robot", "payload": {}}.
    def create_corridor_arm_robot_wait_actions(self, observation: PolicyObservation) -> list[dict]:
        return [
            {
                "action_type": "wait_corridor_arm_robot",
                "payload": {},
            }
        ]


    # Erzeugt Pick-Aktionen für Jobs im Maschineneingangspuffer und eine Warteaktion.
    # Beispiel: Jobs im Eingangspuffer werden zu pick_machine_job-Aktionen.
    def create_machine_pick_actions(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        actions = []
        input_storage = current_state["input_storage"]
        for job in self.store_jobs(input_storage):
            actions.append({
                "action_type": "pick_machine_job",
                "payload": {
                    "target_store_id": input_storage["store_id"],
                    "selected_job_id": self.job_id(job),
                },
            })
        actions.extend(self.create_machine_wait_actions(observation))
        return actions

    # Erzeugt eine Bearbeitungsaktion oder bei vollem Ausgangspuffer eine Warteaktion.
    # Beispiel: Freier Ausgangspuffer ergibt process_machine_job, voller Puffer ergibt wait_machine.
    def create_machine_process_actions(self, observation: PolicyObservation) -> list[dict]:
        current_state = self.current_state(observation)
        operation_id = current_state["next_operation_id"]
        planned_machine_id = current_state["next_machine_id"]
        tool_type_id = current_state["required_tool_type_id"]
        consumed_life_units = current_state["consumed_life_units"]
        remaining_life_units_before_operation = current_state[
            "remaining_life_units_before_operation"
        ]

        if current_state["needs_tool_change"]:
            if current_state["mounted_tool_type_id"] is None:
                tool_setup_action = "unmount_dummy_tool_and_mount_tool"
            else:
                tool_setup_action = "unmount_and_mount_tool"
        elif not current_state["has_enough_tool_life"]:
            tool_setup_action = "replace_tool_same_type"
        else:
            tool_setup_action = "keep_tool"

        actions = []
        if self.store_has_free_capacity(current_state["output_storage"]):
            actions.append({
                "action_type": "process_machine_job",
                "payload": {
                    "operation_id": operation_id,
                    "planned_machine_id": planned_machine_id,
                    "tool_type_id": tool_type_id,
                    "total_life_units": current_state["required_tool_total_life_units"],
                    "consumed_life_units": consumed_life_units,
                    "remaining_life_units_before_operation": remaining_life_units_before_operation,
                    "tool_setup_action": tool_setup_action,
                    "target_store_id": current_state["output_storage"]["store_id"],
                },
            })
        else:
            actions.extend(self.create_machine_wait_actions(observation))
        return actions

    # Erzeugt die Warteaktion für die Maschine.
    # Beispiel: Das Ergebnis ist {"action_type": "wait_machine", "payload": {}}.
    def create_machine_wait_actions(self, observation: PolicyObservation) -> list[dict]:
        return [
            {
                "action_type": "wait_machine",
                "payload": {},
            }
        ]


    # Berechnet alle technisch möglichen Maschinenfolgen für eine Operationsfolge.
    # Beispiel: Die Operation [op1] kann beispielsweise die Maschinenfolge [m1] liefern.
    def calculate_machine_sequences_from_operation_sequence(
        self,
        operation_sequence: list[str],
        layout_id: str,
        model: dict,
    ) -> list[list[str]]:
        if len(operation_sequence) == 0:
            return [[]]

        result: list[list[str]] = []
        operation_id = operation_sequence[0]
        remaining_operation_sequence = operation_sequence[1:]
        operation = model["operations_by_id"][operation_id]

        for machine_id, machine in model["machines_by_id"].items():
            if machine["machine_type_id"] != operation["machine_type_id"]:
                continue

            if machine["layout_id"] != layout_id:
                continue

            machine_tool_type_ids = machine.get("tool_type_ids")
            if machine_tool_type_ids is not None:
                required_tool_type_id = operation["tool_type_id"]
                if required_tool_type_id not in machine_tool_type_ids:
                    continue

            maschinenrouten = (
                self.calculate_machine_sequences_from_operation_sequence(
                    remaining_operation_sequence,
                    layout_id,
                    model,
                )
            )
            for maschinenroute in maschinenrouten:
                maschinenroute.insert(0, machine_id)
                result.append(maschinenroute)

        return result

    # Berechnet alle Maschinenfolgen für Operationsfolgen eines Produkttyps in einem Layout.
    # Beispiel: product_type_id="p2" liefert alle passenden Operations- und Maschinenfolgen.
    def calculate_machine_sequences(self, product_type_id: str, layout_id: str, model: dict) -> list[list[str]]:
        result: list[list[str]] = []
        operation_sequences = self.calculate_operation_sequences(product_type_id, model)
        for operation_sequence in operation_sequences:
            maschinenrouten = self.calculate_machine_sequences_from_operation_sequence(operation_sequence, layout_id, model)
            for maschinenroute in maschinenrouten:
                exists = False
                for andere_maschinenroute in result:
                    if all(x == y for x, y in zip(maschinenroute, andere_maschinenroute)):
                        exists = True
                        break
                if not exists:
                    result.append(maschinenroute)
        return result

    # Ermittelt rekursiv alle Operationsfolgen vom Startprodukttyp zum Zielprodukttyp.
    # Beispiel: Von p1 nach p3 kann das Ergebnis [[op1, op2]] sein.
    def calculate_operation_sequences_between(
        self,
        start_product_type_id: str,
        target_product_type_id: str,
        model: dict,
    ) -> list[list[str]]:
        if start_product_type_id == target_product_type_id:
            return [[]]

        result: list[list[str]] = []
        for operation_id, operation in model["operations_by_id"].items():
            if operation["consumes_product_type_id"] != start_product_type_id:
                continue
            remaining_operation_sequences_until_target = self.calculate_operation_sequences_between(
                operation["produces_product_type_id"],
                target_product_type_id,
                model,
            )

            for remaining_operation_sequence_until_target in remaining_operation_sequences_until_target:
                result.append([operation_id] + remaining_operation_sequence_until_target)
        return result

    # Ermittelt rekursiv alle Operationsfolgen, die den Produkttyp herstellen.
    # Beispiel: Für p3 kann das Ergebnis [[op1, op2]] sein.
    def calculate_operation_sequences(
        self,
        product_type_id: str,
        model: dict,
        visited_product_types: set[str] | None = None,
    ) -> list[list[str]]:
        visited = (
            set()
            if visited_product_types is None
            else set(visited_product_types)
        )
        if product_type_id in visited:
            return []
        visited.add(product_type_id)

        result: list[list[str]] = []
        for operation_id, operation in model["operations_by_id"].items():
            if operation["produces_product_type_id"] != product_type_id:
                continue
            vorherige_operationsfolgen = self.calculate_operation_sequences(
                operation["consumes_product_type_id"],
                model,
                visited,
            )

            if not vorherige_operationsfolgen:
                result.append([operation_id])
            else:
                for vorherige_operationsfolge in vorherige_operationsfolgen:
                    result.append(vorherige_operationsfolge + [operation_id])
        return result
