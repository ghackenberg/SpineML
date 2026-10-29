from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import salabim as sim
from ..Configuration import Layout, Scenario, Order, Machine, OperationType
from ..SimulationInterface import SimulationBridge

if TYPE_CHECKING:
    from .SimOrder import SimOrder


class SimOrderJob(sim.Component):
    DEFECT_STRATEGY_ACTION_TYPES = {
        "job_rework_on_defect_machine",
        "job_rework_on_alternative_machine",
        "downgrade_product",
        "job_scrap",
    }

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, layout: Layout, scenario: Scenario, order: Order, number: int, store_start: sim.Store, bridge: SimulationBridge, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fabriklayout, in dem dieser Job simuliert wird.
        self.layout = layout
        # Szenario, zu dem der Auftrag und der Job gehören.
        self.scenario = scenario
        # Auftrag, aus dem dieser einzelne Job erzeugt wurde.
        self.order = order
        # Laufende Nummer des Jobs innerhalb des Auftrags.
        self.number = number
        # Startlager, in dem der Job zu Beginn abgelegt wird.
        self.store_start = store_start
        # Bridge für den Austausch von Zuständen und Aktionen mit der Steuerung.
        self.bridge = bridge

        self.bridge.register(
            f"{self.order.name}:{self.number}",
            self,
        )


        # Gibt an, ob der Job für die Produktion freigegeben wurde.
        self.released = False
        # Priorität des Jobs in den Simulationswarteschlangen.
        self.queue_priority = 0.0
        # Zeitpunkt, an dem der Job vollständig abgeschlossen wurde.
        self.completed_time = None

        # Gibt an, ob der Prozess dieses Jobs beendet werden darf.
        self.process_finished = False
        # Aktueller Aufenthaltsort des Jobs.
        self.location = "start_storage"

        # Von der Steuerung ausgewählte nächste Operation.
        self.selected_operation: OperationType | None = None
        # Von der Steuerung ausgewählte Maschine für die nächste Operation.
        self.selected_machine: Machine | None = None

        # Aktueller Produktzustand bzw. Name des Produkttyps; anfangs "unconfigured".
        self.processing_state = sim.State("ProcessingState", value="unconfigured", env=self.env)
       
        # Allgemeiner Qualitätszustand des Jobs: intact, defect oder scrap.
        self.general_state = sim.State("General state", value="intact", env=self.env)
        
        # Aktueller Terminstatus des Jobs, zum Beispiel on-time oder late; anfangs None.
        self.due_state = sim.State("Due", value=None, env=self.env)

        # Gibt an, ob der Job herabgestuft wurde.
        self.downgraded = False

        # Ziel-Produkttyp trotz Herabstufung, zum Beispiel weiterhin poliert; anfangs None.
        self.downgrade_product_type = None

        # Zeitpunkt, an dem der letzte Defekt erkannt wurde.
        self.defect_detected_time = None
        # Operation, die den letzten Defekt verursacht hat.
        self.defect_operation: OperationType | None = None
        # Maschine, auf der der letzte Defekt entstanden ist.
        self.defect_machine: Machine | None = None

        
        # Produktzustand vor der fehlerhaften Operation.
        self.defect_product_state_before = None
        # Produktzustand, den die fehlerhafte Operation erzeugen sollte.
        self.defect_product_state_target = None
        # Schweregrad des letzten Defekts.
        self.defect_severity = None
        
        # Ausgewählte Strategie für die Behandlung eines Defekts.
        self.defect_recovery_strategy = None
        # Bleibt während des Recovery-Transports und der Recovery-Nacharbeit aktiv.
        self.recovery_in_progress = False
        # Anzahl der bei diesem Job erkannten Defekte.
        self.defect_count = 0
        # Anzahl der für diesen Job gestarteten Nacharbeiten.
        self.rework_count = 0
        # Anzahl der Ausschussentscheidungen; im normalen Ablauf höchstens einmal.
        self.scrap_count = 0

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self):
       
        while True:
            yield self.bridge.request_action(self)
            action = yield self.bridge.action(self)

            if "selected_operation" in action.payload:
                self.selected_operation = action.payload["selected_operation"]

            if "selected_machine" in action.payload:
                self.selected_machine = action.payload["selected_machine"]

            if "processing_state" in action.payload:
                self.processing_state.set(action.payload["processing_state"])

            if "general_state" in action.payload:
                self.general_state.set(action.payload["general_state"])

            if "due_state" in action.payload:
                self.due_state.set(action.payload["due_state"])

            if "released" in action.payload:
                self.released = action.payload["released"]

            if "downgraded" in action.payload:
                self.downgraded = action.payload["downgraded"]

            if "downgrade_product_type" in action.payload:
                self.downgrade_product_type = action.payload["downgrade_product_type"]

            if "queue_priority" in action.payload:
                self.queue_priority = action.payload["queue_priority"]

            if "completed_time" in action.payload:
                self.completed_time = action.payload["completed_time"]

            if "defect_detected_time" in action.payload:
                self.defect_detected_time = action.payload["defect_detected_time"]

            if "defect_operation" in action.payload:
                self.defect_operation = action.payload["defect_operation"]

            if "defect_machine" in action.payload:
                self.defect_machine = action.payload["defect_machine"]

            if "defect_product_state_before" in action.payload:
                self.defect_product_state_before = action.payload["defect_product_state_before"]

            if "defect_product_state_target" in action.payload:
                self.defect_product_state_target = action.payload["defect_product_state_target"]

            if "defect_severity" in action.payload:
                self.defect_severity = action.payload["defect_severity"]

            if "defect_recovery_strategy" in action.payload:
                self.defect_recovery_strategy = action.payload["defect_recovery_strategy"]

            if "release_time" in action.payload:
                release_time = action.payload["release_time"]
                if release_time > self.env.now():
                    yield self.hold(release_time - self.env.now())

            target_store = action.payload.get("target_store")
            if target_store is not None:
                yield self.to_store(target_store, self, priority=self.queue_priority)
                self.location = target_store.name()
                yield self.bridge.notify_state_change(self)

            if action.action_type == "release_job":
                yield self.bridge.notify_state_change(self)
              
                yield self.hold(1.0)
                continue

            if action.action_type == "wait_job":
                yield self.hold(1.0)
                continue

            if action.action_type in self.DEFECT_STRATEGY_ACTION_TYPES:
                if action.action_type in {
                    "job_rework_on_defect_machine",
                    "job_rework_on_alternative_machine",
                }:
                    self.rework_count += 1
                    # The rework strategy is selected; recovery is not complete yet.
                    self.recovery_in_progress = True
                elif action.action_type == "job_scrap":
                    self.scrap_count += 1
                yield self.bridge.notify_state_change(self)
                yield self.hold(1.0)
                continue

            if action.payload.get("finish_process", False):
                self.process_finished = True
                break

    # Wird von SimRobotMain beim Einlagern im Endlager aufgerufen 
    # und speichert die Abschlusszeit des Jobs.
    def mark_finished(self):
        self.completed_time = self.env.now()

    # Speichert einen von SimMachine festgestellten Defekt 
    # und seine zugehörigen Daten im Job.
    def mark_defective(
        self,
        operation: OperationType | None = None,
        machine: Machine | None = None,
        product_state_before: str | None = None,
        product_state_target: str | None = None,
        defect_severity: float | None = None,
    ):
        self.defect_count += 1
        self.general_state.set("defect")
        self.defect_detected_time = self.env.now()
        self.defect_operation = operation
        self.defect_machine = machine
        self.defect_product_state_before = product_state_before
        self.defect_product_state_target = product_state_target
        self.defect_severity = defect_severity
        self.defect_recovery_strategy = None

    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        return None
