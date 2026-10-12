# Implementierung gegenüber dem ursprünglichen Projektstand

Dieses Dokument vergleicht den Originalstand des Professoren-Repositorys mit
unserem aktuellen lokalen Arbeitsstand. Verglichen wird mit dem ursprünglichen
Projektstand, nicht mit einem bereits optimierten Zwischenstand.

## 0. Struktur des Originals und des aktuellen Projekts

Im Original lagen die Kernklassen in zwei Bereichen:

~~~text
SpineML/Configuration
    Definition   → Produkt-, Werkzeug-, Maschinen- und Operationstypen
    Evaluation   → Szenarien und Aufträge
    Solution     → Layouts, Korridore und konkrete Maschinen

SpineML/Simulation
    Laufzeitobjekte für Layout, Korridore, Roboter, Maschinen und Jobs
~~~

Die vier Schritte aus dem ursprünglichen README sind Unterteilungen dieser
beiden Bereiche:

~~~text
1. Basic configuration      → Configuration/Definition
2. Scenario configuration   → Configuration/Evaluation
3. Layout configuration     → Configuration/Solution
4. Performance evaluation   → Simulation durch simulate(layout, scenario)
~~~

Im Original entschieden die Simulationsklassen selbst, welcher Job
transportiert oder bearbeitet wird. Eine separate Policy-, Control- oder
Optimierungsschicht existierte dort nicht. Diese Grundlage bleibt erhalten;
die neuen Steuerungs- und Optimierungsmodule bauen darauf auf.

## 1. Neue und erweiterte Konfigurationsdaten

### Unveränderte Teile

Die Typen `ProductType`, `ToolType`, `MachineType`, `OperationType` und
`Scenario` behalten ihre ursprüngliche fachliche Bedeutung. Sie beschreiben
weiterhin Produkte, Werkzeuge, Maschinen, Operationen und Szenarien.

### Layout

Der Konstruktor besitzt jetzt zusätzlich eine Kapazität:

~~~python
Layout(name, storage_out_time, storage_in_time, storage_capacity)
~~~

`storage_capacity` wird für Start- und Endlager verwendet.
Das Startlager und das Endlager sind zwei getrennte Stores. Bei
`storage_capacity=10` kann jeder Store bis zu 10 Jobs enthalten.

### Corridor

`Corridor` hatte diese Werte bereits im ursprünglichen Projekt:

~~~text
storage_capacity
storage_out_time
storage_in_time
~~~

Der Konfigurationskonstruktor wurde dafür nicht neu erfunden. Neu ist, dass
die Simulation diese vorhandenen Werte jetzt tatsächlich an die drei
Laufzeit-Stores des Korridors weitergibt.

`storage_out_time` wird beim Entnehmen eines Jobs aus einem Store verwendet.
`storage_in_time` wird beim Ablegen eines Jobs verwendet. Der zuständige
Roboter wartet die jeweilige Zeit während der Pick- oder Place-Aktion ab.

### Machine

Eine konkrete Maschine besitzt zusätzlich:

~~~python
Machine(
    name,
    machine_type,
    corridor,
    left,
    input_storage_capacity,
    output_storage_capacity,
    tool_types=None,
    processing_speed_factor=1.0,
)
~~~

Neu ist:

- eigener Eingangspuffer,
- eigener Ausgangspuffer mit eigener Kapazität,
- Liste erlaubter Werkzeugtypen,
- Bearbeitungsgeschwindigkeitsfaktor,
- Schutzwerkzeug mit Montage- und Demontagezeit.

### Order

Aufträge enthielten auch im Original:

~~~text
name
quantity
earliest_start_time
latest_end_time
product_type
scenario
~~~

`Order.__repr__` gibt den realen Auftragsnamen zurück. Das ist für Ausgaben,
Beobachtungen und verständliche Kennzahlen wichtig.

## 2. Begrenzte Puffer und reale Fabrikressourcen

Die Simulations-Stores besitzen reale Kapazitäten:

~~~text
Layout.storage_capacity
    → Startlager und Endlager

Corridor.storage_capacity
    → Corridor-Main-, Left- und Right-Store

Machine.input_storage_capacity
    → Maschinen-Eingangspuffer

Machine.output_storage_capacity
    → Maschinen-Ausgangspuffer
~~~

