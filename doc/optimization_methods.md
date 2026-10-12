# Methodenreferenz: `sources/optimization.py`

Diese Datei erklärt den Optimierer für Python-Anfänger. Für jede Methode stehen
Zweck, konkrete Eingabe, Rückgabe und Wirkung. Die Beispiele zeigen normale
Python-Werte. Speicheradressen wie `<Layout object at 0x...>` sind unwichtig.

## 1. Ablauf nach dem Play-Button

### Prozess 1: Python-Starter

Du startest:

~~~text
.venv\Scripts\python.exe sources\optimization.py
~~~

Python führt die Datei als erstes Programm aus.

- Eingabe von `main()`: keine Argumente.
- Rückgabe von `main()`: normalerweise `None`.
- Wirkung: `main()` startet einen zweiten Python-Prozess mit Streamlit und
  wartet auf diesen Prozess.

Inhaltlich startet `main()` diesen Befehl:

~~~text
.venv\Scripts\python.exe -m streamlit run sources\optimization.py
~~~

Prozess 1 ist nicht die Weboberfläche. Er wartet nur. Prozess 2 ist der lokale
Streamlit-Webserver. Der Browser zeigt Prozess 2 an; der Browser führt keinen
Python-Code aus.

### Prozess 2: Streamlit

Streamlit führt `optimization.py` erneut aus. Jetzt ist
`st.runtime.exists()` wahr, deshalb wird kein dritter Server gestartet. Am
Ende ruft Prozess 2 auf:

~~~python
_streamlit_app()
~~~

- Eingabe: keine direkten Argumente; die Funktion liest die Sitzung.
- Rückgabe: `None`.
- Wirkung: die aktuelle Browserseite wird aufgebaut.

Beim Klick auf den Button ruft Streamlit als Callback auf:

~~~python
_start_optimization(state, optimizer)
~~~

Danach kann Streamlit das Script erneut ausführen (Rerun). Das ist die normale
Arbeitsweise von Streamlit.

## 2. Globale Einstellungen

~~~python
EXAMPLE_FILE = "example-2.py"
SEEDS = [1, 2]
ITERATIONS = 2
INITIAL_WEIGHT_STEP = 0.40
EXPLORATION_CANDIDATES = 3
~~~

Konkret bedeutet das:

- Standardmäßig wird `sources/examples/normal/example-2.py` geladen.
- Jeder Gewichtssatz wird mit Seed 1 und Seed 2 simuliert.
- Es gibt höchstens zwei Optimierungsrunden.
- Nachbar-Gewichte werden zunächst um `0.40` verändert.
- Pro Runde werden drei zusätzliche zufällige Gewichtssätze erzeugt.

Änderst du `EXAMPLE_FILE` auf `"example-1.py"`, optimiert der Play-Button
Example 1. Die Variable ist eine normale Python-Variable, keine Windows-
Systemvariable.

## 3. Methode `_resolve_model_path`

~~~python
_resolve_model_path(model_file: str | Path) -> Path
~~~

### Zweck

Sie sucht die Modelldatei und liefert ihren vollständigen Pfad. Sie führt die
Datei noch nicht aus.

### Eingabe

`model_file` ist Text oder ein `Path`:

~~~python
"example3"
"example-3.py"
Path("C:/Projekt/sources/examples/normal/example-3.py")
~~~

### Was passiert Schritt für Schritt?

1. `Path(str(model_file))` macht aus Text und `Path` ein einheitliches Objekt.
2. Der reguläre Ausdruck erkennt `example3`, `example-3`, `example_3.py` usw.
3. Zu `example3` wird zusätzlich `example-3` ausprobiert.
4. Gesucht wird im aktuellen Arbeitsordner, in `sources` sowie in den Ordnern
   `sources/examples/normal` und `sources/examples/optimization`.
5. Ohne Endung wird zusätzlich `.py` versucht.
6. Die erste vorhandene Python-Datei wird zurückgegeben.

### Konkrete Ausgabe

~~~text
Eingabe:  "example3"
Ausgabe:  C:\Users\...\Hackenberg\sources\examples\normal\example-3.py
Typ:      pathlib.Path
~~~

Existiert keine Datei, gibt es keinen normalen Rückgabewert. Stattdessen
entsteht `FileNotFoundError` mit allen geprüften Pfaden.

## 4. Methode `_find_layout_and_scenario`

~~~python
_find_layout_and_scenario(model: dict[str, object], model_path: Path)
    -> tuple[object, object]
~~~

### Zweck

Diese eine Methode liest selbst den Quelltext und wählt die Konfiguration für
die Optimierung. Sie ersetzt damit die frühere zusätzliche Suchmethode.

### Eingabe

`model` ist das Dictionary aus `runpy.run_path`. Es enthält alle globalen
Namen der ausgeführten Modelldatei, zum Beispiel:

~~~python
{
    "__name__": "spine_model",
    "__file__": ".../examples/normal/example-3.py",
    "s3": <Scenario ...>,
    "l3": <Layout ...>,
    "simulate": <function simulate ...>,
}
~~~

`model_path` ist der Pfad zur Quelldatei.

### Was passiert intern?

1. Die Methode liest mit `model_path.read_text(...)` den Quelltext.
2. `ast.parse(...)` macht daraus einen Python-Syntaxbaum.
3. Sie sucht Aufrufe wie:

~~~python
simulate(l3, s3, till=sim.inf)
~~~

4. Die Namen `l3` und `s3` werden im Dictionary `model` nachgeschlagen.
5. Die zugehörigen Layout- und Szenarioobjekte werden zurückgegeben.
6. Falls kein passender Aufruf existiert, wird geprüft, ob genau ein Layout und
   genau ein Szenario vorhanden sind.
7. Bei mehreren möglichen Objekten entsteht ein `ValueError`.

### Auswahlreihenfolge

1. `simulate(layout, scenario)` im Quelltext verwenden.
2. Sonst das einzige Layout und das einzige Szenario verwenden.
3. Sonst einen Fehler melden.

### Konkrete Ausgabe

~~~text
(
    Layout("Layout 3"),
    Scenario("Schicht 3")
)
~~~

Der Rückgabewert ist ein Tupel, kein Dateiname und kein Dictionary.

## 5. Kontextmanager `_suppress_model_visualization`

~~~python
_suppress_model_visualization()
~~~

### Zweck

Ein Example kann am Ende selbst `simulate(...)` aufrufen. Beim Laden durch den
Optimierer soll dadurch noch keine Simulation gestartet werden.

~~~python
with _suppress_model_visualization():
    model = runpy.run_path(...)
~~~

Während des Blocks wird diese Funktion kurz durch eine leere Funktion ersetzt.
Beim Verlassen wird die Originalfunktion wiederhergestellt.

### Eingabe und Ausgabe

- Eingabe: keine sichtbaren Argumente.
- Eintritt: Originalfunktionen speichern und ersetzen.
- Im Block: unterdrückte Aufrufe geben `None` zurück.
- Austritt: Originalfunktionen wiederherstellen.
- Rückgabe: Der Kontextmanager liefert nicht das Modelldictionary; dieses kommt
  weiterhin von `runpy.run_path`.

## 6. Methode `_load_model`

~~~python
_load_model(model_path: Path) -> dict[str, object]
~~~

### Zweck

Sie führt die Modelldatei mit `runpy.run_path` aus und sammelt globale
Variablen in einem Dictionary. Die Visualisierung wird dabei unterdrückt.

### Eingabe

~~~text
Path("C:/.../sources/examples/normal/example-3.py")
~~~

### Konkrete Ausgabe

~~~python
model = {
    "__name__": "spine_model",
    "__file__": ".../examples/normal/example-3.py",
    "mt1": MachineType(...),
    "tt1": ToolType(...),
    "pt1": ProductType(...),
    "op1": OperationType(...),
    "s3": Scenario(...),
    "o3_1": Order(...),
    "l3": Layout(...),
    "c3_1": Corridor(...),
    "Machine": <class ...>,
    "simulate": <function ...>,
}
~~~

Schlüssel sind Namen aus der Datei; Werte sind die Python-Objekte. Das
Dictionary enthält auch importierte Namen und Funktionen, nicht nur Maschinen.

## 7. Methode `_global_evaluation`

~~~python
_global_evaluation() -> GlobalSimulationEvaluation
~~~

### Zweck

Sie erstellt die globale Zielfunktion. Diese übersetzt Simulationskennzahlen
in eine Zahl: globale Kosten. Niedrigere Kosten sind besser.

### Eingabe

Keine. Intern werden diese Gewichtungen verwendet:

~~~python
GlobalSimulationWeights(
    makespan=5.0,
    total_tardiness=4.0,
    total_transport_time=1.0,
    tool_change_time=1.0,
    blocking_time=1.0,
    nacharbeit_job_penalty=3.0,
    job_scrap_weight=4.0,
    unfinished_jobs=20.0,
    defect_job_penalty=3.0,
    non_intact_penalty=3.0,
)
~~~

### Ausgabe

~~~text
<GlobalSimulationEvaluation object>
~~~

Das Objekt enthält die Gewichte und später die aus der Baseline berechneten
Normalisierungsskalen.

## 8. Methode `create_optimizer`

~~~python
create_optimizer(model_file: str, model_stamp: int)
~~~

### Zweck

Sie verbindet Modelldatei, Layout, Szenario, Simulations-Runner und globale
Kostenfunktion zu einem Optimierer.

