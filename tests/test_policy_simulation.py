import pytest

from SpineML import Configuration as configuration
from SpineML.Control.GeneralControl import RandomPolicy
from SpineML.Control.HeuristicControl import HeuristicWeights, SpineMLSimulationRunner
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import LocalHeuristicActionEvaluator
from SpineML.Simulation.SimMachine import SimMachine


@pytest.fixture
def small_runner(monkeypatch):
    # Konfigurationsregister isolieren, damit diese Läufe keine anderen Modelle verändern.
    registries = [getattr(configuration, name) for name in (
        "MACHINE_TYPES", "TOOL_TYPES", "PRODUCT_TYPES", "OPERATION_TYPES",
        "SCENARIOS", "ORDERS", "LAYOUTS", "CORRIDORS", "MACHINES",
    )]
    previous = [list(registry) for registry in registries]
    for registry in registries:
        registry.clear()
    monkeypatch.setattr(SimMachine, "QUALITY_SEED", SimMachine.QUALITY_SEED)
    try:
        machine_type = configuration.MachineType("machine type")
        tool = configuration.ToolType("tool", 1, 1, 100)
        raw = configuration.ProductType("raw", 1, 1, 1, 1)
        finished = configuration.ProductType("finished", 1, 1, 1, 1)
        configuration.OperationType("operation", 2, 1, 0.0, machine_type, tool, raw, finished)
        scenario = configuration.Scenario("scenario")
        configuration.Order("order", 2, 0, 100, finished, scenario)
        layout = configuration.Layout("layout", 1, 1, 10)
        corridor = configuration.Corridor("corridor", 10, 1, 1, layout)
        configuration.Machine("machine A", machine_type, corridor, True, 2, 2)
        configuration.Machine("machine B", machine_type, corridor, False, 2, 2)
        yield SpineMLSimulationRunner(layout, scenario, till=1000)
    finally:
        for registry, original in zip(registries, previous):
            registry[:] = original


def assert_completed(metrics):
    assert metrics.total_jobs == metrics.completed_jobs == metrics.intact_jobs == 2
    assert metrics.unfinished_jobs == 0
    assert metrics.makespan > 0
    assert metrics.total_transport_time > 0


def test_random_policy_completes_real_bridge_simulation_without_evaluator(small_runner, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("RandomPolicy must not create or invoke a heuristic evaluator")

    monkeypatch.setattr(LocalHeuristicActionEvaluator, "__init__", forbidden)
    first = small_runner.run_policy(RandomPolicy(seed=101), seed=101)
    second = small_runner.run_policy(RandomPolicy(seed=101), seed=101)

    assert_completed(first)
    assert first == second


def test_heuristic_runner_remains_reproducible(small_runner):
    first = small_runner(HeuristicWeights(), seed=101)
    second = small_runner(HeuristicWeights(), seed=101)

    assert_completed(first)
    assert first == second
