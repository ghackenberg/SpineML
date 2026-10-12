# SpineMLSimulationRunner

Python-Datei:
`sources/SpineML/Control/HeuristicControl/SpineMLSimulationRunner.py`

## Aufgabe

`SpineMLSimulationRunner` ist eine normale Python-Klasse. Sie ist keine
Salabim-Klasse und erbt von keiner Salabim-Klasse. Stattdessen verwendet sie
Salabim innerhalb ihrer Methoden, um einen vollständigen SpineML-
Simulationslauf zu organisieren.

Die Klasse ermöglicht insbesondere headless Simulationsläufe. Das bedeutet:

```text
keine 2D-/3D-Visualisierung
kein Simulationsfenster
nur Berechnung des Simulationsablaufs und der Kennzahlen



SpineMLSimulationRunner
    ├── erstellt eine Salabim-Environment
    ├── erstellt SimLayout und SimScenario
    ├── verbindet Policy und SimulationBridge
    ├── startet env.run(...)
    └── sammelt globale Kennzahlen





Ein einzelner Runner-Aufruf bedeutet daher:
ein konkreter lokaler Gewichtssatz+ ein konkreter Seed + eine Fabrikkonfiguration
        ↓
ein vollständiger Simulationslauf
        ↓
GlobalSimulationMetrics für genau diesen Lauf
```

Dadurch können viele vollständige Läufe für verschiedene lokale Gewichte und
Seeds nacheinander ausgeführt werden. Der Runner erhält einen konkreten Satz
lokaler `HeuristicWeights` und einen `seed`, verwendet diese während des
gesamten Laufs und liefert danach globale Kennzahlen zurück.

Der Runner bewertet keine Gewichtssätze selbst und verändert sie auch nicht.
Der `LocalHeuristicWeightOptimizer` ruft ihn wiederholt mit unterschiedlichen
Gewichtssätzen auf.

## `__init__(layout, scenario, till=sim.inf)`

Der Konstruktor erstellt einen Runner und speichert die Fabrikkonfiguration
für spätere Simulationsläufe.

### Eingabe und Ausgabe

```python
runner = SpineMLSimulationRunner(layout, scenario)
metrics = runner(weights, seed=1)
```

## `__call__(weights, seed)`

Diese Methode führt genau einen vollständigen Simulationslauf aus.

### Was bedeutet `__call__`?

`__call__` ist eine spezielle Python-Methode. Sie macht ein Objekt aufrufbar,
ähnlich wie eine Funktion. Deshalb kann der Runner direkt so verwendet werden:

```python
metrics = runner(weights, seed=1)
```

Python behandelt diesen Aufruf intern als:

```python
metrics = runner.__call__(weights, seed=1)
```

Ohne `__call__` müsste man die Methode mit ihrem Namen aufrufen. Der Runner
würde dann beispielsweise so aussehen:

```python
metrics = runner.run(weights, seed=1)
```

Im Optimierer wird die aufrufbare Variante verwendet, weil der Runner als
`simulation_runner`-Funktion übergeben werden kann.

Eingaben:


| Eingabe    | Bedeutung                                                                |
| ------------ | -------------------------------------------------------------------------- |
| `layout`   | Fabriklayout mit Stores, Korridoren und Maschinen                        |
| `scenario` | Aufträge und ihre Produktionsanforderungen                              |
| `weights`  | Ein konkreter Satz lokaler Aktionsgewichte                               |
| `seed`     | Fester Startwert für reproduzierbare Zufallsereignisse                  |
| `till`     | Simulationsende; standardmäßig`sim.inf` für einen vollständigen Lauf |

Ausgabe:

```python
GlobalSimulationMetrics
```

Die Ausgabe enthält unter anderem Makespan, Verspätung, Transportzeit,
Werkzeugwechselzeit, Nacharbeitskosten, Ausschusskosten und unfertige Jobs.

### Ablauf eines Aufrufs

```text
SpineMLSimulationRunner(weights, seed)
        ↓
Salabim-Ausführungsmodus einstellen (`sim.yieldless(False)`)
        ↓
Zufallszahlengenerator mit seed initialisieren
        ↓
Salabim-Umgebung erzeugen
        ↓
LocalHeuristicActionEvaluator(weights) erzeugen
        ↓
GeneratorSelectorPolicy mit dem Evaluator erzeugen
        ↓
SimulationBridge, SimLayout und SimScenario erzeugen
        ↓
vollständigen Simulationslauf ausführen
        ↓
globale Kennzahlen sammeln
        ↓
GlobalSimulationMetrics zurückgeben
```