Start- und Endlager teilen sich keinen gemeinsamen Zähler: Jeder Store erhält
seine eigene Kapazität aus `Layout.storage_capacity`.

Dadurch können folgende Situationen entstehen:

~~~text
Puffer voll
→ Transport kann nicht abgelegt werden
→ Roboter oder Maschine wird blockiert
→ Blocking-Time wird gemessen
~~~

Die Kapazitätsinformationen stehen außerdem in der Policy-Observation.

## 3. Neue Steuerungsarchitektur

Im Original lagen viele Entscheidungen direkt in den Simulationsklassen.
Jetzt gibt es eine getrennte Steuerungsschicht:

~~~text
Simulationskern
    → führt Zeit, Zustände, Stores und Bewegungen aus

SimulationBridge
    → vermittelt Zustände und Aktionen

Policy
    → entscheidet, welche Aktion ausgeführt werden soll

ActionGenerator
    → erzeugt technisch mögliche Aktionskandidaten

ActionEvaluator
    → berechnet einen Score für jeden Kandidaten

ActionSelector
    → wählt den Kandidaten mit dem besten Score
~~~

Die neue Steuerung liegt unter:

~~~text
sources/SpineML/Control/
~~~

Die Steuerung ist in vier Bereiche gegliedert:

~~~text
Interface/
    InterfaceTypes.py
GeneralControl/
    ActionGenerators.py
    ActionSelectors.py
    GeneratorSelectorPolicy.py
SimulationBridge/
    SimulationBridge.py
HeuristicControl/
~~~

## 4. Einheitliche Nachrichten zwischen Simulation und Policy

Für die Kommunikation wurden eigene Nachrichtentypen eingeführt.

### CurrentSimulationState

Ein Simulationsobjekt meldet seinen aktuellen Zustand:

~~~text
Job-ID
Position
Bearbeitungszustand
Qualitätszustand
gewählte Operation
gewählte Maschine
Pufferinformationen
~~~

### PolicyTrigger

Ein Trigger meldet der Bridge, dass ein Objekt eine neue Entscheidung benötigt:

~~~text
PolicyTrigger(
    event_id,
    sender_id,
    state_version,
    time,
)
~~~

### PolicyObservation

Die Policy erhält eine Beobachtung mit:

~~~text
aktuelle Simulationszeit
aktueller Zustand aller registrierten Objekte
statisches Konfigurationsmodell
wartende Objekte
Zustandsversion
~~~

### PolicyDecision und SelectedObjectAction

Die Policy liefert eine abstrakte Aktion mit IDs:

~~~python
SelectedObjectAction(
    target_id="Order A:1",
    action_type="release_job",
    payload={
        "release_time": 15,
    },
)
~~~

Die Policy verwendet keine laufenden Salabim-Objekte, sondern IDs und einfache
Daten.

### SimulationAction

Erst die Bridge wandelt die Policy-Aktion in eine ausführbare Aktion um:

~~~text
Policy-ID
→ echtes Simulationsobjekt

Store-ID
→ echter Salabim-Store

Operation-ID
→ echte OperationType-Instanz

Machine-ID
→ echte Machine-Instanz
~~~

Diese Trennung ermöglicht austauschbare Policies ohne Änderungen am
Simulationskern.

## 5. SimulationBridge

`SimulationBridge` ist eine neue Salabim-Komponente.

### Registrierung

Die Bridge registriert Jobs, Roboter, Maschinen und Korridore:

~~~text
Policy-ID → Simulationsobjekt
Simulationsobjekt → Policy-ID
Policy-Store-ID → echter Store
Simulationsobjekt → eigener Action-Store
~~~

Jedes steuerbare Objekt erhält einen persönlichen Action-Store. Dadurch wartet
ein Job nur auf seine eigene nächste Aktion.

### Zustandsablauf

~~~text
Simulationsobjekt fordert Aktion an
→ Bridge legt PolicyTrigger ab
→ Bridge sammelt Trigger derselben Simulationszeit
→ Bridge erstellt Snapshot
→ Policy erzeugt PolicyDecision
→ Bridge löst IDs in Laufzeitobjekte auf
→ konkrete SimulationAction wird zugestellt
~~~

### Gemeinsamer Snapshot

Vor jeder Policy-Entscheidung wird der aktuelle Zustand aller registrierten
Objekte gesammelt:

~~~python
{
    "time": ...,
    "state_version": ...,
    "simulation_object_states_by_id": ...,
    "configuration_model": ...,
}
~~~

So kann eine Entscheidung den Fabrikkontext berücksichtigen. Ein defekter Job
kann zum Beispiel sehen, ob seine Defektmaschine frei ist und ob ihre Puffer
Kapazität haben.

### Schutz vor veralteten Entscheidungen

Wenn zwischen Beobachtung und Zustellung ein anderer Zustand gemeldet wird,
prüft die Bridge die Zustandsversion erneut. Dadurch wird keine alte
Entscheidung blind weiterverwendet.

## 6. Beobachtungen des Fabrikzustands

`SimulationObjectObserver` erstellt ID-basierte Dictionaries.

### Beobachtung eines Jobs

Eine Job-Observation enthält unter anderem:

~~~text
object_type
job_id
order_id
number
layout_id
scenario_id
target_product_type_id
earliest_start_time
latest_end_time
released
queue_priority
bearbeitungs_state
general_state
due_state
location
selected_operation_id
selected_machine_id
defect_operation_id
defect_machine_id
defekt_schwergrad
defect_recovery_strategy
waiting_for_recovery_transport
completed_time
~~~

### Beobachtung einer Maschine

Eine Maschinen-Observation enthält unter anderem:

~~~text
machine_name
machine_type_id
corridor_id
left
state
processing_speed_factor
mounted_tool_type_id
dummy_tool_mounted
tool_type_names
remaining_life_units_by_tool
can_process_current_job
needs_tool_change
input_storage
output_storage
~~~

### Beobachtung der Roboter

Für Main-Roboter und Corridor-Arm-Roboter werden unter anderem beobachtet:

~~~text
Position x, y, z
Bewegungszustand
Ladezustand
aktuelle Job-ID
Bewegungsgeschwindigkeit
Ziel-Store
Store-Positionen
Pufferinhalte
nächste Operation
nächste Maschine
~~~

### Statische Konfiguration

`ConfigurationObjectObserver` baut zusätzlich ein ID-basiertes Modell:

~~~text
product_types_by_id
operations_by_id
machines_by_id
tools_by_id
corridors_by_id
layouts_by_id
configuration_maxima
~~~

Das Modell enthält nur Strings, Zahlen, Booleans, Dictionaries und Listen und
wird von der aktuellen Heuristik verwendet.

## 7. ActionGenerator und Produktionsrouten

`SpineActionGenerator` erzeugt mögliche Aktionen für das Objekt, das gerade auf
eine Entscheidung wartet.

### Job-Aktionen

~~~text
release_job
wait_job
complete_job
job_nacharbeiten_auf_defektmaschine
job_nacharbeiten_auf_alternativer_maschine
produkt_herabstufen
job_ausschuss
~~~

Ein fertiger Job erhält eine Abschlussaktion. Ein noch nicht freigegebener Job
erhält eine Freigabe- oder Warteaktion. Ein defekter Job erhält Recovery-
Aktionen, soweit sie technisch möglich sind.

### Roboter- und Maschinenaktionen

~~~text
pick_main_robot
place_main_robot
wait_main_robot

pick_corridor_arm_robot
place_corridor_arm_robot
wait_corridor_arm_robot

pick_machine_job
process_machine_job
wait_machine
~~~

Die Kandidaten enthalten unter anderem ausgewählten Job, Quell-Store, Ziel-
Store, Operation und Maschine.

### Routenberechnung

Die frühere separate Datei `SpineML/calculate.py` wurde entfernt. Die
Routenlogik liegt jetzt in `ActionGenerators.py`:

~~~text
Produktzustand
→ mögliche Operationenfolgen
→ mögliche Maschinenfolgen
→ konkrete Place-Aktionskandidaten
~~~

Für jeden Kandidaten werden gespeichert:

~~~text
operation_sequence
machine_sequence
next_operation_id
next_machine_id
~~~

Doppelte unmittelbare Aktionen werden entfernt, damit dieselbe Place-Aktion
nicht mehrfach bewertet wird.

### Defekt- und Nacharbeitsrouten

Bei einem reparierbaren Defekt werden mögliche Strategien erzeugt:

~~~text
Nacharbeit auf der Defektmaschine
Nacharbeit auf einer alternativen Maschine
Produktherabstufung
Warten
~~~

