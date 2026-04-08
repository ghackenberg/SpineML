from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from .Configuration import (
    Corridor,
    Layout,
    Machine,
    MachineType,
    OperationType,
    Order,
    ProductType,
    Scenario,
    ToolType,
)

GeneratedProfile = Literal[
    "balanced",
    "routing_heavy",
    "bottleneck_machine",
    "tool_change_heavy",
    "due_date_pressure",
    "defect_heavy",
]

PROFILE_NAMES: tuple[GeneratedProfile, ...] = (
    "balanced",
    "routing_heavy",
    "bottleneck_machine",
    "tool_change_heavy",
    "due_date_pressure",
    "defect_heavy",
)


@dataclass(frozen=True, slots=True)
class GeneratedExampleConfig:
    seed: int = 0
    scale: int = 2
    profile: GeneratedProfile = "balanced"
    reset_state: bool = True


def reset_generated_configuration_state() -> None:
    from .Configuration.Definition.MachineType import MACHINE_TYPES
    from .Configuration.Definition.OperationType import OPERATION_TYPES
    from .Configuration.Definition.ProductType import PRODUCT_TYPES
    from .Configuration.Definition.ToolType import TOOL_TYPES
    from .Configuration.Evaluation.Order import ORDERS
    from .Configuration.Evaluation.Scenario import SCENARIOS
    from .Configuration.Solution.Corridor import CORRIDORS
    from .Configuration.Solution.Layout import LAYOUTS
    from .Configuration.Solution.Machine import MACHINES

    PRODUCT_TYPES.clear()
    OPERATION_TYPES.clear()
    TOOL_TYPES.clear()
    MACHINE_TYPES.clear()
    ORDERS.clear()
    SCENARIOS.clear()
    CORRIDORS.clear()
    LAYOUTS.clear()
    MACHINES.clear()


def _normalize_profile(profile: str) -> GeneratedProfile:
    normalized = profile.strip().lower()
    if normalized not in PROFILE_NAMES:
        choices = ", ".join(PROFILE_NAMES)
        raise ValueError(f"Unknown generated example profile '{profile}'. Expected one of: {choices}")
    return normalized  # type: ignore[return-value]


def _profile_settings(profile: GeneratedProfile, scale: int) -> dict[str, float | int | bool]:
    settings: dict[str, float | int | bool] = {
        "corridors": scale + 2,
        "families": scale + 2,
        "orders": scale + 4,
        "layout_storage_capacity": 500 + 250 * scale,
        "corridor_storage_capacity": 100 + 30 * scale,
        "machine_storage_capacity": 1,
        "layout_in_time": 4,
        "layout_out_time": 6,
        "corridor_in_time": 2,
        "corridor_out_time": 2,
        "machine_in_time": 1,
        "machine_out_time": 1,
        "due_factor": 3.1,
        "defect_multiplier": 1.0,
        "shortcut_routes": False,
        "bottleneck_finish": False,
        "shared_machine_type": False,
        "extra_prep_machines": 0,
        "extra_finish_machines": 0,
    }

    if profile == "routing_heavy":
        settings.update(
            corridors=scale + 3,
            shortcut_routes=True,
            extra_prep_machines=1,
            extra_finish_machines=1,
            due_factor=3.4,
        )
    elif profile == "bottleneck_machine":
        settings.update(
            bottleneck_finish=True,
            due_factor=2.4,
        )
    elif profile == "tool_change_heavy":
        settings.update(
            shared_machine_type=True,
            shortcut_routes=True,
            extra_prep_machines=1,
            due_factor=3.0,
        )
    elif profile == "due_date_pressure":
        settings.update(
            shortcut_routes=True,
            due_factor=1.8,
        )
    elif profile == "defect_heavy":
        settings.update(
            defect_multiplier=2.2,
            due_factor=2.8,
        )

    return settings


def _build_machine_types(profile: GeneratedProfile) -> dict[str, MachineType]:
    if profile == "tool_change_heavy":
        shared = MachineType("Generated shared machine")
        return {
            "prep_a": shared,
            "prep_b": shared,
            "finish": shared,
            "flex": shared,
        }

    return {
        "prep_a": MachineType("Generated prep A"),
        "prep_b": MachineType("Generated prep B"),
        "finish": MachineType("Generated finish"),
        "flex": MachineType("Generated flex"),
    }