### 1. Simulationsmodus einstellen

Salabim kennt zwei Ausführungsarten für Simulationsprozesse:

```text
yieldless-Modus
    → Prozesse werden ohne yield-Anweisungen geschrieben

yield-Modus
    → Prozesse verwenden yield oder yield from
```

Eure Roboter- und Maschinenmethoden sind im `yield`-Modus geschrieben. Sie
verwenden beispielsweise:

```python
yield from self.move_x(target_x, speed)
```

Deshalb stellt der Runner vor dem Aufbau der Simulation ausdrücklich den
passenden Modus ein:

```python
sim.yieldless(False)
```

Das bedeutet wörtlich:

```text
yieldless(False)
    → yieldless-Modus wird deaktiviert
    → yield-Modus wird aktiviert
```

Dadurch kann Salabim erkennen, wann eine Bewegung oder Operation pausiert und
zu welchem Simulationszeitpunkt sie fortgesetzt werden soll. Andere Maschinen
und Roboter können während dieser Pause weiterlaufen.

Ohne diese Einstellung könnte Salabim im `yieldless`-Modus bleiben. Dann würde
der Ausführungsmodus nicht zu den `yield`- und `yield from`-Anweisungen der
SpineML-Komponenten passen. Der Runner setzt die Einstellung deshalb bei jedem
neuen Optimierungslauf ausdrücklich erneut.

Die Zeile verändert keine Gewichte und erzeugt keine Zufallszahlen. Sie stellt
nur den erforderlichen Simulationsmodus ein.

### 2. Seed setzen

#### Grundidee und Ziele

Ein `seed` ist ein fester Startwert für einen Zufallszahlengenerator. Er legt
fest, welche pseudozufällige Zahlenfolge während eines Simulationslaufs
verwendet wird. Der Seed macht die Zufallsentscheidungen wiederholbar; er
entfernt die Wahrscheinlichkeiten nicht.

Beim Optimieren verfolgen wir zwei Ziele:


| Ziel                     | Vorgehen                                       | Was wird dadurch erreicht?                                                                         |
| -------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Fairer Gewichtsvergleich | Alle Gewichtssätze mit denselben Seeds testen | Unterschiede stammen möglichst von den Gewichten und nicht von unterschiedlichen Zufallsszenarien |
| Robustheitsprüfung      | Jeden Gewichtssatz mit mehreren Seeds testen   | Ein Gewichtssatz soll auch bei verschiedenen Zufallsszenarien zuverlässig funktionieren           |

Robust bedeutet hier also nicht „immer dasselbe Ergebnis“, sondern „unter
unterschiedlichen möglichen Zufallsverläufen nicht plötzlich deutlich
schlechter“.

Beispiel für einen vollständigen Vergleich:

```text
Gewichtssatz A → Seed 1, Seed 2, Seed 3 → Mittelwert A
Gewichtssatz B → Seed 1, Seed 2, Seed 3 → Mittelwert B
```

Seed 1 wird sowohl für A als auch für B verwendet. Dasselbe gilt für Seed 2
und Seed 3. Dadurch sind die Gewichtssätze vergleichbar und werden gleichzeitig
über mehrere Szenarien geprüft.

Der `seed` wird sowohl für Python-Zufallszahlen als auch für die Salabim-
Umgebung verwendet:

```python
random.seed(seed)
env = sim.Environment(time_unit="hours", random_seed=seed)
```

Der Seed ist keine Wahrscheinlichkeit und auch keine laufende Zufallszahl. Er
ist nur der feste Startwert, aus dem der Zufallszahlengenerator seine Folge
berechnet.

Beispielhaft kann `seed=1` folgende Zahlenfolge erzeugen:

```text
0.1343642441, 0.8474337363, 0.7637746189, ...
```

Bei einer Operation mit `defect_probability = 0.20` wird eine Zufallszahl mit
`0.20` verglichen:

```python
random_value = 0.1343642441
if random_value < 0.20:
    # In diesem Beispiel entsteht ein Defekt.
```

Da `0.1343 < 0.20` ist, würde diese konkrete Ausführung einen Defekt erzeugen.
Die nächste Zufallszahl kann anschließend beispielsweise als
Defektschweregrad verwendet werden:

```text
defekt_schwergrad = 0.8474337363
```

Das ist eine Veranschaulichung der Reihenfolge; welche Zufallszahl für welches
Ereignis verwendet wird, hängt von der tatsächlichen Reihenfolge aller
Zufallsaufrufe im Simulationslauf ab.

Mit demselben Seed beginnt die Folge immer gleich:

```text
seed=1 → 0.1343, 0.8474, 0.7638, ...
seed=1 → 0.1343, 0.8474, 0.7638, ...
```

Mit einem anderen Seed entsteht eine andere Folge:

```text
seed=2 → 0.9560, 0.9478, 0.0566, ...
```

Dadurch kann bei gleicher Fabrik und gleichen lokalen Gewichten ein anderes
Defekt- oder Ablauf-Szenario entstehen. Der `SpineMLSimulationRunner` setzt
beide Zufallsquellen auf denselben Seed, damit ein Lauf reproduzierbar bleibt.

### Warum braucht auch die Salabim-Umgebung einen Seed?

Python und Salabim verwalten ihre Zufallszahlen getrennt. Deshalb reicht
`random.seed(seed)` allein nicht aus, um mögliche Zufallsentscheidungen der
Simulationsbibliothek zu kontrollieren. Der zweite Seed wird direkt beim
Erzeugen der Salabim-Umgebung gesetzt:

```python
env = sim.Environment(random_seed=seed)
```

Damit gilt:

```text
Python-Seed
    → Zufallsereignisse im SpineML-Code,
      zum Beispiel Defektwahrscheinlichkeit und Defektschweregrad

Salabim-Seed
    → Zufallsereignisse, die innerhalb der Simulationsumgebung oder
      ihrer verwendeten Komponenten entstehen können
```

Im aktuellen SpineML-Code werden Defekte und die zufällige Auswahl gleich
hoher Aktionsscores über Python-`random` erzeugt. Der Salabim-Seed stellt
zusätzlich sicher, dass auch stochastische Funktionen der Simulationsumgebung
reproduzierbar bleiben. Werden später Salabim-Verteilungen oder andere
stochastische Komponenten eingesetzt, ist dafür bereits eine feste
Reproduzierbarkeit vorgesehen.

### Was verursacht der Seed konkret in `SimMachine`?

Im `SimMachine`-Code bestimmen die vom Runner erzeugten Zufallszahlen die
Defektentscheidung und — falls ein Defekt entsteht — den Defektschweregrad:

```python
if random.random() < operation.defect_probability:
    defekt_schwergrad = random.random()
```

Der Ablauf ist:

```text
Runner setzt seed
        ↓
SimMachine bearbeitet eine Operation
        ↓
random.random() entscheidet: Defekt oder kein Defekt
        ↓
bei Defekt: random.random() bestimmt den Defektschweregrad
```

Beispielhaft liefert `seed=1` am Anfang die Zahlen:

```text
erste Zufallszahl  = 0.1343
zweite Zufallszahl = 0.8474
```

Bei `operation.defect_probability = 0.20` gilt `0.1343 < 0.20`. Also entsteht
ein Defekt und die nächste Zahl wird als Schweregrad verwendet:

```text
defekt_schwergrad = 0.8474
```

Beim nächsten Zufallsaufruf verwendet `SimMachine` die nächste Zahl der Folge.
Der Seed erzeugt nicht immer denselben Schweregrad für jeden Job. Er legt nur
die reproduzierbare Reihenfolge der Zufallszahlen fest.

### Reproduzierbarkeit beim Gewichtsvergleich

Reproduzierbarkeit bedeutet zunächst, dass `SimMachine` bei gleicher
Konfiguration und gleichem Seed dieselben Zufallsentscheidungen wiederholt.
Zum Beispiel erhält eine Operation erneut dieselbe Zufallszahl für die
Defektprüfung und — falls ein Defekt entsteht — denselben Schweregrad:

```text
Erster Lauf mit seed=1:  Job 2 → Defekt, Schweregrad 0.8474
Zweiter Lauf mit seed=1: Job 2 → Defekt, Schweregrad 0.8474
```

Diese wiederholbaren Zufallsentscheidungen helfen anschließend beim Vergleich
verschiedener lokaler Gewichtssätze:

```text
Gewichtssatz A + seed=1 → Simulationsergebnis A
Gewichtssatz B + seed=1 → Simulationsergebnis B
```