Die Defektmaschine wird bei der alternativen Route ausgeschlossen. Ist der
Defektschweregrad technisch nicht reparierbar, wird Ausschuss erzeugt.


## 8. ActionSelector und Policy

### BaselineActionSelector

Der Selector:

1. bereitet jeden Aktionskandidaten vor,
2. berechnet dessen Score,
3. sammelt die beste Aktion,
4. wählt bei Gleichstand reproduzierbar zufällig.

Zusätzlich gibt es eine kleine Exploration:

~~~text
SCORE_TOLERANCE = 0.05
EXPLORATION_EPSILON = 0.10
~~~

Eine fast gleich gute produktive Aktion kann gelegentlich gewählt werden. Der
Zufallsgenerator wird im Runner über den Seed festgelegt.

### GeneratorSelectorPolicy

`GeneratorSelectorPolicy` verbindet Generator, Evaluator und Selector:

~~~text
PolicyObservation
→ SpineActionGenerator.generate_actions(...)
→ LocalHeuristicActionEvaluator.prepare_action_candidate(...)
→ LocalHeuristicActionEvaluator.evaluate_action(...)
→ BaselineActionSelector.select_action(...)
→ PolicyDecision
~~~

Wenn mehrere Objekte gleichzeitig warten, werden ihre Entscheidungen zunächst
gesammelt. Ein Job darf dabei nicht gleichzeitig von zwei Pick-Aktionen gewählt
werden.

Wenn ein Objekt fünfmal hintereinander nur warten würde, wird eine vorhandene
produktive Alternative als Notfallentscheidung verwendet.

## 9. Lokale heuristische Steuerung

### HeuristicWeights

`HeuristicWeights` speichert die lokalen Aktionsgewichte. Sie beeinflussen
nicht direkt die globale Zielfunktion, sondern die Entscheidung innerhalb
eines Simulationsschritts.

Die Gewichte decken diese Bereiche ab:

~~~text
Job abschließen und warten
Queue- und EDD-Priorität
Roboter-Pick: Entnahmezeit und Transport
Maschinen-Pick: Bearbeitungsdauer, Werkzeugübereinstimmung, Werkzeugleben
Place: Zielkapazität, Einlagerung, Transport und Maschinenqueue
Job-Freigabe
Defekt: Nacharbeit, Herabstufung, Ausschuss und Warten
Defekt-EDD und erwartete Reparaturqualität
~~~

Beispiel:

~~~python
HeuristicWeights(
    queue_priority=0.9,
    release_edd=0.8,
    place_machine_queue=0.6,
)
~~~

### LocalHeuristicActionEvaluator

Der Evaluator bereitet Kandidaten vor und berechnet Scores.

Bewertete Kriterien sind unter anderem:

- EDD-Dringlichkeit anhand von `latest_end_time` und aktueller Zeit,
- freie Pufferkapazität,
- Lagerzeiten,
- geschätzte Transportzeit aus Position und Geschwindigkeit,
- kurze Bearbeitungsdauer (SPT),
- passendes Werkzeug,
- verbleibende Werkzeuglebensdauer,
- Defektschweregrad als erwartete Reparatur-Fehlschlagswahrscheinlichkeit,
- verbleibende Zeit bis zur Deadline.

Die Operation wird beim Place bereits festgelegt. Beim anschließenden
Maschinen-Pick wird sie nicht erneut zufällig ausgewählt.

## 10. Defekte, Qualität und reproduzierbarer Zufall

### Defektentscheidung

Nach der Bearbeitungszeit erzeugt die Maschine zwei pseudozufällige Werte:

~~~text
1. Defekt ja oder nein
2. Defektschweregrad
~~~

Der Schlüssel enthält:

~~~text
QUALITY_SEED
Szenario
Auftrag
Jobnummer
Operation
nacharbeit_count
~~~

Daraus wird ein SHA-256-Fingerabdruck und ein eigener `random.Random`-
Generator erzeugt.

Gleicher Schlüssel bedeutet:

~~~text
gleiche Defektentscheidung
gleicher Defektschweregrad
~~~

Baseline und optimierte Steuerung erhalten bei gleichem Seed dieselbe
Defektwelt. Unterschiedlich kann nur sein, wann und wie die Steuerung auf den
Defekt reagiert.

### Nacharbeit

Der Job speichert:

~~~text
defect_count
nacharbeit_count
ausschuss_count
defect_operation
defect_machine
defekt_schwergrad
defect_recovery_strategy
waiting_for_recovery_transport
~~~

`nacharbeit_count` unterscheidet wiederholte Ausführungen derselben Operation.
Dadurch erhält eine erneute Nacharbeit einen eigenen reproduzierbaren
Zufallswert. Die globale Qualitätskennzahl zählt einen Job mit mindestens einer
Nacharbeit nur einmal als Nacharbeitsjob; die Rohanzahl der Aktionen bleibt für
Diagnosen im Job erhalten.

### Maschinen- und Robotergeschwindigkeit

Vor dem Aufbau eines Simulationslaufs wird der Seed gesetzt. Danach werden
Geschwindigkeitsvariationen reproduzierbar gezogen:

~~~text
Maschinenfaktor: zufällig aus [0.45, 0.70, 1.00, 1.50, 2.00]
Maschinenvariation: zufällige kleine Abweichung
Roboter-Multiplikator: zufällige kleine Abweichung
Startup-Delay: zufällige kleine Verzögerung
~~~

Die Bearbeitungsdauer berücksichtigt Operation, Produktgewicht, Produktvolumen,
Maschinengeschwindigkeitsfaktor und Laufvariation.

## 11. Job-Lebenszyklus und Simulationsende

Ein Job besitzt getrennte Zustände für:

~~~text
bearbeitungs_state
general_state
due_state
released
location
selected_operation
selected_machine
completed_time
process_finished
~~~

Nach jeder Aktion bleibt der Job im Entscheidungszyklus aktiv. Er wird nicht
vorzeitig passiviert, nur weil er wartet oder einen Recovery-Schritt ausführt.

`SimCompletionWatcher` prüft regelmäßig:

~~~text
Sind alle Jobs process_finished?
→ sim.SimulationStopped auslösen
~~~

Der headless Runner fängt dieses normale Abschlusssignal ab. Dadurch gilt es
nicht als Fehler. Mit `till=sim.inf` endet ein vollständiger Lauf, sobald alle
Jobs abgeschlossen sind.

## 12. SpineMLSimulationRunner und globale Kennzahlen

### Runner

~~~python
runner = SpineMLSimulationRunner(
    layout,
    scenario,
    till=sim.inf,
)
metrics = runner(weights, seed=1)
~~~

Der Runner:

1. richtet Salabim ein,
2. setzt `random.seed(seed)`,
3. setzt `SimMachine.QUALITY_SEED`,
4. erstellt Environment, Bridge, Policy, Layout und Szenario,
5. führt den vollständigen Lauf aus,
6. sammelt `GlobalSimulationMetrics`.

### Gesammelte Kennzahlen

~~~text
makespan
total_tardiness
total_transport_time
tool_change_time
blocking_time
nacharbeit_job_count
ausschuss_job_count
unfinished_jobs
total_jobs
completed_jobs
intact_jobs
defect_jobs
~~~

### Tardiness

Tardiness wird pro Auftrag berechnet, nicht pro Job:

~~~text
spätester Abschlussjob des Auftrags
− latest_end_time
~~~

Negative Werte werden zu `0`. Bei mehreren Jobs desselben Auftrags zählt nur
die letzte Fertigstellung für diesen Auftrag.

### Makespan

~~~text
letzte Abschlusszeit aller fertigen Jobs
− frühester Startzeitpunkt der Aufträge
~~~

### Transport-, Werkzeug- und Blockierungszeit

Die Zeiten werden aus Laufzeit-Zuständen gesammelt:

~~~text
Roboter moving_x + moving_y + moving_z
Maschine mounting + unmounting
Maschine blocked
~~~

## 13. Globale Zielfunktion und Normalisierung

`GlobalSimulationEvaluation` macht aus Kennzahlen eine Kosten-Zahl.

Zeitwerte werden durch Baseline-Mittelwerte geteilt:

~~~text
makespan
total_tardiness
total_transport_time
tool_change_time
blocking_time
~~~

Qualitätswerte werden direkt als Raten verwendet:

~~~text
rework_rate
scrap_rate
defect_rate
non_intact_rate
unfinished_rate
~~~

Die Normalisierung wird aus den Baseline-Läufen mit allen Seeds kalibriert.
Ein optimierter Lauf verwendet dieselben Skalen, damit der Vergleich fair
bleibt.

