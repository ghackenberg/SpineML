from __future__ import annotations

from collections.abc import Mapping
import math
from numbers import Integral

import numpy as np

from ...SimulationInterface.InterfaceTypes import PolicyObservation
from .RLCandidatePolicy import DecisionRequest


OBJECT_TYPES = ("order_job", "main_robot", "corridor_arm_robot", "machine")
ACTION_TYPES = (
    "release_job", "wait_job", "complete_job", "job_rework_on_alternative_machine",
    "job_rework_on_defect_machine", "job_scrap", "downgrade_product",
    "pick_main_robot", "place_main_robot", "wait_main_robot",
    "pick_corridor_arm_robot", "place_corridor_arm_robot", "wait_corridor_arm_robot",
    "pick_machine_job", "process_machine_job", "wait_machine",
)
CONTEXT_FEATURE_NAMES = (
    "time", "current_object_index", *(f"object_type_{name}" for name in OBJECT_TYPES),
    "candidate_count", "entity_count", "waiting_fraction", "pending_action_count",
    "reserved_job_count", "released_job_fraction", "completed_job_fraction",
    "defect_job_fraction", "scrap_job_fraction", "downgraded_job_fraction",
    "current_job_index", "x", "y", "z", "deadline_remaining", "queue_priority",
    "defect_severity", "recovery_in_progress",
)
ENTITY_FEATURE_NAMES = (
    *(f"object_type_{name}" for name in OBJECT_TYPES),
    "object_index", "job_index", "processing_product_index", "target_product_index",
    "operation_index", "machine_index", "mounted_tool_index", "is_current_object",
    "is_waiting_for_action", "action_already_selected", "job_reserved_by_pick",
    "released", "downgraded", "recovery_in_progress", "completed", "is_loaded",
    "is_moving", "is_idle", "has_enough_tool_life", "needs_tool_change",
    "general_intact", "general_defect", "general_scrap", "due_on_time", "due_late",
    "processing_unconfigured", "processing_defect", "x", "y", "z",
    "movement_speed", "deadline_remaining", "release_remaining", "queue_priority",
    "defect_severity", "defect_probability", "processing_speed_factor",
    "input_count", "input_available_capacity", "output_count", "output_available_capacity",
    "remaining_tool_life", "consumed_life_units", "store_job_count", "store_available_capacity",
)
CANDIDATE_FEATURE_NAMES = (
    *(f"action_type_{name}" for name in ACTION_TYPES),
    "job_index", "operation_index", "machine_index", "product_index", "tool_index",
    "target_store_index", "processing_product_index", "target_product_index",
    "deadline_remaining", "queue_priority", "defect_severity", "job_released",
    "job_downgraded", "job_recovery_in_progress", "job_completed", "general_intact",
    "general_defect", "general_scrap", "product_weight", "product_volume",
    "operation_duration", "operation_tool_consumption", "machine_defect_probability",
    "machine_processing_speed_factor", "machine_input_count", "machine_input_available_capacity",
    "machine_output_count", "machine_output_available_capacity", "machine_tool_matches",
    "machine_has_enough_tool_life", "machine_remaining_tool_life", "tool_mount_time",
    "tool_unmount_time", "tool_total_life_units", "target_store_count",
    "target_store_available_capacity", "target_store_capacity", "storage_in_time",
    "storage_out_time", "target_distance", "release_time_remaining", "job_reserved_by_pick",
)


def _bounded(value: object) -> float:
    """Monotone, feste Skalierung ohne laufabhängige Mittelwerte oder Clipping."""
    if value is None:
        return 0.0
    number = float(value)
    if math.isnan(number):
        raise ValueError("RL features cannot contain NaN")
    if math.isinf(number):
        return math.copysign(1.0, number)
    return number / (1.0 + abs(number))


def _walk(value):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


