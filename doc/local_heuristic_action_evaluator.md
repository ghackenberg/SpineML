# LocalHeuristicActionEvaluator

Python-Datei:
`sources/SpineML/Control/HeuristicControl/LocalHeuristicActionEvaluator.py`

## Example-Start und feste Gewichte

Beim normalen Start von `example-0.py` werden die lokalen Heuristiken des
`LocalHeuristicActionEvaluator` mit dem aktuell konfigurierten,
festen `HeuristicWeights`-Objekt verwendet:

```text
Example starten
    ↓
ActionGenerator erzeugt technisch mögliche Aktionen
    ↓
Evaluator berechnet für jede Aktion lokale Teil- und Gesamtscores
    ↓
HeuristicWeights geben an, wie stark die einzelnen Kriterien zählen
    ↓
ActionSelector wählt den höchsten Score
    ↓
ausgewählte Aktion wird an die Simulation zurückgegeben
```

Der normale Example-Lauf optimiert die Gewichte noch nicht. Die enthaltenen
EDD-, SPT-, Transport-, Kapazitäts- und Werkzeugheuristiken bewerten lediglich
die aktuellen Kandidaten mit den festgelegten Gewichten. Eine automatische
Gewichtsoptimierung beginnt erst beim separaten Optimierungs-Example.

## Einordnung: Greedy-Auswahl mit lokalen Heuristiken

Der normale Ablauf ist mit einer greedy Strategie vergleichbar. Der Selector
bewertet nur die aktuell verfügbaren Aktionskandidaten und wählt sofort den
Kandidaten mit dem höchsten Gesamtscore. EDD, SPT, Transportzeit, Kapazität
und Werkzeuglebensdauer sind dabei lokale Heuristiken.

## Lokale Regeln und ihre Teilscore-Formeln

```text
EDD: urgency = calculate_edd_priority(latest_end_time, current_time)
     Early Due Date: Je dringender die Deadline, desto höher der Score.

SPT: processing_time_score = 1 / (1 + operation_duration)
     Shortest Processing Time: Je kürzer die Bearbeitungsdauer,
     desto höher der Score.

Transport:
    distance = |Δx| + |Δy| + |Δz|
    transport_time = distance / movement_speed
    transport_time_score = 1 / (1 + transport_time)

Kapazität:
    capacity_score = available_capacity / capacity

Queue:
    queue_score = 1 / (1 + queue_length)

Tool-Matching:
    1, wenn das benötigte Werkzeug bereits montiert ist, sonst 0

Tool-Leben:
    tool_life_score = min(1, remaining_life / consumed_life)
```

Jeder Teilscore liegt grundsätzlich in einem vergleichbaren Bereich und wird
mit dem zugehörigen Gewicht aus `HeuristicWeights` multipliziert. Die gewichteten
Teilscores werden anschließend zum Gesamtscore der aktuellen Aktion addiert.

| Regel | Bedeutung | Verwendung |
|---|---|---|
| EDD | Dringlichkeit bis zur Deadline | Release, Pick, Defektaktionen |
| Queue-Priorität | Priorität des Jobs | Pick-Aktionen |
| SPT | Kürzere Bearbeitungszeit wird bevorzugt | Maschinen-Pick und Place |
| Transportzeit | Kürzere Roboterfahrt wird bevorzugt | Roboter-Pick und Place |
| Quell-/Ziel-Store-Zeit | Kürzere Ein- oder Auslagerung wird bevorzugt | Pick bzw. Place |
| Zielkapazität | Mehr freier Platz wird bevorzugt | Place |
| Maschinen-Queue | Kürzere Maschinenwarteschlange wird bevorzugt | Place |
| Werkzeug-Matching | Bereits montiertes passendes Werkzeug wird bevorzugt | Maschinen-Pick |
| Werkzeuglebensdauer | Ausreichende Restlebensdauer wird bevorzugt | Maschinen-Pick |
| Nacharbeitskosten | Günstigere Nacharbeit wird bevorzugt | Defektaktionen |
| Reparaturwahrscheinlichkeit | Erfolgreiche Nacharbeit wird bevorzugt | Defektaktionen |
| Deadline-Druck | Bei dringenden Jobs verändern sich Ausschuss-, Warte- und Nacharbeitsscores | Defektaktionen |

Der Gesamtscore einer Aktion wird aus den jeweils relevanten gewichteten
Teilscores gebildet:

```text
Gesamtscore = Σ (Teilscore × zugehöriges HeuristicWeight)
```

Welche Teilregel verwendet wird, hängt vom Aktionstyp ab. Die Heuristiken
bewerten nur die aktuelle Entscheidung und nicht direkt die gesamte zukünftige
Simulation.

## Aufgabe

Der `SpineActionGenerator` erzeugt alle technisch möglichen Aktionskandidaten.
Der `LocalHeuristicActionEvaluator` bewertet anschließend jeden dieser
Kandidaten einzeln. Der `BaselineActionSelector` wählt eine Aktion mit dem
höchsten Score aus.

```text
PolicyObservation mit aktuellem Snapshot
                    ↓
SpineActionGenerator
└── technisch mögliche Aktionskandidaten
                    ↓
BaselineActionSelector durchläuft jeden Kandidaten
├── prepare_action_candidate(...)
└── evaluate_action(...)
                    ↓
Aktion mit dem höchsten Score



- ActionGenerator: erzeugt nur Aktionen, die technisch möglich sind.
  Beispiel: Ist Nacharbeit auf einer Maschine technisch nicht möglich, wird diese Aktion gar nicht erzeugt.
- LocalHeuristicActionEvaluator: bewertet die erzeugten Aktionen hinsichtlich Ziel und Nutzen:
  - Deadline-/EDD-Dringlichkeit
  - Wirtschaftlichkeit und Nacharbeitskosten
  - Transportzeit
  - Kapazität
  - Bearbeitungszeit
  - Werkzeugverbrauch
  - erwartete Reparaturqualität
Der Evaluator entscheidet also nicht, was technisch möglich ist. Er gibt jeder bereits möglichen Aktion nur einen Score.
Der Selector wählt anschließend den Kandidaten mit dem höchsten Score.
```

