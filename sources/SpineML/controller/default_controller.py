from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .calculate import (
    calculateMachineSequencesFromOperationSequence,
    calculateOperationSequences,
)
from .controller import PolicyController
from .policy import DispatchPolicy, RoutingPolicy, RuleBasedDispatchPolicy
from .types import (
    ArmRobotObservation,
    ArmRobotPickAction,
    ArmRobotPlaceAction,
    JobHeadObservation,
    JobKey,
    JobPlanningRequest,
    JobPlan,
    MachineCommand,
    MachineObservation,
    MainRobotObservation,
    MainRobotPickAction,
    MainRobotPlaceAction,
    ToolAction,
)

if TYPE_CHECKING:
    from ..Configuration import Order


class DefaultRoutingPolicy(RoutingPolicy):
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def choose_operation_sequence(self, order: Order, operation_sequences: list[list]):
        return list(self.rng.choice(operation_sequences))

    def choose_machine_sequence(self, job_key: JobKey, machine_sequences: list[list]):
        return list(self.rng.choice(machine_sequences))

    def plan_job(self, request: JobPlanningRequest) -> JobPlan:
        order = request.order
        layout = request.layout

        operation_sequences = calculateOperationSequences(order.product_type)
        operation_sequence = self.choose_operation_sequence(order, operation_sequences)

        machine_sequences = calculateMachineSequencesFromOperationSequence(list(operation_sequence), layout)
        machine_sequence = self.choose_machine_sequence(request.job_key, machine_sequences)
        return JobPlan(operation_sequence=operation_sequence, machine_sequence=machine_sequence)


class DefaultDispatchPolicy(RuleBasedDispatchPolicy):
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def decide_main_robot_pick(self, robot: MainRobotObservation) -> MainRobotPickAction | None:
        if robot.load_state != "empty":
            return None

        candidates: list[MainRobotPickAction] = []
        if robot.start_queue.length > 0:
            candidates.append(MainRobotPickAction(kind="start"))

        for corridor in robot.corridors:
            if corridor.main_queue.length > 0:
                candidates.append(
                    MainRobotPickAction(kind="corridor_main", corridor_name=corridor.corridor_name)
                )

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return self.rng.choice(candidates)

    def decide_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
    ) -> MainRobotPlaceAction:
        if job.next_machine_name is None or job.next_machine_corridor_name is None:
            return MainRobotPlaceAction(kind="end")

        return MainRobotPlaceAction(
            kind="corridor_in",
            corridor_name=job.next_machine_corridor_name,
            side=job.next_machine_side,
        )

    def decide_arm_robot_pick(self, robot: ArmRobotObservation) -> ArmRobotPickAction | None:
        if robot.load_state != "empty":
            return None

        candidates: list[ArmRobotPickAction] = []
        if robot.input_queue.length > 0:
            candidates.append(ArmRobotPickAction(kind="store_in"))

        for machine_slot in robot.machine_slots:
            if machine_slot.output_queue.length > 0:
                candidates.append(
                    ArmRobotPickAction(kind="machine_out", machine_num=machine_slot.machine_num)
                )

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return self.rng.choice(candidates)

    def decide_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
    ) -> ArmRobotPlaceAction:
        if job.next_machine_name is not None and job.next_machine_corridor_name == robot.corridor_name:
            for machine_slot in robot.machine_slots:
                if machine_slot.machine_name == job.next_machine_name:
                    return ArmRobotPlaceAction(kind="machine_in", machine_num=machine_slot.machine_num)
            return ArmRobotPlaceAction(kind="arm_out")

        return ArmRobotPlaceAction(kind="main_out")

    def decide_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
    ) -> MachineCommand | None:
        if job.next_machine_name != machine.machine_name:
            raise ValueError(
                f"Machine command mismatch: expected {job.next_machine_name}, got {machine.machine_name}"
            )

        if job.next_tool_name is None:
            raise ValueError(f"Job {job.job_key} has no next tool for machine {machine.machine_name}")
        if job.next_operation_duration is None or job.next_consumed_life_units is None:
            raise ValueError(f"Job {job.job_key} has incomplete next operation for {machine.machine_name}")
        if job.next_produced_product_name is None:
            raise ValueError(f"Job {job.job_key} has no produced product for {machine.machine_name}")

        tool_specs = {tool.name: tool for tool in machine.available_tools}
        tool_spec = tool_specs[job.next_tool_name]
        remaining_life_units = machine.remaining_life_units[job.next_tool_name]
        tool_actions: list[ToolAction] = []

        if machine.current_tool_name != job.next_tool_name:
            if machine.current_tool_name is not None:
                current_tool = tool_specs[machine.current_tool_name]
                tool_actions.append(
                    ToolAction(
                        state="unmounting",
                        duration=current_tool.unmount_time,
                    )
                )
            tool_actions.append(
                ToolAction(
                    state="mounting",
                    duration=tool_spec.mount_time,
                    mount_tool_name=job.next_tool_name,
                )
            )
            if remaining_life_units < job.next_consumed_life_units:
                remaining_life_units = tool_spec.total_life_units
        elif remaining_life_units < job.next_consumed_life_units:
            tool_actions.append(
                ToolAction(
                    state="unmounting",
                    duration=tool_spec.unmount_time,
                )
            )
            tool_actions.append(
                ToolAction(
                    state="mounting",
                    duration=tool_spec.mount_time,
                    mount_tool_name=job.next_tool_name,
                )
            )
            remaining_life_units = tool_spec.total_life_units

        return MachineCommand(
            job_key=job.job_key,
            expected_machine_name=machine.machine_name,
            tool_name=job.next_tool_name,
            duration=job.next_operation_duration,
            produced_product_name=job.next_produced_product_name,
            remaining_life_units_before=remaining_life_units,
            remaining_life_units_after=remaining_life_units - job.next_consumed_life_units,
            tool_actions=tuple(tool_actions),
        )


class DefaultController(PolicyController):
    def __init__(
        self,
        routing_policy: RoutingPolicy | None = None,
        dispatch_policy: DispatchPolicy | None = None,
        *args,
        **kwargs,
    ):
        rng = random.Random()
        super().__init__(
            routing_policy=routing_policy or DefaultRoutingPolicy(rng=rng),
            dispatch_policy=dispatch_policy or DefaultDispatchPolicy(rng=rng),
            *args,
            **kwargs,
        )