Beide Läufe werden mit derselben Ausgangsfolge von Zufallszahlen gestartet.
Dadurch stammen Unterschiede im Ergebnis möglichst von den unterschiedlichen
Gewichten und nicht von einem völlig anderen Zufallsszenario. Mit mehreren
Seeds wird jeder Gewichtssatz in mehreren Szenarien geprüft und anschließend
der Mittelwert verglichen:

```text
Gewichtssatz A → Seeds 1, 2, 3 → Mittelwert
Gewichtssatz B → Seeds 1, 2, 3 → Mittelwert

mittlere Kosten = (Kosten Seed 1 + Kosten Seed 2 + Kosten Seed 3) / 3
```

Ein anderer Seed kann andere Defekte erzeugen. Wenn unterschiedliche Gewichte
die Reihenfolge der Zufallsaufrufe verändern, kann sich auch die Zuordnung
einzelner Zufallswerte ändern. Der gleiche Seed macht den Vergleich deshalb
fairer und reproduzierbar, aber nicht in jeder Situation mathematisch
vollkommen identisch.

### 3. Steuerung mit lokalen Gewichten verbinden

```python
evaluator = LocalHeuristicActionEvaluator(weights)
policy = GeneratorSelectorPolicy(action_evaluator=evaluator)
bridge = SimulationBridge(policy, env=env)
```

Der `ActionGenerator` erzeugt technisch mögliche Aktionen. Der lokale
Evaluator bewertet diese Aktionen mit dem übergebenen Gewichtssatz. Der
Selector wählt die Aktion mit dem höchsten lokalen Score. Die Bridge übergibt
die ausgewählte Aktion an den Simulationskern.

```text
Observation
    ↓
ActionGenerator → technisch mögliche Kandidaten
    ↓
LocalHeuristicActionEvaluator(weights) → lokaler Score je Kandidat
    ↓
Selector → Kandidat mit höchstem Score
    ↓
Simulationskern führt Aktion aus
```

### 4. Simulation aufbauen und ausführen

`SimLayout` erstellt die simulierten Maschinen, Stores und Roboter. `SimScenario`
erstellt die simulierten Aufträge und Jobs. Anschließend startet:

```python
env.run(till=self.till)
```

Bei der Optimierung wird kein 3D-Fenster geöffnet. Dadurch können viele
vollständige Läufe nacheinander effizient ausgeführt werden.

## `collect_global_metrics(sim_layout, sim_scenario, simulation_end_time)`

Diese Methode wird am Ende von `__call__` aufgerufen und berechnet die globalen
Kennzahlen aus dem beendeten Simulationslauf.

### Zeile-für-Zeile-Ablauf

Die Methode erhält drei Eingaben:

```text
sim_layout
    → alle simulierten Maschinen, Stores und Roboter
sim_scenario
    → alle simulierten Aufträge und Jobs
simulation_end_time
    → ist einfach die Zeit, zu der die Simulation beendet wurde
```

#### 1. Alle Jobs in einer Liste sammeln

```python
jobs = []
for sim_order in sim_scenario.sim_orders:
    jobs.extend(sim_order.sim_jobs)
```

`jobs = []` erstellt zunächst eine leere Liste. Die äußere Schleife geht jeden
simulierten Auftrag durch. `sim_order.sim_jobs` enthält die Jobs dieses
Auftrags. `extend(...)` fügt diese Jobs einzeln in die gemeinsame Liste ein.

Beispiel:

```text
Auftrag 1 → [Job 1, Job 2]
Auftrag 2 → [Job 3]
jobs      → [Job 1, Job 2, Job 3]
```

#### 2. Zähler und Zwischenlisten initialisieren

```python
completed_times = []
total_tardiness = 0.0
unfinished_jobs = 0
nacharbeit_job_count = 0.0
ausschuss_job_count = 0.0
```

Diese Variablen sammeln die Ergebnisse:


| Variable               | Anfangswert | Bedeutung                                                                                                       |
| ------------------------ | ------------: | ----------------------------------------------------------------------------------------------------------------- |
| `completed_times`      |        `[]` | Liste der Abschlusszeitpunkte aller fertiggestellten Jobs; sie startet leer, weil noch kein Job geprüft wurde. |
| `total_tardiness`      |       `0.0` | Summe der Verspätung aller fertiggestellten Jobs; zunächst gibt es noch keine Verspätung.                    |
| `unfinished_jobs`      |         `0` | Zähler für Jobs ohne`completed_time`; er wird bei jedem unfertigen Job um `1` erhöht.                        |
| `nacharbeit_job_count` |       `0.0` | Anzahl der Jobs mit Nacharbeitsstrategie; pro Nacharbeitsjob wird`1.0` gezählt.                                |
| `ausschuss_job_count`  |       `0.0` | Anzahl der Jobs im Zustand`ausschuss`; pro Ausschussjob wird `1.0` gezählt.                                    |

