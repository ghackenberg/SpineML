from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from ..Configuration import Layout, Order, ProductType


@dataclass(frozen=True, slots=True)
# Die Identitaet einer Produktionseinheit.
# Jede Order besteht aus mehreren Jobs bzw. Produktionseinheiten.

class JobKey:
    #jede Szenario mehrere orders
    scenario_name: str
    order_name: str
    job_number: int


#das ist das Ergebnis der Planung für den Job, Ausgabe vom Controller
@dataclass(slots=True)
class JobPlan:
    operation_sequence: list[Any]
    machine_sequence: list[Any]



@dataclass(frozen=True, slots=True)

## Anfrage an den Controller zur Planung eines Jobs.

class JobPlanningRequest:
    job_key: JobKey
    layout: Layout
    order: Order
    current_product_type: ProductType | None = None


@dataclass(frozen=True, slots=True)

## Zustandsbeobachtung eines Jobs am Kopf einer Queue.
class RoutingCandidate:
    operation_sequence: tuple[Any, ...]
    machine_sequence: tuple[Any, ...]
    route_score: float
    remaining_operations: int
    remaining_machines: int
    remaining_processing_time_estimate: float
    next_operation_name: str | None
    next_tool_name: str | None
    next_operation_duration: float | None
    next_consumed_life_units: int | None
    next_produced_product_name: str | None
    next_machine_name: str | None
    next_machine_corridor_name: str | None
    next_machine_side: Literal["left", "right"] | None


@dataclass(frozen=True, slots=True)
class JobHeadObservation:
    job_key: JobKey
    current_product_name: str
    current_product_weight: float
    current_product_length: float
    current_product_width: float
    current_product_depth: float
    is_defective: bool
    release_time: float
    due_time: float
    remaining_operations: int
    remaining_machines: int
    remaining_processing_time_estimate: float
    slack_time: float
    routing_candidates: tuple[RoutingCandidate, ...]
    next_operation_name: str | None
    next_tool_name: str | None
    next_operation_duration: float | None
    next_consumed_life_units: int | None
    next_produced_product_name: str | None
    next_machine_name: str | None
    next_machine_corridor_name: str | None
    next_machine_side: Literal["left", "right"] | None


@dataclass(frozen=True, slots=True)

## Beobachtung einer Queue mit ihrem Namen, ihrer Laenge
# und dem Job am Kopf der Warteschlange.
class QueueObject:
    queue_id: str
    length: int
    capacity: float
    free_capacity: float
    head: JobHeadObservation | None
    jobs: tuple[JobHeadObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class CorridorObservation:
    corridor_name: str
    main_queue: QueueObject
    left_queue: QueueObject
    right_queue: QueueObject


@dataclass(frozen=True, slots=True)
class ArmMachineObservation:
    machine_num: int
    machine_name: str
    input_queue: QueueObject
    output_queue: QueueObject


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    mount_time: float
    unmount_time: float
    total_life_units: int


@dataclass(frozen=True, slots=True)
class MainRobotObservation:
    actor_id: str
    name: str
    move_state: str
    load_state: str
    x: float
    y: float
    z: float
    busy: bool
    pending_commands: int
    start_queue: QueueObject
    end_queue: QueueObject
    corridors: tuple[CorridorObservation, ...]


@dataclass(frozen=True, slots=True)
class ArmRobotObservation:
    actor_id: str
    name: str
    corridor_name: str
    direction: str
    move_state: str
    load_state: str
    x: float
    y: float
    z: float
    busy: bool
    pending_commands: int
    input_queue: QueueObject
    out_arm_queue: QueueObject
    out_main_queue: QueueObject
    machine_slots: tuple[ArmMachineObservation, ...]


@dataclass(frozen=True, slots=True)
class MachineObservation:
    actor_id: str
    machine_name: str
    corridor_name: str
    side: Literal["left", "right"]
    state: str
    current_tool_name: str | None
    busy: bool
    pending_commands: int
    input_queue: QueueObject
    output_queue: QueueObject
    remaining_life_units: dict[str, int]
    available_tools: tuple[ToolSpec, ...]


@dataclass(frozen=True, slots=True)
class OrderJobObservation:
    job_key: JobKey
    current_product_name: str
    current_product_weight: float
    current_product_length: float
    current_product_width: float
    current_product_depth: float
    is_defective: bool
    released: bool
    completed: bool
    completion_time: float | None
    defect_time: float | None
    release_time: float
    due_time: float
    remaining_operations: int
    remaining_machines: int
    remaining_processing_time_estimate: float
    slack_time: float
    next_operation_name: str | None
    next_machine_name: str | None


@dataclass(frozen=True, slots=True)
class SystemObservation:
    time: float
    main_robots: tuple[MainRobotObservation, ...]
    arm_robots: tuple[ArmRobotObservation, ...]
    machines: tuple[MachineObservation, ...]
    order_jobs: tuple[OrderJobObservation, ...]



@dataclass(frozen=True, slots=True)
class MainRobotPickAction:
    kind: Literal["start", "corridor_main"]
    corridor_name: str | None = None


@dataclass(frozen=True, slots=True)
class MainRobotPlaceAction:
    kind: Literal["end", "corridor_in"]
    route: RoutingCandidate
    corridor_name: str | None = None
    side: Literal["left", "right"] | None = None


@dataclass(frozen=True, slots=True)
class ArmRobotPickAction:
    kind: Literal["store_in", "machine_out"]
    machine_num: int | None = None


@dataclass(frozen=True, slots=True)
class ArmRobotPlaceAction:
    kind: Literal["machine_in", "arm_out", "main_out"]
    route: RoutingCandidate
    machine_num: int | None = None


@dataclass(frozen=True, slots=True)
class ToolAction:
    state: Literal["mounting", "unmounting"]
    duration: float
    mount_tool_name: str | None = None


@dataclass(frozen=True, slots=True)
class MainRobotCommand:
    job_key: JobKey
    pick: MainRobotPickAction
    place: MainRobotPlaceAction


@dataclass(frozen=True, slots=True)
class ArmRobotCommand:
    job_key: JobKey
    pick: ArmRobotPickAction
    place: ArmRobotPlaceAction


@dataclass(frozen=True, slots=True)
class MachineCommand:
    job_key: JobKey
    expected_machine_name: str
    tool_name: str
    duration: float
    produced_product_name: str
    remaining_life_units_before: int
    remaining_life_units_after: int
    tool_actions: tuple[ToolAction, ...]


@dataclass(frozen=True, slots=True)

#das ist ein allgemeiner Befehl an einen Actor im System

class DispatchCommand:
    actor_id: str
    payload: MainRobotCommand | ArmRobotCommand | MachineCommand
