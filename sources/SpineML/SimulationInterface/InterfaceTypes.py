from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import salabim as sim

if TYPE_CHECKING:
    from ..Simulation.SimMachine import SimMachine
    from ..Simulation.SimOrderJob import SimOrderJob
    from ..Simulation.SimRobotCorridorArm import SimRobotCorridorArm
    from ..Simulation.SimRobotMain import SimRobotMain


class SimulationObjectObserver:
    """Wandelt Laufzeitobjekte in ID-basierte Beobachtungen für die Policy um."""

    @classmethod
    # Wählt anhand des konkreten Laufzeittyps die passende Beobachtungsmethode.
    def observe_simulation_object(cls, sender: sim.Component, time: float) -> dict[str, object]:
        from ..Simulation.SimMachine import SimMachine
        from ..Simulation.SimOrderJob import SimOrderJob
        from ..Simulation.SimRobotCorridorArm import SimRobotCorridorArm
        from ..Simulation.SimRobotMain import SimRobotMain

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
    # Erstellt die vollständige Policy-Beobachtung für einen Auftragsjob.
    def observe_order_job(job: SimOrderJob, time: float) -> dict[str, object]:
        observation = {
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
        }
        if job.downgrade_product_type is None:
            observation["downgrade_product_type_id"] = None
        else:
            observation["downgrade_product_type_id"] = job.downgrade_product_type.name

        observation.update({
            "queue_priority": job.queue_priority,
            "processing_state": job.processing_state.get(),
            "general_state": job.general_state.get(),
            "due_state": job.due_state.get(),
            "defect_detected_time": job.defect_detected_time,
        })
        if job.defect_operation is None:
            observation["defect_operation_id"] = None
        else:
            observation["defect_operation_id"] = job.defect_operation.name

        if job.defect_operation is None:
            observation["defect_operation_duration"] = None
        else:
            observation["defect_operation_duration"] = job.defect_operation.duration

        if job.defect_operation is None:
            observation["defect_operation_consumed_life_units"] = None
        else:
            observation["defect_operation_consumed_life_units"] = job.defect_operation.consumes_life_units

        if job.defect_machine is None:
            observation["defect_machine_id"] = None
        else:
            observation["defect_machine_id"] = job.defect_machine.name

        observation.update({
            "defect_product_state_before": job.defect_product_state_before,
            "defect_product_state_target": job.defect_product_state_target,
            "defect_severity": job.defect_severity,
            "defect_recovery_strategy": job.defect_recovery_strategy,
            "recovery_in_progress": job.recovery_in_progress,
            "completed_time": job.completed_time,
            "location": job.location,
        })
        if job.selected_operation is None:
            observation["selected_operation_id"] = None
        else:
            observation["selected_operation_id"] = job.selected_operation.name

        if job.selected_machine is None:
            observation["selected_machine_id"] = None
        else:
            observation["selected_machine_id"] = job.selected_machine.name
        return observation

    @staticmethod
    # Erstellt die Policy-Beobachtung für den Main-Roboter inklusive Stores und Job.
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
            if next_machine.left:
                next_machine_side = "left"
            else:
                next_machine_side = "right"

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

        observation = {
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
        }
        if current_job is None or current_job.defect_operation is None:
            observation["current_job_defect_operation_id"] = None
        else:
            observation["current_job_defect_operation_id"] = current_job.defect_operation.name

        if current_job is None or current_job.defect_machine is None:
            observation["current_job_defect_machine_id"] = None
        else:
            observation["current_job_defect_machine_id"] = current_job.defect_machine.name

        if current_job is None:
            observation["current_job_queue_priority"] = None
        else:
            observation["current_job_queue_priority"] = current_job.queue_priority

        if current_job is None:
            observation["current_job_processing_state"] = None
        else:
            observation["current_job_processing_state"] = current_job.processing_state.get()

        if current_job is None:
            observation["current_job_general_state"] = None
        else:
            observation["current_job_general_state"] = current_job.general_state.get()

        if current_job is None or current_job.selected_operation is None:
            observation["current_job_selected_operation_id"] = None
        else:
            observation["current_job_selected_operation_id"] = current_job.selected_operation.name

        if current_job is None or current_job.selected_machine is None:
            observation["current_job_selected_machine_id"] = None
        else:
            observation["current_job_selected_machine_id"] = current_job.selected_machine.name

        if current_job is not None:
            observation["remaining_operation_count"] = None
        else:
            observation["remaining_operation_count"] = 0

        if current_job is None or current_job.selected_machine is None:
            observation["remaining_machine_count"] = 0
        else:
            observation["remaining_machine_count"] = 1

        if next_operation is None:
            observation["next_operation_id"] = None
        else:
            observation["next_operation_id"] = next_operation.name

        if next_machine is None:
            observation["next_machine_id"] = None
        else:
            observation["next_machine_id"] = next_machine.name

        observation.update({
            "next_corridor_index": next_corridor_index,
            "next_corridor_id": next_corridor_id,
            "next_machine_side": next_machine_side,
            "start_store_id": robot.store_start.name(),
            "end_store_id": robot.store_end.name(),
            "store_positions_by_id": store_positions_by_id,
            "start_storage": SimulationObjectObserver.observe_store(robot.store_start),
            "end_storage": SimulationObjectObserver.observe_store(robot.store_end),
            "corridor_storages": [],
        })
        for corridor_index, sim_corridor in enumerate(robot.sim_corridors):
            observation["corridor_storages"].append({
                "corridor_index": corridor_index,
                "corridor_id": sim_corridor.corridor.name,
                "main": SimulationObjectObserver.observe_store(sim_corridor.store_main),
                "left": SimulationObjectObserver.observe_store(sim_corridor.store_left),
                "right": SimulationObjectObserver.observe_store(sim_corridor.store_right),
            })
        return observation

    @staticmethod
    # Erstellt die Policy-Beobachtung für einen Korridorroboter inklusive Stores und Job.
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

        observation = {
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
        }
        if current_job is None:
            observation["current_job_queue_priority"] = None
        else:
            observation["current_job_queue_priority"] = current_job.queue_priority

        if current_job is None:
            observation["current_job_processing_state"] = None
        else:
            observation["current_job_processing_state"] = current_job.processing_state.get()

        if current_job is None:
            observation["current_job_general_state"] = None
        else:
            observation["current_job_general_state"] = current_job.general_state.get()

        if current_job is None or current_job.selected_operation is None:
            observation["current_job_selected_operation_id"] = None
        else:
            observation["current_job_selected_operation_id"] = current_job.selected_operation.name

        if current_job is None or current_job.selected_machine is None:
            observation["current_job_selected_machine_id"] = None
        else:
            observation["current_job_selected_machine_id"] = current_job.selected_machine.name

        if current_job is None or current_job.defect_operation is None:
            observation["current_job_defect_operation_id"] = None
        else:
            observation["current_job_defect_operation_id"] = current_job.defect_operation.name

        if current_job is None or current_job.defect_machine is None:
            observation["current_job_defect_machine_id"] = None
        else:
            observation["current_job_defect_machine_id"] = current_job.defect_machine.name

        if current_job is not None:
            observation["remaining_operation_count"] = None
        else:
            observation["remaining_operation_count"] = 0

        if current_job is None or current_job.selected_machine is None:
            observation["remaining_machine_count"] = 0
        else:
            observation["remaining_machine_count"] = 1

        observation["machine_names"] = []
        for machine in robot.machines:
            observation["machine_names"].append(machine.name)

        if next_operation is None:
            observation["next_operation_id"] = None
        else:
            observation["next_operation_id"] = next_operation.name

        if next_machine is None:
            observation["next_machine_id"] = None
        else:
            observation["next_machine_id"] = next_machine.name

        observation.update({
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
            "machine_storages": [],
        })
        for machine_index, sim_machine in enumerate(robot.sim_machines):
            observation["machine_storages"].append({
                "machine_index": machine_index,
                "machine_name": sim_machine.machine.name,
                "sim_machine_id": sim_machine.policy_id,
                "input": SimulationObjectObserver.observe_store(sim_machine.store_in),
                "output": SimulationObjectObserver.observe_store(sim_machine.store_out),
            })
        return observation

    @staticmethod
    # Erstellt die Policy-Beobachtung für eine Maschine inklusive Job- und Werkzeugdaten.
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

        observation = {
            "object_type": "machine",
            "object_id": machine.policy_id,
            "time": time,
            "machine_name": machine.machine.name,
            "machine_type_id": machine.machine.machine_type.name,
            "corridor_id": machine.machine.corridor.name,
            "left": machine.machine.left,
            "state": machine.state.get(),
            "processing_speed_factor": machine.processing_speed_factor,
            "defect_probability": machine.defect_probability,
            "is_idle": machine.current_job is None and machine.state.get() == "waiting",
            "has_current_job": machine.current_job is not None,
            "can_process_current_job": (
                machine.current_job is not None
                and next_operation is not None
                and next_machine_is_this_machine is True
            ),
        }
        if machine.tool_type is None:
            observation["mounted_tool_type_id"] = None
        else:
            observation["mounted_tool_type_id"] = machine.tool_type.name

        observation.update({
            "dummy_tool_mounted": machine.dummy_tool_mounted,
            "tool_type_names": [],
        })
        for tool_type in machine.tool_types:
            observation["tool_type_names"].append(tool_type.name)

        observation["remaining_life_units_by_tool"] = {}
        for tool_type in machine.tool_types:
            observation["remaining_life_units_by_tool"][tool_type.name] = (
                machine.remaining_life_units[tool_type]
            )

        observation.update({
            "current_job_summary": SimulationObjectObserver.observe_job_summary(current_job),
            "current_job_id": SimulationObjectObserver.job_id(current_job),
        })
        if current_job is None:
            observation["current_job_queue_priority"] = None
        else:
            observation["current_job_queue_priority"] = current_job.queue_priority

        if current_job is None:
            observation["current_job_processing_state"] = None
        else:
            observation["current_job_processing_state"] = current_job.processing_state.get()

        if current_job is None:
            observation["current_job_general_state"] = None
        else:
            observation["current_job_general_state"] = current_job.general_state.get()

        if current_job is not None:
            observation["remaining_operation_count"] = None
        else:
            observation["remaining_operation_count"] = 0

        if current_job is None or current_job.selected_machine is None:
            observation["remaining_machine_count"] = 0
        else:
            observation["remaining_machine_count"] = 1

        if next_operation is None:
            observation["next_operation_id"] = None
        else:
            observation["next_operation_id"] = next_operation.name

        if next_machine is None:
            observation["next_machine_id"] = None
        else:
            observation["next_machine_id"] = next_machine.name

        observation["next_machine_is_this_machine"] = next_machine_is_this_machine
        if required_tool_type is None:
            observation["required_tool_type_id"] = None
        else:
            observation["required_tool_type_id"] = required_tool_type.name

        if required_tool_type is None:
            observation["required_tool_mount_time"] = None
        else:
            observation["required_tool_mount_time"] = required_tool_type.mount_time

        if required_tool_type is None:
            observation["required_tool_unmount_time"] = None
        else:
            observation["required_tool_unmount_time"] = required_tool_type.unmount_time

        observation.update({
            "consumed_life_units": consumed_life_units,
            "remaining_life_units_before_operation": remaining_life_units,
            "required_tool_total_life_units": total_life_units,
            "has_enough_tool_life": has_enough_tool_life,
            "needs_tool_change": needs_tool_change,
            "input_storage": SimulationObjectObserver.observe_store(machine.store_in),
            "output_storage": SimulationObjectObserver.observe_store(machine.store_out),
        })
        return observation

    @staticmethod
    # Erstellt eine Beobachtung der Store-Belegung, Kapazität und enthaltenen Jobs.
    def observe_store(store: sim.Store) -> dict[str, object]:
        items = list(store.as_list())
        observation = {
            "store_id": store.name(),
            "count": len(items),
            "capacity": store.capacity(),
            "available_capacity": store.available_quantity(),
            "is_empty": len(items) == 0,
            "has_items": len(items) > 0,
            "has_capacity": store.available_quantity() > 0,
            "job_summaries": [],
        }
        for item in items:
            observation["job_summaries"].append(
                SimulationObjectObserver.observe_job_summary(item)
            )

        observation["job_ids"] = []
        for item in items:
            observation["job_ids"].append(SimulationObjectObserver.job_id(item))

        observation["job_queue_priorities"] = []
        for item in items:
            observation["job_queue_priorities"].append(getattr(item, "queue_priority", None))

        observation["job_processing_states"] = []
        for item in items:
            if hasattr(item, "processing_state"):
                observation["job_processing_states"].append(item.processing_state.get())
            else:
                observation["job_processing_states"].append(None)

        observation["job_general_states"] = []
        for item in items:
            if hasattr(item, "general_state"):
                observation["job_general_states"].append(item.general_state.get())
            else:
                observation["job_general_states"].append(None)

        observation["job_due_states"] = []
        for item in items:
            if hasattr(item, "due_state"):
                observation["job_due_states"].append(item.due_state.get())
            else:
                observation["job_due_states"].append(None)
        return observation

    @staticmethod
    # Erstellt eine kompakte Jobbeschreibung für Roboter- und Store-Beobachtungen.
    def observe_job_summary(job: SimOrderJob | None) -> dict[str, object] | None:
        if job is None:
            return None
        observation = {
            "job_id": SimulationObjectObserver.job_id(job),
            "order_name": job.order.name,
            "number": job.number,
            "processing_state": job.processing_state.get(),
            "general_state": job.general_state.get(),
            "target_product_type_name": job.order.product_type.name,
            "target_product_weight": job.order.product_type.weight,
            "earliest_start_time": job.order.earliest_start_time,
            "latest_end_time": job.order.latest_end_time,
            "released": job.released,
            "downgraded": job.downgraded,
            "queue_priority": job.queue_priority,
        }
        if job.selected_operation is None:
            observation["selected_operation_id"] = None
        else:
            observation["selected_operation_id"] = job.selected_operation.name

        if job.selected_machine is None:
            observation["selected_machine_id"] = None
        else:
            observation["selected_machine_id"] = job.selected_machine.name

        observation["completed_time"] = job.completed_time
        observation["due_state"] = job.due_state.get()
        return observation

    @staticmethod
    # Erzeugt aus Auftrag und Jobnummer die stabile ID eines Jobs.
    def job_id(job: SimOrderJob | None) -> str | None:
        if job is None:
            return None
        if hasattr(job, "order") and hasattr(job, "number"):
            return f"{job.order.name}:{job.number}"
        return None

