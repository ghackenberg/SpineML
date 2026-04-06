from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from .calculate import (
    calculateMachineSequencesFromOperationSequence,
    calculateOperationSequences,
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
    QueueObservation,
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

    def plan_job(self, request: JobPlanningRequest) -> JobPlan:
        order = request.order
        layout = request.layout

        operation_sequences = calculateOperationSequences(order.product_type)
        if len(operation_sequences) == 0:
            raise ValueError(f"No operation sequence found for order {order.name}")
        operation_sequence = self.choose_operation_sequence(order, operation_sequences)

        machine_sequences = calculateMachineSequencesFromOperationSequence(list(operation_sequence), layout)
        if len(machine_sequences) == 0:
            raise ValueError(f"No machine sequence found for order {order.name} in layout {layout.name}")
        machine_sequence = self.choose_machine_sequence(request, operation_sequence, machine_sequences)

        return JobPlan(operation_sequence=operation_sequence, machine_sequence=machine_sequence)


class RuleBasedDispatchPolicy(DispatchPolicy, ABC):
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    @abstractmethod
    def score_main_robot_pick(
        self,
        robot: MainRobotObservation,
        action: MainRobotPickAction,
        source_queue: QueueObservation,
    ) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def score_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
        source_queue: QueueObservation,
    ) -> float | None:
        raise NotImplementedError

    def score_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        action: MainRobotPlaceAction,
        target_queue: QueueObservation,
    ) -> float | None:
        return 0.0

    def score_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        action: ArmRobotPlaceAction,
        target_queue: QueueObservation,
    ) -> float | None:
        return 0.0

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
    ) -> QueueObservation:
        if action.kind == "start":
            return robot.start_queue
        return self._corridor_by_name(robot.corridors, action.corridor_name).main_queue

    def decide_main_robot_pick(self, robot: MainRobotObservation) -> MainRobotPickAction | None:
        candidates = list(self.main_robot_pick_candidates(robot))

        def _score_main_robot_pick(action: MainRobotPickAction) -> float | None:
            return self.score_main_robot_pick(
                robot,
                action,
                self.main_robot_pick_source_queue(robot, action),
            )

        return _select_best_candidate(
            candidates,
            _score_main_robot_pick,
            self.rng,
        )

    def main_robot_place_candidates(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
    ) -> tuple[MainRobotPlaceAction, ...]:
        if job.next_machine_name is None or job.next_machine_corridor_name is None:
            return (MainRobotPlaceAction(kind="end"),)
        return (
            MainRobotPlaceAction(
                kind="corridor_in",
                corridor_name=job.next_machine_corridor_name,
                side=job.next_machine_side,
            ),
        )

    def main_robot_place_target_queue(
        self,
        robot: MainRobotObservation,
        action: MainRobotPlaceAction,
    ) -> QueueObservation:
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
    ) -> MainRobotPlaceAction:
        candidates = list(self.main_robot_place_candidates(robot, job))

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
    ) -> QueueObservation:
        if action.kind == "store_in":
            return robot.input_queue
        return self._machine_slot_by_num(robot.machine_slots, action.machine_num).output_queue

    def decide_arm_robot_pick(self, robot: ArmRobotObservation) -> ArmRobotPickAction | None:
        candidates = list(self.arm_robot_pick_candidates(robot))

        def _score_arm_robot_pick(action: ArmRobotPickAction) -> float | None:
            return self.score_arm_robot_pick(
                robot,
                action,
                self.arm_robot_pick_source_queue(robot, action),
            )

        return _select_best_candidate(
            candidates,
            _score_arm_robot_pick,
            self.rng,
        )

    def arm_robot_place_candidates(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
    ) -> tuple[ArmRobotPlaceAction, ...]:
        if job.next_machine_name is not None and job.next_machine_corridor_name == robot.corridor_name:
            candidates: list[ArmRobotPlaceAction] = []
            for machine_slot in robot.machine_slots:
                if machine_slot.machine_name == job.next_machine_name:
                    candidates.append(
                        ArmRobotPlaceAction(kind="machine_in", machine_num=machine_slot.machine_num)
                    )
            if len(candidates) == 0:
                candidates.append(ArmRobotPlaceAction(kind="arm_out"))
            return tuple(candidates)

        return (ArmRobotPlaceAction(kind="main_out"),)

    def arm_robot_place_target_queue(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPlaceAction,
    ) -> QueueObservation:
        if action.kind == "machine_in":
            return self._machine_slot_by_num(robot.machine_slots, action.machine_num).input_queue
        if action.kind == "arm_out":
            return robot.out_arm_queue
        return robot.out_main_queue

    def decide_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
    ) -> ArmRobotPlaceAction:
        candidates = list(self.arm_robot_place_candidates(robot, job))

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
        job: JobHeadObservation,
    ) -> tuple[MachineCommand, ...]:
        return (self.build_machine_command(machine, job),)

    def decide_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
    ) -> MachineCommand | None:
        candidates = list(self.machine_process_candidates(machine, job))

        def _score_machine_process(command: MachineCommand) -> float | None:
            return self.score_machine_process(machine, job, command)

        return _select_best_candidate(
            candidates,
            _score_machine_process,
            self.rng,
        )

    def decide(self, system_status: SystemObservation) -> tuple[DispatchCommand, ...]:
        commands: list[DispatchCommand] = []

        for robot in system_status.main_robots:
            if robot.busy or robot.pending_commands > 0:
                continue
            pick_action = self.decide_main_robot_pick(robot)
            if pick_action is None:
                continue

            source_queue = self.main_robot_pick_source_queue(robot, pick_action)
            head = source_queue.head
            if head is None:
                continue

            place_action = self.decide_main_robot_place(robot, head)
            commands.append(
                DispatchCommand(
                    actor_id=robot.actor_id,
                    payload=MainRobotCommand(
                        job_key=head.job_key,
                        pick=pick_action,
                        place=place_action,
                    ),
                )
            )

        for robot in system_status.arm_robots:
            if robot.busy or robot.pending_commands > 0:
                continue
            pick_action = self.decide_arm_robot_pick(robot)
            if pick_action is None:
                continue

            source_queue = self.arm_robot_pick_source_queue(robot, pick_action)
            head = source_queue.head
            if head is None:
                continue

            place_action = self.decide_arm_robot_place(robot, head)
            commands.append(
                DispatchCommand(
                    actor_id=robot.actor_id,
                    payload=ArmRobotCommand(
                        job_key=head.job_key,
                        pick=pick_action,
                        place=place_action,
                    ),
                )
            )

        for machine in system_status.machines:
            if machine.busy or machine.pending_commands > 0:
                continue
            head = machine.input_queue.head
            if head is None:
                continue
            machine_command = self.decide_machine_process(machine, head)
            if machine_command is None:
                continue
            commands.append(
                DispatchCommand(
                    actor_id=machine.actor_id,
                    payload=machine_command,
                )
            )

        return tuple(commands)
