
# LocalHeuristicWeightOptimizer

Python-Datei:
`sources/SpineML/Control/HeuristicControl/LocalHeuristicWeightOptimizer.py`

## Aufgabe

Der `LocalHeuristicWeightOptimizer` sucht einen besseren Satz lokaler
`HeuristicWeights`. Dazu verändert er die lokalen Gewichte schrittweise, führt
für jeden Kandidaten vollständige Simulationen aus und vergleicht anschließend
deren globale Kosten. Die globalen Gewichte werden nicht verändert.

Die Suche verbindet **Exploitation** (Nachbarn des bisher besten Satzes gezielt
prüfen) mit **Exploration** (zufällige Kandidaten und gelegentliche Neustarts in
anderen Bereichen des Gewichtsraums).

## Methoden-Hierarchie und Aufrufreihenfolge

```text
LocalHeuristicWeightOptimizer
├── __init__(simulation_runner, global_evaluation)
├── optimize_iteratively(initial_local_weights, seeds, iterations, initial_local_weight_step_fraction,
│                       exploration_candidate_count, restart_after_no_improvement)
│                       stop_after_no_improvement, progress_callback)
│   ├── neighboring_weights(local_weights, weight_step_fraction)
│   ├── random_local_weight_candidates(candidate_count, rng)
│   └── select_best_local_weight_set_across_seeds(local_weight_candidates, seeds)
│       └── evaluate_local_weights_across_seeds(local_weights, seeds)
└── WeightEvaluation / WeightOptimizationResult
```

## `__init__(simulation_runner, global_evaluation)`

Der Konstruktor speichert den Simulationsrunner und die globale Bewertung. Die
globalen Gewichte werden über `GlobalSimulationEvaluation` ausdrücklich
übergeben.

## `optimize_iteratively(...)`

Diese Methode startet die iterative Suche:

Wichtig: Der Aufruf beginnt in `optimize_iteratively(...)`. Erst danach werden
die Hilfsmethoden in dieser Reihenfolge aufgerufen:

```text
optimize_iteratively(...)
    ↓
neighboring_weights(...)
    ↓
random_local_weight_candidates(...)
    ↓
select_best_local_weight_set_across_seeds(...)
    ↓
evaluate_local_weights_across_seeds(...)
```

`optimize_iteratively(...)` steuert also den gesamten Ablauf; die anderen
Methoden erledigen jeweils nur ihren eigenen Teilschritt.

Mit `progress_callback` kann der aktuelle Stand während der Optimierung
angezeigt werden. Die Funktion wird nach jeder abgeschlossenen Runde aufgerufen
und erhält die Nummer der gespeicherten Verbesserung sowie deren
`WeightEvaluation`. Im Example aktualisiert sie damit den Live-Plot.

```python
result = optimizer.optimize_iteratively(
    initial_local_weights=HeuristicWeights(),
    seeds=[1, 2, 3],
    iterations=5,
    initial_local_weight_step_fraction=0.25,
    exploration_candidate_count=10,
    restart_after_no_improvement=2,
    stop_after_no_improvement=6,
    progress_callback=show_optimization_progress,
)
```

Die Parameter bedeuten:


| Parameter                            | Bedeutung                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `initial_local_weights`              | Ausgangssatz der lokalen Heuristik-Gewichte. Von diesem Satz aus werden die ersten Nachbarn erzeugt. |
| `seeds`                              | Feste Zufalls-Startwerte. Jeder Gewichtssatz wird mit jedem angegebenen Seed simuliert.              |
| `iterations`                         | Anzahl der Suchrunden. Nach jeder Runde wird der beste gefundene Satz zum neuen Ausgangspunkt.       |
| `initial_local_weight_step_fraction` | Anfangsschrittweite für jedes Gewicht; nach einer Verbesserung wird sie halbiert.                   |
| `exploration_candidate_count`        | Anzahl zufälliger Gewichtssätze je Iteration für die Suche in entfernten Bereichen.               |
| `restart_after_no_improvement`       | Anzahl erfolgloser Iterationen bis zum Neustart bei der bisher besten Lösung. |
| `stop_after_no_improvement`          | Beendet die Optimierung nach dieser Anzahl aufeinanderfolgender erfolgloser Runden; `None` deaktiviert den Abbruch. |
| `progress_callback`                  | Funktion, die nach jeder Runde den aktuellen Optimierungsstand erhält und anzeigen kann. |

1. Nachbarn um den aktuellen Gewichtssatz erzeugen.
2. Zusätzliche zufällige Gewichtssätze für die Exploration erzeugen.
3. Jeden Kandidaten mit jedem Seed simulieren.
4. Globale Kennzahlen und Kosten berechnen.
5. Den bisher global besten Kandidaten speichern.
6. Bei Verbesserung die Schrittweite halbieren; nach mehreren erfolglosen Runden neu starten.
7. Nach `stop_after_no_improvement` aufeinanderfolgenden erfolglosen Runden abbrechen.

### Diese Schritte entsprechen den Methoden

1. `neighboring_weights(...)` nimmt den aktuellen vollständigen
   `HeuristicWeights`-Satz und erzeugt pro Gewicht eine kleinere und eine
   größere Variante.
2. `random_local_weight_candidates(...)` erzeugt zusätzliche vollständige,
   zufällige Gewichtssätze zwischen `0.0` und `1.0`.
3. `select_best_local_weight_set_across_seeds(...)` bekommt beide Kandidatenlisten zusammen und prüft jeden
   Kandidaten.
4. Für jeden einzelnen Kandidaten ruft `select_best_local_weight_set_across_seeds(...)` zuerst
   `evaluate_local_weights_across_seeds(...)` auf.