### Eingabe

~~~python
model_file = "example-3.py"
model_stamp = 1720000000000000000
~~~

`model_stamp` ist die Änderungszeit der Datei als Cache-Schlüssel, kein
Simulationswert. Wenn sich die Datei ändert, kann Streamlit ein neues Objekt
erzeugen.

### Interne Reihenfolge

1. `_resolve_model_path` findet die Datei.
2. `_load_model` führt die Modelldefinition aus.
3. `_find_layout_and_scenario` wählt Layout und Szenario.
4. Es wird erstellt:
   `SpineMLSimulationRunner(layout, scenario, till=sim.inf)`.
5. `_global_evaluation()` erstellt die globale Bewertung.
6. Beides wird in `LocalHeuristicWeightOptimizer` eingesetzt.

### Ausgabe

~~~text
<LocalHeuristicWeightOptimizer object>
~~~

Wichtige Attribute:

~~~python
optimizer.simulation_runner  # Funktion (Gewichte, Seed)
optimizer.global_evaluation  # Objekt für globale Kosten
~~~

`@st.cache_resource` speichert diesen Optimierer im Python-Prozess. Der Cache
ist nicht automatisch als Dictionary im Browser sichtbar.

## 9. Innere Funktion `run_simulation`

~~~python
def run_simulation(weights, seed):
    return runner(weights, seed)
~~~

### Eingabe und Ausgabe

~~~python
weights = HeuristicWeights(...)
seed = 1
~~~

~~~text
Ausgabe:
GlobalSimulationMetrics(
    makespan=344.14,
    total_tardiness=0.0,
    total_transport_time=246.12,
    ...
)
~~~

`runner(weights, seed)` startet einen vollständigen SpineML-Lauf. Wegen
`till=sim.inf` läuft er, bis die Jobs fertig sind. Die Funktion ist eine
Verbindung zwischen dem allgemeinen Optimierer und dem konkreten
`SpineMLSimulationRunner`.

## 10. Methode `_mean_metric`

~~~python
_mean_metric(metrics_by_seed, attribute_name: str) -> float
~~~

### Zweck

Sie bildet den Mittelwert einer Kennzahl über mehrere Seeds.

### Eingabe

~~~python
metrics_by_seed = (
    GlobalSimulationMetrics(makespan=340.0, ...),
    GlobalSimulationMetrics(makespan=360.0, ...),
)
attribute_name = "makespan"
~~~

Die Methode liest bei jedem Objekt das Attribut mit diesem Namen:

~~~python
total_value = 0.0
for metrics in metrics_by_seed:
    metric_value = getattr(metrics, attribute_name)
    total_value += float(metric_value)

return total_value / len(metrics_by_seed)
~~~

### Ausgabe

~~~text
(340.0 + 360.0) / 2 = 350.0
Typ: float
~~~

`getattr(metrics, "makespan")` bedeutet: Lies das Attribut `makespan` aus dem
jeweiligen Metrics-Objekt.

## 11. Diagrammfunktion `globale_kosten_pro_kandidat`

~~~python
globale_kosten_pro_kandidat(costs, container=None)
~~~

### Zweck

Sie zeichnet die mittleren globalen Kosten jedes getesteten Kandidaten.

### Eingabe

~~~python
costs = [14.13, 14.13, 14.27, 13.61]
container = ein Streamlit-Platzhalter oder None
~~~

Daraus entsteht intern diese Tabelle:

~~~text
Kandidat | Mittlere globale Kosten
1        | 14.13
2        | 14.13
3        | 14.27
4        | 13.61
~~~

### Ausgabe

Es gibt keinen sinnvollen Python-Rückgabewert: Rückgabe `None`. Als
Seiteneffekt wird ein Altair-Liniendiagramm im Browser gezeichnet. Die Liste
`costs` wird nicht verändert.

## 12. Diagrammfunktion `mittlere_kennzahlen_pro_kandidat`

~~~python
mittlere_kennzahlen_pro_kandidat(metrics, container=None)
~~~

### Zweck

Sie zeigt pro Kandidat die Kennzahlen-Mittelwerte über alle Seeds.

### Eingabe

~~~python
metrics = [
    {
        "Kandidat": 1,
        "Makespan": 350.0,
        "Tardiness": 2.0,
        "Transportzeit": 240.0,
        "Unfertige Jobs": 0.0,
        "Intaktquote (%)": 50.0,
        "Defektquote (%)": 62.5,
        "Ausschussquote (%)": 25.0,
        "Nacharbeitsquote (%)": 12.5,
        "Unfertigenquote (%)": 0.0,
    }
]
~~~

### Ausgabe

