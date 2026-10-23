import importlib
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

import optimization
from SpineML import Configuration as configuration
from SpineML.Control.GeneralControl import RandomPolicy
from SpineML.Control.HeuristicControl import HeuristicWeights, SpineMLSimulationRunner
from SpineML.Control.Interface.InterfaceTypes import (
    ConfigurationObjectObserver,
    SimulationObjectObserver,
)
from SpineML.Simulation.SimMachine import SimMachine
from SpineML.Simulation.SimOrderJob import SimOrderJob


@pytest.fixture
def machine_model(monkeypatch):
    registry_names = (
        "MACHINE_TYPES", "TOOL_TYPES", "PRODUCT_TYPES", "OPERATION_TYPES",
        "SCENARIOS", "ORDERS", "LAYOUTS", "CORRIDORS", "MACHINES",
    )
    registries = [getattr(configuration, name) for name in registry_names]
    originals = [list(registry) for registry in registries]
    for registry in registries:
        registry.clear()
    monkeypatch.setattr(SimMachine, "QUALITY_SEED", SimMachine.QUALITY_SEED)
    try:
        machine_type = configuration.MachineType("machine type")
        tool = configuration.ToolType("tool", 1, 1, 100)
        raw = configuration.ProductType("raw", 1, 1, 1, 1)
        finished = configuration.ProductType("finished", 1, 1, 1, 1)
        operations = [
            configuration.OperationType(
                "operation A", 2, 1, machine_type, tool, raw, finished,
            ),
            configuration.OperationType(
                "operation B", 4, 2, machine_type, tool, raw, finished,
            ),
        ]
        scenario = configuration.Scenario("scenario")
        order = configuration.Order("order", 2, 0, 100, finished, scenario)
        layout = configuration.Layout("layout", 1, 1, 10)
        corridor = configuration.Corridor("corridor", 10, 1, 1, layout)
        machines = [
            configuration.Machine(
                "machine A", machine_type, corridor, True, 2, 2,
                defect_probability=0.05,
            ),
            configuration.Machine(
                "machine B", machine_type, corridor, False, 2, 2,
                defect_probability=0.35,
            ),
        ]
        yield SimpleNamespace(
            machine_type=machine_type, tool=tool, raw=raw, finished=finished,
            operations=operations, scenario=scenario, order=order, layout=layout,
            corridor=corridor, machines=machines,
        )
    finally:
        for registry, original in zip(registries, originals):
            registry[:] = original


@pytest.mark.parametrize("probability", [0.0, 0.05, 1.0])
def test_each_machine_accepts_its_own_probability(machine_model, probability):
    model = machine_model
    machine = configuration.Machine(
        "candidate", model.machine_type, model.corridor, True, 2, 2,
        defect_probability=probability,
    )

    assert machine.defect_probability == probability
    assert model.machines[0].defect_probability == 0.05
    assert model.machines[1].defect_probability == 0.35
    assert all(not hasattr(operation, "defect_probability") for operation in model.operations)


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan"), float("inf"), -float("inf")])
def test_invalid_machine_probability_is_rejected_before_registration(machine_model, probability):
    model = machine_model
    before = list(configuration.MACHINES)

    with pytest.raises(ValueError, match="defect_probability"):
        configuration.Machine(
            "invalid", model.machine_type, model.corridor, True, 2, 2,
            defect_probability=probability,
        )

    assert configuration.MACHINES == before


def test_probability_is_optional_on_machine_and_not_allowed_on_operation(machine_model):
    model = machine_model
    machine = configuration.Machine(
        "automatic", model.machine_type, model.corridor, True, 2, 2,
    )
    assert machine.defect_probability is None
    assert 0 <= machine.resolve_defect_probability(seed=101) < 1
    with pytest.raises(TypeError, match="defect_probability"):
        configuration.OperationType(
            "invalid", 2, 1, model.machine_type, model.tool, model.raw, model.finished,
            defect_probability=0.05,
        )


@pytest.mark.parametrize("seed", [1, 2, 101])
def test_explicit_machine_probability_is_independent_of_seed(machine_model, seed):
    assert machine_model.machines[0].resolve_defect_probability(seed) == 0.05
    assert machine_model.machines[1].resolve_defect_probability(seed) == 0.35