class ConfigurationObjectObserver:
    """Wandelt die Fabrikkonfiguration in ein ID-basiertes Policy-Modell um."""

    @staticmethod
    # Erstellt aus den Konfigurationsobjekten das ID-basierte Policy-Modell.
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
            operation_durations = []
            for operation in operation_types:
                operation_durations.append(float(operation.duration))
            configuration_maxima["operation_duration"] = max(operation_durations)

            operation_tool_consumptions = []
            for operation in operation_types:
                operation_tool_consumptions.append(float(operation.consumes_life_units))
            configuration_maxima["operation_tool_consumption"] = max(operation_tool_consumptions)

        if product_types:
            product_weights = []
            for product in product_types:
                product_weights.append(float(product.weight))
            configuration_maxima["product_weight"] = max(product_weights)

            product_volumes = []
            for product in product_types:
                product_volumes.append(float(product.length * product.width * product.depth))
            configuration_maxima["product_volume"] = max(product_volumes)

        product_types_by_id = {}
        for product in product_types:
            product_id = product.name
            product_types_by_id[product_id] = {
                "product_type_id": product.name,
                "length": product.length,
                "width": product.width,
                "depth": product.depth,
                "weight": product.weight,
            }

        operations_by_id = {}
        for operation in operation_types:
            operation_id = operation.name
            operations_by_id[operation_id] = {
                "operation_id": operation.name,
                "duration": operation.duration,
                "consumed_life_units": operation.consumes_life_units,
                "machine_type_id": operation.machine_type.name,
                "tool_type_id": operation.tool_type.name,
                "consumes_product_type_id": operation.consumes_product_type.name,
                "produces_product_type_id": operation.produces_product_type.name,
            }

        machines_by_id = {}
        for machine in machines:
            machine_id = machine.name
            machine_model = {
                "machine_id": machine.name,
                "machine_type_id": machine.machine_type.name,
                "corridor_id": machine.corridor.name,
                "layout_id": machine.corridor.layout.name,
                "left": machine.left,
                "input_storage_capacity": machine.input_storage_capacity,
                "output_storage_capacity": machine.output_storage_capacity,
                "defect_probability": machine.defect_probability,
                "dummy_tool_mount_time": machine.dummy_tool_mount_time,
                "dummy_tool_unmount_time": machine.dummy_tool_unmount_time,
                "tool_type_ids": [],
            }
            for tool_type in machine.tool_types:
                machine_model["tool_type_ids"].append(tool_type.name)
            machines_by_id[machine_id] = machine_model

        tools_by_id = {}
        for tool in tool_types:
            tool_id = tool.name
            tools_by_id[tool_id] = {
                "tool_type_id": tool.name,
                "mount_time": tool.mount_time,
                "unmount_time": tool.unmount_time,
                "total_life_units": tool.total_life_units,
            }

        corridors_by_id = {}
        for corridor in corridors:
            corridor_id = corridor.name
            corridor_model = {
                "corridor_id": corridor.name,
                "layout_id": corridor.layout.name,
                "storage_capacity": corridor.storage_capacity,
                "storage_out_time": corridor.storage_out_time,
                "storage_in_time": corridor.storage_in_time,
                "machine_ids": [],
            }
            for machine in corridor.machines_left + corridor.machines_right:
                corridor_model["machine_ids"].append(machine.name)
            corridors_by_id[corridor_id] = corridor_model

        layouts_by_id = {}
        for layout in layouts:
            layout_id = layout.name
            layout_model = {
                "layout_id": layout.name,
                "storage_capacity": layout.storage_capacity,
                "storage_out_time": layout.storage_out_time,
                "storage_in_time": layout.storage_in_time,
                "corridor_ids": [],
            }
            for corridor in layout.corridors:
                layout_model["corridor_ids"].append(corridor.name)
            layouts_by_id[layout_id] = layout_model

        return {
            "configuration_maxima": configuration_maxima,
            "product_types_by_id": product_types_by_id,
            "operations_by_id": operations_by_id,
            "machines_by_id": machines_by_id,
            "tools_by_id": tools_by_id,
            "corridors_by_id": corridors_by_id,
            "layouts_by_id": layouts_by_id,
        }


