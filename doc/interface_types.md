# InterfaceTypes.py

Python-Datei: `sources/SpineML/Control/Interface/InterfaceTypes.py`

## Aufgabe der Datei

`InterfaceTypes.py` enthält die gemeinsamen Verträge und Datentypen der Steuerungsarchitektur.

```text
InterfaceTypes.py
├── SimulationObjectObserver
├── ConfigurationObjectObserver
├── PolicyObservation
├── PolicyTrigger
├── SelectedObjectAction
├── PolicyDecision
├── SimulationAction
├── ActionGenerator
├── ActionSelector
├── policy_payload_id_mappings()
├── is_wait_action()
└── Policy
```

Die Datei enthält keine konkrete Entscheidungsstrategie. Sie legt fest, welche
Daten zwischen den Komponenten ausgetauscht werden, welche Methoden
Implementierungen anbieten müssen und wie Daten an beiden Seiten der
Bridge-Schnittstelle übersetzt werden.

## Schnittstelle in beide Richtungen

```text
Simulation → Policy
└── SimulationObjectObserver
    └── echte Salabim-Objekte → reine Dictionaries und IDs

Konfiguration → Policy
└── ConfigurationObjectObserver
    └── echte Konfigurationsobjekte → statisches ID-basiertes Modell

Policy → Simulation
└── policy_payload_id_mappings()
    └── Policy-IDs → Register mit echten Laufzeitobjekten
```

---

## Importe

```python
from __future__ import annotations
```

Typannotationen können Namen verwenden, die erst später in der Datei definiert werden.

Ein konkretes Beispiel steht in `PolicyDecision`:

```python
class PolicyDecision:
    actions: list[SelectedObjectAction]

    @classmethod
    def with_single_selected_action(
        cls,
        action: dict[str, object],
        target_id: str,
    ) -> PolicyDecision:
        return cls([...])
```

Während Python die Methodensignatur verarbeitet, wird die Klasse
`PolicyDecision` selbst gerade erst definiert und ist noch nicht
vollständig fertiggestellt. Trotzdem wird ihr Name bereits als Rückgabetyp
verwendet:

```python
-> PolicyDecision
```

Durch:

```python
from __future__ import annotations
```

wird diese Typannotation zunächst verzögert behandelt. Python muss
`PolicyDecision` an dieser Stelle nicht sofort als fertig definiertes
Klassenobjekt auswerten.

Ohne diesen Import müsste man bei entsprechenden Python-Versionen den Namen
als String schreiben:

```python
) -> "PolicyDecision":
```

Der Import betrifft nur die Verarbeitung der Typannotationen. Die eigentliche
Rückgabe bleibt ein normales `PolicyDecision`-Objekt.

```python
from abc import ABC, abstractmethod
```

- `ABC` kennzeichnet eine Klasse als abstrakte Basisklasse. Sie dient als
  Vorlage für andere Klassen.
- `@abstractmethod` kennzeichnet eine einzelne Methode, die eine konkrete
  Unterklasse implementieren muss.

Konkretes Beispiel:

```python
class ActionGenerator(ABC):
    @abstractmethod
    def generate_actions(self, observation):
        pass
```

Dabei bedeutet:

```text
ActionGenerator(ABC)
→ ActionGenerator ist eine abstrakte Basisklasse.
→ Sie dient als Vorlage für andere Klassen.

@abstractmethod
→ generate_actions() ist eine verpflichtende Methode.
→ Jede konkrete Unterklasse muss diese Methode implementieren.
```

Die konkrete Unterklasse ist in diesem Projekt:

```python
class SpineActionGenerator(ActionGenerator):
    def generate_actions(self, observation):
        ...
```

Kurz gesagt:

```text
ABC             → betrifft die gesamte Klasse
@abstractmethod → betrifft eine einzelne Methode
```

```python
from dataclasses import dataclass
```

Eine `dataclass` ist eine Klasse, deren Hauptaufgabe das Speichern von Daten ist.

Ohne `@dataclass` müsste der Konstruktor selbst geschrieben werden:

```python
class SelectedObjectAction:
    def __init__(self, target_id: str, action_type: str, payload: dict):
        self.target_id = target_id
        self.action_type = action_type
        self.payload = payload
```

Mit `@dataclass` reicht die Beschreibung der Attribute:

```python
@dataclass
class SelectedObjectAction:
    target_id: str
    action_type: str
    payload: dict
```

Python erzeugt dabei automatisch unter anderem:

```text
__init__() → Konstruktor zum Erzeugen des Objekts
__repr__() → verständliche Textdarstellung des Objekts
__eq__()   → Vergleich zweier Objekte anhand ihrer Attribute
```

Ein Objekt kann danach so erzeugt werden:

```python
action = SelectedObjectAction(
    target_id="Main robot",
    action_type="wait_main_robot",
    payload={},
)
```

Die Attribute können direkt gelesen werden:

```python
action.target_id
# "Main robot"

action.action_type
# "wait_main_robot"

action.payload
# {}
```

In `InterfaceTypes.py` wird meistens Folgendes verwendet:

```python
@dataclass(frozen=True)
```

`frozen=True` bedeutet, dass ein Attribut nach der Erzeugung des Objekts nicht
neu zugewiesen werden darf:

```python
action.action_type = "pick_main_robot"
# FrozenInstanceError
```

Wichtig: `frozen=True` macht enthaltene veränderbare Objekte nicht automatisch
vollständig unveränderbar. Das Attribut `payload` darf nicht durch ein anderes
Dictionary ersetzt werden, das bereits enthaltene Dictionary kann aber weiterhin
verändert werden:

```python
action.payload = {}
# nicht erlaubt

action.payload["job_id"] = "Order 1.1:0"
# bei einem normalen Dictionary weiterhin möglich
```

```python
from typing import Any
```

`Any` bedeutet, dass an dieser Stelle ein beliebiger Python-Datentyp erlaubt ist.

```text
Any
├── str      → Text, zum Beispiel "Main robot"
├── int      → ganze Zahl, zum Beispiel 1
├── float    → Kommazahl, zum Beispiel 2.5
├── bool     → Wahrheitswert: True oder False
├── list     → Liste, zum Beispiel ["Fräsen", "Polieren"]
├── dict     → Dictionary, zum Beispiel {"job_id": "Order 1.1:0"}
└── None     → kein vorhandener Wert
```

Beispiel aus der `ActionGenerator`-/`ActionSelector`-Schnittstelle:

```python
actions: list[dict[str, Any]]
```

Das bedeutet:

```text
list
└── enthält Action-Dictionaries
    ├── Schlüssel → immer str
    └── Wert      → Any, also ein beliebiger Python-Datentyp
```

Konkretes Payload:

```python
payload = {
    "selected_job_id": "Order 1.1:0",       # str
    "corridor_index": 0,                     # int
    "storage_in_time": 2.5,                  # float
    "downgraded": False,                     # bool
    "operation_ids": ["Fräsen", "Polieren"], # list
    "optional_value": None,                  # None
}
```

Kurz gesagt:

```text
Any = str, int, float, bool, list, dict, None oder ein anderer Python-Typ
```

```python
import salabim as sim
```

`salabim` wird unter dem lokalen Kurznamen `sim` importiert:

```text
salabim → sim
```

Der Import wird benötigt, weil `PolicyTrigger` und `SimulationAction` beide
Salabim-Komponenten sind. Beide Klassen erben von `sim.Component`:

```python
class PolicyTrigger(sim.Component):
    ...

class SimulationAction(sim.Component):
    ...
```

Das bedeutet ausgeschrieben:

```text
PolicyTrigger ist eine salabim.Component
SimulationAction ist eine salabim.Component
```

Zusätzlich wird `sim.Component` als Typ für das echte Zielobjekt einer
`SimulationAction` verwendet:

```python
target: sim.Component
```

---

# Eingehende Simulationsschnittstelle

## SimulationObjectObserver

### Position im Ablauf

Der `SimulationObjectObserver` liest echte Salabim-Simulationsobjekte und
erzeugt daraus reine, ID-basierte Dictionaries für den Policy-Snapshot.

### `_id`-Suffix und Vorbereitung für die Policy

Der `SimulationObjectObserver` bereitet die dynamischen Daten der echten
Simulationsobjekte für die Policy vor. Echte `sim.Component`-, Store-,
Maschinen- oder Operationsobjekte werden nicht an die Policy weitergegeben.
Die Policy erhält stattdessen deren IDs. Die zugehörigen Keys enden mit dem
Suffix `_id`.

```text
echtes Simulationsobjekt
└── SimulationObjectObserver
    ├── liest aktuelle Zustandswerte
    ├── gibt statt echter Objekte nur deren IDs aus
    └── erzeugt policygeeignete Dictionary-Daten
```

Beispiele:

```python
{
    "object_id": "Order 1.1:0",
    "layout_id": "Beispiellayout",
    "selected_operation_id": "Rohes Werkstück schleifen",
    "selected_machine_id": "Schleifmaschine A",
    "start_store_id": "start",
}
```

Regel:

```text
Key endet mit _id
└── Wert ist eine reine ID für die Policy
    └── kein echtes Simulations- oder Konfigurationsobjekt
```

```text
Simulationskernobjekt (Salabim: sim.Component)
        ↓
SimulationObjectObserver
(normale Python-Klasse, keine sim.Component und selbst kein Dictionary)
        ↓ erzeugt als Ausgabe
Beobachtung: dict[str, object]
(String-Schlüssel mit IDs und reinen Zustandsdaten unterschiedlicher Typen)
        ↓
SimulationBridge (Salabim: sim.Component)
```

Bei:

```python
dict[str, object]
```

bedeutet:

```text
str
→ jeder Dictionary-Schlüssel ist ein String
→ zum Beispiel "object_id", "time" oder "released"

object
→ der Wert darf ein beliebiges Python-Objekt sein
→ zum Beispiel str, int, float, bool, list, dict oder None
→ der konkrete Typ des gelesenen Wertes ist zunächst nicht genauer bekannt
```

Beispiel:

```python
observation: dict[str, object] = {
    "object_id": "Order 1.1:0",  # str
    "time": 11.0,                # float
    "number": 0,                 # int
    "released": True,            # bool
    "completed_time": None,      # None
}
```

Kurz:

```text
Simulationskernobjekt → Observer → Bridge
```

Der Observer bildet damit die eingehende Schnittstellenrichtung zur Bridge.

Sowohl die registrierten Simulationsobjekte als auch die `SimulationBridge`
erben von `sim.Component`. Sie haben aber unterschiedliche Rollen:

```text
SimMachine, SimRobotMain, SimOrderJob usw.
→ simulieren Fabrikobjekte

SimulationBridge
→ simuliert kein Fabrikobjekt
→ koordiniert die Kommunikation mit der Policy

SimulationObjectObserver
→ erbt nicht von sim.Component
→ ist selbst kein Dictionary
→ liest Simulationsobjekte und gibt pro Beobachtung ein Dictionary zurück
```

Beispiel:

```python
observation = SimulationObjectObserver.observe_simulation_object(
    sim_robot_main,
    time=11.0,
)
```

