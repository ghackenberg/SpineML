from __future__ import annotations

from abc import ABC, abstractmethod

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
    SystemObservation,
)


class RoutingPolicy(ABC):
    @abstractmethod
    def plan_job(self, request: JobPlanningRequest) -> JobPlan:
        raise NotImplementedError


class DispatchPolicy(ABC):
    @abstractmethod
    def decide(self, system_status: SystemObservation) -> tuple[DispatchCommand, ...]:
        raise NotImplementedError


class RuleBasedDispatchPolicy(DispatchPolicy, ABC):
    @abstractmethod
    def decide_main_robot_pick(self, robot: MainRobotObservation) -> MainRobotPickAction | None:
        raise NotImplementedError

    @abstractmethod
    def decide_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
    ) -> MainRobotPlaceAction:
        raise NotImplementedError

    @abstractmethod
    def decide_arm_robot_pick(self, robot: ArmRobotObservation) -> ArmRobotPickAction | None:
        raise NotImplementedError

    @abstractmethod
    def decide_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
    ) -> ArmRobotPlaceAction:
        raise NotImplementedError

    @abstractmethod
    def decide_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
    ) -> MachineCommand | None:
        raise NotImplementedError

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

    def decide(self, system_status: SystemObservation) -> tuple[DispatchCommand, ...]:
        commands: list[DispatchCommand] = []

        for robot in system_status.main_robots:
            if robot.busy or robot.pending_commands > 0:
                continue
            pick_action = self.decide_main_robot_pick(robot)
            if pick_action is None:
                continue

            if pick_action.kind == "start":
                source_queue = robot.start_queue
            else:
                source_queue = self._corridor_by_name(robot.corridors, pick_action.corridor_name).main_queue

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

            if pick_action.kind == "store_in":
                source_queue = robot.input_queue
            else:
                source_queue = self._machine_slot_by_num(robot.machine_slots, pick_action.machine_num).output_queue

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
