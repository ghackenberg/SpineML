from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import salabim as sim

if TYPE_CHECKING:
    from ...Simulation.SimMachine import SimMachine
    from ...Simulation.SimOrderJob import SimOrderJob
    from ...Simulation.SimRobotCorridorArm import SimRobotCorridorArm
    from ...Simulation.SimRobotMain import SimRobotMain


class SimulationObjectObserver:
    @classmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_simulation_object(cls, sender: sim.Component, time: float) -> dict[str, object]:
        from ...Simulation.SimMachine import SimMachine
        from ...Simulation.SimOrderJob import SimOrderJob
        from ...Simulation.SimRobotCorridorArm import SimRobotCorridorArm
        from ...Simulation.SimRobotMain import SimRobotMain

        if isinstance(sender, SimOrderJob):
            return cls.observe_order_job(sender, time)
        if isinstance(sender, SimRobotMain):
            return cls.observe_main_robot(sender, time)
        if isinstance(sender, SimRobotCorridorArm):
            return cls.observe_corridor_arm_robot(sender, time)
        if isinstance(sender, SimMachine):
            return cls.observe_machine(sender, time)
        raise ValueError(f"Unsupported simulation object '{sender}'")

    @staticmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_order_job(job: SimOrderJob, time: float) -> dict[str, object]:
        return {
            "object_type": "order_job",
            "object_id": SimulationObjectObserver.job_id(job),
            "time": time,
            "job_id": f"{job.order.name}:{job.number}",
            "number": job.number,
            "layout_id": job.layout.name,
            "scenario_id": job.scenario.name,
            "order_id": job.order.name,
            "start_store_id": job.store_start.name(),
            "target_product_type_id": job.order.product_type.name,
            "target_product_length": job.order.product_type.length,
            "target_product_width": job.order.product_type.width,
            "target_product_depth": job.order.product_type.depth,
            "target_product_weight": job.order.product_type.weight,
            "quantity": job.order.quantity,
            "earliest_start_time": job.order.earliest_start_time,
            "latest_end_time": job.order.latest_end_time,
            "released": job.released,
            "downgraded": job.downgraded,
            "downgrade_product_type_id": None if job.downgrade_product_type is None else job.downgrade_product_type.name,
            "queue_priority": job.queue_priority,
            "bearbeitungs_state": job.bearbeitungs_state.get(),
            "general_state": job.general_state.get(),
            "due_state": job.due_state.get(),
            "defect_detected_time": job.defect_detected_time,
            "defect_operation_id": None if job.defect_operation is None else job.defect_operation.name,
            "defect_operation_duration": None if job.defect_operation is None else job.defect_operation.duration,
            "defect_operation_consumed_life_units": None if job.defect_operation is None else job.defect_operation.consumes_life_units,
            "defect_machine_id": None if job.defect_machine is None else job.defect_machine.name,
            "defect_product_state_before": job.defect_product_state_before,
            "defect_product_state_target": job.defect_product_state_target,
            "defekt_schwergrad": job.defekt_schwergrad,
            "defect_recovery_strategy": job.defect_recovery_strategy,
            "recovery_in_progress": job.recovery_in_progress,
            "completed_time": job.completed_time,
            "location": job.location,
            "selected_operation_id": None if job.selected_operation is None else job.selected_operation.name,
            "selected_machine_id": None if job.selected_machine is None else job.selected_machine.name,
        }

    @staticmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_main_robot(robot: SimRobotMain, time: float) -> dict[str, object]:
        current_job = robot.current_job
        next_operation = None
        next_machine = None
        next_corridor_index = None
        next_corridor_id = None
        next_machine_side = None

        if current_job is not None:
            next_operation = current_job.selected_operation
            next_machine = current_job.selected_machine

        if next_machine is not None:
            next_corridor_index = robot.configured_corridor_index(
                next_machine.corridor
            )
            next_corridor_id = next_machine.corridor.name
            next_machine_side = "left" if next_machine.left else "right"

        store_positions_by_id = {
            robot.store_start.name(): {
                "x": 0.0,
                "y": -robot.calculate_storage_y_position(),
                "z": 1.25,
            },
            robot.store_end.name(): {
                "x": 0.0,
                "y": robot.calculate_storage_y_position(),
                "z": 1.25,
            },
        }
        for corridor_index, sim_corridor in enumerate(robot.sim_corridors):
            corridor_y = robot.calculate_corridor_y_position(corridor_index)
            for store in (
                sim_corridor.store_main,
                sim_corridor.store_left,
                sim_corridor.store_right,
            ):
                store_positions_by_id[store.name()] = {
                    "x": 0.0,
                    "y": corridor_y,
                    "z": 1.25,
                }

        return {
            "object_type": "main_robot",
            "object_id": robot.label,
            "time": time,
            "layout_id": robot.layout.name,
            "storage_in_time": robot.layout.storage_in_time,
            "storage_out_time": robot.layout.storage_out_time,
            "scenario_id": robot.scenario.name,
            "x": robot.x,
            "y": robot.y,
            "z": robot.z,
            "move_state": robot.state_move.get(),
            "load_state": robot.state_load.get(),
            "is_loaded": current_job is not None,
            "is_empty": current_job is None,
            "is_moving": robot.state_move.get() not in ["waiting", "idle"],
            "movement_speed": robot.configured_movement_speed,
            "current_job_summary": SimulationObjectObserver.observe_job_summary(current_job),
            "current_job_id": SimulationObjectObserver.job_id(current_job),
            "current_job_defect_operation_id": None if current_job is None or current_job.defect_operation is None else current_job.defect_operation.name,
            "current_job_defect_machine_id": None if current_job is None or current_job.defect_machine is None else current_job.defect_machine.name,
            "current_job_queue_priority": None if current_job is None else current_job.queue_priority,
            "current_job_bearbeitungs_state": None if current_job is None else current_job.bearbeitungs_state.get(),
            "current_job_general_state": None if current_job is None else current_job.general_state.get(),
            "current_job_selected_operation_id": None if current_job is None or current_job.selected_operation is None else current_job.selected_operation.name,
            "current_job_selected_machine_id": None if current_job is None or current_job.selected_machine is None else current_job.selected_machine.name,
            "remaining_operation_count": None if current_job is not None else 0,
            "remaining_machine_count": 0 if current_job is None or current_job.selected_machine is None else 1,
            "next_operation_id": None if next_operation is None else next_operation.name,
            "next_machine_id": None if next_machine is None else next_machine.name,
            "next_corridor_index": next_corridor_index,
            "next_corridor_id": next_corridor_id,
            "next_machine_side": next_machine_side,
            "start_store_id": robot.store_start.name(),
            "end_store_id": robot.store_end.name(),
            "store_positions_by_id": store_positions_by_id,
            "start_storage": SimulationObjectObserver.observe_store(robot.store_start),
            "end_storage": SimulationObjectObserver.observe_store(robot.store_end),
            "corridor_storages": [
                {
                    "corridor_index": corridor_index,
                    "corridor_id": sim_corridor.corridor.name,
                    "main": SimulationObjectObserver.observe_store(sim_corridor.store_main),
                    "left": SimulationObjectObserver.observe_store(sim_corridor.store_left),
                    "right": SimulationObjectObserver.observe_store(sim_corridor.store_right),
                }
                for corridor_index, sim_corridor in enumerate(robot.sim_corridors)
            ],
        }

    @staticmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_corridor_arm_robot(robot: SimRobotCorridorArm, time: float) -> dict[str, object]:
        current_job = robot.current_job
        next_operation = None
        next_machine = None
        next_machine_index = None
        next_machine_in_arm_side = False
        next_machine_same_corridor = False

        if current_job is not None:
            next_operation = current_job.selected_operation
            next_machine = current_job.selected_machine

        if next_machine is not None:
            next_machine_in_arm_side = next_machine in robot.machines
            next_machine_same_corridor = next_machine.corridor == robot.corridor
            if next_machine_in_arm_side:
                next_machine_index = robot.machines.index(next_machine)

        store_positions_by_id = {
            robot.store_in.name(): {"x": robot.dx, "y": robot.y, "z": 1.25},
            robot.store_out_arm.name(): {"x": robot.dx, "y": robot.y, "z": 1.25},
            robot.store_out_main.name(): {"x": 0.0, "y": robot.y, "z": 1.25},
        }
        for machine_index, sim_machine in enumerate(robot.sim_machines):
            machine_x = robot.compute_machine_x(machine_index)
            for store in (sim_machine.store_in, sim_machine.store_out):
                store_positions_by_id[store.name()] = {
                    "x": machine_x,
                    "y": robot.y,
                    "z": 1.5,
                }

        return {
            "object_type": "corridor_arm_robot",
            "object_id": f"CorridorArmRobot:{robot.corridor.name}:{robot.direction}",
            "time": time,
            "robot_name": robot.label,
            "corridor_id": robot.corridor.name,
            "storage_in_time": robot.corridor.storage_in_time,
            "storage_out_time": robot.corridor.storage_out_time,
            "direction": robot.direction,
            "x": robot.x,
            "y": robot.y,
            "z": robot.z,
            "move_state": robot.state_move.get(),
            "load_state": robot.state_load.get(),
            "is_loaded": current_job is not None,
            "is_empty": current_job is None,
            "is_moving": robot.state_move.get() not in ["waiting", "idle"],
            "movement_speed": robot.configured_movement_speed,
            "current_job_summary": SimulationObjectObserver.observe_job_summary(current_job),
            "current_job_id": SimulationObjectObserver.job_id(current_job),
            "current_job_queue_priority": None if current_job is None else current_job.queue_priority,
            "current_job_bearbeitungs_state": None if current_job is None else current_job.bearbeitungs_state.get(),
            "current_job_general_state": None if current_job is None else current_job.general_state.get(),
            "current_job_selected_operation_id": None if current_job is None or current_job.selected_operation is None else current_job.selected_operation.name,
            "current_job_selected_machine_id": None if current_job is None or current_job.selected_machine is None else current_job.selected_machine.name,
            "current_job_defect_operation_id": None if current_job is None or current_job.defect_operation is None else current_job.defect_operation.name,
            "current_job_defect_machine_id": None if current_job is None or current_job.defect_machine is None else current_job.defect_machine.name,
            "remaining_operation_count": None if current_job is not None else 0,
            "remaining_machine_count": 0 if current_job is None or current_job.selected_machine is None else 1,
            "machine_names": [
                machine.name for machine in robot.machines
            ],
            "next_operation_id": None if next_operation is None else next_operation.name,
            "next_machine_id": None if next_machine is None else next_machine.name,
            "next_machine_index": next_machine_index,
            "next_machine_in_arm_side": next_machine_in_arm_side,
            "next_machine_same_corridor": next_machine_same_corridor,
            "store_in_id": robot.store_in.name(),
            "store_other_arm_input_id": robot.store_out_arm.name(),
            "store_main_id": robot.store_out_main.name(),
            "store_positions_by_id": store_positions_by_id,
            "sim_corridor_store_arm_input": SimulationObjectObserver.observe_store(robot.store_in),
            "sim_corridor_store_other_arm_input": SimulationObjectObserver.observe_store(robot.store_out_arm),
            "sim_corridor_store_main": SimulationObjectObserver.observe_store(robot.store_out_main),
            "machine_storages": [
                {
                    "machine_index": machine_index,
                    "machine_name": sim_machine.machine.name,
                    "sim_machine_id": sim_machine.policy_id,
                    "input": SimulationObjectObserver.observe_store(sim_machine.store_in),
                    "output": SimulationObjectObserver.observe_store(sim_machine.store_out),
                }
                for machine_index, sim_machine in enumerate(robot.sim_machines)
            ],
        }

    @staticmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_machine(machine: SimMachine, time: float) -> dict[str, object]:
        current_job = machine.current_job
        next_operation = None
        next_machine = None
        required_tool_type = None
        consumed_life_units = None
        remaining_life_units = None
        total_life_units = None
        has_enough_tool_life = None
        needs_tool_change = None
        next_machine_is_this_machine = None

        if current_job is not None and current_job.selected_operation is not None:
            next_operation = current_job.selected_operation
            required_tool_type = next_operation.tool_type
            consumed_life_units = next_operation.consumes_life_units
            remaining_life_units = machine.remaining_life_units[required_tool_type]
            total_life_units = required_tool_type.total_life_units
            has_enough_tool_life = remaining_life_units >= consumed_life_units
            needs_tool_change = required_tool_type != machine.tool_type

        if current_job is not None:
            next_machine = current_job.selected_machine

        if next_machine is not None:
            next_machine_is_this_machine = next_machine == machine.machine

        return {
            "object_type": "machine",
            "object_id": machine.policy_id,
            "time": time,
            "machine_name": machine.machine.name,
            "machine_type_id": machine.machine.machine_type.name,
            "corridor_id": machine.machine.corridor.name,
            "left": machine.machine.left,
            "state": machine.state.get(),
            "processing_speed_factor": machine.machine.processing_speed_factor,
            "is_idle": machine.current_job is None and machine.state.get() == "waiting",
            "has_current_job": machine.current_job is not None,
            "can_process_current_job": (
                machine.current_job is not None
                and next_operation is not None
                and next_machine_is_this_machine is True
            ),
            "mounted_tool_type_id": None if machine.tool_type is None else machine.tool_type.name,
            "dummy_tool_mounted": machine.dummy_tool_mounted,
            "tool_type_names": [
                tool_type.name for tool_type in machine.tool_types
            ],
            "remaining_life_units_by_tool": {
                tool_type.name: machine.remaining_life_units[tool_type]
                for tool_type in machine.tool_types
            },
            "current_job_summary": SimulationObjectObserver.observe_job_summary(current_job),
            "current_job_id": SimulationObjectObserver.job_id(current_job),
            "current_job_queue_priority": None if current_job is None else current_job.queue_priority,
            "current_job_bearbeitungs_state": None if current_job is None else current_job.bearbeitungs_state.get(),
            "current_job_general_state": None if current_job is None else current_job.general_state.get(),
            "remaining_operation_count": None if current_job is not None else 0,
            "remaining_machine_count": 0 if current_job is None or current_job.selected_machine is None else 1,
            "next_operation_id": None if next_operation is None else next_operation.name,
            "next_machine_id": None if next_machine is None else next_machine.name,
            "next_machine_is_this_machine": next_machine_is_this_machine,
            "required_tool_type_id": None if required_tool_type is None else required_tool_type.name,
            "required_tool_mount_time": None if required_tool_type is None else required_tool_type.mount_time,
            "required_tool_unmount_time": None if required_tool_type is None else required_tool_type.unmount_time,
            "consumed_life_units": consumed_life_units,
            "remaining_life_units_before_operation": remaining_life_units,
            "required_tool_total_life_units": total_life_units,
            "has_enough_tool_life": has_enough_tool_life,
            "needs_tool_change": needs_tool_change,
            "input_storage": SimulationObjectObserver.observe_store(machine.store_in),
            "output_storage": SimulationObjectObserver.observe_store(machine.store_out),
        }

    @staticmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_store(store: sim.Store) -> dict[str, object]:
        items = list(store.as_list())
        return {
            "store_id": store.name(),
            "count": len(items),
            "capacity": store.capacity(),
            "available_capacity": store.available_quantity(),
            "is_empty": len(items) == 0,
            "has_items": len(items) > 0,
            "has_capacity": store.available_quantity() > 0,
            "job_summaries": [
                SimulationObjectObserver.observe_job_summary(item)
                for item in items
            ],
            "job_ids": [
                SimulationObjectObserver.job_id(item)
                for item in items
            ],
            "job_queue_priorities": [
                getattr(item, "queue_priority", None)
                for item in items
            ],
            "job_bearbeitungs_states": [
                item.bearbeitungs_state.get() if hasattr(item, "bearbeitungs_state") else None
                for item in items
            ],
            "job_general_states": [
                item.general_state.get() if hasattr(item, "general_state") else None
                for item in items
            ],
            "job_due_states": [
                item.due_state.get() if hasattr(item, "due_state") else None
                for item in items
            ],
        }

    @staticmethod
    # Liest den angeforderten Wert oder Zustand aus.
    def observe_job_summary(job: SimOrderJob | None) -> dict[str, object] | None:
        if job is None:
            return None
        return {
            "job_id": SimulationObjectObserver.job_id(job),
            "order_name": job.order.name,
            "number": job.number,
            "bearbeitungs_state": job.bearbeitungs_state.get(),
            "general_state": job.general_state.get(),
            "target_product_type_name": job.order.product_type.name,
            "target_product_weight": job.order.product_type.weight,
            "earliest_start_time": job.order.earliest_start_time,
            "latest_end_time": job.order.latest_end_time,
            "released": job.released,
            "downgraded": job.downgraded,
            "queue_priority": job.queue_priority,
            "selected_operation_id": None if job.selected_operation is None else job.selected_operation.name,
            "selected_machine_id": None if job.selected_machine is None else job.selected_machine.name,
            "completed_time": job.completed_time,
            "due_state": job.due_state.get(),
        }

    @staticmethod
    # Führt die Funktion mit den übergebenen Werten aus.
    def job_id(job: SimOrderJob | None) -> str | None:
        if job is None:
            return None
        if hasattr(job, "order") and hasattr(job, "number"):
            return f"{job.order.name}:{job.number}"
        return None

