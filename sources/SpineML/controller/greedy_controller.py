from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

from .simulation_bridge import SimulationBridge
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
    RoutingCandidate,
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
    AGING_WEIGHT = 0.2
    MACHINE_AGING_WEIGHT = 0.15
    STARVATION_WAIT_THRESHOLD = 25.0
    STARVATION_BONUS = 8.0
    TARGET_FREE_CAPACITY_WEIGHT = 1.0
    PICK_QUEUE_LENGTH_WEIGHT = 0.4
    PICK_QUEUE_UTILIZATION_WEIGHT = 4.0
    DOWNSTREAM_PLACE_WEIGHT = 0.15
    MAIN_PICK_TRAVEL_WEIGHT = 1.0
    MAIN_PLACE_TRAVEL_WEIGHT = 0.8
    ARM_PICK_TRAVEL_WEIGHT = 1.0
    ARM_PLACE_TRAVEL_WEIGHT = 0.8
    MACHINE_DELAY_WEIGHT = 0.2
    MACHINE_OUTPUT_CLEAR_BONUS = 18.0
    CORRIDOR_CLEAR_BONUS = 12.0
    FINISH_JOB_BONUS = 10.0
    DEFECTIVE_EXIT_BONUS = 8.0
    SHORT_OPERATION_WEIGHT = 0.4
    REMAINING_MACHINE_WEIGHT = 4.0

    def _job_priority(
        self,
        job: JobHeadObservation,
        route: RoutingCandidate | None = None,
    ) -> float:
        slack_time = job.slack_time
        remaining_processing_time_estimate = job.remaining_processing_time_estimate
        remaining_machines = job.remaining_machines
        next_machine_name = job.next_machine_name

        if route is not None:
            slack_time += job.remaining_processing_time_estimate - route.remaining_processing_time_estimate
            remaining_processing_time_estimate = route.remaining_processing_time_estimate
            remaining_machines = route.remaining_machines
            next_machine_name = route.next_machine_name

        score = -self.SLACK_WEIGHT * slack_time
        score -= self.SHORT_OPERATION_WEIGHT * remaining_processing_time_estimate
        score -= self.REMAINING_MACHINE_WEIGHT * remaining_machines
        if next_machine_name is None:
            score += self.FINISH_JOB_BONUS
        if job.is_defective:
            score += self.DEFECTIVE_EXIT_BONUS
        return score

    def _queue_pick_pressure(self, source_queue: QueueObject) -> float:
        score = self.PICK_QUEUE_LENGTH_WEIGHT * math.log1p(source_queue.length)
        if source_queue.capacity > 0 and source_queue.capacity != float("inf"):
            score += self.PICK_QUEUE_UTILIZATION_WEIGHT * (source_queue.length / source_queue.capacity)
        return score

    def _aging_bonus(self, wait_time: float, *, weight: float) -> float:
        score = weight * math.log1p(max(0.0, wait_time))
        if wait_time >= self.STARVATION_WAIT_THRESHOLD:
            score += self.STARVATION_BONUS
        return score

    def _normalized_free_capacity_score(self, queue: QueueObject) -> float:
        if queue.capacity > 0 and queue.capacity != float("inf"):
            return queue.free_capacity / queue.capacity
        return 1.0 if queue.free_capacity > 0 else 0.0

    def _distance_penalty(self, distance: float, *, weight: float) -> float:
        return weight * math.log1p(abs(distance))

    def _machine_observation_by_name(self, machine_name: str):
        if self._current_system_status is None:
            return None
        for machine in self._current_system_status.machines:
            if machine.machine_name == machine_name:
                return machine
        return None

    def _tool_adjustment_delay(self, route: RoutingCandidate) -> float:
        if route.next_machine_name is None or route.next_tool_name is None:
            return 0.0
        machine = self._machine_observation_by_name(route.next_machine_name)
        if machine is None:
            return 0.0

        tool_specs = {tool.name: tool for tool in machine.available_tools}
        target_tool = tool_specs.get(route.next_tool_name)
        if target_tool is None:
            return 0.0

        remaining_life_units = machine.remaining_life_units.get(route.next_tool_name, target_tool.total_life_units)
        required_life_units = route.next_consumed_life_units or 0

        if machine.current_tool_name != route.next_tool_name:
            delay = target_tool.mount_time
            if machine.current_tool_name is not None:
                current_tool = tool_specs.get(machine.current_tool_name)
                if current_tool is not None:
                    delay += current_tool.unmount_time
            if remaining_life_units < required_life_units:
                remaining_life_units = target_tool.total_life_units
            return delay

        if remaining_life_units < required_life_units:
            return target_tool.unmount_time + target_tool.mount_time
        return 0.0

    def _machine_delay_penalty(self, route: RoutingCandidate) -> float:
        if route.next_machine_name is None:
            return 0.0
        machine = self._machine_observation_by_name(route.next_machine_name)
        if machine is None:
            return 0.0

        queue_delay = sum((job.next_operation_duration or 0.0) for job in machine.input_queue.jobs)
        busy_delay = (route.next_operation_duration or 0.0) if (machine.busy or machine.pending_commands > 0) else 0.0
        tool_delay = self._tool_adjustment_delay(route)
        expected_delay = queue_delay + busy_delay + tool_delay
        return self.MACHINE_DELAY_WEIGHT * math.log1p(expected_delay)

    def _main_storage_y(self, robot: MainRobotObservation) -> float:
        return 2.0 + len(robot.corridors) / 1.15

    def _main_pick_y(self, robot: MainRobotObservation, action: MainRobotPickAction) -> float:
        if action.kind == "start":
            return -self._main_storage_y(robot)
        corridor = self._corridor_by_name(robot.corridors, action.corridor_name)
        return corridor.y

    def _main_place_y(self, robot: MainRobotObservation, action: MainRobotPlaceAction) -> float:
        if action.kind == "end":
            return self._main_storage_y(robot)
        corridor = self._corridor_by_name(robot.corridors, action.corridor_name)
        return corridor.y

    def _arm_pick_x(self, robot: ArmRobotObservation, action: ArmRobotPickAction) -> float:
        if action.kind == "store_in":
            return robot.corridor_x
        return self._machine_slot_by_num(robot.machine_slots, action.machine_num).x

    def _arm_place_x(self, robot: ArmRobotObservation, action: ArmRobotPlaceAction) -> float:
        if action.kind == "machine_in":
            return self._machine_slot_by_num(robot.machine_slots, action.machine_num).x
        return robot.corridor_x

    def _pick_job_priority(
        self,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> float:
        return (
            self._job_priority(job)
            + self._queue_pick_pressure(source_queue)
            + self._aging_bonus(job.queue_wait_time, weight=self.AGING_WEIGHT)
        )

    def score_main_robot_pick(
        self,
        robot: MainRobotObservation,
        action: MainRobotPickAction,
        source_queue: QueueObject,
        job: JobHeadObservation,
    ) -> float | None:
        best_place_score = self.best_main_robot_place_score(robot, job, source_queue)
        if best_place_score is None:
            return None

        score = self._pick_job_priority(job, source_queue)
        score -= self._distance_penalty(robot.y - self._main_pick_y(robot, action), weight=self.MAIN_PICK_TRAVEL_WEIGHT)
        score += self.DOWNSTREAM_PLACE_WEIGHT * best_place_score
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
            self._job_priority(job, action.route)
            + action.route.route_score
            + self.TARGET_FREE_CAPACITY_WEIGHT * self._normalized_free_capacity_score(target_queue)
            - self._distance_penalty(robot.y - self._main_place_y(robot, action), weight=self.MAIN_PLACE_TRAVEL_WEIGHT)
            - self._machine_delay_penalty(action.route)
        )

    def score_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
        source_queue: QueueObject,
        job: JobHeadObservation,
    ) -> float | None:
        best_place_score = self.best_arm_robot_place_score(robot, job, source_queue)
        if best_place_score is None:
            return None

        score = self._pick_job_priority(job, source_queue)
        score -= self._distance_penalty(robot.x - self._arm_pick_x(robot, action), weight=self.ARM_PICK_TRAVEL_WEIGHT)
        score += self.DOWNSTREAM_PLACE_WEIGHT * best_place_score
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
            self._job_priority(job, action.route)
            + action.route.route_score
            + self.TARGET_FREE_CAPACITY_WEIGHT * self._normalized_free_capacity_score(target_queue)
            - self._distance_penalty(robot.x - self._arm_place_x(robot, action), weight=self.ARM_PLACE_TRAVEL_WEIGHT)
            - self._machine_delay_penalty(action.route)
        )

    def score_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
        command: MachineCommand,
    ) -> float | None:
        if job.is_defective:
            return None
        return (
            self._job_priority(job)
            + self._aging_bonus(job.queue_wait_time, weight=self.MACHINE_AGING_WEIGHT)
            - self.SHORT_OPERATION_WEIGHT * command.duration
        )


class GreedyController(SimulationBridge):
    def __init__(
        self,

        rng_seed: int | None = None,
        *args,
        **kwargs,
    ):
        rng = random.Random(rng_seed)
        routing_policy = GreedyRoutingPolicy(rng=rng)
        super().__init__(
            routing_policy=routing_policy,
            dispatch_policy=GreedyDispatchPolicy(rng=rng, routing_policy=routing_policy),
            *args,
            **kwargs,
        )
