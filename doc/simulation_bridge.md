# SimulationBridge

Python-Datei: `sources/SpineML/Control/SimulationBridge/SimulationBridge.py`

**Aufgabe und Position im Ablauf**

Die `SimulationBridge` ist selbst eine Salabim-Komponente:

```python
class SimulationBridge(sim.Component):
```

Sie trennt Simulationskern und Policy:

```text
Simulationskern
├── echte sim.Component-Objekte
├── echte sim.Store-Objekte
└── echte Konfigurationsobjekte
        │
        ▼
SimulationBridge
├── liest über SimulationObjectObserver die Zustände der Simulationsobjekte
├── übersetzt diese Zustände in IDs und reine Daten
├── übergibt die globale PolicyObservation an self.policy.make_decision(...)
│   └── aktuelle Standardimplementierung: GeneratorSelectorPolicy
├── erhält von dieser Policy eine ID-basierte PolicyDecision zurück
├── löst deren IDs zu echten Laufzeitobjekten des Simulationskerns auf
└── legt jede SimulationAction in den Action-Store ihres Zielobjekts
        │
        ▼
SimMachine / SimRobotMain / SimRobotCorridorArm / SimOrderJob
```

Die Policyseite liegt dabei zwischen Beobachtung und Rückgabe der Entscheidung:

```text
SimulationBridge
└── PolicyObservation
        │
        ▼
GeneratorSelectorPolicy
├── gibt objektbezogene PolicyObservations an den SpineActionGenerator
├── gibt dessen Aktionskandidaten an den ActionSelector
└── gibt die resultierende PolicyDecision an die SimulationBridge zurück
        │
        ▼
SimulationBridge
└── SimulationActions an die wartenden Simulationsobjekte
```

Die Policy erhält keine echten Salabim- oder Konfigurationsobjekte.

## __init__()

### Policy

```python
self.policy = policy if policy is not None else GeneratorSelectorPolicy()
```

Ohne übergebene Policy verwendet die Bridge die `GeneratorSelectorPolicy`.
Später kann hier eine andere Policy, etwa für Heuristik oder RL, eingesetzt
werden.

### policy_trigger_store

```python
self.policy_trigger_store = sim.Store(
    "simulation bridge policy triggers",
    env=self.env,
)
```

```text
Simulationsobjekt
└── PolicyTrigger erzeugen
        │
        ▼
policy_trigger_store
        │
        ▼
SimulationBridge.process()
```

### Registrierungs-Dictionaries

```text
sim_action_stores
└── Simulationsobjekt → persönlicher Action-Store
    SimMachine (simmachine.0)
    → Store (simmachine.0 simulation actions)

policy_object_id_to_simulation_object
└── Policy-ID → echtes Simulationsobjekt
    "SimMachine:Machine 1.1.1:left"
    → SimMachine (simmachine.0)

simulation_object_to_policy_object_id
└── echtes Simulationsobjekt → Policy-ID
    SimMachine (simmachine.0)
    → "SimMachine:Machine 1.1.1:left"

policy_store_id_to_simulation_store
└── Policy-Store-ID → echter Salabim-Store
    "Machine 1.1.1 in"
    → Store (Machine 1.1.1 in)
```

Die beiden Objekt-Dictionaries werden für beide Richtungen benötigt:

```text
Simulation → Policy
└── simulation_object_to_policy_object_id

Policy → Simulation
└── policy_object_id_to_simulation_object
```

### Konfigurationsregister

```python
self.operations_by_id = {}
self.machines_by_id = {}
self.product_types_by_id = {}
self.tool_types_by_id = {}
```

Diese Dictionaries ordnen IDs den echten Konfigurationsobjekten zu. Sie bleiben
auf der Bridge-/Simulationsseite und dienen später der Payload-Umwandlung.

### Wartende Objekte

```python
self.sim_objects_waiting_for_action: set[sim.Component] = set()
```

Das Set enthält Objekte, die eine Aktion angefordert, aber noch keine
ausführbare `SimulationAction` erhalten haben. Ein `set` verhindert doppelte
Einträge desselben Objekts.

### Zähler

```text
_policy_trigger_event_number
└── policy_trigger_1, policy_trigger_2, ...

_action_event_number
└── action_1, action_2, ...

_simulation_state_version
└── globaler Meldungsstand der Bridge
```

---

**Registrierungsmethoden**

## Register

Die Registrierung findet beim Erzeugen der Simulationsobjekte statt. Jedes
Objekt ruft die passende Registrierungsmethode in seinem Konstruktor einmal
auf.

```text
Aufbau der Simulation
│
├── SimCorridor.__init__()
│   └── bridge.register_corridor(...)
│       ├── registriert den echten SimCorridor unter seiner Policy-ID
│       └── ruft für main-, left- und right-Store jeweils register_store() auf
│
├── SimMachine.__init__()
│   └── bridge.register(..., stores=[store_in, store_out])
│       ├── registriert die Maschine und erzeugt ihren Action-Store
│       └── ruft für store_in und store_out jeweils register_store() auf
│
├── SimRobotMain.__init__()
│   └── bridge.register(..., stores=[store_start, store_end])
│       ├── registriert den Main-Roboter und erzeugt seinen Action-Store
│       └── ruft für Start- und End-Store jeweils register_store() auf
│
├── SimRobotCorridorArm.__init__()
│   └── bridge.register(...)
│       └── registriert den Arm und erzeugt seinen Action-Store
│           └── keine Stores übergeben → register_store() wird nicht aufgerufen
│
└── SimOrderJob.__init__()
    └── bridge.register(...)
        └── registriert den Job und erzeugt seinen Action-Store
            └── keine Stores übergeben → register_store() wird nicht aufgerufen
```

`register_store()` wird in der aktuellen Architektur also indirekt von
`register()` und `register_corridor()` aufgerufen. Die Simulationsobjekte
übergeben ihre Stores als Liste an eine dieser beiden Methoden.

### Ziel der Registrierung

Vor dem eigentlichen Simulationsablauf werden einmalig alle Verbindungen
zwischen Policy-IDs und echten Laufzeitobjekten aufgebaut:

```text
Policy-ID → echtes Simulationsobjekt
echtes Simulationsobjekt → Policy-ID
Simulationsobjekt → persönlicher Action-Store
Policy-Store-ID → echter Salabim-Store
```

Danach verwendet die Bridge diese bestehenden Register während der gesamten
Simulation zum Erzeugen von Snapshots, Umwandeln von IDs und Zustellen von
Aktionen. Die Register werden nicht bei
jedem Snapshot oder bei jeder Aktion neu aufgebaut.

### Unterschied zwischen Registrierungsmethoden und Registern

`register()`, `register_corridor()` und `register_store()` sind Methoden. Sie
sind selbst keine Register und keine Dictionaries. Ihre Aufgabe ist es, die
Registrierungs-Dictionaries zu befüllen.

```text
Registrierungsmethoden
├── register()
├── register_corridor()
└── register_store()
        │
        ▼
befüllen die Registrierungs-Dictionaries
```

Die eigentlichen dauerhaft gespeicherten Register sind diese vier
Python-Dictionaries:

```python
self.sim_action_stores: dict[sim.Component, sim.Store] = {}
self.policy_object_id_to_simulation_object: dict[str, sim.Component] = {}
self.simulation_object_to_policy_object_id: dict[sim.Component, str] = {}
self.policy_store_id_to_simulation_store: dict[str, sim.Store] = {}
```

```text
sim_action_stores
└── Simulationsobjekt → persönlicher Action-Store

policy_object_id_to_simulation_object
└── Policy-ID → echtes Simulationsobjekt

simulation_object_to_policy_object_id
└── echtes Simulationsobjekt → Policy-ID

policy_store_id_to_simulation_store
└── Policy-Store-ID → echter Salabim-Store
```

```text
einmaliger Simulationsaufbau
└── Registrierungsmethoden befüllen die Dictionaries
        │
        ▼
laufende Simulation
└── Bridge liest und verwendet die bestehenden Dictionary-Einträge
```

### register(policy_object_id, simulation_object, stores=None)

Registriert ein aktionsfähiges Simulationsobjekt.

Aktueller Code:

```python
def register(
    self,
    policy_object_id: str,
    simulation_object: sim.Component,
    stores: list[sim.Store] | None = None,
):
    registration_is_allowed = self.can_register_policy_object(
        policy_object_id,
        simulation_object,
    )
    if registration_is_allowed is False:
        return

    self.policy_object_id_to_simulation_object[
        policy_object_id
    ] = simulation_object

    self.simulation_object_to_policy_object_id[
        simulation_object
    ] = policy_object_id

    self.sim_action_stores[simulation_object] = sim.Store(
        f"{simulation_object.name()} simulation actions",
        env=self.env,
    )

    for store in stores or []:
        self.register_store(store)
```

Zeilenweise Bedeutung:

```text
can_register_policy_object(...)
└── prüft, ob Policy-ID und Simulationsobjekt noch nicht widersprüchlich
    registriert wurden

if registration_is_allowed is False:
    return
└── ist die Registrierung nicht frei, wird register() sofort beendet
    und kein Dictionary verändert

policy_object_id_to_simulation_object[policy_object_id] = simulation_object
└── speichert die Umwandlungsrichtung Policy → Simulation
    "Main robot" → SimRobotMain (simrobotmain.0)

simulation_object_to_policy_object_id[simulation_object] = policy_object_id
└── speichert die umgekehrte Richtung Simulation → Policy
    SimRobotMain (simrobotmain.0) → "Main robot"

sim_action_stores[simulation_object] = sim.Store(...)
└── erzeugt genau für dieses Simulationsobjekt seinen persönlichen
    Action-Store

for store in stores or []:
└── wenn stores eine Liste ist, wird jeder darin enthaltene echte Store
    einzeln registriert

stores or []
└── stores ist eine Liste → diese Liste verwenden
└── stores ist None → leere Liste verwenden; Schleife läuft keinmal
```

```python
self.bridge.register(
    "SimMachine:Machine 1.1.1:left",
    sim_machine,
    stores=[sim_machine.store_in, sim_machine.store_out],
)
```

Dabei entstehen:

```text
1. Policy-ID → Simulationsobjekt
2. Simulationsobjekt → Policy-ID
3. Simulationsobjekt → persönlicher Action-Store
4. optional: Policy-Store-ID → echter Store
```

Der persönliche Action-Store wird nur einmal beim Registrieren erzeugt:

```python
self.sim_action_stores[simulation_object] = sim.Store(
    f"{simulation_object.name()} simulation actions",
    env=self.env,
)
```

#### Konkreter echter register()-Fall: SimMachine

Die erste Maschine auf der linken Seite von `Corridor 1.1` wird erzeugt. Das
echte Laufzeitobjekt lautet beispielsweise:

```text
SimMachine (simmachine.0)
```

Seine Policy-ID und seine beiden echten Stores sind:

```text
policy_object_id
└── "SimMachine:Machine 1.1.1:left"

simulation_object
└── SimMachine (simmachine.0)

stores
├── Store (Machine 1.1.1 in)
└── Store (Machine 1.1.1 out)
```

Die `SimMachine` ruft in ihrem Konstruktor auf:

```python
self.bridge.register(
    "SimMachine:Machine 1.1.1:left",
    self,
    stores=[self.store_in, self.store_out],
)
```

Zu diesem Zeitpunkt ist `self` das echte Objekt:

```text
self = SimMachine (simmachine.0)
```

`can_register_policy_object(...)` findet weder die Policy-ID noch das Objekt:

```text
policy_object_id_is_registered = False
simulation_object_is_registered = False
registration_is_allowed = True
```

Deshalb führt `register()` die Registrierung aus. Danach enthalten die vier
Bridge-Dictionaries folgende neue Einträge:

```text
policy_object_id_to_simulation_object
└── "SimMachine:Machine 1.1.1:left"
    → SimMachine (simmachine.0)

simulation_object_to_policy_object_id
└── SimMachine (simmachine.0)
    → "SimMachine:Machine 1.1.1:left"

sim_action_stores
└── SimMachine (simmachine.0)
    → Store (simmachine.0 simulation actions)

policy_store_id_to_simulation_store
├── "Machine 1.1.1 in"
│   → Store (Machine 1.1.1 in)
└── "Machine 1.1.1 out"
    → Store (Machine 1.1.1 out)
```

Das Ergebnis aus Sicht beider Seiten:

```text
Policyseite
├── kennt "SimMachine:Machine 1.1.1:left"
├── kennt "Machine 1.1.1 in"
└── kennt "Machine 1.1.1 out"

Bridge und Simulationskern
├── kennen SimMachine (simmachine.0)
├── kennen die beiden echten sim.Store-Objekte
└── besitzen den persönlichen Action-Store der Maschine
```

Die Policy erhält dabei nicht die echten Objekte. Die Bridge kann ihre IDs
später bei einer ausgewählten Aktion wieder in diese Objekte umwandeln.

### register_corridor(...)

Der `SimCorridor` wird für die interne ID-Umwandlung registriert, besitzt aber
keinen eigenen Action-Store:

```python
bridge.register_corridor(
    corridor.name,
    sim_corridor,
    stores=[store_main, store_left, store_right],
)
```

```text
SimCorridor
├── Policy-ID → echter SimCorridor
├── registriert main-, left- und right-Store
└── kein persönlicher Action-Store
```

#### Konkreter echter register_corridor()-Fall: Corridor 1.1

Der erste Corridor im ersten Layout wird als echtes Simulationsobjekt erzeugt:

```text
policy_object_id
└── "Corridor 1.1"

simulation_corridor
└── SimCorridor (simcorridor.0)

stores
├── Store (Corridor 1.1 main)
├── Store (Corridor 1.1 left)
└── Store (Corridor 1.1 right)
```

Die Zahlen im Namen bedeuten:

```text
Corridor 1.1
         │ │
         │ └── erster Corridor innerhalb des Layouts
         └── erstes Layout
```

Der konkrete Aufruf in `SimCorridor.__init__()` lautet:

```python
bridge.register_corridor(
    "Corridor 1.1",
    self,
    stores=[
        self.store_main,
        self.store_left,
        self.store_right,
    ],
)
```

Dabei ist:

```text
self = SimCorridor (simcorridor.0)
```

Nach der Registrierung enthält die Bridge:

```text
policy_object_id_to_simulation_object
└── "Corridor 1.1"
    → SimCorridor (simcorridor.0)

policy_store_id_to_simulation_store
├── "Corridor 1.1 main"
│   → Store (Corridor 1.1 main)
├── "Corridor 1.1 left"
│   → Store (Corridor 1.1 left)
└── "Corridor 1.1 right"
    → Store (Corridor 1.1 right)
```

Im Gegensatz zu `register()` erzeugt `register_corridor()` keinen Eintrag in:

```text
sim_action_stores
```

Der Grund: `SimCorridor (simcorridor.0)` fordert selbst keine Policyaktion an
und benötigt deshalb keinen persönlichen Action-Store. Aktionen fordern seine
beiden `SimRobotCorridorArm`-Objekte an.

Der konkrete Zustand ist damit:

```text
Corridor 1.1
├── als echtes SimCorridor-Objekt für die interne ID-Umwandlung registriert
├── drei Corridor-Stores einmalig bei der Bridge registriert
└── kein Action-Store für den Corridor selbst
```

### register_store(store)

Der Salabim-Name des Stores wird zur Policy-Store-ID:

```python
policy_store_id = store.name()
```

Beispiele:

```text
"Corridor 1.1 main"  → Store (Corridor 1.1 main)
"Corridor 1.1 left"  → Store (Corridor 1.1 left)
"Corridor 1.1 right" → Store (Corridor 1.1 right)
"Machine 1.1.1 in"  → Store (Machine 1.1.1 in)
"Machine 1.1.1 out" → Store (Machine 1.1.1 out)
"start"              → Store (start)
"end"                → Store (end)
```

Ist eine Store-ID bereits registriert, beendet sich die Methode ohne erneutes
Überschreiben.

### can_register_policy_object(...)

Diese Hilfsmethode wird vor jeder Objektregistrierung aufgerufen:

```text
register(...)
└── für SimMachine, SimRobotMain, SimRobotCorridorArm und SimOrderJob

register_corridor(...)
└── für SimCorridor ohne persönlichen Action-Store
```

Die Methode prüft nur und verändert selbst kein Dictionary.

```text
Weder die Policy-ID noch das Simulationsobjekt ist vorhanden.
→ Das Objekt kann registriert werden.
```

Aktueller vereinfachter Code:

```python
def can_register_policy_object(
    self,
    policy_object_id: str,
    simulation_object: sim.Component,
) -> bool:
    policy_object_id_is_registered = policy_object_id in self.policy_object_id_to_simulation_object
    simulation_object_is_registered = simulation_object in self.simulation_object_to_policy_object_id

    if policy_object_id_is_registered:
        return False
    elif simulation_object_is_registered:
        return False
    else:
        return True
```

#### Eingaben

```text
policy_object_id
└── gewünschte Policy-ID
    Beispiel: "Main robot"

simulation_object
└── echtes Salabim-Objekt
    Beispiel: SimRobotMain (simrobotmain.0)
```

#### Erste boolesche Prüfung

```python
policy_object_id_is_registered = policy_object_id in self.policy_object_id_to_simulation_object
```

`in` prüft, ob die Policy-ID als Key im Dictionary vorhanden ist:

```text
policy_object_id_to_simulation_object = {
    "Main robot": SimRobotMain (simrobotmain.0)
}

policy_object_id = "Main robot"
└── policy_object_id_is_registered = True

policy_object_id = "Order 1.1:0"
└── policy_object_id_is_registered = False
```

#### Zweite boolesche Prüfung

```python
simulation_object_is_registered = simulation_object in self.simulation_object_to_policy_object_id
```

Hier wird geprüft, ob das echte Simulationsobjekt bereits als Key in der
umgekehrten Zuordnung vorhanden ist:

```text
simulation_object_to_policy_object_id = {
    SimRobotMain (simrobotmain.0): "Main robot"
}

simulation_object = SimRobotMain (simrobotmain.0)
└── simulation_object_is_registered = True

simulation_object = SimOrderJob (simorderjob.0)
└── simulation_object_is_registered = False
```

#### if/elif/else

```python
if policy_object_id_is_registered:
    return False
```

Die gewünschte Policy-ID ist bereits belegt. Die Registrierung wird abgelehnt.

```python
elif simulation_object_is_registered:
    return False
```

Die Policy-ID ist frei, aber das echte Simulationsobjekt ist bereits unter
einer anderen ID registriert. Die Registrierung wird ebenfalls abgelehnt.

```python
else:
    return True
```

Weder ID noch Objekt wurden gefunden. Die Registrierung darf fortgesetzt
werden.

#### Konkrete Fälle

```text
Fall 1: neue ID und neues Objekt
├── policy_object_id_is_registered = False
├── simulation_object_is_registered = False
└── Rückgabe = True

Fall 2: ID bereits vorhanden
├── policy_object_id_is_registered = True
└── Rückgabe = False

Fall 3: ID ist neu, Objekt ist aber bereits vorhanden
├── policy_object_id_is_registered = False
├── simulation_object_is_registered = True
└── Rückgabe = False
```

Der Aufrufer verwendet das Ergebnis so:

```python
registration_is_allowed = self.can_register_policy_object(
    policy_object_id,
    simulation_object,
)
if registration_is_allowed is False:
    return
```

```text
registration_is_allowed = True
└── Bedingung `is False` ist nicht erfüllt
    └── register() schreibt die neue Registrierung

registration_is_allowed = False
└── Bedingung `is False` ist erfüllt
    └── return beendet register() ohne Änderung
```

---

## Aktionsanforderung und Zustandsmeldung

Dieser Kommunikationsweg führt von einem Simulationsobjekt zur Bridge:

```text
Simulationsobjekt
├── request_action(sender)      → benötigt eine neue Aktion
└── notify_state_change(sender) → meldet nur eine Zustandsänderung
        │
        ▼
SimulationBridge
└── erzeugt einen PolicyTrigger im policy_trigger_store
```

### request_action(sender)

```python
def request_action(self, sender):
    self.sim_objects_waiting_for_action.add(sender)
    return self.notify_state_change(sender)
```

```text
yield bridge.request_action(self)
├── Sender im Waiting-Set markieren
├── Zustandsversion erhöhen
├── PolicyTrigger erzeugen
└── Trigger in policy_trigger_store legen
```

Dieses `yield` wartet nur auf das erfolgreiche Einlegen des Triggers. Danach
wartet das Simulationsobjekt mit der nächsten Zeile auf seine Aktion:

```python
action = yield self.bridge.action(self)
```

### notify_state_change(sender)

Diese Methode meldet eine Zustandsänderung, markiert den Sender aber nicht
automatisch als aktionswartend:

```text
1. _simulation_state_version += 1
2. neue Trigger-ID erzeugen
3. Policy-ID des Senders bestimmen
4. PolicyTrigger erzeugen
5. Trigger in policy_trigger_store legen
```

Beispiel:

```text
PolicyTrigger
├── event_id      = "policy_trigger_8"
├── sender_id     = "Order 1.1:0"
├── state_version = 8
└── time          = 0.0
```

Die `state_version` ist eine Kopie des globalen Bridge-Zählers zum Zeitpunkt
der Meldung, keine eigene Version des Jobs.

---

## Policy Observation

### Tatsächliche Aufrufreihenfolge