Die leere Liste und die Nullwerte sind Startwerte. Während die anschließende
Job-Schleife läuft, werden sie Schritt für Schritt ergänzt oder erhöht.

#### 3. Jeden Job auswerten

```python
for job in jobs:
```

Die folgende Schleife verarbeitet jeden Job genau einmal.

##### Fall A: Job ist nicht fertig

```python
if job.completed_time is None:
    unfinished_jobs += 1
```

`completed_time is None` bedeutet, dass der Job bis zum Simulationsende nicht
abgeschlossen wurde. Der Zähler `unfinished_jobs` wird um eins erhöht.

##### Fall B: Job ist fertig

```python
else:
    completed_times.append(float(job.completed_time))
    total_tardiness += max(
        0.0,
        float(job.completed_time)
        - float(job.order.latest_end_time),
    )
```

Bei einem fertigen Job wird zuerst seine Abschlusszeit in `completed_times`
gespeichert. Danach wird die Verspätung berechnet:

```text
Verspätung = completed_time − latest_end_time
```

`max(0.0, ...)` verhindert negative Verspätung. Wird ein Job vor seiner
Deadline fertig, zählt seine Verspätung als `0.0`.

Beispiel:

```text
completed_time = 23
latest_end_time = 20
→ Verspätung = max(0, 23 − 20) = 3
```

##### Nacharbeitskosten zählen

```python
if job.defect_recovery_strategy in {
    "nacharbeiten_auf_defektmaschine",
    "nacharbeiten_auf_alternativer_maschine",
}:
    nacharbeit_job_count += 1.0
```

Hat der Job eine dieser beiden Nacharbeitsstrategien, wird `nacharbeit_job_count`
um `1.0` erhöht. In der aktuellen Implementierung entspricht das einer
einfachen Zählung der Nacharbeitsjobs, nicht einem Eurobetrag.

##### Ausschusskosten zählen

```python
if job.general_state.get() == "ausschuss":
    ausschuss_job_count += 1.0
```

Wenn der allgemeine Jobzustand `ausschuss` ist, wird `ausschuss_job_count` um `1.0`
erhöht. Auch dies ist aktuell eine Zählung und keine detaillierte
Produktkostenberechnung.

#### 4. Makespan bestimmen

```python
if jobs:
    # Frühester Produktionsbeginn aller Aufträge.
    production_start_time = min(
        float(job.order.earliest_start_time)
        for job in jobs
    )
else:
    production_start_time = 0.0

if completed_times:
    # Letzte Abschlusszeit minus tatsächlicher Produktionsbeginn.
    makespan = max(
        0.0,
        max(completed_times) - production_start_time,
    )
else:
    # Kein Job ist fertig: bis zum Simulationsende messen.
    makespan = max(
        0.0,
        float(simulation_end_time) - production_start_time,
    )
```

Zuerst wird aus `job.order.earliest_start_time` der früheste geplante
Produktionsbeginn aller Jobs bestimmt. Der Makespan ist dann die verstrichene
Zeit vom Produktionsbeginn bis zum letzten Abschluss. `max(0.0, ...)` verhindert
einen negativen Wert, falls die Simulation vor dem frühesten Startzeitpunkt
beendet wird.

```text
frühester Start = 11
completed_times = [23, 18, 20]
→ makespan = 23 − 11 = 12

keine fertigen Jobs
simulation_end_time = 100
frühester Start = 11
→ makespan = 100 − 11 = 89
```

#### 5. Roboter für die Transportmessung sammeln

```python
robots = [sim_layout.sim_main_robot]
```

Der Main-Roboter wird immer aufgenommen.

```python
for sim_corridor in sim_layout.sim_corridors:
    if sim_corridor.sim_arm_left.machineCount() > 0:
        robots.append(sim_corridor.sim_arm_left.sim_arm_robot)
    if sim_corridor.sim_arm_right.machineCount() > 0:
        robots.append(sim_corridor.sim_arm_right.sim_arm_robot)
```

