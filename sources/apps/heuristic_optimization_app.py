"""Weboberfläche und Ablaufsteuerung für die heuristische Gewichtssuche."""

from __future__ import annotations

import os
import hashlib
import json
import math
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

SOURCES_DIRECTORY = Path(__file__).resolve().parents[1]
if sys.path[:1] != [str(SOURCES_DIRECTORY)]:
    sys.path.insert(0, str(SOURCES_DIRECTORY))

# Spawn lädt dieses Hauptmodul erneut, benötigt dort aber keine Weboberfläche.
if __name__ != "__mp_main__":
    import altair as alt
    import pandas as pd
    import streamlit as st


EXAMPLE_FILE = "example-5.py"
MAX_WORKERS = min(os.cpu_count() or 1, 20)
SEEDS = [1, 2]
# Nur für den abschließenden Vergleich, nicht für die Gewichtssuche.
TEST_SEEDS = [101, 102, 103, 104, 105]
ITERATIONS = 2
INITIAL_WEIGHT_STEP = 0.40
EXPLORATION_CANDIDATES = 3
RESTART_AFTER_NO_IMPROVEMENT = 2
STOP_AFTER_NO_IMPROVEMENT = 4

# Diese Kennzahlen gehen in die globale Bewertung ein.
SCORED_METRICS = (
    "Makespan",
    "Total job tardiness",
    "Transport time",
    "Tool change time",
    "Rework rate (%)",
    "Scrap rate (%)",
    "Downgrade rate (%)",
)

JOB_RATE_METRICS = (
    "Rework rate (%)",
    "Scrap rate (%)",
    "Downgrade rate (%)",
)


# Definiert die unveränderten globalen Produktionsziele für den Elternprozess.
def _global_evaluation() -> GlobalSimulationEvaluation:
    return GlobalSimulationEvaluation(
        GlobalSimulationWeights(
            # Weight für die gesamte Durchlaufzeit bis zum letzten Abschluss.
            makespan=5.0,
            # Weight für die aufsummierten positiven Verspätungen einzelner Jobs.
            total_tardiness=4.0,
            # Weight für die gesamte Transportzeit aller Roboter.
            total_transport_time=1.0,
            # Weight für Werkzeugwechsel sowie Montage- und Demontagezeiten.
            tool_change_time=1.0,
            # Strafe für den Anteil der Jobs, die nachgearbeitet wurden.
            rework_job_penalty=3.0,
            # Strafe für den Anteil der Jobs, die als Scrap endeten.
            scrap_job_penalty=4.0,
            # Penalize the share of downgraded jobs.
            downgrade_job_penalty=3.0,
        )
    )


# Erstellt den Optimierer, ohne die Modelldefinition im Elternprozess zu laden.
def create_optimizer(model_file: str, execution_mode: str = "parallel"):
    """Wählt nur die Ausführungsart; Suche, Simulation und Bewertung bleiben gleich."""
    model_path = _resolve_model_path(model_file)
    if execution_mode == "sequential":
        layout, scenario = load_layout_and_scenario(model_path)
        runner = SimulationRunner(layout, scenario)
    elif execution_mode == "parallel":
        runner = ParallelSimulationRunner(model_path, max_workers=MAX_WORKERS)
    else:
        raise ValueError("execution_mode muss 'sequential' oder 'parallel' sein.")
    return LocalHeuristicWeightOptimizer(
        simulation_runner=runner,
        global_evaluation=_global_evaluation(),
    )


def _optimization_configuration(model_file, timing_context="streamlit"):
    """Kennzeichnet dieselbe Arbeitslast unabhängig von ihrer Ausführungsart."""
    source_directory = SOURCES_DIRECTORY
    model_path = _resolve_model_path(model_file)
    source_hash = hashlib.sha256()
    source_files = [Path(__file__).resolve(), *sorted(
        (source_directory / "SpineML").rglob("*.py")
    )]
    for source_file in source_files:
        source_hash.update(str(source_file.relative_to(source_directory)).encode("utf-8"))
        source_hash.update(b"\0")
        source_hash.update(source_file.read_bytes())
        source_hash.update(b"\0")
    return {
        "model_file": model_path.name,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "source_sha256": source_hash.hexdigest(),
        "python_version": sys.version,
        "salabim_version": version("salabim"),
        "platform": sys.platform,
        "processor": os.environ.get("PROCESSOR_IDENTIFIER"),
        "logical_processors": os.cpu_count(),
        "timing_context": timing_context,
        "seeds": list(SEEDS),
        "test_seeds": list(TEST_SEEDS),
        "iterations": ITERATIONS,
        "initial_weight_step": INITIAL_WEIGHT_STEP,
        "exploration_candidates": EXPLORATION_CANDIDATES,
        "restart_after_no_improvement": RESTART_AFTER_NO_IMPROVEMENT,
        "stop_after_no_improvement": STOP_AFTER_NO_IMPROVEMENT,
        "initial_weights": asdict(HeuristicWeights()),
        "global_weights": asdict(_global_evaluation().weights),
    }