Rückgabe `None`; als Seiteneffekt wird ein Altair-Diagramm gerendert.
Die Prozentwerte sind hier schon mit `* 100` umgerechnet. Die Diagrammfunktion
multipliziert sie nicht noch einmal.

## 13. Diagrammfunktion `kennzahlenabweichung_gegen_kandidat_1`

~~~python
kennzahlenabweichung_gegen_kandidat_1(metrics, container=None)
~~~

### Zweck

Sie vergleicht jeden Kandidaten mit Kandidat 1. Für jede Kennzahl gilt:

~~~text
(Kennzahl des Kandidaten - Kennzahl von Kandidat 1)
--------------------------------------------------- * 100
        |Kennzahl von Kandidat 1|
~~~

### Konkretes Beispiel

~~~text
Kandidat 1 Makespan = 350
Kandidat 2 Makespan = 315

(315 - 350) / 350 * 100 = -10 %
~~~

`-10 %` bedeutet zehn Prozent weniger Zeit. Ist der Wert des ersten
Kandidaten `0`, setzt die Methode die Abweichung auf `0`, statt durch null zu
teilen.

### Ausgabe

Rückgabe `None`; ein Abweichungsdiagramm wird in Streamlit gezeichnet. Die
Eingabeliste wird nicht als Ergebnis zurückgegeben.

## 14. Methode `vergleich_baseline_optimiert`

~~~python
vergleich_baseline_optimiert(benchmark) -> None
~~~

### Zweck

Sie vergleicht Originalgewichte (Baseline) und beste gefundene Gewichte.

### Eingabe

~~~python
benchmark = {
    "Baseline": [
        {
            "Seed": 1,
            "Makespan": 344.0,
            "Tardiness": 0.0,
            "Transportzeit": 246.0,
            "Unfertige Jobs": 0,
            "Intaktquote (%)": 43.75,
            "Defektquote (%)": 75.0,
            "Ausschussquote (%)": 37.5,
            "Nacharbeitsquote (%)": 25.0,
            "Globale Kosten": 14.20,
        },
        # Zeile für Seed 2
    ],
    "Optimiert": [
        # Zeile für Seed 1 und Zeile für Seed 2
    ],
}
~~~

Für jede Zeile wird eine Kopie angelegt und ein Feld ergänzt:

~~~python
item["Steuerung"] = "Baseline"
~~~

oder:

~~~python
item["Steuerung"] = "Optimiert"
~~~

### Ausgabe

Rückgabe `None`. Die Methode erzeugt eine Tabelle mit Mittelwerten je
Steuerung und ein Diagramm je Kennzahl und Seed. Die Benchmark-Daten selbst
werden nicht verändert.

## 15. Methode `_run_benchmark`

~~~python
_run_benchmark(
    state,
    optimizer,
    weights,
    calibrate_normalization=False,
) -> list[dict]
~~~

### Zweck

Sie simuliert einen konkreten lokalen Gewichtssatz mit allen Seeds und baut
Tabellenzeilen für die Anzeige.

### Eingabe

~~~python
weights = HeuristicWeights()
calibrate_normalization = True
~~~

`state` ist das Sitzungs-Dictionary. `optimizer` enthält die Funktion
`simulation_runner` und die globale Bewertung.

### Ablauf mit `SEEDS = [1, 2]`

1. Seed 1 wird simuliert.
2. Seed 2 wird simuliert.
3. Beide Metrics-Objekte landen in `metrics_by_seed`.
4. Bei `True` werden Zeitmittelwerte der Baseline zu Skalen.
5. Für jeden Seed wird eine Zeile erstellt.

### Konkrete Ausgabe

~~~python
[
    {
        "Seed": 1,
        "Makespan": 344.0,
        "Tardiness": 0.0,
        "Transportzeit": 246.0,
        "Unfertige Jobs": 0,
        "Intaktquote (%)": 43.75,
        "Defektquote (%)": 75.0,
        "Ausschussquote (%)": 37.5,
        "Nacharbeitsquote (%)": 25.0,
        "Globale Kosten": 14.20,
    },
    {
        "Seed": 2,
        # dieselben Spalten, Werte aus Seed 2
    },
]
~~~

Bei zwei Seeds gibt es zwei Zeilen, aber nur einen getesteten lokalen
Gewichtssatz. Die globale Kosten-Spalte enthält Kosten je Seed; der
Optimierer bildet zusätzlich den Seed-Mittelwert.

Bei der Baseline wird außerdem geschrieben:

~~~python
state["normalization_scales"] = {
    "makespan": 350.0,
    "total_tardiness": 1.0,
    "total_transport_time": 240.0,
    "tool_change_time": 35.0,
    "blocking_time": 1.0,
}
~~~

Diese fünf Einträge sind Zeit-Skalen. Qualitätsraten stehen nicht darin,
sondern werden direkt als Raten verwendet.

