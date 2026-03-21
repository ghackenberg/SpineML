from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import salabim as sim

from ..Configuration import Layout, Order, Scenario
from ..controller.types import JobKey, JobPlanningRequest
from ..util import toString

if TYPE_CHECKING:
    from ..controller import PolicyController


class SimOrderJob(sim.Component):
    def __init__(
        self,
        layout: Layout,
        scenario: Scenario,
        order: Order,
        number: int,
        store_start: sim.Store,
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

    def process(self):
        yield self.to_store(self.store_start, self)

    def printStatistics(self):
        output = toString(self.state)
        print(f"    - Job {self.number} ({output})")