@dataclass(frozen=True)
class PolicyObservation:
    """Enthält Konfiguration und aktuellen Simulationszustand für die Policy."""

    simulation_configuration_snapshot: dict[str, object]
    current_object_id: str | None = None


class PolicyTrigger(sim.Component):
    """Meldet der Bridge eine Zustandsänderung eines Simulationsobjekts."""

    # Initialisiert einen Trigger mit ID, Absender, Zustandsversion und Simulationszeit.
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
    """Beschreibt eine von der Policy ausgewählte Aktion mit Ziel und Payload."""

    target_id: str
    action_type: str
    payload: dict[str, object]


@dataclass(frozen=True)
class PolicyDecision:
    """Enthält die Aktionsauswahl, die die Policy an die Bridge zurückgibt."""

    actions: list[SelectedObjectAction]

    @classmethod
    # Erstellt eine Entscheidung mit genau einer ausgewählten Aktion.
    def with_single_selected_action(cls, action: dict[str, object], target_id: str) -> PolicyDecision:
        return cls([
            SelectedObjectAction(target_id, action["action_type"], action["payload"])
        ])

class SimulationAction(sim.Component):
    """Repräsentiert eine von der Bridge zugestellte ausführbare Aktion."""

    # Initialisiert eine ausführbare Aktion für ein konkretes Simulationsobjekt.
    def __init__(self, event_id: str, target: sim.Component, source_policy_trigger_id: str, action_type: str, time: float, payload: dict[str, object], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_id = event_id
        self.target = target
        self.source_policy_trigger_id = source_policy_trigger_id
        self.action_type = action_type
        self.time = time
        self.payload = payload


class ActionGenerator(ABC):
    """Schnittstelle zum Erzeugen technisch möglicher Aktionen."""

    @abstractmethod
    # Erzeugt die technisch möglichen Aktionen aus einer Policy-Beobachtung.
    def generate_actions(self, observation: "PolicyObservation") -> list[dict[str, Any]]:
        pass


class ActionEvaluator(ABC):
    """Schnittstelle zum Bewerten vollständig erzeugter Aktionskandidaten."""

    @abstractmethod
    # Berechnet den Bewertungswert eines Aktionskandidaten.
    def evaluate_action(
        self,
        action: dict[str, Any],
        observation: "PolicyObservation",
    ) -> float:
        pass


class ActionSelector(ABC):
    """Schnittstelle zum Auswählen von Aktionen aus bewerteten Kandidaten."""

    @abstractmethod
    # Wählt aus den bewerteten Kandidaten eine oder mehrere Aktionen aus.
    def select_action(
        self,
        actions: list[dict[str, Any]],
        *,
        evaluator: "ActionEvaluator",
        observation: "PolicyObservation",
        target_id: str,
    ) -> "PolicyDecision":
        pass


def policy_payload_id_mappings(bridge: Any) -> dict[str, tuple[str, dict]]:
    """Ordnet Payload-IDs den internen Feldern und Registern der Bridge zu."""
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


# Prüft, ob ein Aktionstyp mit dem Präfix für eine Warteaktion beginnt.
def is_wait_action(action_type: str) -> bool:
    return action_type.startswith("wait_")



class Policy(ABC):
    """Schnittstelle einer Steuerung, die Beobachtungen in Entscheidungen umwandelt."""

    @abstractmethod
    # Verarbeitet eine Beobachtung und gibt die ausgewählte Aktion zurück.
    def make_decision(self, observation: PolicyObservation) -> PolicyDecision:
        pass
