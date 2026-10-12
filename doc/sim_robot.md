# SimRobot

Python-Datei: `sources/SpineML/Simulation/SimRobot.py`

`SimRobot` ist die gemeinsame Basisklasse von:

```text
SimRobot (sim.Component)
├── SimRobotMain
└── SimRobotCorridorArm
```

Die Klasse enthält die gemeinsamen Positionsdaten, Bewegungszustände,
Animationsfunktionen, Geschwindigkeitsberechnung und Bewegungsmethoden. Sie
besitzt keinen eigenen `process()`-Ablauf. Die konkreten Roboterklassen
implementieren ihren Prozess und verwenden die Methoden dieser Basisklasse.

## __init__()

```python
def __init__(
    self,
    label: str,
    indent: int,
    x: float,
    y: float,
    z: float,
    color: str,
    *args,
    **kwargs,
):
```

### Eingaben

| Parameter | Beispiel Main-Roboter | Bedeutung |
| --- | --- | --- |
| `label` | `"Main robot"` | lesbarer Name des Roboters |
| `indent` | `0` | Einrückung für Statistikdarstellungen |
| `x` | `0` | anfängliche X-Position |
| `y` | `2.5` | anfängliche Y-Position |
| `z` | `2.5` | anfängliche Z-Position |
| `color` | `"red"` | Farbe des 3D-Roboterkörpers |

### Salabim-Komponente initialisieren

```python
super().__init__(*args, **kwargs)
```

Dadurch wird der Roboter zu einer echten `sim.Component` und erhält unter
anderem seine Simulationsumgebung `self.env`.

### Name und Statistik-Einrückung speichern

```python
self.label = label
self.indent = indent
```

### Aktuelle Position und Startzeit speichern

```python
self.x = x
self.y = y
self.z = z
self.t = self.env.now()
```

```text
x / y / z
└── aktuell vollständig erreichte Position

t
└── Simulationszeit, zu der diese Position erreicht beziehungsweise eine neue
    Bewegung begonnen wurde
```

### Nächste Position und Zielzeit initialisieren

```python
self.next_x = x
self.next_y = y
self.next_z = z
self.next_t = self.env.now()
```

Am Anfang sind aktuelle und nächste Position gleich. Der Roboter bewegt sich
noch nicht.

```text
aktuelle Position = nächste Position
aktuelle Zeit      = nächste Zeit
```

### Bewegungs- und Ladungszustände

```python
self.state_move = sim.State(
    "Move",
    value="waiting",
    env=self.env,
)

self.state_load = sim.State(
    "Load",
    value="empty",
    env=self.env,
)
```

Mögliche Werte:

```text
state_move
├── "waiting"
├── "moving_x"
├── "moving_y"
└── "moving_z"

state_load
├── "empty"
└── "loaded"
```

`"Move"` und `"Load"` sind lediglich die internen Namen der beiden
Salabim-States. Die aktuellen Werte sind anfangs `"waiting"` und `"empty"`.

### Sichtbaren Roboterkörper erzeugen

```python
sim.Animate3dBox(
    x_len=0.5,
    y_len=0.5,
    z_len=0.5,
    color=color,
    edge_color="white",
    x=self.x_func,
    y=self.y_func,
    z=self.z_func,
)
```

Die Positionen werden nicht als feste Zahlen übergeben. Salabim ruft während
der Animation `x_func()`, `y_func()` und `z_func()` auf, damit der Roboter
zwischen Start- und Zielposition sichtbar bewegt wird.

## x_func(animation_time)

```python
def x_func(self, animation_time: float):
    if self.next_t == self.t:
        return self.x
    return self.x + (
        (self.next_x - self.x)
        * (animation_time - self.t)
        / (self.next_t - self.t)
    )
```

Die Methode gibt die X-Position für einen bestimmten Animationszeitpunkt
zurück.

