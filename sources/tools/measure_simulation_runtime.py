"""Vergleicht die echte Batch-Rechenzeit unabhängiger Example-5-Läufe."""

from __future__ import annotations

import argparse
import cProfile
from dataclasses import asdict
import json
from pathlib import Path
import pstats
from statistics import mean
import sys
from time import perf_counter

SOURCES_DIRECTORY = Path(__file__).resolve().parents[1]
if sys.path[:1] != [str(SOURCES_DIRECTORY)]:
    sys.path.insert(0, str(SOURCES_DIRECTORY))

from SpineML.Control.HeuristicPolicy.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicPolicy.HeuristicPolicyFactory import HeuristicPolicyFactory
from SpineML.SimulationExecution.ModelLoader import load_layout_and_scenario
from SpineML.SimulationExecution.ParallelSimulationRunner import (
    ParallelSimulationRunner,
    SimulationRunRequest,
    SimulationRunResult,
)
from SpineML.SimulationExecution.SimulationRunner import SimulationRunner


MODEL_FILE = (
    SOURCES_DIRECTORY / "examples" / "normal" / "example-5.py"
)
DEFAULT_SEEDS = (1, 2, 3, 4, 5)


def positive_int(value: str) -> int:
    """Verlangt positive Workerzahlen und Wiederholungszahlen."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Der Wert muss größer als 0 sein.")
    return number


def measure_batch(
    requests: tuple[SimulationRunRequest, ...],
    workers: int,
) -> tuple[tuple[SimulationRunResult, ...], float]:
    """Misst den vollständigen Kontext einschließlich Start und Shutdown."""
    completed_count = 0

    def on_completed(index: int, result: SimulationRunResult) -> None:
        nonlocal completed_count
        completed_count += 1
        print(
            f"  Fertig {completed_count}/{len(requests)}: "
            f"Input {index + 1}, Seed {requests[index].seed}, "
            f"PID {result.worker_pid}, Laufzeit {result.elapsed_seconds:.3f} s",
            flush=True,
        )

    print(f"\nStarte Batch mit {workers} Worker(n) ...", flush=True)
    started_at = perf_counter()
    with ParallelSimulationRunner(MODEL_FILE, max_workers=workers) as runner:
        results = runner.run_many(requests, on_completed=on_completed)
    elapsed_seconds = perf_counter() - started_at
    return results, elapsed_seconds


def compare_metrics(
    requests: tuple[SimulationRunRequest, ...],
    reference: tuple[SimulationRunResult, ...],
    actual: tuple[SimulationRunResult, ...],
    workers: int,
) -> None:
    """Vergleicht jede Kennzahl je ursprünglichem Input ohne Rundung/Toleranz."""
    if len(actual) != len(requests) or len(reference) != len(requests):
        raise RuntimeError(f"Unvollständiger Ergebnisstapel bei {workers} Workern.")
    for index, (expected, result) in enumerate(zip(reference, actual)):
        expected_metrics = asdict(expected.metrics)
        actual_metrics = asdict(result.metrics)
        if actual_metrics != expected_metrics:
            differences = {
                name: {"reference": expected_metrics[name], "actual": value}
                for name, value in actual_metrics.items()
                if value != expected_metrics[name]
            }
            raise RuntimeError(
                f"Kennzahlen weichen bei {workers} Workern ab: "
                f"Input {index + 1}, Seed {requests[index].seed}: {differences}"
            )


def profile_run(weights: HeuristicWeights, seed: int) -> None:
    """Profiliert einen separaten direkten Lauf außerhalb aller Batch-Timer."""
    print(
        f"\nZusätzlicher direkter Profiling-Lauf mit Seed {seed} "
        "(nicht in den Batchzeiten enthalten).",
        flush=True,
    )
    layout, scenario = load_layout_and_scenario(MODEL_FILE)
    runner = SimulationRunner(layout, scenario)
    profiler = cProfile.Profile()
    profiler.runcall(runner.run_policy, HeuristicPolicyFactory(weights)(seed), seed)
    pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(20)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Vergleicht identische vollständige Example-5-Simulationsbatches "
            "ohne 3D-Anzeige mit verschiedenen Workerzahlen."
        ),
    )
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS),
        help="Seeds des Taskstapels (Standard: 1 2 3 4 5).",
    )
    parser.add_argument(
        "--workers", type=positive_int, nargs="+", default=[1],
        help="Zu vergleichende Workerzahlen (Standard: 1); keine weiteren Modi.",
    )
    parser.add_argument(
        "--repeats", type=positive_int, default=1,
        help="Wiederholt den Seed-Taskstapel innerhalb jedes Batches (Standard: 1).",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Schreibt den gemessenen Vergleich mit allen Kennzahlen als JSON.",
    )
    parser.add_argument(
        "--profile", action="store_true",
        help="Analysiert anschließend einen separaten direkten Lauf mit cProfile.",
    )
    args = parser.parse_args()

    weights = HeuristicWeights()
    policy_factory = HeuristicPolicyFactory(weights)
    requests = tuple(
        SimulationRunRequest(policy_factory, seed)
        for _ in range(args.repeats)
        for seed in args.seeds
    )
    # Nur angeforderte Modi messen. Falls enthalten, dient ein Worker als Referenz.
    worker_counts = list(dict.fromkeys(args.workers))
    if 1 in worker_counts:
        worker_counts.remove(1)
        worker_counts.insert(0, 1)
    reference_workers = worker_counts[0]
    print(f"Modell: {MODEL_FILE}")
    print("Steuerung: Heuristik mit Standardgewichtssatz, ohne 3D-Anzeige.")
    print(f"Identische Tasks je Batch: {len(requests)}; Workerzahlen: {worker_counts}.")
    print(f"Kennzahlen- und Speedup-Referenz: {reference_workers} Worker.")
    print("Batch-Wallzeit umfasst Modellladen, Poolstart, Läufe und Shutdown.")
    print("Laufzeiten je Task sind Zusatzinformationen, keine Batchzeit.", flush=True)

    measurements = []
    reference: tuple[SimulationRunResult, ...] | None = None
    for workers in worker_counts:
        results, total_seconds = measure_batch(requests, workers)
        if reference is None:
            reference = results
        compare_metrics(requests, reference, results, workers)
        durations = [result.elapsed_seconds for result in results]
        measurements.append({
            "workers": workers,
            "total_seconds": total_seconds,
            "run_seconds": {
                "mean": mean(durations), "min": min(durations), "max": max(durations),
            },
            "metrics_match_reference": True,
            "results": [
                {
                    "input_index": index,
                    "repeat": index // len(args.seeds) + 1,
                    "seed": requests[index].seed,
                    "policy_kind": "heuristic",
                    "elapsed_seconds": result.elapsed_seconds,
                    "worker_pid": result.worker_pid,
                    "metrics": asdict(result.metrics),
                }
                for index, result in enumerate(results)
            ],
        })
        print(
            f"Batch gesamt: {total_seconds:.3f} s; alle Kennzahlen exakt gleich.",
            flush=True,
        )

    reference_seconds = measurements[0]["total_seconds"]
    for measurement in measurements:
        measurement["speedup"] = reference_seconds / measurement["total_seconds"]
    fastest = min(measurements, key=lambda item: item["total_seconds"])
    report = {
        "model_file": MODEL_FILE.name,
        "seeds": args.seeds,
        "repeats": args.repeats,
        "tasks_per_batch": len(requests),
        "weights": asdict(weights),
        "worker_counts": worker_counts,
        "reference_workers": reference_workers,
        "metrics_match_reference": True,
        "measurements": measurements,
        "fastest": {
            "workers": fastest["workers"],
            "total_seconds": fastest["total_seconds"],
            "speedup": fastest["speedup"],
        },
    }
    print("\nVergleich nach vollständiger Batch-Wallzeit:")
    for measurement in measurements:
        print(
            f"  {measurement['workers']:>3} Worker: "
            f"{measurement['total_seconds']:.3f} s; "
            f"Speedup gegen {reference_workers} Worker: {measurement['speedup']:.3f}x"
        )
    print(
        f"Schnellster gemessener Wert: {fastest['workers']} Worker, "
        f"{fastest['total_seconds']:.3f} s. Keine allgemeine Hardwareempfehlung."
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON-Bericht: {args.output.resolve()}")
    if args.profile:
        profile_run(weights, args.seeds[0])


if __name__ == "__main__":
    main()
