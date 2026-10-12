# SimRobotMain

Python-Datei: `sources/SpineML/Simulation/SimRobotMain.py`

Basisklasse: `sources/SpineML/Simulation/SimRobot.py`

## Position im Ablauf

```text
SimRobotMain
├── zentraler Transportroboter eines Layouts
├── transportiert Jobs zwischen Start-/Endlager und Corridors
└── kommuniziert aktiv mit der SimulationBridge
    │
    ▼
bridge.request_action(self)
└── Main-Roboter wird als wartend markiert und löst PolicyTrigger aus
    │
    ▼
PolicyObservation → GeneratorSelectorPolicy → PolicyDecision
    │
    ▼
SimulationBridge
└── validiert, löst IDs auf und erzeugt SimulationAction
    │
    ▼
persönlicher Action-Store des SimRobotMain
    │
    ▼
SimRobotMain.process()
└── führt pick_main_robot oder place_main_robot aus
```

`SimRobotMain` ist ein echtes Salabim-Simulationsobjekt. Die Policy sieht nur
die ID `"Main robot"` und das reine Dictionary aus
`SimulationObjectObserver.observe_main_robot()`.

## __init__()

Der Konstruktor erzeugt und verbindet den Main-Roboter mit Layout, Szenario,
Stores, Corridors und Bridge.

```python
def __init__(
    self,
    layout,
    scenario,
    store_start,
    store_end,
    sim_corridors,
    bridge,
    y,
    z,
    *args,
    **kwargs,
):
```

### Eingaben


| Parameter       | Konkretes Beispiel                      | Bedeutung                      |
| ----------------- | ----------------------------------------- | -------------------------------- |
| `layout`        | `layout_1`                              | echte Layout-Konfiguration     |
| `scenario`      | `scenario_1`                            | echte Szenario-Konfiguration   |
| `store_start`   | `Store (start)`                         | echtes Startlager              |
| `store_end`     | `Store (end)`                           | echtes Endlager                |
| `sim_corridors` | `[SimCorridor (simcorridor.0)]`         | Laufzeit-Corridors des Layouts |
| `bridge`        | `SimulationBridge (simulationbridge.0)` | gemeinsame SimulationBridge    |
| `y`             | `2.5`                                   | anfängliche Y-Position        |
| `z`             | `2.5`                                   | anfängliche Z-Position        |

### 1. Basisklasse SimRobot initialisieren

```python
super().__init__("Main robot", 0, 0, y, z, "red", *args, **kwargs)
```

Die Werte werden positionsbezogen an `SimRobot` übergeben:

```text
label  = "Main robot"
indent = 0
x      = 0
y      = übergebene Startposition
z      = übergebene Startposition
color  = "red"
```

Die Basisklasse erzeugt dabei unter anderem:

```text
x / y / z
└── aktuelle Position

next_x / next_y / next_z
└── nächste Zielposition für die Animation

t / next_t
└── Anfangs- und Endzeit der animierten Bewegung

state_move
└── anfänglich "waiting"

state_load
└── anfänglich "empty"

rote Animate3dBox
└── sichtbarer Körper des Main-Roboters
```

### 2. Übergebene Beziehungen speichern

```python
self.layout = layout
self.scenario = scenario
self.bridge = bridge
self.store_start = store_start
self.store_end = store_end
self.sim_corridors = sim_corridors
```

Hier werden echte Konfigurations- und Simulationsobjekte gespeichert. Sie
bleiben auf der Seite des Simulationskerns und werden nicht direkt an die
Policy weitergegeben.

### 3. Anfangszustand der Ladung

```python
self.current_job: SimOrderJob | None = None
```

```text
current_job = None
└── Main-Roboter transportiert noch keinen Job

current_job = SimOrderJob (...)
└── Main-Roboter ist mit genau diesem Job beladen
```

### 4. Bei der Bridge registrieren

```python
self.bridge.register(
    self.label,
    self,
    stores=[self.store_start, self.store_end],
)
```

Nach Abschluss von `__init__()` existiert damit ein leerer, roter
`SimRobotMain`, der unter der Policy-ID `"Main robot"` registriert ist und über
einen persönlichen Action-Store mit der Bridge kommunizieren kann.

## Registrierung

```python
self.bridge.register(
    self.label,
    self,
    stores=[self.store_start, self.store_end],
)
```

