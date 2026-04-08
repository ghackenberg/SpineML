from __future__ import annotations

import importlib.util
import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import salabim as sim

from .Configuration import Layout, Scenario
from .Simulation import SimLayout, SimScenario
from .controller.default_controller import DefaultController
from .controller.greedy_controller import GreedyController
from .example_generator import PROFILE_NAMES, build_generated_example


@dataclass(slots=True)
class BenchmarkRuntimeStats:
    wip_area: float = 0.0


@dataclass(slots=True)
class OrderBenchmarkResult:
    order_name: str
    quantity: int
    release_time: float
    due_time: float
    completion_time: float | None
    tardiness: float
    defective_jobs: int
    completed_jobs: int


@dataclass(slots=True)
class BenchmarkRunResult:
    example_name: str
    controller_name: str
    seed: int | None
    till: float | None
    final_simulation_time: float
    makespan: float | None
    wall_clock_seconds: float
    all_orders_completed: bool
    total_orders: int
    completed_orders: int
    total_jobs: int
    completed_jobs: int
    defective_jobs: int
    total_tardiness: float
    average_tardiness: float
    max_tardiness: float
    throughput_jobs_per_time: float
    robot_utilization: float
    machine_utilization: float
    tool_change_count: int
    tool_change_time: float
    start_queue_length: int
    end_queue_length: int
    corridor_main_queue_length: int
    corridor_side_queue_length: int
    machine_input_queue_length: int
    machine_output_queue_length: int
    average_wip: float
    average_queue_wait_time: float
    max_queue_wait_time: float
    generated_profile: str | None = None
    generated_scale: int | None = None
    generated_instance_seed: int | None = None
    orders: list[OrderBenchmarkResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BenchmarkReport:
    created_at: str
    runs: list[BenchmarkRunResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "runs": [run.to_dict() for run in self.runs],
        }


CONTROLLER_REGISTRY = {
    "default": DefaultController,
    "greedy": GreedyController,
}

GENERATED_EXAMPLE_PREFIX = "generated:"


def _example_sources_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def available_examples() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.stem
            for path in _example_sources_dir().glob("example-*.py")
            if path.stem != "example-generated"
        )
    )


def available_generated_profiles() -> tuple[str, ...]:
    return PROFILE_NAMES


def make_generated_example_name(profile: str, scale: int, instance_seed: int) -> str:
    return f"{GENERATED_EXAMPLE_PREFIX}{profile}:scale={scale}:seed={instance_seed}"


def parse_generated_example_name(example_name: str) -> tuple[str, int, int] | None:
    if not example_name.startswith(GENERATED_EXAMPLE_PREFIX):
        return None

    parts = example_name.split(":")
    if len(parts) != 4:
        raise ValueError(
            "Generated example names must follow "
            "'generated:<profile>:scale=<int>:seed=<int>'"
        )

    _, profile, scale_part, seed_part = parts
    if profile not in PROFILE_NAMES:
        choices = ", ".join(PROFILE_NAMES)
        raise ValueError(f"Unknown generated profile '{profile}'. Expected one of: {choices}")
    if not scale_part.startswith("scale="):
        raise ValueError(f"Generated example name is missing scale=...: {example_name}")
    if not seed_part.startswith("seed="):
        raise ValueError(f"Generated example name is missing seed=...: {example_name}")

    try:
        scale = int(scale_part.split("=", 1)[1])
        instance_seed = int(seed_part.split("=", 1)[1])
    except ValueError as exc:
        raise ValueError(
            f"Generated example name must contain integer scale and seed: {example_name}"
        ) from exc

    if scale < 1:
        raise ValueError(f"Generated example scale must be >= 1: {example_name}")

    return profile, scale, instance_seed


def generated_example_names(
    profiles: Iterable[str],
    scales: Iterable[int],
    instance_seeds: Iterable[int],
) -> tuple[str, ...]:
    names: list[str] = []
    for profile in profiles:
        for scale in scales:
            for instance_seed in instance_seeds:
                names.append(
                    make_generated_example_name(profile, scale, instance_seed)
                )
    return tuple(names)


def reset_configuration_state() -> None:
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


def load_example_builder(example_name: str) -> Callable[[], Any]:
    path = _example_sources_dir() / f"{example_name}.py"
    if not path.exists():
        raise ValueError(f"Unknown example script: {example_name}")

    module_name = f"_spineml_benchmark_{example_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_example = getattr(module, "build_example", None)
    if build_example is None:
        raise ValueError(f"Example script {example_name} does not define build_example()")
    return build_example