def _build_tool_types(scale: int) -> list[ToolType]:
    count = max(4, scale + 3)
    tools: list[ToolType] = []
    for index in range(count):
        tools.append(
            ToolType(
                f"Generated tool {index + 1}",
                1 + (index % 3),
                1 + ((index + 1) % 3),
                12 + index * 4,
            )
        )
    return tools


def _machine_counts_by_side(
    settings: dict[str, float | int | bool],
    corridor_index: int,
    corridor_count: int,
) -> dict[str, int]:
    extra_prep_machines = int(settings["extra_prep_machines"])
    extra_finish_machines = int(settings["extra_finish_machines"])
    bottleneck_finish = bool(settings["bottleneck_finish"])

    counts = {
        "prep_a_left": 1 + extra_prep_machines,
        "finish_left": 1 + extra_finish_machines,
        "prep_b_right": 1 + extra_prep_machines,
        "flex_right": 1 if bool(settings["shortcut_routes"]) else 0,
    }

    if bottleneck_finish:
        counts["finish_left"] = 1 if corridor_index == 0 else 0
        counts["flex_right"] = 1 if corridor_index < max(1, corridor_count // 2) else 0

    return counts


def build_generated_example(
    seed: int = 0,
    scale: int = 2,
    profile: GeneratedProfile | str = "balanced",
    *,
    reset_state: bool = True,
) -> tuple[Layout, Scenario, Layout, Order]:
    if scale < 1:
        raise ValueError("Generated example scale must be >= 1")

    profile_name = _normalize_profile(profile)
    if reset_state:
        reset_generated_configuration_state()

    rng = random.Random(seed)
    settings = _profile_settings(profile_name, scale)
    machine_types = _build_machine_types(profile_name)
    tool_types = _build_tool_types(scale)

    family_count = int(settings["families"])
    corridor_count = int(settings["corridors"])
    order_count = int(settings["orders"])
    due_factor = float(settings["due_factor"])
    defect_multiplier = float(settings["defect_multiplier"])

    raw_products: list[ProductType] = []
    route_targets: list[ProductType] = []

    for family_index in range(family_count):
        raw = ProductType(
            f"Generated raw {family_index + 1}",
            10 + rng.randint(0, 4),
            10 + rng.randint(0, 5),
            8 + rng.randint(0, 4),
            4 + rng.randint(0, 6),
        )
        mid_a = ProductType(
            f"Generated mid A {family_index + 1}",
            raw.length + rng.randint(0, 4),
            raw.width + rng.randint(0, 3),
            raw.depth + rng.randint(0, 2),
            raw.weight + rng.randint(1, 4),
        )
        mid_b = ProductType(
            f"Generated mid B {family_index + 1}",
            raw.length + rng.randint(1, 5),
            raw.width + rng.randint(0, 2),
            raw.depth + rng.randint(1, 3),
            raw.weight + rng.randint(1, 5),
        )
        final = ProductType(
            f"Generated final {family_index + 1}",
            max(mid_a.length, mid_b.length) + rng.randint(0, 3),
            max(mid_a.width, mid_b.width) + rng.randint(0, 3),
            max(mid_a.depth, mid_b.depth) + rng.randint(0, 3),
            max(mid_a.weight, mid_b.weight) + rng.randint(1, 4),
        )

        raw_products.append(raw)
        route_targets.append(final)

        prep_tool = tool_types[family_index % len(tool_types)]
        alt_prep_tool = tool_types[(family_index + 1) % len(tool_types)]
        finish_tool = tool_types[(family_index + 2) % len(tool_types)]
        alt_finish_tool = tool_types[(family_index + 3) % len(tool_types)]

        prep_duration = 2 + rng.randint(0, 3)
        alt_prep_duration = prep_duration + rng.randint(0, 2)
        finish_duration = 3 + rng.randint(0, 3)
        alt_finish_duration = finish_duration + rng.randint(0, 2)

        OperationType(
            f"Generated prep A {family_index + 1}",
            prep_duration,
            3 + rng.randint(0, 3),
            min(0.45, (0.04 + rng.random() * 0.08) * defect_multiplier),
            machine_types["prep_a"],
            prep_tool,
            raw,
            mid_a,
        )
        OperationType(
            f"Generated prep B {family_index + 1}",
            alt_prep_duration,
            3 + rng.randint(0, 4),
            min(0.45, (0.05 + rng.random() * 0.10) * defect_multiplier),
            machine_types["prep_b"],
            alt_prep_tool,
            raw,
            mid_b,
        )
        OperationType(
            f"Generated finish A {family_index + 1}",
            finish_duration,
            4 + rng.randint(0, 4),
            min(0.45, (0.03 + rng.random() * 0.07) * defect_multiplier),
            machine_types["finish"],
            finish_tool,
            mid_a,
            final,
        )
        OperationType(
            f"Generated finish B {family_index + 1}",
            alt_finish_duration,
            4 + rng.randint(0, 4),
            min(0.45, (0.04 + rng.random() * 0.08) * defect_multiplier),
            machine_types["finish"],
            alt_finish_tool,
            mid_b,
            final,
        )

        if bool(settings["shortcut_routes"]):
            shortcut_tool = tool_types[(family_index + 4) % len(tool_types)]
            OperationType(
                f"Generated shortcut {family_index + 1}",
                finish_duration + alt_prep_duration + rng.randint(1, 3),
                6 + rng.randint(0, 5),
                min(0.45, (0.05 + rng.random() * 0.10) * defect_multiplier),
                machine_types["flex"],
                shortcut_tool,
                raw,
                final,
            )

    scenario = Scenario(
        f"Generated scenario ({profile_name}, seed={seed}, scale={scale})"
    )
    layout = Layout(
        f"Generated layout ({profile_name}, seed={seed}, scale={scale})",
        int(settings["layout_out_time"]),
        int(settings["layout_in_time"]),
        int(settings["layout_storage_capacity"]),
    )

    corridors = [
        Corridor(
            f"Generated corridor {corridor_index + 1}",
            int(settings["corridor_storage_capacity"]),
            int(settings["corridor_out_time"]),
            int(settings["corridor_in_time"]),
            layout,
        )
        for corridor_index in range(corridor_count)
    ]

    for corridor_index, corridor in enumerate(corridors):
        machine_counts = _machine_counts_by_side(settings, corridor_index, corridor_count)

        for machine_index in range(machine_counts["prep_a_left"]):
            Machine(
                f"PrepA-{corridor_index + 1}-{machine_index + 1}",
                machine_types["prep_a"],
                corridor,
                True,
                int(settings["machine_storage_capacity"]),
                int(settings["machine_out_time"]),
                int(settings["machine_in_time"]),
            )

        for machine_index in range(machine_counts["finish_left"]):
            Machine(
                f"Finish-{corridor_index + 1}-{machine_index + 1}",
                machine_types["finish"],
                corridor,
                True,
                int(settings["machine_storage_capacity"]),
                int(settings["machine_out_time"]),
                int(settings["machine_in_time"]),
            )

        for machine_index in range(machine_counts["prep_b_right"]):
            Machine(
                f"PrepB-{corridor_index + 1}-{machine_index + 1}",
                machine_types["prep_b"],
                corridor,
                False,
                int(settings["machine_storage_capacity"]),
                int(settings["machine_out_time"]),
                int(settings["machine_in_time"]),
            )

        for machine_index in range(machine_counts["flex_right"]):
            Machine(
                f"Flex-{corridor_index + 1}-{machine_index + 1}",
                machine_types["flex"],
                corridor,
                False,
                int(settings["machine_storage_capacity"]),
                int(settings["machine_out_time"]),
                int(settings["machine_in_time"]),
            )

    route_order: Order | None = None
    for order_index in range(order_count):
        product = route_targets[order_index % len(route_targets)]
        release_time = rng.randint(0, 4 * scale) + order_index * rng.randint(0, 2)
        quantity = 2 + scale + rng.randint(0, 3 + scale)
        due_window = int(
            due_factor * (8 + scale * 3 + rng.randint(0, 6))
        )
        order = Order(
            f"Generated order {order_index + 1}",
            quantity,
            release_time,
            release_time + max(8, due_window),
            product,
            scenario,
        )
        if route_order is None:
            route_order = order

    if route_order is None:
        raise RuntimeError("Generated example did not create any orders")

    return layout, scenario, layout, route_order