### Warum ist `calibrate_normalization=False` der Standard?

`False` bedeutet nicht, dass keine Kennzahlen und keine globalen Kosten
berechnet werden. Beides wird immer berechnet. Der Parameter entscheidet nur,
ob dieser Lauf neue Zeit-Skalen erzeugt:

~~~text
Baseline-Lauf:       True  -> Skalen aus der Baseline berechnen und speichern
Optimierter Lauf:    False -> dieselben Baseline-Skalen wiederverwenden
~~~

So werden Baseline und Optimiert fair mit derselben Bezugsgröße verglichen.

## 16. Methode `_start_optimization`

~~~python
_start_optimization(state, optimizer) -> None
~~~

### Zweck

Sie wird genau beim Button-Klick aufgerufen. Sie setzt den alten Lauf zurück
und startet den Rechen-Thread.

### Eingabe

- `state`: Dictionary der aktuellen Streamlit-Sitzung
- `optimizer`: Ergebnis von `create_optimizer`

### Erster Schritt: Zustand zurücksetzen

~~~python
state.update(
    running=True,
    iteration=0,
    candidate=0,
    total_candidates=0,
    costs=[],
    metrics=[],
    result=None,
    benchmark=None,
    normalization_scales={},
    phase="",
    error=None,
)
~~~

Nur alte Anzeige- und Ergebniswerte werden zurückgesetzt. Layout-, Szenario-
und Maschinenobjekte werden dadurch nicht gelöscht.

### Zweiter Schritt

Die inneren Funktionen `progress` und `worker` werden definiert. Danach startet:

~~~python
threading.Thread(target=worker, daemon=True).start()
~~~

### Ausgabe

Rückgabe `None`. Die zeitaufwendige Arbeit läuft danach im Hintergrundthread.
`daemon=True` bedeutet: Dieser Thread hält das Programm beim Beenden nicht
künstlich offen. Er ist kein zweiter Prozess, sondern ein Thread im
Streamlit-Prozess.

## 17. Innere Methode `progress`

~~~python
progress(iteration, evaluation, candidate, total_candidates) -> None
~~~

### Zweck

Der Optimierer ruft sie vor und nach jedem Kandidaten auf, damit der
Fortschritt sichtbar wird.

### Eingabe vor der Simulation

~~~python
iteration = 1
evaluation = None
candidate = 1
total_candidates = 50
~~~

Bedeutung: Runde 1, Kandidat 1 von 50; es gibt noch keine fertige Bewertung.

### Eingabe nach der Simulation

~~~python
iteration = 1
evaluation = WeightEvaluation(
    weights=<ein lokaler Gewichtssatz>,
    objective_values=(14.10, 13.80),
    mean_global_cost=13.95,
    metrics_by_seed=(metrics_seed1, metrics_seed2),
)
candidate = 1
total_candidates = 50
~~~

### Wirkung auf `state`

~~~python
state["iteration"] = 1
state["candidate"] = 1
state["total_candidates"] = 50
state["costs"].append(13.95)
~~~

Zusätzlich wird eine Kennzahlenzeile mit Mittelwerten über Seed 1 und Seed 2
an `state["metrics"]` angehängt:

~~~python
state["metrics"][-1] = {
    "Kandidat": 1,
    "Makespan": 350.0,
    "Tardiness": 0.0,
    "Transportzeit": 240.0,
    "Unfertige Jobs": 0.0,
    "Intaktquote (%)": 43.75,
    "Defektquote (%)": 75.0,
    "Ausschussquote (%)": 37.5,
    "Nacharbeitsquote (%)": 25.0,
    "Unfertigenquote (%)": 0.0,
}
~~~

Die Rückgabe ist `None`; die Information wird über `state` weitergegeben.

### Bedeutung der Zähler

- `iteration`: Nummer der Optimierungsrunde; eine Runde prüft viele Kandidaten.
- `candidate`: Nummer des gerade geprüften lokalen Gewichtssatzes.
- `total_candidates`: Gesamtzahl der Kandidaten in dieser Runde.

Eine Runde sieht so aus:

~~~text
Runde 1
├─ Kandidat 1: Gewichte mit Seed 1 und Seed 2 simulieren
├─ Kandidat 2: Gewichte mit Seed 1 und Seed 2 simulieren
├─ ...
└─ Kandidat 50: Gewichte mit Seed 1 und Seed 2 simulieren
~~~

Ein Kandidat ist ein lokaler Gewichtssatz. Ein Seed ist keine Gewichtung,
sondern eine feste Zufallsbedingung für einen Simulationslauf.

## 18. Innere Methode `worker`

~~~python
worker() -> None
~~~

### Zweck

Sie enthält die vollständige, zeitaufwendige Reihenfolge. Sie erhält keine
Argumente, weil sie auf `state`, `optimizer` und äußere Konstanten zugreift.