class RLObservationEncoder:
    """Feste, gepaddete numerische Sicht auf ID-basierte Bridge-Snapshots.

    Jede Zeile beschreibt ein Objekt bzw. einen tatsächlich angebotenen
    Kandidaten; Zeilen sind keine global fest zugeordneten Aktionsnummern.
    Masken markieren gültige Zeilen. Die Features sind eine kompakte Beobachtung,
    keine Behauptung eines vollständigen Markov-Zustands oder fertigen NN-Modells.

    ID-Kataloge werden aus dem ersten vollständigen Snapshot sortiert aufgebaut
    und bleiben über Resets identischer Modelle stabil. 0 bedeutet keinen Wert;
    reale IDs werden kollisionsfrei durch Rang/(Kataloggröße+1) repräsentiert.
    Ein anderes Modell/Objektschema benötigt einen neuen Encoder. Es werden keine
    Kategorien gehasht, unbekannten IDs eingefügt oder überzähligen Zeilen gekürzt.
    """

    context_feature_names = CONTEXT_FEATURE_NAMES
    entity_feature_names = ENTITY_FEATURE_NAMES
    candidate_feature_names = CANDIDATE_FEATURE_NAMES
    context_size = len(CONTEXT_FEATURE_NAMES)
    entity_feature_size = len(ENTITY_FEATURE_NAMES)
    candidate_feature_size = len(CANDIDATE_FEATURE_NAMES)

    def __init__(self, max_actions: int = 256, max_entities: int = 256):
        for name, value in (("max_actions", max_actions), ("max_entities", max_entities)):
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.max_actions = int(max_actions)
        self.max_entities = int(max_entities)
        self._catalogs: dict[str, dict[str, float]] | None = None

    def empty_observation(self) -> dict[str, np.ndarray]:
        """Terminalbeobachtung ohne gültige Entitäts- oder Aktionszeile."""
        return {
            "context": np.zeros(self.context_size, dtype=np.float32),
            "entities": np.zeros((self.max_entities, self.entity_feature_size), dtype=np.float32),
            "entity_mask": np.zeros(self.max_entities, dtype=np.int8),
            "candidates": np.zeros((self.max_actions, self.candidate_feature_size), dtype=np.float32),
            "action_mask": np.zeros(self.max_actions, dtype=np.int8),
        }

    def _catalog_values(self, snapshot: dict, stores: dict) -> dict[str, set[str]]:
        model = snapshot["configuration_model"]
        states = snapshot["simulation_object_states_by_id"]
        return {
            "object": set(states),
            "job": {str(state.get("job_id", key)) for key, state in states.items()
                    if state["object_type"] == "order_job"},
            "operation": set(model.get("operations_by_id", {})),
            "machine": set(model.get("machines_by_id", {})),
            "product": set(model.get("product_types_by_id", {})),
            "tool": set(model.get("tools_by_id", {})),
            "store": set(stores),
        }

    def _initialize_or_validate_catalogs(self, snapshot: dict, stores: dict) -> None:
        values = self._catalog_values(snapshot, stores)
        if self._catalogs is None:
            self._catalogs = {
                kind: {name: (index + 1) / (len(names) + 1)
                       for index, name in enumerate(sorted(names))}
                for kind, names in values.items()
            }
        else:
            for kind, names in values.items():
                if names != set(self._catalogs[kind]):
                    raise ValueError(
                        f"RL {kind} ID schema changed; create a new RLObservationEncoder"
                    )

    def _id(self, kind: str, value: object) -> float:
        if value is None:
            return 0.0
        try:
            return self._catalogs[kind][str(value)]
        except KeyError as error:
            raise ValueError(f"Unknown RL {kind} ID {value!r}") from error

    def _product_id(self, value: object) -> float:
        if value in (None, "unconfigured", "defect"):
            return 0.0
        return self._id("product", value)

    @staticmethod
    def _job_for_state(state: dict, jobs: dict) -> dict:
        if state["object_type"] == "order_job":
            return state
        summary = state.get("current_job_summary") or {}
        return {**summary, **jobs.get(state.get("current_job_id"), {})}

    @staticmethod
    def _row(names: tuple[str, ...], values: dict) -> np.ndarray:
        return np.asarray([values.get(name, 0.0) for name in names], dtype=np.float32)

    def encode(self, request: DecisionRequest) -> dict[str, np.ndarray]:
        return self._encode(request, allow_empty_candidates=False)

    def encode_snapshot(self, snapshot: dict) -> dict[str, np.ndarray]:
        """Globalzustand am Zeithorizont ohne erfundene Aktion oder aktuellen Akteur.

        Für Trunkierungen bleiben reale Zustandsfeatures zum späteren Value-
        Bootstrapping erhalten. Alle Aktionsmasken sind 0; echte Terminierungen
        verwenden weiterhin empty_observation().
        """
        return self._encode(
            DecisionRequest(PolicyObservation(snapshot, None), ()),
            allow_empty_candidates=True,
        )

    def _encode(self, request: DecisionRequest, *, allow_empty_candidates: bool) -> dict[str, np.ndarray]:
        snapshot = request.observation.simulation_configuration_snapshot
        states = snapshot["simulation_object_states_by_id"]
        if len(states) > self.max_entities:
            raise ValueError(f"RL entity count {len(states)} exceeds max_entities={self.max_entities}")
        if not request.candidates and not allow_empty_candidates:
            raise ValueError("A nonterminal RL decision must contain at least one candidate")
        if len(request.candidates) > self.max_actions:
            raise ValueError(f"RL candidate count {len(request.candidates)} exceeds max_actions={self.max_actions}")
        current_id = request.observation.current_object_id
        current = states[current_id] if current_id is not None else {"object_type": None}
        model = snapshot["configuration_model"]
        stores = {node["store_id"]: node for node in _walk(states)
                  if "store_id" in node and "count" in node}
        self._initialize_or_validate_catalogs(snapshot, stores)
        jobs = {str(state.get("job_id", key)): state for key, state in states.items()
                if state["object_type"] == "order_job"}
        machines = {state["machine_name"]: state for state in states.values()
                    if state["object_type"] == "machine"}
        reserved = {str(action.payload["selected_job_id"]) for action in request.selected_actions
                    if action.action_type.startswith("pick_")}
        assigned = {action.target_id for action in request.selected_actions}
        time = float(snapshot["time"])
        result = self.empty_observation()
        current_job = self._job_for_state(current, jobs)
        context = {
            "time": _bounded(time), "current_object_index": self._id("object", current_id),
            **{f"object_type_{kind}": float(current["object_type"] == kind) for kind in OBJECT_TYPES},
            "candidate_count": _bounded(len(request.candidates)), "entity_count": _bounded(len(states)),
            "waiting_fraction": sum(bool(state.get("is_waiting_for_action")) for state in states.values()) / max(1, len(states)),
            "pending_action_count": _bounded(len(request.selected_actions)), "reserved_job_count": _bounded(len(reserved)),
            "current_job_index": self._id("job", current_job.get("job_id")),
            "x": _bounded(current.get("x")), "y": _bounded(current.get("y")), "z": _bounded(current.get("z")),
            "deadline_remaining": _bounded(float(current_job["latest_end_time"]) - time) if current_job else 0.0,
            "queue_priority": _bounded(current_job.get("queue_priority")),
            "defect_severity": _bounded(current_job.get("defect_severity")),
            "recovery_in_progress": float(bool(current_job.get("recovery_in_progress"))),
        }
        for name, predicate in (
            ("released_job_fraction", lambda job: bool(job.get("released"))),
            ("completed_job_fraction", lambda job: job.get("completed_time") is not None),
            ("defect_job_fraction", lambda job: job.get("general_state") == "defect"),
            ("scrap_job_fraction", lambda job: job.get("general_state") == "scrap"),
            ("downgraded_job_fraction", lambda job: bool(job.get("downgraded"))),
        ):
            context[name] = sum(predicate(job) for job in jobs.values()) / max(1, len(jobs))
        result["context"] = self._row(CONTEXT_FEATURE_NAMES, context)

        # Entitätszeilen sind reproduzierbar sortiert; die Aktionsreihenfolge bleibt unverändert.
        for index, object_id in enumerate(sorted(states)):
            state = states[object_id]
            if state["object_type"] not in OBJECT_TYPES:
                raise ValueError(f"Unknown RL object type {state['object_type']!r}")
            job = self._job_for_state(state, jobs)
            processing = job.get("processing_state")
            operation_id = job.get("selected_operation_id") or state.get("next_operation_id")
            machine_id = state.get("machine_name") or job.get("selected_machine_id") or state.get("next_machine_id")
            owned_stores = {node["store_id"]: node for node in _walk(state)
                            if "store_id" in node and "count" in node}
            values = {
                **{f"object_type_{kind}": float(state["object_type"] == kind) for kind in OBJECT_TYPES},
                "object_index": self._id("object", object_id), "job_index": self._id("job", job.get("job_id")),
                "processing_product_index": self._product_id(processing),
                "target_product_index": self._product_id(job.get("target_product_type_id", job.get("target_product_type_name"))),
                "operation_index": self._id("operation", operation_id), "machine_index": self._id("machine", machine_id),
                "mounted_tool_index": self._id("tool", state.get("mounted_tool_type_id")),
                "is_current_object": float(object_id == current_id),
                "is_waiting_for_action": float(bool(state.get("is_waiting_for_action"))),
                "action_already_selected": float(object_id in assigned),
                "job_reserved_by_pick": float(str(job.get("job_id")) in reserved),
                "completed": float(bool(job) and job.get("completed_time") is not None),
                "deadline_remaining": _bounded(float(job["latest_end_time"]) - time) if job else 0.0,
                "release_remaining": _bounded(float(job["earliest_start_time"]) - time) if job else 0.0,
                "processing_unconfigured": float(processing == "unconfigured"), "processing_defect": float(processing == "defect"),
                "store_job_count": _bounded(sum(float(store["count"]) for store in owned_stores.values())),
                "store_available_capacity": _bounded(sum(float(store["available_capacity"]) for store in owned_stores.values())),
                "remaining_tool_life": _bounded(state.get("remaining_life_units_before_operation")),
            }
            for name in ("released", "downgraded", "recovery_in_progress"):
                values[name] = float(bool(job.get(name)))
            for name in ("is_loaded", "is_moving", "is_idle", "has_enough_tool_life", "needs_tool_change"):
                values[name] = float(bool(state.get(name)))
            # Maschinen nennen ihre Belegung has_current_job, Roboter is_loaded.
            values["is_loaded"] = float(bool(state.get("is_loaded", state.get("has_current_job", False))))
            for name in ("x", "y", "z", "movement_speed", "defect_probability", "processing_speed_factor", "consumed_life_units"):
                values[name] = _bounded(state.get(name))
            for name in ("queue_priority", "defect_severity"):
                values[name] = _bounded(job.get(name))
            for general in ("intact", "defect", "scrap"):
                values[f"general_{general}"] = float(job.get("general_state") == general)
            values["due_on_time"] = float(job.get("due_state") == "on-time")
            values["due_late"] = float(job.get("due_state") == "late")
            for prefix in ("input", "output"):
                store = state.get(f"{prefix}_storage") or {}
                values[f"{prefix}_count"] = _bounded(store.get("count"))
                values[f"{prefix}_available_capacity"] = _bounded(store.get("available_capacity"))
            result["entities"][index] = self._row(ENTITY_FEATURE_NAMES, values)
            result["entity_mask"][index] = 1

        for index, action in enumerate(request.candidates):
            values = self._candidate_values(action, current, current_job, jobs, machines, stores, model, states, time, reserved)
            result["candidates"][index] = self._row(CANDIDATE_FEATURE_NAMES, values)
            result["action_mask"][index] = 1
        for name, array in result.items():
            if not np.isfinite(array).all() or np.any(np.abs(array) > 1):
                raise ValueError(f"RL observation {name!r} contains invalid numeric features")
        return result

    def _candidate_values(self, action, current, current_job, jobs, machines, stores, model, states, time, reserved):
        action_type = action["action_type"]
        if action_type not in ACTION_TYPES:
            raise ValueError(f"Unknown RL action type {action_type!r}")
        payload = action["payload"]
        job = jobs.get(payload.get("selected_job_id"), current_job)
        operation_id = payload.get("selected_operation_id") or payload.get("operation_id") or job.get("selected_operation_id") or current.get("next_operation_id")
        machine_id = payload.get("selected_machine_id") or payload.get("planned_machine_id") or job.get("selected_machine_id") or current.get("machine_name") or current.get("next_machine_id")
        if machine_id is None and payload.get("sim_machine_id") is not None:
            machine_id = states[payload["sim_machine_id"]]["machine_name"]
        operation = model.get("operations_by_id", {}).get(operation_id, {})
        machine = machines.get(machine_id, {})
        # Die aufgelöste Laufzeitwahrscheinlichkeit hat Vorrang vor der Konfiguration.
        machine_config = model.get("machines_by_id", {}).get(machine_id, {})
        tool_id = payload.get("tool_type_id") or operation.get("tool_type_id")
        tool = model.get("tools_by_id", {}).get(tool_id, {})
        product_id = payload.get("downgrade_product_type_id") or operation.get("consumes_product_type_id")
        if product_id is None:
            processing = payload.get("processing_state", job.get("processing_state"))
            if processing not in (None, "unconfigured", "defect"):
                product_id = processing
        product = model.get("product_types_by_id", {}).get(product_id, {})
        store_id = payload.get("target_store_id")
        store = stores.get(store_id, {})
        remaining = machine.get("remaining_life_units_by_tool", {}).get(tool_id)
        consumption = operation.get("consumed_life_units")
        position = current.get("store_positions_by_id", {}).get(store_id)
        distance = math.sqrt(sum((float(position[axis]) - float(current[axis])) ** 2 for axis in ("x", "y", "z"))) if position else 0.0
        values = {
            **{f"action_type_{kind}": float(action_type == kind) for kind in ACTION_TYPES},
            "job_index": self._id("job", job.get("job_id")), "operation_index": self._id("operation", operation_id),
            "machine_index": self._id("machine", machine_id), "product_index": self._product_id(product_id),
            "tool_index": self._id("tool", tool_id), "target_store_index": self._id("store", store_id),
            "processing_product_index": self._product_id(job.get("processing_state")),
            "target_product_index": self._product_id(job.get("target_product_type_id", job.get("target_product_type_name"))),
            "deadline_remaining": _bounded(float(job["latest_end_time"]) - time) if job else 0.0,
            "queue_priority": _bounded(payload.get("queue_priority", job.get("queue_priority"))),
            "defect_severity": _bounded(job.get("defect_severity")),
            "job_released": float(bool(job.get("released"))), "job_downgraded": float(bool(job.get("downgraded"))),
            "job_recovery_in_progress": float(bool(job.get("recovery_in_progress"))),
            "job_completed": float(bool(job) and job.get("completed_time") is not None),
            **{f"general_{general}": float(job.get("general_state") == general) for general in ("intact", "defect", "scrap")},
            "product_weight": _bounded(product.get("weight")),
            "product_volume": _bounded(float(product.get("length", 0)) * float(product.get("width", 0)) * float(product.get("depth", 0))),
            "operation_duration": _bounded(operation.get("duration")),
            "operation_tool_consumption": _bounded(consumption),
            "machine_defect_probability": _bounded(machine.get("defect_probability", machine_config.get("defect_probability"))),
            "machine_processing_speed_factor": _bounded(machine.get("processing_speed_factor")),
            "machine_tool_matches": float(tool_id is not None and machine.get("mounted_tool_type_id") == tool_id),
            "machine_has_enough_tool_life": float(remaining is not None and consumption is not None and remaining >= consumption),
            "machine_remaining_tool_life": _bounded(remaining),
            "tool_mount_time": _bounded(tool.get("mount_time")), "tool_unmount_time": _bounded(tool.get("unmount_time")),
            "tool_total_life_units": _bounded(tool.get("total_life_units")),
            "target_store_count": _bounded(store.get("count")),
            "target_store_available_capacity": _bounded(store.get("available_capacity")),
            "target_store_capacity": _bounded(store.get("capacity")),
            "storage_in_time": _bounded(payload.get("storage_in_time")),
            "storage_out_time": _bounded(payload.get("storage_out_time")), "target_distance": _bounded(distance),
            "release_time_remaining": _bounded(float(payload["release_time"]) - time) if payload.get("release_time") is not None else 0.0,
            "job_reserved_by_pick": float(str(job.get("job_id")) in reserved),
        }
        for prefix in ("input", "output"):
            machine_store = machine.get(f"{prefix}_storage") or {}
            values[f"machine_{prefix}_count"] = _bounded(machine_store.get("count"))
            values[f"machine_{prefix}_available_capacity"] = _bounded(machine_store.get("available_capacity"))
        return values
