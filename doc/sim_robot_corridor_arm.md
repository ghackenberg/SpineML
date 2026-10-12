# SimRobotCorridorArm

Python-Datei: `sources/SpineML/Simulation/SimRobotCorridorArm.py`

Basisklasse: `sources/SpineML/Simulation/SimRobot.py`

## Position im Ablauf

```text
SimRobotMain
└── legt einen Job in einen linken oder rechten Corridor-Eingangsstore
    │
    ▼
SimRobotCorridorArm
├── transportiert Jobs zwischen Corridor-Stores und Maschinen
├── kann Jobs zwischen den beiden Armen beziehungsweise zum Main-Store geben
└── kommuniziert aktiv mit der SimulationBridge
    │
    ▼
request_action → Policyentscheidung → SimulationAction
    │
    ▼
pick_corridor_arm_robot oder place_corridor_arm_robot
```

Jeder Corridor besitzt einen linken und einen rechten Arm-Roboter. Die Policy
sieht beispielsweise:

```text
"CorridorArmRobot:Corridor 1.1:left"
"CorridorArmRobot:Corridor 1.1:right"
```

### Bedeutung der mehrteiligen ID

```text
CorridorArmRobot:Corridor 1.1:left
                  │       │ │   └── linker Arm des Corridors
                  │       │ └── erster Corridor innerhalb des Layouts
                  │       └── erstes Layout
                  └── Konfigurationsobjekt ist ein Corridor
```

Die Zahlen gehören zum Namen des konfigurierten Corridors:

```text
Corridor 1.1
         │ │
         │ └── Corridor Nummer 1 innerhalb von Layout 1
         └── Layout Nummer 1

Corridor 1.2
└── Corridor Nummer 2 innerhalb von Layout 1

Corridor 2.1
└── Corridor Nummer 1 innerhalb von Layout 2
```

Der letzte Teil ist keine weitere Nummer:

```text
:left  → linker Corridor-Arm-Roboter
:right → rechter Corridor-Arm-Roboter
```

Damit bedeutet die vollständige ID beispielsweise:

```text
"CorridorArmRobot:Corridor 1.1:left"
└── linker Arm-Roboter des ersten Corridors im ersten Layout
```

## Registrierung

```python
self.bridge.register(
    f"CorridorArmRobot:{self.corridor.name}:{self.direction}",
    self,
)
```

Beispiel:

```text
Policy-ID
└── "CorridorArmRobot:Corridor 1.1:left"

echtes Objekt
└── SimRobotCorridorArm (simrobotcorridorarm.0)

persönlicher Action-Store
└── wird von bridge.register(...) erzeugt
```

Der Roboter registriert hier keine Stores. Die Corridor-Stores werden vom
`SimCorridor` und die Maschinen-Stores von den `SimMachine`-Objekten bei der
Bridge registriert.

### Wer registriert welche Stores?

Die echten Stores werden nicht bei der Policy registriert. Sie werden nur in
der `SimulationBridge` registriert. Die Policy sieht anschließend lediglich
deren IDs und beobachtete Zustandsdaten.

```text
SimCorridor
└── bridge.register_corridor(...)
    ├── "Corridor 1.1 main"  → echter store_main
    ├── "Corridor 1.1 left"  → echter store_left
    └── "Corridor 1.1 right" → echter store_right

SimMachine
└── bridge.register(..., stores=[store_in, store_out])
    ├── "Machine 1.1.1 in"  → echter store_in
    └── "Machine 1.1.1 out" → echter store_out

SimRobotMain
└── bridge.register(..., stores=[store_start, store_end])
    ├── "start" → echter Start-Store
    └── "end"   → echter End-Store

SimRobotCorridorArm
└── registriert keinen Store
```

Der `SimCorridor` führt konkret aus:

```python
bridge.register_corridor(
    corridor.name,
    self,
    stores=[self.store_main, self.store_left, self.store_right],
)
```

Die Bridge speichert dabei für jeden Store die Zuordnung:

```text
policy_store_id_to_simulation_store
├── "Corridor 1.1 main"  → Store (Corridor 1.1 main)
├── "Corridor 1.1 left"  → Store (Corridor 1.1 left)
└── "Corridor 1.1 right" → Store (Corridor 1.1 right)
```