5. `evaluate_local_weights_across_seeds(...)` startet mit jedem Seed einen vollständigen Runner-
   Lauf, sammelt die globalen Kennzahlen und berechnet daraus die globalen
   Kosten.
6. `select_best_local_weight_set_across_seeds(...)` bildet den Mittelwert über die Seeds und wählt den besten
   Kandidaten dieser Runde.
7. `optimize_iteratively(...)` vergleicht diesen Runden-Besten mit dem bisher
   global besten Satz, passt Schrittweite oder Neustart an und beginnt die
   nächste Runde.

### Auswahl des besten Kandidaten in der Iteration

Nach der Erzeugung aller Kandidaten führt `optimize_iteratively(...)` genau
diese Zeilen aus:

```python
# Wählt den Gewichtssatz, der in verschiedenen Situationen besser funktioniert.
iteration_result = self.select_best_local_weight_set_across_seeds(
    candidates,
    seed_values,
)

iteration_best = iteration_result.evaluations[0]
for evaluation in iteration_result.evaluations:
    if evaluation.mean_global_cost < iteration_best.mean_global_cost:
        iteration_best = evaluation
```

```python
iteration_result = self.select_best_local_weight_set_across_seeds(
    candidates,
    seed_values,
)
```

Alle Nachbarschafts- und Zufallskandidaten werden mit allen Seeds bewertet.
`iteration_result.best_weights` ist danach der lokale Gewichtssatz mit den
niedrigsten mittleren globalen Kosten über alle Seeds. Dieser Satz hat in den
getesteten unterschiedlichen Situationen insgesamt am robustesten funktioniert.
Zusätzlich enthält `iteration_result` die vollständige Bewertung aller
Kandidaten dieser Iteration. Über mehrere Iterationen wird nicht mehr jede
Bewertung gespeichert; dafür gibt es das Gedächtnis `best_solution_memory`, das
nur neue globale Bestlösungen enthält.

Konkretes Beispiel:

```text
Satz A: Seed-Kosten (120, 110, 130) → Mittelwert 120
Satz B: Seed-Kosten ( 90, 100,  95) → Mittelwert  95
Satz C: Seed-Kosten (105, 115, 110) → Mittelwert 110

iteration_result.best_weights
→ die Gewichte von Satz B

iteration_result.best_mean_global_cost
→ 95

iteration_result.evaluations
→ (
    WeightEvaluation(
        weights=HeuristicWeights(queue_priority=0.40,
                                  pick_short_transport_time=0.30),
        objective_values=(120, 110, 130),
        mean_global_cost=120,
    ),
    WeightEvaluation(
        weights=HeuristicWeights(queue_priority=0.65,
                                  pick_short_transport_time=0.30),
        objective_values=(90, 100, 95),
        mean_global_cost=95,
    ),
    WeightEvaluation(
        weights=HeuristicWeights(queue_priority=0.40,
                                  pick_short_transport_time=0.55),
        objective_values=(105, 115, 110),
        mean_global_cost=110,
    ),
  )
```

`iteration_result.evaluations` enthält also für jeden Kandidaten den vollständigen
Gewichtssatz, die Kosten je Seed (`objective_values`) und den Mittelwert
`mean_global_cost`. Im Beispiel sind nur die beiden relevanten Felder sichtbar;
die übrigen `HeuristicWeights`-Felder sind ebenfalls vorhanden. `best_weights`
ist nur der daraus ausgewählte Satz mit `queue_priority=0.65`.

Die vollständige Kandidatenliste dieser Iteration wird nicht über alle Runden
gespeichert. Nur ein neuer globaler Bestwert wird in
`best_solution_memory` abgelegt. Beispiel:

```text
Runde 1: Satz B (95) → best_solution_memory = [B]
Runde 2: Satz D (88) → best_solution_memory = [B, D]
Runde 3: schlechter → best_solution_memory bleibt [B, D]
```

Dieses Gedächtnis wird bei einem Neustart verwendet, während die Bewertungen
aller einzelnen Kandidaten nach ihrer Iteration verworfen werden.

Beim Neustart wird immer die beste gespeicherte Lösung verwendet, nicht eine
zufällige Lösung:

```python
remembered_solution = best_solution_memory[-1]
current_local_weights = remembered_solution.weights
```

Die letzte gespeicherte Lösung ist die bisher beste, weil nur echte
Verbesserungen an `best_solution_memory` angehängt werden.

```python
iteration_best = iteration_result.evaluations[0]
```

Die erste Bewertung wird zunächst als bester Kandidat der aktuellen Iteration
angenommen.

```python
for evaluation in iteration_result.evaluations:
```

Danach werden alle Bewertungen dieser Iteration nacheinander geprüft.

```python
if evaluation.mean_global_cost < iteration_best.mean_global_cost:
    iteration_best = evaluation
```

Hat ein Kandidat niedrigere mittlere globale Kosten, wird er als neuer
`iteration_best` gespeichert. Nach der Schleife ist damit der beste Kandidat
dieser Iteration bekannt. Im Beispiel wird zuerst A gesetzt, danach ersetzt B
A, weil `95 < 120`; C ersetzt B nicht, weil `110 > 95`. Somit gilt:

```text
iteration_best = Satz B
iteration_best.mean_global_cost = 95
```

Danach wird der Runden-Beste mit dem bisherigen globalen Bestwert verglichen:

```python
if (
    best_evaluation is None
    or iteration_best.mean_global_cost < best_evaluation.mean_global_cost
):
    best_evaluation = iteration_best
    current_local_weights = iteration_best.weights
    weight_step_fraction /= 2.0
    rounds_without_improvement = 0
else:
    rounds_without_improvement += 1
    if rounds_without_improvement >= restart_after_no_improvement:
        current_local_weights = self.random_local_weight_candidates(
            1, exploration_rng
        )[0]
        weight_step_fraction = initial_local_weight_step_fraction
        rounds_without_improvement = 0
```

`best_evaluation is None` ist nur bei der ersten Iteration wahr. Dann wird der
erste Runden-Beste als globaler Bestwert gespeichert. Ist der neue
`iteration_best` günstiger, werden außerdem seine Gewichte zum Mittelpunkt der
nächsten Nachbarschaft und die Schrittweite wird halbiert. Der Zähler für
erfolglose Runden wird zurückgesetzt.

Wenn keine Verbesserung vorliegt, erhöht `rounds_without_improvement` den
Zähler. Erreicht er `restart_after_no_improvement` (standardmäßig `2`), wird
ein zufälliger neuer Gewichtssatz als Ausgangspunkt gewählt und die Schrittweite
auf ihren Anfangswert zurückgesetzt. Der bisher globale Bestwert bleibt dabei
unverändert.

Bei jeder erfolglosen Runde werden zwei Zähler erhöht:

```python
# Zählt erfolglose Runden bis zum nächsten Neustart.
rounds_without_improvement += 1

# Zählt erfolglose Runden für den endgültigen Abbruch.
total_rounds_without_improvement += 1
```

Der erste Zähler wird nach einem Neustart zurückgesetzt und steuert nur den
Neustart. Der zweite zählt für den gesamten aktuellen Suchlauf weiter und
steuert den Abbruch nach `stop_after_no_improvement` Runden. Beide Zähler werden
bei einer Verbesserung auf `0` zurückgesetzt.

Im konkreten ersten Durchlauf wird deshalb Satz B übernommen:

```text
best_evaluation = Satz B
current_local_weights = Satz B
weight_step_fraction: 0.25 → 0.125
rounds_without_improvement: 0
```

### Erste Runde vollständig als Ablauf

Zu Beginn der ersten Runde gilt im Programm:

```text
best_evaluation = None
current_local_weights = Ausgangssatz
weight_step_fraction = 0.25
rounds_without_improvement = 0
```

Nach der Kandidatenbewertung ist im Beispiel Satz B der beste Satz der Runde:

```text
iteration_best = Satz B
iteration_best.mean_global_cost = 95
```

Dann ist die `if`-Bedingung wahr, weil `best_evaluation` noch `None` ist. Die
vier Zuweisungen bedeuten nacheinander:

```python
best_evaluation = iteration_best
```

Der globale Bestwert wird auf Satz B gesetzt. `best_evaluation` enthält jetzt
Satz B und seinen Mittelwert `95`.

```python
current_local_weights = iteration_best.weights
```

Der aktuelle Mittelpunkt für die nächste Suche wird ebenfalls Satz B. Die
nächsten Nachbarn werden also um Bs Gewichte gebildet.

```python
weight_step_fraction /= 2.0
```

Die Schrittweite wird von `0.25` auf `0.125` verkleinert. Verbesserungen werden
ab jetzt in kleineren Schritten untersucht.

```python
rounds_without_improvement = 0
```

Der Zähler für erfolglose Runden wird zurückgesetzt, weil eine Verbesserung
gefunden wurde.

Danach beginnt die zweite Runde der äußeren Schleife. Das Gedächtnis der
bisherigen Bestlösungen wird dabei nicht als neuer Mittelpunkt verwendet;
`current_local_weights` enthält diesen Mittelpunkt:

```text
best_solution_memory = [Satz B]
current_local_weights = Satz B
weight_step_fraction = 0.125
best_evaluation = Satz B mit Kosten 95
```

Mit diesen Werten erzeugt die zweite Runde neue Nachbarn um Satz B und ergänzt
erneut zufällige Explorationskandidaten.

### Einfaches Beispiel: zwei Runden

```text
Runde 1:
  Ausgangssatz wird getestet.
  Satz B ist mit mittleren globalen Kosten von 95 am besten.
  → best_evaluation = B
  → current_local_weights = B
  → Schrittweite: 0.25 → 0.125

Runde 2:
  Neue Kandidaten werden um B mit Schrittweite 0.125 erzeugt.
  Satz D erreicht mittlere globale Kosten von 88.
  → D ist besser als B (88 < 95)
  → best_evaluation = D
  → current_local_weights = D
  → Schrittweite: 0.125 → 0.0625
```

Wenn in Runde 2 kein Kandidat unter `95` liegt, bleibt B der globale Bestwert.
Dann wird die Schrittweite nicht halbiert; stattdessen zählt
`rounds_without_improvement` eine erfolglose Runde. Nach der festgelegten Zahl
erfolgloser Runden wird ein zufälliger Neustart durchgeführt.

Die Änderungen in Runde 2 werden durch diese konkreten Codezeilen verursacht:

| Ergebnis | Verursachende Codezeile | Bedeutung |
|---|---|---|
| Neue Nachbarn um B | `neighboring_weights(current_local_weights, weight_step_fraction)` | verwendet B als Mittelpunkt und `0.125` als Schrittweite |
| D wird als Runden-Bester gefunden | `if evaluation.mean_global_cost < iteration_best.mean_global_cost` | vergleicht alle Kandidaten der Runde |
| `best_evaluation = D` | `best_evaluation = iteration_best` | speichert D als neuen globalen Bestwert |
| Mittelpunkt wird D | `current_local_weights = iteration_best.weights` | nächste Runde startet um D |
| `0.125 → 0.0625` | `weight_step_fraction /= 2.0` | halbiert die Schrittweite nach einer Verbesserung |