def compare_optimization_reports(sequential, parallel):
    """Berechnet einen Zeitvorteil nur bei identischen Aufgaben und Ergebnissen."""
    if (sequential.get("execution_mode") != "sequential"
            or parallel.get("execution_mode") != "parallel"):
        return {"comparable": False, "reason": "Expected one sequential and one parallel report."}
    if sequential["configuration"] != parallel["configuration"]:
        return {"comparable": False, "reason": "Configuration or source code differs."}
    if sequential["results"] != parallel["results"]:
        return {"comparable": False, "reason": "Simulation or optimization results differ."}
    if sequential["simulation_count"] != parallel["simulation_count"]:
        return {"comparable": False, "reason": "Simulation counts differ."}
    serial_seconds = sequential["elapsed_seconds"]
    parallel_seconds = parallel["elapsed_seconds"]
    if (not math.isfinite(serial_seconds) or not math.isfinite(parallel_seconds)
            or serial_seconds <= 0 or parallel_seconds <= 0):
        return {"comparable": False, "reason": "A complete positive timing is missing."}
    return {
        "comparable": True,
        "results_identical": True,
        "sequential_seconds": serial_seconds,
        "parallel_seconds": parallel_seconds,
        "speedup": serial_seconds / parallel_seconds,
        "saved_seconds": serial_seconds - parallel_seconds,
        "saved_percent": (1.0 - parallel_seconds / serial_seconds) * 100.0,
    }


# Berechnet den Mittelwert einer Kennzahl über alle Seeds.
def _mean_metric(metrics_by_seed, attribute_name: str) -> float:
    total_value = 0.0
    for metrics in metrics_by_seed:
        total_value += float(getattr(metrics, attribute_name))
    return total_value / len(metrics_by_seed)


# Zeichnet die mittleren globalen Kosten je Kandidat.
def global_costs_per_candidate(costs, container=None):
    if not costs:
        return
    data = pd.DataFrame(
        {
            "Candidate": range(1, len(costs) + 1),
            "Mean global cost": costs,
        }
    )
    chart = (
        alt.Chart(data)
        .mark_line(point=True, color="#f28e2b")
        .encode(
            x=alt.X("Candidate:Q", title="Candidate"),
            y=alt.Y(
                "Mean global cost:Q",
                title="Mean global cost",
                scale=alt.Scale(zero=False),
            ),
            tooltip=["Candidate:Q", "Mean global cost:Q"],
        )
        .interactive()
    )
    target = st if container is None else container
    target.altair_chart(chart, use_container_width=True)