Dabei gilt:

```text
SimulationObjectObserver → Klasse
observation              → dict
```

Beispielinhalt der Ausgabe:

```python
{
    "object_type": "main_robot",
    "object_id": "Main robot",
    "time": 11.0,
    "current_job_id": None,
    "is_empty": True,
}
```

```text
SimOrderJob         → observe_order_job()            → dict
SimRobotMain        → observe_main_robot()           → dict
SimRobotCorridorArm → observe_corridor_arm_robot()   → dict
SimMachine          → observe_machine()              → dict
sim.Store           → observe_store()                → dict
```

Der allgemeine Einstieg ist:

```python
observation = SimulationObjectObserver.observe_simulation_object(
    sim_object,
    time,
)
```

Die Methode erkennt den konkreten Objekttyp und ruft die passende
Beobachtungsmethode auf. Das Ergebnis enthält das eingelesene echte
Simulationsobjekt nicht.

```text
echtes Simulationsobjekt
        ↓
SimulationObjectObserver
        ↓
object_id, Zustände, Zahlen, boolesche Werte und Store-Dictionaries
```

### Methodenübersicht

```text
SimulationObjectObserver
├── observe_simulation_object(sender, time)
├── observe_order_job(job, time)
├── observe_main_robot(robot, time)
├── observe_corridor_arm_robot(robot, time)
├── observe_machine(machine, time)
├── observe_store(store)
├── observe_job_summary(job)
└── job_id(job)
```

### `@classmethod` und `@staticmethod`

Im `SimulationObjectObserver` werden beide Varianten verwendet.

#### `@classmethod`

```python
@classmethod
def observe_simulation_object(cls, sender, time):
    return cls.observe_main_robot(sender, time)
```

Eine Klassenmethode erhält als ersten Parameter die Klasse selbst:

```text
cls = SimulationObjectObserver
```

Dadurch kann sie andere Methoden über die aktuelle Klasse aufrufen:

```python
cls.observe_order_job(...)
cls.observe_main_robot(...)
```

Das ist nützlich, wenn später eine Unterklasse von `SimulationObjectObserver`
eine Beobachtungsmethode ersetzt.

#### `@staticmethod`

```python
@staticmethod
def observe_store(store):
    return {...}
```

Eine statische Methode erhält weder ein Objekt als `self` noch die Klasse als
`cls`. Sie bekommt nur die ausdrücklich angegebenen Parameter.

```text
@classmethod
→ erster Parameter ist cls
→ kennt die aufgerufene Klasse

@staticmethod
→ kein self und kein cls
→ arbeitet nur mit den eingegebenen Parametern
```

Im aktuellen Observer gilt:

```text
observe_simulation_object() → @classmethod
    erkennt den Objekttyp und leitet an eine passende Methode weiter

observe_order_job()          → @staticmethod
observe_main_robot()         → @staticmethod
observe_corridor_arm_robot() → @staticmethod
observe_machine()            → @staticmethod
observe_store()              → @staticmethod
observe_job_summary()        → @staticmethod
job_id()                     → @staticmethod
    lesen nur ihre Eingaben und erzeugen daraus eine Ausgabe
```

### `observe_simulation_object(sender, time)`

Diese Klassenmethode ist der gemeinsame Einstieg für alle aktiven
Simulationskomponenten.

Eingabe:

```python
sender = sim_robot_main
time = 11.0
```

Interne Typauswahl:

```text
sender ist SimOrderJob         → observe_order_job()
sender ist SimRobotMain        → observe_main_robot()
sender ist SimRobotCorridorArm → observe_corridor_arm_robot()
sender ist SimMachine          → observe_machine()
```

Ausgabe:

```python
{
    "object_type": "main_robot",
    "object_id": "Main robot",
    "time": 11.0,
    ...
}
```

Wenn der Objekttyp nicht unterstützt wird, wird ein `ValueError` ausgelöst.

### `observe_order_job(job, time)`

Liest den vollständigen dynamischen Zustand eines `SimOrderJob`.

Vollständige Gruppen der Ausgabe von `observe_order_job()`:

```text
Identifikation
├── object_type
├── object_id
├── time
├── job_id
├── number
├── order_id
├── layout_id
├── scenario_id
└── start_store_id

Produkt und Auftrag
├── bearbeitungs_state
├── general_state
├── target_product_type_id
├── target_product_length
├── target_product_width
├── target_product_depth
├── target_product_weight
├── quantity
├── earliest_start_time
└── latest_end_time

Jobzustand
├── released
├── downgraded
├── downgrade_product_type_id
├── queue_priority
├── completed_time
└── due_state

Planung
├── selected_operation_id
└── selected_machine_id

Defekt
├── defect_detected_time
├── defect_operation_id
├── defect_operation_duration
├── defect_operation_consumed_life_units
├── defect_machine_id
├── defect_product_state_before
├── defect_product_state_target
├── defekt_schwergrad
└── defect_recovery_strategy
```

Damit gibt `observe_order_job()` genau diese Attribute zurück:

```python
{
    "object_type": ...,
    "object_id": ...,
    "time": ...,
    "job_id": ...,
    "number": ...,
    "layout_id": ...,
    "scenario_id": ...,
    "order_id": ...,
    "start_store_id": ...,
    "target_product_type_id": ...,
    "target_product_length": ...,
    "target_product_width": ...,
    "target_product_depth": ...,
    "target_product_weight": ...,
    "quantity": ...,
    "earliest_start_time": ...,
    "latest_end_time": ...,
    "released": ...,
    "downgraded": ...,
    "downgrade_product_type_id": ...,
    "queue_priority": ...,
    "bearbeitungs_state": ...,
    "general_state": ...,
    "due_state": ...,
    "defect_detected_time": ...,
    "defect_operation_id": ...,
    "defect_operation_duration": ...,
    "defect_operation_consumed_life_units": ...,
    "defect_machine_id": ...,
    "defect_product_state_before": ...,
    "defect_product_state_target": ...,
    "defekt_schwergrad": ...,
    "defect_recovery_strategy": ...,
    "completed_time": ...,
    "selected_operation_id": ...,
    "selected_machine_id": ...,
}
```

`is_waiting_for_action` gehört nicht direkt zur Rückgabe von
`observe_order_job()`. Die `SimulationBridge` ergänzt dieses Attribut danach
beim Aufbau von `states_by_id`:

```python
observation["is_waiting_for_action"] = (
    sim_object in self.sim_objects_waiting_for_action
)
```

### `observe_main_robot(robot, time)`

Liest den Zustand des Main-Roboters und alle Stores, die dieser für seine
Entscheidung sehen muss.

Die Ausgabe enthält:

```text
Main-Robot-Zustand
├── Position x, y, z
├── move_state und load_state
├── current_job_id und current_job_summary
├── nächste Operation, Maschine und Corridor
├── start_storage
├── end_storage
└── corridor_storages
    ├── main
    ├── left
    └── right
```

Die große konkrete `PolicyObservation` weiter unten zeigt die entsprechende
Ausgabe mit realistischen Werten.

### `observe_corridor_arm_robot(robot, time)`

Liest den Zustand eines linken oder rechten Corridor-Arm-Roboters.

Zusätzlich zum Roboterzustand werden unter anderem ausgegeben:

```text
corridor_id
direction
machine_names
next_machine_index
next_machine_in_arm_side
next_machine_same_corridor
sim_corridor_store_arm_input
sim_corridor_store_other_arm_input
sim_corridor_store_main
machine_storages
```

Damit kann der Generator feststellen, von welchem Store der Arm einen Job
nehmen und an welchen Maschinen-Store er ihn ablegen darf.

### `observe_machine(machine, time)`

Liest den Zustand einer simulierten Maschine.

Die Ausgabe enthält unter anderem:

```text
Maschinenzustand
├── machine_name
├── machine_type_id
├── corridor_id
├── left
├── state
├── is_idle
├── current_job_id und current_job_summary
├── next_operation_id und next_machine_id
├── Werkzeugtyp und verbleibende Lebensdauer
├── has_enough_tool_life
├── needs_tool_change
├── input_storage
└── output_storage
```

### `observe_store(store)`

Wandelt einen echten `sim.Store` in ein reines Store-Dictionary um.

Beispiel-Eingabe:

```text
Store (start)
├── capacity = 1000
└── enthält Order 1.1:0
```

Beispiel-Ausgabe:

```python
{
    "store_id": "start",
    "count": 1,
    "capacity": 1000,
    "available_capacity": 999,
    "is_empty": False,
    "has_items": True,
    "has_capacity": True,
    "job_summaries": [{...}],
    "job_ids": ["Order 1.1:0"],
    "job_queue_priorities": [0.75],
    "job_bearbeitungs_states": ["Rohes Werkstück"],
    "job_general_states": ["intakt"],
    "job_due_states": [None],
}
```

### `observe_job_summary(job)`

Erzeugt eine kompakte Beschreibung eines Jobs, wenn dieser in einem Store oder
auf einem Roboter beziehungsweise einer Maschine liegt.

Eingabe:

```python
job = sim_order_job
```

Ausgabe:

```python
{
    "job_id": "Order 1.1:0",
    "order_name": "Order 1.1",
    "number": 0,
    "bearbeitungs_state": "Rohes Werkstück",
    "general_state": "intakt",
    "target_product_type_name": "Poliertes Werkstück",
    "released": True,
    "downgraded": False,
    "queue_priority": 0.75,
    "selected_operation_id": None,
    "selected_machine_id": None,
    "completed_time": None,
    "due_state": None,
}
```

Bei `job=None` ist die Ausgabe ebenfalls `None`.

### `job_id(job)`

Erzeugt die stabile Policy-ID eines Jobs:

```python
job.order.name = "Order 1.1"
job.number = 0

SimulationObjectObserver.job_id(job)
# "Order 1.1:0"
```

Bei `job=None` wird `None` zurückgegeben.

# Statische Konfigurationsschnittstelle

## ConfigurationObjectObserver

### Position im Ablauf

Der `ConfigurationObjectObserver` übersetzt die echten statischen
Konfigurationsobjekte in das reine ID-basierte Modell der Policy.

### `_id`-Suffix und Vorbereitung für die Policy

Der `ConfigurationObjectObserver` bereitet die statischen
Konfigurationsobjekte für die Policy vor. Die echten `ProductType`,
`OperationType`, `Machine`, `ToolType`, `Corridor`- und `Layout`-Objekte bleiben
auf der Simulations- und Bridge-Seite. Die Policy erhält nur ihre Eigenschaften
und ID-basierte Beziehungen.

```text
echte Konfigurationsobjekte
└── ConfigurationObjectObserver
    ├── liest statische Eigenschaften
    ├── ersetzt Beziehungen zwischen Objekten durch IDs mit _id-Suffix
    └── erzeugt das policygeeignete Konfigurationsmodell
```

Beispiel:

```python
{
    "machine_id": "Schleifmaschine A",
    "machine_type_id": "Schleifmaschine",
    "corridor_id": "Bearbeitungskorridor",
    "layout_id": "Beispiellayout",
}
```