Der Evaluator erzeugt keine technischen Möglichkeiten und führt keine Aktion
aus. Er gibt für genau einen Kandidaten genau einen `float`-Score zurück.

## Woher kommen die Bewertungsdaten?

Der Evaluator liest alle Simulationsinformationen direkt aus:

```python
observation.simulation_configuration_snapshot
```

Es gibt kein zusätzliches `evaluation_context`-Dictionary. Der Snapshot enthält
unter anderem:

```text
simulation_configuration_snapshot
├── time
├── model
│   └── operations_by_id
└── states_by_id
    ├── Jobs
    ├── Stores und Job-Zusammenfassungen
    ├── Maschinenzustände
    ├── Roboterpositionen
    └── store_positions_by_id
```

Die Suchmethoden lesen verschachtelte Daten direkt aus diesem Snapshot:

```text
current_state(...)         → Zustand des aktuell entscheidenden Objekts
find_store_state(...)      → Store anhand seiner Store-ID
find_machine_state(...)    → Maschine anhand Objekt-ID oder Maschinenname
find_store_position(...)   → Koordinaten eines Stores
selected_job_state(...)    → genau der in einer Pick-Aktion ausgewählte Job
```

## Vollständige Methodenübersicht in der Reihenfolge der Python-Datei

Dieser Baum enthält jede Methode aus
`LocalHeuristicActionEvaluator.py`. Die Einrückung zeigt, welche Methode
eine andere Methode aufruft.

```text
LocalHeuristicActionEvaluator
├── __init__(weights)
├── current_state(observation)
├── prepare_action_candidate(action, observation)
│   ├── calculate_pick_edd_priority(action, observation)
│   │   ├── selected_job_state(action, observation)
│   │   │   └── find_store_state(value, store_id)
│   │   └── calculate_edd_priority(latest_end_time, current_time)
│   ├── calculate_robot_movement_speed(action, observation)
│   │   └── read_queue_priority(action, observation)
│   └── calculate_processing_speed_factor(observation)
├── find_machine_state(value, machine_id)
├── find_store_position(value, store_id)
└── evaluate_action(action, observation)
    ├── evaluate_release_action(observation)
    │   ├── calculate_edd_priority(...)
    │   └── find_store_state(...)
    ├── evaluate_defect_action(action_type, current_state, observation)
    │   ├── estimate_remaining_time(current_state) → deadline_missed
    │   ├── calculate_edd_priority(...) → urgency
    │   ├── job_ausschuss → Ausschuss-Score zurückgeben
    │   ├── wait_job → Warte-Score zurückgeben
    │   ├── is_nacharbeit_allowed(current_state, observation)
    │   │   ├── estimate_remaining_time(current_state)
    │   │   └── estimate_nacharbeit_cost(current_state, observation)
    │   │       ├── configuration_maxima(observation)
    │   │       ├── estimate_nacharbeit_time(current_state, observation)
    │   │       └── estimate_nacharbeit_failure_probability(current_state)
    │   ├── produkt_herabstufen → Herabstufungs-Score zurückgeben
    │   └── Nacharbeit → Maschinen-Score zurückgeben
    ├── evaluate_pick_action(action, observation)
    │   ├── evaluate_robot_pick_action(action, observation)
    │   │   ├── evaluate_queue_priority(action, observation)
    │   │   │   └── read_queue_priority(action, observation)
    │   │   ├── evaluate_pick_source_storage_time(action)
    │   │   └── evaluate_transport_time(action, observation, weight)
    │   │       └── find_store_position(value, store_id)
    │   └── evaluate_machine_pick_action(action, observation)
    │       ├── evaluate_queue_priority(action, observation)
    │       ├── SPT der ausgewählten Operation
    │       ├── Werkzeug-Matching
    │       └── verfügbare Werkzeuglebensdauer
    ├── evaluate_place_action(action, observation)
    │   ├── evaluate_target_store_capacity(action, observation)
    │   │   └── find_store_state(value, store_id)
    │   ├── evaluate_place_target_storage_time(action)
    │   ├── evaluate_transport_time(action, observation, weight)
    │   ├── evaluate_place_machine_queue(action, observation)
    │   │   └── find_machine_state(value, machine_id)
    │   └── evaluate_place_processing_time(action, observation)
    └── evaluate_process_action(action, observation)
        └── gibt neutralen Score zurück
```

### `__init__(weights)`

Speichert das übergebene `HeuristicWeights`-Objekt in `self.weights`.

### `current_state(observation)`

Liest anhand von `current_object_id` den Zustand des aktuell entscheidenden
Objekts direkt aus `snapshot["simulation_object_states_by_id"]`.

### `calculate_pick_edd_priority(action, observation)`

Sucht den ausgewählten Pick-Job und übergibt dessen `latest_end_time` zusammen
mit der aktuellen Snapshot-Zeit an `calculate_edd_priority(...)`.

### `calculate_edd_priority(latest_end_time, current_time)`

Berechnet aus Deadline und aktueller Zeit einen Wert zwischen nahe `0` und nahe
`1`. Vor der Deadline steigt der Wert bis `0.5`; nach der Deadline steigt er
weiter in Richtung `1`. Die genaue Formel steht im Abschnitt `release_job`.

0.0 bis 0.5  → Deadline noch nicht überschritten
0.5          → Deadline genau erreicht
0.5 bis 1.0  → Deadline bereits überschritten

