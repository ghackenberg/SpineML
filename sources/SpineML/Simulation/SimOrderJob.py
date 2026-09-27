from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import salabim as sim
from ..Configuration import Layout, Scenario, Order, Machine, OperationType
from ..Control import SimulationBridge

if TYPE_CHECKING:
    from ..controller.simulation_bridge import SimulationBridge
    from .SimOrder import SimOrder


class SimOrderJob(sim.Component):
    DEFECT_STRATEGY_ACTION_TYPES = {
        "job_nacharbeiten_auf_defektmaschine",
        "job_nacharbeiten_auf_alternativer_maschine",
        "produkt_herabstufen",
        "job_ausschuss",
    }

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, layout: Layout, scenario: Scenario, order: Order, number: int, store_start: sim.Store, bridge: SimulationBridge, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.layout = layout
        self.scenario = scenario
        self.order = order
        self.number = number
        self.store_start = store_start
        self.bridge = bridge

        self.bridge.register(
            f"{self.order.name}:{self.number}",
            self,
        )


        self.released = False  
        self.queue_priority = 0.0  
        self.completed_time = None  
        self.process_finished = False  
        self.location = "start_storage"
        self.selected_operation: OperationType | None = None  
        self.selected_machine: Machine | None = None  
        self.bearbeitungs_state = sim.State("Bearbeitungszustand", value="unconfigured", env=self.env)  
        self.general_state = sim.State("General state", value="intakt", env=self.env)  
        self.due_state = sim.State("Due", value=None, env=self.env)  

        self.downgraded = False  
        self.downgrade_product_type = None  

        self.defect_detected_time = None  
        self.defect_operation: OperationType | None = None  
        self.defect_machine: Machine | None = None  
        self.defect_product_state_before = None  
        self.defect_product_state_target = None  
        self.defekt_schwergrad = None  
        self.defect_recovery_strategy = None  
        # Bleibt während des Recovery-Transports und der Recovery-Bearbeitung aktiv.
        self.recovery_in_progress = False
        self.defect_count = 0
        self.nacharbeit_count = 0
        self.ausschuss_count = 0

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self):
       
        while True:
            yield self.bridge.request_action(self)
            action = yield self.bridge.action(self)

            if "selected_operation" in action.payload:
                self.selected_operation = action.payload["selected_operation"]

            if "selected_machine" in action.payload:
                self.selected_machine = action.payload["selected_machine"]

            if "bearbeitungs_state" in action.payload:
                self.bearbeitungs_state.set(action.payload["bearbeitungs_state"])

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

            if "defekt_schwergrad" in action.payload:
                self.defekt_schwergrad = action.payload["defekt_schwergrad"]

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
                    "job_nacharbeiten_auf_defektmaschine",
                    "job_nacharbeiten_auf_alternativer_maschine",
                }:
                    self.nacharbeit_count += 1
                    # Nacharbeitsstrategie ist gewählt; die Recovery ist noch nicht abgeschlossen.
                    self.recovery_in_progress = True
                elif action.action_type == "job_ausschuss":
                    self.ausschuss_count += 1
                yield self.bridge.notify_state_change(self)
                yield self.hold(1.0)
                continue

            if action.payload.get("finish_process", False):
                self.process_finished = True
                break

    # Setzt oder aktualisiert den angegebenen Zustand.
    def mark_finished(self):
        self.completed_time = self.env.now()

    # Setzt oder aktualisiert den angegebenen Zustand.
    def mark_defective(
        self,
        operation: OperationType | None = None,
        machine: Machine | None = None,
        product_state_before: str | None = None,
        product_state_target: str | None = None,
        defekt_schwergrad: float | None = None,
    ):
        self.defect_count += 1
        self.general_state.set("defect")
        self.defect_detected_time = self.env.now()
        self.defect_operation = operation
        self.defect_machine = machine
        self.defect_product_state_before = product_state_before
        self.defect_product_state_target = product_state_target
        self.defekt_schwergrad = defekt_schwergrad
        self.defect_recovery_strategy = None

    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        return None
