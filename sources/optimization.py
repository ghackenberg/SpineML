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
EXAMPLE_FILE = "example-1.py"
SEEDS = [1, 2]
ITERATIONS = 2
INITIAL_WEIGHT_STEP = 0.40
EXPLORATION_CANDIDATES = 3
RESTART_AFTER_NO_IMPROVEMENT = 2
STOP_AFTER_NO_IMPROVEMENT = 4


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
            # Gewicht für die gesamte Durchlaufzeit bis zum letzten Abschluss.
            makespan=5.0,
            # Gewicht für die aufsummierte Verspätung abgeschlossener Aufträge.
            total_tardiness=4.0,
            # Gewicht für die gesamte Transportzeit aller Roboter.
            total_transport_time=1.0,
            # Gewicht für Werkzeugwechsel sowie Montage- und Demontagezeiten.
            tool_change_time=1.0,
            # Gewicht für Wartezeit durch blockierte oder volle Puffer.
            blocking_time=1.0,
            # Strafe für den Anteil der Jobs, die nachgearbeitet wurden.
            nacharbeit_job_penalty=3.0,
            # Strafe für den Anteil der Jobs, die als Ausschuss endeten.
            ausschuss_job_penalty=4.0,
            # Strafe für den Anteil der Jobs, die nicht fertiggestellt wurden.
            unfinished_jobs=20.0,
            # Strafe für den Anteil der Jobs, bei denen ein Defekt auftrat.
            defect_job_penalty=3.0,
            # Strafe für den Anteil der Jobs, die nicht intakt abgeschlossen wurden.
            non_intact_penalty=3.0,
            # Strafe für den Anteil der herabgestuften Jobs.
            downgrade_job_penalty=3.0,
        )
    )


# @st.cache_resource sorgt dafür, dass der Optimierer bei einer erneuten
# Ausführung des Streamlit-Webservers nicht jedes Mal neu erstellt wird.
@st.cache_resource
# Erstellt den Optimierer aus dem ausgewählten Beispielmodell.
def create_optimizer(model_file: str, model_stamp: int):
    """Lädt ein Beispiel und erstellt den Optimierer für Layout und Szenario."""
    del model_stamp
    # Sucht die ausgewählte Beispieldatei und liefert ihren vollständigen Pfad.
    model_path = _resolve_model_path(model_file)
    # Führt die Modelldefinition aus und sammelt ihre globalen Variablen.
    model = _load_model(model_path)
    # Wählt aus dem geladenen Modell das zu simulierende Layout und Szenario.
    layout, scenario = _find_layout_and_scenario(model, model_path)

    # Erstellt den Simulationsrunner, der das ausgewählte Layout und Szenario
    # mit einem Gewichtssatz und Seed ausführen kann.
    runner = SpineMLSimulationRunner(
        layout,
        scenario,
        till=sim.inf,
    )

    # Definiert die Funktion, die einen Lauf mit einem vollständigen lokalen
    # Gewichtssatz und einem Seed startet.
    def run_simulation(weights, seed):
        # Übergibt den Gewichtssatz und den Seed an den Simulationsrunner.
        return runner(weights, seed)

    # Erstellt den Optimierer. Bei optimize_iteratively() lässt er später
    # verschiedene lokale heuristische Gewichtssätze simulieren, vergleicht
    # ihre globalen Kosten und wählt den besten Satz aus.
    return LocalHeuristicWeightOptimizer(
        simulation_runner=run_simulation,
        global_evaluation=_global_evaluation(),
    )


# Berechnet den Mittelwert einer Kennzahl über alle Seeds.
def _mean_metric(metrics_by_seed, attribute_name: str) -> float:
    total_value = 0.0
    for metrics in metrics_by_seed:
        total_value += float(getattr(metrics, attribute_name))
    return total_value / len(metrics_by_seed)


# Zeichnet die mittleren globalen Kosten je Kandidat.
def globale_kosten_pro_kandidat(costs, container=None):
    if not costs:
        return
    data = pd.DataFrame(
        {
            "Kandidat": range(1, len(costs) + 1),
            "Mittlere globale Kosten": costs,
        }
    )
    chart = (
        alt.Chart(data)
        .mark_line(point=True, color="#f28e2b")
        .encode(
            x=alt.X("Kandidat:Q", title="Kandidat"),
            y=alt.Y(
                "Mittlere globale Kosten:Q",
                title="Mittlere globale Kosten",
                scale=alt.Scale(zero=False),
            ),
            tooltip=["Kandidat:Q", "Mittlere globale Kosten:Q"],
        )
        .interactive()
    )
    target = st if container is None else container
    target.altair_chart(chart, use_container_width=True)


