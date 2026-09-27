from __future__ import annotations

import salabim as sim

from ..Configuration import Corridor, Machine
from ..Control import SimulationBridge

from .SimRobot import SimRobot
from .SimMachine import SimMachine
from .SimOrderJob import SimOrderJob
from .SimRobot import SimRobot


class SimRobotCorridorArm(SimRobot):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, corridor: Corridor, machines: list[Machine], direction: str, store_in: sim.Store, store_out_arm: sim.Store, store_out_main: sim.Store, sim_machines: list[SimMachine], bridge: SimulationBridge, dx: float, y: float, *args, **kwargs):
        super().__init__(f"Arm {direction} robot", 2, dx, y, 2.5, "green", *args, **kwargs)
        self.configured_movement_speed = 1.5

        self.corridor = corridor
        self.machines = machines
        self.bridge = bridge

        self.direction = direction

        self.store_in = store_in
        self.store_out_arm = store_out_arm
        self.store_out_main = store_out_main
        
        
        self.dx = dx
        self.sim_machines = sim_machines
        self.current_job: SimOrderJob | None = None

        self.bridge.register(
            f"CorridorArmRobot:{self.corridor.name}:{self.direction}",
            self,
        )

    # Berechnet die feste X-Position der Maschine im Corridor.
    def compute_machine_x(self, machine_num: int) -> float:
        return (3 + machine_num * 2) * self.dx

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_to_corridor_storage_x(self, speed: float):
        if self.x != self.dx:
            yield from self.move_x(self.dx, speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_to_machine_storage(self, machine_num: int, speed: float):
        x = self.compute_machine_x(machine_num)
        if self.x != x:
            yield from self.move_x(x, speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_down_to_corridor_storage(self, speed: float):
        yield from self.move_z(1.25, speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_down_to_machine_storage(self, speed: float):
        yield from self.move_z(1.5, speed)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_up_from_storage(self, speed: float):
        yield from self.move_z(2.5, speed)

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self):
        while True:
            yield self.bridge.request_action(self)
            action = yield self.bridge.action(self)

            if action.action_type == "pick_corridor_arm_robot":
                yield from self.execute_pick_action(action)
            elif action.action_type == "place_corridor_arm_robot":
                yield from self.execute_place_action(action)
            elif action.action_type == "wait_corridor_arm_robot":
                yield self.hold(1.0)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def execute_pick_action(self, action):
        target_type = action.payload["target_type"]
        target_store = action.payload["target_store"]
        movement_speed = self.configured_movement_speed
        if target_type == "sim_corridor_store_arm_input":
            yield from self.move_to_corridor_storage_x(movement_speed)
            job: SimOrderJob | None = yield from self.take_selected_job_from_store(action, target_store)
            if job is None:
                return
            job.location = f"{self.label}:loaded"
            job.queue_priority = action.payload["queue_priority"]
            storage_out_time = action.payload.get("storage_out_time", 0)
            if storage_out_time > 0:
                yield self.hold(storage_out_time)
            yield from self.move_down_to_corridor_storage(movement_speed)
            self.current_job = job
            self.state_load.set("loaded")
            yield from self.move_up_from_storage(movement_speed)
            return

        if target_type == "machine_output_storage":
            sim_machine = action.payload["sim_machine"]
            machine_num = self.sim_machines.index(sim_machine)
            yield from self.move_to_machine_storage(machine_num, movement_speed)
            job: SimOrderJob | None = yield from self.take_selected_job_from_store(action, target_store)
            if job is None:
                return
            job.queue_priority = action.payload["queue_priority"]
            yield from self.move_down_to_machine_storage(movement_speed)
            self.current_job = job
            self.state_load.set("loaded")
            sim_machine.state.set("waiting")
            yield from self.move_up_from_storage(movement_speed)
            return

        return

    # Führt die angeforderte Bewegung oder Aktion aus.
    def execute_place_action(self, action):
        if self.current_job is None:
            return

        job = self.current_job
        target_type = action.payload["target_type"]
        target_store = action.payload["target_store"]
        movement_speed = self.configured_movement_speed

        if target_type == "machine_input_storage":
            sim_machine = action.payload["sim_machine"]
            machine_num = self.sim_machines.index(sim_machine)
            if "selected_operation" in action.payload:
                job.selected_operation = action.payload["selected_operation"]
            if "selected_machine" in action.payload:
                job.selected_machine = action.payload["selected_machine"]
            yield from self.move_to_machine_storage(machine_num, movement_speed)
            yield from self.move_down_to_machine_storage(movement_speed)
            yield self.to_store(target_store, job, priority=job.queue_priority)
            job.location = target_store.name()
            yield self.bridge.notify_state_change(self)
            self.current_job = None
            self.state_load.set("empty")
            yield from self.move_up_from_storage(movement_speed)
            return

        if target_type in ["sim_corridor_store_other_arm_input", "sim_corridor_store_main"]:
            if "selected_operation" in action.payload:
                job.selected_operation = action.payload["selected_operation"]
            if "selected_machine" in action.payload:
                job.selected_machine = action.payload["selected_machine"]
            if target_type == "sim_corridor_store_main":
                if self.x != 0.0:
                    yield from self.move_x(0.0, movement_speed)
            else:
                yield from self.move_to_corridor_storage_x(movement_speed)
            yield from self.move_down_to_corridor_storage(movement_speed)
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
