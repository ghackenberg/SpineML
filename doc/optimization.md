# Allgemeiner Optimierer für alle Examples

Die Optimierungslogik liegt jetzt in `sources/optimization.py`. Sie ist
nicht mehr fest an Example 3 gebunden. Beim Start wird das ausgewählte
Example geladen; Layout und Szenario werden automatisch bestimmt.

## Ausführliche Methoden-Erklärung

Die vollständige Referenz steht in
[optimization_methods.md](optimization_methods.md). Dort sind für jede Methode
Zweck, konkrete Eingabe, Rückgabe, Zustandsänderungen und Zahlenbeispiele
angegeben. Die Aufrufkette beginnt beim Play-Button und trennt Prozess 1
(Python-Starter) von Prozess 2 (Streamlit-Webserver).

## Standard-Example im Code

Oben in `optimization.py` steht:

```python
EXAMPLE_FILE = "example-2.py"
```

Diese Variable wird beim Start über den Play-Button verwendet. Wenn du ein
anderes Example optimieren möchtest, änderst du den Dateinamen an dieser
Stelle, zum Beispiel auf `"example-1.py"`. Eine Befehlszeilen-Auswertung über
`sys.argv` gibt es nicht mehr.

## Funktion `_resolve_model_path(...)`

Diese Funktion bekommt den Dateinamen des Examples und gibt den vollständigen
Pfad zur vorhandenen `.py`-Datei zurück. Sie öffnet die Datei noch nicht.

```python
def _resolve_model_path(model_file: str | Path) -> Path:
    requested = Path(str(model_file))
    requested_names = [requested]
```

`model_file` darf ein Text wie `"example3"` oder ein `Path`-Objekt sein.
`Path(...)` macht daraus einen einheitlichen Pfad. In `requested_names` wird
zuerst genau der ursprünglich angegebene Name gespeichert.

```python
example_number = re.fullmatch(
    r"example[-_]?(\d+)(\.py)?",
    requested.name,
    flags=re.IGNORECASE,
)
```

Dieser reguläre Ausdruck prüft Namen wie `example3`, `example-3`,
`example_3`, `example3.py` und `example-3.py`.

`(\d+)` bedeutet eine oder mehrere Ziffern. Die Ziffer wird als Gruppe 1
gespeichert. `\.py` ist die optionale Dateiendung und wird als Gruppe 2
gespeichert.

```python
if example_number:
    suffix = example_number.group(2) or requested.suffix
    requested_names.append(
        requested.with_name(
            f"example-{example_number.group(1)}{suffix}"
        )
    )
```

Wenn der Name passt, wird zusätzlich die einheitliche Schreibweise erzeugt:

```text
Eingabe:    example3       -> zusätzlicher Name: example-3
Eingabe:    example3.py    -> zusätzlicher Name: example-3.py
```

Danach sucht die Funktion beide Namen zuerst im aktuellen Arbeitsordner und
dann in `sources`, `sources/examples/normal` sowie
`sources/examples/optimization`. Fehlt die Endung `.py`, wird sie ebenfalls
versucht. Beim ersten vorhandenen Treffer wird der vollständige Pfad
zurückgegeben.
Wird keine Datei gefunden, meldet die Funktion einen `FileNotFoundError` und
listet die geprüften Pfade auf.

### Konkretes Beispiel mit dem Play-Button

Angenommen, oben steht:

```python
EXAMPLE_FILE = "example3"
```

Dann entstehen zunächst diese Namen:

```python
requested_names = [
    Path("example3"),
    Path("example-3"),
]
```

Für jeden Namen werden mögliche Pfade gebildet. Wenn das aktuelle Verzeichnis
`C:\Users\...\Hackenberg` ist, gehören dazu zum Beispiel:

```text
C:\Users\...\Hackenberg\example3
C:\Users\...\Hackenberg\example3.py
C:\Users\...\Hackenberg\sources\example3
C:\Users\...\Hackenberg\sources\example3.py
C:\Users\...\Hackenberg\example-3
C:\Users\...\Hackenberg\example-3.py
C:\Users\...\Hackenberg\sources\example-3
C:\Users\...\Hackenberg\sources\example-3.py
C:\Users\...\Hackenberg\sources\examples\normal\example-3
C:\Users\...\Hackenberg\sources\examples\normal\example-3.py
C:\Users\...\Hackenberg\sources\examples\optimization\example-3
C:\Users\...\Hackenberg\sources\examples\optimization\example-3.py
```

Die Schleife

```python
for path in expanded_paths:
    if path.is_file() and path.suffix == ".py":
        return path.resolve()
```

prüft jeden Kandidaten. Sobald zum Beispiel
`...\sources\examples\normal\example-3.py` existiert, wird genau dieser
absolute Pfad zurückgegeben. Die Modelldatei wird erst später mit
`runpy.run_path(...)` geladen.

## Starten mit dem Play-Button

1. Öffne `sources/optimization.py`.
2. Ändere bei Bedarf `EXAMPLE_FILE`.
3. Klicke in VS Code auf den Play-Button.
4. `main()` liest `EXAMPLE_FILE` und startet Streamlit.

Die kurzen Optimierungsstarter liegen im Ordner
`sources/examples/optimization` und bleiben als Kompatibilität erhalten:

```powershell
.venv\Scripts\python.exe sources\examples\optimization\example-3-optimize.py
```

Dieser Starter wählt automatisch `example-3.py` und ruft intern den
allgemeinen Optimierer auf. `example-0-optimize.py` und
`example-3b-quality-optimize.py` funktionieren entsprechend.

## Voraussetzungen der Modelldatei

Eine Modelldatei erstellt die normalen SpineML-Objekte, zum Beispiel
`MachineType`, `OperationType`, `Order`, `Layout`, `Scenario`,
`Corridor` und `Machine`. Zusätzlich sollte sie einen Aufruf der Form
enthalten:

```python
simulate(layout, scenario)
```

Der Aufruf wird beim Laden nur gelesen. Damit weiß der Optimierer, welches
`Layout` und welches `Scenario` verwendet werden. Die Simulation wird
dabei nicht gestartet. Das ist wichtig, weil einige ältere Examples
`simulate(...)` direkt am Dateiende aufrufen. `optimization.py` unterdrückt
diesen Aufruf während des Ladens und startet später nur den headless Runner.

Wenn kein `simulate(...)`-Aufruf vorhanden ist, funktioniert eine Datei mit
genau einem Layout und genau einem Szenario ebenfalls. Bei mehreren Layouts
oder Szenarien muss der Aufruf eindeutig sein.

## Die zwei Prozesse

### Prozess 1: Python-Starter

Beim Klicken auf den Play-Button

passiert Folgendes:

1. Python startet `optimization.py` als Prozess 1.
2. `main()` liest `EXAMPLE_FILE` und kopiert die Umgebungsvariablen.
3. Der Modellname wird als `SPINEML_MODEL_FILE` ergänzt.
4. `subprocess.run(...)` startet Prozess 2 mit
   `python -m streamlit run sources\optimization.py`.
5. Prozess 1 wartet, solange der Streamlit-Server läuft. Wenn der Server
   beendet wird, kehrt `subprocess.run(...)` zurück und Prozess 1 endet.

### Prozess 2: Streamlit-Server

Prozess 2 führt dieselbe Datei erneut aus. Streamlit ist jetzt aktiv, daher
wird `main()` nicht nochmals gestartet:

1. `runpy.run_path(...)` lädt die Modelldatei.
2. Das Ergebnis ist ein Dictionary mit ihren globalen Variablen, zum Beispiel
   `mt1`, `pt1`, `s1`, `l1`, `c1_1` und `Machine`.
3. Aus dem ersten `simulate(layout, scenario)`-Aufruf werden Layout und
   Szenario ausgewählt.