Die beiden Arm-Roboter bekommen beim Erzeugen nur Referenzen auf diese bereits
existierenden Stores:

```text
linker Arm
├── store_in       = Corridor 1.1 left
├── store_out_arm  = Corridor 1.1 right
└── store_out_main = Corridor 1.1 main

rechter Arm
├── store_in       = Corridor 1.1 right
├── store_out_arm  = Corridor 1.1 left
└── store_out_main = Corridor 1.1 main
```

Dadurch werden die drei Corridor-Stores nur einmal durch `SimCorridor`
registriert und nicht noch einmal durch beide Arm-Roboter.

## Wichtige Attribute und Stores

```text
corridor
└── zugehörige Corridor-Konfiguration

direction
└── "left" oder "right"

dx
└── Richtungsfaktor der Corridor-Seite
    ├── linker Arm  → dx = +1
    └── rechter Arm → dx = -1

machines / sim_machines
└── Konfigurationsmaschinen und echte SimMachine-Objekte dieser Seite

store_in
└── Eingangsstore dieses Arms

store_out_arm
└── Eingangsstore des gegenüberliegenden Arms

store_out_main
└── gemeinsamer Corridor-Main-Store

current_job
└── aktuell transportierter SimOrderJob oder None
```

## Positions- und Bewegungsmethoden

Der Corridor-Arm bewegt sich horizontal auf der X-Achse und vertikal auf der
Z-Achse. Die Zielpositionen bleiben im Simulationskern festgelegt. Die
Geschwindigkeit `speed` stammt aus `movement_speed` der Policyaktion.

### compute_machine_x(machine_num)

```python
def compute_machine_x(self, machine_num: int) -> float:
    return (3 + machine_num * 2) * self.dx
```

Die Methode berechnet die feste X-Position einer Maschine auf der Seite dieses
Arms.

```text
machine_num
└── nullbasierter Index der Maschine in self.sim_machines

dx
└── Richtung und Grundabstand des Arms
    ├── dx = +1 → linker Arm und positive X-Positionen
    └── dx = -1 → rechter Arm und negative X-Positionen
```

Konkretes Beispiel mit `dx = 1.0`:

```text
machine_num = 0 → (3 + 0 · 2) · 1.0 = 3.0
machine_num = 1 → (3 + 1 · 2) · 1.0 = 5.0
machine_num = 2 → (3 + 2 · 2) · 1.0 = 7.0
```

Spiegelbildliches Beispiel für die erste Maschine:

```text
linker Arm mit dx = +1
└── (3 + 0 · 2) · (+1) = +3

rechter Arm mit dx = -1
└── (3 + 0 · 2) · (-1) = -3
```

Dadurch verwendet dieselbe Positionsformel für beide Arme spiegelbildliche
Maschinenpositionen auf den beiden Corridor-Seiten.

Die Methode bewegt den Roboter noch nicht. Sie gibt nur die berechnete
X-Koordinate als `float` zurück.

### move_to_corridor_storage_x(speed)

```python
def move_to_corridor_storage_x(self, speed: float):
    if self.x != self.dx:
        yield from self.move_x(self.dx, speed)
```

Der Name `corridor_storage` wird verwendet, weil diese X-Position für die
seitlichen Übergabe-Stores `store_in` und `store_out_arm` gilt. Der zentrale
`store_out_main` wird bei einer Place-Aktion separat auf `x = 0.0` angefahren.

Der Methodenname endet mit `_x`, weil sie den Arm nur horizontal zu dieser
gemeinsamen Corridor-Store-Position fährt. Das Absenken erfolgt danach separat
durch `move_down_to_corridor_storage()`.

Die seitlichen Corridor-Stores liegen für den Arm an der festen X-Position
`self.dx`. Der zentrale Main-Store liegt bei `x = 0.0`.
Befindet sich der Arm bereits dort, wird keine Bewegung ausgeführt. Andernfalls führt
`yield from` den Generator `move_x()` vollständig aus. Erst nach dem Ende der
horizontalen Bewegung läuft die aufrufende Methode weiter.

### move_to_machine_storage(machine_num, speed)

```python
def move_to_machine_storage(self, machine_num: int, speed: float):
    x = self.compute_machine_x(machine_num)
    if self.x != x:
        yield from self.move_x(x, speed)
```

