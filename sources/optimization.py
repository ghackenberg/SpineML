from __future__ import annotations

import ast
from contextlib import contextmanager
import os
import re
import runpy
import subprocess
import sys
import threading
import time
from pathlib import Path

import altair as alt
import pandas as pd
import salabim as sim
import streamlit as st


SOURCES_DIRECTORY = Path(__file__).parent.resolve()
EXAMPLES_DIRECTORY = SOURCES_DIRECTORY / "examples"
NORMAL_EXAMPLES_DIRECTORY = EXAMPLES_DIRECTORY / "normal"
OPTIMIZATION_EXAMPLES_DIRECTORY = EXAMPLES_DIRECTORY / "optimization"
EXAMPLE_FILE = "example-5.py"
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


# Sucht die angegebene Beispieldatei in den möglichen Projektordnern und gibt
# ihren vollständigen Pfad zurück; die Datei wird dabei noch nicht ausgeführt.
def _resolve_model_path(model_file: str | Path) -> Path:
    """Findet eine Beispieldatei im Arbeitsordner oder in einem Examples-Ordner."""
    requested = Path(str(model_file))
    requested_names = [requested]

    example_number = re.fullmatch(
        r"example[-_]?(\d+)(\.py)?",
        requested.name,
        flags=re.IGNORECASE,
    )
    if example_number:
        suffix = example_number.group(2) or requested.suffix
        requested_names.append(
            requested.with_name(
                f"example-{example_number.group(1)}{suffix}"
            )
        )

    possible_paths = []

    for requested_name in requested_names:
        if requested_name.is_absolute():
            possible_paths.append(requested_name)
        else:
            possible_paths.append(Path.cwd() / requested_name)
            possible_paths.append(SOURCES_DIRECTORY / requested_name)
            possible_paths.append(NORMAL_EXAMPLES_DIRECTORY / requested_name)
            possible_paths.append(OPTIMIZATION_EXAMPLES_DIRECTORY / requested_name)

    expanded_paths = []
    for path in possible_paths:
        expanded_paths.append(path)
        if path.suffix == "":
            expanded_paths.append(path.with_suffix(".py"))

    for path in expanded_paths:
        if path.is_file() and path.suffix == ".py":
            return path.resolve()

    searched = "\n".join(str(path) for path in expanded_paths)
    raise FileNotFoundError(
        f"Beispieldatei {model_file!r} wurde nicht gefunden. Gesucht wurde in:\n{searched}"
    )