def test_automatic_machine_probability_depends_only_on_seed_and_machine(machine_model):
    first, second = machine_model.machines
    first.defect_probability = None
    second.defect_probability = None
    random_state = random.getstate()

    probability = first.resolve_defect_probability(seed=101)
    other_machine_probability = second.resolve_defect_probability(seed=101)
    other_seed_probability = first.resolve_defect_probability(seed=102)

    assert 0 <= probability < 1
    assert probability == first.resolve_defect_probability(seed=101)
    assert probability != other_machine_probability
    assert probability != other_seed_probability
    assert random.getstate() == random_state
    assert first.defect_probability is None
    assert second.defect_probability is None


def test_explicit_zero_does_not_trigger_random_probability(machine_model, monkeypatch):
    def unexpected_random(*args):
        raise AssertionError("An explicit probability must not be replaced by a random one")

    machine_model.machines[0].defect_probability = 0.0
    module = importlib.import_module("SpineML.Configuration.Solution.Machine")
    monkeypatch.setattr(module.random, "Random", unexpected_random)

    assert machine_model.machines[0].resolve_defect_probability(seed=101) == 0.0


@pytest.mark.parametrize("second_probability", [0.35, None])
def test_configuration_observer_publishes_machine_risk_not_operation_risk(
    machine_model, second_probability,
):
    model = machine_model
    model.machines[1].defect_probability = second_probability
    snapshot = ConfigurationObjectObserver.build_policy_configuration_model(
        [model.raw, model.finished], model.operations, model.machines,
        [model.tool], [model.corridor], [model.layout],
    )

    assert snapshot["machines_by_id"]["machine A"]["defect_probability"] == 0.05
    assert snapshot["machines_by_id"]["machine B"]["defect_probability"] == second_probability
    assert all(
        "defect_probability" not in operation
        for operation in snapshot["operations_by_id"].values()
    )


def quality_context(model, machine):
    component = SimpleNamespace(
        machine=machine, QUALITY_SEED=101,
        defect_probability=machine.resolve_defect_probability(seed=101),
    )
    job = SimpleNamespace(
        scenario=model.scenario, order=model.order, number=0, rework_count=0,
    )
    return component, job


@pytest.mark.parametrize(("probability", "expected"), [
    (0.0, None), (0.2, None), (0.4, None), (0.6, 0.7), (1.0, 0.7),
])
def test_quality_check_uses_machine_probability_for_every_operation(
    machine_model, monkeypatch, probability, expected,
):
    class FixedRandom:
        def __init__(self, seed):
            self.draws = iter((0.4, 0.7))

        def random(self):
            return next(self.draws)

    module = importlib.import_module("SpineML.Simulation.SimMachine")
    monkeypatch.setattr(module.random, "Random", FixedRandom)
    machine = machine_model.machines[0]
    machine.defect_probability = probability
    component, job = quality_context(machine_model, machine)

    for operation in machine_model.operations:
        assert SimMachine._sample_defect_severity(component, job, operation) == expected


def test_same_processing_context_reuses_draws_when_machine_choice_changes(machine_model, monkeypatch):
    seeds = []

    class RecordingRandom:
        def __init__(self, seed):
            seeds.append(seed)

        def random(self):
            return 0.99

    module = importlib.import_module("SpineML.Simulation.SimMachine")
    monkeypatch.setattr(module.random, "Random", RecordingRandom)
    component, job = quality_context(machine_model, machine_model.machines[0])
    operation = machine_model.operations[0]
    SimMachine._sample_defect_severity(component, job, operation)
    SimMachine._sample_defect_severity(component, job, operation)
    component.machine = machine_model.machines[1]
    component.defect_probability = component.machine.resolve_defect_probability(seed=101)
    SimMachine._sample_defect_severity(component, job, operation)
    job.rework_count += 1
    SimMachine._sample_defect_severity(component, job, operation)

    assert seeds[0] == seeds[1] == seeds[2]
    assert seeds[0] != seeds[3]