### Runde 3: schlechteres Ergebnis und `else`

Angenommen, D bleibt der bisher globale Bestwert mit Kosten `88`, aber der
beste Kandidat der dritten Runde (Satz E) hat Kosten `100`:

```text
iteration_best = E       → mean_global_cost = 100
best_evaluation = D      → mean_global_cost = 88
```

Die Bedingung ist falsch, weil `100 < 88` nicht gilt. Deshalb wird der
`else`-Teil ausgeführt:

```python
rounds_without_improvement += 1
```

Der Zähler steigt von `0` auf `1`. Der globale Bestwert D bleibt unverändert,
die aktuellen Gewichte bleiben D und die Schrittweite bleibt `0.0625`.

```text
best_evaluation = D (88)
current_local_weights = D
weight_step_fraction = 0.0625
rounds_without_improvement = 1
```

Erst wenn auch die nächste Runde keine Verbesserung bringt, erreicht der Zähler
bei `restart_after_no_improvement=2` den Grenzwert. Dann wird ein zufälliger
neuer Gewichtssatz als Ausgangspunkt gewählt und die Schrittweite auf den
Anfangswert zurückgesetzt. D mit Kosten `88` bleibt trotzdem als global bester
Satz gespeichert.

### Was passiert beim Erreichen des Grenzwerts?

In Runde 3 steht der Zähler nach `rounds_without_improvement += 1` auf `1`.
Da `1 >= 2` falsch ist, wird dieser Block noch nicht ausgeführt:

```python
if rounds_without_improvement >= restart_after_no_improvement:
```

In Runde 4 ist der neue Kandidat wieder schlechter. Der Zähler steigt von `1`
auf `2`. Jetzt gilt `2 >= 2`, und der innere Block wird ausgeführt:

```python
current_local_weights = self.random_local_weight_candidates(
    1, exploration_rng
)[0]
```

Es wird genau ein zufälliger vollständiger Gewichtssatz erzeugt und als neuer
Ausgangspunkt gespeichert. Der bisher globale Bestwert D bleibt davon
unberührt.

```python
weight_step_fraction = initial_local_weight_step_fraction
```

Die Schrittweite wird auf den ursprünglichen Parameterwert zurückgesetzt, zum
Beispiel:

```text
initial_local_weight_step_fraction = 0.25
weight_step_fraction: 0.0625 → 0.25
```

Damit kann die Suche vom neuen zufälligen Ausgangspunkt wieder mit größeren
Schritten beginnen.

```python
rounds_without_improvement = 0
```

Der Zähler wird nach dem Neustart zurückgesetzt. Die nächste erfolglose Runde
beginnt daher wieder bei `0`.

### Konkrete Runde 4: zweite erfolglose Runde

```text
Vor Runde 4:
best_evaluation = Satz D mit Kosten 88
rounds_without_improvement = 1
restart_after_no_improvement = 2
```

Der beste Kandidat der Runde 4 (Satz F) hat Kosten `101`:

```text
101 < 88  → falsch
```

Daher läuft `else` und danach:

```text
rounds_without_improvement: 1 → 2
```

Jetzt ist `2 >= 2` wahr. Genau deshalb wird ein einzelner zufälliger
Gewichtssatz erzeugt, als `current_local_weights` gespeichert und die
Schrittweite von `0.0625` auf den Anfangswert `0.25` zurückgesetzt. Satz D mit
Kosten `88` bleibt weiterhin der globale Bestwert.

Nach allen Iterationen gibt die Methode genau diesen global besten Satz zurück;
ein späterer Neustart kann ihn nicht überschreiben, solange er schlechter ist.

```text
initiale lokale Gewichte
        ↓
neighboring_weights(...)
        ↓
select_best_local_weight_set_across_seeds(...)
        ↓
bester Kandidat, kleinere Schrittweite und gelegentliche zufällige Neustarts
```

## `neighboring_weights(local_weights, weight_step_fraction)`

Erzeugt den aktuellen Satz sowie Nachbarn, bei denen jeweils genau ein
Gewicht kleiner oder größer ist. Die Werte werden auf `0.0` bis `1.0` begrenzt.

### Eingaben


| Eingabe                | Bedeutung                                                           |
| ------------------------ | --------------------------------------------------------------------- |
| `local_weights`        | Der aktuelle lokale Gewichtssatz, zum Beispiel`queue_priority=0.4`. |
| `weight_step_fraction` | Feste Größe der Änderung, zum Beispiel`0.25`.                    |

### Codezeile für Codezeile

### Einfaches Beispiel: Wert aus einer `dataclass` lesen

Eine `dataclass` speichert Werte als benannte Attribute:

```python
from dataclasses import dataclass

@dataclass
class SimpleWeights:
    speed: float = 0.4
    capacity: float = 0.7

weights = SimpleWeights()
value = weights.speed
```

Nach `value = weights.speed` enthält `value` die Zahl `0.4`. Der Name `speed`
ist dabei ein Attributname und kein Dictionary-Schlüssel.

Wenn der Attributname erst als Text vorliegt, wird `getattr` verwendet:

```python
field_name = "speed"
value = getattr(weights, field_name)
```

Das ist dasselbe wie `weights.speed` und liefert ebenfalls `0.4`. Mit
`getattr` kann derselbe Code nacheinander verschiedene Attribute lesen.

### Anwendung auf `HeuristicWeights`

```python
neighbors = [local_weights]
```