```text
next_t == t
└── keine zeitlich laufende Bewegung
    └── aktuelle Position x zurückgeben

next_t != t
└── Zwischenposition zwischen x und next_x interpolieren
```

Beispiel:

```text
x = 0                 next_x = 10
t = 20                next_t = 30
animation_time = 25

x_func(25) = 0 + (10 - 0) × (25 - 20) / (30 - 20)
           = 5
```

Nach der Hälfte der Bewegungszeit wird der Roboter in der Mitte dargestellt.

## y_func(animation_time)

`y_func()` verwendet dieselbe Interpolation für die Y-Achse:

```text
aktuelle Y-Position
+ Positionsunterschied
× vergangene Bewegungszeit
/ gesamte Bewegungszeit
```

Wenn keine Y-Bewegung läuft, wird direkt `self.y` zurückgegeben.

## z_func(animation_time)

`z_func()` verwendet dieselbe Interpolation für die Z-Achse. Diese Achse wird
beispielsweise beim Absenken zu einem Store und beim anschließenden Anheben
verwendet.

## movement_speed aus der Policyaktion

Der `SpineActionGenerator` definiert die zulässigen Geschwindigkeiten als
Tupel:

```python
ROBOT_MOVEMENT_SPEEDS = (0.5, 1.0, 2.0)
```

Der Generator erzeugt für jede Roboter-Basisaktion drei Kandidaten:

```python
"movement_speed": 0.5
"movement_speed": 1.0
"movement_speed": 2.0
```

```text
0.5 → halbe Geschwindigkeit → doppelte Bewegungsdauer
1.0 → normale Geschwindigkeit
2.0 → doppelte Geschwindigkeit → halbe Bewegungsdauer
```

Der Evaluator bewertet die drei Kandidaten. Der Selector wählt anhand dieser
Bewertung eine Variante aus. Die aktuelle Baseline bevorzugt `2.0`; ein
späterer heuristischer oder RL-Evaluator kann andere Ziele berücksichtigen.

Die konkreten Roboter lesen die Geschwindigkeit aus der aufgelösten
`SimulationAction`:

```python
movement_speed = action.payload["movement_speed"]
```

```text
SpineActionGenerator auf der Policyseite
└── erzeugt je einen Kandidaten für 0.5, 1.0 und 2.0
        ↓
ActionEvaluator und ActionSelector
└── bewerten und wählen eine Geschwindigkeitsvariante
        ↓
SimulationBridge
└── übergibt den reinen Zahlenwert unverändert
        ↓
SimRobotMain / SimRobotCorridorArm
└── übergibt movement_speed an move_x(), move_y() oder move_z()
        ↓
SimRobot
└── berechnet duration = distance / movement_speed
```

Die Policy bestimmt nicht die Koordinaten und liefert nicht die tatsächliche
Bewegungsdauer. Diese beiden Aufgaben verbleiben im Simulationskern.

## take_selected_job_from_store(action, target_store)

Die Methode nimmt exakt den Job aus einem echten Store, den die Policy zuvor
über seine ID ausgewählt hat und den die Bridge in ein echtes
`SimOrderJob`-Objekt aufgelöst hat.

Konkrete Eingabe:

```python
action.payload = {
    "selected_job_id": "Order 1.1:0",
    "selected_job": sim_order_job_0,
}

target_store = start_store
```

### 1. Aufgelöstes Jobobjekt lesen

```python
selected_job = action.payload["selected_job"]
```

### 2. Genau diesen Job aus dem Store nehmen

```python
job = yield self.from_store(
    target_store,
    filter=lambda item, selected_job=selected_job: item is selected_job,
)
```

```text
from_store(...)
└── Salabim-Anforderung zum Entnehmen eines Store-Elements

filter=...
└── nur das Element akzeptieren, das dasselbe Python-Objekt wie selected_job ist

item is selected_job
└── Identitätsprüfung, nicht nur Vergleich gleicher Attribute
```