```text
SimulationBridge.process()
        │
        ▼
create_policy_observation(policy_triggers)
        │
        ▼
build_policy_simulation_snapshot()
        │
        ├── beim ersten Snapshot:
        │       build_policy_configuration_model()
        │
        └── erzeugt:
            ├── time
            ├── state_version
            ├── states_by_id
            └── model
        │
        ▼
create_policy_observation(...)
ergänzt:
├── policy_trigger_event_ids
└── policy_trigger_sender_ids
        │
        ▼
PolicyObservation
        │
        ▼
GeneratorSelectorPolicy.decide(...)
```

An die Policy wird nur das fertige `PolicyObservation`-Objekt übergeben. Die
beiden anderen Methoden werden intern beim Erzeugen dieser Observation
aufgerufen.

### build_policy_configuration_model()

```text
echte Konfigurationsobjekte
├── PRODUCT_TYPES
├── OPERATION_TYPES
├── MACHINES
├── TOOL_TYPES
├── CORRIDORS
└── LAYOUTS
        │
        ▼
ConfigurationObjectObserver.build_policy_configuration_model(...)
        │
        ▼
reine Dictionaries, IDs und Werte in snapshot["configuration_model"]
```

Die echten Konfigurationsobjekte bleiben in den Bridge-Registern, um
Policy-IDs später wieder aufzulösen.

Konkrete Rückgabe für ausgewählte Konfigurationsobjekte aus `example-0.py`:

```python
{
    "product_types_by_id": {
        "Rohes Werkstück": {
            "product_type_id": "Rohes Werkstück",
            "length": 12,
            "width": 12,
            "depth": 12,
            "weight": 5,
        },
        "Poliertes Werkstück": {
            "product_type_id": "Poliertes Werkstück",
            "length": 12,
            "width": 24,
            "depth": 11,
            "weight": 10,
        },
    },
    "operations_by_id": {
        "Rohes Werkstück schleifen": {
            "operation_id": "Rohes Werkstück schleifen",
            "duration": 1,
            "consumed_life_units": 10,
            "defect_probability": 0.20,
            "machine_type_id": "Schleifmaschine",
            "tool_type_id": "Schleifwerkzeug",
            "consumes_product_type_id": "Rohes Werkstück",
            "produces_product_type_id": "Geschliffenes Werkstück",
        },
    },
    "machines_by_id": {
        "Poliermaschine A": {
            "machine_id": "Poliermaschine A",
            "machine_type_id": "Poliermaschine",
            "corridor_id": "Bearbeitungskorridor",
            "layout_id": "Beispiellayout",
            "left": True,
            "storage_capacity": 10,
            "dummy_tool_mount_time": 1.0,
            "dummy_tool_unmount_time": 1.0,
            "tool_type_ids": [
                "Polierwerkzeug",
                "Polierwerkzeug fein",
                "Polierwerkzeug grob",
                "Polierwerkzeug weich",
                "Polierwerkzeug hart",
            ],
        },
    },
    "tools_by_id": {
        "Schleifwerkzeug": {
            "tool_type_id": "Schleifwerkzeug",
            "mount_time": 1,
            "unmount_time": 2,
            "total_life_units": 25,
        },
    },
    "corridors_by_id": {
        "Bearbeitungskorridor": {
            "corridor_id": "Bearbeitungskorridor",
            "layout_id": "Beispiellayout",
            "storage_capacity": 200,
            "storage_out_time": 2,
            "storage_in_time": 3,
            "machine_ids": [
                "Poliermaschine A",
                "Schleifmaschine A",
                "Fräsmaschine A",
                "Poliermaschine B",
                "Schleifmaschine B",
                "Fräsmaschine B",
            ],
        },
    },
    "layouts_by_id": {
        "Beispiellayout": {
            "layout_id": "Beispiellayout",
            "storage_capacity": 1000,
            "storage_out_time": 10,
            "storage_in_time": 5,
            "corridor_ids": ["Bearbeitungskorridor"],
        },
    },
}
```

Das echte vollständige Dictionary enthält nach demselben Aufbau alle in der
Konfiguration vorhandenen Produkte, Operationen, Maschinen, Werkzeuge,
Korridore und Layouts. Oben wurde pro Bereich nur ein repräsentativer Eintrag
gezeigt, damit die Struktur lesbar bleibt.

---

**Methoden zum Validieren und Umwandeln einer PolicyDecision**

### build_policy_simulation_snapshot()

Beim ersten Aufruf wird einmalig das statische Modell erzeugt:

```python
if self.policy_model is None:
    self.policy_model = self.build_policy_configuration_model()
```

Der globale Snapshot besitzt folgende Hauptstruktur:

```text
simulation_configuration_snapshot
├── time
├── state_version
├── states_by_id
└── model
```

Für jedes aktionsfähige Objekt wird der aktuelle Zustand beobachtet:

```python
observation = SimulationObjectObserver.observe_simulation_object(
    sim_object,
    self.env.now(),
)
```

Danach ergänzt die Bridge:

```python
observation["is_waiting_for_action"] = (
    sim_object in self.sim_objects_waiting_for_action
)
```

Beispiel:

```text
states_by_id
├── object_id = "Main robot"
│   └── object_state aus observe_main_robot()
│       └── is_waiting_for_action = True
├── object_id = "SimMachine:Machine 1.1.1:left"
│   └── object_state aus observe_machine()
│       └── is_waiting_for_action = False
└── object_id = "Order 1.1:0"
    └── object_state aus observe_order_job()
        └── is_waiting_for_action = True
```

Store-Zustände und Job-Zusammenfassungen werden von den Observer-Methoden als
reine Daten in die Objektzustände eingebettet.

#### Konkrete Ausgabe von `build_policy_simulation_snapshot()`

Beispiel bei Simulationszeit `t = 11.0`:

```python
{
    "time": 11.0,
    "state_version": 14,
    "simulation_object_states_by_id": {
        "Main robot": {
            "object_type": "main_robot",
            "object_id": "Main robot",
            "time": 11.0,
            "layout_id": "Beispiellayout",
            "scenario_id": "Beispielszenario mit drei Produktionswegen",
            "x": 0,
            "y": 0,
            "z": 2.5,
            "move_state": "waiting",
            "load_state": "empty",
            "is_loaded": False,
            "is_empty": True,
            "movement_speed": None,
            "current_job_id": None,
            "start_store_id": "start",
            "end_store_id": "end",
            "start_storage": {
                "store_id": "start",
                "count": 2,
                "capacity": 1000,
                "available_capacity": 998,
                "is_empty": False,
                "has_items": True,
                "job_ids": [
                    "Auftrag poliertes Werkstück:0",
                    "Auftrag poliertes Werkstück:1",
                ],
            },
            "end_storage": {
                "store_id": "end",
                "count": 0,
                "capacity": 1000,
                "available_capacity": 1000,
                "is_empty": True,
                "has_items": False,
                "job_ids": [],
            },
            "corridor_storages": [
                {
                    "corridor_index": 0,
                    "corridor_id": "Bearbeitungskorridor",
                    "main": {
                        "store_id": "Bearbeitungskorridor main",
                        "count": 0,
                        "capacity": 200,
                        "job_ids": [],
                    },
                    "left": {
                        "store_id": "Bearbeitungskorridor left",
                        "count": 0,
                        "capacity": 200,
                        "job_ids": [],
                    },
                    "right": {
                        "store_id": "Bearbeitungskorridor right",
                        "count": 0,
                        "capacity": 200,
                        "job_ids": [],
                    },
                }
            ],
            "is_waiting_for_action": True,
        },
        "SimMachine:Poliermaschine A:left": {
            "object_type": "machine",
            "object_id": "SimMachine:Poliermaschine A:left",
            "time": 11.0,
            "machine_name": "Poliermaschine A",
            "machine_type_id": "Poliermaschine",
            "corridor_id": "Bearbeitungskorridor",
            "left": True,
            "state": "waiting",
            "processing_speed_factor": None,
            "is_idle": True,
            "has_current_job": False,
            "mounted_tool_type_id": None,
            "dummy_tool_mounted": True,
            "current_job_id": None,
            "input_storage": {
                "store_id": "Poliermaschine A in",
                "count": 0,
                "capacity": 10,
                "job_ids": [],
            },
            "output_storage": {
                "store_id": "Poliermaschine A out",
                "count": 0,
                "capacity": 10,
                "job_ids": [],
            },
            "is_waiting_for_action": False,
        },
        "Auftrag poliertes Werkstück:0": {
            "object_type": "order_job",
            "object_id": "Auftrag poliertes Werkstück:0",
            "time": 11.0,
            "job_id": "Auftrag poliertes Werkstück:0",
            "number": 0,
            "layout_id": "Beispiellayout",
            "scenario_id": "Beispielszenario mit drei Produktionswegen",
            "order_id": "Auftrag poliertes Werkstück",
            "start_store_id": "start",
            "target_product_type_id": "Poliertes Werkstück",
            "quantity": 2,
            "earliest_start_time": 11,
            "latest_end_time": 20,
            "released": True,
            "queue_priority": 0.17,
            "processing_state": "Rohes Werkstück",
            "general_state": "intact",
            "due_state": None,
            "completed_time": None,
            "selected_operation_id": None,
            "selected_machine_id": None,
            "is_waiting_for_action": True,
        },
    },
    "configuration_model": {
        "product_types_by_id": {
            "Rohes Werkstück": {
                "product_type_id": "Rohes Werkstück",
                "length": 12,
                "width": 12,
                "depth": 12,
                "weight": 5,
            }
        },
        "operations_by_id": {
            "Rohes Werkstück schleifen": {
                "operation_id": "Rohes Werkstück schleifen",
                "duration": 1,
                "consumed_life_units": 10,
                "defect_probability": 0.20,
                "machine_type_id": "Schleifmaschine",
                "tool_type_id": "Schleifwerkzeug",
                "consumes_product_type_id": "Rohes Werkstück",
                "produces_product_type_id": "Geschliffenes Werkstück",
            }
        },
        "machines_by_id": {
            "Poliermaschine A": {
                "machine_id": "Poliermaschine A",
                "machine_type_id": "Poliermaschine",
                "corridor_id": "Bearbeitungskorridor",
                "layout_id": "Beispiellayout",
                "left": True,
            }
        },
        "tools_by_id": {
            "Schleifwerkzeug": {
                "tool_type_id": "Schleifwerkzeug",
                "mount_time": 1,
                "unmount_time": 2,
                "total_life_units": 25,
            }
        },
        "corridors_by_id": {
            "Bearbeitungskorridor": {
                "corridor_id": "Bearbeitungskorridor",
                "layout_id": "Beispiellayout",
                "machine_ids": [
                    "Poliermaschine A",
                    "Schleifmaschine A",
                    "Fräsmaschine A",
                    "Poliermaschine B",
                    "Schleifmaschine B",
                    "Fräsmaschine B",
                ],
            }
        },
        "layouts_by_id": {
            "Beispiellayout": {
                "layout_id": "Beispiellayout",
                "corridor_ids": ["Bearbeitungskorridor"],
            }
        },
    },
}
```

Im wirklichen Snapshot stehen unter `states_by_id` alle registrierten
aktionsfähigen Simulationsobjekte. Oben werden zur besseren Lesbarkeit nur der
Main-Roboter, eine Maschine und ein Job gezeigt. `model` ist das statische
Dictionary aus `build_policy_configuration_model()` und wird nicht bei jedem Snapshot neu
berechnet.

### create_policy_observation(policy_triggers)

Die Methode ergänzt:

```text
policy_trigger_event_ids
└── ["policy_trigger_1", "policy_trigger_2"]

policy_trigger_sender_ids
└── ["Machine 1", "Main robot"]
```

Danach wird der Snapshot verpackt:

```python
PolicyObservation(
    simulation_configuration_snapshot=snapshot,
    current_object_id=None,
)
```

In der globalen Bridge-Observation ist `current_object_id` `None`. Die
`GeneratorSelectorPolicy` setzt sie später für jedes wartende Objekt.

### Konkretes Beispiel

Die Bridge hat beispielsweise zwei Trigger derselben Simulationszeit
gesammelt:

```python
policy_triggers = [
    PolicyTrigger(
        event_id="policy_trigger_13",
        sender_id="Auftrag poliertes Werkstück:0",
        state_version=13,
        time=11.0,
    ),
    PolicyTrigger(
        event_id="policy_trigger_14",
        sender_id="Main robot",
        state_version=14,
        time=11.0,
    ),
]
```

`create_policy_observation(policy_triggers)` erzeugt daraus folgende globale
Observation. Die Zustände und das Modell entsprechen dem konkreten Snapshot
aus dem vorherigen Abschnitt:

```python
PolicyObservation(
    simulation_configuration_snapshot={
        "time": 11.0,
        "state_version": 14,
        "simulation_object_states_by_id": {
            "Main robot": {
                "object_type": "main_robot",
                "object_id": "Main robot",
                "move_state": "waiting",
                "load_state": "empty",
                "current_job_id": None,
                "start_storage": {
                    "store_id": "start",
                    "count": 2,
                    "job_ids": [
                        "Auftrag poliertes Werkstück:0",
                        "Auftrag poliertes Werkstück:1",
                    ],
                },
                "is_waiting_for_action": True,
            },
            "SimMachine:Poliermaschine A:left": {
                "object_type": "machine",
                "object_id": "SimMachine:Poliermaschine A:left",
                "state": "waiting",
                "current_job_id": None,
                "is_waiting_for_action": False,
            },
            "Auftrag poliertes Werkstück:0": {
                "object_type": "order_job",
                "object_id": "Auftrag poliertes Werkstück:0",
                "processing_state": "Rohes Werkstück",
                "general_state": "intact",
                "released": True,
                "is_waiting_for_action": True,
            },
        },
        "configuration_model": {
            "product_types_by_id": {
                "Rohes Werkstück": {
                    "product_type_id": "Rohes Werkstück",
                    "length": 12,
                    "width": 12,
                    "depth": 12,
                    "weight": 5,
                }
            },
            "operations_by_id": {
                "Rohes Werkstück schleifen": {
                    "operation_id": "Rohes Werkstück schleifen",
                    "machine_type_id": "Schleifmaschine",
                    "tool_type_id": "Schleifwerkzeug",
                    "consumes_product_type_id": "Rohes Werkstück",
                    "produces_product_type_id": "Geschliffenes Werkstück",
                }
            },
            "machines_by_id": {
                "Poliermaschine A": {
                    "machine_id": "Poliermaschine A",
                    "corridor_id": "Bearbeitungskorridor",
                    "layout_id": "Beispiellayout",
                    "left": True,
                }
            },
            "tools_by_id": {
                "Schleifwerkzeug": {
                    "tool_type_id": "Schleifwerkzeug",
                    "mount_time": 1,
                    "unmount_time": 2,
                    "total_life_units": 25,
                }
            },
            "corridors_by_id": {
                "Bearbeitungskorridor": {
                    "corridor_id": "Bearbeitungskorridor",
                    "layout_id": "Beispiellayout",
                }
            },
            "layouts_by_id": {
                "Beispiellayout": {
                    "layout_id": "Beispiellayout",
                    "corridor_ids": ["Bearbeitungskorridor"],
                }
            },
        },
        "policy_trigger_event_ids": [
            "policy_trigger_13",
            "policy_trigger_14",
        ],
        "policy_trigger_sender_ids": [
            "Auftrag poliertes Werkstück:0",
            "Main robot",
        ],
    },
    current_object_id=None,
)
```