Die Liste beginnt mit dem unveränderten aktuellen Gewichtssatz. Dieser wird
ebenfalls getestet. `local_weights` enthält dabei alle 26 lokalen Gewichte:

```text
complete_job, wait_action, queue_priority,
pick_source_storage_time, pick_short_transport_time,
machine_pick_processing_time, machine_pick_tool_match,
machine_pick_tool_life, target_store_capacity,
place_target_storage_time, place_short_transport_time,
place_machine_queue, place_shortest_processing_time,
release_edd,
rework_defect_machine_deadline_penalty_weight, rework_alternative_machine_deadline_penalty_weight,
downgrade_product, wait_defect_job, job_scrap,
rework_not_allowed_downgrade_bonus_weight,
deadline_pressure_scrap_bonus_weight, deadline_missed_wait_penalty,
rework_defect_machine_deadline_penalty_weight,
rework_alternative_machine_deadline_penalty_weight,
defect_edd, defect_repair_quality
```

Es handelt sich also nicht nur um `queue_priority` oder Transportzeit,
sondern um einen vollständigen lokalen Gewichtssatz.

```python
for weight_field in fields(local_weights):
```

`fields(...)` liefert nacheinander alle Felder von `HeuristicWeights`. Die
Schleife bearbeitet jedes lokale Gewicht einzeln.

```python
field_name = weight_field.name
```

`weight_field.name` liefert den Namen des aktuellen `dataclass`-Feldes, zum
Beispiel `"queue_priority"`.

```python
current_value = float(getattr(local_weights, field_name))
```

`getattr` liest mit diesem Textnamen den aktuellen Wert aus dem Objekt. Bei
`field_name="queue_priority"` entspricht die Zeile also
`local_weights.queue_priority` und liest beispielsweise `0.4`.

```python
step = weight_step_fraction
```

Legt die feste Schrittweite fest. Da alle lokalen Gewichte im Bereich `0.0`
bis `1.0` liegen, wäre `abs(current_value) * weight_step_fraction` immer
kleiner oder gleich dieser festen Schrittweite und ist deshalb nicht nötig.

```python
lower_value = max(0.0, current_value - step)
higher_value = min(1.0, current_value + step)
```

Berechnet einen kleineren und einen größeren Wert. `max` und `min` begrenzen
beide Werte auf den gültigen Bereich von `0.0` bis `1.0`.

```python
neighbors.append(replace(local_weights, **{field_name: lower_value}))
neighbors.append(replace(local_weights, **{field_name: higher_value}))
```

Erzeugt zwei neue, unveränderliche Gewichtssätze. In jedem neuen Satz wird nur
das aktuelle Feld geändert; alle anderen Gewichte bleiben gleich.

```python
return tuple(neighbors)
```

Gibt alle Kandidaten als Tupel zurück.

### Konkretes Beispiel

Zur übersichtlichen Darstellung verwenden wir zunächst nur zwei Gewichte:

```python
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class DemoWeights:
    queue_priority: float
    transport_time: float

local_weights = DemoWeights(
    queue_priority=0.40,
    transport_time=0.30,
)
weight_step_fraction = 0.25
```

Die konkrete Eingabe ist damit:

```text
local_weights       = (queue_priority=0.40, transport_time=0.30)
weight_step_fraction = 0.25
```

Die Methode verändert zuerst nur `queue_priority`:

```text
lower_value = max(0.0, 0.40 - 0.25) = 0.15
higher_value = min(1.0, 0.40 + 0.25) = 0.65
```

Dadurch entstehen zwei vollständige neue Sätze:

```text
(queue_priority=0.15, transport_time=0.30)
(queue_priority=0.65, transport_time=0.30)
```

Danach verändert die Methode nur `transport_time`:

```text
lower_value = max(0.0, 0.30 - 0.25) = 0.05
higher_value = min(1.0, 0.30 + 0.25) = 0.55
```

Die vollständige Ausgabe der Methode ist deshalb:

```python
(
    DemoWeights(queue_priority=0.40, transport_time=0.30),
    DemoWeights(queue_priority=0.15, transport_time=0.30),
    DemoWeights(queue_priority=0.65, transport_time=0.30),
    DemoWeights(queue_priority=0.40, transport_time=0.05),
    DemoWeights(queue_priority=0.40, transport_time=0.55),
)
```

Die Zahlen lassen sich direkt zurückrechnen:

```text
queue_priority:          0.40 - 0.25 = 0.15
queue_priority:          0.40 + 0.25 = 0.65
transport_time:          0.30 - 0.25 = 0.05
transport_time:          0.30 + 0.25 = 0.55
```

Die Reihenfolge der Ausgabe ist daher:

```text
1. (0.40, 0.30) unveränderter Ausgangssatz
2. (0.15, 0.30) nur queue_priority kleiner
3. (0.65, 0.30) nur queue_priority größer
4. (0.40, 0.05) nur transport_time kleiner
5. (0.40, 0.55) nur transport_time größer
```

### Wichtig: Pro Nachbar ändert sich nur ein Gewicht

Jeder Nachbar ist trotzdem ein vollständiger Gewichtssatz. Die Methode ändert
aber pro neuem Satz genau ein Feld; alle übrigen Felder werden aus dem
Ausgangssatz übernommen:

```text
Ausgang: queue_priority=0.40, transport_time=0.30, tool_life=0.10

Nachbar 1: queue_priority=0.15, transport_time=0.30, tool_life=0.10
           └── nur queue_priority geändert

Nachbar 2: queue_priority=0.40, transport_time=0.05, tool_life=0.10
                              └── nur transport_time geändert

Nachbar 3: queue_priority=0.40, transport_time=0.30, tool_life=0.35
                                             └── nur tool_life geändert
```