Die Policy sieht damit beispielsweise `corridor_id = "Bearbeitungskorridor"`,
aber niemals das echte Python-Objekt `Corridor(...)`.

```text
Konfigurationsobjekte
├── ProductType
├── OperationType
├── Machine
├── ToolType
├── Corridor
└── Layout
        ↓
ConfigurationObjectObserver
(normale Python-Klasse, keine sim.Component)
        ↓ erzeugt
Policy-Modell: dict[str, object]
(nur Dictionaries, IDs und reine Konfigurationsdaten)
        ↓
SimulationBridge
(Salabim: sim.Component)
        ↓ speichert als
self.policy_model
        ↓ wird Bestandteil von
PolicyObservation.simulation_configuration_snapshot["configuration_model"]
```

Kurzfassung:

```text
Konfigurationsobjekte
→ ConfigurationObjectObserver
→ ID-basiertes Policy-Modell
→ SimulationBridge (sim.Component)
→ PolicyObservation.simulation_configuration_snapshot["configuration_model"]
```

Wichtig: Der `ConfigurationObjectObserver` ist keine Salabim-Komponente. Die
`SimulationBridge` ist eine `sim.Component` und ruft den Observer beim Aufbau
ihres statischen Policy-Modells auf.

Im Unterschied zum `SimulationObjectObserver` beobachtet er keine dynamischen
Zustände:

```text
SimulationObjectObserver
→ dynamisch
→ Positionen, Jobs, Maschinenzustände, Stores

ConfigurationObjectObserver
→ statisch
→ Produktarten, Operationen, Maschinenkonfiguration, Werkzeuge, Corridors, Layouts
```

### `build_policy_configuration_model(...)`

Eingaben:

```python
ConfigurationObjectObserver.build_policy_configuration_model(
    product_types=PRODUCT_TYPES,
    operation_types=OPERATION_TYPES,
    machines=MACHINES,
    tool_types=TOOL_TYPES,
    corridors=CORRIDORS,
    layouts=LAYOUTS,
)
```

Die Methode erhält Listen mit echten Konfigurationsobjekten, gibt diese Objekte
aber nicht an die Policy weiter.

Ausgabe auf der obersten Ebene:

```python
{
    "configuration_maxima": {...},
    "product_types_by_id": {...},
    "operations_by_id": {...},
    "machines_by_id": {...},
    "tools_by_id": {...},
    "corridors_by_id": {...},
    "layouts_by_id": {...},
}
```

### `configuration_maxima`

Der Observer berechnet die Normalisierungsgrenzen aus den tatsächlich
vorhandenen Objekten der aktuellen Fabrikkonfiguration:

```python
"configuration_maxima": {
    "operation_duration": max(
        operation.duration for operation in operation_types
    ),
    "operation_tool_consumption": max(
        operation.consumes_life_units for operation in operation_types
    ),
    "product_weight": max(
        product.weight for product in product_types
    ),
    "product_volume": max(
        product.length * product.width * product.depth
        for product in product_types
    ),
}
```

Beispiel:

```text
Operationsdauern:       4, 10, 25  → Maximum 25
Werkzeugverbräuche:     3,  8, 12  → Maximum 12
Produktgewichte:        5, 20, 80  → Maximum 80
Produktvolumen:        24, 500, 6000 → Maximum 6000
```

Der Evaluator normalisiert anschließend relativ zu dieser konkreten
Konfiguration. Es gibt keine festen `FOR_POLICY`-Maximalwerte mehr. Deshalb
werden große Produkt- oder Operationswerte auch nicht mehr allein wegen einer
Policy-Normalisierungsgrenze mit einer Fehlermeldung abgelehnt.

Wenn noch keine Operationen oder Produkttypen konfiguriert sind, bleibt der
jeweilige Teil von `configuration_maxima` leer. Ein echter Evaluationslauf setzt
die dazugehörige Fabrikkonfiguration voraus.

### `product_types_by_id`

```python
{
    "Rohes Werkstück": {
        "product_type_id": "Rohes Werkstück",
        "length": 100,
        "width": 50,
        "depth": 20,
        "weight": 10,
    }
}
```

### `operations_by_id`

```python
{
    "Polieren": {
        "operation_id": "Polieren",
        "duration": 20,
        "consumed_life_units": 5,
        "defect_probability": 0.01,
        "machine_type_id": "Poliermaschine",
        "tool_type_id": "Polierwerkzeug",
        "consumes_product_type_id": "Rohes Werkstück",
        "produces_product_type_id": "Poliertes Werkstück",
    }
}
```

### `machines_by_id`

```python
{
    "Machine 1.1.1": {
        "machine_id": "Machine 1.1.1",
        "machine_type_id": "Poliermaschine",
        "corridor_id": "Corridor 1.1",
        "layout_id": "Layout 1",
        "left": True,
        "storage_capacity": 100,
    }
}
```

### `tools_by_id`

```python
{
    "Polierwerkzeug": {
        "tool_type_id": "Polierwerkzeug",
        "mount_time": 2,
        "unmount_time": 2,
        "total_life_units": 100,
    }
}
```

### `corridors_by_id`

```python
{
    "Corridor 1.1": {
        "corridor_id": "Corridor 1.1",
        "layout_id": "Layout 1",
        "storage_capacity": 200,
        "storage_out_time": 2,
        "storage_in_time": 3,
        "machine_ids": ["Machine 1.1.1"],
    }
}
```

### `layouts_by_id`

```python
{
    "Layout 1": {
        "layout_id": "Layout 1",
        "storage_capacity": 1000,
        "storage_out_time": 10,
        "storage_in_time": 5,
        "corridor_ids": ["Corridor 1.1"],
    }
}
```

### Aufgabentrennung zur SimulationBridge

Die Bridge behält weiterhin ihre Register mit echten Konfigurationsobjekten:

```python
self.product_types_by_id = {obj.name: obj for obj in PRODUCT_TYPES}
self.operations_by_id = {obj.name: obj for obj in OPERATION_TYPES}
self.machines_by_id = {obj.name: obj for obj in MACHINES}
self.tool_types_by_id = {obj.name: obj for obj in TOOL_TYPES}
```

Diese Register benötigt sie später zum Auflösen von Policy-IDs. Das statische
Policy-Modell wird dagegen vom `ConfigurationObjectObserver` erzeugt:

```python
return ConfigurationObjectObserver.build_policy_configuration_model(
    PRODUCT_TYPES,
    OPERATION_TYPES,
    MACHINES,
    TOOL_TYPES,
    CORRIDORS,
    LAYOUTS,
)
```

```text
Bridge-Register
→ echte Konfigurationsobjekte
→ bleiben auf der Bridge-/Simulationsseite
→ gelangen nicht zur Policy

ConfigurationObjectObserver-Ausgabe
→ IDs und reine Daten
→ darf zur Policy gelangen
```

---

# Datentypen

## PolicyObservation

### Position im Ablauf

```text
SimulationBridge
    │ erzeugt eine globale PolicyObservation
    │ current_object_id = None
    │ simulation_configuration_snapshot enthält alle Objektzustände und das Konfigurationsmodell
    ▼
GeneratorSelectorPolicy.make_decision(...)
    │
    ├── durchläuft alle Einträge in states_by_id
    ├── berücksichtigt nur Objekte mit is_waiting_for_action = True
    └── erzeugt für jedes wartende Objekt eine eigene objektbezogene
        PolicyObservation mit demselben vollständigen Snapshot und:
        current_object_id = ID dieses wartenden Objekts
            │
            ▼
        ActionGenerator.generate_actions(...)
            │ erzeugt mögliche Aktionen für genau dieses Objekt
            ▼
```

Die objektbezogene `PolicyObservation` enthält weiterhin den gesamten
`simulation_configuration_snapshot`. `current_object_id` entfernt oder filtert keine anderen
Objektzustände. Die ID zeigt dem Generator und Selector lediglich, für welches
wartende Objekt gerade entschieden wird.

Der Evaluator liest die benötigten Informationen direkt aus dem vollständigen
`simulation_configuration_snapshot`. Ein zusätzliches `evaluation_context`-
Dictionary ist nicht erforderlich und wurde deshalb entfernt:

```python
PolicyObservation(
    simulation_configuration_snapshot=snapshot,
    current_object_id="Main robot",
)
```

```text
simulation_configuration_snapshot
└── vollständige Momentaufnahme für Generator und Evaluator
    ├── Jobdaten für EDD und SPT
    ├── Storedaten für Kapazität und Queue-Länge
    ├── Maschinendaten für Auslastung und Werkzeugzustand
    └── Positionen für die Transportzeit
```

Die `SimulationBridge` erzeugt bei jeder Zustandsänderung einen neuen Snapshot.
Der Evaluator durchsucht diesen Snapshot bei Bedarf über seine Suchmethoden,
beispielsweise `find_store_state(...)`, `find_machine_state(...)` und
`find_store_position(...)`.

<!-- Der folgende frühere Abschnitt ist nicht mehr Teil der aktuellen Architektur.

### Ehemaliges `build_evaluation_context(snapshot)`

Die Funktion bekommt genau einen vollständigen aktuellen Snapshot:

```python
evaluation_context = build_evaluation_context(snapshot)
```

Der Snapshot enthält die Informationen in der Struktur der Simulation. Stores,
Jobs und Maschinen können deshalb an verschiedenen Stellen und unterschiedlich
tief verschachtelt liegen. Der Evaluator soll diese Struktur nicht bei jeder
Bewertung erneut durchsuchen müssen. `build_evaluation_context(...)` durchsucht
den Snapshot einmal und erstellt daraus Wörterbücher für den direkten Zugriff
über IDs.

#### Vereinfachte Eingabe

```python
snapshot = {
    "time": 11.0,
    "configuration_model": {
        "operations_by_id": {
            "Bohren": {"duration": 8.0},
        },
    },
    "simulation_object_states_by_id": {
        "Main robot": {
            "object_type": "main_robot",
            "object_id": "Main robot",
            "time": 11.0,
            "store_positions_by_id": {
                "start": {"x": 0.0, "y": -5.0, "z": 1.25},
            },
            "start_storage": {
                "store_id": "start",
                "capacity": 10,
                "available_capacity": 9,
                "job_summaries": [
                    {
                        "job_id": "Order 1:0",
                        "latest_end_time": 20.0,
                    }
                ],
            },
        },
        "Machine 1": {
            "object_type": "machine",
            "object_id": "Machine 1",
            "machine_name": "Bohrmaschine",
        },
    },
}
```

#### Schritt 1: Leere ID-Verzeichnisse anlegen

```python
jobs_by_id = {}
stores_by_id = {}
machines_by_id = {}
robots_by_id = {}
store_positions_by_id = {}
```

Diese Dictionaries werden während der Suche gefüllt.

#### Schritt 2: `states_by_id` rekursiv durchsuchen

```python
def collect(value: object) -> None:
    ...

collect(states_by_id)
```

`collect(...)` betrachtet den übergebenen Wert:

```text
Dictionary
├── enthält store_id?             → in stores_by_id eintragen
├── enthält job_id?               → in jobs_by_id eintragen
├── ist eine Maschine?            → in machines_by_id eintragen
├── ist ein Roboter?              → in robots_by_id eintragen
├── enthält Store-Positionen?     → in store_positions_by_id eintragen
└── anschließend alle enthaltenen Werte weiter durchsuchen

Liste
└── jedes Element weiter durchsuchen

anderer Wert, zum Beispiel str oder float
└── nichts tun
```

Die Rekursion ist notwendig, weil beispielsweise ein Job innerhalb einer
`job_summaries`-Liste liegt, die wiederum innerhalb eines Store-Dictionaries
liegt.

`collect(...) -> None` bedeutet: Die Hilfsfunktion gibt kein eigenes Ergebnis
zurück. Sie trägt gefundene Werte direkt in die fünf äußeren ID-Dictionaries
ein.

#### Konkrete Ausgabe

Für die vereinfachte Eingabe entsteht sinngemäß:

```python
evaluation_context = {
    "jobs_by_id": {
        "Order 1:0": {
            "job_id": "Order 1:0",
            "latest_end_time": 20.0,
        },
    },
    "stores_by_id": {
        "start": {
            "store_id": "start",
            "capacity": 10,
            "available_capacity": 9,
            "job_summaries": [...],
        },
    },
    "machines_by_id": {
        "Machine 1": {...},
        "Bohrmaschine": {...},
    },
    "robots_by_id": {
        "Main robot": {...},
    },
    "store_positions_by_id": {
        "start": {"x": 0.0, "y": -5.0, "z": 1.25},
    },
}
```

Es werden dabei keine neuen Simulationswerte und keine Scores erzeugt. Die
bereits vorhandenen Rohdaten werden lediglich neu nach IDs geordnet:

```text
Snapshot mit verschachtelten Daten
              ↓ build_evaluation_context(...)
dieselben Daten als schnell zugängliche ID-Verzeichnisse
              ↓
Evaluator kann beispielsweise stores_by_id["start"] direkt lesen
```

`time`, `model` und `states_by_id` werden nicht zusätzlich in den Kontext
eingetragen, weil sie bereits direkt im Snapshot vorhanden sind:

```python
snapshot["time"]
snapshot["configuration_model"]
snapshot["simulation_object_states_by_id"]
```

Der `evaluation_context` enthält somit ausschließlich die neu aufgebauten
Suchindizes und keine unnötigen Dopplungen der obersten Snapshot-Einträge.

-->

### Konkretes Beispiel: Main-Roboter wartet auf eine Aktion

Die Bridge erzeugt zunächst einen Snapshot, in dem der Main-Roboter und alle
anderen Simulationsobjekte enthalten sind:

```python
snapshot = {
    "time": 11.0,
    "state_version": 14,
    "simulation_object_states_by_id": {
        "Main robot": {
            "object_type": "main_robot",
            "object_id": "Main robot",
            "current_job_id": None,
            "move_state": "waiting",
            "load_state": "empty",
            "is_waiting_for_action": True,
        },
        "Order 1.1:0": {
            "object_type": "order_job",
            "object_id": "Order 1.1:0",
            "released": True,
            "is_waiting_for_action": False,
        },
        "SimMachine:Machine 1.1.1:left": {
            "object_type": "machine",
            "object_id": "SimMachine:Machine 1.1.1:left",
            "current_job_id": None,
            "is_waiting_for_action": False,
        },
    },
    "configuration_model": {
        "product_types_by_id": {},
        "operations_by_id": {},
        "machines_by_id": {},
        "tool_types_by_id": {},
        "corridors_by_id": {},
        "layouts_by_id": {},
    },
    "policy_trigger_event_ids": ["policy_trigger_14"],
    "policy_trigger_sender_ids": ["Main robot"],
}

policy_observation = PolicyObservation(
    simulation_configuration_snapshot=snapshot,
    current_object_id=None,
)
```

Die `GeneratorSelectorPolicy` erkennt:

```python
object_id = "Main robot"
object_state = snapshot["simulation_object_states_by_id"][object_id]

object_state["is_waiting_for_action"]
# True
```

Deshalb erzeugt sie für den Main-Roboter eine objektbezogene Observation:

```python
object_observation = PolicyObservation(
    simulation_configuration_snapshot=snapshot,  # weiterhin der vollständige Snapshot
    current_object_id="Main robot",     # aktuell zu entscheidendes Objekt
)
```

Der `ActionGenerator` kann dadurch genau den Main-Roboter-Zustand auswählen:

```python
current_state = object_observation.simulation_configuration_snapshot["simulation_object_states_by_id"][
    object_observation.current_object_id
]

# Ergebnis: das Dictionary von "Main robot"
```

Da der Main-Roboter leer ist und auf eine Aktion wartet, kann der Generator
beispielsweise folgende mögliche Aktion erzeugen:

```python
{
    "action_type": "pick_main_robot",
    "payload": {
        "target_type": "start_storage",
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "storage_out_time": 10.0,
    },
}
```

```python
@dataclass(frozen=True)
class PolicyObservation:
    simulation_configuration_snapshot: dict[str, object]
    current_object_id: str | None = None
```

### Aufgabe

Transportiert den reinen, ID-basierten Simulationszustand zur Policy.

### Attribute


| Attribut                            | Typ                 | Bedeutung                                                                       |
| ----------------------------------- | ------------------- | ------------------------------------------------------------------------------- |
| `simulation_configuration_snapshot` | `dict[str, object]` | Dynamische Zustände der Simulationsobjekte und statisches Konfigurationsmodell |
| `current_object_id`                | `str \| None`       | ID des Simulationsobjekts, für das gerade entschieden wird                     |

`frozen=True` bedeutet: Nach der Erzeugung können die Attribute der Dataclass nicht neu zugewiesen werden.

### Herkunft der Daten im `simulation_configuration_snapshot`

```text
PolicyObservation.simulation_configuration_snapshot
│
├── states_by_id
│   └── dynamische Zustände aller Simulationsobjekte
│       └── entstehen durch mehrere Aufrufe des SimulationObjectObserver
│           ├── SimOrderJob       → observe_order_job(...)
│           ├── SimRobotMain     → observe_main_robot(...)
│           ├── SimMachine       → observe_machine(...)
│           └── CorridorArmRobot → observe_corridor_arm_robot(...)
│
├── model
│   └── statisches, ID-basiertes Konfigurationsmodell
│       └── entsteht durch ConfigurationObjectObserver.build_policy_configuration_model(...)

├── policy_trigger_event_ids
│   └── IDs der Trigger, die diesen Entscheidungszyklus ausgelöst haben
│
└── policy_trigger_sender_ids
    └── Policy-IDs der Objekte, von denen diese Trigger stammen
```

`states_by_id` enthält somit die Ausgaben mehrerer Beobachtungen. `model`
enthält die Ausgabe des `ConfigurationObjectObserver`. In beiden Bereichen
stehen nur IDs und reine Daten; echte Simulations- und Konfigurationsobjekte
bleiben auf der Bridge-/Simulationsseite.

Die beiden Trigger-Listen werden nicht von einem Observer erzeugt. Die Methode
`SimulationBridge.create_policy_observation(policy_triggers)` ergänzt sie nach
`build_policy_simulation_snapshot()` direkt im Snapshot. Werden mehrere
Trigger derselben Simulationszeit gebündelt, enthalten die Listen entsprechend
mehrere Einträge.

### Beispiel-Eingabe bei der Erzeugung

```python
observation = PolicyObservation(
    simulation_configuration_snapshot={
        "time": 11.0,
        "state_version": 14,
        "simulation_object_states_by_id": {  # Ausgaben des SimulationObjectObserver
            "Main robot": {
                "object_type": "main_robot",
                "current_job_id": None,
                "is_waiting_for_action": True,
            }
        },
        "configuration_model": {},  # Ausgabe des ConfigurationObjectObserver
    },
    current_object_id="Main robot",
)
```

### Ergebnis

```python
observation.current_object_id
# "Main robot"

observation.simulation_configuration_snapshot["time"]
# 11.0
```

### Konkretes zusammenhängendes Beispiel

Das folgende Beispiel zeigt eine objektbezogene `PolicyObservation` für den
wartenden Main-Roboter. Der Snapshot enthält den dynamischen Objektzustand und
das statische ID-basierte Fabrikmodell:

```python
observation = PolicyObservation(
    simulation_configuration_snapshot={
        "time": 11.0,
        "state_version": 14,
        "simulation_object_states_by_id": {
            "Main robot": {
                "object_type": "main_robot",
                "object_id": "Main robot",
                "time": 11.0,
                "layout_id": "Layout 1",
                "scenario_id": "Scenario 1",
                "storage_in_time": 5.0,
                "storage_out_time": 10.0,
                "x": 0.0,
                "y": 0.0,
                "z": 2.5,
                "move_state": "waiting",
                "load_state": "empty",
                "is_loaded": False,
                "is_empty": True,
                "is_moving": False,
                "current_job_summary": None,
                "current_job_id": None,
                "current_job_queue_priority": None,
                "current_job_bearbeitungs_state": None,
                "current_job_general_state": None,
                "current_job_selected_operation_id": None,
                "current_job_selected_machine_id": None,
                "remaining_operation_count": 0,
                "remaining_machine_count": 0,
                "next_operation_id": None,
                "next_machine_id": None,
                "next_corridor_index": None,
                "next_corridor_id": None,
                "next_machine_side": None,
                "start_store_id": "start",
                "end_store_id": "end",
                "start_storage": {
                    "store_id": "start",
                    "count": 1,
                    "capacity": 1000,
                    "available_capacity": 999,
                    "is_empty": False,
                    "has_items": True,
                    "has_capacity": True,
                    "job_summaries": [
                        {
                            "job_id": "Order 1.1:0",
                            "order_name": "Order 1.1",
                            "number": 0,
                            "bearbeitungs_state": "Rohes Werkstück",
                            "general_state": "intakt",
                            "target_product_type_name": "Poliertes Werkstück",
                            "released": True,
                            "downgraded": False,
                            "queue_priority": 0.75,
                            "selected_operation_id": None,
                            "selected_machine_id": None,
                            "completed_time": None,
                            "due_state": None,
                        }
                    ],
                    "job_ids": ["Order 1.1:0"],
                    "job_queue_priorities": [0.75],
                    "job_bearbeitungs_states": ["Rohes Werkstück"],
                    "job_general_states": ["intakt"],
                    "job_due_states": [None],
                },
                "end_storage": {
                    "store_id": "end",
                    "count": 0,
                    "capacity": 1000,
                    "available_capacity": 1000,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "corridor_storages": [
                    {
                        "corridor_index": 0,
                        "corridor_id": "Corridor 1.1",
                        "main": {
                            "store_id": "Corridor 1.1 main",
                            "count": 0,
                            "capacity": 200,
                            "available_capacity": 200,
                            "is_empty": True,
                            "has_items": False,
                            "has_capacity": True,
                            "job_summaries": [],
                            "job_ids": [],
                            "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                            "job_due_states": [],
                        },
                        "left": {
                            "store_id": "Corridor 1.1 left",
                            "count": 0,
                            "capacity": 200,
                            "available_capacity": 200,
                            "is_empty": True,
                            "has_items": False,
                            "has_capacity": True,
                            "job_summaries": [],
                            "job_ids": [],
                            "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                            "job_due_states": [],
                        },
                        "right": {
                            "store_id": "Corridor 1.1 right",
                            "count": 0,
                            "capacity": 200,
                            "available_capacity": 200,
                            "is_empty": True,
                            "has_items": False,
                            "has_capacity": True,
                            "job_summaries": [],
                            "job_ids": [],
                            "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                            "job_due_states": [],
                        },
                    }
                ],
                "is_waiting_for_action": True,
            },
            "CorridorArmRobot:Corridor 1.1:left": {
                "object_type": "corridor_arm_robot",
                "object_id": "CorridorArmRobot:Corridor 1.1:left",
                "time": 11.0,
                "robot_name": "Corridor 1.1 left arm",
                "corridor_id": "Corridor 1.1",
                "storage_in_time": 3,
                "storage_out_time": 2,
                "direction": "left",
                "x": 10.0,
                "y": -5.0,
                "z": 2.5,
                "move_state": "waiting",
                "load_state": "empty",
                "is_loaded": False,
                "is_empty": True,
                "is_moving": False,
                "current_job_summary": None,
                "current_job_id": None,
                "current_job_queue_priority": None,
                "current_job_bearbeitungs_state": None,
                "current_job_general_state": None,
                "current_job_selected_operation_id": None,
                "current_job_selected_machine_id": None,
                "remaining_operation_count": 0,
                "remaining_machine_count": 0,
                "machine_names": ["Machine 1.1.1"],
                "next_operation_id": None,
                "next_machine_id": None,
                "next_machine_index": None,
                "next_machine_in_arm_side": False,
                "next_machine_same_corridor": False,
                "store_in_id": "Corridor 1.1 left",
                "store_other_arm_input_id": "Corridor 1.1 right",
                "store_main_id": "Corridor 1.1 main",
                "sim_corridor_store_arm_input": {
                    "store_id": "Corridor 1.1 left",
                    "count": 0,
                    "capacity": 200,
                    "available_capacity": 200,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "sim_corridor_store_other_arm_input": {
                    "store_id": "Corridor 1.1 right",
                    "count": 0,
                    "capacity": 200,
                    "available_capacity": 200,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "sim_corridor_store_main": {
                    "store_id": "Corridor 1.1 main",
                    "count": 0,
                    "capacity": 200,
                    "available_capacity": 200,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "machine_storages": [
                    {
                        "machine_index": 0,
                        "machine_name": "Machine 1.1.1",
                        "sim_machine_id": "SimMachine:Machine 1.1.1:left",
                        "input": {
                            "store_id": "Machine 1.1.1 in",
                            "count": 0,
                            "capacity": 100,
                            "available_capacity": 100,
                            "is_empty": True,
                            "has_items": False,
                            "has_capacity": True,
                            "job_summaries": [],
                            "job_ids": [],
                            "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                            "job_due_states": [],
                        },
                        "output": {
                            "store_id": "Machine 1.1.1 out",
                            "count": 0,
                            "capacity": 100,
                            "available_capacity": 100,
                            "is_empty": True,
                            "has_items": False,
                            "has_capacity": True,
                            "job_summaries": [],
                            "job_ids": [],
                            "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                            "job_due_states": [],
                        },
                    }
                ],
                "is_waiting_for_action": False,
            },
            "CorridorArmRobot:Corridor 1.1:right": {
                "object_type": "corridor_arm_robot",
                "object_id": "CorridorArmRobot:Corridor 1.1:right",
                "time": 11.0,
                "robot_name": "Corridor 1.1 right arm",
                "corridor_id": "Corridor 1.1",
                "direction": "right",
                "move_state": "waiting",
                "load_state": "empty",
                "current_job_id": None,
                "machine_names": [],
                "sim_corridor_store_arm_input": {
                    "store_id": "Corridor 1.1 right",
                    "count": 0,
                    "capacity": 200,
                    "available_capacity": 200,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "is_waiting_for_action": False,
            },
            "SimMachine:Machine 1.1.1:left": {
                "object_type": "machine",
                "object_id": "SimMachine:Machine 1.1.1:left",
                "time": 11.0,
                "machine_id": "Machine 1.1.1",
                "machine_type_id": "Poliermaschine",
                "corridor_id": "Corridor 1.1",
                "layout_id": "Layout 1",
                "left": True,
                "move_state": "waiting",
                "load_state": "empty",
                "current_job_summary": None,
                "current_job_id": None,
                "input_storage": {
                    "store_id": "Machine 1.1.1 in",
                    "count": 0,
                    "capacity": 100,
                    "available_capacity": 100,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "output_storage": {
                    "store_id": "Machine 1.1.1 out",
                    "count": 0,
                    "capacity": 100,
                    "available_capacity": 100,
                    "is_empty": True,
                    "has_items": False,
                    "has_capacity": True,
                    "job_summaries": [],
                    "job_ids": [],
                    "job_queue_priorities": [],
                    "job_bearbeitungs_states": [],
                    "job_general_states": [],
                    "job_due_states": [],
                },
                "is_waiting_for_action": False,
            },
            "Order 1.1:0": {
                "object_type": "order_job",
                "object_id": "Order 1.1:0",
                "time": 11.0,
                "job_id": "Order 1.1:0",
                "number": 0,
                "layout_id": "Layout 1",
                "scenario_id": "Scenario 1",
                "order_id": "Order 1.1",
                "start_store_id": "start",
                "end_store_id": "end",
                "bearbeitungs_state": "Rohes Werkstück",
                "general_state": "intakt",
                "target_product_type_id": "Poliertes Werkstück",
                "released": True,
                "queue_priority": 0.75,
                "downgraded": False,
                "selected_operation_id": None,
                "selected_machine_id": None,
                "completed_time": None,
                "due_state": None,
                "is_waiting_for_action": False,
            },
            "Order 1.1:1": {
                "object_type": "order_job",
                "object_id": "Order 1.1:1",
                "time": 11.0,
                "job_id": "Order 1.1:1",
                "number": 1,
                "layout_id": "Layout 1",
                "scenario_id": "Scenario 1",
                "order_id": "Order 1.1",
                "start_store_id": "start",
                "end_store_id": "end",
                "bearbeitungs_state": "Rohes Werkstück",
                "general_state": "intakt",
                "target_product_type_id": "Poliertes Werkstück",
                "released": True,
                "queue_priority": 0.50,
                "downgraded": False,
                "selected_operation_id": None,
                "selected_machine_id": None,
                "completed_time": None,
                "due_state": None,
                "is_waiting_for_action": False,
            }
        },
        "configuration_model": {
            "product_types_by_id": {
                "Rohes Werkstück": {
                    "product_type_id": "Rohes Werkstück",
                    "length": 100,
                    "width": 50,
                    "depth": 20,
                    "weight": 10,
                },
                "Poliertes Werkstück": {
                    "product_type_id": "Poliertes Werkstück",
                    "length": 100,
                    "width": 50,
                    "depth": 20,
                    "weight": 10,
                },
            },
            "operations_by_id": {
                "Polieren": {
                    "operation_id": "Polieren",
                    "duration": 20,
                    "consumed_life_units": 5,
                    "defect_probability": 0.01,
                    "machine_type_id": "Poliermaschine",
                    "tool_type_id": "Polierwerkzeug",
                    "consumes_product_type_id": "Rohes Werkstück",
                    "produces_product_type_id": "Poliertes Werkstück",
                }
            },
            "machines_by_id": {
                "Machine 1.1.1": {
                    "machine_id": "Machine 1.1.1",
                    "machine_type_id": "Poliermaschine",
                    "corridor_id": "Corridor 1.1",
                    "layout_id": "Layout 1",
                    "left": True,
                    "storage_capacity": 100,
                }
            },
            "tools_by_id": {
                "Polierwerkzeug": {
                    "tool_type_id": "Polierwerkzeug",
                    "mount_time": 2,
                    "unmount_time": 2,
                    "total_life_units": 100,
                }
            },
            "corridors_by_id": {
                "Corridor 1.1": {
                    "corridor_id": "Corridor 1.1",
                    "layout_id": "Layout 1",
                    "storage_capacity": 200,
                    "storage_out_time": 2,
                    "storage_in_time": 3,
                    "machine_ids": ["Machine 1.1.1"],
                }
            },
            "layouts_by_id": {
                "Layout 1": {
                    "layout_id": "Layout 1",
                    "corridor_ids": ["Corridor 1.1"],
                }
            },
        },
        "policy_trigger_event_ids": ["policy_trigger_14"],
        "policy_trigger_sender_ids": ["Main robot"],
    },
    current_object_id="Main robot",
)
```

In diesem konkreten Beispiel gilt:

```text
simulation_configuration_snapshot → enthält weiterhin alle Objektzustände und das Konfigurationsmodell
current_object_id         → "Main robot"
Main robot wartet         → is_waiting_for_action = True
Main robot ist leer       → current_job_id = None
Start-Store enthält Job  → "Order 1.1:0"
ActionGenerator kann daher eine pick_main_robot-Aktion erzeugen
```

`states_by_id` enthält in diesem Beispiel alle dynamischen Simulationsobjekte:

```text
states_by_id
├── Main robot
├── CorridorArmRobot:Corridor 1.1:left
├── CorridorArmRobot:Corridor 1.1:right
├── SimMachine:Machine 1.1.1:left
├── Order 1.1:0
└── Order 1.1:1
```

Die anderen Objekte bleiben im Snapshot erhalten, obwohl:

```python
current_object_id = "Main robot"
```

gesetzt ist. `current_object_id` entfernt oder filtert keine Zustände. Es zeigt
nur darauf, für welches wartende Objekt der Generator und der Selector in diesem
einzelnen Schritt entscheiden sollen.

Wichtig: Der Snapshot enthält reine Daten und IDs, keine echten `SimMachine`-, `SimOrderJob`- oder Store-Objekte.

### Globale und objektbezogene PolicyObservation

Im Ablauf werden zwei Formen derselben Dataclass verwendet.

#### 1. Globale Observation aus der SimulationBridge

Die `SimulationBridge` erzeugt zunächst eine Observation des gesamten Simulationszustands:

```python
global_observation = PolicyObservation(
    simulation_configuration_snapshot={
        "time": 11.0,
        "state_version": 14,
        "simulation_object_states_by_id": {
            "Main robot": {
                "object_type": "main_robot",
                "current_job_id": None,
                "is_waiting_for_action": True,
            },
            "Machine 1": {
                "object_type": "machine",
                "current_job_id": None,
                "is_waiting_for_action": False,
            },
        },
        "configuration_model": {},
        "policy_trigger_event_ids": ["policy_trigger_14"],
        "policy_trigger_sender_ids": ["Main robot"],
    },
)
```

Da `current_object_id` nicht angegeben wird, gilt der Standardwert:

```python
global_observation.current_object_id
# None
```

Das bedeutet:

```text
Der Zustand der gesamten Simulation ist vorhanden.
Es wurde noch kein einzelnes Objekt für eine Entscheidung ausgewählt.
```

