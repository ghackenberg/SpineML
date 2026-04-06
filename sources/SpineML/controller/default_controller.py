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
    JobPlanningRequest,
    MainRobotObservation,
    MainRobotPickAction,
    QueueObservation,
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
        source_queue: QueueObservation,
    ) -> float | None:
        return self.rng.random()

    def score_arm_robot_pick(
        self,
        robot: ArmRobotObservation,
        action: ArmRobotPickAction,
        source_queue: QueueObservation,
    ) -> float | None:
        return self.rng.random()


class DefaultController(PolicyController):
    def __init__(
        self,
        routing_policy: RoutingPolicy | None = None,
        dispatch_policy: DispatchPolicy | None = None,
        rng_seed: int | None = None,
        *args,
        **kwargs,
    ):
        rng = random.Random(rng_seed)
        super().__init__(
            routing_policy=routing_policy or DefaultRoutingPolicy(rng=rng),
            dispatch_policy=dispatch_policy or DefaultDispatchPolicy(rng=rng),
            *args,
            **kwargs,
        )