Der Ausgangssatz wird nicht überschrieben. `replace(...)` erzeugt für jeden
Nachbarn eine neue Kopie; deshalb kann der unveränderte Satz ebenfalls fair
mit allen Varianten verglichen werden.

Es kommen also fünf vollständige Gewichtssätze zurück: ein unveränderter Satz
und für jedes der zwei Gewichte jeweils ein kleinerer und ein größerer Satz.

## `random_local_weight_candidates(candidate_count, rng)`

Nach `neighboring_weights(...)` ruft `optimize_iteratively(...)` diese Methode
auf. Sie erzeugt zusätzliche vollständige Gewichtssätze für die Exploration.

```text
candidate_count = 10
→ zehn Kandidaten erzeugen
→ jedes der 27 Gewichte erhält einen Zufallswert zwischen 0.0 und 1.0
→ jeder Kandidat enthält wieder alle 27 Gewichte
```

Diese Kandidaten liegen nicht nur direkt neben dem aktuellen Satz. Dadurch kann
der Optimierer auch andere Bereiche des Gewichtsraums untersuchen.

Die Methode arbeitet dabei bewusst in einzelnen Schritten:

```python
values = {}
```

Für einen neuen Kandidaten wird zunächst ein leeres Dictionary vorbereitet.

```python
for weight_field in fields(HeuristicWeights):
    field_name = weight_field.name
    values[field_name] = rng.random()
```

Danach werden alle 27 Feldnamen nacheinander gelesen. Für jedes Feld erzeugt
`rng.random()` eine Zahl zwischen `0.0` und `1.0` und speichert sie unter diesem
Namen. Nach der Schleife enthält `values` beispielsweise:

```text
{
    "queue_priority": 0.62,
    "pick_short_transport_time": 0.18,
    "machine_pick_tool_life": 0.91,
    ...
}
```

```python
candidate = HeuristicWeights(**values)
candidates.append(candidate)
```

`HeuristicWeights(**values)` baut aus diesem Dictionary einen vollständigen
Gewichtssatz. Dieser fertige Satz wird anschließend in die Kandidatenliste
eingefügt. Das `**` übergibt jedes Dictionary-Feld als benanntes Argument.

Konkretes Zahlenbeispiel mit nur drei Feldern:

```python
values = {
    "queue_priority": 0.62,
    "pick_short_transport_time": 0.18,
    "machine_pick_tool_life": 0.91,
}

candidate = HeuristicWeights(**values)
candidates.append(candidate)
```

Das Entpacken entspricht dabei dieser Schreibweise:

```python
candidate = HeuristicWeights(
    queue_priority=0.62,
    pick_short_transport_time=0.18,
    machine_pick_tool_life=0.91,
)
```

Nach `candidates.append(candidate)` enthält die Liste beispielsweise:

```text
[
    HeuristicWeights(queue_priority=0.62,
                     pick_short_transport_time=0.18,
                     machine_pick_tool_life=0.91),
    ...
]
```

Wird die Schleife dreimal ausgeführt, entstehen drei vollständige Kandidaten,
zum Beispiel:

```text
Kandidat 1: queue=0.62, transport=0.18, tool_life=0.91
Kandidat 2: queue=0.11, transport=0.74, tool_life=0.36
Kandidat 3: queue=0.89, transport=0.27, tool_life=0.05
```

`return tuple(candidates)` gibt diese Kandidaten anschließend als Tupel zurück.

## Was passiert danach in `optimize_iteratively(...)`?

`neighboring_weights(...)` gibt zunächst nur die 55 lokalen
Nachbarschaftskandidaten zurück. `optimize_iteratively(...)` führt danach den
eigentlichen Vergleich durch:

```text
1. 55 Nachbarn von neighboring_weights(...) erhalten
2. 10 zufällige Gewichtssätze für Exploration ergänzen
3. insgesamt 65 vollständige Gewichtssätze haben
4. jeden Gewichtssatz mit jedem Seed an den Runner übergeben
5. pro Lauf GlobalSimulationMetrics sammeln
6. pro Lauf globale Kosten mit GlobalSimulationEvaluation berechnen
7. je Kandidat den Mittelwert seiner Seed-Kosten bilden
8. den Kandidaten mit den niedrigsten mittleren Kosten auswählen
9. den bisher global besten Kandidaten speichern
10. bei Verbesserung die Schrittweite halbieren
11. nach mehreren erfolglosen Runden zufällig neu starten
```

Konkretes Beispiel mit `seeds=[1, 2, 3]`:

```text
65 Kandidaten × 3 Seeds = 195 Simulationsläufe pro Iteration
```

Der ausgewählte Kandidat wird in der nächsten Iteration zum neuen Mittelpunkt
der Nachbarschaftssuche. Der globale Bestwert bleibt auch dann erhalten, wenn
ein späterer zufälliger Neustart schlechtere Ergebnisse liefert.

Bei den echten 26 lokalen Gewichten sind es entsprechend
`1 + 27 + 27 = 55` vollständige Nachbarschaftskandidaten. Die zehn zusätzlichen
Zufallskandidaten werden erst in `optimize_iteratively(...)` ergänzt.

```text
aktueller Satz
├── unveränderter Satz
├── jeder einzelne Wert etwas kleiner
└── jeder einzelne Wert etwas größer
```

## `select_best_local_weight_set_across_seeds(local_weight_candidates, seeds, iteration_number, progress_callback)`

