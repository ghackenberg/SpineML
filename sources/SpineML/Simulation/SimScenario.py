import salabim as sim
import matplotlib.pyplot as plt
from typing import TYPE_CHECKING, Optional

from ..Configuration import Layout, Scenario
from .SimOrder import SimOrder

if TYPE_CHECKING:
    from ..controller import PolicyController


class SimScenario(sim.Component):
    def __init__(
        self,
        layout: Layout,
        scenario: Scenario,
        store_start: sim.Store,
        controller: Optional["PolicyController"] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.scenario = scenario
        self.controller = controller

        self.sim_orders: list[SimOrder] = []
        for order in scenario.orders:
            sim_order = SimOrder(layout, scenario, order, store_start, controller=self.controller, env=self.env)
            self.sim_orders.append(sim_order)

    def printStatistics(self):
        print(f"{self.scenario.name}:")
        for sim_order in self.sim_orders:
            sim_order.printStatistics()

    def plot(self, legend=True):
        rows = 1
        columns = len(self.sim_orders)

        plt.figure(self.scenario.name)

        col = 1
        for sim_order in self.sim_orders:
            plt.subplot(rows, columns, col)
            sim_order.plot(legend)
            col = col + 1