# Zeichnet die mittleren Kennzahlen je Kandidat.
def mittlere_kennzahlen_pro_kandidat(metrics, container=None):
    if not metrics:
        return
    frame = pd.DataFrame(metrics)
    frame = frame.melt(
        id_vars=["Kandidat"],
        var_name="Kennzahl",
        value_name="Wert",
    )
    chart = (
        alt.Chart(frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Kandidat:Q", title="Kandidat"),
            y=alt.Y(
                "Wert:Q",
                title="Mittelwert über Seeds",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color("Kennzahl:N", title="Kennzahl"),
            facet=alt.Facet("Kennzahl:N", columns=2, title=None),
            tooltip=["Kandidat:Q", "Kennzahl:N", "Wert:Q"],
        )
        .properties(height=180)
        .resolve_scale(y="independent")
        .interactive()
    )
    target = st if container is None else container
    target.altair_chart(chart, use_container_width=True)


# Zeichnet die prozentuale Kennzahlenabweichung gegenüber dem ersten Kandidaten.
def kennzahlenabweichung_gegen_kandidat_1(metrics, container=None):
    if not metrics:
        return
    frame = pd.DataFrame(metrics)
    metric_names = [
        "Makespan",
        "Tardiness",
        "Transportzeit",
        "Unfertige Jobs",
        "Intaktquote (%)",
        "Defektquote (%)",
        "Ausschussquote (%)",
        "Nacharbeitsquote (%)",
        "Unfertigenquote (%)",
        "Herabstufungsquote (%)",
    ]
    for name in metric_names:
        baseline = float(frame[name].iloc[0])
        if baseline == 0.0:
            frame[name] = 0.0
        else:
            frame[name] = (
                (frame[name] - baseline) / abs(baseline) * 100.0
            )

    delta_frame = frame.melt(
        id_vars=["Kandidat"],
        var_name="Kennzahl",
        value_name="Abweichung in %",
    )
    chart = (
        alt.Chart(delta_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Kandidat:Q", title="Kandidat"),
            y=alt.Y(
                "Abweichung in %:Q",
                title="Abweichung gegenüber Kandidat 1 (%)",
            ),
            color=alt.Color("Kennzahl:N", title="Kennzahl"),
            tooltip=[
                "Kandidat:Q",
                "Kennzahl:N",
                "Abweichung in %:Q",
            ],
        )
        .interactive()
    )
    target = st if container is None else container
    target.altair_chart(chart, use_container_width=True)


# Zeigt den Mittelwertvergleich zwischen Baseline und optimierten Gewichten.
def vergleich_baseline_optimiert(benchmark):
    if not benchmark:
        return

    rows = []
    for label, seed_rows in benchmark.items():
        for row in seed_rows:
            item = dict(row)
            item["Steuerung"] = label
            rows.append(item)

    frame = pd.DataFrame(rows)
    metric_names = [
        "Makespan",
        "Tardiness",
        "Transportzeit",
        "Unfertige Jobs",
        "Intaktquote (%)",
        "Defektquote (%)",
        "Ausschussquote (%)",
        "Nacharbeitsquote (%)",
        "Herabstufungsquote (%)",
        "Gewichtete Summe der relativ zur Baseline skalierten Kennzahlen",
    ]
    mean_frame = frame.groupby(
        "Steuerung",
        as_index=False,
    )[metric_names].mean()

    st.subheader("Vergleich: Originalgewichte gegen optimierte Gewichte")
    st.dataframe(mean_frame, use_container_width=True, hide_index=True)

    chart_frame = frame.melt(
        id_vars=["Seed", "Steuerung"],
        var_name="Kennzahl",
        value_name="Wert",
    )
    chart = (
        alt.Chart(chart_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Seed:O", title="Seed"),
            y=alt.Y("Wert:Q", title="Wert", scale=alt.Scale(zero=False)),
            color=alt.Color("Steuerung:N", title="Steuerung"),
            facet=alt.Facet("Kennzahl:N", columns=3, title=None),
            tooltip=[
                "Seed:O",
                "Steuerung:N",
                "Kennzahl:N",
                "Wert:Q",
            ],
        )
        .properties(height=180)
        .resolve_scale(y="independent")
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)


# Simuliert einen lokalen Gewichtssatz mit allen Seeds und sammelt globale Kennzahlen.
def _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
    # Zustands-Dictionary des Streamlit-Webservers für Fortschritt und Ergebnisse.
    state,
    # Optimierer mit Simulationsrunner und globaler Kostenberechnung.
    optimizer,
    # Vollständiger lokaler Gewichtssatz mit allen einzelnen Heuristik-Gewichten.
    weights,
    # Gibt an, ob die Referenzwerte aus dieser Baseline berechnet werden.
    calculate_reference_values=False,
):
    metrics_by_seed = []
    for seed_index, seed in enumerate(SEEDS, start=1):
        # Legt nur die Statusmeldung im Streamlit-Webserver 
        # für den aktuellen Lauf fest.
        if calculate_reference_values:
            phase_name = "Baseline"
        else:
            phase_name = "Optimierte Gewichte"
        state["phase"] = (
            f"{phase_name}: Seed {seed_index}/{len(SEEDS)}"
        )
        # Führt die Simulation mit dem lokalen Gewichtssatz und diesem Seed aus.
        # metrics enthält danach die globalen Kennzahlen dieses Simulationslaufs.
        metrics = optimizer.simulation_runner(weights, seed)
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
            "Tardiness": metrics.total_tardiness,
            "Transportzeit": metrics.total_transport_time,
            "Unfertige Jobs": metrics.unfinished_jobs,
            "Intaktquote (%)": metrics.intact_rate * 100.0,
            "Defektquote (%)": metrics.defect_rate * 100.0,
            "Ausschussquote (%)": metrics.scrap_rate * 100.0,
            "Nacharbeitsquote (%)": metrics.rework_rate * 100.0,
            "Herabstufungsquote (%)": metrics.downgrade_rate * 100.0,
            # Die Kennzahlen werden relativ zur Baseline skaliert und anschließend gewichtet addiert.
            "Gewichtete Summe der relativ zur Baseline skalierten Kennzahlen": (
                optimizer.global_evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                    metrics
                )
            ),
        }
        rows.append(row)
    return rows