```text
machine_num
└── bestimmt, zu welcher Maschine gefahren wird

compute_machine_x(machine_num)
└── liefert deren feste X-Position

move_x(x, speed)
└── bewegt den Arm mit der Geschwindigkeit aus der Policyaktion
```

Auch hier wird keine Bewegung erzeugt, wenn sich der Arm bereits an der
berechneten Maschinenposition befindet.

### move_down_to_corridor_storage(speed)

```python
def move_down_to_corridor_storage(self, speed: float):
    yield from self.move_z(1.25, speed)
```

Der Arm senkt sich auf die feste Corridor-Store-Höhe `z = 1.25`. Dort nimmt er
einen Job aus `store_in`, `store_out_arm` oder `store_out_main` beziehungsweise
legt ihn in einem dieser Corridor-Stores ab.

### move_down_to_machine_storage(speed)

```python
def move_down_to_machine_storage(self, speed: float):
    yield from self.move_z(1.5, speed)
```

Der Arm senkt sich auf die feste Maschinen-Store-Höhe `z = 1.5`. Dort nimmt er
einen Job aus dem Ausgang einer Maschine oder legt ihn in deren Eingang.

### move_up_from_storage(speed)

```python
def move_up_from_storage(self, speed: float):
    yield from self.move_z(2.5, speed)
```

Nach Pick oder Place hebt sich der Arm wieder auf die feste Transporthöhe
`z = 2.5`. Auf dieser Höhe fährt er horizontal zwischen Übergabe- und
Maschinenpositionen.

`speed` ist ein Pflichtparameter. Im Aktionsablauf wird die durch Evaluator und
Selector aus den Generatorvarianten `0.5`, `1.0` und `2.0` ausgewählte
`movement_speed` aus dem Policy-Aktionspayload übergeben.

### Bedeutung von yield from

Alle `move_to_...`, `move_down_...` und `move_up_...`-Methoden sind Generatoren,
weil sie `yield from` enthalten:

```text
execute_pick_action() oder execute_place_action()
        │
        └── yield from move_to_machine_storage(...)
                    │
                    └── yield from move_x(...)
                                │
                                └── yield hold(Bewegungsdauer)
```

`yield from` bedeutet hier: Die aufrufende Methode wartet, bis die komplette
Teilbewegung beendet ist. Während `hold(Bewegungsdauer)` vergeht
Simulationszeit; andere Salabim-Komponenten können in dieser Zeit ausgeführt
werden.

## process()

### Position im Ablauf

```text
while True
├── bridge.request_action(self)
├── action = bridge.action(self)
├── pick_corridor_arm_robot  → execute_pick_action(...)
└── place_corridor_arm_robot → execute_place_action(...)
```

Nach jeder ausgeführten Aktion fordert der Arm erneut eine Aktion an.

## execute_pick_action(action)

Diese Generator-Methode führt eine zuvor von der Policy ausgewählte
`pick_corridor_arm_robot`-Aktion im Simulationskern aus.

Zu Beginn liest sie die bereits von der Bridge aufgelösten Aktionsdaten:

```python
target_type = action.payload["target_type"]
target_store = action.payload["target_store"]
movement_speed = action.payload["movement_speed"]
```

```text
action
└── ausführbare SimulationAction
    ├── target_type
    │   └── beschreibt, von welcher Store-Art aufgenommen wird
    ├── target_store
    │   └── echter Salabim-Store, von der Bridge aufgelöst
    ├── selected_job
    │   └── echter SimOrderJob, von der Bridge aufgelöst
    └── movement_speed
        └── vom ActionGenerator erzeugte Bewegungsgeschwindigkeit
```

Je nach `target_type` wird genau einer der folgenden beiden Pick-Zweige
ausgeführt.

### Quelle: Corridor-Eingangsstore

```text
target_type = "sim_corridor_store_arm_input"
→ zum Übergabe-Store fahren
→ ausgewählten Job aus target_store nehmen
→ optional storage_out_time warten
→ absenken
→ current_job setzen und state_load = "loaded"
→ anheben
→ return beendet execute_pick_action()
```

### Quelle: Maschinen-Ausgang

