import hashlib
import random
import salabim as sim
import matplotlib.pyplot as plt
import salabim as sim

from ..Configuration import Machine, ToolType
from ..Control import SimulationBridge

from .SimOrderJob import SimOrderJob


class SimMachine(sim.Component):
    QUALITY_SEED = 0
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        machine: Machine,
        bridge: SimulationBridge,
        x: float,
        y: float,
        *args,
        max_product_weight: float = 1.0,
        max_product_volume: float = 1.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.machine = machine
        self.max_product_weight = max(float(max_product_weight), 1.0)
        self.max_product_volume = max(float(max_product_volume), 1.0)
        self.machine.processing_speed_factor = random.uniform(0.45, 2.00)
        self.bridge = bridge
        machine_side = "left" if self.machine.left else "right"
        self.policy_id = f"SimMachine:{self.machine.name}:{machine_side}"

        self.state = sim.State("State", value='waiting', env=self.env)

        self.tool_type: ToolType | None = None
        self.dummy_tool_mounted = True
        self.processing_speed_factor = machine.processing_speed_factor
        self.processing_variation = random.uniform(0.90, 1.10)
        self.startup_delay = random.uniform(0.0, 4.0)
        self._startup_delay_applied = False

        self.tool_types = list(machine.tool_types)

        self.remaining_life_units: dict[ToolType, int] = {}
        self.remaining_life_units_t: dict[ToolType, float] = {}
        self.remaining_life_units_next: dict[ToolType, int] = {}
        self.remaining_life_units_next_t: dict[ToolType, float] = {}
        for tool_type in self.tool_types:
            self.remaining_life_units[tool_type] = tool_type.total_life_units
            self.remaining_life_units_t[tool_type] = self.env.now()
            self.remaining_life_units_next[tool_type] = tool_type.total_life_units
            self.remaining_life_units_next_t[tool_type] = self.env.now()

        self.store_in = sim.Store(
            f"{machine.name} in", env=self.env, capacity=machine.input_storage_capacity
        )
        self.store_out = sim.Store(
            f"{machine.name} out", env=self.env, capacity=machine.output_storage_capacity
        )
        self.current_job: SimOrderJob | None = None

        self.bridge.register(
            self.policy_id,
            self,
            stores=[self.store_in, self.store_out],
        )

        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.20, color="green", x=x, y=y + 0.00, z=1.80)

        sim.Animate3dBox(x_len=0.05, y_len=0.18, z_len=0.05, color="white", x=x, y=y + 0.19, z=1.18)
        sim.Animate3dBox(x_len=0.60, y_len=0.18, z_len=0.05, color="white", x=x, y=y + 0.19, z=1.18)

        m = 0
        for tool_type in self.tool_types:
            sim.Animate3dBox(x_len=0.05, y_len=0.05, z_len=0.18, color="blue", x=x + m, y=y + 0.25, z=1.10)
            m = m + 0.1

        z = 0.70
        for tool_type in self.tool_types:
            x_len = self.create_tool_life_bar_length_function(tool_type)
            color = self.create_tool_life_bar_color_function(tool_type)
            sim.Animate3dBox(x_len=x_len, y_len=0.01, z_len=0.07, color=color, x=x, y=y + 0.4379, z=z)
            z = z - 0.08
        
        sim.Animate3dBox(x_len=0.60, y_len=0.40, z_len=0.40, color="lightgray", x=x, y=y - 0.08, z=1.00)
        sim.Animate3dBox(x_len=0.60, y_len=0.70, z_len=0.60, color="lightgray", x=x, y=y + 0.08, z=0.50)

    # Erstellt das angeforderte Modell, Objekt oder Ergebnis.
    def create_tool_life_bar_length_function(self, tool_type: ToolType):
        """Create the time-dependent bar-length function required by Salabim."""

        # Führt die Funktion mit den übergebenen Werten aus.
        def tool_life_bar_length(animation_time: float):
            rtlu = self.remaining_life_units[tool_type]
            rtlu_t = self.remaining_life_units_t[tool_type]
            rtlu_next = self.remaining_life_units_next[tool_type]
            rtlu_next_t = self.remaining_life_units_next_t[tool_type]
            if rtlu_next_t == rtlu_t:
                return rtlu / tool_type.total_life_units * 0.4
            return (
                rtlu
                + (rtlu_next - rtlu)
                * (animation_time - rtlu_t)
                / (rtlu_next_t - rtlu_t)
            ) / tool_type.total_life_units * 0.4

        return tool_life_bar_length
    # Erstellt das angeforderte Modell, Objekt oder Ergebnis.
    def create_tool_life_bar_color_function(self, tool_type: ToolType):
        """Create the time-compatible bar-color function required by Salabim."""

        # Führt die Funktion mit den übergebenen Werten aus.
        def tool_life_bar_color(animation_time: float):
            if tool_type != self.tool_type:
                return "gray"
            if self.state.get() == "unmounting":
                return "orange"
            if self.state.get() == "mounting":
                return "yellow"
            if self.state.get() == "working":
                return "red"
            return "green"

        return tool_life_bar_color

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self):
        if self.controller is None:
            raise RuntimeError("SimMachine requires a controller for dispatched commands")

        while True:
            if self.store_out.available_quantity() <= 0:
                self.state.set("blocked")
            else:
                self.state.set("waiting")
            yield self.bridge.request_action(self)
            action = yield self.bridge.action(self)

            if action.action_type == "pick_machine_job":
                yield from self.execute_pick_action(action)
            elif action.action_type == "process_machine_job":
                yield from self.execute_process_action(action)
            elif action.action_type == "wait_machine":
                yield self.hold(1.0)

    # Führt die angeforderte Bewegung oder Aktion aus.
    def execute_pick_action(self, action):
        target_store = action.payload["target_store"]
        selected_job = action.payload["selected_job"]
        current_items = target_store.as_list()
        if selected_job not in current_items:
            return None

        # Prüft die angegebene Bedingung.
        def is_selected_job(item):
            if item is selected_job:
                return True
            return False

        job = yield self.from_store(
            target_store,
            filter=is_selected_job,
        )
        job.location = f"{self.machine.name}:loaded"
        job.queue_priority = action.payload["queue_priority"]
        self.current_job = job

    # Führt die angeforderte Bewegung oder Aktion aus.
    def execute_process_action(self, action):
        job = self.current_job
        if not self._startup_delay_applied and self.startup_delay > 0:
            self.state.set("waiting")
            yield self.hold(self.startup_delay)
            self._startup_delay_applied = True
        operation = action.payload["operation"]
        tool_type = action.payload["tool_type"]

        total_life_units = action.payload["total_life_units"]

        consumed_life_units = action.payload["consumed_life_units"]

        remaining_life_units_before_operation = action.payload[
            "remaining_life_units_before_operation"
        ]
        self.processing_speed_factor = self.machine.processing_speed_factor

        tool_setup_action = action.payload["tool_setup_action"]
        if tool_setup_action == "unmount_dummy_tool_and_mount_tool":
            self.state.set("unmounting")
            yield self.hold(self.machine.dummy_tool_unmount_time)
            self.dummy_tool_mounted = False

        if tool_setup_action in ["unmount_and_mount_tool", "replace_tool_same_type"] and self.tool_type is not None:
            self.state.set("unmounting")
            yield self.hold(self.tool_type.unmount_time)

        if tool_setup_action in ["unmount_dummy_tool_and_mount_tool", "unmount_and_mount_tool", "replace_tool_same_type"]:
            self.state.set("mounting")
            self.tool_type = tool_type
            yield self.hold(self.tool_type.mount_time)
            if remaining_life_units_before_operation < consumed_life_units:
                remaining_life_units_before_operation = total_life_units

        product = job.order.product_type
        volume = product.length * product.width * product.depth
        weight_ratio = float(product.weight) / self.max_product_weight
        volume_ratio = float(volume) / self.max_product_volume
        size_factor = 1.0 + 0.5 * weight_ratio + 0.5 * volume_ratio
        duration = operation.duration * size_factor / self.processing_speed_factor
        duration *= self.processing_variation

        self.remaining_life_units[tool_type] = remaining_life_units_before_operation
        self.remaining_life_units_t[tool_type] = self.env.now()
        self.remaining_life_units_next[tool_type] = (
            remaining_life_units_before_operation - consumed_life_units
        )
        self.remaining_life_units_next_t[tool_type] = self.env.now() + duration

        self.state.set("working")
        yield self.hold(duration)

        self.state.set("returning")

        defekt_schwergrad = None

        quality_key = (
            f"{self.QUALITY_SEED}|{job.scenario.name}|{job.order.name}|"
            f"{job.number}|{operation.name}|{job.nacharbeit_count}"
        ).encode("utf-8")

        quality_rng = random.Random(
            int.from_bytes(hashlib.sha256(quality_key).digest()[:8], "big")
        )

        if quality_rng.random() < operation.defect_probability:
         
            defekt_schwergrad = quality_rng.random()

        if defekt_schwergrad is not None and defekt_schwergrad >= 0.001:
            job.mark_defective(
                operation=operation,
                machine=self.machine,
                product_state_before=operation.consumes_product_type.name,
                product_state_target=operation.produces_product_type.name,
                defekt_schwergrad=defekt_schwergrad,
            )
        else:
            job.bearbeitungs_state.set(operation.produces_product_type.name)
            job.general_state.set("intakt")
            if job.defect_recovery_strategy in {
                "nacharbeiten_auf_defektmaschine",
                "nacharbeiten_auf_alternativer_maschine",
            }:
                job.defect_recovery_strategy = None

        # Die Recovery-Strategie ist nach dieser Bearbeitung abgeschlossen.
        if job.recovery_in_progress:
            job.recovery_in_progress = False

        job.selected_operation = None
        job.selected_machine = None

        self.remaining_life_units[tool_type] = (
            remaining_life_units_before_operation - consumed_life_units
        )
        self.remaining_life_units_t[tool_type] = self.env.now()
        self.remaining_life_units_next[tool_type] = (
            remaining_life_units_before_operation - consumed_life_units
        )
        self.remaining_life_units_next_t[tool_type] = self.env.now()

        yield self.to_store(action.payload["target_store"], job, priority=job.queue_priority)
        job.location = action.payload["target_store"].name()
        yield self.bridge.notify_state_change(self)

        self.current_job = None

    # Führt die Funktion mit den übergebenen Werten aus.
    def utilization(self):
        waiting = self.state.value.value_duration("waiting")
        mounting = self.state.value.value_duration("mounting")
        unmounting = self.state.value.value_duration("unmounting")
        working = self.state.value.value_duration("working")
        returning = self.state.value.value_duration("returning")

        total = waiting + mounting + unmounting + working + returning
        if total > 0:
            return working / total
        else:
            return 1
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        pass
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def plot(self, legend = False):
        categories = ['Waiting', 'Mounting', 'Unmounting', 'Working', 'Returning']

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

        plt.xlabel('Machine State')
        plt.ylabel('State Duration')
        plt.title(self.machine.name)

        if legend:
            plt.legend()


class SimMachineShutdown(sim.Component):
    """Run the end-of-simulation dummy-tool setup for one SimMachine."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, machine: SimMachine, *args, **kwargs):
        self.machine = machine
        super().__init__(*args, **kwargs)

    # Führt den Prozess dieser Simulationskomponente aus.
    def process(self):
        if self.machine.dummy_tool_mounted:
            return

        if self.machine.tool_type is not None:
            self.machine.state.set("unmounting")
            yield self.hold(self.machine.tool_type.unmount_time)
            self.machine.tool_type = None

        self.machine.state.set("mounting")
        yield self.hold(self.machine.machine.dummy_tool_mount_time)
        self.machine.dummy_tool_mounted = True
        self.machine.state.set("waiting")
