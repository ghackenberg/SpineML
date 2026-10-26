import ast
from pathlib import Path
import runpy

import pytest

import optimization
from SpineML import Configuration as configuration


EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "sources" / "examples" / "normal" / "example-5.py"
)


def test_only_example_five_is_available_and_selected_by_default():
    examples_directory = EXAMPLE_PATH.parents[1]
    assert sorted(examples_directory.rglob("example*.py")) == [EXAMPLE_PATH]
    assert optimization.EXAMPLE_FILE == EXAMPLE_PATH.name


@pytest.fixture
def complex_model():
    registry_names = (
        "MACHINE_TYPES", "TOOL_TYPES", "PRODUCT_TYPES", "OPERATION_TYPES",
        "SCENARIOS", "ORDERS", "LAYOUTS", "CORRIDORS", "MACHINES",
    )
    registries = [getattr(configuration, name) for name in registry_names]
    previous = [list(registry) for registry in registries]
    for registry in registries:
        registry.clear()
    try:
        model = runpy.run_path(str(EXAMPLE_PATH))
        yield model
    finally:
        for registry, original in zip(registries, previous):
            registry[:] = original


def test_optimizer_selects_the_complex_layout_and_scenario(complex_model):
    layout, scenario = optimization._find_layout_and_scenario(
        complex_model, EXAMPLE_PATH,
    )

    assert layout is complex_model["layout"]
    assert scenario is complex_model["scenario"]
    assert len(scenario.orders) == 8
    assert sum(order.quantity for order in scenario.orders) == 24
    assert len({order.product_type for order in scenario.orders}) == 3
    assert len({order.latest_end_time for order in scenario.orders}) == 8
    assert len(layout.corridors) == 3
    assert len(configuration.MACHINES) == 12


def test_complex_example_has_distinct_routes_and_usable_tools(complex_model):
    operations = configuration.OPERATION_TYPES
    machines = configuration.MACHINES

    assert len(operations) == 12
    assert len({operation.duration for operation in operations}) > 4
    assert len({operation.consumes_life_units for operation in operations}) > 3
    for operation in operations:
        assert not hasattr(operation, "defect_probability")
        assert 0 < operation.consumes_life_units <= operation.tool_type.total_life_units
        eligible = [
            machine for machine in machines
            if machine.machine_type is operation.machine_type
        ]
        assert len(eligible) == 3
        assert all(operation.tool_type in machine.tool_types for machine in eligible)
        assert len({machine.defect_probability for machine in eligible}) > 1

    assert all(0 < machine.defect_probability < 1 for machine in machines)

    for intermediate in (
        complex_model["base_body"], complex_model["milled_body"],
        complex_model["drilled_body"],
    ):
        assert len(intermediate.producing_operations) >= 2


def test_all_machines_declare_their_tool_types_explicitly(complex_model):
    tree = ast.parse(EXAMPLE_PATH.read_text(encoding="utf-8"))
    machine_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Machine"
    ]
    assert len(machine_calls) == 12
    for call in machine_calls:
        tool_list = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "tool_types"),
            None,
        )
        assert isinstance(tool_list, ast.List)
        assert tool_list.elts

    for machine in configuration.MACHINES:
        assert machine.tool_types == machine.machine_type.computeToolTypes()


def test_every_order_has_an_acyclic_route_to_raw_material(complex_model):
    def route_lengths(product, visited):
        assert product not in visited, "Product routes must not contain cycles"
        if not product.producing_operations:
            return {0}
        return {
            1 + length
            for operation in product.producing_operations
            for length in route_lengths(
                operation.consumes_product_type, visited | {product},
            )
        }

    lengths = set()
    for order in complex_model["scenario"].orders:
        product_lengths = route_lengths(order.product_type, set())
        assert min(product_lengths) >= 2
        lengths.update(product_lengths)
    assert lengths == {2, 3}