# Zeichnet die mittleren Kennzahlen je Kandidat.
def mean_metrics_per_candidate(metrics, container=None):
    if not metrics:
        return
    frame = pd.DataFrame(metrics)
    frame = frame.melt(
        id_vars=["Candidate"],
        value_vars=SCORED_METRICS,
        var_name="Metric",
        value_name="Value",
    )
    chart = (
        alt.Chart(frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Candidate:Q", title="Candidate"),
            y=alt.Y(
                "Value:Q",
                title="Mean across seeds",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color("Metric:N", title="Metric"),
            facet=alt.Facet("Metric:N", columns=2, title=None),
            tooltip=["Candidate:Q", "Metric:N", "Value:Q"],
        )
        .properties(height=180)
        .resolve_scale(y="independent")
        .interactive()
    )
    target = st if container is None else container
    target.altair_chart(chart, use_container_width=True)


def _candidate_metric_changes(metrics):
    """Trennt relative Zeitänderungen von Quotendifferenzen in Prozentpunkten."""
    frame = pd.DataFrame(metrics)[["Candidate", *SCORED_METRICS]].copy()
    frame = frame.sort_values("Candidate")
    reference = frame.iloc[0]
    changes = frame.melt(
        id_vars=["Candidate"],
        value_vars=SCORED_METRICS,
        var_name="Metric",
        value_name="Mean value",
    )
    changes["Reference mean"] = changes["Metric"].map(reference)
    changes["Change"] = changes["Mean value"] - changes["Reference mean"]
    is_rate = changes["Metric"].isin(JOB_RATE_METRICS)
    rate_changes = changes.loc[is_rate].copy()
    time_changes = changes.loc[~is_rate].copy()
    zero_reference = time_changes["Reference mean"] == 0.0
    zero_time_metrics = tuple(time_changes.loc[zero_reference, "Metric"].unique())
    # Gegenüber einer Zeitreferenz null ist keine relative Änderung definiert.
    # Die absoluten Werte bleiben erhalten; keine künstliche Nullkurve zeichnen.
    time_changes.loc[zero_reference, "Change"] = float("nan")
    valid_reference = ~zero_reference
    time_changes.loc[valid_reference, "Change"] = (
        time_changes.loc[valid_reference, "Change"]
        / time_changes.loc[valid_reference, "Reference mean"].abs()
        * 100.0
    )
    return time_changes, rate_changes, zero_time_metrics


# Zeichnet Zeiten in relativen Prozent und Jobquoten getrennt in Prozentpunkten.
def metric_deviation_from_candidate_1(metrics, container=None):
    if not metrics:
        return
    time_changes, rate_changes, zero_time_metrics = _candidate_metric_changes(metrics)
    time_note = "Compared with candidate 1; negative values mean lower times."
    if zero_time_metrics:
        time_note += (
            " No relative curve for zero reference: "
            + ", ".join(zero_time_metrics)
            + ". See the absolute values in Mean metrics per candidate."
        )
    time_chart = (
        alt.Chart(time_changes)
        .mark_line(point=True)
        .encode(
            x=alt.X("Candidate:Q", title="Candidate"),
            y=alt.Y("Change:Q", title="Time change from candidate 1 (%)"),
            color=alt.Color("Metric:N", title="Time metric"),
            tooltip=[
                "Candidate:Q", "Metric:N", "Mean value:Q", "Reference mean:Q",
                alt.Tooltip("Change:Q", title="Change (%)", format=".3f"),
            ],
        )
        .properties(
            height=220,
            title=alt.TitleParams(text="Relative change in time metrics", subtitle=time_note),
        )
        .interactive(name="time_metric_zoom")
    )
    rate_chart = (
        alt.Chart(rate_changes)
        .mark_line(point=True)
        .encode(
            x=alt.X("Candidate:Q", title="Candidate"),
            y=alt.Y("Change:Q", title="Rate change from candidate 1 (percentage points)"),
            color=alt.Color("Metric:N", title="Job rate"),
            tooltip=[
                "Candidate:Q", "Metric:N",
                alt.Tooltip("Mean value:Q", title="Mean rate (%)"),
                alt.Tooltip("Reference mean:Q", title="Reference rate (%)"),
                alt.Tooltip("Change:Q", title="Change (percentage points)", format=".3f"),
            ],
        )
        .properties(
            height=220,
            title=alt.TitleParams(
                text="Change in job rates",
                subtitle="Difference in percentage points: 0% to 5% is +5 percentage points.",
            ),
        )
        .interactive(name="job_rate_zoom")
    )
    chart = alt.vconcat(time_chart, rate_chart, spacing=30).resolve_scale(color="independent")
    target = st if container is None else container
    target.altair_chart(chart, use_container_width=True)


# Vergleicht Zufallspolicy, Standardheuristik und optimierte Heuristik.
def compare_baseline_optimized(benchmark):
    if not benchmark:
        return

    rows = []
    for label, seed_rows in benchmark.items():
        for row in seed_rows:
            item = dict(row)
            item["Control"] = label
            rows.append(item)

    frame = pd.DataFrame(rows)
    metric_names = [
        *SCORED_METRICS,
        "Weighted sum of metrics relative to baseline",
    ]
    mean_frame = frame.groupby(
        "Control",
        as_index=False,
    )[metric_names].mean()

    st.subheader("Comparison: random vs. default vs. optimized heuristic")
    st.caption(
        "Held-out benchmark seeds (not used for weight optimization). "
        "Random selects non-wait actions uniformly; waiting is a fallback."
    )
    st.dataframe(mean_frame, use_container_width=True, hide_index=True)

    chart_frame = frame.melt(
        id_vars=["Seed", "Control"],
        value_vars=metric_names,
        var_name="Metric",
        value_name="Value",
    )
    chart = (
        alt.Chart(chart_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Seed:O", title="Seed"),
            y=alt.Y("Value:Q", title="Value", scale=alt.Scale(zero=False)),
            color=alt.Color("Control:N", title="Control"),
            facet=alt.Facet("Metric:N", columns=3, title=None),
            tooltip=[
                "Seed:O",
                "Control:N",
                "Metric:N",
                "Value:Q",
            ],
        )
        .properties(height=180)
        .resolve_scale(y="independent")
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)


# Erstellt eine Ergebniszeile; alle globalen Kosten werden im Elternprozess berechnet.
def _global_metric_row(seed, metrics, global_evaluation):
    return {
        "Seed": seed,
        "Makespan": metrics.makespan,
        "Total job tardiness": metrics.total_tardiness,
        "Transport time": metrics.total_transport_time,
        "Tool change time": metrics.tool_change_time,
        "Scrap rate (%)": metrics.scrap_rate * 100.0,
        "Rework rate (%)": metrics.rework_rate * 100.0,
        "Downgrade rate (%)": metrics.downgrade_rate * 100.0,
        "Weighted sum of metrics relative to baseline": (
            global_evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                metrics
            )
        ),
    }