def build_example_model(example_name: str) -> tuple[Layout, Scenario]:
    generated_spec = parse_generated_example_name(example_name)
    if generated_spec is not None:
        profile, scale, instance_seed = generated_spec
        layout, scenario, *_ = build_generated_example(
            seed=instance_seed,
            scale=scale,
            profile=profile,
            reset_state=True,
        )
        return layout, scenario

    reset_configuration_state()
    definition = load_example_builder(example_name)()
    if not isinstance(definition, tuple) or len(definition) < 2:
        raise ValueError(f"build_example() in {example_name} must return at least (layout, scenario)")
    layout, scenario = definition[0], definition[1]
    return layout, scenario


def _instantiate_controller(controller_class: type, env: sim.Environment, seed: int | None):
    try:
        return controller_class(env=env, rng_seed=seed)
    except TypeError:
        return controller_class(env=env)


def _seed_machine_rngs(sim_machines: list[Any], seed: int | None) -> None:
    if seed is None:
        return
    for index, sim_machine in enumerate(sim_machines):
        sim_machine.rng = random.Random(seed + 1000 + index)


def _all_orders_completed(sim_scenario: SimScenario) -> bool:
    return all(sim_order.completion_time is not None for sim_order in sim_scenario.sim_orders)


def _current_wip(sim_scenario: SimScenario, current_time: float) -> int:
    wip = 0
    for sim_order in sim_scenario.sim_orders:
        for job in sim_order.sim_jobs:
            if current_time < job.order.earliest_start_time:
                continue
            if job.completion_time is None:
                wip += 1
    return wip


def _run_until_finished(
    env: sim.Environment,
    sim_scenario: SimScenario,
    till: float,
    max_steps: int,
) -> BenchmarkRuntimeStats:
    steps = 0
    stats = BenchmarkRuntimeStats()
    while True:
        if _all_orders_completed(sim_scenario):
            return stats
        if steps >= max_steps:
            return stats

        current_time = env.now()
        next_event_time = env.peek()
        if next_event_time == sim.inf:
            return stats

        stop_time = next_event_time
        if till != sim.inf and next_event_time > till:
            stop_time = till

        if stop_time > current_time:
            stats.wip_area += _current_wip(sim_scenario, current_time) * (stop_time - current_time)

        if till != sim.inf and next_event_time > till:
            env.run(till=till)
            return stats

        env.step()
        steps += 1