def test_same_operation_can_have_different_risk_on_two_machines(machine_model, monkeypatch):
    module = importlib.import_module("SpineML.Simulation.SimMachine")
    monkeypatch.setattr(
        module.random, "Random",
        lambda seed: SimpleNamespace(random=iter((0.2, 0.7)).__next__),
    )
    results = []
    for machine in machine_model.machines:
        component, job = quality_context(machine_model, machine)
        results.append(SimMachine._sample_defect_severity(
            component, job, machine_model.operations[0],
        ))

    assert results == [None, 0.7]


@pytest.mark.parametrize("random_policy", [False, True])
@pytest.mark.parametrize("probability", [0.0, 1.0])
def test_real_simulation_checks_machine_risk_without_operation_probability(
    machine_model, monkeypatch, random_policy, probability,
):
    model = machine_model
    for machine in model.machines:
        machine.defect_probability = probability
    defects = []
    mark_defective = SimOrderJob.mark_defective

    def capture_defect(job, *args, **kwargs):
        defects.append(kwargs["machine"])
        return mark_defective(job, *args, **kwargs)

    monkeypatch.setattr(SimOrderJob, "mark_defective", capture_defect)
    runner = SpineMLSimulationRunner(model.layout, model.scenario, till=1000)
    if random_policy:
        metrics = runner.run_policy(RandomPolicy(seed=101), seed=101)
    else:
        metrics = runner(HeuristicWeights(), seed=101)

    assert metrics.completed_jobs == metrics.total_jobs == 2
    assert metrics.unfinished_jobs == 0
    assert bool(defects) == (probability == 1.0)
    assert all(machine.defect_probability == probability for machine in defects)


def test_real_simulation_supports_fixed_and_seeded_auto_probabilities(machine_model, monkeypatch):
    model = machine_model
    model.machines[1].defect_probability = None
    runner = SpineMLSimulationRunner(model.layout, model.scenario, till=1000)
    sampled_by_run = []
    collect = runner.collect_global_metrics

    def capture_probabilities(layout, scenario, end_time):
        sampled = {}
        for machine in layout.simMachines():
            observed = SimulationObjectObserver.observe_machine(machine, end_time)
            assert observed["defect_probability"] == machine.defect_probability
            sampled[machine.machine.name] = machine.defect_probability
        sampled_by_run.append(sampled)
        return collect(layout, scenario, end_time)

    monkeypatch.setattr(runner, "collect_global_metrics", capture_probabilities)
    first = runner(HeuristicWeights(), seed=101)
    different_seed = runner(HeuristicWeights(), seed=102)
    repeated = runner(HeuristicWeights(), seed=101)
    random_metrics = runner.run_policy(RandomPolicy(seed=101), seed=101)

    assert first == repeated
    for metrics in (first, different_seed, repeated, random_metrics):
        assert metrics.completed_jobs == metrics.total_jobs == 2
    assert all(sampled["machine A"] == 0.05 for sampled in sampled_by_run)
    assert sampled_by_run[0] == sampled_by_run[2] == sampled_by_run[3]
    assert sampled_by_run[0]["machine B"] != sampled_by_run[1]["machine B"]
    assert sampled_by_run[0]["machine B"] == model.machines[1].resolve_defect_probability(101)
    assert model.machines[1].defect_probability is None


@pytest.mark.parametrize("filename", [
    "example-0.py", "example-1.py", "example-2.py", "example-3.py",
    "example-3b-quality.py", "example-5.py",
])
def test_working_examples_use_machine_probabilities(machine_model, filename):
    path = (
        Path(__file__).resolve().parents[1]
        / "sources" / "examples" / "normal" / filename
    )
    model = optimization._load_model(path)
    layout, scenario = optimization._find_layout_and_scenario(model, path)
    machines = [
        machine
        for corridor in layout.corridors
        for machine in corridor.machines_left + corridor.machines_right
    ]

    assert scenario.orders
    assert machines
    assert all(0 <= machine.defect_probability <= 1 for machine in machines)
    assert all(
        not hasattr(operation, "defect_probability")
        for machine in machines
        for operation in machine.machine_type.operations
    )
