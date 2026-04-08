from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from .calculate import (
    calculateMachineSequencesFromOperationSequence,
    calculateOperationSequences,
    calculateRemainingOperationSequences,
)
from .types import (
    ArmMachineObservation,
    ArmRobotCommand,
    ArmRobotObservation,
    ArmRobotPickAction,
    ArmRobotPlaceAction,
    CorridorObservation,
    DispatchCommand,
    JobHeadObservation,
    JobPlanningRequest,
    JobPlan,
    MachineCommand,
    MachineObservation,
    MainRobotCommand,
    MainRobotObservation,
    MainRobotPickAction,
    MainRobotPlaceAction,
    QueueObject,
    RoutingCandidate,
    SystemObservation,
    ToolAction,
)

if TYPE_CHECKING:
    from ..Configuration import Order


T = TypeVar("T")


def _select_best_candidate(
    candidates: list[T],
    score_fn: Callable[[T], float | None],
    rng: random.Random,
) -> T | None:
    best_score: float | None = None
    best_candidates: list[T] = []
    for candidate in candidates:
        score = score_fn(candidate)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_candidates = [candidate]
        elif score == best_score:
            best_candidates.append(candidate)

    if len(best_candidates) == 0:
        return None
    if len(best_candidates) == 1:
        return best_candidates[0]
    return rng.choice(best_candidates)


class RoutingPolicy(ABC):
    @abstractmethod
    def plan_job_candidates(self, request: JobPlanningRequest) -> tuple[RoutingCandidate, ...]:
        raise NotImplementedError

    @abstractmethod
    def plan_job(self, request: JobPlanningRequest) -> JobPlan:
        raise NotImplementedError


class DispatchPolicy(ABC):
    @abstractmethod
    def decide(self, system_status: SystemObservation) -> tuple[DispatchCommand, ...]:
        raise NotImplementedError