### `find_store_state(value, store_id)`

Durchsucht den Snapshot rekursiv nach Store-Dictionaries und gibt genau den
Store mit der verlangten `store_id` zurück.

### `find_machine_state(value, machine_id)`

Durchsucht den Snapshot rekursiv nach Maschinenzuständen. Eine Maschine kann
über ihre `object_id` oder ihren `machine_name` gefunden werden.

### `find_store_position(value, store_id)`

Durchsucht `value` rekursiv nach allen Dictionaries mit dem Schlüssel
`store_positions_by_id`. Dabei werden sowohl verschachtelte Dictionaries als
auch Listen durchlaufen. Jede gefundene Position wird in einem gemeinsamen
Index unter ihrer Store-ID gesammelt.

Konkrete Eingabe:

```python
value = {
    "simulation_object_states_by_id": {
        "Main robot": {
            "store_positions_by_id": {
                "start_storage": {"x": 0.0, "y": 2.0, "z": 1.0},
            }
        }
    }
}
store_id = "start_storage"
```

Die Methode sucht dann nach dem Eintrag mit genau dieser ID und gibt nur
dessen Positions-Dictionary zurück:

```python
{"x": 0.0, "y": 2.0, "z": 1.0}
```

Diese Koordinaten werden anschließend von `evaluate_transport_time(...)`
verwendet, um die Entfernung zwischen Roboter und Ziel-Store zu berechnen.
Die Methode liefert also eine einzelne Store-Position, nicht alle Positionen.
Ist die `store_id` im Snapshot nicht vorhanden, führt der abschließende
Dictionary-Zugriff zu einem `KeyError`; dadurch wird eine fehlende
Konfigurations- oder Beobachtungsinformation sichtbar.

Bei einem Corridor-Arm-Roboter liegen `store_in` und `store_out_arm` am
seitlichen Zugriffspunkt `x = robot.dx` (`+1` links, `-1` rechts). Der zentrale
`store_out_main` erhält dagegen `x = 0.0`. Dadurch berücksichtigt die
Transportbewertung, dass der Main-Store vom seitlichen Arm aus eine zusätzliche
Querbewegung benötigt.

### Rekursion und `isinstance` im Detail

Die Methode ruft `collect_store_positions(...)` für alle verschachtelten
Kinder erneut auf. Dieses Selbstaufrufen nennt man Rekursion. Mit
`isinstance(nested_value, dict)` und `isinstance(nested_value, list)` wird vor
jedem Schritt geprüft, welche Containerstruktur gerade vorliegt.

Die beiden Verzweigungen der rekursiven Suche bedeuten:

```python
def collect_store_positions(nested_value):
    if isinstance(nested_value, dict):
        # Ein Dictionary kann selbst Store-Positionen enthalten.
        positions = nested_value.get("store_positions_by_id")
        if positions is not None:
            # Alle darin enthaltenen IDs und Koordinaten übernehmen.
            for position_store_id, position in positions.items():
                store_positions_by_id[str(position_store_id)] = position

        # Danach jedes einzelne Dictionary-Feld weiter durchsuchen.
        for child_value in nested_value.values():
            # Rekursiver Selbstaufruf für jeden Dictionary-Wert.
            collect_store_positions(child_value)

    elif isinstance(nested_value, list):
        # Eine Liste enthält mehrere weitere Snapshot-Objekte.
        for child_value in nested_value:
            # Rekursiver Selbstaufruf für jedes Listenelement.
            collect_store_positions(child_value)
```

`nested_value` ist dabei jeweils der aktuell untersuchte Teil des Snapshots:
zuerst der gesamte Snapshot, danach zum Beispiel `states_by_id`, ein einzelner
Roboterzustand oder ein Element einer Liste. Der `if`-Fall verarbeitet
Dictionary-Strukturen, der `elif`-Fall Listen. Andere Datentypen (zum Beispiel
Zahlen oder Texte) enthalten keine verschachtelten Store-Positionen und werden
einfach übersprungen.

Konkretes Listen- und Rekursionsbeispiel:

```python
value = [
    {"store_positions_by_id": {
        "store_left": {"x": -1.0, "y": 5.0, "z": 1.25}
    }},
    {"robot": {
        "store_positions_by_id": {
            "store_main": {"x": 0.0, "y": 5.0, "z": 1.25}
        }
    }},
]
```

Der Ablauf ist dann:

```text
collect_store_positions(value)       → value ist eine Liste
├── Element 1                         → Dictionary
│   ├── store_positions_by_id finden
│   ├── store_left speichern
│   └── Werte weiter durchsuchen
└── Element 2                         → Dictionary
    ├── Feld "robot" weiter durchsuchen
    │   └── store_positions_by_id finden
    ├── store_main speichern
    └── Werte weiter durchsuchen
```

Nach diesen rekursiven Aufrufen enthält `store_positions_by_id` beide
Positionen. Die Rekursion endet automatisch, sobald ein Wert weder Dictionary
noch Liste ist.

### `selected_job_state(action, observation)`

Liest `target_store_id` und `selected_job_id` aus der Pick-Aktion, sucht zuerst
den Quell-Store und gibt anschließend genau die passende Job-Zusammenfassung
aus dessen `job_summaries` zurück.

### `read_queue_priority(action, observation)`

Bei Pick liest die Methode die gerade vorbereitete `queue_priority` aus dem
Aktions-Payload. Bei anderen Aktionen liest sie die Priorität des bereits
geladenen Jobs aus dem aktuellen Objektzustand.

### `calculate_robot_movement_speed(action, observation)`

Berechnet `0.5 + 1.5 × queue_priority` und liefert die Geschwindigkeit für eine
Main- oder Corridor-Arm-Roboterbewegung.

### `calculate_processing_speed_factor(observation)`