Die globalen Gewichte bestimmen die Bedeutung:

~~~text
makespan                  5.0
total_tardiness           4.0
total_transport_time      1.0
tool_change_time          1.0
blocking_time             1.0
nacharbeit_job_penalty    3.0
ausschuss_job_penalty     4.0
unfinished_jobs          20.0
defect_job_penalty        3.0
non_intact_penalty        3.0
~~~

Die normalisierten Kennzahlen werden mit diesen Gewichten multipliziert und
addiert. Der Optimierer wählt die kleinste globale Kosten-Zahl.


## 14. Lokale Gewichtungsoptimierung

`LocalHeuristicWeightOptimizer` testet lokale Gewichtssätze.

### Ablauf

~~~text
HeuristicWeights als Startsatz
→ Nachbar-Gewichte erzeugen
→ zusätzliche zufällige Kandidaten erzeugen
→ jeden Kandidaten mit Seed 1 und Seed 2 simulieren
→ globale Kosten je Seed berechnen
→ Mittelwert über Seeds bilden
→ besten Kandidaten der Runde wählen
→ über mehrere Runden verbessern
~~~

Aktuelle Einstellungen:

~~~python
SEEDS = [1, 2]
ITERATIONS = 2
INITIAL_WEIGHT_STEP = 0.40
EXPLORATION_CANDIDATES = 3
~~~

Ein Kandidat ist ein kompletter lokaler Gewichtssatz. Ein Seed ist eine
reproduzierbare Zufallswelt. Ein Kandidat wird mit beiden Seeds simuliert.

### Ergebnis

~~~python
WeightOptimizationResult(
    best_weights=...,
    best_mean_global_cost=...,
    evaluations=...,
)
~~~

`best_weights` beeinflusst danach die lokalen Aktionsentscheidungen in jeder
Simulation. `best_mean_global_cost` ist der mittlere globale Kostenwert über
alle verwendeten Seeds.

## 15. Allgemeine Optimierungsoberfläche

Die allgemeine Oberfläche liegt in:

~~~text
sources/optimization.py
~~~

Oben wird das Example gewählt:

~~~python
EXAMPLE_FILE = "example-2.py"
~~~

### Ablauf

~~~text
Play-Button
→ main()
→ Prozess 2 mit Streamlit starten
→ _streamlit_app()
→ Modelldatei mit runpy laden
→ Layout und Szenario aus simulate(layout, scenario) lesen
→ create_optimizer(...)
→ Button anzeigen
→ _start_optimization(...)
→ worker im Daemon-Thread
→ Baseline
→ heuristische Optimierung
→ optimierte Nachsimulation
→ Benchmark und Diagramme
~~~

### Modelldatei laden

`runpy.run_path` führt die Modelldefinition im aktuellen Streamlit-Prozess aus
und gibt ein Dictionary aller globalen Namen zurück. Durch
`_suppress_model_visualization` werden Simulation und Visualisierung beim
Laden vorübergehend unterdrückt.

### Sitzungszustand

Streamlit speichert laufende Ergebnisse in:

~~~python
st.session_state.optimization_state
~~~

Darin stehen:

~~~text
running
iteration
candidate
total_candidates
costs
metrics
result
benchmark
normalization_scales
phase
error
~~~

### Anzeige

Die Oberfläche zeigt:

~~~text
aktueller Status
Optimierungsrunde
Kandidat / Gesamtkandidaten
Fortschrittsbalken
Kostenkurve
Kennzahlenkurven
Abweichung zu Kandidat 1
Baseline gegen Optimiert
~~~

Die Anzeige-Platzhalter (`st.empty`) sind Streamlit-Elemente und keine
zusätzlichen Attribute im Zustands-Dictionary.

## 16. Neue und geänderte Examples

### Example 0, 1, 2 und 4

Die bestehenden Examples wurden an erweiterte Konstruktoren und Stores
angepasst. Sie können mit dem allgemeinen Optimierer geladen werden, sofern
sie einen eindeutigen `simulate(layout, scenario)`-Aufruf besitzen.

### Example 3

Example 3 ist jetzt eine reale Schicht-/Fabriksituation:

~~~text
Maschinentypen:
Grundbearbeitungszentrum
Praezisionsbearbeitungszentrum
Polierzentrum

