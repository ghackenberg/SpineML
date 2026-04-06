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
        self.store_start = store_start
        self.controller = controller
        self.completion_time: float | None = None
        self.lateness: float | None = None
        self.tardiness: float = 0.0
        self._completed_job_numbers: set[int] = set()
        self.defective_job_count = 0

        self.sim_jobs: list[SimOrderJob] = []
        for i in range(order.quantity):
            sim_job = SimOrderJob(
                layout,
                scenario,
                order,
                i,
                store_start,
                sim_order=self,
                controller=self.controller,
                env=self.env,
            )
            self.sim_jobs.append(sim_job)

    def process(self):
        release_delay = max(0, self.order.earliest_start_time - self.env.now())
        if release_delay > 0:
            yield self.hold(release_delay)
        for sim_job in self.sim_jobs:
            sim_job.release()

    def mark_job_completed(self, sim_job: SimOrderJob) -> None:
        if sim_job.number in self._completed_job_numbers:
            return
        sim_job.mark_completed()
        self._completed_job_numbers.add(sim_job.number)
        if sim_job.is_defective:
            self.defective_job_count += 1

        if len(self._completed_job_numbers) == len(self.sim_jobs):
            self.completion_time = max(
                job.completion_time for job in self.sim_jobs if job.completion_time is not None
            )
            self.lateness = self.completion_time - self.order.latest_end_time
            self.tardiness = max(0.0, self.lateness)

    def printStatistics(self):
        if self.completion_time is None:
            completion_output = "not completed"
            tardiness_output = "-"
        else:
            completion_output = f"{self.completion_time:.3f}"
            tardiness_output = f"{self.tardiness:.3f}"
        print(
            f" - {self.order.name} "
            f"(release={self.order.earliest_start_time:.3f}, due={self.order.latest_end_time:.3f}, "
            f"completion={completion_output}, tardiness={tardiness_output}, defects={self.defective_job_count}):"
        )
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