Die Bridge übergibt diese globale Observation an:

```python
GeneratorSelectorPolicy.make_decision(global_observation)
```

#### 2. Objektbezogene Observation in GeneratorSelectorPolicy

Die `GeneratorSelectorPolicy` durchläuft alle Objektzustände:

```python
for object_id, object_state in snapshot["simulation_object_states_by_id"].items():
    if not object_state["is_waiting_for_action"]:
        continue
```

Nur für ein Objekt mit:

```python
"is_waiting_for_action": True
```

wird eine objektbezogene Observation erzeugt:

```python
object_observation = PolicyObservation(
    simulation_configuration_snapshot=snapshot,
    current_object_id=object_id,
)
```

Für den Main-Roboter ergibt das:

```python
object_observation = PolicyObservation(
    simulation_configuration_snapshot=snapshot,
    current_object_id="Main robot",
)
```

Die konkrete objektbezogene Observation besitzt damit folgende Struktur:

```python
{
    "simulation_configuration_snapshot": {
        "time": 11.0,
        "state_version": 14,
        "simulation_object_states_by_id": {
            "Main robot": {
                "object_type": "main_robot",
                "object_id": "Main robot",
                "current_job_id": None,
                "move_state": "waiting",
                "load_state": "empty",
                "is_waiting_for_action": True,
            },
            "Machine 1": {
                "object_type": "machine",
                "object_id": "Machine 1",
                "current_job_id": None,
                "is_waiting_for_action": False,
            },
        },
        "configuration_model": {
            "product_types_by_id": {},
            "operations_by_id": {},
            "machines_by_id": {},
            "tool_types_by_id": {},
            "corridors_by_id": {},
            "layouts_by_id": {},
        },
        "policy_trigger_event_ids": ["policy_trigger_14"],
        "policy_trigger_sender_ids": ["Main robot"],
    },
    "current_object_id": "Main robot",
}
```

Das ist keine auf den Main-Roboter verkleinerte Kopie. Unter
`simulation_configuration_snapshot["simulation_object_states_by_id"]` bleiben auch die Zustände
der Maschine und aller weiteren Simulationsobjekte vorhanden. Lediglich
`current_object_id` kennzeichnet den Main-Roboter als das Objekt, für das in
diesem Schritt eine Aktion erzeugt und ausgewählt wird.

Der vollständige globale `simulation_configuration_snapshot` bleibt erhalten. Es wird nur
zusätzlich festgelegt, für welches wartende Objekt jetzt Aktionen erzeugt und
ausgewählt werden.

Diese objektbezogene Observation geht an Generator und Selector:

```python
actions = action_generator.generate_actions(object_observation)

selected_action = action_selector.select_action(
    actions,
    observation=object_observation,
    target_id=object_observation.current_object_id,
)
```

Gesamtablauf:

```text
SimulationBridge
└── globale PolicyObservation
    └── current_object_id = None
            ↓
GeneratorSelectorPolicy
└── sucht Objekte mit is_waiting_for_action = True
            ↓
objektbezogene PolicyObservation
└── current_object_id = zum Beispiel "Main robot"
            ↓
SpineActionGenerator
└── erzeugt Aktionskandidaten für dieses Objekt
            ↓
ActionSelector
└── wählt eine Aktion für dieses Objekt
```

Der direkte Vergleich zeigt, dass sich nur `current_object_id` ändert:

```text
Globale PolicyObservation
├── simulation_configuration_snapshot = vollständiger Snapshot
│   ├── Zustände aller Simulationsobjekte
│   └── statisches Konfigurationsmodell
└── current_object_id = None

Objektbezogene PolicyObservation (GeneratorSelectorPolicy.py)
├── simulation_configuration_snapshot = derselbe vollständige Snapshot
│   ├── Zustände aller Simulationsobjekte
│   └── statisches Konfigurationsmodell
└── current_object_id = "Main robot"
```

`current_object_id = "Main robot"` bedeutet: Generator und Selector sollen in
diesem Schritt eine Aktion für den Main-Roboter erzeugen und auswählen. Die
Zustände der anderen Objekte werden dabei nicht aus dem Snapshot entfernt.

Kurzfassung:

```text
Bridge-Observation          → current_object_id = None
objektbezogene Observation → current_object_id = ID eines wartenden Objekts
```

---

## PolicyTrigger

### Position im Ablauf

```text
Simulationsobjekt, zum Beispiel SimMachine
└── yield self.bridge.request_action(self)
    │
    ▼
SimulationBridge.request_action(sim_machine)
├── markiert SimMachine in sim_objects_waiting_for_action
└── ruft notify_state_change(sim_machine) auf
    │
    ▼
SimulationBridge.notify_state_change(sim_machine)
├── erhöht _simulation_state_version
├── erzeugt einen PolicyTrigger mit der Policy-ID der SimMachine
└── legt den PolicyTrigger in policy_trigger_store
    │
    ▼
SimulationBridge.process()
├── nimmt den PolicyTrigger aus policy_trigger_store
└── startet den Policy-Entscheidungszyklus
    │
    ▼
PolicyObservation erzeugen
    │
    ▼
Policy-Aktion auswählen
    │
    ▼
SimulationAction in den persönlichen Action-Store der SimMachine legen
```

`SimOrderJob.py` kann außerdem direkt
`yield self.bridge.notify_state_change(self)` aufrufen. Dadurch meldet der Job
eine relevante Zustandsänderung und erzeugt ebenfalls einen `PolicyTrigger`,
ohne dadurch zwingend selbst als auf eine Aktion wartend markiert zu werden.

### Was passiert nach dem Einlegen in den Bridge-Store?

```text
policy_trigger_store ist leer
    │
    └── SimulationBridge.process() wartet bei:
        yield self.from_store(self.policy_trigger_store)

Simulationsobjekt legt einen PolicyTrigger hinein
    │
    └── die from_store-Anforderung wird erfüllt
        │
        └── der Bridge-Prozess wird fortgesetzt
            ├── nimmt den ersten Trigger entgegen
            ├── gibt mit hold(0) eine Ereignisrunde frei
            ├── sammelt weitere Trigger derselben Simulationszeit
            ├── erzeugt die PolicyObservation
            ├── ruft policy.make_decision(...) auf
            ├── prüft die state_version
            ├── erhält eine konfliktfreie PolicyDecision von der Policy
            ├── wandelt sie in SimulationActions um
            └── legt sie in die Action-Stores der Zielobjekte
```

Die Schleifen in `SimulationBridge.process()` haben getrennte Aufgaben:

```text
äußere while True
└── verarbeitet dauerhaft nacheinander neue Entscheidungszyklen

Trigger-Sammelschleife
└── sammelt bereits vorhandene Trigger derselben Simulationszeit

State-Version-Schleife
└── wiederholt Snapshot und Auswahl, wenn die Entscheidung bereits
    durch eine neuere Zustandsmeldung veraltet ist
```

Nach dem abgeschlossenen Entscheidungszyklus springt die äußere
`while True`-Schleife wieder an den Anfang. Ist kein neuer Trigger vorhanden,
wartet die Bridge erneut bei `yield self.from_store(...)`. Sie rechnet während
dieser Wartezeit nicht fortlaufend weiter.

```python
class PolicyTrigger(sim.Component):
```

### Aufgabe

Meldet der `SimulationBridge`, dass ein neuer Policy-Entscheidungszyklus notwendig ist.

`PolicyTrigger` ist selbst eine Salabim-Komponente.

### Konstruktor

```python
PolicyTrigger(
    event_id: str,
    sender_id: str,
    state_version: int,
    time: float,
    env=env,
)
```

### Attribute


| Attribut        | Beispiel             | Bedeutung                                        |
| ----------------- | ---------------------- | -------------------------------------------------- |
| `event_id`      | `"policy_trigger_8"` | Eindeutige ID des Triggers                       |
| `sender_id`     | `"Order 1.1:0"`      | Policy-ID des meldenden Objekts                  |
| `state_version` | `8`                  | Stand des globalen Bridge-Zustands beim Erzeugen |
| `time`          | `0.0`                | Simulationszeit der Meldung                      |

### Konkretes Beispiel

```python
policy_trigger = PolicyTrigger(
    event_id="policy_trigger_8",
    sender_id="Order 1.1:0",
    state_version=8,
    time=0.0,
    env=env,
)
```

Inhalt:

```python
{
    "event_id": "policy_trigger_8",
    "sender_id": "Order 1.1:0",
    "state_version": 8,
    "time": 0.0,
}
```

---

## SelectedObjectAction

### Position im Ablauf

```text
Objektbezogene PolicyObservation
└── current_object_id = zum Beispiel "Main robot"
    │
    ▼
SpineActionGenerator.generate_actions(...) (ActionGenerators.py)
└── erzeugt mehrere mögliche Aktionskandidaten als Dictionaries
    ├── pick_main_robot für Order 1.1:0
    ├── pick_main_robot für Order 1.1:1
    └── wait_main_robot
    │
    ▼
ActionSelector.select_action(...) (ActionSelectors.py)
└── wählt genau einen Aktionskandidaten für dieses Objekt
    │
    ▼
PolicyDecision.with_single_selected_action(...) (InterfaceTypes.py)
├── erzeugt eine SelectedObjectAction
│   ├── target_id   = "Main robot"
│   ├── action_type = "pick_main_robot"
│   └── payload     = IDs und reine Aktionsdaten
└── verpackt sie in eine PolicyDecision
    │
    ▼
GeneratorSelectorPolicy (GeneratorSelectorPolicy.py)
└── sammelt die SelectedObjectAction jedes wartenden Objekts
    │
    ▼
globale PolicyDecision
└── actions: list[SelectedObjectAction]
    │
    ▼
SimulationBridge (SimulationBridge.py)
├── ordnet Policy-IDs den echten Simulationsobjekten zu
├── erzeugt daraus SimulationAction-Objekte
└── legt diese in die Action-Stores der Zielobjekte
```

Die `SelectedObjectAction` wird somit nicht direkt im `ActionSelector`
konstruiert. Der Selector ruft
`PolicyDecision.with_single_selected_action(...)` auf. Diese Klassenmethode in
`InterfaceTypes.py` erzeugt intern die `SelectedObjectAction`.

```python
return cls([
    SelectedObjectAction(
        target_id,
        action["action_type"],
        action["payload"],
    )
])
```

An der Grenze zwischen Policy und Bridge enthält sie nur IDs und reine Daten.
Beim anschließenden Auflösen der IDs darf die Bridge intern eine Kopie erzeugen,
in der zusätzlich die echten Simulationsobjekte stehen. Diese Kopie bleibt auf
der Bridge-/Simulationsseite und gelangt nicht zur Policy zurück.

```python
@dataclass(frozen=True)
class SelectedObjectAction:
    target_id: str
    action_type: str
    payload: dict[str, object]
```

### Aufgabe

Beschreibt eine ausgewählte Aktion für genau ein Simulationsobjekt, aber weiterhin nur mit Policy-IDs und reinen Daten.

### Beispiel

