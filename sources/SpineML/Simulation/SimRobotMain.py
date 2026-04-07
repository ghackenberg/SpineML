from __future__ import annotations

import salabim as sim

from ..Configuration import Layout, Scenario
from ..controller import JobKey, MainRobotCommand
from .SimCorridor import SimCorridor
from .SimOrderJob import SimOrderJob
from .SimRobot import SimRobot


class SimRobotMain(SimRobot):
    WEIGHT_SPEED_FACTOR = 0.05
    MIN_LOADED_SPEED = 0.1

    def __init__(
        self,
        layout: Layout,
        scenario: Scenario,
        store_start: sim.Store,
        store_end: sim.Store,
        sim_corridors: list[SimCorridor],
        y: float,
        z: float,
        controller=None,
        speed: float = 1.0,
        *args,
        **kwargs,
    ):
        super().__init__("Main robot", 0, 0, y, z, "red", *args, **kwargs)

        self.layout = layout
        self.scenario = scenario
        self.store_start = store_start
        self.store_end = store_end
        self.sim_corridors = sim_corridors
        self.controller = controller

        self.speed = speed
        self.corridor_count = len(self.layout.corridors)
        self.y_stock = 2 + self.corridor_count / 1.15

        self.cmd_store = sim.Store(f"{self.label} cmd", env=self.env)
        self.cmd_active = False

    def _corridor_y(self, sim_corridor: SimCorridor) -> float:
        corridor_num = self.sim_corridors.index(sim_corridor)
        return (corridor_num + 0.5 - self.corridor_count / 2) * 2

    def _sim_corridor_by_name(self, corridor_name: str) -> SimCorridor:
        for sim_corridor in self.sim_corridors:
            if sim_corridor.corridor.name == corridor_name:
                return sim_corridor
        raise ValueError(f"Unknown corridor for main robot command: {corridor_name}")

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

    def move_to_layout_start_storage(self):
        if self.y != -self.y_stock:
            yield from self.move_y(-self.y_stock, self.speed)

    def move_to_layout_end_storage(self):
        if self.y != self.y_stock:
            yield from self.move_y(self.y_stock, self.speed)

    def move_to_corridor_storage(self, sim_corridor: SimCorridor):
        y_corridor = self._corridor_y(sim_corridor)
        if self.y != y_corridor:
            yield from self.move_y(y_corridor, self.speed)

    def move_down(self):
        yield from self.move_z(1.25, self.speed)

    def move_up(self):
        yield from self.move_z(2.5, self.speed)

    def move_down_loaded(self, loaded_speed: float):
        yield from self.move_z(1.25, loaded_speed)

    def move_up_loaded(self, loaded_speed: float):
        yield from self.move_z(2.5, loaded_speed)

    def process(self):
        if self.controller is None:
            raise RuntimeError("SimRobotMain requires a controller for dispatched commands")

        while True:
            cmd_component = yield self.from_store(self.cmd_store)
            cmd = cmd_component.payload
            if not isinstance(cmd, MainRobotCommand):
                raise ValueError(f"Unsupported main robot command payload: {type(cmd).__name__}")

            self.cmd_active = True
            try:
                if cmd.pick.kind == "start":
                    yield from self.move_to_layout_start_storage()
                    source_store = self.store_start
                    source_out_time = self.layout.storage_out_time
                elif cmd.pick.kind == "corridor_main":
                    source_corridor = self._sim_corridor_by_name(cmd.pick.corridor_name)
                    yield from self.move_to_corridor_storage(source_corridor)
                    source_store = source_corridor.store_main
                    source_out_time = source_corridor.corridor.storage_out_time
                else:
                    raise ValueError(f"Unsupported main robot pick action: {cmd.pick.kind}")

                yield from self.move_down()
                job: SimOrderJob = yield self.from_store(source_store)
                if not self._job_matches(job, cmd.job_key):
                    raise ValueError(
                        f"Main robot picked unexpected job {job.order.name}/{job.number}; expected {cmd.job_key}"
                    )

                if source_out_time > 0:
                    yield self.hold(source_out_time)
                loaded_speed = self._loaded_speed(job)
                job.apply_route(
                    list(cmd.place.route.operation_sequence),
                    list(cmd.place.route.machine_sequence),
                )

                self.state_load.set("loaded")
                yield from self.move_up_loaded(loaded_speed)

                if cmd.place.kind == "end":
                    if self.y != self.y_stock:
                        yield from self.move_y(self.y_stock, loaded_speed)
                    target_store = self.store_end
                    target_in_time = self.layout.storage_in_time
                elif cmd.place.kind == "corridor_in":
                    target_corridor = self._sim_corridor_by_name(cmd.place.corridor_name)
                    if cmd.place.side == "left":
                        target_store = target_corridor.store_left
                    elif cmd.place.side == "right":
                        target_store = target_corridor.store_right
                    else:
                        raise ValueError(f"Missing side for main robot corridor placement: {cmd.place}")
                    target_y = self._corridor_y(target_corridor)
                    if self.y != target_y:
                        yield from self.move_y(target_y, loaded_speed)
                    target_in_time = target_corridor.corridor.storage_in_time
                else:
                    raise ValueError(f"Unsupported main robot place action: {cmd.place.kind}")

                yield from self.move_down_loaded(loaded_speed)
                yield self.to_store(target_store, job)
                if target_in_time > 0:
                    yield self.hold(target_in_time)
                if target_store is self.store_end:
                    if job.sim_order is None:
                        job.mark_completed()
                    else:
                        job.sim_order.mark_job_completed(job)
                self.state_load.set("empty")
                yield from self.move_up()
            finally:
                self.cmd_active = False