Der Unterschied zur direkten Ausgabe von
`build_policy_simulation_snapshot()` sind hier die beiden zusätzlich
eingefügten Listen:

```text
policy_trigger_event_ids  = IDs der gebündelten Trigger
policy_trigger_sender_ids = Policy-IDs ihrer auslösenden Simulationsobjekte
```

Danach verpackt die Methode das Dictionary in ein `PolicyObservation`-Objekt.
Sie filtert noch kein einzelnes Objekt heraus. Deshalb ist
`current_object_id=None` und `states_by_id` enthält weiterhin alle beobachteten
Simulationsobjekte.

## PolicyDecision → SimulationAction

```text
konfliktfreie PolicyDecision mit Policy-IDs
│
├── create_simulation_actions(decision, source_policy_trigger_id)
│   ├── Policy-IDs unmittelbar in echte Objekte umwandeln
│   ├── Policy-ID-Keys aus dem kopierten Payload entfernen
│   └── ausführbare SimulationAction-Objekte erzeugen
│
└── action(target)
    └── wartendes Simulationsobjekt empfängt seine SimulationAction
```

### Verantwortung vor der Bridge

Die `GeneratorSelectorPolicy` liefert bereits eine konfliktfreie
`PolicyDecision`. Wait-Aktionen, doppelte Zielobjekte und doppelt ausgewählte
Jobs wurden auf der Policy-Seite anhand der `PolicyObservation` entfernt.

Die Bridge trifft ab hier keine Auswahl- oder Validierungsentscheidung mehr:

```text
konfliktfreie PolicyDecision mit IDs
        │
        ▼
SimulationBridge
├── create_simulation_actions(...)
└── SimulationAction zustellen
```

### create_simulation_actions(decision, source_policy_trigger_id)

Die Methode verbindet die ID-Umwandlung und die Erzeugung der
`SimulationAction`. Es gibt keine zwischenzeitliche `PolicyDecision`, die
echte Simulationsobjekte enthält.

#### Konkrete Eingabe

```python
decision = PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Main robot",
            action_type="pick_main_robot",
            payload={
                "target_store_id": "start",
                "selected_job_id": "Auftrag poliertes Werkstück:0",
                "movement_speed": 1.0,
            },
        ),
        SelectedObjectAction(
            target_id="CorridorArmRobot:Bearbeitungskorridor:left",
            action_type="pick_corridor_arm_robot",
            payload={
                "target_store_id": "Bearbeitungskorridor main",
                "selected_job_id": "Auftrag poliertes Werkstück:1",
                "movement_speed": 0.5,
            },
        ),
    ]
)

source_policy_trigger_id = "policy_trigger_14"

# Aktuelle Simulationszeit bei diesem Methodenaufruf:
self.env.now()  # ergibt 11.0
```

Konkreter Aufruf:

```python
simulation_actions = self.create_simulation_actions(
    decision,
    source_policy_trigger_id,
)
```

#### Konkrete Ausgabe

Die Methode gibt keine einzelne Aktion zurück, sondern eine Liste mit einer
`SimulationAction` pro `SelectedObjectAction`:

```python
simulation_actions = [
    SimulationAction(
        event_id="action_15",
        target=sim_robot_main,
        source_policy_trigger_id="policy_trigger_14",
        action_type="pick_main_robot",
        time=11.0,
        payload={
            "movement_speed": 1.0,
            "target_store": start_store,
            "selected_job": sim_order_job_0,
        },
        env=self.env,
    ),
    SimulationAction(
        event_id="action_16",
        target=sim_corridor_arm_left,
        source_policy_trigger_id="policy_trigger_14",
        action_type="pick_corridor_arm_robot",
        time=11.0,
        payload={
            "movement_speed": 0.5,
            "target_store": corridor_main_store,
            "selected_job": sim_order_job_1,
        },
        env=self.env,
    ),
]
```

Die Umwandlung ist damit:

```text
PolicyDecision.actions
├── SelectedObjectAction für "Main robot"
│   └── SimulationAction mit target = sim_robot_main
│
└── SelectedObjectAction für linken Corridor-Arm-Roboter
    └── SimulationAction mit target = sim_corridor_arm_left
```

Die beiden erzeugten Aktionen besitzen dieselbe
`source_policy_trigger_id`, weil sie aus demselben gebündelten
Policy-Entscheidungszyklus stammen. Jede Aktion erhält aber durch
`next_action_event_id()` ihre eigene eindeutige `event_id`.

```text
SelectedObjectAction
├── target_id = "Main robot"
├── action_type = "pick_main_robot"
└── ID-basiertes Policy-Payload
        │
        ▼
SimulationAction
├── event_id = "action_12"
├── target = echter SimRobotMain
├── source_policy_trigger_id = "policy_trigger_8"
├── action_type = "pick_main_robot"
├── time = env.now()
└── Payload = echte Objekte, keine aufgelösten Policy-ID-Keys
```

Eine `PolicyDecision` kann mehrere Objektaktionen enthalten. Deshalb gibt die
Methode `list[SimulationAction]` zurück.

### action(target): fertige Aktion beim Simulationsobjekt empfangen

Diese Methode gehört zur Rückrichtung von der Bridge zum Simulationsobjekt.
Sie wird zwar vom Simulationsobjekt bereits unmittelbar nach
`request_action()` aufgerufen, bleibt dort aber blockiert, bis die Bridge die
Policy-Entscheidung erhalten, die IDs aufgelöst und eine `SimulationAction` in
den persönlichen Action-Store gelegt hat.

```python
return target.from_store(self.sim_action_stores[target])
```

```text
PolicyDecision
        │
        ▼
IDs in echte Objekte umwandeln
        │
        ▼
SimulationAction erzeugen
        │
        ▼
persönlicher Action-Store des Zielobjekts
        │
        ▼
action(target)
└── gibt die fertige SimulationAction an das wartende Simulationsobjekt zurück
```

```text
persönlicher Action-Store leer
└── Zielobjekt bleibt am yield blockiert

SimulationAction liegt im Store
└── yield gibt diese Aktion zurück
```

---

**Hilfsmethoden für IDs**

## simulation_object_for_policy_object_id(policy_object_id)