# Sammelt Kennzahlen eines Gewichtssatzes und bildet gegebenenfalls die Baseline.
def _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
    state,
    optimizer,
    weights,
    calculate_reference_values=False,
    *,
    seeds=None,
    phase_name=None,
    policy_factory=None,
):
    seed_values = tuple(SEEDS if seeds is None else seeds)
    if not seed_values:
        raise ValueError("Mindestens ein Seed ist erforderlich.")
    if phase_name is None:
        phase_name = "Baseline" if calculate_reference_values else "Optimized weights"
    state["phase"] = f"{phase_name}: 0/{len(seed_values)} seeds completed"
    run_many = getattr(optimizer.simulation_runner, "run_many", None)
    factory = policy_factory if policy_factory is not None else HeuristicPolicyFactory(weights)

    if callable(run_many):
        requests = tuple(
            SimulationRunRequest(factory, seed)
            for seed in seed_values
        )
        completed_indices = set()

        def on_completed(index, result):
            # Nur Statusdaten ändern; dieser Callback läuft im Elternprozess.
            completed_indices.add(index)
            state["phase"] = (
                f"{phase_name}: {len(completed_indices)}/{len(seed_values)} seeds completed"
            )

        results = tuple(run_many(requests, on_completed=on_completed))
        if len(results) != len(seed_values):
            raise ValueError("Der Runner muss genau ein Ergebnis je Seed liefern.")
        metrics_by_seed = [
            (seed, result.metrics) for seed, result in zip(seed_values, results)
        ]
        state["phase"] = f"{phase_name}: {len(seed_values)}/{len(seed_values)} seeds completed"
    else:
        # Einfache Runner bleiben für bestehende direkte Aufrufe verwendbar.
        metrics_by_seed = []
        for seed_index, seed in enumerate(seed_values, start=1):
            metrics = optimizer.simulation_runner.run_policy(factory(seed), seed)
            metrics_by_seed.append((seed, metrics))
            state["phase"] = (
                f"{phase_name}: {seed_index}/{len(seed_values)} seeds completed"
            )

    if calculate_reference_values:
        state["baseline_metrics"] = [asdict(metrics) for seed, metrics in metrics_by_seed]
        state["baseline_reference_values"] = (
            optimizer.global_evaluation.calculate_baseline_reference_values(
                [metrics for seed, metrics in metrics_by_seed]
            )
        )
    else:
        state.setdefault("benchmark_metrics", {})[phase_name] = [
            asdict(metrics) for seed, metrics in metrics_by_seed
        ]
    return [
        _global_metric_row(seed, metrics, optimizer.global_evaluation)
        for seed, metrics in metrics_by_seed
    ]


