from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import salabim as sim

from ..Configuration import Layout, Order, ProductType, Scenario
from ..controller.types import JobKey, JobPlanningRequest
from ..util import toString

if TYPE_CHECKING:
    from ..controller.simulation_bridge import SimulationBridge
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
        controller: Optional[SimulationBridge] = None,
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

        self.operation_sequence: list = []
        self.machine_sequence: list = []
        self.current_product_type: ProductType = self._infer_initial_product_type()
        self.current_queue_entry_time = self.env.now()
        self.queue_wait_active = False
        self.total_queue_wait_time = 0.0
        self.queue_wait_events = 0
        self.max_queue_wait_time = 0.0
        self.completion_time: float | None = None
        self.is_defective = False
        self.defect_time: float | None = None
        self.defect_operation_name: str | None = None
        self.released = sim_order is None

        value = self.current_product_type.name
        self.state = sim.State("State", value=value, env=self.env)

    def _planning_request(self, *, current_product_type: ProductType | None) -> JobPlanningRequest:
        return JobPlanningRequest(
            job_key=JobKey(
                scenario_name=self.scenario.name,
                order_name=self.order.name,
                job_number=self.number,
            ),
            layout=self.layout,
            order=self.order,
            current_product_type=current_product_type,
        )

    def _infer_initial_product_type(self) -> ProductType:
        candidates = self.controller.plan_job_candidates(
            self._planning_request(current_product_type=None),
        )
        initial_products = {
            route.operation_sequence[0].consumes_product_type
            for route in candidates
            if len(route.operation_sequence) > 0
        }
        if len(initial_products) == 0:
            return self.order.product_type
        if len(initial_products) > 1:
            product_names = ", ".join(sorted(product_type.name for product_type in initial_products))
            raise ValueError(
                f"Job {self.order.name}/{self.number} has multiple possible initial products: {product_names}"
            )
        return next(iter(initial_products))

    def apply_route(
        self,
        operation_sequence: list,
        machine_sequence: list,
        *,
        allow_initial_reset: bool = False,
    ) -> None:
        self.operation_sequence = list(operation_sequence)
        self.machine_sequence = list(machine_sequence)

        if len(self.operation_sequence) == 0:
            return

        first_input_product = self.operation_sequence[0].consumes_product_type
        if first_input_product != self.current_product_type and not (
            allow_initial_reset and self.current_product_type == self.order.product_type
        ):
            raise ValueError(
                f"Applied route for job {self.order.name}/{self.number} does not match current product "
                f"{self.current_product_type.name}; got {first_input_product.name}"
            )
        self.current_product_type = first_input_product

    def replan_route(self, *, initial: bool = False) -> None:
        plan_request = self._planning_request(
            current_product_type=None if initial else self.current_product_type,
        )
        plan = self.controller.plan_job(plan_request)
        self.apply_route(
            plan.operation_sequence,
            plan.machine_sequence,
            allow_initial_reset=initial,
        )

    def clear_route(self) -> None:
        self.operation_sequence.clear()
        self.machine_sequence.clear()

    def mark_queue_entry(self) -> None:
        self.current_queue_entry_time = self.env.now()
        self.queue_wait_active = True

    def mark_queue_exit(self) -> None:
        if not self.queue_wait_active:
            return
        wait_time = max(0.0, self.env.now() - self.current_queue_entry_time)
        self.total_queue_wait_time += wait_time
        self.queue_wait_events += 1
        if wait_time > self.max_queue_wait_time:
            self.max_queue_wait_time = wait_time
        self.queue_wait_active = False

    def mark_completed(self) -> None:
        if self.completion_time is not None:
            return
        self.queue_wait_active = False
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
        self.mark_queue_entry()
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