```text
Eingabe:  "Main robot"
Ausgabe:  SimRobotMain (simrobotmain.0)
```

## next_action_event_id()

Die Methode erhöht bei jedem Aufruf den internen Zähler
`self._action_event_number` um eins und erzeugt dadurch für jede
`SimulationAction` eine eindeutige ID.

```text
1. Aufruf → "action_1"
2. Aufruf → "action_2"
3. Aufruf → "action_3"
```

Für die reine Ausführung einer Aktion durch Roboter oder Maschine ist diese ID
aktuell nicht zwingend erforderlich. Sie bleibt trotzdem sinnvoll für:

```text
├── Debugging und Logging
├── Zuordnung eines Fehlers zu einer konkreten Aktion
├── Nachverfolgung der Aktionsreihenfolge
├── Speicherung späterer RL-Transitions
└── Auswertung oder Replay einer Simulation
```

`source_policy_trigger_id` und `event_id` haben verschiedene Aufgaben:

```text
source_policy_trigger_id
└── welcher PolicyTrigger hat den Entscheidungszyklus ausgelöst?

event_id der SimulationAction
└── welche einzelne ausführbare Aktion ist daraus entstanden?
```

Eine Policyentscheidung kann mehrere Aktionen erzeugen. Deshalb können mehrere
Action-IDs dieselbe `source_policy_trigger_id` besitzen:

```text
policy_trigger_14
├── action_15 für Main robot
└── action_16 für Corridor-Arm-Roboter
```

## next_policy_trigger_event_id()

```text
1. Aufruf → "policy_trigger_1"
2. Aufruf → "policy_trigger_2"
```

## process(): Entscheidungszyklus

### Vollständiger aktueller Code

```python
def process(self):
    while True:
        first_policy_trigger = yield self.from_store(
            self.policy_trigger_store
        )

        yield self.hold(0)

        policy_triggers = [first_policy_trigger]

        while self.policy_trigger_store.as_list():
            next_policy_trigger = self.policy_trigger_store.as_list()[0]
            if next_policy_trigger.time != first_policy_trigger.time:
                break
            collected_trigger = yield self.from_store(
                self.policy_trigger_store
            )
            policy_triggers.append(collected_trigger)

        while True:
            policy_snapshot = self.create_policy_observation(policy_triggers)
            selected_action_policy = self.policy.make_decision(policy_snapshot)

            snapshot_state_version = (
                policy_snapshot.simulation_configuration_snapshot[
                    "state_version"
                ]
            )
            if snapshot_state_version == self._simulation_state_version:
                break

        if len(selected_action_policy.actions) == 0:
            continue

        simulation_actions = self.create_simulation_actions(
            selected_action_policy,
            first_policy_trigger.event_id,
        )

        for simulation_action in simulation_actions:
            self.sim_objects_waiting_for_action.remove(
                simulation_action.target
            )
            yield self.to_store(
                self.sim_action_stores[simulation_action.target],
                simulation_action,
            )
```

### Aufbau der beiden while-Schleifen

```text
äußere while True
└── Bridge bleibt während der gesamten Simulation aktiv
    └── jeder Durchlauf verarbeitet einen gebündelten Trigger-Zyklus

innere while True
└── Snapshot und Policyentscheidung wiederholen
    └── endet erst, wenn beide Stände von self._simulation_state_version
        gleich sind
```

`break` in der inneren Schleife beendet nur diese innere Schleife. Der Code
setzt danach mit der bereits konfliktfreien `PolicyDecision` fort. `continue`
auf der Einrückungsebene der äußeren Schleife startet dagegen den nächsten
Trigger-Zyklus und wartet wieder auf einen Trigger.

### 1. Auf den ersten Trigger warten

```python
first_policy_trigger = yield self.from_store(self.policy_trigger_store)
```

Ist der Store leer, ist nur der Bridge-Prozess blockiert. Andere Komponenten
können weiterlaufen.

```text
self.from_store(self.policy_trigger_store)
└── erzeugt eine Salabim-Anforderung zum Entnehmen eines Elements

yield
└── pausiert den Bridge-Prozess, solange der Trigger-Store leer ist

first_policy_trigger = ...
└── sobald ein Trigger vorhanden ist, wird genau dieser PolicyTrigger
    entnommen und in first_policy_trigger gespeichert
```

### 2. Eine Ereignisrunde freigeben

```python
yield self.hold(0)
```

`hold(0)` erhöht die Simulationszeit nicht. Die Bridge wird jedoch für eine
Ereignisrunde zurückgestellt, sodass andere bereits zur gleichen Zeit geplante
Komponenten ihre Trigger einlegen können.

```text
t = 0.0
├── Maschine meldet Trigger
├── Main-Roboter meldet Trigger
├── Job meldet Trigger
└── Bridge wird nach hold(0) erneut ausgeführt
```

`hold(0)` wartet nicht auf zukünftige Trigger mit einer späteren Zeit.

### 3. Trigger derselben Zeit sammeln

```python
policy_triggers = [first_policy_trigger]

while self.policy_trigger_store.as_list():
    next_policy_trigger = self.policy_trigger_store.as_list()[0]
    if next_policy_trigger.time != first_policy_trigger.time:
        break
    collected_trigger = yield self.from_store(self.policy_trigger_store)
    policy_triggers.append(collected_trigger)
```

Ein Trigger mit einer anderen Simulationszeit bleibt für den nächsten Zyklus
im Store.

Zeilenweise Bedeutung:

```text
policy_triggers = [first_policy_trigger]
└── erzeugt eine Liste und legt den ersten Trigger hinein

while self.policy_trigger_store.as_list():
└── Schleife läuft, solange im Trigger-Store mindestens ein Element liegt

self.policy_trigger_store.as_list()[0]
└── betrachtet den ersten noch wartenden Trigger, ohne ihn zu entnehmen

next_policy_trigger.time != first_policy_trigger.time
└── prüft, ob der nächste Trigger zu einer anderen Simulationszeit gehört

break
└── beendet die Sammelschleife; der anderszeitige Trigger bleibt im Store

yield self.from_store(...)
└── entnimmt den Trigger jetzt wirklich aus dem Store

policy_triggers.append(collected_trigger)
└── fügt den entnommenen Trigger am Ende der Sammelliste hinzu
```

### 4. Snapshot und Entscheidung erzeugen

```python
policy_snapshot = self.create_policy_observation(policy_triggers)
selected_action_policy = self.policy.make_decision(policy_snapshot)
```

`selected_action_policy` ist ein Objekt vom Typ `PolicyDecision` und enthält
eine Liste von `SelectedObjectAction`-Objekten.

```text
create_policy_observation(policy_triggers)
└── Bridge erzeugt den globalen Snapshot und ergänzt die gesammelten
    Trigger-IDs und Sender-IDs

self.policy.make_decision(policy_snapshot)
└── Bridge übergibt die globale PolicyObservation an die konfigurierte Policy

Rückgabe
└── Policy gibt eine PolicyDecision an die Bridge zurück
```

### 5. Zustandsversion vergleichen

```python
snapshot_state_version = (
    policy_snapshot.simulation_configuration_snapshot["state_version"]
)

if snapshot_state_version == self._simulation_state_version:
    break
```