def _benchmark_policies(state, optimizer, optimized_weights):
    # Reihenfolge und Referenzwerte bleiben für alle drei Steuerungen unverändert.
    policy_specs = (
        ("Random", None, RandomPolicy),
        ("Heuristic (default)", HeuristicWeights(), None),
        ("Heuristic (optimized)", optimized_weights, None),
    )
    seed_values = tuple(TEST_SEEDS)
    if not seed_values:
        raise ValueError("Mindestens ein Test-Seed ist erforderlich.")
    run_many = getattr(optimizer.simulation_runner, "run_many", None)
    if not callable(run_many):
        return {
            label: _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
                state,
                optimizer,
                weights,
                seeds=seed_values,
                phase_name=label,
                policy_factory=policy_factory,
            )
            for label, weights, policy_factory in policy_specs
        }

    # Alle Steuerungs-Seed-Paare gemeinsam einreichen, damit der Pool ausgelastet wird.
    requests = tuple(
        SimulationRunRequest(
            policy_factory if policy_factory is not None else HeuristicPolicyFactory(weights),
            seed,
        )
        for label, weights, policy_factory in policy_specs
        for seed in seed_values
    )
    completed_indices = set()
    state["phase"] = f"Benchmark: 0/{len(requests)} simulation runs completed"

    def on_completed(index, result):
        completed_indices.add(index)
        state["phase"] = (
            f"Benchmark: {len(completed_indices)}/{len(requests)} simulation runs completed"
        )

    results = tuple(run_many(requests, on_completed=on_completed))
    if len(results) != len(requests):
        raise ValueError("Der Runner muss genau ein Ergebnis je Benchmark-Anfrage liefern.")
    # Abschlussreihenfolgen beeinflussen weder Labels, Seedreihenfolge noch Kosten.
    benchmark = {}
    state["benchmark_metrics"] = {}
    for policy_index, (label, weights, policy_factory) in enumerate(policy_specs):
        offset = policy_index * len(seed_values)
        state["benchmark_metrics"][label] = [
            asdict(results[offset + seed_index].metrics)
            for seed_index in range(len(seed_values))
        ]
        benchmark[label] = [
            _global_metric_row(
                seed,
                results[offset + seed_index].metrics,
                optimizer.global_evaluation,
            )
            for seed_index, seed in enumerate(seed_values)
        ]
    state["phase"] = f"Benchmark: {len(requests)}/{len(requests)} simulation runs completed"
    return benchmark