Danach werden alle Seitenarmroboter der Korridore geprüft. Ein Seitenarm wird
nur dann aufgenommen, wenn sein Korridor mindestens eine Maschine besitzt.
Leere oder nicht verwendete Seitenarme werden dadurch nicht berücksichtigt.

#### 6. Transportzeit berechnen

```python
total_transport_time = 0.0
for robot in robots:
    total_transport_time += robot.state_move.value.value_duration("moving_x")
    total_transport_time += robot.state_move.value.value_duration("moving_y")
    total_transport_time += robot.state_move.value.value_duration("moving_z")
```

Für jeden berücksichtigten Roboter werden die Bewegungszeiten in X-, Y- und
Z-Richtung aus dem Bewegungszustand gelesen und addiert:

```text
Transportzeit eines Roboters
= moving_x + moving_y + moving_z
```

Die Summe aller Roboter ergibt `total_transport_time`.

#### 7. Werkzeugwechselzeit berechnen

```python
tool_change_time = 0.0
for machine in sim_layout.simMachines():
    tool_change_time += machine.state.value.value_duration("mounting")
    tool_change_time += machine.state.value.value_duration("unmounting")
```

Für jede Maschine werden die Zeiten für Werkzeugmontage (`mounting`) und
Werkzeugdemontage (`unmounting`) gelesen. Ihre Summe ergibt
`tool_change_time`.

#### 8. Ergebnisobjekt zurückgeben

```python
return GlobalSimulationMetrics(
    makespan=makespan,
    total_tardiness=total_tardiness,
    total_transport_time=total_transport_time,
    tool_change_time=tool_change_time,
    nacharbeit_job_count=nacharbeit_job_count,
    ausschuss_job_count=ausschuss_job_count,
    unfinished_jobs=unfinished_jobs,
)
```

Am Ende werden alle berechneten Werte in einem
`GlobalSimulationMetrics`-Objekt zusammengefasst. Dieses Objekt wird an
`LocalHeuristicWeightOptimizer` zurückgegeben. Erst danach berechnet
`GlobalSimulationEvaluation` mit den festen globalen Gewichten die globalen
Kosten des Simulationslaufs.

`collect_global_metrics(...)` durchsucht alle simulierten Jobs, Roboter und
Maschinen und bildet daraus die Ergebniskennzahlen:


| Kennzahl               | Berechnung im Runner                                                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `makespan`             | Verstrichene Zeit vom frühesten`earliest_start_time` bis zum letzten Abschluss; falls kein Job abgeschlossen ist, bis zur Simulationsendzeit |
| `total_tardiness`      | Summe von`max(0, completed_time - latest_end_time)` über alle abgeschlossenen Jobs                                                           |
| `total_transport_time` | Bewegungsdauer aller Roboter in X-, Y- und Z-Richtung                                                                                         |
| `tool_change_time`     | Dauer aller Werkzeugmontage- und Demontagevorgänge                                                                                           |
| `nacharbeit_job_count` | Zählung der Jobs mit einer Nacharbeitsstrategie                                                                                              |
| `ausschuss_job_count`  | Zählung der Jobs im Zustand`ausschuss`                                                                                                       |
| `unfinished_jobs`      | Anzahl der Jobs ohne`completed_time`                                                                                                          |

Die Kennzahlen werden als ein Objekt zurückgegeben:

```python
return GlobalSimulationMetrics(
    makespan=...,
    total_tardiness=...,
    total_transport_time=...,
    tool_change_time=...,
    nacharbeit_job_count=...,
    ausschuss_job_count=...,
    unfinished_jobs=...,
)
```

`GlobalSimulationEvaluation` verwendet diese Kennzahlen anschließend mit den
festen `GlobalSimulationWeights`, um die globalen Kosten des Laufs zu berechnen.

## Verwendung im Optimierer

```text
ein lokaler Gewichtssatz
        ↓
SpineMLSimulationRunner(weights, seed)
        ↓
vollständige Simulation
        ↓
GlobalSimulationMetrics
        ↓
GlobalSimulationEvaluation
        ↓
globaler Vergleichswert
```

Der Optimierer wiederholt diesen Ablauf für jeden Gewichtssatz und jeden
angegebenen Seed. Anschließend wird der Gewichtssatz mit dem niedrigsten
mittleren globalen Vergleichswert ausgewählt.