Wenn der Job noch nicht entnommen werden kann, wartet nur der aktuelle
Roboterprozess an diesem `yield`. Andere Simulationskomponenten laufen weiter.

Die Methode erzeugt selbst keinen `ValueError`. Die `GeneratorSelectorPolicy`
prüft anhand der PolicyObservation, ob die Job-ID im Ziel-Store liegt, und
reserviert sie innerhalb der PolicyDecision für genau eine Aktion. Die Bridge
löst danach nur die IDs auf. Der Identitätsfilter stellt bei der Store-
Entnahme zusätzlich sicher, dass kein anderer Job entnommen wird.

### 3. Job zurückgeben

```python
return job
```

Der aufrufende Generator erhält den echten `SimOrderJob`:

```python
job = yield from self.take_selected_job_from_store(action, target_store)
```

## Was ist ein Generator?

Eine Python-Funktion beziehungsweise Methode wird zum Generator, sobald sie
ein `yield` enthält. Diese Methoden sind deshalb Generatoren:

```text
take_selected_job_from_store()
move_x()
move_y()
move_z()
```

Ein Generator kann seine Ausführung unterbrechen und später an derselben Stelle
fortsetzen.

```text
Code vor yield ausführen
        ↓
bei yield unterbrechen
        ↓
Salabim verarbeitet andere Ereignisse
        ↓
Anforderung ist erfüllt
        ↓
Code nach yield fortsetzen
```

## Was bedeutet yield from?

Die konkreten Roboter verwenden beispielsweise:

```python
yield from self.move_y(target_y, speed)
```

`yield from` führt den Generator `move_y()` vollständig aus. Der aufrufende
Roboterprozess wird erst hinter dieser Zeile fortgesetzt, wenn `move_y()`
beendet ist.

```text
execute_pick_action()
├── yield from move_y(...)
│   ├── Bewegung vorbereiten
│   ├── bei yield hold(duration) warten
│   └── Bewegung abschließen
└── erst danach nächste Zeile von execute_pick_action() ausführen
```

Nicht die gesamte Simulation wird blockiert. Nur der Prozess dieses Roboters
wartet.

## move_x(next_x, speed)

`move_x()` bewegt den Roboter auf der X-Achse und ist wegen des enthaltenen
`yield` ein Generator.

```python
duration = abs(next_x - self.x) / speed
```

Beispiel:

```text
aktuelle Position x = 2
Zielposition next_x = 8
speed               = 2

duration = |8 - 2| / 2 = 3
```

Vollständige Reihenfolge:

```text
1. duration = Strecke / Geschwindigkeit berechnen
2. t = aktuelle Simulationszeit speichern
3. next_x = Zielposition speichern
4. next_t = aktuelle Simulationszeit + duration speichern
5. state_move = "moving_x"
6. yield self.hold(duration)
7. state_move = "waiting"
8. x = next_x endgültig speichern
9. Generator endet
```

## move_y(next_y, speed)

`move_y()` besitzt denselben Ablauf für die Y-Achse:

```python
def move_y(self, next_y: float, speed: float):
    duration = abs(next_y - self.y) / speed
    self.t = self.env.now()
    self.next_y = next_y
    self.next_t = self.env.now() + duration
    self.state_move.set("moving_y")
    yield self.hold(duration)
    self.state_move.set("waiting")
    self.y = self.next_y
```

Konkretes Beispiel:

```text
Simulationszeit       = 10
aktuelle Position y   = -1
Zielposition next_y   = 3
speed                 = 1
duration              = |-1 - 3| / 1 = 4

t = 10
next_t = 14
state_move = "moving_y"
```

Bei `yield self.hold(4)` passiert:

```text
t = 10
└── dieser Roboterprozess wird bis t = 14 eingeplant und unterbrochen

t = 10 bis 14
├── andere Roboter können sich bewegen
├── Maschinen können Jobs bearbeiten
├── Jobs können aktiviert werden
└── die SimulationBridge kann Ereignisse verarbeiten

t = 14
├── move_y() läuft hinter yield weiter
├── state_move = "waiting"
└── y = 3 wird als endgültige Position gespeichert
```

