from __future__ import annotations

import salabim as sim

from ..Configuration import Corridor, Machine
from ..controller import ArmRobotCommand, JobKey
from .SimMachine import SimMachine
from .SimOrderJob import SimOrderJob
from .SimRobot import SimRobot


class SimRobotCorridorArm(SimRobot):
    WEIGHT_SPEED_FACTOR = 0.05
    MIN_LOADED_SPEED = 0.1

    def __init__(
        self,
        corridor: Corridor,
        machines: list[Machine],
        direction: str,
        store_in: sim.Store,
        store_out_arm: sim.Store,
        store_out_main: sim.Store,
        sim_machines: list[SimMachine],
        dx: float,
        y: float,
        controller=None,
        speed: float = 1.0,
        *args,
        **kwargs,
    ):
        super().__init__(f"Arm {direction} robot", 2, dx, y, 2.5, "green", *args, **kwargs)

        self.corridor = corridor
        self.machines = machines
        self.direction = direction

        self.store_in = store_in
        self.store_out_arm = store_out_arm
        self.store_out_main = store_out_main

        self.dx = dx
        self.sim_machines = sim_machines
        self.controller = controller

        self.speed = speed

        self.cmd_store = sim.Store(f"{self.label} cmd", env=self.env)
        self.cmd_active = False

    def _machine_x(self, machine_num: int) -> float:
        return (3 + machine_num * 2) * self.dx

    def _sim_machine_by_num(self, machine_num: int) -> SimMachine:
        try:
            return self.sim_machines[machine_num]
        except IndexError as exc:
            raise ValueError(f"Unknown machine slot {machine_num} for arm robot") from exc

    def _job_matches(self, job: SimOrderJob, job_key: JobKey) -> bool:
        return (
            job.scenario.name == job_key.scenario_name
            and job.order.name == job_key.order_name
            and job.number == job_key.job_number
        )

    def _loaded_speed(self, job: SimOrderJob) -> float:
        return max(
            self.MIN_LOADED_SPEED,
            self.speed / (1 + job.current_product_type.weight * self.WEIGHT_SPEED_FACTOR),
        )

    def move_down_corridor_storage(self):
        yield from self.move_z(1.25, self.speed)

    def move_down_machine_storage(self):
        yield from self.move_z(1.5, self.speed)

    def move_up(self):
        yield from self.move_z(2.5, self.speed)

    def move_down_corridor_storage_loaded(self, loaded_speed: float):
        yield from self.move_z(1.25, loaded_speed)

    def move_down_machine_storage_loaded(self, loaded_speed: float):
        yield from self.move_z(1.5, loaded_speed)

    def move_up_loaded(self, loaded_speed: float):
        yield from self.move_z(2.5, loaded_speed)

    def move_to_machine_input_storage(self, machine_num: int):
        x = self._machine_x(machine_num)
        if self.x != x:
            yield from self.move_x(x, self.speed)

    def move_to_machine_output_storage(self, machine_num: int):
        x = self._machine_x(machine_num)
        if self.x != x:
            yield from self.move_x(x, self.speed)

    def move_to_corridor_storage(self):
        if self.x != self.dx:
            yield from self.move_x(self.dx, self.speed)

    def process(self):
        if self.controller is None:
            raise RuntimeError("SimRobotCorridorArm requires a controller for dispatched commands")

        while True:
            cmd_component = yield self.from_store(self.cmd_store)
            cmd = cmd_component.payload
            if not isinstance(cmd, ArmRobotCommand):
                raise ValueError(f"Unsupported corridor arm command payload: {type(cmd).__name__}")

            self.cmd_active = True
            try:
                if cmd.pick.kind == "store_in":
                    yield from self.move_to_corridor_storage()
                    yield from self.move_down_corridor_storage()
                    source_store = self.store_in
                    source_machine = None
                    source_out_time = self.corridor.storage_out_time
                elif cmd.pick.kind == "machine_out":
                    source_machine = self._sim_machine_by_num(cmd.pick.machine_num)
                    yield from self.move_to_machine_output_storage(cmd.pick.machine_num)
                    yield from self.move_down_machine_storage()
                    source_store = source_machine.store_out
                    source_out_time = source_machine.machine.storage_out_time
                else:
                    raise ValueError(f"Unsupported arm robot pick action: {cmd.pick.kind}")

                job: SimOrderJob = yield self.from_store(source_store)
                if not self._job_matches(job, cmd.job_key):
                    raise ValueError(
                        f"Arm robot picked unexpected job {job.order.name}/{job.number}; expected {cmd.job_key}"
                    )

                if source_out_time > 0:
                    yield self.hold(source_out_time)
                loaded_speed = self._loaded_speed(job)
                job.apply_route(
                    list(cmd.place.route.operation_sequence),
                    list(cmd.place.route.machine_sequence),
                )

                self.state_load.set("loaded")
                if source_machine is not None:
                    source_machine.state.set("waiting")
                yield from self.move_up_loaded(loaded_speed)

                if cmd.place.kind == "machine_in":
                    target_machine = self._sim_machine_by_num(cmd.place.machine_num)
                    target_x = self._machine_x(cmd.place.machine_num)
                    if self.x != target_x:
                        yield from self.move_x(target_x, loaded_speed)
                    yield from self.move_down_machine_storage_loaded(loaded_speed)
                    target_store = target_machine.store_in
                    target_in_time = target_machine.machine.storage_in_time
                elif cmd.place.kind == "arm_out":
                    if self.x != self.dx:
                        yield from self.move_x(self.dx, loaded_speed)
                    yield from self.move_down_corridor_storage_loaded(loaded_speed)
                    target_store = self.store_out_arm
                    target_in_time = self.corridor.storage_in_time
                elif cmd.place.kind == "main_out":
                    if self.x != self.dx:
                        yield from self.move_x(self.dx, loaded_speed)
                    yield from self.move_down_corridor_storage_loaded(loaded_speed)
                    target_store = self.store_out_main
                    target_in_time = self.corridor.storage_in_time
                else:
                    raise ValueError(f"Unsupported arm robot place action: {cmd.place.kind}")

                yield self.to_store(target_store, job)
                if target_in_time > 0:
                    yield self.hold(target_in_time)
                self.state_load.set("empty")
                yield from self.move_up()
            finally:
                self.cmd_active = False
