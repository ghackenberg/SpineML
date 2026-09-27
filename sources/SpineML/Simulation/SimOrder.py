import salabim as sim
import matplotlib.pyplot as plt

from ..Configuration import Layout, Scenario, Order
from ..Control import SimulationBridge

from .SimOrderJob import SimOrderJob

class SimOrder(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, layout: Layout, scenario: Scenario, order: Order, store_start: sim.Store, bridge: SimulationBridge, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.order = order
        self.bridge = bridge
        
        self.sim_jobs: list[SimOrderJob] = []
        for i in range(order.quantity):
            sim_job = SimOrderJob(layout, scenario, order, i, store_start, bridge, env=self.env)
            self.sim_jobs.append(sim_job)

    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        for sim_job in self.sim_jobs:
            sim_job.printStatistics()
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def plot(self, legend=True):
        categories = []
        for job in self.sim_jobs:
            for value in job.bearbeitungs_state.value.values():
                if value not in categories:
                    categories.append(value)
        
        values = [0 for c in categories]
        for job in self.sim_jobs:
            for value in job.bearbeitungs_state.value.values():
                duration = job.bearbeitungs_state.value.value_duration(value)
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