# Sucht im geladenen Modell das für die Simulation vorgesehene Layout-Szenario-Paar
# und gibt beide Konfigurationsobjekte als Tupel zurück.
def _find_layout_and_scenario(
    model: dict[str, object],
    model_path: Path,
) -> tuple[object, object]:
    """Liest und wählt die Konfiguration des Beispiels für die Optimierung."""
    from SpineML.Configuration import Layout, Scenario

    # Sammelt alle Layout- und Szenario-Objekte aus den globalen Modellvariablen.
    layouts = []
    scenarios = []
    for name, value in model.items():
        # Speichert eine Modellvariable, wenn sie ein Layout-Objekt enthält.
        if isinstance(value, Layout):
            layouts.append((name, value))
        # Speichert eine Modellvariable, wenn sie ein Scenario-Objekt enthält.
        if isinstance(value, Scenario):
            scenarios.append((name, value))

    # Liest den Quelltext nur als Text; die Datei wird hier nicht erneut ausgeführt.
    source = model_path.read_text(encoding="utf-8")
    # Erstellt einen Syntaxbaum, um simulate(layout, scenario) zu untersuchen.
    tree = ast.parse(source, filename=str(model_path))
    simulate_calls = []
    # Durchsucht den Syntaxbaum nach allen direkten simulate-Aufrufen.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "simulate":
            continue
        simulate_calls.append(node)

    # Ordnet mehrere simulate-Aufrufe nach ihrer Position im Quelltext.
    simulate_calls.sort(
        key=lambda node: (
            getattr(node, "lineno", 0),
            getattr(node, "col_offset", 0),
        )
    )
    for node in simulate_calls:
        # Ein gültiger Aufruf muss mindestens Layout und Szenario übergeben.
        if len(node.args) < 2:
            continue

        # Liest die ersten beiden Argumente des simulate-Aufrufs.
        layout_node = node.args[0]
        scenario_node = node.args[1]
        # Die Argumente müssen einfache Variablennamen sein, z. B. layout und scenario.
        if not isinstance(layout_node, ast.Name):
            continue
        if not isinstance(scenario_node, ast.Name):
            continue

        # Löst die Variablennamen im bereits geladenen Modell-Dictionary auf.
        layout = model.get(layout_node.id)
        scenario = model.get(scenario_node.id)
        # Gibt das erste eindeutig referenzierte Layout-Szenario-Paar zurück.
        if layout is not None and scenario is not None:
            return layout, scenario

    # Ohne auswertbaren simulate-Aufruf wird ein Paar nur bei genau einem
    # Layout und genau einem Szenario automatisch ausgewählt.
    if len(layouts) == 1 and len(scenarios) == 1:
        return layouts[0][1], scenarios[0][1]

    # Mehrere mögliche Objekte ohne eindeutige Auswahl führen zu einem Fehler.
    layout_names = [name for name, value in layouts]
    scenario_names = [name for name, value in scenarios]
    raise ValueError(
        "Layout und Szenario konnten nicht eindeutig ausgewählt werden. "
        f"Layouts: {layout_names}; Szenarien: {scenario_names}. "
        "Im Beispiel muss ein simulate(layout, scenario)-Aufruf vorhanden sein."
    )


@contextmanager
# Deaktiviert während des Modellladens vorübergehend SpineML.simulate(),
# damit ein direkter simulate()-Aufruf im Beispiel keinen Lauf startet.
def _suppress_model_visualization():
    """Verhindert, dass ein Beispiel beim Laden selbst eine Simulation startet.

    Einige Beispieldateien rufen ``simulate(...)`` direkt am Dateiende auf.
    Für die Optimierung soll dieser Aufruf erst später durch den headless
    Runner erfolgen. Während ``runpy.run_path`` die Modelldatei lädt, wird
    ``simulate`` deshalb vorübergehend durch eine leere Funktion ersetzt.
    """
    import SpineML

    original_simulate = getattr(SpineML, "simulate", None)
    SpineML.simulate = lambda *args, **kwargs: None
    try:
        yield
    finally:
        if original_simulate is not None:
            SpineML.simulate = original_simulate


# Führt die Modelldatei aus und gibt ihre globalen Modellobjekte zurück.
def _load_model(model_path: Path) -> dict[str, object]:
    """Führt nur die Modelldefinition aus und gibt deren globale Variablen zurück."""
    with _suppress_model_visualization():
        return runpy.run_path(str(model_path), run_name="spine_model")


# kennzahlen und macht daraus eine einzelne Kosten-Zahl zum Vergleichen.
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


# Erstellt den Optimierer aus dem ausgewählten Beispielmodell.
def create_optimizer(model_file: str):
    """Lädt ein Beispiel und erstellt den Optimierer mit den sieben globalen Zielen."""
    # Sucht die ausgewählte Beispieldatei und liefert ihren vollständigen Pfad.
    model_path = _resolve_model_path(model_file)
    # Führt die Modelldefinition aus und sammelt ihre globalen Variablen.
    model = _load_model(model_path)
    # Wählt aus dem geladenen Modell das zu simulierende Layout und Szenario.
    layout, scenario = _find_layout_and_scenario(model, model_path)

    # Erstellt den Simulationsrunner, der das ausgewählte Layout und Szenario
    # mit einem weight set und Seed ausführen kann.
    runner = SpineMLSimulationRunner(
        layout,
        scenario,
        till=sim.inf,
    )

    # Erstellt den Optimierer. Bei optimize_iteratively() lässt er später
    # verschiedene lokale heuristische weight sets simulieren, vergleicht
    # ihre globalen Kosten und wählt den besten Satz aus.
    return LocalHeuristicWeightOptimizer(
        simulation_runner=runner,
        global_evaluation=_global_evaluation(),
    )


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