Da die Basisklasse mit `label="Main robot"` initialisiert wird, entstehen:

```text
Policy-ID
└── "Main robot"

Policy-ID → Simulationsobjekt
└── "Main robot" → SimRobotMain (simrobotmain.0)

Simulationsobjekt → Policy-ID
└── SimRobotMain (simrobotmain.0) → "Main robot"

Simulationsobjekt → Action-Store
└── SimRobotMain (simrobotmain.0) → persönlicher Action-Store

Policy-Store-ID → echter Store
├── "start" → start_store
└── "end"   → end_store
```

## Wichtige Attribute

```text
layout
└── Layout und Corridor-Reihenfolge

scenario
└── aktuelles Simulationsszenario

store_start / store_end
└── echte Salabim-Stores des Layouts

sim_corridors
└── echte SimCorridor-Objekte

current_job
└── aktuell transportierter SimOrderJob oder None

state_move
└── waiting, moving_x, moving_y oder moving_z

state_load
└── empty oder loaded
```

## Was die Policy vom Main-Roboter sieht

`SimulationObjectObserver.observe_main_robot()` liest den echten
`SimRobotMain` auf der Simulationsseite und erzeugt daraus ein Dictionary mit
IDs und reinen Zustandsdaten. Die Policy erhält keine Referenz auf den echten
Roboter, auf `SimOrderJob` oder auf Salabim-Stores.

```text
states_by_id
└── object_id = "Main robot"
    └── object_state
        ├── object_type = "main_robot"
        ├── object_id = "Main robot"
        ├── time
        ├── layout_id / scenario_id
        ├── x / y / z
        ├── move_state
        ├── load_state
        ├── is_loaded / is_empty / is_moving
        ├── current_job_summary
        ├── current_job_id
        ├── next_operation_id
        ├── next_machine_id
        ├── next_corridor_id
        ├── next_machine_side
        ├── start_storage
        ├── end_storage
        ├── corridor_storages
        └── is_waiting_for_action
```

Konkreter verkürzter Zustand eines leeren, wartenden Main-Roboters:

```python
{
    "object_type": "main_robot",
    "object_id": "Main robot",
    "time": 11.0,
    "layout_id": "Beispiellayout",
    "scenario_id": "Beispielszenario",
    "x": 0,
    "y": 0,
    "z": 2.5,
    "move_state": "waiting",
    "load_state": "empty",
    "is_loaded": False,
    "is_empty": True,
    "is_moving": False,
    "current_job_summary": None,
    "current_job_id": None,
    "next_operation_id": None,
    "next_machine_id": None,
    "start_store_id": "start",
    "end_store_id": "end",
    "start_storage": {
        "store_id": "start",
        "count": 1,
        "job_ids": ["Order 1.1:0"],
        "has_items": True,
    },
    "end_storage": {
        "store_id": "end",
        "count": 0,
        "job_ids": [],
        "has_capacity": True,
    },
    "corridor_storages": [],
    "is_waiting_for_action": True,
}
```

`is_waiting_for_action` wird von der `SimulationBridge` ergänzt. Es stammt
nicht aus `observe_main_robot()`.

## Positions- und Bewegungsmethoden

Diese Methoden stehen im Code zwischen `__init__()` und `process()` und
berechnen beziehungsweise führen die Bewegungen des Main-Roboters aus.

### calculate_storage_y_position()

```python
def calculate_storage_y_position(self) -> float:
    corridor_count = len(self.layout.corridors)
    return 2 + corridor_count / 1.15
```

Die Methode hat keine Eingabeparameter. Sie verwendet die Anzahl der Corridors
des gespeicherten Layouts und gibt den Y-Abstand der Start- und Endlager vom
Layoutzentrum zurück.

Beispiel mit einem Corridor:

```text
corridor_count = 1
storage_y = 2 + 1 / 1.15
storage_y ≈ 2.87
```

Dieser positive Abstand wird für beide Lager verwendet:

```text
Startlager → y ≈ -2.87
Endlager   → y ≈ +2.87
```

### calculate_corridor_y_position(corridor_index)

```python
def calculate_corridor_y_position(self, corridor_index: int) -> float:
    corridor_count = len(self.layout.corridors)
    return (corridor_index + 0.5 - corridor_count / 2) * 2
```