Die Animation ruft zwischen `t = 10` und `t = 14` immer wieder `y_func()` auf
und zeigt dadurch die Zwischenpositionen.

## move_z(next_z, speed)

`move_z()` besitzt denselben Ablauf für die Z-Achse:

```text
duration berechnen
→ Start- und Zieldaten speichern
→ state_move = "moving_z"
→ yield hold(duration)
→ state_move = "waiting"
→ z = next_z endgültig speichern
```

Die Methode wird insbesondere für diese Bewegungen verwendet:

```text
z = 2.5 → z = 1.25
└── Roboter zu einem Store absenken

z = 1.25 → z = 2.5
└── Roboter wieder auf Transporthöhe anheben
```

## Was macht self.hold(duration)?

`self.hold(duration)` erzeugt eine Salabim-Anforderung. Erst durch `yield` wird
diese Anforderung an den Scheduler übergeben:

```python
yield self.hold(duration)
```

```text
self.hold(duration)
└── Anforderung: diesen Komponentenprozess für duration Simulationszeit warten

yield
└── Anforderung an Salabim übergeben und Prozess unterbrechen

Salabim-Scheduler
├── plant die Komponente für env.now() + duration ein
├── führt inzwischen andere anstehende Ereignisse aus
└── aktiviert den Prozess am geplanten Zeitpunkt wieder
```

`hold()` blockiert daher weder Python für reale Stunden noch die gesamte
Simulation. Es verschiebt nur die Fortsetzung dieser Komponente auf einen
späteren Simulationszeitpunkt.

## utilization()

Die Methode berechnet den Anteil der Simulationszeit, in dem sich der Roboter
bewegt hat.

```python
moving = moving_x + moving_y + moving_z
total = moving + waiting
utilization = moving / total
```

Als Formel:

```text
                 moving_x + moving_y + moving_z
utilization = ─────────────────────────────────────
              waiting + moving_x + moving_y + moving_z
```

Beispiel:

```text
waiting  = 6
moving_x = 1
moving_y = 2
moving_z = 1

moving = 4
total  = 10
utilization = 4 / 10 = 0.4 = 40 %
```

Wenn noch keine Zustandszeit aufgezeichnet wurde und `total == 0` gilt, gibt
die aktuelle Implementierung `1` zurück.

## printStatistics()

Die Methode liest aktuell formatierte Texte für `state_move` und `state_load`
und erzeugt die konfigurierte Einrückung:

```python
move_output = toString(self.state_move)
load_output = toString(self.state_load)
```

In der aktuellen Implementierung werden diese Werte anschließend nicht
ausgegeben oder zurückgegeben. Die Methode hat daher derzeit keine sichtbare
Ausgabe.

## plot(legend=False)

Die Methode erstellt mit Matplotlib ein Balkendiagramm der Zustandszeiten:

```text
Loaded
Empty
Waiting
Moving_x
Moving_y
Moving_z
```

Für jeden Zustand wird über `value_duration(...)` die bisher verbrachte
Simulationszeit gelesen. `legend=True` blendet zusätzlich die Legende ein.

## Beziehung zur SimulationBridge

`SimRobot` selbst registriert sich nicht bei der Bridge und fordert keine
Aktionen an. Das erledigen seine konkreten Unterklassen:

```text
SimRobot
└── gemeinsame Bewegung und Animation
    │
    ├── SimRobotMain
    │   └── registriert sich und fordert Main-Robot-Aktionen an
    │
    └── SimRobotCorridorArm
        └── registriert sich und fordert Corridor-Arm-Aktionen an
```

Die Policy erhält keine Referenz auf `SimRobot`. Sie sieht ausschließlich die
von `SimulationObjectObserver` erzeugten ID-basierten Zustandsdaten der
konkreten Roboterkomponente.

