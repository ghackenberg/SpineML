from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import salabim as sim

from ..Configuration import Layout, Order, ProductType, Scenario
from ..controller.types import JobKey, JobPlanningRequest
from ..util import toString

if TYPE_CHECKING:
    from ..controller import PolicyController
    from .SimOrder import SimOrder


class SimOrderJob(sim.Component):
    def __init__(
        self,
        layout: Layout,
        scenario: Scenario,
        order: Order,
        number: int,
        store_start: sim.Store,
        sim_order: Optional[SimOrder] = None,
        controller: Optional[PolicyController] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.layout = layout
        self.scenario = scenario
        self.order = order
        self.number = number
        self.store_start = store_start
        self.sim_order = sim_order
        self.controller = controller

        if self.controller is None:
            raise ValueError("Controller is required for SimOrderJob planning")

        plan_request = JobPlanningRequest(
            job_key=JobKey(
                scenario_name=self.scenario.name,
                order_name=self.order.name,
                job_number=self.number,
            ),
            layout=self.layout,
            order=self.order,
        )
        plan = self.controller.plan_job(plan_request)
        self.operation_sequence = plan.operation_sequence
        self.machine_sequence = plan.machine_sequence

        value = self.operation_sequence[0].consumes_product_type.name
        self.state = sim.State("State", value=value, env=self.env)
        self.current_product_type: ProductType = self.operation_sequence[0].consumes_product_type
        self.completion_time: float | None = None
        self.is_defective = False
        self.defect_time: float | None = None
        self.defect_operation_name: str | None = None
        self.released = sim_order is None

    def mark_completed(self) -> None:
        if self.completion_time is not None:
            return
        self.completion_time = self.env.now()

    def mark_defective(self, defective_product_name: str, operation_name: str) -> None:
        self.is_defective = True
        if self.defect_time is None:
            self.defect_time = self.env.now()
        self.defect_operation_name = operation_name
        self.state.set(f"{defective_product_name} defective")
        self.operation_sequence.clear()
        self.machine_sequence.clear()

    def release(self) -> None:
        self.released = True
        self.activate()

    def process(self):
        while not self.released:
            yield self.passivate()
        yield self.to_store(self.store_start, self)

    def printStatistics(self):
        output = toString(self.state)
        completion_output = "not completed" if self.completion_time is None else f"{self.completion_time:.3f}"
        if self.is_defective:
            defect_output = (
                f", defective_at={self.defect_time:.3f}, defect_operation={self.defect_operation_name}"
            )
        else:
            defect_output = ""
        print(f"    - Job {self.number} ({output}, completion={completion_output}{defect_output})")
