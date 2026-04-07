from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from .controller import PolicyController
from .policy import (
    DispatchPolicy,
    RuleBasedDispatchPolicy,
    RoutingPolicy,
    ScoredRoutingPolicy,
)
from .types import (
    ArmRobotObservation,
    ArmRobotPickAction,
    ArmRobotPlaceAction,
    JobHeadObservation,
    JobPlanningRequest,
    MachineCommand,
    MachineObservation,
    MainRobotObservation,
    MainRobotPickAction,
    MainRobotPlaceAction,
    QueueObject,
)

if TYPE_CHECKING:
    from ..Configuration import Order


class GreedyRoutingPolicy(ScoredRoutingPolicy):
    DEFECT_RISK_WEIGHT = 10.0
    CORRIDOR_CHANGE_PENALTY = 6.0
    MACHINE_POSITION_WEIGHT = 0.5

    def _operation_duration(self, operation_sequence: list[Any]) -> float:
        return float(sum(operation.duration for operation in operation_sequence))

    def _operation_defect_risk(self, operation_sequence: list[Any]) -> float:
        return float(sum(operation.defect_probability for operation in operation_sequence))

    def _machine_processing_duration(
        self,
        operation_sequence: list[Any],
        machine_sequence: list[Any],
    ) -> float:
        duration = 0.0
        for operation, machine in zip(operation_sequence, machine_sequence, strict=True):
            duration += operation.duration
            duration += machine.dimension_processing_time(operation.consumes_product_type)
        return duration

    def _machine_position_index(self, machine: Any) -> int:
        side_machines = (
            machine.corridor.machines_left
            if machine.left
            else machine.corridor.machines_right
        )
        try:
            return side_machines.index(machine)
        except ValueError:
            return 0

    def _corridor_switch_count(self, machine_sequence: list[Any]) -> int:
        switches = 0
        for current_machine, next_machine in zip(machine_sequence, machine_sequence[1:], strict=False):
            if current_machine.corridor != next_machine.corridor:
                switches += 1
        return switches

    def _machine_position_cost(self, machine_sequence: list[Any]) -> float:
        cost = 0.0
        for machine in machine_sequence:
            cost += 2.0 + 2.0 * self._machine_position_index(machine)
        return cost

    def _transfer_duration(
        self,
        request: JobPlanningRequest,
        machine_sequence: list[Any],
    ) -> float:
        if len(machine_sequence) == 0:
            return request.layout.storage_out_time + request.layout.storage_in_time

        duration = 0.0
        first_machine = machine_sequence[0]
        duration += request.layout.storage_out_time
        duration += first_machine.corridor.storage_in_time
        duration += first_machine.corridor.storage_out_time
        duration += first_machine.storage_in_time

        for current_machine, next_machine in zip(machine_sequence, machine_sequence[1:], strict=False):
            duration += current_machine.storage_out_time
            if current_machine.corridor == next_machine.corridor:
                duration += next_machine.storage_in_time
            else:
                duration += current_machine.corridor.storage_in_time
                duration += current_machine.corridor.storage_out_time
                duration += next_machine.corridor.storage_in_time
                duration += next_machine.corridor.storage_out_time
                duration += next_machine.storage_in_time

        last_machine = machine_sequence[-1]
        duration += last_machine.storage_out_time
        duration += last_machine.corridor.storage_in_time
        duration += last_machine.corridor.storage_out_time
        duration += request.layout.storage_in_time

        return duration

    def score_operation_sequence(self, order: Order, operation_sequence: list[Any]) -> float | None:
        duration = self._operation_duration(operation_sequence)
        defect_risk = self._operation_defect_risk(operation_sequence)
        return -(duration + self.DEFECT_RISK_WEIGHT * defect_risk)

    def score_machine_sequence(
        self,
        request: JobPlanningRequest,
        operation_sequence: list[Any],
        machine_sequence: list[Any],
    ) -> float | None:
        if len(operation_sequence) != len(machine_sequence):
            return None

        processing_duration = self._machine_processing_duration(operation_sequence, machine_sequence)
        transfer_duration = self._transfer_duration(request, machine_sequence)
        corridor_change_cost = self.CORRIDOR_CHANGE_PENALTY * self._corridor_switch_count(machine_sequence)
        machine_position_cost = self.MACHINE_POSITION_WEIGHT * self._machine_position_cost(machine_sequence)
        return -(processing_duration + transfer_duration + corridor_change_cost + machine_position_cost)


class GreedyDispatchPolicy(RuleBasedDispatchPolicy):
    SLACK_WEIGHT = 0.3
    TARGET_FREE_CAPACITY_WEIGHT = 1.0
    MACHINE_OUTPUT_CLEAR_BONUS = 18.0
    CORRIDOR_CLEAR_BONUS = 12.0
    FINISH_JOB_BONUS = 10.0
    DEFECTIVE_EXIT_BONUS = 8.0
    SHORT_OPERATION_WEIGHT = 0.4
    REMAINING_MACHINE_WEIGHT = 4.0

    def _job_priority(self, job: JobHeadObservation) -> float:
        score = -self.SLACK_WEIGHT * job.slack_time
        score -= self.SHORT_OPERATION_WEIGHT * job.remaining_processing_time_estimate
        score -= self.REMAINING_MACHINE_WEIGHT * job.remaining_machines
        if job.next_machine_name is None:
            score += self.FINISH_JOB_BONUS
        if job.is_defective:
            score += self.DEFECTIVE_EXIT_BONUS
        return score

    def score_main_robot_pick(
        self,
        robot: MainRobotObservation,
        action: MainRobotPickAction,
        source_queue: QueueObject,
    ) -> float | None:
        job = source_queue.head
        if job is None:
            return None

        best_place_score = self.best_main_robot_place_score(robot, job)
        if best_place_score is None:
            return None

        score = best_place_score
        if action.kind == "corridor_main":
            score += self.CORRIDOR_CLEAR_BONUS
        return score

    def score_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        action: MainRobotPlaceAction,
        target_queue: QueueObject,
    ) -> float | None:
        if target_queue.free_capacity <= 0:
            return None
        return (
            self._job_priority(job)
            + action.route.route_score
            + self.TARGET_FREE_CAPACITY_WEIGHT * target_queue.free_capacity
        )

    def score_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
        source_queue: QueueObject,
    ) -> float | None:
        job = source_queue.head
        if job is None:
            return None

        best_place_score = self.best_arm_robot_place_score(robot, job)
        if best_place_score is None:
            return None

        score = best_place_score
        if action.kind == "machine_out":
            score += self.MACHINE_OUTPUT_CLEAR_BONUS
        return score

    def score_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        action: ArmRobotPlaceAction,
        target_queue: QueueObject,
    ) -> float | None:
        if target_queue.free_capacity <= 0:
            return None
        return (
            self._job_priority(job)
            + action.route.route_score
            + self.TARGET_FREE_CAPACITY_WEIGHT * target_queue.free_capacity
        )

    def score_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
        command: MachineCommand,
    ) -> float | None:
        if job.is_defective:
            return None
        return self._job_priority(job) - self.SHORT_OPERATION_WEIGHT * command.duration


class GreedyController(PolicyController):
    def __init__(
        self,

        rng_seed: int | None = None,
        *args,
        **kwargs,
    ):
        rng = random.Random(rng_seed)
        super().__init__(
            routing_policy=GreedyRoutingPolicy(rng=rng),
            dispatch_policy=GreedyDispatchPolicy(rng=rng),
            *args,
            **kwargs,
        )