# Bereitet den UI-Zustand vor; der Hintergrundthread verwaltet den Prozesspool.
def _start_optimization(state, model_file, execution_mode="parallel", timing_context="streamlit"):
    if execution_mode not in {"sequential", "parallel"}:
        raise ValueError("execution_mode muss 'sequential' oder 'parallel' sein.")
    if state.get("running"):
        raise RuntimeError("Es läuft bereits eine Optimierung.")
    state.setdefault("timing_history", [])
    state.update(
        running=True,
        iteration=0,
        candidate=0,
        total_candidates=0,
        costs=[],
        metrics=[],
        result=None,
        benchmark=None,
        baseline_reference_values={},
        baseline_metrics=[],
        benchmark_metrics={},
        candidate_evaluations=[],
        configuration=None,
        run_report=None,
        phase_seconds={},
        execution_mode=execution_mode,
        started_at_utc=datetime.now(timezone.utc).isoformat(),
        phase="",
        error=None,
        started_at=time.perf_counter(),
        elapsed_seconds=0.0,
    )
    progress_iteration = None
    completed_candidates = set()
    pending_evaluations = {}
    next_to_plot = 1
    iteration_offset = 0

    def progress(iteration, evaluation, candidate, total_candidates):
        nonlocal progress_iteration, next_to_plot, iteration_offset
        if progress_iteration != iteration:
            progress_iteration = iteration
            completed_candidates.clear()
            pending_evaluations.clear()
            next_to_plot = 1
            iteration_offset = len(state["costs"])
        state["iteration"] = iteration
        state["total_candidates"] = total_candidates

        if evaluation is not None and candidate not in completed_candidates:
            if not 1 <= candidate <= total_candidates:
                raise ValueError("Die Kandidatennummer liegt außerhalb der aktuellen Iteration.")
            completed_candidates.add(candidate)
            pending_evaluations[candidate] = evaluation
        # candidate ist der Originalindex; angezeigt wird die Zahl fertiger Gewichtssätze.
        state["candidate"] = len(completed_candidates)
        state["phase"] = (
            f"Optimization: iteration {iteration}, "
            f"{len(completed_candidates)}/{total_candidates} candidates completed"
        )

        # Später fertige Vorgänger geben gepufferte Ergebnisse in Originalreihenfolge frei.
        # So bleibt Kandidat 1 auch für die Abweichungskurve die ursprüngliche Referenz.
        while next_to_plot in pending_evaluations:
            completed_evaluation = pending_evaluations.pop(next_to_plot)
            state["candidate_evaluations"].append({
                "iteration": iteration,
                "candidate": next_to_plot,
                "evaluation": completed_evaluation,
            })
            global_candidate = iteration_offset + next_to_plot
            state["costs"].append(completed_evaluation.mean_global_cost)
            metrics_by_seed = completed_evaluation.metrics_by_seed
            if metrics_by_seed:
                state["metrics"].append({
                    "Candidate": global_candidate,
                    "Makespan": _mean_metric(metrics_by_seed, "makespan"),
                    "Total job tardiness": _mean_metric(metrics_by_seed, "total_tardiness"),
                    "Transport time": _mean_metric(metrics_by_seed, "total_transport_time"),
                    "Tool change time": _mean_metric(metrics_by_seed, "tool_change_time"),
                    "Scrap rate (%)": _mean_metric(metrics_by_seed, "scrap_rate") * 100.0,
                    "Rework rate (%)": _mean_metric(metrics_by_seed, "rework_rate") * 100.0,
                    "Downgrade rate (%)": _mean_metric(metrics_by_seed, "downgrade_rate") * 100.0,
                })
            next_to_plot += 1

    def worker():
        optimizer = None
        try:
            # Auch die Initialisierung kann fehlschlagen und gehört in diesen Fehlerpfad.
            state["configuration"] = _optimization_configuration(model_file, timing_context)
            optimizer = create_optimizer(model_file, execution_mode)
            state["phase_seconds"]["initialization"] = (
                time.perf_counter() - state["started_at"]
            )
            state["phase"] = "Calculating baseline with original weights ..."
            phase_started_at = time.perf_counter()
            _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
                state,
                optimizer,
                HeuristicWeights(),
                calculate_reference_values=True,
            )
            state["phase_seconds"]["baseline"] = time.perf_counter() - phase_started_at
            phase_started_at = time.perf_counter()
            state["result"] = optimizer.optimize_iteratively(
                initial_local_weights=HeuristicWeights(),
                seeds=SEEDS,
                iterations=ITERATIONS,
                initial_local_weight_step_fraction=INITIAL_WEIGHT_STEP,
                exploration_candidate_count=EXPLORATION_CANDIDATES,
                restart_after_no_improvement=RESTART_AFTER_NO_IMPROVEMENT,
                stop_after_no_improvement=STOP_AFTER_NO_IMPROVEMENT,
                progress_callback=progress,
            )
            state["phase_seconds"]["weight_search"] = time.perf_counter() - phase_started_at
            phase_started_at = time.perf_counter()
            state["benchmark"] = _benchmark_policies(
                state,
                optimizer,
                state["result"].best_weights,
            )
            state["phase_seconds"]["policy_comparison"] = time.perf_counter() - phase_started_at
        except Exception as error:
            state["error"] = str(error)
        finally:
            shutdown_started_at = time.perf_counter()
            try:
                if optimizer is not None:
                    close_runner = getattr(optimizer.simulation_runner, "close", None)
                    if callable(close_runner):
                        state["phase"] = "Closing simulation workers ..."
                        close_runner()
            except Exception as error:
                close_error = f"Simulation workers could not be closed: {error}"
                state["error"] = (
                    f"{state['error']}\n{close_error}" if state["error"] else close_error
                )
            finally:
                # Die Gesamtzeit enthält auch das Warten auf die Poolbeendigung.
                state["phase_seconds"]["shutdown"] = time.perf_counter() - shutdown_started_at
                state["elapsed_seconds"] = time.perf_counter() - state["started_at"]
                try:
                    if state["error"] is None:
                        if state["configuration"] != _optimization_configuration(model_file, timing_context):
                            raise RuntimeError("Modell, Quellcode oder Einstellungen wurden während des Laufs geändert.")
                        candidate_evaluations = [
                            {
                                "iteration": item["iteration"],
                                "candidate": item["candidate"],
                                "evaluation": asdict(item["evaluation"]),
                            }
                            for item in state["candidate_evaluations"]
                        ]
                        simulation_count = (
                            len(state["baseline_metrics"])
                            + sum(len(item["evaluation"]["metrics_by_seed"])
                                  for item in candidate_evaluations)
                            + sum(len(items) for items in state["benchmark_metrics"].values())
                        )
                        state["run_report"] = {
                            "execution_mode": execution_mode,
                            "max_workers": MAX_WORKERS if execution_mode == "parallel" else 1,
                            "started_at_utc": state["started_at_utc"],
                            "elapsed_seconds": state["elapsed_seconds"],
                            "phase_seconds": dict(state["phase_seconds"]),
                            "simulation_count": simulation_count,
                            "configuration": state["configuration"],
                            "results": {
                                "baseline_metrics": state["baseline_metrics"],
                                "baseline_reference_values": state["baseline_reference_values"],
                                "candidate_evaluations": candidate_evaluations,
                                "optimization_result": asdict(state["result"]),
                                "benchmark_metrics": state["benchmark_metrics"],
                                "benchmark": state["benchmark"],
                            },
                        }
                        state["timing_history"].append(state["run_report"])
                except Exception as error:
                    state["error"] = str(error)
                finally:
                    state["running"] = False

    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception as error:
        # Wenn schon der Threadstart scheitert, wurde noch kein Pool angelegt.
        state["error"] = str(error)
        state["elapsed_seconds"] = time.perf_counter() - state["started_at"]
        state["running"] = False