Diese Methode wird in `optimize_iteratively(...)` nach
`random_local_weight_candidates(...)` aufgerufen. Zu diesem Zeitpunkt enthält
`local_weight_candidates` bereits beide Arten von Kandidaten:

```text
55 Nachbarschaftskandidaten
+ 10 zufällige Explorationskandidaten
= 65 vollständige lokale Gewichtssätze
```

Die Methode bewertet jeden lokalen Gewichtssatz mit allen Seeds, berechnet pro
Gewichtssatz den Mittelwert der globalen Kosten und gibt den Gewichtssatz mit
dem kleinsten Mittelwert zurück.

Nach jedem fertig bewerteten Kandidaten wird `progress_callback` aufgerufen.
Dadurch kann das Webinterface bereits während einer Iteration den aktuellen
Kostenwert anzeigen.

### Vergleichstabelle


| Gewichtssatz | Kosten Seed 1 | Kosten Seed 2 | Kosten Seed 3 | Mittlere globale Kosten | Ergebnis          |
| -------------- | --------------: | --------------: | --------------: | ------------------------: | ------------------- |
| Satz A       |           120 |           110 |           130 |                     120 | nicht ausgewählt |
| Satz B       |            90 |           100 |            95 |                      95 | **bester Satz**   |
| Satz C       |           105 |           115 |           110 |                     110 | nicht ausgewählt |

Berechnung für Satz B:

```text
(90 + 100 + 95) / 3 = 95
```

Da `95` der kleinste Mittelwert ist, gibt die Methode Satz B zurück.

Das Ziel von `select_best_local_weight_set_across_seeds(...)` ist, den lokalen
Gewichtssatz auszuwählen, der in unterschiedlichen möglichen
Fabriksituationen zuverlässig funktioniert. Ein Satz, der nur in einem
einzelnen Seed sehr gut, in den anderen aber deutlich schlechter ist, erhält
einen höheren Mittelwert. Der Satz mit dem niedrigsten Mittelwert ist deshalb
im Vergleich robuster.

### Codezeile für Codezeile

Die vollständige Methode sieht im Programm so aus:

```python
def select_best_local_weight_set_across_seeds(self, local_weight_candidates, seeds):
    seed_values = tuple(seeds)
    evaluations = []

    for local_weights in local_weight_candidates:
        evaluations.append(
            self.evaluate_local_weights_across_seeds(local_weights, seed_values)
        )

    best_evaluation = evaluations[0]
    for evaluation in evaluations:
        if evaluation.mean_global_cost < best_evaluation.mean_global_cost:
            best_evaluation = evaluation

    return WeightOptimizationResult(
        best_weights=best_evaluation.weights,
        best_mean_global_cost=best_evaluation.mean_global_cost,
        evaluations=tuple(evaluations),
    )
```

Die folgenden Erklärungen beziehen sich genau auf diese Codezeilen.

```python
seed_values = tuple(seeds)
```

Die Seeds werden in ein Tupel umgewandelt, damit sie für jeden Kandidaten
erneut verwendet werden können.

```python
evaluations = []
```

Eine leere Liste wird für die Ergebnisse aller Kandidaten vorbereitet.

```python
for local_weights in local_weight_candidates:
```

Die Methode nimmt nacheinander jeden vollständigen lokalen Gewichtssatz aus
der Kandidatenliste.

```python
evaluations.append(
    self.evaluate_local_weights_across_seeds(local_weights, seed_values)
)
```

Der aktuelle Gewichtssatz wird mit allen Seeds getestet. `evaluate_local_weights_across_seeds(...)`
führt die vollständigen Simulationen aus und gibt eine `WeightEvaluation` mit
den Kosten je Seed und deren Mittelwert zurück. Dieses Ergebnis wird gespeichert.

```python
best_evaluation = evaluations[0]
```

Der erste bewertete Kandidat wird zunächst als bester Kandidat angenommen.

```python
for evaluation in evaluations:
    if evaluation.mean_global_cost < best_evaluation.mean_global_cost:
        best_evaluation = evaluation
```

Danach werden alle Bewertungen verglichen. Der Kandidat mit dem kleinsten
mittleren globalen Kostenwert wird als bester Kandidat behalten.

```python
return WeightOptimizationResult(
    best_weights=best_evaluation.weights,
    best_mean_global_cost=best_evaluation.mean_global_cost,
    evaluations=tuple(evaluations),
)
```

Zurückgegeben werden der beste lokale Gewichtssatz, sein mittlerer globaler
Kostenwert und das Gedächtnis der bisher gefundenen Verbesserungen.

### Konkretes Ergebnisbeispiel

```text
Kandidat A → Seed-Kosten (120, 110, 130) → Mittelwert 120
Kandidat B → Seed-Kosten ( 90, 100,  95) → Mittelwert 95
Kandidat C → Seed-Kosten (105, 115, 110) → Mittelwert 110
```

`select_best_local_weight_set_across_seeds(...)` gibt in diesem Beispiel Kandidat B zurück, weil `95` der
niedrigste mittlere Kostenwert ist.

## `evaluate_local_weights_across_seeds(local_weights, seeds)`

Diese Methode wird von `select_best_local_weight_set_across_seeds(...)` für jeden einzelnen Kandidaten
aufgerufen. Sie bewertet genau einen lokalen Gewichtssatz mit allen
angegebenen Seeds.

### Warum wird diese Methode benötigt?

Ein einzelner Simulationslauf zeigt nur ein mögliches Szenario der Fabrik.
Zufällige Defekte, Defektschweregrade und andere Zufallsentscheidungen können
das Ergebnis beeinflussen. Deshalb wird derselbe lokale Gewichtssatz mit
mehreren Seeds getestet:

```text
ein Gewichtssatz
    ↓
Seed 1: mögliches Fabrikszenario 1
Seed 2: mögliches Fabrikszenario 2
Seed 3: mögliches Fabrikszenario 3
    ↓
mittlere globale Kosten
```

Das Ziel ist, einen Gewichtssatz zu finden, der in verschiedenen möglichen
Situationen zuverlässig funktioniert und nicht nur zufällig in einem einzigen
Lauf gut abschneidet. Der Mittelwert fasst die Ergebnisse dieser Szenarien zu
einem Vergleichswert zusammen. `select_best_local_weight_set_across_seeds(...)` kann damit unterschiedliche
Gewichtssätze fair vergleichen.

So bewerten wir, ob ein Gewichtssatz in verschiedenen möglichen Situationen
zuverlässig funktioniert und nicht nur zufällig in einem einzigen
Simulationslauf gut ist.

### Konkrete Eingabe

```python
local_weights = HeuristicWeights(queue_priority=0.62)
seeds = [1, 2, 3]
```

Das bedeutet: Dieser eine vollständige lokale Gewichtssatz wird in drei
Simulationsläufen mit den Seeds `1`, `2` und `3` getestet.

### Codezeile für Codezeile

Die vollständige Methode lautet:

```python
def evaluate_local_weights_across_seeds(self, local_weights, seeds):
    objective_values = []

    for seed in seeds:
        metrics = self.simulation_runner(local_weights, seed)
        objective_values.append(self.global_evaluation.evaluate(metrics))

    objective_values_tuple = tuple(objective_values)
    return WeightEvaluation(
        weights=local_weights,
        objective_values=objective_values_tuple,
        mean_global_cost=mean(objective_values_tuple),
    )
```

```python
objective_values = []
```

Eine leere Liste für die globalen Kosten jedes Simulationslaufs wird angelegt.

```python
for seed in seeds:
```

Die Methode durchläuft jeden angegebenen Seed einzeln.

```python
metrics = self.simulation_runner(local_weights, seed)
```

Der Runner führt mit genau diesem Gewichtssatz und diesem Seed einen
vollständigen headless Simulationslauf aus. Danach liefert er die globalen
Kennzahlen, zum Beispiel Makespan, Verspätung und Transportzeit.

```python
objective_values.append(self.global_evaluation.evaluate(metrics))
```

Die globale Bewertung kombiniert diese Kennzahlen mit den festen globalen
Gewichten zu einem Kostenwert. Dieser Kostenwert wird gespeichert.

```python
objective_values_tuple = tuple(objective_values)
```

Die gesammelten Kosten werden in ein unveränderliches Tupel umgewandelt.

```python
return WeightEvaluation(
    weights=local_weights,
    objective_values=objective_values_tuple,
    mean_global_cost=mean(objective_values_tuple),
)
```

Die Methode gibt den getesteten Gewichtssatz, die Kosten jedes Seeds und den
Mittelwert dieser Kosten zurück.

### Konkrete Ausgabe

Angenommen, die drei Läufe liefern diese globalen Kosten:

```text
Seed 1 → 120.0
Seed 2 →  90.0
Seed 3 → 105.0
```

Dann ist die Ausgabe:

```python
WeightEvaluation(
    weights=local_weights,
    objective_values=(120.0, 90.0, 105.0),
    mean_global_cost=105.0,
)
```

Der Mittelwert wird so berechnet:

```text
(120.0 + 90.0 + 105.0) / 3 = 105.0
```

Dieser Mittelwert wird anschließend von `select_best_local_weight_set_across_seeds(...)` mit den Mittelwerten
der anderen Kandidaten verglichen.

```text
HeuristicWeights
    ↓
für jeden Seed: Runner(weights, seed)
    ↓
GlobalSimulationMetrics
    ↓
GlobalSimulationEvaluation.evaluate(metrics)
    ↓
globaler Kostenwert
    ↓
Mittelwert über alle Seeds
```

Das Ergebnis ist ein `WeightEvaluation` mit Gewichtssatz, Einzelwerten je Seed
und mittlerem globalem Kostenwert.

## `WeightEvaluation` und `WeightOptimizationResult`

`WeightEvaluation` speichert das Ergebnis eines Gewichtssatzes. Darin stehen
der Satz selbst, die Kosten pro Seed und ihr Mittelwert.

`WeightOptimizationResult` speichert den besten lokalen Satz, dessen besten
mittleren Kostenwert und die vollständige Bewertungshistorie.

## Zahlenbeispiel

Bei drei lokalen Gewichten entstehen pro Runde ungefähr:

```text
1 ursprünglicher Satz
+ 3 Sätze mit jeweils einem kleineren Gewicht
+ 3 Sätze mit jeweils einem größeren Gewicht
= 7 Kandidaten
```

Mit drei Seeds werden daraus:

```text
7 Kandidaten × 3 Seeds = 21 vollständige Simulationsläufe
```

```text
mittlere Kosten = (Kosten Seed 1 + Kosten Seed 2 + Kosten Seed 3) / 3
```

## Gesamtzusammenhang

```text
LocalHeuristicWeightOptimizer
    ↓ lokale Gewichtskandidaten erzeugen
SpineMLSimulationRunner(weights, seed)
    ↓ vollständigen Lauf ausführen
GlobalSimulationMetrics
    ↓ globale Kennzahlen liefern
GlobalSimulationEvaluation
    ↓ globale Kosten mit festen Gewichten berechnen
LocalHeuristicWeightOptimizer
    ↓ besten lokalen Satz auswählen
```