class ConfigurationObjectObserver:
    """Convert configured factory objects into an ID-only policy model."""

    @staticmethod
    # Erstellt das angeforderte Modell, Objekt oder Ergebnis.
    def build_policy_configuration_model(
        product_types: list[Any],
        operation_types: list[Any],
        machines: list[Any],
        tool_types: list[Any],
        corridors: list[Any],
        layouts: list[Any],
    ) -> dict[str, object]:
        configuration_maxima = {}
        if operation_types:
            configuration_maxima["operation_duration"] = max(
                float(operation.duration) for operation in operation_types
            )
            configuration_maxima["operation_tool_consumption"] = max(
                float(operation.consumes_life_units)
                for operation in operation_types
            )
        if product_types:
            configuration_maxima["product_weight"] = max(
                float(product.weight) for product in product_types
            )
            configuration_maxima["product_volume"] = max(
                float(product.length * product.width * product.depth)
                for product in product_types
            )

        return {
            "configuration_maxima": configuration_maxima,
            "product_types_by_id": {
                product.name: {
                    "product_type_id": product.name,
                    "length": product.length,
                    "width": product.width,
                    "depth": product.depth,
                    "weight": product.weight,
                }
                for product in product_types
            },
            "operations_by_id": {
                operation.name: {
                    "operation_id": operation.name,
                    "duration": operation.duration,
                    "consumed_life_units": operation.consumes_life_units,
                    "defect_probability": operation.defect_probability,
                    "machine_type_id": operation.machine_type.name,
                    "tool_type_id": operation.tool_type.name,
                    "consumes_product_type_id": operation.consumes_product_type.name,
                    "produces_product_type_id": operation.produces_product_type.name,
                }
                for operation in operation_types
            },
            "machines_by_id": {
                machine.name: {
                    "machine_id": machine.name,
                    "machine_type_id": machine.machine_type.name,
                    "corridor_id": machine.corridor.name,
                    "layout_id": machine.corridor.layout.name,
                    "left": machine.left,
                    "input_storage_capacity": machine.input_storage_capacity,
                    "output_storage_capacity": machine.output_storage_capacity,
                    "dummy_tool_mount_time": machine.dummy_tool_mount_time,
                    "dummy_tool_unmount_time": machine.dummy_tool_unmount_time,
                    "tool_type_ids": [
                        tool_type.name for tool_type in machine.tool_types
                    ],
                }
                for machine in machines
            },
            "tools_by_id": {
                tool.name: {
                    "tool_type_id": tool.name,
                    "mount_time": tool.mount_time,
                    "unmount_time": tool.unmount_time,
                    "total_life_units": tool.total_life_units,
                }
                for tool in tool_types
            },
            "corridors_by_id": {
                corridor.name: {
                    "corridor_id": corridor.name,
                    "layout_id": corridor.layout.name,
                    "storage_capacity": corridor.storage_capacity,
                    "storage_out_time": corridor.storage_out_time,
                    "storage_in_time": corridor.storage_in_time,
                    "machine_ids": [
                        machine.name
                        for machine in corridor.machines_left + corridor.machines_right
                    ],
                }
                for corridor in corridors
            },
            "layouts_by_id": {
                layout.name: {
                    "layout_id": layout.name,
                    "storage_capacity": layout.storage_capacity,
                    "storage_out_time": layout.storage_out_time,
                    "storage_in_time": layout.storage_in_time,
                    "corridor_ids": [
                        corridor.name for corridor in layout.corridors
                    ],
                }
                for layout in layouts
            },
        }


