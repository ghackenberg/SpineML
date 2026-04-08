from __future__ import annotations

from typing import TYPE_CHECKING

import salabim as sim

from .policy import DispatchPolicy, RoutingPolicy
from .types import (
    ArmMachineObservation,
    ArmRobotObservation,
    CorridorObservation,
    DispatchCommand,
    JobHeadObservation,
    JobKey,
    JobPlanningRequest,
    JobPlan,
    MachineObservation,
    MainRobotObservation,
    OrderJobObservation,
    QueueObject,
    SystemObservation,
    ToolSpec,
)

if TYPE_CHECKING:
    from ..Simulation.SimMachine import SimMachine
    from ..Simulation.SimOrderJob import SimOrderJob
    from ..Simulation.SimRobotCorridorArm import SimRobotCorridorArm
    from ..Simulation.SimRobotMain import SimRobotMain


class ControllerCommand(sim.Component):
    def __init__(self, payload: object, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.payload = payload


class SimulationBridge(sim.Component):
    def __init__(
        self,
        routing_policy: RoutingPolicy,
        dispatch_policy: DispatchPolicy,
        machines: list[SimMachine] | None = None,
        order_jobs: list[SimOrderJob] | None = None,
        main_robots: list[SimRobotMain] | None = None,
        arm_robots: list[SimRobotCorridorArm] | None = None,
        interval: float = 0.001,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.routing_policy = routing_policy
        self.dispatch_policy = dispatch_policy
        self.machines = machines or []
        self.order_jobs = order_jobs or []
        self.main_robots = main_robots or []
        self.arm_robots = arm_robots or []
        self.interval = interval
        self._cmd_stores: dict[str, sim.Store] = {}
        self._rebuild_dispatch_map()

    def attach(
        self,
        machines: list[SimMachine] | None = None,
        order_jobs: list[SimOrderJob] | None = None,
        main_robots: list[SimRobotMain] | None = None,
        arm_robots: list[SimRobotCorridorArm] | None = None,
    ) -> None:
        self.machines = machines or self.machines
        self.order_jobs = order_jobs or self.order_jobs
        self.main_robots = main_robots or self.main_robots
        self.arm_robots = arm_robots or self.arm_robots
        self._rebuild_dispatch_map()

    def _actor_id(self, component: sim.Component) -> str:
        return f"{component.__class__.__name__}:{id(component)}"

    def _rebuild_dispatch_map(self) -> None:
        self._cmd_stores = {}
        for component in [*self.main_robots, *self.arm_robots, *self.machines]:
            cmd_store = getattr(component, "cmd_store", None)
            if cmd_store is None:
                continue
            self._cmd_stores[self._actor_id(component)] = cmd_store

    def _job_key(self, job: SimOrderJob) -> JobKey:
        return JobKey(
            scenario_name=job.scenario.name,
            order_name=job.order.name,
            job_number=job.number,
        )

    def _remaining_processing_time_estimate_from_sequences(
        self,
        operation_sequence: list,
        machine_sequence: list,
    ) -> float:
        estimate = 0.0
        for index, operation in enumerate(operation_sequence):
            estimate += operation.duration
            if index < len(machine_sequence):
                estimate += machine_sequence[index].dimension_processing_time(
                    operation.consumes_product_type
                )
        return estimate

    def _job_slack_time(self, job: SimOrderJob) -> float:
        return (
            job.order.latest_end_time
            - self.env.now()
            - self._remaining_processing_time_estimate_from_sequences(
                job.operation_sequence,
                job.machine_sequence,
            )
        )

    def _job_head_observation(self, job: SimOrderJob) -> JobHeadObservation:
        operation_sequence = job.operation_sequence
        machine_sequence = job.machine_sequence
        next_operation = operation_sequence[0] if len(operation_sequence) > 0 else None
        next_machine = machine_sequence[0] if len(machine_sequence) > 0 else None
        next_side = None
        if next_machine is not None:
            next_side = "left" if next_machine.left else "right"

        return JobHeadObservation(
            job_key=self._job_key(job),
            routing_request=JobPlanningRequest(
                job_key=self._job_key(job),
                layout=job.layout,
                order=job.order,
                current_product_type=job.current_product_type,
            ),
            current_product_name=job.state.get(),
            current_product_weight=job.current_product_type.weight,
            current_product_length=job.current_product_type.length,
            current_product_width=job.current_product_type.width,
            current_product_depth=job.current_product_type.depth,
            is_defective=job.is_defective,
            release_time=job.order.earliest_start_time,
            due_time=job.order.latest_end_time,
            queue_wait_time=max(0.0, self.env.now() - job.current_queue_entry_time),
            remaining_operations=len(operation_sequence),
            remaining_machines=len(machine_sequence),
            remaining_processing_time_estimate=self._remaining_processing_time_estimate_from_sequences(
                operation_sequence,
                machine_sequence,
            ),
            slack_time=self._job_slack_time(job),
            committed_operation_sequence=tuple(operation_sequence),
            committed_machine_sequence=tuple(machine_sequence),
            next_operation_name=next_operation.name if next_operation is not None else None,
            next_tool_name=next_operation.tool_type.name if next_operation is not None else None,
            next_operation_duration=(
                next_operation.duration + next_machine.dimension_processing_time(next_operation.consumes_product_type)
                if next_operation is not None and next_machine is not None
                else (next_operation.duration if next_operation is not None else None)
            ),
            next_consumed_life_units=next_operation.consumes_life_units if next_operation is not None else None,
            next_produced_product_name=(
                next_operation.produces_product_type.name if next_operation is not None else None
            ),
            next_machine_name=next_machine.name if next_machine is not None else None,
            next_machine_corridor_name=(next_machine.corridor.name if next_machine is not None else None),
            next_machine_side=next_side,
        )

    def _queue_object(self, queue_id: str, queue_kind: str, store: sim.Store) -> QueueObject:
        jobs = tuple(self._job_head_observation(job) for job in store)
        head = jobs[0] if len(jobs) > 0 else None
        return QueueObject(
            queue_id=queue_id,
            queue_kind=queue_kind,
            length=store.length(),
            capacity=float(store.capacity()),
            free_capacity=float(store.available_quantity()),
            head=head,
            jobs=jobs,
        )

    def order_job_status(self, job: SimOrderJob) -> OrderJobObservation:
        next_operation = job.operation_sequence[0] if len(job.operation_sequence) > 0 else None
        next_machine = job.machine_sequence[0] if len(job.machine_sequence) > 0 else None
        return OrderJobObservation(
            job_key=self._job_key(job),
            current_product_name=job.state.get(),
            current_product_weight=job.current_product_type.weight,
            current_product_length=job.current_product_type.length,
            current_product_width=job.current_product_type.width,
            current_product_depth=job.current_product_type.depth,
            is_defective=job.is_defective,
            released=self.env.now() >= job.order.earliest_start_time,
            completed=job.completion_time is not None,
            completion_time=job.completion_time,
            defect_time=job.defect_time,
            release_time=job.order.earliest_start_time,
            due_time=job.order.latest_end_time,
            remaining_operations=len(job.operation_sequence),
            remaining_machines=len(job.machine_sequence),
            remaining_processing_time_estimate=self._remaining_processing_time_estimate_from_sequences(
                job.operation_sequence,
                job.machine_sequence,
            ),
            slack_time=self._job_slack_time(job),
            next_operation_name=next_operation.name if next_operation is not None else None,
            next_machine_name=next_machine.name if next_machine is not None else None,
        )

    def main_robot_status(self, robot: SimRobotMain) -> MainRobotObservation:
        corridors = []
        for sim_corridor in robot.sim_corridors:
            corridor_name = sim_corridor.corridor.name
            corridor_y = robot._corridor_y(sim_corridor)
            corridors.append(
                CorridorObservation(
                    corridor_name=corridor_name,
                    y=corridor_y,
                    main_queue=self._queue_object(
                        f"corridor:{corridor_name}:main",
                        "corridor_main",
                        sim_corridor.store_main,
                    ),
                    left_queue=self._queue_object(
                        f"corridor:{corridor_name}:left",
                        "corridor_left",
                        sim_corridor.store_left,
                    ),
                    right_queue=self._queue_object(
                        f"corridor:{corridor_name}:right",
                        "corridor_right",
                        sim_corridor.store_right,
                    ),
                )
            )

        return MainRobotObservation(
            actor_id=self._actor_id(robot),
            name=robot.label,
            move_state=robot.state_move.get(),
            load_state=robot.state_load.get(),
            x=robot.x,
            y=robot.y,
            z=robot.z,
            busy=robot.cmd_active,
            pending_commands=robot.cmd_store.length(),
            start_queue=self._queue_object(
                f"layout:{robot.layout.name}:start",
                "layout_start",
                robot.store_start,
            ),
            end_queue=self._queue_object(
                f"layout:{robot.layout.name}:end",
                "layout_end",
                robot.store_end,
            ),
            corridors=tuple(corridors),
        )

    def arm_robot_status(self, robot: SimRobotCorridorArm) -> ArmRobotObservation:
        machine_slots = []
        for machine_num, sim_machine in enumerate(robot.sim_machines):
            machine_name = robot.machines[machine_num].name
            machine_slots.append(
                ArmMachineObservation(
                    machine_num=machine_num,
                    machine_name=machine_name,
                    x=robot._machine_x(machine_num),
                    input_queue=self._queue_object(
                        f"machine:{machine_name}:in",
                        "machine_in",
                        sim_machine.store_in,
                    ),
                    output_queue=self._queue_object(
                        f"machine:{machine_name}:out",
                        "machine_out",
                        sim_machine.store_out,
                    ),
                )
            )

        return ArmRobotObservation(
            actor_id=self._actor_id(robot),
            name=robot.label,
            corridor_name=robot.corridor.name,
            corridor_x=robot.dx,
            direction=robot.direction,
            move_state=robot.state_move.get(),
            load_state=robot.state_load.get(),
            x=robot.x,
            y=robot.y,
            z=robot.z,
            busy=robot.cmd_active,
            pending_commands=robot.cmd_store.length(),
            input_queue=self._queue_object(
                f"arm:{robot.corridor.name}:{robot.direction}:in",
                "arm_in",
                robot.store_in,
            ),
            out_arm_queue=self._queue_object(
                f"arm:{robot.corridor.name}:{robot.direction}:arm_out",
                "arm_out",
                robot.store_out_arm,
            ),
            out_main_queue=self._queue_object(
                f"arm:{robot.corridor.name}:{robot.direction}:main_out",
                "main_out",
                robot.store_out_main,
            ),
            machine_slots=tuple(machine_slots),
        )

    def machine_status(self, machine: SimMachine) -> MachineObservation:
        tool_specs = tuple(
            ToolSpec(
                name=tool_type.name,
                mount_time=tool_type.mount_time,
                unmount_time=tool_type.unmount_time,
                total_life_units=tool_type.total_life_units,
            )
            for tool_type in machine.tool_types
        )
        remaining_life_units = {
            tool_type.name: machine.remaining_life_units[tool_type]
            for tool_type in machine.tool_types
        }
        return MachineObservation(
            actor_id=self._actor_id(machine),
            machine_name=machine.machine.name,
            corridor_name=machine.machine.corridor.name,
            side="left" if machine.machine.left else "right",
            state=machine.state.get(),
            current_tool_name=machine.tool_type.name if machine.tool_type is not None else None,
            busy=machine.cmd_active,
            pending_commands=machine.cmd_store.length(),
            input_queue=self._queue_object(
                f"machine:{machine.machine.name}:in",
                "machine_in",
                machine.store_in,
            ),
            output_queue=self._queue_object(
                f"machine:{machine.machine.name}:out",
                "machine_out",
                machine.store_out,
            ),
            remaining_life_units=remaining_life_units,
            available_tools=tool_specs,
        )

    def read_status(self) -> SystemObservation:
        return SystemObservation(
            time=self.env.now(),
            main_robots=tuple(self.main_robot_status(robot) for robot in self.main_robots),
            arm_robots=tuple(self.arm_robot_status(robot) for robot in self.arm_robots),
            machines=tuple(self.machine_status(machine) for machine in self.machines),
            order_jobs=tuple(self.order_job_status(job) for job in self.order_jobs),
        )

    def plan_job(self, request: JobPlanningRequest) -> JobPlan:
        return self.routing_policy.plan_job(request)

    def plan_job_candidates(self, request: JobPlanningRequest):
        return self.routing_policy.plan_job_candidates(request)

    def build_commands(self, system_status: SystemObservation) -> tuple[DispatchCommand, ...]:
        return self.dispatch_policy.decide(system_status)

    def process(self):
        while True:
            system_status = self.read_status()
            commands = self.build_commands(system_status)

            for command in commands:
                cmd_store = self._cmd_stores.get(command.actor_id)
                if cmd_store is None:
                    raise ValueError(f"Missing command store for actor {command.actor_id}")
                yield self.to_store(cmd_store, ControllerCommand(command.payload, env=self.env))

            yield self.hold(self.interval)
