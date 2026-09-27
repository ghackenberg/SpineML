from __future__ import annotations

import salabim as sim

from ..Configuration import Layout, Scenario
from ..Control import SimulationBridge

from .SimCorridor import SimCorridor
from .SimOrderJob import SimOrderJob
from .SimRobot import SimRobot


class SimRobotMain(SimRobot):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, layout: Layout, scenario: Scenario, store_start: sim.Store, store_end: sim.Store, sim_corridors: list[SimCorridor], bridge: SimulationBridge, y: float, z: float, *args, **kwargs):
        super().__init__("Main robot", 0, 0, y, z, "red", *args, **kwargs)
        self.configured_movement_speed = 2.0

        self.layout = layout
        self.scenario = scenario
        self.bridge = bridge

        self.store_start = store_start
        self.store_end = store_end
        self.sim_corridors = sim_corridors
        self.current_job: SimOrderJob | None = None

        self.bridge.register(
            self.label,
            self,
            stores=[self.store_start, self.store_end],
        )

    # Berechnet den angeforderten Wert.
    def calculate_storage_y_position(self) -> float:
        corridor_count = len(self.layout.corridors)
        return 2 + corridor_count / 1.15

    # Berechnet den angeforderten Wert.
    def calculate_corridor_y_position(self, corridor_index: int) -> float:
        corridor_count = len(self.layout.corridors)
        return (corridor_index + 0.5 - corridor_count / 2) * 2

    # ValueError.
    def configured_corridor_index(self, corridor) -> int:
        corridor_name = getattr(corridor, "name", None)
        for index, configured_corridor in enumerate(self.layout.corridors):
            if configured_corridor is corridor:
                return index
            if corridor_name is not None and configured_corridor.name == corridor_name:
                return index
        raise ValueError(
            f"Corridor {corridor_name!r} gehört nicht zum Layout "
            f"{self.layout.name!r}."
        )

    # Führt die Funktion mit den übergebenen Werten aus.
    def simulation_corridor_index(self, sim_corridor) -> int:
        """Resolve a runtime corridor by object or configured corridor name."""
        corridor_name = getattr(
            getattr(sim_corridor, "corridor", None),
            "name",
            getattr(sim_corridor, "name", None),
        )
        for index, configured_sim_corridor in enumerate(self.sim_corridors):
            if configured_sim_corridor is sim_corridor:
                return index
            configured_name = getattr(
                getattr(configured_sim_corridor, "corridor", None),
                "name",
                None,
            )
            if corridor_name is not None and configured_name == corridor_name:
                return index
        raise ValueError(
            f"Simulations-Corridor {corridor_name!r} gehört nicht zum Layout."
        )

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_to_start_storage(self, speed: float):
        yield from self.move_y(-self.calculate_storage_y_position(), speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_to_corridor_storage(self, sim_corridor: SimCorridor, corridor_index: int, speed: float):
        y = self.calculate_corridor_y_position(corridor_index)
        if y != self.y:
            yield from self.move_y(y, speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_to_end_storage(self, speed: float):
        yield from self.move_y(self.calculate_storage_y_position(), speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_down_to_storage(self, speed: float):
        yield from self.move_z(1.25, speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_up_from_storage(self, speed: float = 1.0):
        yield from self.move_z(2.5, speed)

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self) :
        while True:
            yield self.bridge.request_action(self)
            action = yield self.bridge.action(self)

            if action.action_type == "pick_main_robot":
                yield from self.execute_pick_action(action)
            elif action.action_type == "place_main_robot":
                yield from self.execute_place_action(action)
            elif action.action_type == "wait_main_robot":
                yield self.hold(1.0)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def execute_pick_action(self, action):
        target_type = action.payload["target_type"]
        target_store = action.payload["target_store"]
        movement_speed = self.configured_movement_speed

        if target_type == "start_storage":
            yield from self.move_to_start_storage(movement_speed)
        elif target_type == "sim_corridor_store_main":
            sim_corridor = action.payload["sim_corridor"]
            corridor_index = self.simulation_corridor_index(sim_corridor)
            yield from self.move_to_corridor_storage(sim_corridor, corridor_index, movement_speed)
        else:
            return

        job: SimOrderJob | None = yield from self.take_selected_job_from_store(action, target_store)
        if job is None:
            return
        job.location = f"{self.label}:loaded"
        job.queue_priority = action.payload["queue_priority"]
        storage_out_time = action.payload.get("storage_out_time", 0)
        if storage_out_time > 0:
            yield self.hold(storage_out_time)

        yield from self.move_down_to_storage(movement_speed)
        self.current_job = job
        self.state_load.set("loaded")
        yield from self.move_up_from_storage(movement_speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def execute_place_action(self, action):
        if self.current_job is None:
            return

        job = self.current_job
        target_type = action.payload["target_type"]
        target_store = action.payload["target_store"]
        movement_speed = self.configured_movement_speed
        if target_type == "sim_corridor_store_arm_input":
            sim_corridor = action.payload["sim_corridor"]
            corridor_index = self.simulation_corridor_index(sim_corridor)
            if "selected_operation" in action.payload:
                job.selected_operation = action.payload["selected_operation"]
            if "selected_machine" in action.payload:
                job.selected_machine = action.payload["selected_machine"]
            if "defect_recovery_strategy" in action.payload:
                # Speichert die gewählte Nacharbeitsstrategie; der Job markiert die laufende Recovery selbst.
                recovery_strategy = action.payload["defect_recovery_strategy"]
                if (
                    recovery_strategy in {
                        "nacharbeiten_auf_defektmaschine",
                        "nacharbeiten_auf_alternativer_maschine",
                    }
                    and job.defect_recovery_strategy not in {
                        "nacharbeiten_auf_defektmaschine",
                        "nacharbeiten_auf_alternativer_maschine",
                    }
                ):
                    job.nacharbeit_count += 1
                job.defect_recovery_strategy = recovery_strategy
                if recovery_strategy in {
                    "nacharbeiten_auf_defektmaschine",
                    "nacharbeiten_auf_alternativer_maschine",
                }:
                    job.recovery_in_progress = True
            yield from self.move_to_corridor_storage(sim_corridor, corridor_index, movement_speed)
            yield from self.move_down_to_storage(movement_speed)
            storage_in_time = action.payload.get("storage_in_time", 0)
            if storage_in_time > 0:
                yield self.hold(storage_in_time)
            yield self.to_store(target_store, job, priority=job.queue_priority)
            job.location = target_store.name()
            yield self.bridge.notify_state_change(self)
            self.current_job = None
            self.state_load.set("empty")
            yield from self.move_up_from_storage(movement_speed)
            return

        if target_type == "end_storage":
            yield from self.move_to_end_storage(movement_speed)
            yield from self.move_down_to_storage(movement_speed)
            job.selected_operation = None
            job.selected_machine = None
            job.mark_finished()
            storage_in_time = action.payload.get("storage_in_time", 0)
            if storage_in_time > 0:
                yield self.hold(storage_in_time)
            yield self.to_store(target_store, job, priority=job.queue_priority)
            job.location = target_store.name()
            yield self.bridge.notify_state_change(self)
            self.current_job = None
            self.state_load.set("empty")
            yield from self.move_up_from_storage(movement_speed)
            return

        return