@dataclass(frozen=True)
class PolicyObservation:
    simulation_configuration_snapshot: dict[str, object]
    current_object_id: str | None = None


class PolicyTrigger(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        event_id: str,
        sender_id: str,
        state_version: int,
        time: float,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.event_id = event_id
        self.sender_id = sender_id
        self.state_version = state_version
        self.time = time


@dataclass(frozen=True)
class SelectedObjectAction:
    target_id: str
    action_type: str
    payload: dict[str, object]


@dataclass(frozen=True)
class PolicyDecision:
    actions: list[SelectedObjectAction]

    @classmethod
    # Führt die Funktion mit den übergebenen Werten aus.
    def with_single_selected_action(cls, action: dict[str, object], target_id: str) -> PolicyDecision:
        return cls([
            SelectedObjectAction(target_id, action["action_type"], action["payload"])
        ])

class SimulationAction(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, event_id: str, target: sim.Component, source_policy_trigger_id: str, action_type: str, time: float, payload: dict[str, object], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_id = event_id
        self.target = target
        self.source_policy_trigger_id = source_policy_trigger_id
        self.action_type = action_type
        self.time = time
        self.payload = payload


class ActionGenerator(ABC):
    @abstractmethod
    # Führt die Funktion mit den übergebenen Werten aus.
    def generate_actions(self, observation: "PolicyObservation") -> list[dict[str, Any]]:
        pass


class ActionEvaluator(ABC):
    @abstractmethod
    # Führt die Funktion mit den übergebenen Werten aus.
    def prepare_action_candidate(
        self,
        action: dict[str, Any],
        observation: "PolicyObservation",
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    # Bewertet oder schätzt die übergebenen Daten.
    def evaluate_action(
        self,
        action: dict[str, Any],
        observation: "PolicyObservation",
    ) -> float:
        pass


class ActionSelector(ABC):
    @abstractmethod
    # Wählt ein passendes Objekt oder eine passende Aktion aus.
    def select_action(
        self,
        actions: list[dict[str, Any]],
        *,
        evaluator: "ActionEvaluator",
        observation: "PolicyObservation",
        target_id: str,
    ) -> "PolicyDecision":
        pass


# Führt die Funktion mit den übergebenen Werten aus.
def policy_payload_id_mappings(bridge: Any) -> dict[str, tuple[str, dict]]:
    """Map policy payload IDs to simulation-side runtime objects."""
    return {
        "target_store_id": (
            "target_store",
            bridge.policy_store_id_to_simulation_store,
        ),
        "selected_job_id": (
            "selected_job",
            bridge.policy_object_id_to_simulation_object,
        ),
        "sim_machine_id": (
            "sim_machine",
            bridge.policy_object_id_to_simulation_object,
        ),
        "sim_corridor_id": (
            "sim_corridor",
            bridge.policy_object_id_to_simulation_object,
        ),
        "selected_operation_id": (
            "selected_operation",
            bridge.operations_by_id,
        ),
        "selected_machine_id": (
            "selected_machine",
            bridge.machines_by_id,
        ),
        "downgrade_product_type_id": (
            "downgrade_product_type",
            bridge.product_types_by_id,
        ),
        "operation_id": ("operation", bridge.operations_by_id),
        "planned_machine_id": ("planned_machine", bridge.machines_by_id),
        "tool_type_id": ("tool_type", bridge.tool_types_by_id),
    }


# Prüft die angegebene Bedingung.
def is_wait_action(action_type: str) -> bool:
    return action_type.startswith("wait_")



class Policy(ABC):
    @abstractmethod
    # Führt die Funktion mit den übergebenen Werten aus.
    def make_decision(self, observation: PolicyObservation) -> PolicyDecision:
        pass