Eingabe ist der nullbasierte Index eines Corridors. Ausgabe ist dessen
Y-Position.

Beispiel mit zwei Corridors:

```text
corridor_index = 0 → y = (0 + 0.5 - 2 / 2) × 2 = -1
corridor_index = 1 → y = (1 + 0.5 - 2 / 2) × 2 = +1
```

Die Corridors liegen dadurch symmetrisch um `y = 0`.

### move_to_start_storage(speed)

```python
def move_to_start_storage(self, speed: float):
    yield from self.move_y(-self.calculate_storage_y_position(), speed)
```

Die Methode berechnet die negative Lagerposition und bewegt den Roboter mit der
von Evaluator und Selector ausgewählten Geschwindigkeit aus dem Aktionspayload
zum Startlager.

```text
calculate_storage_y_position() = 2.87
        ↓
move_y(next_y=-2.87, speed=movement_speed)
```

`move_y()` ist ein Generator, weil die Methode ein `yield` enthält.
`yield from` führt diesen Generator vollständig aus. Der aufrufende
Roboterprozess läuft erst weiter, wenn `move_y()` beendet ist. Dabei ist nur
dieser Roboterprozess blockiert; andere Simulationskomponenten laufen weiter.

### move_to_corridor_storage(sim_corridor, corridor_index, speed)

```python
def move_to_corridor_storage(
    self,
    sim_corridor,
    corridor_index,
    speed,
):
    y = self.calculate_corridor_y_position(corridor_index)
    if y != self.y:
        yield from self.move_y(y, speed)
```

```text
sim_corridor
└── echter SimCorridor des Ziels

corridor_index
└── Index dieses Corridors in self.sim_corridors

speed
└── Geschwindigkeit der Bewegung
```

Nur wenn Ziel- und aktuelle Y-Position verschieden sind, wird eine Bewegung
ausgeführt. Befindet sich der Roboter bereits vor dem Corridor, vergeht keine
zusätzliche Bewegungszeit.

### move_to_end_storage(speed)

```python
def move_to_end_storage(self, speed: float):
    yield from self.move_y(self.calculate_storage_y_position(), speed)
```

Der Roboter fährt mit der im Aktionspayload enthaltenen Geschwindigkeit zur
positiven Lagerposition des Endlagers.

### move_down_to_storage(speed)

```python
def move_down_to_storage(self, speed):
    yield from self.move_z(1.25, speed)
```

Der Roboter senkt sich auf die feste Store-/Übergabehöhe `z = 1.25` ab. Auf
dieser Höhe nimmt er einen Job auf oder legt ihn ab.

### move_up_from_storage(speed=1.0)

```python
def move_up_from_storage(self, speed=1.0):
    yield from self.move_z(2.5, speed)
```

Der Roboter hebt sich wieder auf die feste Transporthöhe `z = 2.5`. Auf dieser
Höhe fährt er zwischen Startlager, Corridors und Endlager. Der aktuelle
Aktionsablauf übergibt immer den vom Generator erzeugten `movement_speed`-Wert.
Der Methodenstandard `1.0` ist nur ein technischer Fallback für direkte Aufrufe.

### Zusammenhang mit den geerbten Methoden

```text
SimRobotMain.move_to_start_storage()
└── SimRobot.move_y(...)

SimRobotMain.move_to_corridor_storage(...)
└── SimRobot.move_y(...)

SimRobotMain.move_to_end_storage(...)
└── SimRobot.move_y(...)

SimRobotMain.move_down_to_storage(...)
└── SimRobot.move_z(...)

SimRobotMain.move_up_from_storage(...)
└── SimRobot.move_z(...)
```

## process()

### Position im Ablauf

```text
while True
├── 1. Aktion bei Bridge anfordern
├── 2. auf SimulationAction im persönlichen Store warten
├── 3. pick_main_robot  → execute_pick_action(...)
└── 4. place_main_robot → execute_place_action(...)
```

```python
yield self.bridge.request_action(self)
action = yield self.bridge.action(self)
```

Nach der vollständigen Ausführung einer Pick- oder Place-Aktion beginnt der
nächste Schleifendurchlauf und der Roboter fordert erneut eine Entscheidung an.

Für eine Pick-Aktion ruft `process()` einen weiteren Generator auf:

```python
yield from self.execute_pick_action(action)
```

`execute_pick_action()` ist ein Generator, weil die Methode selbst `yield` und
`yield from` enthält. Das äußere `yield from` führt diesen Generator vollständig
aus. `process()` läuft erst weiter, wenn die gesamte Pick-Aktion beendet ist.

```text
process()
│
├── yield from execute_pick_action(action)
│       ├── zum Store fahren
│       │   └── yield from move_y(...)
│       │       └── yield hold(Bewegungsdauer)
│       ├── ausgewählten Job aus dem Store nehmen
│       │   └── yield from take_selected_job_from_store(...)
│       │       └── yield from_store(...)
│       ├── gegebenenfalls storage_out_time abwarten
│       ├── Roboter absenken
│       │   └── yield from move_z(...)
│       ├── current_job und state_load setzen
│       └── Roboter anheben
│           └── yield from move_z(...)
│
└── execute_pick_action() ist vollständig beendet
    └── process() beginnt den nächsten while-Durchlauf
        └── Main-Roboter fordert erneut eine Aktion an
```

`yield from` reicht dabei alle inneren Salabim-Unterbrechungen an den äußeren
Roboterprozess weiter. Nur dieser Roboterprozess wartet; andere
Simulationskomponenten können währenddessen weiterlaufen.

Die beiden `yield` haben verschiedene Aufgaben:

```text
yield self.bridge.request_action(self)
└── wartet nur, bis der PolicyTrigger erfolgreich in den Bridge-Store gelegt ist
    └── danach erreicht der Roboter sofort die nächste Codezeile

action = yield self.bridge.action(self)
└── wartet auf eine ausführbare SimulationAction im persönlichen Action-Store
    └── solange keine Aktion zugestellt wird, bleibt SimRobotMain blockiert
```

Wählt die Policy nur `wait_main_robot`, filtert die Bridge diese Wait-Aktion
vor der Zustellung heraus. Der persönliche Action-Store bleibt leer und der
Roboter wartet bei `bridge.action(self)`, bis ein späterer Zustands-Trigger eine
neue ausführbare Entscheidung ermöglicht.

## pick_main_robot

### Mögliche Quellen

```text
target_type = "start_storage"
└── Job aus dem Startlager holen

target_type = "sim_corridor_store_main"
└── Job aus dem Main-Store eines Corridors holen
```

Konkrete aufgelöste Aktion. Der gezeigte Wert `movement_speed = 1.0` ist ein
mögliches Ergebnis der Zufallsauswahl aus `(0.5, 1.0, 2.0)`:

```python
SimulationAction(
    target=sim_robot_main,
    action_type="pick_main_robot",
    payload={
        "target_type": "start_storage",
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "target_store": start_store,
        "selected_job": sim_order_job,
        "storage_out_time": 10.0,
        "movement_speed": 1.0,
    },
    # weitere Attribute
)
```

Vor der Auflösung durch die Bridge sieht dieselbe Aktion so aus:

```python
SelectedObjectAction(
    target_id="Main robot",
    action_type="pick_main_robot",
    payload={
        "target_type": "start_storage",
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "storage_out_time": 10.0,
        "movement_speed": 1.0,
    },
)
```

```text
target_id
└── Policy-ID des ausführenden Main-Roboters

action_type
└── der Main-Roboter soll einen Job aufnehmen

target_type
└── beschreibt, welche Art von Quelle angefahren wird

target_store_id
└── Policy-ID des Quell-Stores

selected_job_id
└── Policy-ID des exakt ausgewählten Jobs

storage_out_time
└── Auslagerungszeit des Quell-Stores

movement_speed
└── vom Evaluator und Selector aus den Generatorvarianten gewählter Wert
```

Die Bridge ergänzt daraus die echten Laufzeitobjekte:

```text
"target_store_id": "start"
        ↓ policy_store_id_to_simulation_store
"target_store": echter start_store

"selected_job_id": "Order 1.1:0"
        ↓ policy_object_id_to_simulation_object
"selected_job": echter SimOrderJob
```

### Ausführung

Der `SpineActionGenerator` erzeugt Varianten mit `0.5`, `1.0` und `2.0`.
Evaluator und Selector wählen eine Variante. Der Main-Roboter berechnet diesen
Wert nicht selbst, sondern liest ihn aus dem Aktionspayload.

