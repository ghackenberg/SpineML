from __future__ import annotations

import salabim as sim

from ...Configuration import (
    CORRIDORS,
    LAYOUTS,
    MACHINES,
    OPERATION_TYPES,
    PRODUCT_TYPES,
    TOOL_TYPES,
)
from ..GeneralControl.GeneratorSelectorPolicy import GeneratorSelectorPolicy
from ..Interface.InterfaceTypes import (
    ConfigurationObjectObserver,
    Policy,
    PolicyObservation,
    PolicyTrigger,
    SimulationAction,
    SimulationObjectObserver,
    policy_payload_id_mappings,
)


class SimulationBridge(sim.Component):

    # Initialisiert die Bridge, die Policy, die Trigger-Warteschlange und alle Zuordnungen.
    def __init__(self, policy: Policy | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if policy is None:
            self.policy = GeneratorSelectorPolicy()
        else:
            self.policy = policy

        # Zentrale Warteschlange für Trigger, die der Policy neue Zustandsänderungen melden.
        self.policy_trigger_store = sim.Store(
            "simulation bridge triggers for policy",
            env=self.env,
        )
 
        # Ordnet jeder Simulationskomponente ihren persönlichen Aktions-Store zu.
        self.sim_action_stores: dict[sim.Component, sim.Store] = {}

        # Ordnet eine für die Policy sichtbare ID der echten Simulationskomponente zu.
        self.policy_object_id_to_simulation_object: dict[
            str,
            sim.Component,
        ] = {}

        # Gegenrichtung: Ordnet eine Simulationskomponente ihrer Policy-ID zu.
        self.simulation_object_to_policy_object_id: dict[
            sim.Component,
            str,
        ] = {}

        # Ordnet eine für die Policy sichtbare Store-ID dem echten Salabim-Store zu.
        self.policy_store_id_to_simulation_store: dict[str, sim.Store] = {}

        # Konfigurationsobjekte, die über ihre IDs aufgelöst werden können.
        self.operations_by_id: dict[str, object] = {}
        self.machines_by_id: dict[str, object] = {}
        self.product_types_by_id: dict[str, object] = {}
        self.tool_types_by_id: dict[str, object] = {}

        # Simulationskomponenten, die auf eine Aktion der Policy warten.
        self.sim_objects_waiting_for_action: set[sim.Component] = set()

        # Zuletzt erstellter Snapshot für die Policy.
        self.current_simulation_snapshot: dict[str, object] = {}

        # ID-basiertes Konfigurationsmodell der Fabrik; anfangs noch nicht erstellt.
        self.policy_model: dict[str, object] | None = None
        
        # Laufende Nummer für erzeugte Policy-Trigger.
        self._policy_trigger_event_number = 0
        # Laufende Nummer für erzeugte Simulationsaktionen.
        self._action_event_number = 0
        # Versionsnummer des aktuellen Simulationszustands.
        self._simulation_state_version = 0


    # Registriert ein Simulationsobjekt, seine Policy-ID und seinen persönlichen Aktions-Store.
    def register(
        self,
        policy_object_id: str,
        simulation_object: sim.Component,
        stores: list[sim.Store] | None = None,
    ):
        registration_is_allowed = self.can_register_policy_object(
            policy_object_id,
            simulation_object,
        )
        if registration_is_allowed is False:
            return
        self.policy_object_id_to_simulation_object[
            policy_object_id
        ] = simulation_object

        self.simulation_object_to_policy_object_id[
            simulation_object
        ] = policy_object_id

        self.sim_action_stores[simulation_object] = sim.Store(
            f"{simulation_object.name()} simulation actions",
            env=self.env,
        )

        for store in stores or []:
            self.register_store(store)

    # Registriert einen Korridor und seine Stores nur für die ID-Auflösung.
    def register_corridor(
        self,
        policy_object_id: str,
        simulation_corridor: sim.Component,
        stores: list[sim.Store] | None = None,
    ):
        """Registriert einen Korridor ohne eigenen Aktions-Store."""
        registration_is_allowed = self.can_register_policy_object(
            policy_object_id,
            simulation_corridor,
        )
        if registration_is_allowed is False:
            return
        self.policy_object_id_to_simulation_object[
            policy_object_id
        ] = simulation_corridor
        for store in stores or []:
            self.register_store(store)

    # Ordnet den Namen eines Salabim-Stores seiner sichtbaren Store-ID zu.
    def register_store(self, store: sim.Store):
        policy_store_id = store.name()
        registered_store = self.policy_store_id_to_simulation_store.get(
            policy_store_id
        )
        if registered_store is not None:
            return
        self.policy_store_id_to_simulation_store[policy_store_id] = store

    # Prüft, ob weder die Policy-ID noch das Simulationsobjekt bereits registriert sind.
    def can_register_policy_object(
        self,
        policy_object_id: str,
        simulation_object: sim.Component,
    ) -> bool:
        policy_object_id_is_registered = (
            policy_object_id in self.policy_object_id_to_simulation_object
        )
        simulation_object_is_registered = (
            simulation_object in self.simulation_object_to_policy_object_id
        )

        if policy_object_id_is_registered:
            return False
        elif simulation_object_is_registered:
            return False
        else:
            return True


    # Markiert ein Objekt als auf eine Aktion wartend und erzeugt einen Policy-Trigger.
    def request_action(self, sender: sim.Component):
        self.sim_objects_waiting_for_action.add(sender)
        return self.notify_state_change(sender)

    # Legt einen Trigger im zentralen Store ab,
    # damit die Policy den aktuellen Snapshot bewertet.
    def notify_state_change(self, sender: sim.Component):
        self._simulation_state_version += 1
        policy_trigger = PolicyTrigger(
            self.next_policy_trigger_event_id(),
            self.simulation_object_to_policy_object_id.get(sender, sender.name()),
            self._simulation_state_version,
            sender.env.now(),
            env=self.env,
        )
        return sender.to_store(
            self.policy_trigger_store,
            policy_trigger,
        )


    # Erstellt das ID-basierte Konfigurationsmodell der Fabrik für die Policy.
    def build_policy_configuration_model(self) -> dict[str, object]:
        """Erstellt eine ID-basierte Beschreibung der konfigurierten Fabrik."""
        self.product_types_by_id = {obj.name: obj for obj in PRODUCT_TYPES}
        self.operations_by_id = {obj.name: obj for obj in OPERATION_TYPES}
        self.machines_by_id = {obj.name: obj for obj in MACHINES}
        #"tool_1": <ToolType-Objekt>,
        #"tool_1": sichtbare ID
        #<ToolType-Objekt>: echtes internes Python-Objekt
        self.tool_types_by_id = {obj.name: obj for obj in TOOL_TYPES}
        return ConfigurationObjectObserver.build_policy_configuration_model(
            PRODUCT_TYPES,
            OPERATION_TYPES,
            MACHINES,
            TOOL_TYPES,
            CORRIDORS,
            LAYOUTS,
        )

    # Sammelt die Zustände aller registrierten Simulationsobjekte und fügt
    # das ID-basierte Konfigurationsmodell in den Policy-Snapshot ein.
    def build_policy_simulation_snapshot(self) -> dict[str, object]:
        if self.policy_model is None:
            self.policy_model = self.build_policy_configuration_model()

        snapshot = {
            "time": self.env.now(),
            "state_version": self._simulation_state_version,
            "simulation_object_states_by_id": {},
            "configuration_model": self.policy_model,
        }

        for sim_object in self.sim_action_stores:
            observation = SimulationObjectObserver.observe_simulation_object(
                sim_object,
                self.env.now(),
            )
            object_id = str(observation["object_id"])
            observation["is_waiting_for_action"] = (
                sim_object in self.sim_objects_waiting_for_action
            )
            snapshot["simulation_object_states_by_id"][object_id] = observation

        self.current_simulation_snapshot = snapshot
        return snapshot

    # Erstellt aus dem aktuellen Snapshot und den auslösenden Triggern eine Beobachtung.
    def create_policy_observation(
        self,
        policy_triggers: list[PolicyTrigger] | None = None,
    ) -> PolicyObservation:
        snapshot = self.build_policy_simulation_snapshot()
        if policy_triggers is not None:
            # Sammelt die IDs aller Trigger, die diese Observation ausgelöst haben.
            # policy_trigger_17 
            snapshot["policy_trigger_event_ids"] = [
                trigger.event_id for trigger in policy_triggers
            ]
            # Sammelt die IDs der Simulationsobjekte, die diese Trigger gesendet haben.
            # Main robot
            snapshot["policy_trigger_sender_ids"] = [
                trigger.sender_id for trigger in policy_triggers
            ]
        return PolicyObservation(
            simulation_configuration_snapshot=snapshot,
        )


    # Wandelt die ID-basierte Policy-Entscheidung in ausführbare SimulationActions um.
    def create_simulation_actions(
        self,
        decision,
        source_policy_trigger_id: str,
    ) -> list[SimulationAction]:
        """Löst IDs im Payload auf und erstellt ausführbare Simulationsaktionen."""
        simulation_actions = []
        
        # Erstellt die Zuordnung, mit der Policy-IDs in echte
        # Simulationsobjekte für den Aktions-Payload umgewandelt werden.
        payload_id_mappings = policy_payload_id_mappings(self)

        # Durchläuft alle von der Policy ausgewählten Aktionen.
        for action in decision.actions:
            payload = dict(action.payload)

            # Durchläuft alle bekannten ID-zu-Objekt-Zuordnungen.
            for policy_id_key, mapping in payload_id_mappings.items():
                # Enthält der Payload diese ID nicht, wird nur das nächste Mapping geprüft.
                if policy_id_key not in payload:
                    continue

                # Liest den neuen Feldnamen aus, unter dem das echte Objekt
                # gespeichert wird, zum Beispiel "selected_job".
                simulation_object_key = mapping[0]
                # Liest das Register mit der Zuordnung ID -> echtes Objekt.
                simulation_object_registry = mapping[1]
                # Entnimmt die ID, zum Beispiel "job_1", aus dem Policy-Payload.
                policy_id_value = payload.pop(policy_id_key)

                # Schreibt None oder das anhand der ID gefundene echte Objekt in den Payload.
                if policy_id_value is None:
                    payload[simulation_object_key] = None
                else:
                    payload[simulation_object_key] = (
                        simulation_object_registry[policy_id_value]
                    )

            simulation_action = SimulationAction(
                self.next_action_event_id(),
                self.simulation_object_for_policy_object_id(action.target_id),
                source_policy_trigger_id,
                action.action_type,
                self.env.now(),
                payload,
                env=self.env,
            )

            # Speichert die erzeugte Aktion, damit sie später an ihr Zielobjekt verteilt wird.
            simulation_actions.append(simulation_action)

            #simulation_actions = [ SimulationAction für den Main-Roboter,SimulationAction für eine Maschine,]

        return simulation_actions


    # Das Zielobjekt entnimmt seine nächste von der Policy ausgewählte Aktion
    # aus seinem persönlichen Aktions-Store.
    def action(self, target: sim.Component):
        return target.from_store(self.sim_action_stores[target])


    # Löst eine sichtbare Policy-ID in das zugehörige Simulationsobjekt auf.
    def simulation_object_for_policy_object_id(
        self,
        policy_object_id: str,
    ) -> sim.Component:
        return self.policy_object_id_to_simulation_object[policy_object_id]

    # Erzeugt die nächste fortlaufende ID für eine SimulationAction.
    def next_action_event_id(self) -> str:
        self._action_event_number += 1
        return f"action_{self._action_event_number}"

    # Erzeugt die nächste fortlaufende ID für einen PolicyTrigger.
    def next_policy_trigger_event_id(self) -> str:
        self._policy_trigger_event_number += 1
        return f"policy_trigger_{self._policy_trigger_event_number}"


    # Verarbeitet Trigger, erstellt Beobachtungen, ruft die Policy auf und verteilt Aktionen.
    def process(self):

        # Wartet dauerhaft auf neue Zustands- (notify_state) oder Aktionsanforderungs-Trigger.
        while True:
            # Entnimmt den ersten wartenden Trigger aus dem zentralen Trigger-Store.
            first_policy_trigger = yield self.from_store(self.policy_trigger_store)

            # Gibt anderen gleichzeitigen Salabim-Ereignissen eine Ausführungsmöglichkeit.
            yield self.hold(0)

            # Beginnt die Trigger-Gruppe mit dem zuerst entnommenen Trigger.
            policy_triggers = [first_policy_trigger]

            # Die Zustandsänderungen werden gemeinsam in einen Snapshot aufgenommen.
            #Die Policy entscheidet einmal für diesen gemeinsamen Zustand.
            while self.policy_trigger_store.as_list():

                next_policy_trigger = self.policy_trigger_store.as_list()[0]

                # Beendet die Gruppe, sobald der nächste Trigger eine andere Zeit hat.
                if next_policy_trigger.time != first_policy_trigger.time:
                    break

                # Entnimmt den gleichzeitigen Trigger aus dem zentralen Store.
                collected_trigger = yield self.from_store(
                    self.policy_trigger_store
                )
                # Fügt den entnommenen Trigger zur aktuellen Gruppe hinzu.
                policy_triggers.append(collected_trigger)

            # Wiederholt Observation und Entscheidung, falls sich der Zustand inzwischen änderte.
            while True:
                # Erstellt einen Snapshot für alle gesammelten Trigger.
                policy_snapshot = self.create_policy_observation(policy_triggers)
                
                # Übergibt die Beobachtung an die Policy und erhält eine
                # Entscheidung mit den ausgewählten Aktionen zurück.
                selected_action_policy = self.policy.make_decision(policy_snapshot)
                # Liest die Zustandsversion, die im verwendeten Snapshot gespeichert ist.
                snapshot_state_version = (
                    policy_snapshot.simulation_configuration_snapshot[
                        "state_version"
                    ]
                )
                # Akzeptiert die Entscheidung nur, wenn der Snapshot noch aktuell ist.
                if snapshot_state_version == self._simulation_state_version:
                    break

            # Ignoriert eine Entscheidung ohne Aktionen und wartet auf den nächsten Trigger.
            if len(selected_action_policy.actions) == 0:
                continue

            # Wandelt die Policy-Auswahl in ausführbare SimulationActions um.
            simulation_actions = self.create_simulation_actions(
                selected_action_policy,
                first_policy_trigger.event_id,
            )
            # Verteilt jede ausführbare Aktion an den persönlichen Store ihres Zielobjekts.
            for simulation_action in simulation_actions:
                # Entfernt das Ziel aus der Liste der Objekte, die noch auf eine Aktion warten.
                self.sim_objects_waiting_for_action.remove(simulation_action.target)
                # Legt die Aktion im Aktions-Store des Zielobjekts ab.
                yield self.to_store(
                    self.sim_action_stores[simulation_action.target],
                    simulation_action,
                )