# Startet den Streamlit-Webserver und übergibt das ausgewählte Beispiel als Umgebungsvorgabe.
def main():
    model_file = os.environ.get("SPINEML_MODEL_FILE", EXAMPLE_FILE)
    environment = os.environ.copy()
    environment["SPINEML_STREAMLIT_STARTED"] = "1"
    environment["SPINEML_MODEL_FILE"] = model_file
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).resolve()),
        ],
        env=environment,
    )


if __name__ == "__main__" and not st.runtime.exists():
    started_by_main = os.environ.get("SPINEML_STREAMLIT_STARTED") == "1"
    if not started_by_main:
        main()
        raise SystemExit

from SpineML.Control.RandomPolicy.RandomPolicy import RandomPolicy
from SpineML.Control.HeuristicPolicy.HeuristicPolicyFactory import HeuristicPolicyFactory
from SpineML.Control.HeuristicPolicy.HeuristicWeights import HeuristicWeights
from SpineML.GlobalEvaluation.GlobalSimulationEvaluation import (
    GlobalSimulationEvaluation,
    GlobalSimulationWeights,
)
from SpineML.Control.HeuristicPolicy.WeightOptimization.LocalHeuristicWeightOptimizer import LocalHeuristicWeightOptimizer
from SpineML.SimulationExecution.SimulationRunner import SimulationRunner
from SpineML.SimulationExecution.ParallelSimulationRunner import (
    ParallelSimulationRunner,
    SimulationRunRequest,
)
# Kompatible Namen ohne Kopien der ausgelagerten Modell-Ladefunktionen.
from SpineML.SimulationExecution.ModelLoader import (
    load_layout_and_scenario,
    _find_layout_and_scenario as _find_layout_and_scenario,
    _load_model as _load_model,
    _resolve_model_path as _resolve_model_path,
)

