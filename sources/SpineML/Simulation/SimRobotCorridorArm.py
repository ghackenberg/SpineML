from __future__ import annotations

import salabim as sim

from ..Configuration import Corridor, Machine
from ..controller import ArmRobotCommand, JobKey
from .SimMachine import SimMachine
from .SimOrderJob import SimOrderJob
from .SimRobot import SimRobot


class SimRobotCorridorArm(SimRobot):
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
        poll_interval: float = 0.1,
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
        self.poll_interval = poll_interval

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

    def move_down_corridor_storage(self):
        yield from self.move_z(1.25, self.speed)

    def move_down_machine_storage(self):
        yield from self.move_z(1.5, self.speed)

    def move_up(self):
        yield from self.move_z(2.5, self.speed)

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
                elif cmd.pick.kind == "machine_out":
                    source_machine = self._sim_machine_by_num(cmd.pick.machine_num)
                    yield from self.move_to_machine_output_storage(cmd.pick.machine_num)
                    yield from self.move_down_machine_storage()
                    source_store = source_machine.store_out
                else:
                    raise ValueError(f"Unsupported arm robot pick action: {cmd.pick.kind}")

                job: SimOrderJob = yield self.from_store(source_store)
                if not self._job_matches(job, cmd.job_key):
                    raise ValueError(
                        f"Arm robot picked unexpected job {job.order.name}/{job.number}; expected {cmd.job_key}"
                    )

                self.state_load.set("loaded")
                if source_machine is not None:
                    source_machine.state.set("waiting")
                yield from self.move_up()

                if cmd.place.kind == "machine_in":
                    target_machine = self._sim_machine_by_num(cmd.place.machine_num)
                    yield from self.move_to_machine_input_storage(cmd.place.machine_num)
                    yield from self.move_down_machine_storage()
                    target_store = target_machine.store_in
                elif cmd.place.kind == "arm_out":
                    yield from self.move_to_corridor_storage()
                    yield from self.move_down_corridor_storage()
                    target_store = self.store_out_arm
                elif cmd.place.kind == "main_out":
                    yield from self.move_to_corridor_storage()
                    yield from self.move_down_corridor_storage()
                    target_store = self.store_out_main
                else:
                    raise ValueError(f"Unsupported arm robot place action: {cmd.place.kind}")

                yield self.to_store(target_store, job)
                self.state_load.set("empty")
                yield from self.move_up()
            finally:
                self.cmd_active = False