```text
→ movement_speed aus der Policyaktion lesen
→ mit movement_speed zum Ziel-Store fahren
→ exakt den von der Policy gewählten Job aus dem Store nehmen
→ optional storage_out_time warten
→ mit derselben movement_speed zum Store absenken
→ current_job = ausgewählter Job
→ state_load = "loaded"
→ mit derselben movement_speed wieder anheben
```

`take_selected_job_from_store()` stammt aus `SimRobot`. Die Methode prüft, ob
das aufgelöste `selected_job`-Objekt noch im echten `target_store` liegt.

### Vollständige Reihenfolge von execute_pick_action()

```text
1. target_type, echten target_store und movement_speed aus dem Payload lesen
        ↓
2. Zielposition auswählen und mit movement_speed anfahren
   ├── start_storage → zum Startlager fahren
   └── sim_corridor_store_main → zum betreffenden Corridor fahren
        ↓
3. exakt selected_job aus target_store entnehmen
        ↓
4. optional storage_out_time mit yield hold(...) abwarten
        ↓
5. movement_speed aus der Policyaktion weiterverwenden
        ↓
6. Roboter zum Store absenken
        ↓
7. current_job = job
        ↓
8. state_load = "loaded"
        ↓
9. Roboter wieder anheben
        ↓
10. Methode endet; process() fordert die nächste Aktion an
```

Die gefilterte Store-Anforderung lautet sinngemäß:

```python
job = yield self.from_store(
    target_store,
    filter=lambda item, selected_job=selected_job: item is selected_job,
)
```

Der Filter nimmt nicht irgendeinen Job. Nur das Objekt, das mit
`selected_job` identisch ist, erfüllt `item is selected_job`.

## place_main_robot

Eine Place-Aktion ist nur möglich, wenn `current_job` nicht `None` ist.

### Konkrete Place-Aktion zum Corridor

Auch hier ist `movement_speed = 1.0` nur ein konkretes mögliches Ergebnis der
Zufallsauswahl; eine andere erzeugte Aktion kann `0.5` oder `2.0` enthalten.

Policyseite, nur mit IDs und reinen Werten:

```python
SelectedObjectAction(
    target_id="Main robot",
    action_type="place_main_robot",
    payload={
        "target_type": "sim_corridor_store_arm_input",
        "selected_operation_id": "Rohes Werkstück schleifen",
        "selected_machine_id": "Schleifmaschine A",
        "sim_corridor_id": "Bearbeitungskorridor",
        "target_store_id": "Bearbeitungskorridor left",
        "storage_in_time": 3,
        "movement_speed": 1.0,
    },
)
```

Nach der Auflösung durch die Bridge enthält die `SimulationAction` zusätzlich:

```python
payload={
    "target_type": "sim_corridor_store_arm_input",
    "selected_operation_id": "Rohes Werkstück schleifen",
    "selected_machine_id": "Schleifmaschine A",
    "sim_corridor_id": "Bearbeitungskorridor",
    "target_store_id": "Bearbeitungskorridor left",
    "storage_in_time": 3,
    "movement_speed": 1.0,

    # echte, ausschließlich simulationsseitige Objekte
    "selected_operation": operation_rohes_werkstueck_schleifen,
    "selected_machine": schleifmaschine_a,
    "sim_corridor": sim_bearbeitungskorridor,
    "target_store": bearbeitungskorridor_left_store,
}
```

### Ziel: Corridor-Arm-Eingang

```text
target_type = "sim_corridor_store_arm_input"
→ selected_operation und selected_machine in den Job übernehmen
→ zum Corridor fahren
→ absenken
→ optional storage_in_time warten
→ Job mit queue_priority in linken oder rechten Corridor-Store legen
→ current_job = None
→ state_load = "empty"
→ anheben
```

### Ziel: Endlager

```text
target_type = "end_storage"
→ zum Endlager fahren und absenken
→ selected_operation und selected_machine des Jobs zurücksetzen
→ job.mark_finished()
→ optional storage_in_time warten
→ Job in end_store legen
→ current_job = None
→ state_load = "empty"
→ anheben
```

`job.mark_finished()` setzt die Fertigstellungszeit und aktiviert den zuvor
passivierten `SimOrderJob`, damit dieser die abschließende `complete_job`-Aktion
anfordern kann.