class ScoredRoutingPolicy(RoutingPolicy, ABC):
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    @abstractmethod
    def score_operation_sequence(self, order: Order, operation_sequence: list[Any]) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def score_machine_sequence(
        self,
        request: JobPlanningRequest,
        operation_sequence: list[Any],
        machine_sequence: list[Any],
    ) -> float | None:
        raise NotImplementedError

    def choose_operation_sequence(self, order: Order, operation_sequences: list[list[Any]]) -> list[Any]:
        def _score_operation_sequence(operation_sequence: list[Any]) -> float | None:
            return self.score_operation_sequence(order, operation_sequence)

        candidate = _select_best_candidate(
            list(operation_sequences),
            _score_operation_sequence,
            self.rng,
        )
        if candidate is None:
            raise ValueError(f"No scored operation sequence found for order {order.name}")
        return list(candidate)

    def choose_machine_sequence(
        self,
        request: JobPlanningRequest,
        operation_sequence: list[Any],
        machine_sequences: list[list[Any]],
    ) -> list[Any]:
        def _score_machine_sequence(machine_sequence: list[Any]) -> float | None:
            return self.score_machine_sequence(
                request,
                operation_sequence,
                machine_sequence,
            )

        candidate = _select_best_candidate(
            list(machine_sequences),
            _score_machine_sequence,
            self.rng,
        )
        if candidate is None:
            raise ValueError(f"No scored machine sequence found for order {request.order.name}")
        return list(candidate)

    def _operation_sequences(self, request: JobPlanningRequest) -> list[list[Any]]:
        order = request.order
        if request.current_product_type is None:
            return calculateOperationSequences(order.product_type)
        return calculateRemainingOperationSequences(
            request.current_product_type,
            order.product_type,
        )

    def _remaining_processing_time_estimate(
        self,
        operation_sequence: list[Any],
        machine_sequence: list[Any],
    ) -> float:
        estimate = 0.0
        for index, operation in enumerate(operation_sequence):
            estimate += operation.duration
            if index < len(machine_sequence):
                estimate += machine_sequence[index].dimension_processing_time(
                    operation.consumes_product_type
                )
        return estimate

    def _build_routing_candidate(
        self,
        operation_sequence: list[Any],
        machine_sequence: list[Any],
        operation_score: float,
        machine_score: float,
    ) -> RoutingCandidate:
        next_operation = operation_sequence[0] if len(operation_sequence) > 0 else None
        next_machine = machine_sequence[0] if len(machine_sequence) > 0 else None
        next_side = None
        if next_machine is not None:
            next_side = "left" if next_machine.left else "right"

        return RoutingCandidate(
            operation_sequence=tuple(operation_sequence),
            machine_sequence=tuple(machine_sequence),
            route_score=operation_score + machine_score,
            remaining_operations=len(operation_sequence),
            remaining_machines=len(machine_sequence),
            remaining_processing_time_estimate=self._remaining_processing_time_estimate(
                operation_sequence,
                machine_sequence,
            ),
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

    def plan_job_candidates(self, request: JobPlanningRequest) -> tuple[RoutingCandidate, ...]:
        order = request.order
        layout = request.layout
        operation_sequences = self._operation_sequences(request)
        if len(operation_sequences) == 0:
            return ()

        scored_candidates: list[RoutingCandidate] = []
        for operation_sequence in operation_sequences:
            operation_score = self.score_operation_sequence(order, operation_sequence)
            if operation_score is None:
                continue

            machine_sequences = calculateMachineSequencesFromOperationSequence(list(operation_sequence), layout)
            for machine_sequence in machine_sequences:
                machine_score = self.score_machine_sequence(request, operation_sequence, machine_sequence)
                if machine_score is None:
                    continue
                scored_candidates.append(
                    self._build_routing_candidate(
                        operation_sequence,
                        machine_sequence,
                        operation_score,
                        machine_score,
                    )
                )

        scored_candidates.sort(
            key=lambda candidate: (candidate.route_score, self.rng.random()),
            reverse=True,
        )
        return tuple(scored_candidates)

    def plan_job(self, request: JobPlanningRequest) -> JobPlan:
        order = request.order
        layout = request.layout
        operation_sequences = self._operation_sequences(request)
        if len(operation_sequences) == 0:
            raise ValueError(f"No operation sequence found for order {order.name}")
        operation_sequence = self.choose_operation_sequence(order, operation_sequences)

        machine_sequences = calculateMachineSequencesFromOperationSequence(list(operation_sequence), layout)
        if len(machine_sequences) == 0:
            raise ValueError(f"No machine sequence found for order {order.name} in layout {layout.name}")
        machine_sequence = self.choose_machine_sequence(request, operation_sequence, machine_sequences)

        return JobPlan(operation_sequence=operation_sequence, machine_sequence=machine_sequence)


class RuleBasedDispatchPolicy(DispatchPolicy, ABC):
    def __init__(
        self,
        rng: random.Random | None = None,
        routing_policy: RoutingPolicy | None = None,
    ):
        self.rng = rng or random.Random()
        self.routing_policy = routing_policy
        self._current_system_status: SystemObservation | None = None

    @abstractmethod
    def score_main_robot_pick(
        self,
        robot: MainRobotObservation,
        action: MainRobotPickAction,
        source_queue: QueueObject,
        job: JobHeadObservation,
    ) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def score_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
        source_queue: QueueObject,
        job: JobHeadObservation,
    ) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def score_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        action: MainRobotPlaceAction,
        target_queue: QueueObject,
    ) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def score_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        action: ArmRobotPlaceAction,
        target_queue: QueueObject,
    ) -> float | None:
        raise NotImplementedError

    def score_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
        command: MachineCommand,
    ) -> float | None:
        return 0.0

    def _corridor_by_name(
        self,
        corridors: tuple[CorridorObservation, ...],
        corridor_name: str,
    ) -> CorridorObservation:
        for corridor in corridors:
            if corridor.corridor_name == corridor_name:
                return corridor
        raise ValueError(f"Unknown corridor in observation: {corridor_name}")

    def _machine_slot_by_num(
        self,
        machine_slots: tuple[ArmMachineObservation, ...],
        machine_num: int,
    ) -> ArmMachineObservation:
        for slot in machine_slots:
            if slot.machine_num == machine_num:
                return slot
        raise ValueError(f"Unknown machine slot in observation: {machine_num}")

    def _remaining_processing_time_estimate_from_sequences(
        self,
        operation_sequence: tuple[Any, ...] | list[Any],
        machine_sequence: tuple[Any, ...] | list[Any],
    ) -> float:
        estimate = 0.0
        for index, operation in enumerate(operation_sequence):
            estimate += operation.duration
            if index < len(machine_sequence):
                estimate += machine_sequence[index].dimension_processing_time(
                    operation.consumes_product_type
                )
        return estimate

    def _empty_routing_candidate(self) -> RoutingCandidate:
        return RoutingCandidate(
            operation_sequence=(),
            machine_sequence=(),
            route_score=0.0,
            remaining_operations=0,
            remaining_machines=0,
            remaining_processing_time_estimate=0.0,
            next_operation_name=None,
            next_tool_name=None,
            next_operation_duration=None,
            next_consumed_life_units=None,
            next_produced_product_name=None,
            next_machine_name=None,
            next_machine_corridor_name=None,
            next_machine_side=None,
        )

    def _routing_candidate_from_sequences(
        self,
        operation_sequence: tuple[Any, ...] | list[Any],
        machine_sequence: tuple[Any, ...] | list[Any],
    ) -> RoutingCandidate:
        next_operation = operation_sequence[0] if len(operation_sequence) > 0 else None
        next_machine = machine_sequence[0] if len(machine_sequence) > 0 else None
        next_side = None
        if next_machine is not None:
            next_side = "left" if next_machine.left else "right"

        return RoutingCandidate(
            operation_sequence=tuple(operation_sequence),
            machine_sequence=tuple(machine_sequence),
            route_score=0.0,
            remaining_operations=len(operation_sequence),
            remaining_machines=len(machine_sequence),
            remaining_processing_time_estimate=self._remaining_processing_time_estimate_from_sequences(
                operation_sequence,
                machine_sequence,
            ),
            next_operation_name=next_operation.name if next_operation is not None else None,
            next_tool_name=next_operation.tool_type.name if next_operation is not None else None,
            next_operation_duration=(
                next_operation.duration
                + next_machine.dimension_processing_time(next_operation.consumes_product_type)
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

    def _routing_candidates(
        self,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> tuple[RoutingCandidate, ...]:
        if job.is_defective:
            return (self._empty_routing_candidate(),)

        if source_queue.queue_kind == "machine_in":
            if len(job.committed_operation_sequence) == 0 and len(job.committed_machine_sequence) == 0:
                return (self._empty_routing_candidate(),)
            return (
                self._routing_candidate_from_sequences(
                    job.committed_operation_sequence,
                    job.committed_machine_sequence,
                ),
            )

        if self.routing_policy is None:
            raise RuntimeError("RuleBasedDispatchPolicy requires a routing policy for routing candidates")

        candidates = self.routing_policy.plan_job_candidates(job.routing_request)
        if len(candidates) > 0:
            return candidates

        if len(job.committed_operation_sequence) == 0 and len(job.committed_machine_sequence) == 0:
            return (self._empty_routing_candidate(),)
        return (
            self._routing_candidate_from_sequences(
                job.committed_operation_sequence,
                job.committed_machine_sequence,
            ),
        )

    def main_robot_pick_candidates(self, robot: MainRobotObservation) -> tuple[MainRobotPickAction, ...]:
        if robot.load_state != "empty":
            return ()

        candidates: list[MainRobotPickAction] = []
        if robot.start_queue.length > 0:
            candidates.append(MainRobotPickAction(kind="start"))
        for corridor in robot.corridors:
            if corridor.main_queue.length > 0:
                candidates.append(
                    MainRobotPickAction(kind="corridor_main", corridor_name=corridor.corridor_name)
                )
        return tuple(candidates)

    def main_robot_pick_source_queue(
        self,
        robot: MainRobotObservation,
        action: MainRobotPickAction,
    ) -> QueueObject:
        if action.kind == "start":
            return robot.start_queue
        return self._corridor_by_name(robot.corridors, action.corridor_name).main_queue

    def decide_main_robot_pick(
        self,
        robot: MainRobotObservation,
    ) -> tuple[MainRobotPickAction, JobHeadObservation] | None:
        candidates: list[tuple[MainRobotPickAction, QueueObject, JobHeadObservation]] = []
        for action in self.main_robot_pick_candidates(robot):
            source_queue = self.main_robot_pick_source_queue(robot, action)
            for job in source_queue.jobs:
                candidates.append((action, source_queue, job))

        def _score_main_robot_pick(
            candidate: tuple[MainRobotPickAction, QueueObject, JobHeadObservation],
        ) -> float | None:
            action, source_queue, job = candidate
            return self.score_main_robot_pick(robot, action, source_queue, job)

        best_candidate = _select_best_candidate(
            candidates,
            _score_main_robot_pick,
            self.rng,
        )
        if best_candidate is None:
            return None
        return best_candidate[0], best_candidate[2]

    def main_robot_place_candidates(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> tuple[MainRobotPlaceAction, ...]:
        candidates: list[MainRobotPlaceAction] = []
        for route in self._routing_candidates(job, source_queue):
            if route.next_machine_name is None or route.next_machine_corridor_name is None:
                candidates.append(MainRobotPlaceAction(kind="end", route=route))
                continue
            candidates.append(
                MainRobotPlaceAction(
                    kind="corridor_in",
                    route=route,
                    corridor_name=route.next_machine_corridor_name,
                    side=route.next_machine_side,
                )
            )
        return tuple(candidates)

    def main_robot_place_target_queue(
        self,
        robot: MainRobotObservation,
        action: MainRobotPlaceAction,
    ) -> QueueObject:
        if action.kind == "end":
            return robot.end_queue

        corridor = self._corridor_by_name(robot.corridors, action.corridor_name)
        if action.side == "left":
            return corridor.left_queue
        return corridor.right_queue

    def decide_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> MainRobotPlaceAction:
        candidates = list(self.main_robot_place_candidates(robot, job, source_queue))

        def _score_main_robot_place(action: MainRobotPlaceAction) -> float | None:
            return self.score_main_robot_place(
                robot,
                job,
                action,
                self.main_robot_place_target_queue(robot, action),
            )

        candidate = _select_best_candidate(
            candidates,
            _score_main_robot_place,
            self.rng,
        )
        if candidate is None:
            raise ValueError(f"No main robot place action found for job {job.job_key}")
        return candidate

    def best_main_robot_place_score(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> float | None:
        best_score: float | None = None
        for action in self.main_robot_place_candidates(robot, job, source_queue):
            score = self.score_main_robot_place(
                robot,
                job,
                action,
                self.main_robot_place_target_queue(robot, action),
            )
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
        return best_score

    def arm_robot_pick_candidates(self, robot: ArmRobotObservation) -> tuple[ArmRobotPickAction, ...]:
        if robot.load_state != "empty":
            return ()

        candidates: list[ArmRobotPickAction] = []
        if robot.input_queue.length > 0:
            candidates.append(ArmRobotPickAction(kind="store_in"))
        for machine_slot in robot.machine_slots:
            if machine_slot.output_queue.length > 0:
                candidates.append(
                    ArmRobotPickAction(kind="machine_out", machine_num=machine_slot.machine_num)
                )
        return tuple(candidates)

    def arm_robot_pick_source_queue(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
    ) -> QueueObject:
        if action.kind == "store_in":
            return robot.input_queue
        return self._machine_slot_by_num(robot.machine_slots, action.machine_num).output_queue

    def decide_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
    ) -> tuple[ArmRobotPickAction, JobHeadObservation] | None:
        candidates: list[tuple[ArmRobotPickAction, QueueObject, JobHeadObservation]] = []
        for action in self.arm_robot_pick_candidates(robot):
            source_queue = self.arm_robot_pick_source_queue(robot, action)
            for job in source_queue.jobs:
                candidates.append((action, source_queue, job))

        def _score_arm_robot_pick(
            candidate: tuple[ArmRobotPickAction, QueueObject, JobHeadObservation],
        ) -> float | None:
            action, source_queue, job = candidate
            return self.score_arm_robot_pick(robot, action, source_queue, job)

        best_candidate = _select_best_candidate(
            candidates,
            _score_arm_robot_pick,
            self.rng,
        )
        if best_candidate is None:
            return None
        return best_candidate[0], best_candidate[2]

    def arm_robot_place_candidates(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> tuple[ArmRobotPlaceAction, ...]:
        candidates: list[ArmRobotPlaceAction] = []
        for route in self._routing_candidates(job, source_queue):
            if route.next_machine_name is not None and route.next_machine_corridor_name == robot.corridor_name:
                local_candidates: list[ArmRobotPlaceAction] = []
                for machine_slot in robot.machine_slots:
                    if machine_slot.machine_name == route.next_machine_name:
                        local_candidates.append(
                            ArmRobotPlaceAction(
                                kind="machine_in",
                                route=route,
                                machine_num=machine_slot.machine_num,
                            )
                        )
                if len(local_candidates) == 0:
                    local_candidates.append(ArmRobotPlaceAction(kind="arm_out", route=route))
                candidates.extend(local_candidates)
                continue

            candidates.append(ArmRobotPlaceAction(kind="main_out", route=route))
        return tuple(candidates)

    def arm_robot_place_target_queue(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPlaceAction,
    ) -> QueueObject:
        if action.kind == "machine_in":
            return self._machine_slot_by_num(robot.machine_slots, action.machine_num).input_queue
        if action.kind == "arm_out":
            return robot.out_arm_queue
        return robot.out_main_queue

    def decide_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> ArmRobotPlaceAction:
        candidates = list(self.arm_robot_place_candidates(robot, job, source_queue))

        def _score_arm_robot_place(action: ArmRobotPlaceAction) -> float | None:
            return self.score_arm_robot_place(
                robot,
                job,
                action,
                self.arm_robot_place_target_queue(robot, action),
            )

        candidate = _select_best_candidate(
            candidates,
            _score_arm_robot_place,
            self.rng,
        )
        if candidate is None:
            raise ValueError(f"No arm robot place action found for job {job.job_key}")
        return candidate

    def best_arm_robot_place_score(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        source_queue: QueueObject,
    ) -> float | None:
        best_score: float | None = None
        for action in self.arm_robot_place_candidates(robot, job, source_queue):
            score = self.score_arm_robot_place(
                robot,
                job,
                action,
                self.arm_robot_place_target_queue(robot, action),
            )
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
        return best_score

    def build_machine_command(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
    ) -> MachineCommand:
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

    def machine_process_candidates(
        self,
        machine: MachineObservation,
    ) -> tuple[tuple[JobHeadObservation, MachineCommand], ...]:
        candidates: list[tuple[JobHeadObservation, MachineCommand]] = []
        for job in machine.input_queue.jobs:
            candidates.append((job, self.build_machine_command(machine, job)))
        return tuple(candidates)

    def decide_machine_process(
        self,
        machine: MachineObservation,
    ) -> MachineCommand | None:
        candidates = list(self.machine_process_candidates(machine))

        def _score_machine_process(candidate: tuple[JobHeadObservation, MachineCommand]) -> float | None:
            job, command = candidate
            return self.score_machine_process(machine, job, command)

        best_candidate = _select_best_candidate(
            candidates,
            _score_machine_process,
            self.rng,
        )
        if best_candidate is None:
            return None
        return best_candidate[1]

    def decide(self, system_status: SystemObservation) -> tuple[DispatchCommand, ...]:
        self._current_system_status = system_status
        commands: list[DispatchCommand] = []

        for robot in system_status.main_robots:
            if robot.busy or robot.pending_commands > 0:
                continue
            pick_candidate = self.decide_main_robot_pick(robot)
            if pick_candidate is None:
                continue
            pick_action, selected_job = pick_candidate

            source_queue = self.main_robot_pick_source_queue(robot, pick_action)

            place_action = self.decide_main_robot_place(robot, selected_job, source_queue)
            commands.append(
                DispatchCommand(
                    actor_id=robot.actor_id,
                    payload=MainRobotCommand(
                        job_key=selected_job.job_key,
                        pick=pick_action,
                        place=place_action,
                    ),
                )
            )

        for robot in system_status.arm_robots:
            if robot.busy or robot.pending_commands > 0:
                continue
            pick_candidate = self.decide_arm_robot_pick(robot)
            if pick_candidate is None:
                continue
            pick_action, selected_job = pick_candidate

            source_queue = self.arm_robot_pick_source_queue(robot, pick_action)

            place_action = self.decide_arm_robot_place(robot, selected_job, source_queue)
            commands.append(
                DispatchCommand(
                    actor_id=robot.actor_id,
                    payload=ArmRobotCommand(
                        job_key=selected_job.job_key,
                        pick=pick_action,
                        place=place_action,
                    ),
                )
            )

        for machine in system_status.machines:
            if machine.busy or machine.pending_commands > 0:
                continue
            if len(machine.input_queue.jobs) == 0:
                continue
            machine_command = self.decide_machine_process(machine)
            if machine_command is None:
                continue
            commands.append(
                DispatchCommand(
                    actor_id=machine.actor_id,
                    payload=machine_command,
                )
            )

        result = tuple(commands)
        self._current_system_status = None
        return result