`self._simulation_state_version` ist der globale Zustandsänderungszähler der
Bridge. Die Bridge erhöht ihn bei jeder gemeldeten Zustandsänderung der
Simulation. Beim Erzeugen eines Snapshots wird der damalige Zählerstand als
`snapshot["state_version"]` kopiert.

```text
snapshot_state_version
└── im Snapshot gespeicherte Kopie des Bridge-Zählers

self._simulation_state_version
└── aktueller Bridge-Zähler
    └── signalisiert den aktuellen Stand der gemeldeten Zustandsänderungen
```

Beispiel mit gleichen Zählerständen:

```text
Snapshot-Zählerstand = 14
aktueller Bridge-Zählerstand = 14
└── seit der Snapshot-Erzeugung wurde keine neue Zustandsänderung gemeldet
    └── Vergleich ist True
        └── break beendet die innere Schleife
```

Beispiel mit unterschiedlichen Zählerständen:

```text
Snapshot-Zählerstand = 14
aktueller Bridge-Zählerstand = 15
└── nach der Snapshot-Erzeugung wurde eine neue Zustandsänderung gemeldet
    └── Vergleich ist False
        └── kein break
            └── neuen Snapshot und neue Policyentscheidung erzeugen
```

#### Warum wird nicht mit einer Version der PolicyDecision verglichen?

Die `PolicyDecision` besitzt aktuell keine eigene `state_version`. Das ist in
der gegenwärtigen Architektur nicht notwendig, weil sie synchron und direkt
aus genau diesem `policy_snapshot` erzeugt wird:

```text
PolicySnapshot mit state_version = 14
        │
        ▼
policy.make_decision(policy_snapshot)
        │
        ▼
PolicyDecision gehört dadurch zum Snapshot mit Version 14
```

`make_decision()` ist ein normaler synchroner Python-Aufruf. Innerhalb dieses
Aufrufs gibt es kein Salabim-`yield`. Daher kann während der Berechnung keine
andere Simulationskomponente ausgeführt werden und den Simulationszustand
ändern.

Der vorhandene Vergleich reicht deshalb aktuell aus:

```text
state_version des verwendeten PolicySnapshots
        ==
aktueller self._simulation_state_version der Bridge
```

Der vollständige Ablauf bis zur Verteilung ist:

```text
Snapshot erzeugen
        ↓
Policy erzeugt daraus Aktionen
        ↓
Snapshot-Version mit aktuellem Bridge-Zähler vergleichen
        │
        ├── gleich
        │   └── Aktionen gehören zum aktuellen Simulationszustand
        │       └── in SimulationActions umwandeln und verteilen
        │
        └── unterschiedlich
            └── zwischenzeitlich wurde eine Zustandsänderung gemeldet
                └── bisherige Aktionen verwerfen
                    └── neuen Snapshot und neue Aktionen erzeugen
```

Die Bridge verteilt damit nur die Aktionen der neuesten gültigen
Policyentscheidung.

Eine eigene Version in der `PolicyDecision` wäre sinnvoll, wenn die
Policyentscheidung später asynchron erzeugt oder zeitversetzt verwendet wird,
beispielsweise:

```text
├── RL-Agent läuft in einem anderen Prozess
├── Entscheidung wird über ein Netzwerk übertragen
├── Policyberechnung enthält eine Unterbrechung beziehungsweise ein yield
└── PolicyDecision wird zwischengespeichert und später ausgeführt
```

Dann könnte die Schnittstelle erweitert werden:

```python
@dataclass
class PolicyDecision:
    actions: list[SelectedObjectAction]
    source_state_version: int
```

Die Bridge könnte anschließend prüfen:

```python
if selected_action_policy.source_state_version == self._simulation_state_version:
    break
```

Aktuell würde `source_state_version` jedoch nur den bereits vorhandenen Wert
des PolicySnapshots duplizieren.

### 6. Leere PolicyDecision behandeln

```python
if len(selected_action_policy.actions) == 0:
    continue
```

Die `GeneratorSelectorPolicy` hat Wait-Aktionen und Konflikte bereits auf der
Policy-Seite behandelt. Enthält ihre Entscheidung keine ausführbare Aktion,
beginnt die Bridge den nächsten Trigger-Zyklus.

### 7. Policy-IDs direkt beim Erzeugen der SimulationAction umwandeln

```python
simulation_actions = self.create_simulation_actions(
    selected_action_policy,
    first_policy_trigger.event_id,
)
```

Die Bridge erzeugt keine zweite, aufgelöste `PolicyDecision`. Sie kopiert für
jede ausgewählte Aktion das Payload, entfernt darin die aufgelösten
Policy-ID-Keys, setzt die registrierten echten Objekte ein und erzeugt direkt
die ausführbare `SimulationAction`.

### 8. Aktion zustellen

```python
for simulation_action in simulation_actions:
    self.sim_objects_waiting_for_action.remove(
        simulation_action.target
    )
    yield self.to_store(
        self.sim_action_stores[simulation_action.target],
        simulation_action,
    )
```

Das Ziel wird aus dem Waiting-Set entfernt. Das Einlegen in seinen persönlichen
Action-Store setzt dessen wartendes `yield bridge.action(self)` fort.

```text
SimulationAction
├── Zielobjekt aus sim_objects_waiting_for_action entfernen
└── in den persönlichen Action-Store des Zielobjekts legen
        │
        ▼
action(target) gibt die SimulationAction an das Objekt zurück
```

---

**Methoden für Snapshot und PolicyObservation**

**Vollständiges Beispiel**

```text
1. Main-Roboter
   └── yield bridge.request_action(self)
       ├── in Waiting-Set aufnehmen
       └── PolicyTrigger in policy_trigger_store legen
                   │
                   ▼
2. SimulationBridge.process()
   ├── hold(0)
   ├── Trigger gleicher Zeit sammeln
   ├── Snapshot erzeugen
   └── PolicyObservation an Policy geben
                   │
                   ▼
3. GeneratorSelectorPolicy
   ├── objektbezogene Observation für "Main robot"
   ├── Aktionskandidaten erzeugen
   ├── eine Aktion auswählen
   └── Konflikte prüfen und ausgewählte Jobs reservieren
                   │
                   ▼
4. PolicyDecision
   └── pick_main_robot mit Store-ID, Job-ID und movement_speed
                   │
                   ▼
5. SimulationBridge
   ├── Store-ID und Job-ID in echte Objekte umwandeln
   ├── SimulationAction erzeugen
   └── in persönlichen Action-Store legen
                   │
                   ▼
6. Main-Roboter
   └── action = yield bridge.action(self) wird fortgesetzt
       └── execute_pick_action(action)
```

**Entkopplungsgrenze**

```text
Policyseite
├── PolicyObservation mit IDs und reinen Daten
├── PolicyDecision
└── SelectedObjectAction mit ID-basiertem Payload
        │
        ▼
SimulationBridge
├── besitzt Objekt- und Store-Register
├── löst IDs zu Laufzeitobjekten auf
└── erzeugt SimulationAction
        │
        ▼
Simulationskern
├── echte sim.Component-Objekte
├── echte sim.Store-Objekte
└── echte Konfigurationsobjekte
```

Die `SimulationBridge` ist damit die einzige Stelle, die beide Seiten kennt.
Die Policy bleibt von Salabim und den echten Konfigurationsobjekten entkoppelt.

