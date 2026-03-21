import salabim as sim
import matplotlib.pyplot as plt
from typing import TYPE_CHECKING, Optional

from ..Configuration import Layout, Scenario, Order
from .SimOrderJob import SimOrderJob

if TYPE_CHECKING:
    from ..controller import PolicyController


class SimOrder(sim.Component):
    def __init__(
        self,
        layout: Layout,
        scenario: Scenario,
        order: Order,
        store_start: sim.Store,
        controller: Optional["PolicyController"] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.order = order
        self.controller = controller

        self.sim_jobs: list[SimOrderJob] = []
        for i in range(order.quantity):
            sim_job = SimOrderJob(layout, scenario, order, i, store_start, controller=self.controller, env=self.env)
            self.sim_jobs.append(sim_job)

    def printStatistics(self):
        print(f" - {self.order.name}:")
        for sim_job in self.sim_jobs:
            sim_job.printStatistics()

    def plot(self, legend=True):
        categories = []
        for job in self.sim_jobs:
            for value in job.state.value.values():
                if value not in categories:
                    categories.append(value)

        values = [0 for _ in categories]
        for job in self.sim_jobs:
            for value in job.state.value.values():
                duration = job.state.value.value_duration(value)
                index = categories.index(value)
                values[index] = values[index] + duration

        bar_width = 0.15

        for i in range(len(categories)):
            plt.bar(i * bar_width, values[i], width=bar_width, label=categories[i])

        plt.xticks([])
        plt.xlabel('Order State')
        plt.ylabel('State Duration')
        plt.title(f'{self.order.name}')

        if legend:
            plt.legend()

