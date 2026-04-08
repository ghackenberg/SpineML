from __future__ import annotations

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
)

if TYPE_CHECKING:
    from ..Configuration import Order


class DefaultRoutingPolicy(ScoredRoutingPolicy):
    def score_operation_sequence(self, order: Order, operation_sequence: list[Any]) -> float | None:
        return self.rng.random()

    def score_machine_sequence(
        self,
        request: JobPlanningRequest,
        operation_sequence: list[Any],
        machine_sequence: list[Any],
    ) -> float | None:
        return self.rng.random()


class DefaultDispatchPolicy(RuleBasedDispatchPolicy):
    def score_main_robot_pick(
        self,
        robot: MainRobotObservation,
        action: MainRobotPickAction,
        source_queue: QueueObject,
        job: JobHeadObservation,
    ) -> float | None:
        if self.best_main_robot_place_score(robot, job, source_queue) is None:
            return None

        return self.rng.random()

    def score_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
        source_queue: QueueObject,
        job: JobHeadObservation,
    ) -> float | None:
        if self.best_arm_robot_place_score(robot, job, source_queue) is None:
            return None

        return self.rng.random()

    def score_main_robot_place(
        self,
        robot: MainRobotObservation,
        job: JobHeadObservation,
        action: MainRobotPlaceAction,
        target_queue: QueueObject,
    ) -> float | None:
        if target_queue.free_capacity <= 0:
            return None
        return self.rng.random()

    def score_arm_robot_place(
        self,
        robot: ArmRobotObservation,
        job: JobHeadObservation,
        action: ArmRobotPlaceAction,
        target_queue: QueueObject,
    ) -> float | None:
        if target_queue.free_capacity <= 0:
            return None
        return self.rng.random()

    def score_machine_process(
        self,
        machine: MachineObservation,
        job: JobHeadObservation,
        command: MachineCommand,
    ) -> float | None:
        if job.is_defective:
            return None
        return self.rng.random()


class DefaultController(SimulationBridge):
    def __init__(
        self,

        rng_seed: int | None = None,
        *args,
        **kwargs,
    ):
        rng = random.Random(rng_seed)
        routing_policy = DefaultRoutingPolicy(rng=rng)
        super().__init__(
            routing_policy=routing_policy,
            dispatch_policy=DefaultDispatchPolicy(rng=rng, routing_policy=routing_policy),
            *args,
            **kwargs,
        )