def _collect_run_result(
    example_name: str,
    controller_name: str,
    seed: int | None,
    till: float | None,
    wall_clock_seconds: float,
    runtime_stats: BenchmarkRuntimeStats,
    env: sim.Environment,
    sim_layout: SimLayout,
    sim_scenario: SimScenario,
) -> BenchmarkRunResult:
    generated_spec = parse_generated_example_name(example_name)
    generated_profile = None
    generated_scale = None
    generated_instance_seed = None
    if generated_spec is not None:
        generated_profile, generated_scale, generated_instance_seed = generated_spec

    sim_machines = []
    for sim_corridor in sim_layout.sim_corridors:
        sim_machines.extend(sim_corridor.sim_arm_left.sim_machines)
        sim_machines.extend(sim_corridor.sim_arm_right.sim_machines)

    total_jobs = 0
    completed_jobs = 0
    defective_jobs = 0
    total_tardiness = 0.0
    max_tardiness = 0.0
    completed_orders = 0
    order_results: list[OrderBenchmarkResult] = []
    total_queue_wait_time = 0.0
    queue_wait_events = 0
    max_queue_wait_time = 0.0

    for sim_order in sim_scenario.sim_orders:
        order_job_count = len(sim_order.sim_jobs)
        order_completed_jobs = sum(1 for job in sim_order.sim_jobs if job.completion_time is not None)
        total_jobs += order_job_count
        completed_jobs += order_completed_jobs
        defective_jobs += sim_order.defective_job_count

        tardiness = sim_order.tardiness if sim_order.completion_time is not None else 0.0
        if sim_order.completion_time is not None:
            completed_orders += 1
            total_tardiness += tardiness
            max_tardiness = max(max_tardiness, tardiness)

        order_results.append(
            OrderBenchmarkResult(
                order_name=sim_order.order.name,
                quantity=sim_order.order.quantity,
                release_time=sim_order.order.earliest_start_time,
                due_time=sim_order.order.latest_end_time,
                completion_time=sim_order.completion_time,
                tardiness=tardiness,
                defective_jobs=sim_order.defective_job_count,
                completed_jobs=order_completed_jobs,
            )
        )

        for job in sim_order.sim_jobs:
            total_queue_wait_time += job.total_queue_wait_time
            queue_wait_events += job.queue_wait_events
            max_queue_wait_time = max(max_queue_wait_time, job.max_queue_wait_time)
            if job.queue_wait_active:
                ongoing_wait = max(0.0, env.now() - job.current_queue_entry_time)
                total_queue_wait_time += ongoing_wait
                queue_wait_events += 1
                max_queue_wait_time = max(max_queue_wait_time, ongoing_wait)

    corridor_main_queue_length = sum(sc.store_main.length() for sc in sim_layout.sim_corridors)
    corridor_side_queue_length = sum(
        sc.store_left.length() + sc.store_right.length() for sc in sim_layout.sim_corridors
    )
    machine_input_queue_length = sum(sm.store_in.length() for sm in sim_machines)
    machine_output_queue_length = sum(sm.store_out.length() for sm in sim_machines)
    tool_change_count = sum(sm.tool_change_count for sm in sim_machines)
    tool_change_time = sum(sm.tool_change_time for sm in sim_machines)
    all_orders_completed = completed_orders == len(sim_scenario.sim_orders)
    makespan = env.now() if all_orders_completed else None
    throughput_jobs_per_time = completed_jobs / env.now() if env.now() > 0 else 0.0
    average_tardiness = total_tardiness / completed_orders if completed_orders > 0 else 0.0
    average_wip = runtime_stats.wip_area / env.now() if env.now() > 0 else 0.0
    average_queue_wait_time = total_queue_wait_time / queue_wait_events if queue_wait_events > 0 else 0.0

    return BenchmarkRunResult(
        example_name=example_name,
        controller_name=controller_name,
        seed=seed,
        till=None if till == sim.inf else till,
        final_simulation_time=env.now(),
        makespan=makespan,
        wall_clock_seconds=wall_clock_seconds,
        all_orders_completed=all_orders_completed,
        total_orders=len(sim_scenario.sim_orders),
        completed_orders=completed_orders,
        total_jobs=total_jobs,
        completed_jobs=completed_jobs,
        defective_jobs=defective_jobs,
        total_tardiness=total_tardiness,
        average_tardiness=average_tardiness,
        max_tardiness=max_tardiness,
        throughput_jobs_per_time=throughput_jobs_per_time,
        robot_utilization=sim_layout.robotUtilization(),
        machine_utilization=sim_layout.machineUtilization(),
        tool_change_count=tool_change_count,
        tool_change_time=tool_change_time,
        start_queue_length=sim_layout.store_start.length(),
        end_queue_length=sim_layout.store_end.length(),
        corridor_main_queue_length=corridor_main_queue_length,
        corridor_side_queue_length=corridor_side_queue_length,
        machine_input_queue_length=machine_input_queue_length,
        machine_output_queue_length=machine_output_queue_length,
        average_wip=average_wip,
        average_queue_wait_time=average_queue_wait_time,
        max_queue_wait_time=max_queue_wait_time,
        generated_profile=generated_profile,
        generated_scale=generated_scale,
        generated_instance_seed=generated_instance_seed,
        orders=order_results,
    )