# Wird nach main() im Streamlit-Webserver aufgerufen und baut die Oberfläche
# für Auswahl, Start und Ergebnisanzeige auf.
def _streamlit_app():
    # Liest den Beispielnamen aus der Umgebung oder verwendet das Standardbeispiel.
    selected_model_file = os.environ.get("SPINEML_MODEL_FILE", EXAMPLE_FILE)
    # Sucht die Beispieldatei und liefert ihren vollständigen Pfad zurück.
    selected_model_path = _resolve_model_path(selected_model_file)
    st.title("SpineML - heuristic optimization")

    if "optimization_state" not in st.session_state:
        st.session_state.optimization_state = {
            "running": False,
            "iteration": 0,
            "candidate": 0,
            "total_candidates": 0,
            "costs": [],
            "metrics": [],
            "result": None,
            "benchmark": None,
            "baseline_reference_values": {},
            "phase": "",
            "error": None,
            "started_at": None,
            "elapsed_seconds": None,
        }


    state = st.session_state.optimization_state
    execution_labels = {
        "sequential": "Sequential (previous execution)",
        "parallel": "Parallel (process pool)",
    }
    execution_mode = st.selectbox(
        "Execution mode",
        options=("sequential", "parallel"),
        index=1,
        format_func=execution_labels.get,
        disabled=state["running"],
    )
    st.caption(
        f"Example: {selected_model_path.name} · "
        + ("one simulation after another, without a process pool"
           if execution_mode == "sequential"
           else f"up to {MAX_WORKERS} simulations in parallel")
    )
    elapsed_display = st.empty()
    # Beide Modi verwenden denselben Ablauf; nur der Runner wird ausgetauscht.
    st.button(
        "Start optimization",
        disabled=state["running"],
        on_click=_start_optimization,
        args=(state, str(selected_model_path), execution_mode),
    )

    if state["running"]:
        status = st.empty()
        iteration = st.empty()
        candidate = st.empty()
        progress_bar = st.empty()
        cost_chart = st.empty()
        metric_chart = st.empty()
        delta_chart = st.empty()
        latest = st.empty()

        while state["running"]:
            if state.get("started_at") is not None:
                elapsed_display.caption(
                    f"Elapsed time: {time.perf_counter() - state['started_at']:.1f} seconds"
                )
            status.info(
                state["phase"]
                or "Optimization running - simulating candidates ..."
            )
            iteration.write(f"Current iteration: {state['iteration']}")
            candidate.write(
                f"Completed candidates: {state['candidate']} / "
                f"{state['total_candidates'] or '?'}"
            )
            if state["total_candidates"]:
                progress_bar.progress(
                    state["candidate"] / state["total_candidates"]
                )
            if state["costs"]:
                global_costs_per_candidate(state["costs"], cost_chart)
                mean_metrics_per_candidate(
                    state["metrics"],
                    metric_chart,
                )
                metric_deviation_from_candidate_1(
                    state["metrics"],
                    delta_chart,
                )
                latest.caption(
                    f"Latest mean global cost: "
                    f"{state['costs'][-1]:.2f}"
                )
            elif state["candidate"]:
                latest.caption(
                    "Completed results are buffered in candidate order."
                )
            else:
                latest.caption("No candidate has been fully evaluated yet.")
            time.sleep(0.5)

    if state.get("elapsed_seconds") is not None and not state["running"]:
        elapsed_display.caption(
            f"Total elapsed time: {state['elapsed_seconds']:.1f} seconds "
            "(including worker shutdown)"
        )
    if not state["running"] and state.get("timing_history"):
        _show_timing_comparison(state["timing_history"])
    if state["error"]:
        st.error(state["error"])
    elif state["result"] is not None:
        st.success("Optimization completed")
        global_costs_per_candidate(state["costs"])
        st.subheader("Mean metrics per candidate")
        mean_metrics_per_candidate(state["metrics"])
        st.subheader("Metric deviation from candidate 1")
        metric_deviation_from_candidate_1(state["metrics"])
        st.write("Best local weights", state["result"].best_weights)
        st.write(
            "Best mean global cost",
            state["result"].best_mean_global_cost,
        )
        st.write(
            "Baseline reference values",
            state["baseline_reference_values"],
        )
        compare_baseline_optimized(state["benchmark"])


def _show_timing_comparison(history):
    st.subheader("Full optimization: sequential vs. parallel")
    st.caption(
        "Each row covers model loading, baseline, all search iterations, "
        "policy comparison and shutdown. These are full optimization times, "
        "not durations of one simulation."
    )
    st.caption(
        "For an isolated comparison in fresh Python processes, use "
        "sources/tools/compare_optimization_runtime.py. Do not run other optimizations concurrently."
    )
    st.dataframe([
        {
            "Execution": report["execution_mode"],
            "Max. simultaneous simulations": report["max_workers"],
            "Completed simulations": report["simulation_count"],
            "Total elapsed (s)": report["elapsed_seconds"],
            **{f"{phase} (s)": seconds for phase, seconds in report["phase_seconds"].items()},
        }
        for report in history
    ], use_container_width=True, hide_index=True)
    latest = {report["execution_mode"]: report for report in history}
    comparison = None
    if "sequential" in latest and "parallel" in latest:
        comparison = compare_optimization_reports(latest["sequential"], latest["parallel"])
        if not comparison["comparable"]:
            st.warning("No valid timing comparison: " + comparison["reason"])
        else:
            st.success("The weight sets, simulation metrics and optimization results are identical.")
            if comparison["speedup"] >= 1.0:
                st.write(
                    f"Measured speedup: {comparison['speedup']:.2f}x · "
                    f"Time saved: {comparison['saved_seconds']:.1f} seconds "
                    f"({comparison['saved_percent']:.1f}%)."
                )
            else:
                st.warning(
                    f"Parallel execution was slower in this comparison: "
                    f"{comparison['parallel_seconds']:.1f} vs. "
                    f"{comparison['sequential_seconds']:.1f} seconds."
                )
    else:
        st.info("Run the other execution mode with unchanged settings to compare both total times.")
    st.download_button(
        "Download timing reports (JSON)",
        data=json.dumps(
            {"measurements": history, "comparison": comparison},
            ensure_ascii=False, indent=2, allow_nan=False,
        ),
        file_name="optimization_timing_comparison.json",
        mime="application/json",
    )

if __name__ == "__main__" and st.runtime.exists():
    _streamlit_app()