Berechnet mit derselben linearen Formel den Bearbeitungsfaktor für den aktuell
in der Maschine geladenen Job.

### `evaluate_release_action(observation)`

Bewertet eine `release_job`-Aktion ausschließlich mit der gewichteten
EDD-Priorität des Jobs. Die Start-Store-Kapazität ist kein Bestandteil dieses
Scores.

### `configuration_maxima(observation)`

Liest die Maximalwerte aus
`snapshot["configuration_model"]["configuration_maxima"]`. Diese Werte wurden aus allen
Operationen und Produkttypen der aktuellen Fabrikkonfiguration berechnet.

Die Methode bekommt keine festen Maximalwerte aus `OperationType` oder
`ProductType`. Sie liest dieses bereits vom `ConfigurationObjectObserver`
erzeugte Dictionary:

```python
{
    "operation_duration": 25.0,
    "operation_tool_consumption": 12.0,
    "product_weight": 80.0,
    "product_volume": 6000.0,
}
```

Die Werte darin sind noch nicht normalisiert:

```text
operation_duration
└── längste Operation der aktuellen Konfiguration

operation_tool_consumption
└── größter Werkzeugverbrauch einer Operation

product_weight
└── größtes konfiguriertes Produktgewicht

product_volume
└── größtes konfiguriertes Produktvolumen
```

Erst die aufrufende Bewertungsmethode führt die Normalisierung aus:

```text
normalisierter Wert
= aktueller Wert / passender Wert aus configuration_maxima
```

Beispiel:

```text
aktuelle Operationsdauer = 10
configuration_maxima["operation_duration"] = 25

normalisierte Operationsdauer = 10 / 25 = 0.4
```

Die früheren festen `FOR_POLICY`-Grenzen und die dazugehörigen
Konfigurationsfehlermeldungen existieren nicht mehr. Dadurch richtet sich die
Skalierung nach der tatsächlich geladenen Fabrikkonfiguration.

### `estimate_nacharbeit_time(current_state, observation)`

Schätzt den normierten Nacharbeitsaufwand aus Operationsdauer, Produktgewicht
und Produktvolumen.

### `estimate_nacharbeit_failure_probability(current_state)`

Verwendet den `defekt_schwergrad` direkt als geschätzte Wahrscheinlichkeit,
dass die Nacharbeit fehlschlägt.

### `estimate_nacharbeit_cost(current_state, observation)`

Mittelt Nacharbeitszeit, normierten Werkzeugverbrauch und Fehlschlagsrisiko.

### `estimate_remaining_time(current_state)`

Berechnet `latest_end_time - time`.

### `is_nacharbeit_allowed(current_state, observation)`

Erlaubt Nacharbeit nur bei verbleibender Zeit und Nacharbeitskosten von
höchstens `MAX_NACHARBEIT_COST`.

### `evaluate_defect_action(action_type, current_state, observation)`

Bewertet den einzelnen Defektkandidaten als Nacharbeit, Herabstufen, Ausschuss
oder Warten.

### `evaluate_pick_action(action, observation)`

Addiert Queue-Priorität, Entnahmezeit und bei einer Roboterfahrt die kurze
Transportzeit. SPT wird nicht beim Pick angewendet, weil die nächste Operation
bei einer vorherigen Place-Entscheidung festgelegt wird.

`pick_main_robot` und `pick_corridor_arm_robot` verwenden
`evaluate_robot_pick_action`. `pick_machine_job` verwendet dagegen
`evaluate_machine_pick_action`. Dabei werden Queue-/EDD-Priorität, SPT,
Werkzeug-Matching und verfügbare Werkzeuglebensdauer verglichen: Die Maschine
nimmt den Job direkt aus ihrem Input-Store auf und fährt nicht.
Andere Pick-Aktionstypen sind nicht Teil der Produktionsschnittstelle und
führen zu einem Fehler, statt über einen Fallback bewertet zu werden.

### `evaluate_pick_source_storage_time(action)`

Bewertet eine vorhandene `storage_out_time` mit `1 / (1 + storage_out_time)`.

### `evaluate_place_action(action, observation)`

Addiert Zielkapazität, Einlagerungszeit, Transportzeit, Maschinenqueue und
gegebenenfalls die Dauer der nächsten Operation.

### `evaluate_transport_time(action, observation, weight)`

Berechnet aus Roboter- und Store-Koordinaten die Distanz, daraus mit der
Geschwindigkeit die Transportzeit und schließlich deren gewichteten Kehrwert.

### `evaluate_place_target_storage_time(action)`

Bewertet eine vorhandene `storage_in_time` mit `1 / (1 + storage_in_time)`.

### `evaluate_place_machine_queue(action, observation)`

Bewertet die Länge des Input-Stores einer ausgewählten Zielmaschine mit
`1 / (1 + queue_length)`.

### `evaluate_place_processing_time(action, observation)`

Bewertet die ausgewählte nächste Operation des Place-Kandidaten nach ihrer
Dauer.

### `evaluate_process_action(action, observation)`

Gibt für die bereits technisch zugelassene `process_machine_job`-Aktion nur
einen neutralen Score zurück. Die Auswahlheuristiken (EDD, SPT,
Werkzeug-Matching und Werkzeuglebensdauer) werden beim `pick_machine_job`
angewendet; der Generator entscheidet vorher anhand der Output-Kapazität
zwischen Process und Wait.

### `evaluate_queue_priority(action, observation)`

Multipliziert die gelesene Queue-Priorität mit `weights.queue_priority`.

### `evaluate_target_store_capacity(action, observation)`

Berechnet `available_capacity / capacity` für den Ziel-Store und gewichtet
diesen freien Kapazitätsanteil.

## Zwei Schritte pro Kandidat

### 1. `prepare_action_candidate(action, observation)`