# Zeichnet die prozentuale Kennzahlenabweichung gegenüber dem ersten Kandidaten.
def metric_deviation_from_candidate_1(metrics, container=None):
    if not metrics:
        return
    frame = pd.DataFrame(metrics)[["Candidate", *SCORED_METRICS]].copy()
    for name in SCORED_METRICS:
        baseline = float(frame[name].iloc[0])
        if baseline == 0.0:
            frame[name] = 0.0
        else:
            frame[name] = (
                (frame[name] - baseline) / abs(baseline) * 100.0
            )

    delta_frame = frame.melt(
        id_vars=["Candidate"],
        var_name="Metric",
        value_name="Deviation (%)",
    )
    chart = (
        alt.Chart(delta_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Candidate:Q", title="Candidate"),
            y=alt.Y(
                "Deviation (%):Q",
                title="Deviation from candidate 1 (%)",
            ),
            color=alt.Color("Metric:N", title="Metric"),
            tooltip=[
                "Candidate:Q",
                "Metric:N",
                "Deviation (%):Q",
            ],
        )
        .interactive()
    )
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


# Sammelt Kennzahlen für Gewichte oder eine Policy auf den angegebenen Seeds.
def _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
    # Zustands-Dictionary des Streamlit-Webservers für Fortschritt und Ergebnisse.
    state,
    # Optimierer mit Simulationsrunner und globaler Kostenberechnung.
    optimizer,
    # Lokale Gewichte; bei einer eigenen policy_factory nicht verwendet.
    weights,
    # Gibt an, ob die Referenzwerte aus dieser Baseline berechnet werden.
    calculate_reference_values=False,
    *,
    seeds=None,
    phase_name=None,
    policy_factory=None,
):
    if seeds is None:
        seeds = SEEDS
    if phase_name is None:
        phase_name = "Baseline" if calculate_reference_values else "Optimized weights"
    metrics_by_seed = []
    for seed_index, seed in enumerate(seeds, start=1):
        # Legt nur die Statusmeldung im Streamlit-Webserver 
        # für den aktuellen Lauf fest.
        state["phase"] = (
            f"{phase_name}: Seed {seed_index}/{len(seeds)}"
        )
        # Erzeugt pro Lauf eine frische Policy und sammelt dieselben Kennzahlen.
        if policy_factory is None:
            metrics = optimizer.simulation_runner(weights, seed)
        else:
            metrics = optimizer.simulation_runner.run_policy(policy_factory(seed), seed)
        metrics_by_seed.append((seed, metrics))

    # Berechnet nur bei der Baseline, Referenzwerte zur relativen Skalierung der
    # globalen Zeitkennzahlen.
    if calculate_reference_values:
        baseline_metrics = []
        # Sammelt die globalen Kennzahlen jedes bereits simulierten Seeds.
        for seed, metrics in metrics_by_seed:
            baseline_metrics.append(metrics)

        # Berechnet für jede globale Zeitkennzahl ihren Baseline-Mittelwert.
        baseline_reference_values = (
            # Gibt die berechneten Referenzwerte aus der globalen Bewertung zurück.
            optimizer.global_evaluation.calculate_baseline_reference_values(
                baseline_metrics
            )
        )
        # Speichert die Referenzwerte für spätere globale Kostenberechnungen.
        state["baseline_reference_values"] = baseline_reference_values

    rows = []

    # Erstellt für jeden Seed eine Zeile mit allen bereits berechneten globalen Kennzahlen.
    for seed, metrics in metrics_by_seed:
        row = {
            "Seed": seed,
            "Makespan": metrics.makespan,
            "Total job tardiness": metrics.total_tardiness,
            "Transport time": metrics.total_transport_time,
            "Tool change time": metrics.tool_change_time,
            "Scrap rate (%)": metrics.scrap_rate * 100.0,
            "Rework rate (%)": metrics.rework_rate * 100.0,
            "Downgrade rate (%)": metrics.downgrade_rate * 100.0,
            # Scale metrics relative to the baseline and add them with weights.
            "Weighted sum of metrics relative to baseline": (
                optimizer.global_evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                    metrics
                )
            ),
        }
        rows.append(row)
    return rows