### Exakte Reihenfolge

1. `state["phase"]` wird auf `"Baseline wird mit Originalgewichten berechnet ..."`
   gesetzt.
2. `_run_benchmark(..., HeuristicWeights(), True)` simuliert Baseline mit Seed 1
   und Seed 2.
3. Die Baseline-Mittelwerte kalibrieren Zeit-Normalisierung.
4. `optimizer.optimize_iteratively(...)` erzeugt und bewertet Kandidaten.
5. `progress` aktualisiert Kosten, Kennzahlen und Zähler.
6. `state["result"]` erhält das beste Optimierungsergebnis.
7. Das beste Gewicht wird mit beiden Seeds erneut simuliert.
8. `state["benchmark"]` erhält Baseline- und Optimiert-Zeilen.
9. Bei einem Fehler wird `state["error"]` gesetzt.
10. Im `finally`-Block wird `state["running"] = False` gesetzt.

### Konkretes Ergebnis in `state["result"]`

~~~python
WeightOptimizationResult(
    best_weights=HeuristicWeights(...),
    best_mean_global_cost=13.61,
    evaluations=(
        WeightEvaluation(
            weights=HeuristicWeights(...),
            objective_values=(14.00, 13.22),
            mean_global_cost=13.61,
            metrics_by_seed=(metrics_seed1, metrics_seed2),
        ),
    ),
)
~~~

`best_weights` ist der beste lokale Gewichtssatz. `best_mean_global_cost` ist
dessen Kostenmittelwert über beide Seeds. `evaluations` speichert Bewertungen
der verbesserten Lösungen.

### Konkretes Ergebnis in `state["benchmark"]`

~~~python
{
    "Baseline":  [Zeile für Seed 1, Zeile für Seed 2],
    "Optimiert": [Zeile für Seed 1, Zeile für Seed 2],
}
~~~


## 19. Methode `main`

~~~python
main() -> None
~~~

### Zweck

Sie startet Streamlit, wenn die Datei direkt mit dem Play-Button oder Python
gestartet wird.

### Eingabe

Keine direkten Argumente. Optional wird diese Variable gelesen:

~~~python
os.environ.get("SPINEML_MODEL_FILE", EXAMPLE_FILE)
~~~

Wenn sie nicht existiert, wird `EXAMPLE_FILE` benutzt.

### Ausgabe und Wirkung

- Rückgabe: `None`, nachdem der Streamlit-Prozess beendet wurde.
- Währenddessen wartet Prozess 1 in `subprocess.run`.
- Wenn Streamlit beendet wird, läuft `subprocess.run` zurück und `main` endet.

Ein Prozessende kann durch Schließen von Streamlit oder `Ctrl+C` im Terminal
erfolgen. `Ctrl+C` beendet den Prozess, dessen Terminal die Tastenkombination
empfängt.

## 20. Methode `_streamlit_app`

~~~python
_streamlit_app() -> None
~~~

### Zweck

Sie baut die Weboberfläche bei jedem Streamlit-Rerun auf.

### Eingabe

Keine direkten Argumente. Sie liest:

- `SPINEML_MODEL_FILE` oder `EXAMPLE_FILE`,
- die Modelldatei,
- `st.session_state`.

### Sitzungs-Dictionary

Beim ersten Rerun wird dieses Dictionary angelegt:

~~~python
st.session_state.optimization_state = {
    "running": False,
    "iteration": 0,
    "candidate": 0,
    "total_candidates": 0,
    "costs": [],
    "metrics": [],
    "result": None,
    "benchmark": None,
    "normalization_scales": {},
    "phase": "",
    "error": None,
}
~~~

Dieses Dictionary liegt im Streamlit-Pythonprozess auf dem PC. Es ist nicht
automatisch als Python-Dictionary im Browser sichtbar. Der Browser sieht nur,
was mit `st.write`, `st.info`, `st.dataframe` oder Diagrammen gerendert wird.

### Button

~~~python
st.button(
    "Optimierung starten",
    disabled=state["running"],
    on_click=_start_optimization,
    args=(state, optimizer),
)
~~~

- Bei `running=False` ist der Button anklickbar.
- Beim Klick ruft Streamlit `_start_optimization(state, optimizer)` auf.
- Diese Methode setzt sofort `running=True`.
- Bei `running=True` wird der Button deaktiviert.
- Nach dem Ende setzt `worker` `running=False`; danach ist er wieder aktiv.

### Platzhalter

~~~python
status = st.empty()
iteration = st.empty()
candidate = st.empty()
progress_bar = st.empty()
~~~

`st.empty()` schreibt nichts in `state`. Es erzeugt einen leeren
Anzeigebereich. Derselbe Bereich kann später aktualisiert werden:

~~~python
status.info("Baseline ...")
iteration.write("Aktuelle Iteration: 1")
candidate.write("Kandidat: 3 / 50")
~~~

`st.info` ist eine blaue Informationsbox. Sie ist eine Streamlit-Methode des
Anzeigebereichs, kein Schlüssel des Zustands-Dictionaries.

Während `state["running"]` wahr ist, liest die Oberfläche aktuelle Werte und
wartet jeweils `0.5` Sekunden. `time.sleep(0.5)` startet keine Simulation; es
verhindert nur zu häufiges Abfragen.

Nach dem Ende:

~~~python
if state["result"] is not None:
    st.success("Optimierung abgeschlossen")
~~~

`st.success` zeichnet eine grüne Erfolgsmeldung. Danach werden Diagramme,
beste Gewichte, beste Kosten, Skalen und der Baseline-Vergleich angezeigt.

## 21. Aufgerufene Optimierermethoden

Diese Methoden liegen nicht in `optimization.py`, werden aber von `worker` über
`optimizer` aufgerufen.

### `optimize_iteratively`

Eingabe:

~~~python
initial_local_weights = HeuristicWeights()
seeds = [1, 2]
iterations = 2
~~~

Ausgabe:

~~~python
WeightOptimizationResult(
    best_weights=...,
    best_mean_global_cost=...,
    evaluations=(...),
)
~~~

Pro Runde werden Nachbarn und Explorationskandidaten erzeugt. Jeder Kandidat
wird mit beiden Seeds simuliert. Der niedrigste Seed-Mittelwert gewinnt.

### `neighboring_weights`

Eingabe:

~~~python
local_weights = HeuristicWeights(queue_priority=0.4)
weight_step_fraction = 0.4
~~~

Ausgabe: mehrere neue `HeuristicWeights`-Objekte: der aktuelle Satz sowie
Sätze mit einem einzelnen Gewicht um `-0.4` oder `+0.4` verändert. Werte
bleiben zwischen `0.0` und `1.0`. Es wird noch nicht simuliert.

### `random_local_weight_candidates`

Eingabe:

~~~python
candidate_count = 3
rng = random.Random(0)
~~~

Ausgabe: Tupel mit drei zufällig erzeugten lokalen Gewichtssätzen. Dieser
Zufallsgenerator erzeugt Suchkandidaten; er ist nicht der Seed für
Defektereignisse in der Simulation.

### `select_best_local_weight_set_across_seeds`

Eingabe: Kandidatenliste, Seeds und optionaler Fortschritts-Callback.

Ausgabe: `WeightOptimizationResult` für diese eine Runde. In
`evaluations` stehen alle geprüften Kandidaten; `best_weights` ist der
Kandidat mit den kleinsten mittleren globalen Kosten.

### `evaluate_local_weights_across_seeds`

Eingabe:

~~~python
local_weights = HeuristicWeights(...)
seeds = [1, 2]
~~~

Ausgabe:

~~~python
WeightEvaluation(
    weights=local_weights,
    objective_values=(14.10, 13.80),
    mean_global_cost=13.95,
    metrics_by_seed=(metrics_seed1, metrics_seed2),
)
~~~

Die beiden Kostenwerte gehören zu demselben Gewichtssatz, aber zu zwei Seeds.
Der Mittelwert `13.95` ist der Wert, nach dem verglichen wird.

## 22. Aufgerufene globale Bewertung

### `calibrate_from_baseline`

Eingabe: die beiden Baseline-`GlobalSimulationMetrics`-Objekte.

Ausgabe:

~~~python
{
    "makespan": 350.0,
    "total_tardiness": 1.0,
    "total_transport_time": 240.0,
    "tool_change_time": 35.0,
    "blocking_time": 1.0,
}
~~~

Jede Zahl ist der Mittelwert über die Baseline-Seeds. Qualitätsraten stehen
nicht in diesem Dictionary; sie werden direkt als Raten verwendet. Bei einem
Zeitmittelwert `0` wird eine sichere Ersatzskala (mindestens `1.0`) benutzt,
damit keine Division durch null entsteht.

### `normalized_metrics`

Eingabe: ein einzelnes `GlobalSimulationMetrics`.

Ausgabe:

~~~python
{
    "makespan": 0.98,
    "total_tardiness": 0.0,
    "total_transport_time": 1.02,
    "tool_change_time": 0.90,
    "blocking_time": 0.0,
    "rework_rate": 0.25,
    "scrap_rate": 0.375,
    "defect_rate": 0.75,
    "non_intact_rate": 0.5625,
    "unfinished_rate": 0.0,
}
~~~

Zeitwerte werden durch ihre Baseline-Skala geteilt. Qualitätswerte bleiben
Anteile zwischen `0` und `1`.