Die Methode erstellt Kopien von Aktion und Payload. Die ursprüngliche Aktion
wird nicht verändert. Anschließend ergänzt sie Werte, die sowohl für die
Bewertung als auch für die spätere Simulation benötigt werden.

```text
Pick-Aktion
└── queue_priority nach EDD berechnen

Main- oder Corridor-Arm-Roboterbewegung
└── movement_speed aus queue_priority berechnen

Maschinenbearbeitung
└── processing_speed_factor aus queue_priority berechnen
```

### 2. `evaluate_action(action, observation)`

Diese Methode verteilt den vorbereiteten Kandidaten entsprechend seinem
`action_type` an die richtige Bewertung:

```text
evaluate_action(...)
├── complete_job                 → direkter Complete-Score
├── release_job                  → evaluate_release_action(...)
├── Aktion eines defekten Jobs   → evaluate_defect_action(...)
├── wait_*                       → direkter Wait-Score
├── pick_*                       → evaluate_pick_action(...)
├── place_*                      → evaluate_place_action(...)
├── process_machine_job          → evaluate_process_action(...)
└── unbekannter Aktionstyp       → 0.0
```

## Grundprinzip der gewichteten Bewertung

Bei Pick, Place und Process werden mehrere Teilbewertungen addiert:

```text
Teilscore = Bewertungswert × Gewicht

Gesamtscore = Teilscore 1 + Teilscore 2 + ... + Teilscore n
```

Ein höheres Gewicht macht ein Kriterium wichtiger. Die Gewichte befinden sich
in `HeuristicWeights.py` und können später durch den Optimierer verändert
werden.

---

## `complete_job`

Der Job ist fertig und kann abgeschlossen werden. Es gibt keine weitere
Berechnung:

```python
score = self.weights.complete_job
```

Standardwert: `1.0`. Da der Generator `complete_job` nur für einen fertigen Job
erzeugt, dient dieser Wert nicht dazu, andere fachliche Kriterien zu überdecken.

---

## `release_job`

Ein noch nicht freigegebener Job soll in das Produktionssystem gelangen.

```text
Release-Gesamtscore
├── EDD-Priorität des Jobs
└── Anteil der freien Kapazität im Start-Store
```

### EDD-Priorität

```text
time_until_deadline = latest_end_time - current_time
```

Deadline noch nicht erreicht:

```text
EDD-Priorität = 0.5 / (1 + time_until_deadline)
```

Deadline überschritten:

```text
overdue_time = current_time - latest_end_time
EDD-Priorität = 0.5 + 0.5 × overdue_time / (1 + overdue_time)
```

Damit gilt:

```text
Deadline weit entfernt       → Priorität nahe 0
Deadline genau jetzt         → Priorität 0.5
Deadline zunehmend verpasst  → Priorität nähert sich 1
```

### Gesamtscore

```text
Release-Score
= EDD-Priorität × release_edd
```

Mit den Standardgewichten gilt:

```text
release_edd = 0.7
```

---

## Defektaktionen

Wenn das aktuelle Objekt ein defekter OrderJob ist, werden die vom Generator
erzeugten Defektaktionen mit `evaluate_defect_action(...)` bewertet.

### `configuration_maxima(observation)`

Liest die vier konfigurationsabhängigen Maximalwerte aus dem Modell:

```text
operation_duration
operation_tool_consumption
product_weight
product_volume
```

Diese Werte werden vom `ConfigurationObjectObserver` aus allen aktuell
konfigurierten Operationen und Produkttypen berechnet.

### `estimate_nacharbeit_time(current_state, observation)`

Schätzt den normierten Zeit- und Produktaufwand der Nacharbeit:

```text
normalized_operation_duration
= operation_duration / configuration_max_operation_duration

normalized_weight
= product_weight / configuration_max_product_weight

normalized_volume
= product_volume / configuration_max_product_volume

estimated_nacharbeit_time
= (normalized_operation_duration
   + normalized_weight
   + normalized_volume) / 3
```

### `estimate_nacharbeit_failure_probability(current_state)`

Der Defektschweregrad wird direkt als geschätzte Fehlschlagswahrscheinlichkeit
verwendet:

```text
failure_probability = defekt_schwergrad
```

### `estimate_nacharbeit_cost(current_state, observation)`

Berechnet aus Nacharbeitszeit, Werkzeugverbrauch und
Fehlschlagswahrscheinlichkeit den mittleren Nacharbeitskostenwert:

```text
normalized_tool_consumption
= defect_operation_consumed_life_units
  / configuration_max_operation_tool_consumption

nacharbeit_cost
= (estimated_nacharbeit_time
   + normalized_tool_consumption
   + failure_probability) / 3
```

### `estimate_remaining_time(current_state)`

```text
remaining_time = latest_end_time - current_time
```

### `is_nacharbeit_allowed(current_state, observation)`

Nacharbeit ist nur zulässig, wenn:

```text
remaining_time > 0
und
nacharbeit_cost <= MAX_NACHARBEIT_COST
```

Aktuell gilt `MAX_NACHARBEIT_COST = 0.6`.

### `evaluate_defect_action(action_type, current_state, observation)`

Bewertet anschließend den konkreten Defektkandidaten. Die möglichen
Kandidaten werden vom Generator erzeugt; der Evaluator weist ihnen nur den
konfigurierbaren Score zu. Zusätzlich wird die EDD-Dringlichkeit des defekten
Jobs berücksichtigt:

```text
urgency = calculate_edd_priority(latest_end_time, current_time)
```

Damit werden Defektaktionen nicht bis zur Deadline mit einem konstanten
Warte-Score bewertet.

### Tatsächliche `if`-Reihenfolge im Code