```text
target_type = "machine_output_storage"
→ sim_machine aus dem aufgelösten Payload lesen
→ Maschinenposition bestimmen und dorthin fahren
→ ausgewählten Job aus machine.store_out nehmen
→ absenken und Job laden
→ sim_machine.state = "waiting"
→ anheben
→ return beendet execute_pick_action()
```

Ist der `target_type` keiner der beiden unterstützten Werte, erreicht die
Methode das abschließende `return` und beendet sich ohne `ValueError`.

## execute_place_action(action)

Diese Generator-Methode führt eine von der Policy ausgewählte
`place_corridor_arm_robot`-Aktion aus. Sie kann nur tatsächlich ablegen, wenn
der Arm einen `current_job` trägt.

```python
if self.current_job is None:
    return

job = self.current_job
target_type = action.payload["target_type"]
target_store = action.payload["target_store"]
movement_speed = action.payload["movement_speed"]
```

```text
current_job = None
└── Methode wird sofort beendet

current_job = SimOrderJob
└── Job, Zieltyp, echter Ziel-Store und Geschwindigkeit werden verwendet
```

Eine Place-Aktion verlangt einen geladenen `current_job`.

### Ziel: Maschinen-Eingang

```text
target_type = "machine_input_storage"
→ selected_operation und selected_machine in den Job übernehmen
→ zur ausgewählten SimMachine fahren
→ absenken
→ Job in machine.store_in legen
→ current_job = None und state_load = "empty"
→ anheben
→ return beendet execute_place_action()
```

### Ziel: anderer Arm oder Main-Store

```text
target_type = "sim_corridor_store_other_arm_input"
oder
target_type = "sim_corridor_store_main"

→ optional Jobplanung übernehmen
→ bei `sim_corridor_store_main` zu x = 0.0 fahren,
  sonst zum seitlichen Zugriffspunkt x = self.dx fahren
→ absenken
→ optional storage_in_time warten
→ Job in target_store legen
→ current_job = None und state_load = "empty"
→ anheben
→ return beendet execute_place_action()
```

Ist der `target_type` keiner der unterstützten Werte, beendet das letzte
`return` die Methode ohne `ValueError`.

## Konkretes Aktionsbeispiel

Im folgenden Beispiel ist `movement_speed = 1.0` ein mögliches Ergebnis der
Zufallsauswahl aus `(0.5, 1.0, 2.0)`.

```python
SimulationAction(
    target=sim_corridor_arm_left,
    action_type="place_corridor_arm_robot",
    payload={
        "target_type": "machine_input_storage",
        "target_store_id": "Machine 1.1.1 in",
        "sim_machine_id": "SimMachine:Machine 1.1.1:left",
        "selected_operation_id": "Fräsen",
        "selected_machine_id": "Machine 1.1.1",
        "movement_speed": 1.0,
        "target_store": machine_input_store,
        "sim_machine": sim_machine,
        "selected_operation": operation,
        "selected_machine": machine_configuration,
    },
    # weitere Attribute
)
```

Die ID-Felder stammen von der Policy. Die Objektfelder wurden von der Bridge
ergänzt und bleiben auf der Simulationsseite.

## Geerbte Robotikfunktionen

Aus `SimRobot` werden insbesondere verwendet:

```text
take_selected_job_from_store(...)
└── nimmt exakt das von der Policy gewählte Jobobjekt

movement_speed aus der SimulationAction
└── wird durch Evaluator und Selector aus den Generatorvarianten
    (0.5, 1.0, 2.0) gewählt und an die Bewegungsmethoden übergeben

move_x / move_z
└── simulieren Bewegung mit hold(dauer) und Bewegungszuständen
```

Die Positionen bleiben fest im Simulationskern. Der Corridor-Arm liest für
Pick und Place:

```python
movement_speed = action.payload["movement_speed"]
```

`move_x()` und `move_z()` berechnen daraus die tatsächliche Dauer:

```text
Bewegungsdauer = Strecke / movement_speed
```

## Entkopplungsgrenze

```text
PolicyObservation
└── IDs und reine Zustände des Corridor-Arms, der Stores und Jobs
    │
    ▼
PolicyDecision
└── Ziel-, Store-, Job-, Maschinen- und Operations-IDs
    │
    ▼
SimulationBridge
└── löst IDs auf
    │
    ▼
SimRobotCorridorArm
└── führt die SimulationAction mit echten Objekten aus
```