def run_benchmark(
    example_name: str,
    controller_class: type,
    seed: int | None = None,
    till: float = 200.0,
    max_steps: int = 1_000_000,
) -> BenchmarkRunResult:
    layout, scenario = build_example_model(example_name)

    sim.yieldless(False)
    env = sim.Environment(time_unit="hours")
    controller = _instantiate_controller(controller_class, env, seed)

    sim_layout = SimLayout(layout, scenario, controller=controller, env=env)
    sim_scenario = SimScenario(layout, scenario, sim_layout.store_start, controller=controller, env=env)

    sim_machines = []
    sim_arm_robots = []
    for sim_corridor in sim_layout.sim_corridors:
        sim_machines.extend(sim_corridor.sim_arm_left.sim_machines)
        sim_machines.extend(sim_corridor.sim_arm_right.sim_machines)
        if sim_corridor.sim_arm_left.machineCount() > 0:
            sim_arm_robots.append(sim_corridor.sim_arm_left.sim_arm_robot)
        if sim_corridor.sim_arm_right.machineCount() > 0:
            sim_arm_robots.append(sim_corridor.sim_arm_right.sim_arm_robot)

    _seed_machine_rngs(sim_machines, seed)

    sim_order_jobs = []
    for sim_order in sim_scenario.sim_orders:
        sim_order_jobs.extend(sim_order.sim_jobs)

    controller.attach(
        machines=sim_machines,
        order_jobs=sim_order_jobs,
        main_robots=[sim_layout.sim_main_robot],
        arm_robots=sim_arm_robots,
    )

    started = time.perf_counter()
    runtime_stats = _run_until_finished(env, sim_scenario, till=till, max_steps=max_steps)
    wall_clock_seconds = time.perf_counter() - started

    return _collect_run_result(
        example_name=example_name,
        controller_name=controller_class.__name__,
        seed=seed,
        till=till,
        wall_clock_seconds=wall_clock_seconds,
        runtime_stats=runtime_stats,
        env=env,
        sim_layout=sim_layout,
        sim_scenario=sim_scenario,
    )


def run_benchmark_suite(
    examples: Iterable[str],
    controllers: Iterable[str | type],
    seeds: Iterable[int | None],
    till: float = 200.0,
    max_steps: int = 1_000_000,
) -> BenchmarkReport:
    runs: list[BenchmarkRunResult] = []
    for example_name in examples:
        for controller in controllers:
            controller_class = CONTROLLER_REGISTRY[controller] if isinstance(controller, str) else controller
            for seed in seeds:
                runs.append(
                    run_benchmark(
                        example_name,
                        controller_class,
                        seed=seed,
                        till=till,
                        max_steps=max_steps,
                    )
                )

    return BenchmarkReport(
        created_at=datetime.now().isoformat(timespec="seconds"),
        runs=runs,
    )


def report_rows(report: BenchmarkReport) -> list[dict[str, Any]]:
    rows = []
    for run in report.runs:
        rows.append(
            {
                "example_name": run.example_name,
                "controller_name": run.controller_name,
                "seed": run.seed,
                "final_simulation_time": run.final_simulation_time,
                "makespan": run.makespan,
                "all_orders_completed": run.all_orders_completed,
                "total_orders": run.total_orders,
                "completed_orders": run.completed_orders,
                "total_jobs": run.total_jobs,
                "completed_jobs": run.completed_jobs,
                "defective_jobs": run.defective_jobs,
                "total_tardiness": run.total_tardiness,
                "average_tardiness": run.average_tardiness,
                "max_tardiness": run.max_tardiness,
                "throughput_jobs_per_time": run.throughput_jobs_per_time,
                "robot_utilization": run.robot_utilization,
                "machine_utilization": run.machine_utilization,
                "tool_change_count": run.tool_change_count,
                "tool_change_time": run.tool_change_time,
                "start_queue_length": run.start_queue_length,
                "end_queue_length": run.end_queue_length,
                "corridor_main_queue_length": run.corridor_main_queue_length,
                "corridor_side_queue_length": run.corridor_side_queue_length,
                "machine_input_queue_length": run.machine_input_queue_length,
                "machine_output_queue_length": run.machine_output_queue_length,
                "average_wip": run.average_wip,
                "average_queue_wait_time": run.average_queue_wait_time,
                "max_queue_wait_time": run.max_queue_wait_time,
                "generated_profile": run.generated_profile,
                "generated_scale": run.generated_scale,
                "generated_instance_seed": run.generated_instance_seed,
                "wall_clock_seconds": run.wall_clock_seconds,
            }
        )
    return rows


def order_rows(report: BenchmarkReport) -> list[dict[str, Any]]:
    rows = []
    for run in report.runs:
        for order in run.orders:
            rows.append(
                {
                    "example_name": run.example_name,
                    "controller_name": run.controller_name,
                    "seed": run.seed,
                    "order_name": order.order_name,
                    "quantity": order.quantity,
                    "release_time": order.release_time,
                    "due_time": order.due_time,
                    "completion_time": order.completion_time,
                    "tardiness": order.tardiness,
                    "defective_jobs": order.defective_jobs,
                    "completed_jobs": order.completed_jobs,
                }
            )
    return rows


def save_report(report: BenchmarkReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