```text
evaluate_defect_action(...)
├── 1. action_type == "job_ausschuss"?
│   └── Ausschuss-Grundscore + Dringlichkeitsbonus zurückgeben
├── 2. action_type == "wait_job"?
│   └── Wait-Score abhängig von urgency zurückgeben
├── 3. nacharbeit_allowed berechnen
│   └── is_nacharbeit_allowed(...)
├── 4. action_type == "produkt_herabstufen"?
│   └── Herabstufungs-Score zurückgeben
└── 5. nacharbeit_allowed?
    ├── Nacharbeit auf Defektmaschine bewerten
    └── Nacharbeit auf alternativer Maschine bewerten
```

Die Reihenfolge ist wichtig: `job_ausschuss` und `wait_job` werden sofort
behandelt. Für Herabstufen und Nacharbeit wird erst danach geprüft, ob die
Nacharbeit zeitlich und wirtschaftlich zulässig ist.

Vor diesen `if`-Abfragen werden `remaining_time`, `deadline_missed`,
`current_time` und `urgency` berechnet. `urgency` ist die EDD-Dringlichkeit
des Jobs (0 = viel Zeit bis zur Deadline, 1 = Deadline sehr nah oder bereits
überschritten). `deadline_missed` ist wahr, sobald `remaining_time <= 0` ist.

#### Schritt 1: Ausschuss bewerten

```text
wenn action_type == "job_ausschuss":
    score = job_ausschuss
    score += urgency × deadline_pressure_ausschuss_bonus
    return score
```

`job_ausschuss` ist der konfigurierbare Grundscore für das Verschrotten.
`urgency × deadline_pressure_ausschuss_bonus` ist der zusätzliche Score für
Zeitdruck: je dringender der Job, desto attraktiver wird Ausschuss gegenüber
weiterem Warten. Beispiel: Bei `job_ausschuss = 0.0`, `urgency = 0.8` und
`deadline_pressure_ausschuss_bonus = 0.5` ergibt sich `0.4`. Die Aktion wird
hier direkt zurückgegeben; Nacharbeitsprüfungen werden für Ausschuss nicht
ausgeführt.

#### Schritt 2: Warten bewerten

```text
wenn action_type == "wait_job":
    score = wait_defect_job × (1 - urgency)
    wenn deadline_missed:
        score -= deadline_missed_wait_penalty
    return score
```

`wait_defect_job` ist der Grundscore für das Zurückstellen des defekten Jobs.
Der Faktor `(1 - urgency)` senkt diesen Score bei wachsendem EDD-Zeitdruck.
`deadline_missed_wait_penalty` ist eine zusätzliche Strafe nach Ablauf der
Deadline. Beispiel vor der Deadline: `0.2 × (1 - 0.8) = 0.04`; danach bei
einer Strafe von `0.2`: `0.04 - 0.2 = -0.16`.

Erst wenn der Kandidat weder Ausschuss noch Warten ist, berechnet der
Evaluator `nacharbeit_allowed`. Danach folgen Herabstufen und zuletzt die
beiden Nacharbeitsaktionen.

#### Schritt 3: Nacharbeitszulässigkeit berechnen

Für Herabstufen und Nacharbeit ruft der Evaluator danach
`is_nacharbeit_allowed(...)` auf. Diese Prüfung liefert nur `True` oder
`False`; sie ist selbst kein Score.

#### Schritt 4: `produkt_herabstufen` bewerten

```text
score = produkt_herabstufen
```

Zusätzlich wird die EDD-Dringlichkeit addiert:

```text
score += urgency × defect_edd
```

Beispiel:

```text
produkt_herabstufen = 0.4
urgency = 0.8
defect_edd = 0.2
Nacharbeit zulässig

Score = 0.4 + (0.8 × 0.2)
      = 0.56
```

Wenn Nacharbeit nicht zulässig ist und der Bonus `0.4` beträgt:

```text
Score = 0.4 + 0.16 + 0.4
      = 0.96
```

Wenn Nacharbeit nicht erlaubt ist:

```text
score += nacharbeit_not_allowed_downgrade_bonus
```

Der Grundscore `produkt_herabstufen` bewertet die Entscheidung, das Produkt
mit niedrigerer Qualitätsstufe weiterzuführen. `urgency × defect_edd` belohnt
die Entscheidung bei einer nahen oder überschrittenen Deadline. Der optionale
Bonus bewertet, dass Herabstufen gewählt wird, wenn Nacharbeit nicht zulässig
ist.

#### Schritt 5: Nacharbeit bewerten

Nur wenn `nacharbeit_allowed` wahr ist, werden die beiden Nacharbeitsaktionen
mit demselben Qualitäts- und Dringlichkeitsanteil bewertet:

#### `job_nacharbeiten_auf_defektmaschine`

```text
score = nacharbeit_defektmaschine
      + urgency × defect_edd
      + repair_economic_score × defect_repair_quality
```

`nacharbeit_defektmaschine` ist die Grundbewertung für die Reparatur auf der
Defektmaschine. `urgency × defect_edd` bewertet den EDD-Zeitdruck.
`repair_economic_score` bewertet ausschließlich die Wirtschaftlichkeit der
Nacharbeit und wird als `1.0 - nacharbeit_cost` berechnet. Geringe Kosten
ergeben daher einen höheren wirtschaftlichen Score. Die technische
Erfolgswahrscheinlichkeit ist davon getrennt und wird als
`repair_success_probability = 1.0 - defekt_schwergrad` beschrieben.

Damit ist jeder Teilscore eindeutig zugeordnet:


| Teilscore                                        | Bedeutung                                                  |
| -------------------------------------------------- | ------------------------------------------------------------ |
| `nacharbeit_defektmaschine`                      | Grundnutzen der Nacharbeit auf der Defektmaschine          |
| `nacharbeit_alternative_maschine`                | Grundnutzen der Nacharbeit auf einer alternativen Maschine |
| `urgency × defect_edd`                          | Bonus für einen dringenden Job nach EDD                   |
| `repair_economic_score × defect_repair_quality` | wirtschaftlicher Bonus für eine günstige Nacharbeit      |
| `repair_success_probability`                     | Wahrscheinlichkeit, dass die Reparatur technisch gelingt   |

Beispiel für `repair_economic_score`: Bei `nacharbeit_cost = 0.3` gilt
`repair_economic_score = 1.0 - 0.3 = 0.7`. Bei Kosten `0.8` wäre der
wirtschaftliche Score nur `0.2`; solche Kosten überschreiten in der Regel
bereits die Zulässigkeitsgrenze.

Beispiel: `1.0 + (0.8 × 0.2) + (0.7 × 0.1) = 1.21`.

Ist Nacharbeit nicht zulässig, wird stattdessen ausschließlich
`nacharbeit_defektmaschine_not_allowed` zurückgegeben.

#### `job_nacharbeiten_auf_alternativer_maschine`

Die Berechnung ist identisch, aber der Grundscore
`nacharbeit_alternative_maschine` bewertet die alternative Maschine. Bei den
Werten `0.8`, `urgency = 0.8`, `defect_edd = 0.2`,
`repair_economic_score = 0.7` und `defect_repair_quality = 0.1` ergibt sich
`0.8 + 0.16 + 0.07 = 1.03`.
Ist Nacharbeit nicht zulässig, wird ausschließlich
`nacharbeit_alternative_maschine_not_allowed` verwendet.

#### Zusammenfassung der tatsächlichen Rückgabepfade

```text
1. job_ausschuss       → Score berechnen und sofort zurückgeben
2. wait_job            → Score berechnen und sofort zurückgeben
3. nacharbeit_allowed  → Zulässigkeit prüfen
4. produkt_herabstufen → Score berechnen und sofort zurückgeben
5. Nacharbeit          → passenden Maschinen-Score zurückgeben
```

Damit kann Warten bei hoher Dringlichkeit nicht mehr dauerhaft den gleichen
Score behalten.

---

## Normale `wait_*`-Aktionen

Das betrifft beispielsweise `wait_job`, `wait_main_robot`,
`wait_corridor_arm_robot` und `wait_machine` außerhalb der Defektlogik.

```python
score = self.weights.wait_action
```

Der Standardwert ist `0.0`. Warten bleibt möglich, wird aber nicht gegenüber
einer sinnvoll positiv bewerteten Arbeitsaktion bevorzugt.

---

## Pick-Aktionen

Das betrifft insbesondere:

```text
pick_main_robot
pick_corridor_arm_robot
pick_machine_job
```

Beim Roboter-Pick wird keine SPT-Bewertung durchgeführt. Der Roboter wählt nur
einen Job zum Transport aus. Beim `pick_machine_job` ist SPT dagegen sinnvoll,
weil mehrere Jobs im Maschinen-Input-Store auf ihre Bearbeitung warten und
deren nächste Operationen bereits feststehen.

### Vorbereitung: Queue-Priorität nach EDD

Für jeden Pick-Kandidaten wird genau der ausgewählte Job im angegebenen
Quell-Store gesucht. Aus seiner Deadline wird die aktuelle EDD-Priorität
berechnet und in die Payload-Kopie geschrieben:

```python
prepared_action["payload"]["queue_priority"] = edd_priority
```

### Vorbereitung: Bewegungsgeschwindigkeit

Nur für Pick-Aktionen eines Main- oder Corridor-Arm-Roboters:

```text
movement_speed = 0.5 + 1.5 × queue_priority
```

```text
queue_priority = 0.0 → movement_speed = 0.5
queue_priority = 0.5 → movement_speed = 1.25
queue_priority = 1.0 → movement_speed = 2.0
```

`pick_machine_job` ist keine Roboterfahrt und erhält keine `movement_speed`.

### Kriterium 1: EDD beziehungsweise Queue-Priorität

```text
queue_priority_score
= queue_priority × queue_priority_weight
```

### Kriterium 2: kurze Entnahmezeit

Für Roboter-Picks gilt zusätzlich, wenn `storage_out_time` vorhanden ist:

```text
storage_time_score = 1 / (1 + storage_out_time)
storage_score = storage_time_score × pick_source_storage_time
```

### Maschinen-Pick: zusätzliche Dispatching-Regeln

`pick_machine_job` verwendet neben dem EDD-/Queue-Score drei weitere Kriterien:

```text
Machine-Pick-Score
= Queue-/EDD-Score
 + processing_time_score × machine_pick_processing_time
 + tool_match_score × machine_pick_tool_match
 + tool_life_score × machine_pick_tool_life
```

`processing_time_score = 1 / (1 + duration)` bevorzugt eine kurze nächste
Operation. `tool_match_score` ist `1.0`, wenn das benötigte Werkzeug bereits
montiert ist, sonst `0.0`; dadurch werden unnötige Werkzeugwechsel vermieden.
`tool_life_score` vergleicht die verfügbare Werkzeuglebensdauer mit dem
Verbrauch der Operation und liegt höchstens bei `1.0`.
Da jeder Job im Maschinen-Input-Store zuvor durch eine Place-Aktion einer
nächsten Operation zugeordnet wurde, ist `selected_operation_id` beim
Maschinen-Pick verpflichtend und wird ohne Fallback gelesen.

### Kriterium 3: kurze Transportzeit

Dieses Kriterium gilt nur für Roboter-Picks mit `movement_speed`.

```text
distance
= |target_x - robot_x|
 + |target_y - robot_y|
 + |target_z - robot_z|

estimated_transport_time = distance / movement_speed
transport_time_score = 1 / (1 + estimated_transport_time)
transport_score = transport_time_score × pick_short_transport_time
```