Szenario:
Schicht 3 – Gehaeusefertigung

Aufträge:
Gehaeuse Los A – Fraesen
Gehaeuse Los B – Bohren
Fertigteil Los C – Polieren
Grundkoerper Los D

Layout:
Layout 3
zwei Korridore
acht Maschinen
~~~

Die Operationen und Aufträge verwenden verständliche reale Namen statt rein
abstrakter Bezeichnungen wie `Operation 1` und `pt1`.

### Example 3B

`example-3b-quality.py` lädt die Fabrik von Example 3 und ergänzt pro wichtiger
Produktumwandlung eine Qualitätsalternative:

~~~text
schnelle Operation
→ kürzere Dauer, höhere Defektwahrscheinlichkeit

Quality-Operation
→ längere Dauer, niedrigere Defektwahrscheinlichkeit
~~~

Damit gibt es einen Zielkonflikt zwischen Produktionszeit und Qualität.
Example 3B wird mit denselben acht Jobs betrieben.

## 17. Entfernte oder bewusst nicht mehr verwendete Bestandteile

Im Vergleich zum lokalen `main` wurden folgende Bestandteile entfernt oder
ersetzt:

~~~text
SpineML.calculate
→ alte separate Routenberechnung; jetzt in ActionGenerators

Produktzustandszyklus-Validierung A → B → A
→ zusätzliche Prüfung entfernt
~~~

`optimization_dashboard.py` und `recursion_path_search_example.py` waren im
lokalen `main` nicht vorhanden und werden daher nicht als Änderungen dieses
Vergleichs gezählt.

Die normale Produktions- und Entscheidungslogik bleibt erhalten. Nur die
zusätzliche Vorabprüfung des Produktzustandsgraphen wurde entfernt.

## 18. Umgesetzter Stand

Bereits implementiert:

~~~text
erweiterte Fabrikkonfiguration
begrenzte Puffer
Policy-/Bridge-Schnittstelle
ID-basierte Observations und Actions
globale Simulations-Snapshots
Job-, Roboter- und Maschinenaktionen
Routen- und Maschinenfolgen
Defekt-, Nacharbeit-, Herabstufungs- und Ausschusslogik
reproduzierbare Zufallswelten
Werkzeugwechsel und Werkzeuglebensdauer
dynamische globale Normalisierung
heuristische Gewichtungsoptimierung
Baseline-/Optimiert-Vergleich
allgemeines Streamlit-Dashboard
~~~

## 19. Weitere funktionale Änderungen gegenüber dem lokalen `main`

Die folgenden Punkte gehören ebenfalls zum lokalen Arbeitsstand und sind keine
reinen Formatierungsänderungen:

### Simulationseinstieg und Visualisierung

~~~text
simulate(...)
→ akzeptiert Policy, SimulationBridge und Animationsgeschwindigkeit
→ schützt Salabims OpenGL-Zeichnen bei einem Fenster mit Höhe 0
→ behandelt SimulationStopped als normales Simulationsende
→ kann Maschinen am Ende in den Schutzwerkzeug-Zustand zurückführen
~~~

### Examples und Startdateien

~~~text
Example 0, 1, 2 und 4
→ an Lager- sowie Maschinenpufferkapazitäten angepasst

Example 3
→ konkrete Gehäusefertigung mit neuen Operationen, Werkzeugen,
  Aufträgen und Maschinen

Example 3B
→ zusätzliche Qualitätsalternative mit Zeit-/Qualitätskonflikt

examples/normal/
→ enthält die sechs normalen Simulationsbeispiele

examples/optimization/
→ enthält die drei kurzen Optimierungsstarter

examples/optimization/example-0-optimize.py
examples/optimization/example-3-optimize.py
examples/optimization/example-3b-quality-optimize.py
→ kompatible Starter für den allgemeinen Optimierungsstarter
~~~

### Paket und Entwicklungsumgebung

~~~text
SpineML.__init__
→ Control-Komponenten werden exportiert
→ der entfernte calculate-Export entfällt

requirements.txt
→ Streamlit und pytest ergänzt

README.md
→ neue kurze Kapitelstruktur ab Fabrikkonfiguration
~~~

Zeilenenden, zusätzliche Leerzeilen und reine Editor-Einstellungen werden in
der fachlichen Liste nicht als eigene Implementierung gezählt.
