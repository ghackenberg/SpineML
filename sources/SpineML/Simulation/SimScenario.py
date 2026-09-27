import salabim as sim
import matplotlib.pyplot as plt
from typing import TYPE_CHECKING, Optional

from ..Configuration import Layout, Scenario
from ..Control import SimulationBridge

from .SimOrder import SimOrder


class SimCompletionWatcher(sim.Component):
    """Beendet den Simulationslauf, sobald alle Jobs abgeschlossen sind."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, sim_orders, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sim_orders = sim_orders
        self.jobs = []
        for order in self.sim_orders:
            for job in order.sim_jobs:
                self.jobs.append(job)

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self):
        while True:
            all_jobs_finished = True
            for job in self.jobs:
                if not job.process_finished:
                    all_jobs_finished = False
                    break

            if len(self.jobs) > 0 and all_jobs_finished:
                raise sim.SimulationStopped
            yield self.hold(1.0)

class SimScenario(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, layout: Layout, scenario: Scenario, store_start: sim.Store, bridge: SimulationBridge, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.scenario = scenario
        self.bridge = bridge
        
        self.sim_orders: list[SimOrder] = []
        for order in scenario.orders:
            sim_order = SimOrder(layout, scenario, order, store_start, bridge, env=self.env)
            self.sim_orders.append(sim_order)
        self.completion_watcher = SimCompletionWatcher(self.sim_orders, env=self.env)
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        for sim_order in self.sim_orders:
            sim_order.printStatistics()
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def plot(self, legend = True):
        rows = 1
        columns = len(self.sim_orders)

        plt.figure(self.scenario.name)

        col = 1
        for sim_order in self.sim_orders:
            plt.subplot(rows, columns, col)
            sim_order.plot(legend)
            col = col + 1