| Roboter            | Ziel                       | Roboterposition     | Zielposition             | Ergebnis                  |
| -------------------- | ---------------------------- | --------------------- | -------------------------- | --------------------------- |
| Main-Roboter       | Start-/End-/Corridor-Store | `robot_x` meist `0` | `target_x = 0`           | X-Anteil meist`0`         |
| Main-Roboter       | Start-/End-Store           | aktuelle`robot_y`   | feste Store-`y`-Position | `abs(target_y - robot_y)` |
| Linker Arm         | seitlicher Store           | aktuelle`robot_x`   | `x = +1`                 | `abs(1 - robot_x)`        |
| Rechter Arm        | seitlicher Store           | aktuelle`robot_x`   | `x = -1`                 | `abs(-1 - robot_x)`       |
| Linker/Rechter Arm | Main-Store                 | aktuelle`robot_x`   | `x = 0`                  | `abs(0 - robot_x)`        |
| Corridor-Arm       | Maschinen-Store            | aktuelle`robot_x`   | `x = (3 + 2n) × dx`     | Abstand zur Maschine      |

Die Roboterposition stammt aus dem aktuellen Zustand. Die Quell-Store-Position
wird über `target_store_id` aus `store_positions_by_id` im Snapshot gelesen.

### Pick-Gesamtscore

```text
Pick-Score (Roboter)
= EDD-/Queue-Prioritäts-Score
 + Entnahmezeit-Score
 + Transportzeit-Score

Pick-Score (Maschine)
= EDD-/Queue-Prioritäts-Score
 + Operationsdauer-Score
 + Werkzeug-Matching-Score
 + Werkzeuglebensdauer-Score
```

---

## Place-Aktionen

* freie Output-Kapazität
* Verarbeitungsgeschwindigkeit
* Werkzeugsetup
* Operationsdauer
* Werkzeugverbrauch

Das betrifft `place_main_robot` und `place_corridor_arm_robot`. Der bereits
geladene Job soll in einen technisch erreichbaren Ziel-Store gebracht werden.

### Vorbereitung: Bewegungsgeschwindigkeit

Die vorhandene Priorität des geladenen Jobs wird verwendet:

```text
movement_speed = 0.5 + 1.5 × current_job_queue_priority
```

### Kriterium 1: freie Zielkapazität

```text
free_capacity_ratio = available_capacity / capacity
capacity_score = free_capacity_ratio × target_store_capacity
```

### Kriterium 2: kurze Einlagerungszeit

Wenn `storage_in_time` vorhanden ist:

```text
short_storage_time = 1 / (1 + storage_in_time)
storage_score = short_storage_time × place_target_storage_time
```

### Kriterium 3: kurze Transportzeit

```text
distance = Manhattan-Distanz zwischen Roboter und Ziel-Store
transport_time = distance / movement_speed
transport_time_score = 1 / (1 + estimated_transport_time)
transport_score = transport_time_score × place_short_transport_time
```

### Kriterium 4: kurze Maschinenqueue

Wenn eine `selected_machine_id` vorhanden ist:

```text
queue_length = machine.input_storage.count
short_queue = 1 / (1 + queue_length)
queue_score = short_queue × place_machine_queue
```

Ohne ausgewählte Zielmaschine beträgt dieser Teilscore `0.0`.

### Kriterium 5: kurze nächste Operation

Wenn eine `selected_operation_id` vorhanden ist:

```text
processing_time_score = 1 / (1 + operation_duration)
operation_score
= processing_time_score × place_shortest_processing_time
```

Ohne ausgewählte Operation beträgt dieser Teilscore `0.0`.

### Place-Gesamtscore

```text
Place-Score
= freie Zielkapazität
 + kurze Einlagerungszeit
 + kurze Transportzeit
 + kurze Maschinenqueue, falls eine Zielmaschine feststeht
 + kurze Operationsdauer, falls eine Operation feststeht
```

---

## `process_machine_job`

Diese Aktion startet die Bearbeitung des aktuell in der Maschine befindlichen
Jobs. Die Aktion wird vom Generator nur erzeugt, wenn der Output-Store frei
ist; bei voller Kapazität erzeugt der Generator ausschließlich `wait_machine`.
Deshalb führt `evaluate_process_action(...)` keine lokale Auswahlheuristik
durch und gibt neutral `0.0` zurück. Die Auswahlregeln werden bereits beim
`pick_machine_job` angewendet.

---

## Unbekannte Aktionstypen

Wenn kein bekannter Fall zutrifft, liefert `evaluate_action(...)`:

```python
return 0.0
```

Der Generator soll im normalen Ablauf ausschließlich bekannte, technisch
mögliche Aktionstypen erzeugen.

## Gesamter aktueller Aufrufbaum

```text
BaselineActionSelector.select_action(...)
└── für jeden Kandidaten
    ├── LocalHeuristicActionEvaluator.prepare_action_candidate(...)
    │   ├── Pick: calculate_pick_edd_priority(...)
    │   ├── Roboter: calculate_robot_movement_speed(...)
    │   └── Process: calculate_processing_speed_factor(...)
    │
    └── LocalHeuristicActionEvaluator.evaluate_action(...)
        ├── complete_job: direkter Gewichtsscore
        ├── release_job: evaluate_release_action(...)
        ├── Defekt: evaluate_defect_action(...)
        ├── wait_*: direkter Gewichtsscore
        ├── pick_*: evaluate_pick_action(...)
        ├── place_*: evaluate_place_action(...)
        └── process_machine_job: evaluate_process_action(...)
```

Der Selector vergleicht anschließend ausschließlich die zurückgegebenen
Gesamtscores und wählt eine Aktion mit dem höchsten Score.