```python
selected_action = SelectedObjectAction(
    target_id="Main robot",
    action_type="pick_main_robot",
    payload={
        "target_type": "start_storage",
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "storage_out_time": 10.0,
    },
)
```

Dieses Beispiel entspricht der aktuellen Ausgabeform des
`SpineActionGenerator` für einen Main-Robot-Pick aus dem Start-Store. Es kann
genau dann ausgewählt werden, wenn `Order 1.1:0` im Start-Store liegt und der
Main-Roboter leer ist und auf eine Aktion wartet. Welcher Job tatsächlich
ausgewählt wird, hängt von den vorhandenen Aktionskandidaten und dem
`ActionSelector` ab.

### Inhalt

```python
{
    "target_id": "Main robot",
    "action_type": "pick_main_robot",
    "payload": {
        "target_type": "start_storage",
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "storage_out_time": 10.0,
    },
}
```

---

## PolicyDecision

```python
@dataclass(frozen=True)
class PolicyDecision:
    actions: list[SelectedObjectAction]
```

### Position im Ablauf

```text
Objektbezogene PolicyObservation (GeneratorSelectorPolicy.py)
    │
    ▼
SpineActionGenerator (ActionGenerators.py)
└── erzeugt mögliche Aktionskandidaten für ein wartendes Objekt
    │
    ▼
ActionSelector (ActionSelectors.py)
└── wählt einen Aktionskandidaten aus
    │
    ▼
PolicyDecision.with_single_selected_action(...) (InterfaceTypes.py)
└── erzeugt eine objektbezogene PolicyDecision
    └── actions = [SelectedObjectAction(...)]
    │
    ▼
GeneratorSelectorPolicy (GeneratorSelectorPolicy.py)
└── sammelt die SelectedObjectAction aller wartenden Objekte
    │
    ▼
globale PolicyDecision
└── actions = Liste mit den ausgewählten Aktionen aller wartenden Objekte
    │
    ▼
SimulationBridge (SimulationBridge.py)
├── löst Policy-IDs zu echten Simulationsobjekten auf
└── erzeugt und verteilt SimulationAction-Objekte
```

### Aufgabe

Verpackt die ausgewählten Aktionen eines globalen Policy-Entscheidungszyklus.

Die Liste kann Aktionen für mehrere gleichzeitig wartende Objekte enthalten.

### Beispiel mit zwei Objekten

```python
decision = PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Main robot",
            action_type="pick_main_robot",
            payload={"selected_job_id": "Order 1.1:0"},
        ),
        SelectedObjectAction(
            target_id="Machine 1",
            action_type="wait_machine",
            payload={},
        ),
    ]
)
```

### Struktur

```text
PolicyDecision
└── actions
    ├── SelectedObjectAction für Main robot
    └── SelectedObjectAction für Machine 1
```

### `with_single_selected_action(action, target_id)`

Erzeugungsbaum:

```text
PolicyDecision.with_single_selected_action(action, target_id)
│
├── erzeugt SelectedObjectAction(...)
│
├── setzt das Objekt in eine Liste
│   └── [SelectedObjectAction(...)]
│
└── ruft cls(Liste) auf
    └── cls = PolicyDecision
        └── erstes Konstruktorargument wird actions zugewiesen
            └── PolicyDecision.actions
                └── [SelectedObjectAction(...)]
```

Erzeugt aus einem einzelnen Action-Dictionary eine `PolicyDecision` mit genau einem Listeneintrag.

Die Methode enthält:

```python
return cls([
    SelectedObjectAction(
        target_id,
        action["action_type"],
        action["payload"],
    )
])
```

`cls` steht in dieser Klassenmethode für `PolicyDecision`. Die eckigen
Klammern erzeugen eine Liste mit genau einer `SelectedObjectAction`:

```python
[
    SelectedObjectAction(...)
]
```

`PolicyDecision` ist eine Dataclass mit genau einem Feld:

```python
class PolicyDecision:
    actions: list[SelectedObjectAction]
```

Python erzeugt deshalb sinngemäß diesen Konstruktor:

```python
def __init__(self, actions):
    self.actions = actions
```

Das erste an `cls(...)` übergebene Argument wird somit automatisch dem ersten
Dataclass-Feld `actions` zugewiesen. Der kurze Code ist gleichbedeutend mit der
deutlicheren Schreibweise:

```python
return PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id=target_id,
            action_type=action["action_type"],
            payload=action["payload"],
        )
    ]
)
```

Eingabe:

```python
action = {
    "action_type": "wait_machine",
    "payload": {},
}

target_id = "Machine 1"
```

Aufruf:

```python
decision = PolicyDecision.with_single_selected_action(action, target_id)
```

Ausgabe:

```python
PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Machine 1",
            action_type="wait_machine",
            payload={},
        )
    ]
)
```

---

## SimulationAction

```python
class SimulationAction(sim.Component):
```

### Position im Ablauf

```text
GeneratorSelectorPolicy
└── sammelt die ausgewählten Aktionen aller wartenden Objekte
    │
    └── erzeugt die globale PolicyDecision
        └── actions = Liste mit SelectedObjectAction-Objekten
            └── jede SelectedObjectAction enthält Policy-IDs und reine Daten
    │
    ▼
GeneratorSelectorPolicy
└── prüft Konflikte und reserviert ausgewählte Job-IDs eindeutig
    │
    ▼
SimulationBridge.create_simulation_actions(...)
└── löst IDs auf und erzeugt aus jeder SelectedObjectAction eine SimulationAction
    ├── target      = echtes Salabim-Simulationsobjekt
    ├── action_type = aus der SelectedObjectAction
    └── payload     = für den Simulationskern aufgelöste Daten
    │
    ▼
persönlicher Action-Store des Zielobjekts
└── enthält die für dieses Simulationsobjekt ausführbare SimulationAction
    │
    ▼
Simulationsobjekt
├── empfängt die SimulationAction mit yield self.bridge.action(self)
└── führt die Aktion in seinem process() aus
```

### Aufgabe

Stellt eine von der Bridge erzeugte und aufgelöste Aktion dar, die von genau
einem Ziel-Simulationsobjekt im Simulationskern ausgeführt werden kann.

Anders als `SelectedObjectAction` darf sie ein echtes Salabim-Zielobjekt enthalten.

### Attribute


| Attribut                   | Bedeutung                                                   |
| ---------------------------- | ------------------------------------------------------------- |
| `event_id`                 | Eindeutige ID dieser Simulationsaktion                      |
| `target`                   | Echtes Salabim-Simulationsobjekt                            |
| `source_policy_trigger_id` | ID des auslösenden Policy-Triggers                         |
| `action_type`              | Art der auszuführenden Aktion                              |
| `time`                     | Zeitpunkt der Aktionserzeugung                              |
| `payload`                  | Von der Bridge für die Simulation aufgelöste Aktionsdaten |

### Beispiel

```python
simulation_action = SimulationAction(
    event_id="simulation_action_17",
    target=sim_robot_main,
    source_policy_trigger_id="policy_trigger_8",
    action_type="pick_main_robot",
    time=11.0,
    payload={
        "target_store": start_store,
        "selected_job": sim_order_job,
    },
    env=env,
)
```

### Wichtiger Unterschied

```text
SelectedObjectAction
→ Policy-Seite
→ IDs und reine Daten

SimulationAction
→ Simulationsseite
→ echte Salabim-Objekte dürfen enthalten sein
```

---

# Abstrakte Schnittstellen

## ActionGenerator

```python
class ActionGenerator(ABC):
    @abstractmethod
    def generate_actions(
        self,
        observation: PolicyObservation,
    ) -> list[dict[str, Any]]:
        pass
```

### Position im Ablauf

```text
objektbezogene PolicyObservation
├── simulation_configuration_snapshot = vollständiger Snapshot aller Objekte
└── current_object_id = ID des aktuell zu entscheidenden Objekts
    │
    ▼
GeneratorSelectorPolicy
└── ruft für dieses wartende Objekt den ActionGenerator auf
    │
    ▼
ActionGenerator
└── erzeugt anhand des gesamten Snapshots alle zulässigen
    Aktionskandidaten für current_object_id
    │
    ▼
GeneratorSelectorPolicy
└── übergibt die Kandidaten und dieselbe Observation an den ActionSelector
```

### Aufgabe

Legt fest, dass jeder konkrete ActionGenerator aus einer Observation eine Liste zulässiger Aktionskandidaten erzeugen muss.

Im produktiven Ablauf ist `observation` nicht die globale Observation der
Bridge mit `current_object_id=None`, sondern die von der
`GeneratorSelectorPolicy` erzeugte objektbezogene Observation. Sie enthält
weiterhin den vollständigen Snapshot, beispielsweise jedoch zusätzlich:

```python
observation.current_object_id
# "Main robot"
```

Der Generator darf damit die Zustände aller Objekte und das
Konfigurationsmodell lesen, erzeugt seine Aktionskandidaten aber für den
Main-Roboter.

Konkrete Implementierung:

```text
ActionGenerator
└── SpineActionGenerator
```

Beispiel-Rückgabe:

```python
[
    {
        "action_type": "pick_main_robot",
        "payload": {...},
    },
    {
        "action_type": "wait_main_robot",
        "payload": {},
    },
]
```

`pass` enthält keine Ausführungslogik. Die Methode muss von der konkreten Unterklasse implementiert werden.

---

## ActionEvaluator

```python
class ActionEvaluator(ABC):
    @abstractmethod
    def evaluate_action(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> float:
        pass

    def prepare_action_candidate(
        self,
        action: dict[str, Any],
        observation: PolicyObservation,
    ) -> dict[str, Any]:
        return action
```

```text
ActionGenerator
└── technisch mögliche Kandidaten
        ↓
ActionEvaluator
├── ein Zahlenwert pro Kandidat
└── darf den ausgewählten Kandidaten um berechnete Policywerte ergänzen
        ↓
ActionSelector
└── Kandidat mit höchstem Wert
```

Konkrete Implementierung:

```text
ActionEvaluator
└── LocalHeuristicActionEvaluator (HeuristicControl/LocalHeuristicActionEvaluator.py)
```

---

## ActionSelector

```python
class ActionSelector(ABC):
    @abstractmethod
    def select_action(
        self,
        actions: list[dict[str, Any]],
        *,
        evaluator: ActionEvaluator,
        observation: PolicyObservation | None = None,
        target_id: str,
    ) -> PolicyDecision:
        pass
```

### Position im Ablauf

```text
ActionGenerator
└── liefert die für current_object_id erzeugten Aktionskandidaten
    │
    ▼
GeneratorSelectorPolicy
└── ruft den ActionSelector mit Kandidaten, Evaluator, Observation und target_id auf
    │
    ▼
ActionSelector
├── erhält dieselbe objektbezogene PolicyObservation
├── lässt jeden Kandidaten durch den ActionEvaluator bewerten
├── erhält target_id = observation.current_object_id
└── wählt den höchstbewerteten Kandidaten für dieses Objekt aus
    │
    ▼
PolicyDecision.with_single_selected_action(...)
└── erzeugt eine objektbezogene PolicyDecision mit einer SelectedObjectAction
└── wird an die GeneratorSelectorPolicy zurückgegeben
```