### `evaluate`

Eingabe: ein einzelnes Metrics-Objekt.

Ausgabe: eine einzelne Zahl, zum Beispiel `13.61`. Jede normalisierte Kennzahl
wird mit ihrem globalen Gewicht multipliziert; alle Produkte werden addiert.
Die kleinere Zahl ist das bessere Ergebnis.

## 23. Metrics-Objekt und abgeleitete Quoten

Eine Simulation liefert ein `GlobalSimulationMetrics`-Objekt. Ein konkretes
Objekt kann so aussehen:

~~~python
GlobalSimulationMetrics(
    makespan=344.0,
    total_tardiness=0.0,
    total_transport_time=246.0,
    tool_change_time=35.0,
    blocking_time=0.0,
    rework_job_count=2.0,
    scrap_job_count=3.0,
    unfinished_jobs=0,
    total_jobs=8,
    completed_jobs=8,
    intact_jobs=5,
    defect_jobs=6,
)
~~~

Das Objekt speichert Rohzahlen. Die Eigenschaften berechnen daraus Quoten:

~~~text
intact_rate     = 5 / 8 = 0.625
rework_rate     = 2 / 8 = 0.250
scrap_rate      = 3 / 8 = 0.375
defect_rate     = 6 / 8 = 0.750
unfinished_rate = 0 / 8 = 0.000
~~~

Für die Browser-Tabelle schreibt `_run_benchmark` zum Beispiel
`rework_rate * 100` und zeigt deshalb `25.0` Prozent. Für die globale
Kostenfunktion bleibt derselbe Wert `0.25`; dort wird nicht nochmals mit 100
multipliziert.

## 24. Die beiden Ergebnis-Datentypen

### `WeightEvaluation`

Dieses Objekt beschreibt genau **einen lokalen Gewichtssatz**, der mit allen
Seeds geprüft wurde:

~~~python
WeightEvaluation(
    weights=HeuristicWeights(...),
    objective_values=(14.10, 13.80),
    mean_global_cost=13.95,
    metrics_by_seed=(metrics_seed1, metrics_seed2),
)
~~~

- `weights`: der getestete lokale Gewichtssatz,
- `objective_values`: eine globale Kosten-Zahl je Seed,
- `mean_global_cost`: Mittelwert dieser Kosten,
- `metrics_by_seed`: ein Metrics-Objekt je Seed.

### `WeightOptimizationResult`

Dieses Objekt ist die Ausgabe des gesamten Optimierers:

~~~python
WeightOptimizationResult(
    best_weights=HeuristicWeights(...),
    best_mean_global_cost=13.61,
    evaluations=(evaluation_a, evaluation_b),
)
~~~

- `best_weights`: der bisher beste lokale Gewichtssatz,
- `best_mean_global_cost`: dessen mittlere Kosten über die Seeds,
- `evaluations`: gespeicherte Bewertungen der besten Verbesserungen.

`state["result"]` enthält dieses Objekt; das Dictionary selbst enthält also
nicht nur eine Zahl, sondern beste Gewichte, Kosten und Bewertungen.

## 25. Kleines vollständiges Zahlenbeispiel

Angenommen, Kandidat 1 liefert:

~~~text
Seed 1 Kosten = 14.10
Seed 2 Kosten = 13.80
~~~

Dann schreibt `progress`:

~~~python
state["costs"] = [13.95]
~~~

Kandidat 2 liefert:

~~~text
Seed 1 Kosten = 13.20
Seed 2 Kosten = 13.60
~~~

Danach:

~~~python
state["costs"] = [13.95, 13.40]
~~~

Die Anzeige zeigt:

~~~text
Aktuelle Iteration: 1
Kandidat: 2 / 50
Letzte mittlere globale Kosten: 13.40
~~~

Kandidat 2 ist zu diesem Zeitpunkt besser, weil `13.40 < 13.95`. Nach
weiteren Runden steht im Ergebnis der beste gefundene Satz in
`state["result"].best_weights`; die gespeicherten Bewertungen stehen in
`state["result"].evaluations`.

## 26. Kurzantwort: Wo beginnt die eigentliche Optimierung?

~~~text
Play-Button
  -> _start_optimization(state, optimizer)
  -> worker() im Daemon-Thread
  -> _run_benchmark(..., HeuristicWeights(), True)
  -> optimizer.optimize_iteratively(...)
     -> Kandidaten erzeugen
     -> je Kandidat Seed 1 und Seed 2 simulieren
     -> globale Kosten berechnen
     -> progress(...) aufrufen
  -> best_weights erneut mit beiden Seeds simulieren
  -> state["result"] und state["benchmark"] füllen
  -> running=False
  -> Streamlit zeigt Ergebnis
~~~
