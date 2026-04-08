from __future__ import annotations

import random

import matplotlib.pyplot as plt
import salabim as sim

from ..Configuration import Machine, ToolType
from ..controller.types import JobKey, MachineCommand
from .SimOrderJob import SimOrderJob


class SimMachine(sim.Component):
    def __init__(self, machine: Machine, x: float, y: float, controller=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.machine = machine
        self.controller = controller
        self.rng = random.Random()

        self.state = sim.State("State", value="waiting", env=self.env)
        self.tool_type: ToolType | None = None
        self.tool_types = machine.machine_type.computeToolTypes()
        self.tool_type_by_name = {tool_type.name: tool_type for tool_type in self.tool_types}

        self.remaining_life_units: dict[ToolType, int] = {}
        self.remaining_life_units_t: dict[ToolType, float] = {}
        self.remaining_life_units_next: dict[ToolType, int] = {}
        self.remaining_life_units_next_t: dict[ToolType, float] = {}

        for tool_type in self.tool_types:
            self.remaining_life_units[tool_type] = tool_type.total_life_units
            self.remaining_life_units_t[tool_type] = self.env.now()
            self.remaining_life_units_next[tool_type] = tool_type.total_life_units
            self.remaining_life_units_next_t[tool_type] = self.env.now()

        self.store_in = sim.Store(f"{machine.name} in", capacity=machine.storage_capacity, env=self.env)
        self.store_out = sim.Store(f"{machine.name} out", capacity=machine.storage_capacity, env=self.env)
        self.cmd_store = sim.Store(f"{machine.name} cmd", env=self.env)
        self.cmd_active = False
        self.tool_change_count = 0
        self.tool_change_time = 0.0

        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.20, color="green", x=x, y=y + 0.00, z=1.80)
        sim.Animate3dBox(x_len=0.05, y_len=0.18, z_len=0.05, color="white", x=x, y=y + 0.19, z=1.18)
        sim.Animate3dBox(x_len=0.60, y_len=0.18, z_len=0.05, color="white", x=x, y=y + 0.19, z=1.18)

        m = 0
        for tool_type in self.tool_types:
            sim.Animate3dBox(x_len=0.05, y_len=0.05, z_len=0.18, color="blue", x=x + m, y=y + 0.25, z=1.10)
            m = m + 0.1

        z = 0.70
        for tool_type in self.tool_types:
            x_len = (lambda tt: lambda t: self.x_func(tt, t))(tool_type)
            color = (lambda tt: lambda t: self.c_func(tt))(tool_type)
            sim.Animate3dBox(x_len=x_len, y_len=0.01, z_len=0.07, color=color, x=x, y=y + 0.4379, z=z)
            z = z - 0.08

        sim.Animate3dBox(x_len=0.60, y_len=0.40, z_len=0.40, color="white", x=x, y=y - 0.08, z=1.00)
        sim.Animate3dBox(x_len=0.60, y_len=0.70, z_len=0.60, color="white", x=x, y=y + 0.08, z=0.50)

    def x_func(self, tool_type: ToolType, t: float):
        rtlu = self.remaining_life_units[tool_type]
        rtlu_t = self.remaining_life_units_t[tool_type]
        rtlu_next = self.remaining_life_units_next[tool_type]
        rtlu_next_t = self.remaining_life_units_next_t[tool_type]
        if rtlu_next_t == rtlu_t:
            return rtlu / tool_type.total_life_units * 0.4
        return (
            rtlu + (rtlu_next - rtlu) * (t - rtlu_t) / (rtlu_next_t - rtlu_t)
        ) / tool_type.total_life_units * 0.4

    def c_func(self, tool_type: ToolType):
        rtlu_t = self.remaining_life_units_t[tool_type]
        rtlu_next_t = self.remaining_life_units_next_t[tool_type]
        if tool_type == self.tool_type:
            if rtlu_t == rtlu_next_t:
                if self.state.get() == "unmounting":
                    return "orange"
                if self.state.get() == "mounting":
                    return "yellow"
                return "green"
            return "red"
        return "gray"

    def _job_matches(self, job: SimOrderJob, job_key: JobKey) -> bool:
        return (
            job.scenario.name == job_key.scenario_name
            and job.order.name == job_key.order_name
            and job.number == job_key.job_number
        )

    def _take_job_from_input_store(self, job_key: JobKey) -> SimOrderJob:
        for queued_job in self.store_in:
            if self._job_matches(queued_job, job_key):
                self.store_in.remove(queued_job)
                return queued_job
        raise ValueError(
            f"Machine {self.machine.name} could not find selected job "
            f"{job_key.order_name}/{job_key.job_number} in input queue"
        )

    def process(self):
        if self.controller is None:
            raise RuntimeError("SimMachine requires a controller for dispatched commands")

        while True:
            cmd_component = yield self.from_store(self.cmd_store)
            cmd = cmd_component.payload
            if not isinstance(cmd, MachineCommand):
                raise ValueError(f"Unsupported machine command payload: {type(cmd).__name__}")

            self.cmd_active = True
            try:
                job = self._take_job_from_input_store(cmd.job_key)
                job.mark_queue_exit()

                next_machine = job.machine_sequence[0]
                if next_machine.name != cmd.expected_machine_name or self.machine.name != cmd.expected_machine_name:
                    raise ValueError(
                        f"Machine command mismatch: expected {cmd.expected_machine_name}, got {self.machine.name}"
                    )

                current_operation = job.operation_sequence[0]
                tool_type = self.tool_type_by_name[cmd.tool_name]
                job.machine_sequence.pop(0)
                job.operation_sequence.pop(0)

                if len(cmd.tool_actions) > 0:
                    self.tool_change_count += 1
                for tool_action in cmd.tool_actions:
                    self.state.set(tool_action.state)
                    self.tool_change_time += tool_action.duration
                    if tool_action.mount_tool_name is not None:
                        self.tool_type = self.tool_type_by_name[tool_action.mount_tool_name]
                    yield self.hold(tool_action.duration)

                self.state.set("working")
                self.remaining_life_units[tool_type] = cmd.remaining_life_units_before
                self.remaining_life_units_t[tool_type] = self.env.now()
                self.remaining_life_units_next[tool_type] = cmd.remaining_life_units_after
                self.remaining_life_units_next_t[tool_type] = self.env.now() + cmd.duration

                yield self.hold(cmd.duration)

                if self.rng.random() < current_operation.defect_probability:
                    job.current_product_type = current_operation.produces_product_type
                    job.mark_defective(cmd.produced_product_name, current_operation.name)
                else:
                    job.current_product_type = current_operation.produces_product_type
                    job.state.set(cmd.produced_product_name)
                    job.clear_route()

                self.remaining_life_units[tool_type] = cmd.remaining_life_units_after
                self.remaining_life_units_t[tool_type] = self.env.now()
                self.remaining_life_units_next[tool_type] = cmd.remaining_life_units_after
                self.remaining_life_units_next_t[tool_type] = self.env.now()

                job.mark_queue_entry()
                yield self.to_store(self.store_out, job)
                self.state.set("returning")
            finally:
                self.cmd_active = False

    def utilization(self):
        waiting = self.state.value.value_duration("waiting")
        mounting = self.state.value.value_duration("mounting")
        unmounting = self.state.value.value_duration("unmounting")
        working = self.state.value.value_duration("working")
        returning = self.state.value.value_duration("returning")

        total = waiting + mounting + unmounting + working + returning
        if total > 0:
            return working / total
        return 1

    def printStatistics(self):
        print(f"       - {self.machine.name} (utilization = {'{:.1f}'.format(self.utilization() * 100)}%)")

    def plot(self, legend=False):
        categories = ["Waiting", "Mounting", "Unmounting", "Working", "Returning"]

        waiting = self.state.value.value_duration("waiting")
        mounting = self.state.value.value_duration("mounting")
        unmounting = self.state.value.value_duration("unmounting")
        working = self.state.value.value_duration("working")
        returning = self.state.value.value_duration("returning")

        values = [waiting, mounting, unmounting, working, returning]
        bar_width = 0.15

        for i in range(len(categories)):
            plt.bar(i * bar_width, values[i], width=bar_width, label=categories[i])

        plt.xticks([])
        plt.xlabel("Machine State")
        plt.ylabel("State Duration")
        plt.title(self.machine.name)

        if legend:
            plt.legend()