4. Der Runner wird erstellt:

```python
runner = SpineMLSimulationRunner(
    layout,
    scenario,
    till=sim.inf,
)
```

`runner` kennt damit genau dieses Layout und Szenario. `sim.inf` bedeutet:
kein künstliches Zeitlimit; der Lauf endet, wenn die Jobs fertig sind.

Danach verbindet eine Wrapper-Funktion den Runner mit dem Optimierer:

```python
def run_simulation(weights, seed):
    return runner(weights, seed)
```

Ihre Rückgabe ist ein `GlobalSimulationMetrics`-Objekt.

## Was passiert nach dem Button-Klick?

Die Schaltfläche ruft beim Klick
`_start_optimization(state, optimizer)` auf:

1. `running` wird `True`; alte Ergebnisse werden gelöscht.
2. Ein Daemon-Hintergrundthread wird gestartet.
3. Der Thread berechnet zuerst die Baseline mit `HeuristicWeights()`.
4. Die Baseline wird mit Seed 1 und Seed 2 simuliert. Daraus entstehen zwei
   Kennzahlenobjekte, zwei Kostenwerte und dynamische Zeit-Normalisierungsskalen.
5. `optimize_iteratively(...)` erzeugt lokale Gewichtssätze (Kandidaten).
   Jeder Kandidat wird mit beiden Seeds simuliert. Seine Kosten sind der
   Mittelwert über die beiden Seeds.
6. Der beste Gewichtssatz wird nochmals mit Seed 1 und Seed 2 simuliert. Das
   ergibt den Vergleich `Baseline` gegen `Optimiert`.
7. Zum Schluss wird `running` wieder `False`; der Button ist wieder aktiv.

Eine Runde bedeutet: alle Kandidaten dieser Runde werden mit allen Seeds
geprüft:

```text
Runde 1: Kandidat 1 -> Seed 1 und Seed 2
          Kandidat 2 -> Seed 1 und Seed 2
Runde 2: Kandidat 1 -> Seed 1 und Seed 2
          ...
```

## Wichtige Optimierungsparameter

```python
optimizer.optimize_iteratively(
    initial_local_weights=HeuristicWeights(),
    seeds=[1, 2],
    iterations=2,
    initial_local_weight_step_fraction=0.40,
    exploration_candidate_count=3,
    restart_after_no_improvement=2,
    stop_after_no_improvement=4,
)
```

- `initial_local_weights`: Start-Gewichtssatz.
- `seeds`: feste Zufallsstarts für vergleichbare Läufe.
- `iterations`: Anzahl der Optimierungsrunden.
- `initial_local_weight_step_fraction`: Größe einer Gewichtsänderung.
- `exploration_candidate_count`: zusätzliche zufällige Kandidaten pro Runde.
- `restart_after_no_improvement`: erfolglose Runden bis zu einem Neustart.
- `stop_after_no_improvement`: erfolglose Runden bis zum endgültigen Abbruch.

## Ergebnisse

In `state["result"]` steht ein `WeightOptimizationResult`:

```text
best_weights          -> bester lokaler Gewichtssatz
best_mean_global_cost -> mittlere Kosten dieses Satzes über alle Seeds
evaluations           -> gespeicherte Bewertungen der Verbesserungsrunden
```

Jede `WeightEvaluation` enthält den geprüften Gewichtssatz, einen
Kostenwert pro Seed, den Seed-Mittelwert und `metrics_by_seed` mit einem
`GlobalSimulationMetrics` pro Seed.

Nach dem Lauf enthält `state["benchmark"]`:

```python
{
    "Baseline":  [eine Zeile für Seed 1, eine für Seed 2],
    "Optimiert": [eine Zeile für Seed 1, eine für Seed 2],
}
```

Die Zeilen enthalten Seed, Makespan, Tardiness, Transportzeit,
Qualitätsquoten und globale Kosten. Die Diagrammfunktionen in
`optimization.py` zeigen diese Werte im Browser an.