### Vollständige Reihenfolge von execute_place_action()

```text
1. current_job übernehmen
2. target_type und echten target_store aus dem Payload lesen
3. movement_speed aus der Policyaktion lesen
        ↓
4. Zielzweig auswählen
```

Corridor-Zweig:

```text
target_type = "sim_corridor_store_arm_input"
├── echten SimCorridor und seinen Index bestimmen
├── selected_operation in den Job schreiben
├── selected_machine in den Job schreiben
├── zum Corridor fahren
├── absenken
├── optional storage_in_time abwarten
├── Job mit queue_priority in target_store legen
├── current_job = None
├── state_load = "empty"
├── anheben
└── return beendet die Methode
```

Endlager-Zweig:

```text
target_type = "end_storage"
├── zum Endlager fahren
├── absenken
├── selected_operation = None
├── selected_machine = None
├── job.mark_finished()
│   ├── completed_time = aktuelle Simulationszeit
│   └── passiven SimOrderJob aktivieren
├── optional storage_in_time abwarten
├── Job mit queue_priority in end_store legen
├── current_job = None
├── state_load = "empty"
├── anheben
└── return beendet die Methode
```

### Warum selected_operation und selected_machine im Job gespeichert werden

Die Policy übergibt nur IDs. Die Bridge löst sie in echte
Konfigurationsobjekte auf. Der Main-Roboter schreibt diese Planung beim
Ablegen am Corridor in den echten `SimOrderJob`:

```python
job.selected_operation = action.payload["selected_operation"]
job.selected_machine = action.payload["selected_machine"]
```

Danach können Corridor-Roboter und Maschine erkennen, wohin der Job gehört und
welche Operation als Nächstes ausgeführt werden soll. Die Policy greift dabei
nicht direkt auf den echten Job zu.

## Geerbte Bewegung aus SimRobot

```text
move_x / move_y / move_z
├── berechnen Wegdauer = Strecke / Geschwindigkeit
├── setzen state_move auf moving_x, moving_y oder moving_z
├── yield hold(dauer)
└── setzen state_move danach wieder auf waiting
```

Die Animationsfunktionen interpolieren zwischen aktueller und nächster
Position. Die konkreten Roboter lesen `movement_speed` aus der von der Bridge
zugestellten `SimulationAction` und übergeben diesen Wert an `move_x()`,
`move_y()` oder `move_z()`.

### movement_speed und Bewegungsdauer

```text
Bewegungsdauer
└── absoluter Weg / Geschwindigkeit
```

Der ActionGenerator auf der Policyseite liefert `movement_speed`, aber nicht die
Dauer. Der Simulationskern
kennt die festen Positionen, berechnet daraus die Strecke und anschließend:

```text
Bewegungsdauer = Strecke / movement_speed
```

Der aktuelle `SpineActionGenerator` trägt als Baselinewert `1.0` in jede
ausführbare Roboteraktion ein. Ein späterer heuristischer oder RL-Selector kann
einen anderen positiven Wert wählen.

Während `move_y()` oder `move_z()` läuft, werden Startposition, Zielposition,
Startzeit und Zielzeit gespeichert. Die Animationsfunktion berechnet daraus
für jeden Darstellungszeitpunkt eine Zwischenposition.

## Gesamter Lebenszyklus einer Main-Roboter-Aktion

```text
Main-Roboter ist leer
    ↓
request_action()
    ↓
PolicyTrigger → Snapshot → PolicyDecision
    ↓
pick_main_robot
    ↓
Job aufnehmen; current_job gesetzt; state_load = "loaded"
    ↓
request_action()
    ↓
PolicyTrigger → Snapshot → PolicyDecision
    ↓
place_main_robot
    ├── Corridor: nächste Operation und Maschine im Job speichern
    └── Endlager: Job als fertig markieren
    ↓
Job ablegen; current_job = None; state_load = "empty"
    ↓
request_action()
```

## Entkopplungsgrenze

```text
Policy
└── kennt "Main robot", Store-IDs und Job-IDs
    │
    ▼
SimulationBridge
└── löst IDs in sim_robot_main, Stores und SimOrderJob auf
    │
    ▼
SimRobotMain
└── arbeitet ausschließlich mit echten Laufzeitobjekten
```