def _benchmark_policies(state, optimizer, optimized_weights):
    # Alle drei Steuerungen nutzen dieselben Test-Seeds und feste Referenzwerte.
    benchmark = {}
    for label, weights, policy_factory in (
        ("Random", None, RandomPolicy),
        ("Heuristic (default)", HeuristicWeights(), None),
        ("Heuristic (optimized)", optimized_weights, None),
    ):
        benchmark[label] = (
            _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
                state,
                optimizer,
                weights,
                seeds=TEST_SEEDS,
                phase_name=label,
                policy_factory=policy_factory,
            )
        )
    return benchmark


# Bereitet einen neuen Optimierungslauf vor und startet anschließend den Worker-Thread.
def _start_optimization(state, model_file):
    optimizer = create_optimizer(model_file)
    # Aktualisiert die Werte, die später im Streamlit-Webserver angezeigt werden.
    # Hier werden diese Werte für einen neuen Optimierungslauf zurückgesetzt.
    state.update(
        # Markiert, dass der neue Optimierungslauf läuft.
        running=True,
        # Setzt die aktuelle Iterationsnummer zurück.
        iteration=0,
        # Setzt die Nummer des aktuell bearbeiteten Kandidaten zurück.
        candidate=0,
        # Setzt die Gesamtzahl der Kandidaten der aktuellen Iteration zurück.
        total_candidates=0,
        # Löscht die Kostenhistorie des vorherigen Laufs.
        costs=[],
        # Löscht die Kennzahlenhistorie des vorherigen Laufs.
        metrics=[],
        # Entfernt das Ergebnis des vorherigen Optimierungslaufs.
        result=None,
        # Entfernt den vorherigen Baseline-Optimierungsvergleich.
        benchmark=None,
        # Setzt die Referenzwerte der Baseline zurück.
        baseline_reference_values={},
        # Löscht die aktuelle Statusmeldung.
        phase="",
        # Entfernt eine Fehlermeldung des vorherigen Laufs.
        error=None,
    )

    # Aktualisiert die Werte, die später im Streamlit-Webserver angezeigt werden.
    def progress(iteration, evaluation, candidate, total_candidates):
        state["iteration"] = iteration
        state["candidate"] = candidate
        state["total_candidates"] = total_candidates
        state["phase"] = (
            f"Optimization: iteration {iteration}, "
            f"candidate {candidate}/{total_candidates}"
        )

        if evaluation is None:
            return

        state["costs"].append(evaluation.mean_global_cost)
        if not evaluation.metrics_by_seed:
            return

        metrics_by_seed = evaluation.metrics_by_seed
        metric_row = {
            "Candidate": len(state["costs"]),
            "Makespan": _mean_metric(metrics_by_seed, "makespan"),
            "Total job tardiness": _mean_metric(
                metrics_by_seed,
                "total_tardiness",
            ),
            "Transport time": _mean_metric(
                metrics_by_seed,
                "total_transport_time",
            ),
            "Tool change time": _mean_metric(
                metrics_by_seed,
                "tool_change_time",
            ),
            "Scrap rate (%)": _mean_metric(
                metrics_by_seed,
                "scrap_rate",
            ) * 100.0,
            "Rework rate (%)": _mean_metric(
                metrics_by_seed,
                "rework_rate",
            ) * 100.0,
            "Downgrade rate (%)": _mean_metric(
                metrics_by_seed,
                "downgrade_rate",
            ) * 100.0,
        }
        state["metrics"].append(metric_row)

    # Berechnet Baseline, Optimierung und den anschließenden Benchmark.
    def worker():
        try:
            # Aktualisiert die Statusanzeige: Jetzt wird zuerst die Baseline berechnet.
            state["phase"] = "Calculating baseline with original weights ..."
        
            # Berechnet die Baseline-Referenzwerte aus Läufen mit dem Standardgewichtssatz.
            _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
                state,
                optimizer,
                HeuristicWeights(),
                calculate_reference_values=True,
            )

            # Startet die iterative Suche nach einem besseren lokalen weight set
            # und speichert das Optimierungsergebnis im Streamlit-Webserver-Zustand.
            state["result"] = optimizer.optimize_iteratively(

                # Start the search with the unchanged default weights.
                initial_local_weights=HeuristicWeights(),

                # Verwendet diese Seeds für jeden getesteten weight set.
                seeds=SEEDS,

                # Legt die maximale Anzahl der Iterationen fest.
                iterations=ITERATIONS,

                # Set the initial relative size of weight changes.
                initial_local_weight_step_fraction=INITIAL_WEIGHT_STEP,

                # Legt fest, wie viele zusätzliche Kandidaten pro Iteration getestet werden.
                exploration_candidate_count=EXPLORATION_CANDIDATES,

                # Startet nach dieser Anzahl erfolgloser Iterationen erneut.
                restart_after_no_improvement=RESTART_AFTER_NO_IMPROVEMENT,

                # Beendet die Suche nach dieser Anzahl erfolgloser Iterationen.
                stop_after_no_improvement=STOP_AFTER_NO_IMPROVEMENT,
                
                # Aktualisiert den Streamlit-Webserver über den aktuellen Fortschritt.
                progress_callback=progress,
            )

            # Vergleicht alle Steuerungen auf Seeds außerhalb der Gewichtssuche.
            state["benchmark"] = _benchmark_policies(
                state,
                optimizer,
                state["result"].best_weights,
            )
        except Exception as error:
            state["error"] = str(error)
        finally:
            state["running"] = False

    threading.Thread(target=worker, daemon=True).start()


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