### Aufgabe

Legt fest, dass jeder Selector aus den Aktionskandidaten eine Aktion auswählen muss.

Konkrete Implementierung:

```text
ActionSelector
└── BaselineActionSelector
```

### Eingaben


| Parameter     | Bedeutung                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------- |
| `actions`     | Alle vom Generator für`current_object_id` erzeugten Aktionskandidaten                       |
| `evaluator`   | Bewertet jeden Aktionskandidaten anhand derselben objektbezogenen Observation                |
| `observation` | Objektbezogene`PolicyObservation`: vollständiger Snapshot plus gesetzte `current_object_id` |
| `target_id`   | Dieselbe Objekt-ID wie`observation.current_object_id`; Ziel der ausgewählten Aktion         |

Das einzelne `*` bedeutet: Die nachfolgenden Argumente müssen beim Aufruf mit ihrem Namen angegeben werden.

```python
selector.select_action(
    actions,
    evaluator=action_evaluator,
    observation=object_observation,
    target_id=object_observation.current_object_id,
)
```

Im aktuellen produktiven Aufruf der `GeneratorSelectorPolicy` wird
`observation` immer mitgegeben. Das `None` in der abstrakten Typannotation
erlaubt lediglich, einen Selector auch ohne Observation aufzurufen; dieser
optionale Fall wird im normalen Generator-Selector-Ablauf nicht verwendet.

---

# Ausgehende Simulationsschnittstelle

## policy_payload_id_mappings(bridge)

### Position im Ablauf

```text
GeneratorSelectorPolicy
├── ruft ActionGenerator und ActionSelector für jedes wartende Objekt auf
├── sammelt deren SelectedObjectAction-Objekte
└── erzeugt daraus die globale PolicyDecision
    │
    ▼
PolicyDecision
└── SelectedObjectAction.payload enthält Policy-IDs
    │
    ▼
SimulationBridge.create_simulation_actions(...)
└── verwendet beim direkten Erzeugen policy_payload_id_mappings(bridge)
    │
    ▼
Bridge-Register
└── ordnen Policy-IDs den echten Laufzeitobjekten zu
    │
    ▼
aufgelöstes Payload für SimulationAction
```

### Durchgängiges konkretes Beispiel

Die `GeneratorSelectorPolicy` liefert der Bridge beispielsweise diese
ID-basierte Entscheidung:

```python
decision = PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Main robot",
            action_type="pick_main_robot",
            payload={
                "target_type": "start_storage",
                "target_store_id": "start",
                "selected_job_id": "Order 1.1:0",
                "storage_out_time": 10.0,
            },
        )
    ]
)
```

Aufbau der enthaltenen Aktion:

```text
SelectedObjectAction
├── target_id = "Main robot"
│   └── Policy-ID des Simulationsobjekts, das die Aktion ausführen soll
│
├── action_type = "pick_main_robot"
│
└── payload
    ├── "target_type": "start_storage"
    ├── "target_store_id": "start"
    │   ├── Policy-ID-Key  = "target_store_id"
    │   └── Policy-ID-Wert = "start"
    ├── "selected_job_id": "Order 1.1:0"
    │   ├── Policy-ID-Key  = "selected_job_id"
    │   └── Policy-ID-Wert = "Order 1.1:0"
    └── "storage_out_time": 10.0
```

Die Bridge hat zu diesem Zeitpunkt unter anderem diese Register aufgebaut:

```python
self.policy_store_id_to_simulation_store = {
    "start": start_store,
    "Machine 1.1.1 in": machine_input_store,
}

self.policy_object_id_to_simulation_object = {
    "Main robot": sim_robot_main,
    "Order 1.1:0": sim_order_job,
}

self.machines_by_id = {
    "Machine 1.1.1": machine_configuration,
}
```

Der Aufruf in `create_simulation_actions()`:

```python
payload_id_mappings = policy_payload_id_mappings(self)
```

liefert ein Dictionary mit den Auflösungsregeln. Der für dieses Beispiel
relevante Ausschnitt der konkreten Rückgabe ist:

```python
{
    "target_store_id": (
        "target_store",
        {
            "start": start_store,
            "Machine 1.1.1 in": machine_input_store,
        },
    ),
    "selected_job_id": (
        "selected_job",
        {
            "Main robot": sim_robot_main,
            "Order 1.1:0": sim_order_job,
        },
    ),
    "selected_machine_id": (
        "selected_machine",
        {
            "Machine 1.1.1": machine_configuration,
        },
    ),
}
```

Die Regel für `selected_machine_id` gehört zwar zur Rückgabe, wird bei
dieser konkreten Pick-Aktion aber nicht benutzt, weil ihr Payload keinen
`selected_machine_id`-Eintrag enthält.

Für `target_store_id` sucht die Bridge:

```python
self.policy_store_id_to_simulation_store["start"]
# start_store
```

Für `selected_job_id` sucht sie:

```python
self.policy_object_id_to_simulation_object["Order 1.1:0"]
# sim_order_job
```

Beim vollständigen Aufruf:

```python
simulation_actions = self.create_simulation_actions(
    decision,
    "policy_trigger_14",
)
```

entsteht direkt diese ausführbare Aktion:

```python
SimulationAction(
    event_id="action_15",
    target=sim_robot_main,
    source_policy_trigger_id="policy_trigger_14",
    action_type="pick_main_robot",
    time=11.0,
    payload={
        "target_type": "start_storage",
        "storage_out_time": 10.0,
        "target_store": start_store,
        "selected_job": sim_order_job,
    },
)
```

Die ursprünglichen Policy-ID-Keys `target_store_id` und `selected_job_id`
bleiben nur in der unveränderten `SelectedObjectAction`. Im Payload der
`SimulationAction` werden sie durch `target_store` und `selected_job` mit den
echten Laufzeitobjekten ersetzt.

`target_id="Main robot"` wird separat zum echten Ziel `sim_robot_main`
aufgelöst und als `SimulationAction.target` gespeichert.

Diese Funktion beschreibt, wie ID-basierte Policy-Payloads auf der
Simulationsseite wieder in echte Laufzeitobjekte aufgelöst werden.

Beispiel:

```text
Policy-Payload
"target_store_id": "Corridor 1.1 left"
        ↓
policy_store_id_to_simulation_store
        ↓
Simulations-Payload
"target_store": Store (Corridor 1.1 left)
```

Die Zuordnungen sind:

```text
target_store_id           → target_store
selected_job_id           → selected_job
sim_machine_id            → sim_machine
sim_corridor_id           → sim_corridor
selected_operation_id     → selected_operation
selected_machine_id       → selected_machine
downgrade_product_type_id → downgrade_product_type
operation_id              → operation
planned_machine_id        → planned_machine
tool_type_id              → tool_type
```

Die konkrete Rückgabe ist ein Dictionary. Jeder Policy-Key zeigt auf ein Tupel
aus Simulations-Payload-Key und dem dafür verwendeten Bridge-Register:

```python
{
    "target_store_id": (
        "target_store",
        bridge.policy_store_id_to_simulation_store,
    ),
    "selected_job_id": (
        "selected_job",
        bridge.policy_object_id_to_simulation_object,
    ),
    "sim_machine_id": (
        "sim_machine",
        bridge.policy_object_id_to_simulation_object,
    ),
    "sim_corridor_id": (
        "sim_corridor",
        bridge.policy_object_id_to_simulation_object,
    ),
    "selected_operation_id": (
        "selected_operation",
        bridge.operations_by_id,
    ),
    "selected_machine_id": (
        "selected_machine",
        bridge.machines_by_id,
    ),
    "downgrade_product_type_id": (
        "downgrade_product_type",
        bridge.product_types_by_id,
    ),
    "operation_id": (
        "operation",
        bridge.operations_by_id,
    ),
    "planned_machine_id": (
        "planned_machine",
        bridge.machines_by_id,
    ),
    "tool_type_id": (
        "tool_type",
        bridge.tool_types_by_id,
    ),
}
```

Ein einzelner Eintrag:

```python
"selected_job_id": (
    "selected_job",
    bridge.policy_object_id_to_simulation_object,
)
```

bedeutet:

```text
Policy-Key
selected_job_id
        ↓ Wert ist zum Beispiel "Order 1.1:0"
Bridge-Register
policy_object_id_to_simulation_object
        ↓ Nachschlagen mit "Order 1.1:0"
Simulations-Key und echtes Objekt
selected_job = SimOrderJob (simorderjob.0)
```

Die Funktion erzeugt selbst keine Simulationsobjekte. Sie verwendet die von
der Bridge aufgebauten Register, um eine Policy-ID dem bereits existierenden
Laufzeitobjekt zuzuordnen.

---

# Hilfsfunktion

## is_wait_action(action_type)

```python
def is_wait_action(action_type: str) -> bool:
    return action_type.startswith("wait_")
```

### Position im Ablauf

```text
ActionSelector
└── unterscheidet ausführbare Aktionen von wait_*-Aktionen
    │
    ▼
is_wait_action(action_type)
    │
    ├── True  → Warteaktion
    └── False → ausführbare Fachaktion

SimulationBridge
└── filtert ausgewählte wait_*-Aktionen vor der Simulationszustellung
```

### Aufgabe

Prüft, ob ein Aktionstyp eine Warteaktion ist.

### Beispiele

```python
is_wait_action("wait_machine")
# True

is_wait_action("wait_main_robot")
# True

is_wait_action("pick_main_robot")
# False
```

---

# Abstrakte Policy-Schnittstelle

## Policy

```python
class Policy(ABC):
    @abstractmethod
    def make_decision(
        self,
        observation: PolicyObservation,
    ) -> PolicyDecision:
        pass
```

### Position im Ablauf

```text
SimulationBridge
└── übergibt die globale PolicyObservation
    │
    ▼
Policy
└── äußere, austauschbare Steuerungsschnittstelle
    │
    ▼
PolicyDecision
└── geht zurück an die SimulationBridge
```

### Aufgabe

Definiert die äußere Schnittstelle, welche die `SimulationBridge` von einer vollständigen Policy erwartet.

Konkrete Implementierung:

```text
Policy
└── GeneratorSelectorPolicy
    ├── ActionGenerator
    └── ActionSelector
```

Die Bridge kennt nur:

```python
decision = policy.make_decision(observation)
```

Sie muss nicht wissen, ob intern eine Baseline-, Greedy- oder RL-Auswahl verwendet wird.

---

# Gesamtablauf

```text
PolicyTrigger
    ↓
SimulationBridge erzeugt PolicyObservation
    ↓
GeneratorSelectorPolicy.make_decision()
    ↓
ActionGenerator.generate_actions()
    ↓
list[Candidate Actions]
    ↓
ActionSelector.select_action()
    ↓
PolicyDecision
    ↓
SimulationBridge erzeugt SimulationAction
```

## Entkopplungsgrenze

```text
PolicyObservation
SelectedObjectAction
PolicyDecision
→ nur IDs und reine Daten

SimulationAction
→ echte Salabim-Objekte auf der Simulationsseite erlaubt
```