# Bereitet einen neuen Optimierungslauf vor und startet anschließend den Worker-Thread.
def _start_optimization(state, optimizer):
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
            f"Optimierung: Runde {iteration}, "
            f"Kandidat {candidate}/{total_candidates}"
        )

        if evaluation is None:
            return

        state["costs"].append(evaluation.mean_global_cost)
        if not evaluation.metrics_by_seed:
            return

        metrics_by_seed = evaluation.metrics_by_seed
        metric_row = {
            "Kandidat": len(state["costs"]),
            "Makespan": _mean_metric(metrics_by_seed, "makespan"),
            "Tardiness": _mean_metric(
                metrics_by_seed,
                "total_tardiness",
            ),
            "Transportzeit": _mean_metric(
                metrics_by_seed,
                "total_transport_time",
            ),
            "Unfertige Jobs": _mean_metric(
                metrics_by_seed,
                "unfinished_jobs",
            ),
            "Intaktquote (%)": _mean_metric(
                metrics_by_seed,
                "intact_rate",
            ) * 100.0,
            "Defektquote (%)": _mean_metric(
                metrics_by_seed,
                "defect_rate",
            ) * 100.0,
            "Ausschussquote (%)": _mean_metric(
                metrics_by_seed,
                "scrap_rate",
            ) * 100.0,
            "Nacharbeitsquote (%)": _mean_metric(
                metrics_by_seed,
                "rework_rate",
            ) * 100.0,
            "Herabstufungsquote (%)": _mean_metric(
                metrics_by_seed,
                "downgrade_rate",
            ) * 100.0,
            "Unfertigenquote (%)": _mean_metric(
                metrics_by_seed,
                "unfinished_rate",
            ) * 100.0,
        }
        state["metrics"].append(metric_row)

    # Berechnet Baseline, Optimierung und den anschließenden Benchmark.
    def worker():
        try:
            # Aktualisiert die Statusanzeige: Jetzt wird zuerst die Baseline berechnet.
            state["phase"] = "Baseline wird mit Originalgewichten berechnet ..."
        
            # hier liefert die Methode eine Zeile mit globalen Kennzahlen pro Seed.
            baseline_rows = _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
                # Übergibt den Streamlit-Webserver-Zustand für angezeigten Fortschritt,
                # Phase, Kennzahlen und Fehlermeldungen.
                state,
                # Übergibt den Optimierer, der die Simulation ausführt und bewertet.
                optimizer,
                # Erzeugt den unveränderten Standard-Gewichtssatz als Vergleichsbasis.
                HeuristicWeights(),
                # Berechnet aus der Baseline die Referenzwerte für die spätere relative Skalierung.
                calculate_reference_values=True,
            )

            # Startet die iterative Suche nach einem besseren lokalen Gewichtssatz
            # und speichert das Optimierungsergebnis im Streamlit-Webserver-Zustand.
            state["result"] = optimizer.optimize_iteratively(

                # Startet die Suche mit den unveränderten Standardgewichten.
                initial_local_weights=HeuristicWeights(),

                # Verwendet diese Seeds für jeden getesteten Gewichtssatz.
                seeds=SEEDS,

                # Legt die maximale Anzahl der Optimierungsrunden fest.
                iterations=ITERATIONS,

                # Legt die anfängliche relative Größe der Gewichtsänderungen fest.
                initial_local_weight_step_fraction=INITIAL_WEIGHT_STEP,

                # Legt fest, wie viele zusätzliche Kandidaten pro Runde getestet werden.
                exploration_candidate_count=EXPLORATION_CANDIDATES,

                # Startet nach dieser Anzahl erfolgloser Runden erneut.
                restart_after_no_improvement=RESTART_AFTER_NO_IMPROVEMENT,

                # Beendet die Suche nach dieser Anzahl erfolgloser Runden.
                stop_after_no_improvement=STOP_AFTER_NO_IMPROVEMENT,
                
                # Aktualisiert den Streamlit-Webserver über den aktuellen Fortschritt.
                progress_callback=progress,
            )

            # Simuliert den besten lokalen Gewichtssatz mit allen Seeds und sammelt
            # pro Seed globale Kennzahlen sowie deren gewichtete relative Summe.
            optimized_rows = _simulate_and_collect_global_metrics_for_one_local_weight_across_all_seeds(
                state,
                optimizer,
                state["result"].best_weights,
            )
            state["benchmark"] = {
                "Baseline": baseline_rows,
                "Optimiert": optimized_rows,
            }
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
    # Erstellt den Optimierer für das gefundene Modell.
    optimizer = create_optimizer(
        # Übergibt den Modellpfad als Zeichenkette an create_optimizer().
        str(selected_model_path),
        # Übergibt den Änderungszeitpunkt als Streamlit-Cache-Schlüssel.
        selected_model_path.stat().st_mtime_ns,
    )

    st.title("SpineML – heuristische Optimierung")
    st.caption(f"Beispiel: {selected_model_path.name}")

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
    # Zeigt den Startbutton und ruft beim Anklicken
    # _start_optimization(state, optimizer) mit diesen beiden Argumenten auf.
    st.button(
        "Optimierung starten",
        disabled=state["running"],
        on_click=_start_optimization,
        args=(state, optimizer),
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
                or "Optimierung läuft – Kandidaten werden simuliert ..."
            )
            iteration.write(f"Aktuelle Iteration: {state['iteration']}")
            candidate.write(
                f"Kandidat: {state['candidate']} / "
                f"{state['total_candidates'] or '?'}"
            )
            if state["total_candidates"]:
                progress_bar.progress(
                    state["candidate"] / state["total_candidates"]
                )
            if state["costs"]:
                globale_kosten_pro_kandidat(state["costs"], cost_chart)
                mittlere_kennzahlen_pro_kandidat(
                    state["metrics"],
                    metric_chart,
                )
                kennzahlenabweichung_gegen_kandidat_1(
                    state["metrics"],
                    delta_chart,
                )
                latest.caption(
                    f"Letzte mittlere globale Kosten: "
                    f"{state['costs'][-1]:.2f}"
                )
            else:
                latest.caption("Noch kein Kandidat vollständig bewertet.")
            time.sleep(0.5)

    if state["error"]:
        st.error(state["error"])
    elif state["result"] is not None:
        st.success("Optimierung abgeschlossen")
        globale_kosten_pro_kandidat(state["costs"])
        st.subheader("Mittlere Kennzahlen pro Kandidat")
        mittlere_kennzahlen_pro_kandidat(state["metrics"])
        st.subheader("Kennzahlenabweichung gegenüber Kandidat 1")
        kennzahlenabweichung_gegen_kandidat_1(state["metrics"])
        st.write("Beste lokale Gewichte", state["result"].best_weights)
        st.write(
            "Beste mittlere globale Kosten",
            state["result"].best_mean_global_cost,
        )
        st.write(
            "Referenzwerte der Baseline",
            state["baseline_reference_values"],
        )
        vergleich_baseline_optimiert(state["benchmark"])

if __name__ == "__main__" and st.runtime.exists():
    _streamlit_app()