from SpineML.Control.GeneralControl import RandomPolicy
from SpineML.Control.HeuristicControl import (
    GlobalSimulationEvaluation,
    GlobalSimulationWeights,
    HeuristicWeights,
    LocalHeuristicWeightOptimizer,
    SpineMLSimulationRunner,
)

# Wird nach main() im Streamlit-Webserver aufgerufen und baut die Oberfläche
# für Auswahl, Start und Ergebnisanzeige auf.
def _streamlit_app():
    # Liest den Beispielnamen aus der Umgebung oder verwendet das Standardbeispiel.
    selected_model_file = os.environ.get("SPINEML_MODEL_FILE", EXAMPLE_FILE)
    # Sucht die Beispieldatei und liefert ihren vollständigen Pfad zurück.
    selected_model_path = _resolve_model_path(selected_model_file)
    st.title("SpineML - heuristic optimization")
    st.caption(f"Example: {selected_model_path.name}")

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
        }


    state = st.session_state.optimization_state
    # Lädt das Modell und erstellt einen neuen Optimierer nur beim Start.
    # Eine erneute Anzeige lädt während der Berechnung kein zweites Modell.
    st.button(
        "Start optimization",
        disabled=state["running"],
        on_click=_start_optimization,
        args=(state, str(selected_model_path)),
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
            status.info(
                state["phase"]
                or "Optimization running - simulating candidates ..."
            )
            iteration.write(f"Current iteration: {state['iteration']}")
            candidate.write(
                f"Candidate: {state['candidate']} / "
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
            else:
                latest.caption("No candidate has been fully evaluated yet.")
            time.sleep(0.5)

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

if __name__ == "__main__" and st.runtime.exists():
    _streamlit_app()
