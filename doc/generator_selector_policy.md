# GeneratorSelectorPolicy

Python-Datei: `sources/SpineML/Control/GeneralControl/GeneratorSelectorPolicy.py`

## Aufgabe

Verbindet einen `ActionGenerator`, einen `ActionEvaluator` und einen
austauschbaren `ActionSelector` und erzeugt daraus eine konfliktfreie globale
`PolicyDecision`.

```text
globale PolicyObservation von der SimulationBridge
        ↓
GeneratorSelectorPolicy.make_decision(...)
        │
        ├── findet alle Objekte mit is_waiting_for_action = True
        │
        └── für jedes wartende Objekt einzeln
                ↓
            objektbezogene PolicyObservation
            ├── vollständiger gemeinsamer Snapshot
            └── current_object_id = ID dieses Objekts
                ↓
            ActionGenerator
            └── erzeugt technisch mögliche Aktionskandidaten für dieses Objekt
                ↓
            ActionEvaluator
            └── bewertet jeden Kandidaten
                ↓
            ActionSelector
            └── wählt den Kandidaten mit der höchsten Bewertung
                ↓
            zurück zur GeneratorSelectorPolicy
                └── selected_actions.append(selected_action)
                    └── zunächst ohne globale Konfliktprüfung sammeln
                            ↓
            nächstes wartendes Objekt auf dieselbe Weise bearbeiten
        │
        ▼
alle ausgewählten Objektaktionen liegen in selected_actions
        ↓
zweite Schleife: Aktionen gemeinsam prüfen
├── Wait-Aktionen herausfiltern
├── denselben Job nur einmal auswählen
└── prüfen, ob der Job im angegebenen Store liegt
        ↓
alle gültigen Aktionen in valid_selected_actions sammeln
        ↓
globale, ausschließlich ID-basierte PolicyDecision
        ↓
SimulationBridge.create_simulation_actions(...)
        ├── Policy-IDs in echte Objekte umwandeln
        ├── ausführbare SimulationActions erzeugen
        └── Aktionen an die persönlichen Action-Stores verteilen
```

## Methoden

### `__init__(action_selector=None, action_generator=None, action_evaluator=None)`

Die Klasse verbindet einen austauschbaren Generator, Evaluator und Selector:

```text
action_generator übergeben
└── diesen Generator verwenden

action_generator = None
└── SpineActionGenerator verwenden

action_selector übergeben
└── diesen Selector verwenden

action_selector = None
└── BaselineActionSelector verwenden

action_evaluator übergeben
└── diesen Evaluator verwenden

action_evaluator = None
└── LocalHeuristicActionEvaluator mit HeuristicWeights verwenden
```

### `make_decision(observation)`

Aufgabe: Ermittelt alle auf eine Aktion wartenden Objekte, lässt für jedes
Objekt eine Aktion auswählen und verhindert Konflikte zwischen diesen
objektbezogenen Auswahlen.

Eingabe:

```python
PolicyObservation(
    simulation_configuration_snapshot={
        "simulation_object_states_by_id": {
            "Main robot": {
                "object_type": "main_robot",
                "is_waiting_for_action": True,
            }
        }
    }
)
```

Ausgabe:

```python
PolicyDecision(actions=[...])
```

Die eingehende globale Observation besitzt `current_object_id=None` und enthält
die Zustände aller registrierten Simulationsobjekte. Für jedes wartende Objekt
erzeugt die Methode eine neue objektbezogene Observation. Dabei bleibt der
vollständige Snapshot unverändert; lediglich `current_object_id` wird gesetzt:

```text
globale PolicyObservation
├── simulation_configuration_snapshot = vollständiger Snapshot
└── current_object_id = None
        │
        ▼ für Main robot mit is_waiting_for_action = True
objektbezogene PolicyObservation
├── simulation_configuration_snapshot = derselbe vollständige Snapshot
└── current_object_id = "Main robot"
```

#### Konkrete Ausgabe von `select_single_action()` und anschließende Schleife

Für die objektbezogene Observation des Main-Roboters wird aufgerufen:

```python
object_decision = self.select_single_action(object_observation)
```

Eine konkrete Ausgabe ist:

```python
object_decision = PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Main robot",
            action_type="pick_main_robot",
            payload={
                "target_store_id": "start",
                "selected_job_id": "Order 1.1:0",
                "movement_speed": 1.0,
            },
        )
    ]
)
```

`object_decision` ist somit eine `PolicyDecision`. Ihr Attribut `actions` ist
eine Liste:

```python
object_decision.actions == [
    SelectedObjectAction(
        target_id="Main robot",
        action_type="pick_main_robot",
        payload={
            "target_store_id": "start",
            "selected_job_id": "Order 1.1:0",
            "movement_speed": 1.0,
        },
    )
]
```

Danach läuft die Schleife über diese Liste:

```python
for selected_action in object_decision.actions:
```

Da die Liste im konkreten Beispiel genau einen Eintrag enthält, wird die
Schleife genau einmal ausgeführt. In diesem Durchlauf gilt:

```python
selected_action = SelectedObjectAction(
    target_id="Main robot",
    action_type="pick_main_robot",
    payload={
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "movement_speed": 1.0,
    },
)
```

In der ersten Phase wird dieses Objekt noch nicht global geprüft, sondern nur
in die gemeinsame Liste eingefügt:

```python
selected_actions.append(selected_action)
```

Nach der Auswahl für weitere wartende Objekte könnte die Liste beispielsweise
so aussehen:

```python
selected_actions = [
    SelectedObjectAction(
        target_id="Main robot",
        action_type="pick_main_robot",
        payload={
            "target_store_id": "start",
            "selected_job_id": "Order 1.1:0",
            "movement_speed": 1.0,
        },
    ),
    SelectedObjectAction(
        target_id="CorridorArmRobot:Corridor 1.1:left",
        action_type="pick_corridor_arm_robot",
        payload={
            "target_store_id": "Corridor 1.1 main",
            "selected_job_id": "Order 1.1:1",
            "movement_speed": 0.8,
        },
    ),
    SelectedObjectAction(
        target_id="SimMachine:Machine 1.1.1:left",
        action_type="wait_machine",
        payload={},
    ),
]
```

Erst in der zweiten Schleife wird jede gesammelte Aktion geprüft:

```python
for selected_action in selected_actions:
```

#### Erster Schleifendurchlauf

`selected_action` erhält den ersten Listeneintrag:

```python
selected_action = SelectedObjectAction(
    target_id="Main robot",
    action_type="pick_main_robot",
    payload={
        "target_store_id": "start",
        "selected_job_id": "Order 1.1:0",
        "movement_speed": 1.0,
    },
)
```

Die Aktion ist keine Wait-Aktion. Laut Snapshot liegt `Order 1.1:0` im Store
`start`. Daher wird sie übernommen:

```python
valid_selected_actions.append(selected_action)
```

#### Zweiter Schleifendurchlauf

`selected_action` erhält den zweiten Listeneintrag:

```python
selected_action = SelectedObjectAction(
    target_id="CorridorArmRobot:Corridor 1.1:left",
    action_type="pick_corridor_arm_robot",
    payload={
        "target_store_id": "Corridor 1.1 main",
        "selected_job_id": "Order 1.1:1",
        "movement_speed": 0.8,
    },
)
```

Wenn `Order 1.1:1` laut Snapshot im Store `Corridor 1.1 main` liegt und noch
nicht von einer anderen Aktion ausgewählt wurde, wird auch diese Aktion in
`valid_selected_actions` eingefügt.

#### Dritter Schleifendurchlauf

`selected_action` erhält den dritten Listeneintrag:

```python
selected_action = SelectedObjectAction(
    target_id="SimMachine:Machine 1.1.1:left",
    action_type="wait_machine",
    payload={},
)
```

Die folgende Bedingung ist bei dieser Aktion `True`:

```python
if is_wait_action(selected_action.action_type):
    continue
```

`continue` beendet nur diesen dritten Schleifendurchlauf. Die Wait-Aktion wird
nicht in `valid_selected_actions` eingefügt.

#### Konkretes Endergebnis

```python
valid_selected_actions = [
    SelectedObjectAction(
        target_id="Main robot",
        action_type="pick_main_robot",
        payload={
            "target_store_id": "start",
            "selected_job_id": "Order 1.1:0",
            "movement_speed": 1.0,
        },
    ),
    SelectedObjectAction(
        target_id="CorridorArmRobot:Corridor 1.1:left",
        action_type="pick_corridor_arm_robot",
        payload={
            "target_store_id": "Corridor 1.1 main",
            "selected_job_id": "Order 1.1:1",
            "movement_speed": 0.8,
        },
    ),
]
```

Die Rückgabe lautet anschließend:

```python
return PolicyDecision(valid_selected_actions)
```

Damit haben die beiden Listen unterschiedliche Aufgaben:

```text
selected_actions
└── alle objektbezogen ausgewählten Aktionen, noch nicht gemeinsam geprüft

valid_selected_actions
└── nur die nach der globalen Prüfung akzeptierten Aktionen
```

Beim aktuellen `BaselineActionSelector` enthält die objektbezogene
`PolicyDecision` genau eine ausgewählte Aktion. Die Schleife bleibt dennoch
allgemein mit dem Listenattribut `actions` kompatibel.

### Konfliktprüfung auf der Policy-Seite

Die Bridge prüft und reserviert keine Policyaktionen mehr. Diese Aufgabe
findet hier ausschließlich mit IDs und den reinen Daten aus der
`PolicyObservation` statt:

```text
Phase 1: objektbezogene Auswahl
├── für jedes Objekt mit is_waiting_for_action = True
├── objektbezogene PolicyObservation erzeugen
├── ActionGenerator erzeugt Kandidaten
├── ActionSelector lässt die Kandidaten vom ActionEvaluator bewerten
├── ActionSelector wählt die Aktion mit dem höchsten Evaluator-Score
└── Aktion zunächst in selected_actions sammeln

Phase 2: globale Prüfung aller gesammelten Aktionen
├── Wait-Aktion?                         → nicht übernehmen
├── selected_job_id bereits ausgewählt?  → Aktion überspringen
├── target_store_id im Snapshot?         → prüfen
├── selected_job_id in dessen job_ids?   → prüfen
└── gültige Aktion in valid_selected_actions aufnehmen
```

Die Job-Reservierung ist ein lokales Policy-Set und gilt nur für diesen einen
Aufruf von `make_decision()`:

```python
selected_job_ids: set[str] = set()
```

Konkretes Beispiel:

```text
Main robot wählt "Auftrag poliertes Werkstück:0"
└── aufnehmen und Job-ID in selected_job_ids eintragen

Corridor-Arm-Roboter wählt ebenfalls "Auftrag poliertes Werkstück:0"
└── überspringen, weil die Job-ID bereits ausgewählt wurde
```

Damit liefert die `GeneratorSelectorPolicy` der Bridge bereits diese
konfliktfreie Entscheidung:

```python
PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Main robot",
            action_type="pick_main_robot",
            payload={
                "target_store_id": "start",
                "selected_job_id": "Auftrag poliertes Werkstück:0",
                "movement_speed": 1.0,
            },
        )
    ]
)
```

Diese `PolicyDecision` bleibt vollständig auf der Policy-Seite:

```text
SelectedObjectAction.target_id
└── Policy-ID, kein Simulationsobjekt

SelectedObjectAction.payload
├── target_store_id = Policy-Store-ID
├── selected_job_id = Policy-Objekt-ID
└── weitere reine Zahlen, Strings und boolesche Werte
```

Die `GeneratorSelectorPolicy` erzeugt weder Salabim-Komponenten noch echte
Stores oder Konfigurationsobjekte. Erst
`SimulationBridge.create_simulation_actions(...)` kopiert das Payload, entfernt
die umzuwandelnden `*_id`-Keys und setzt die entsprechenden echten Objekte in
das Payload der `SimulationAction` ein.

### `store_states_by_id(snapshot)`

> **Entfernt:** Diese Methode gehört nicht mehr zur aktuellen
> `GeneratorSelectorPolicy`. Der ActionGenerator erzeugt Pick-Kandidaten nur
> für Jobs, die sich im jeweiligen Quell-Store befinden. Deshalb prüft die
> Verbindungsklasse Store und Job nicht nochmals. Der folgende Unterabschnitt
> beschreibt nur den früheren Stand und ist für den aktuellen Ablauf nicht
> mehr maßgeblich.

Die Methode erhält den vollständigen Policy-Snapshot. Die Store-Zustände liegen
darin an unterschiedlichen, verschachtelten Stellen. Die Methode sammelt diese
Store-Dictionaries und ordnet sie nach ihrer `store_id`.

#### Konkrete Eingabe

Zur besseren Übersicht ist der folgende Snapshot verkürzt. Ein echter Snapshot
enthält noch weitere Objekt- und Konfigurationsattribute.

```python
snapshot = {
    "time": 11.0,
    "state_version": 14,
    "simulation_object_states_by_id": {
        "Main robot": {
            "object_type": "main_robot",
            "start_storage": {
                "store_id": "start",
                "job_ids": [
                    "Order 1.1:0",
                    "Order 1.1:1",
                ],
            },
            "corridor_storages": [
                {
                    "corridor_id": "Corridor 1.1",
                    "main": {
                        "store_id": "Corridor 1.1 main",
                        "job_ids": [],
                    },
                    "left": {
                        "store_id": "Corridor 1.1 left",
                        "job_ids": [],
                    },
                }
            ],
        },
        "SimMachine:Machine 1.1.1:left": {
            "object_type": "machine",
            "input_storage": {
                "store_id": "Machine 1.1.1 in",
                "job_ids": ["Order 1.1:2"],
            },
        },
    },
    "configuration_model": {},
}
```

Aufruf:

```python
stores_by_id = self.store_states_by_id(snapshot)
```

#### Konkrete Ausgabe

```python
stores_by_id = {
    "start": {
        "store_id": "start",
        "job_ids": [
            "Order 1.1:0",
            "Order 1.1:1",
        ],
    },
    "Corridor 1.1 main": {
        "store_id": "Corridor 1.1 main",
        "job_ids": [],
    },
    "Corridor 1.1 left": {
        "store_id": "Corridor 1.1 left",
        "job_ids": [],
    },
    "Machine 1.1.1 in": {
        "store_id": "Machine 1.1.1 in",
        "job_ids": ["Order 1.1:2"],
    },
}
```

Das sind reine Snapshot-Daten. Die Policy erhält dadurch keinen Zugriff auf
echte Salabim-Stores.

#### Was passiert in der Methode?

Am Anfang wird das noch leere Ergebnis-Dictionary erzeugt:

```python
stores_by_id: dict[str, dict] = {}
```

```text
stores_by_id = {}
```

Danach wird die innere Hilfsfunktion `collect_store_states(value)` definiert.
Sie kann drei Arten von Werten erhalten:

```text
value ist ein Dictionary
├── besitzt es "store_id" und "job_ids"?
│   └── Ja: als Store-Zustand in stores_by_id eintragen
└── danach alle enthaltenen Werte ebenfalls untersuchen

value ist eine Liste
└── jedes Element der Liste untersuchen

value ist zum Beispiel String, Zahl, Boolean oder None
└── nichts tun
```

Der erste tatsächliche Aufruf startet bei allen Objektzuständen:

```python
collect_store_states(snapshot["simulation_object_states_by_id"])
```

Wichtig: Die Funktion arbeitet mit `.values()`. Deshalb wird beispielsweise
nicht der Key `"Main robot"`, sondern das dahinterliegende Dictionary als
neuer Wert an die Funktion übergeben.

#### Tatsächliche Aufrufe für das Dictionary `Main robot`

**Aufruf 1: gesamtes `states_by_id`-Dictionary**

```python
value = {
    "Main robot": {...},
    "SimMachine:Machine 1.1.1:left": {...},
}
```

`value` ist ein Dictionary, aber selbst kein Store, weil die Keys `store_id`
und `job_ids` auf dieser Ebene fehlen. Deshalb läuft Python durch
`value.values()`.

**Aufruf 2: Wert hinter dem Key `"Main robot"`**

```python
value = {
    "object_type": "main_robot",
    "start_storage": {
        "store_id": "start",
        "job_ids": ["Order 1.1:0", "Order 1.1:1"],
    },
    "corridor_storages": [...],
}
```

Auch dieses Dictionary ist selbst kein Store. Die Funktion durchläuft wieder
alle Werte. Dadurch folgen unter anderem diese Aufrufe:

```text
collect_store_states("main_robot")
collect_store_states(start_storage-Dictionary)
collect_store_states(corridor_storages-Liste)
```

**Aufruf 3: der String `"main_robot"`**

```python
value = "main_robot"
```

Ein String ist weder Dictionary noch Liste. Deshalb tut dieser Aufruf nichts
und endet.

**Aufruf 4: das Dictionary `start_storage`**

```python
value = {
    "store_id": "start",
    "job_ids": ["Order 1.1:0", "Order 1.1:1"],
}
```

Jetzt sind beide gesuchten Keys vorhanden:

```python
"store_id" in value  # True
"job_ids" in value   # True
```

Deshalb wird das gesamte Store-Dictionary gespeichert:

```python
stores_by_id[value["store_id"]] = value
```

Konkret ergibt das:

```python
stores_by_id["start"] = {
    "store_id": "start",
    "job_ids": ["Order 1.1:0", "Order 1.1:1"],
}
```

Der Weg durch die Dictionaries lautet damit:

```text
snapshot["simulation_object_states_by_id"]                         Dictionary
└── Wert von "Main robot"                       Dictionary
    └── Wert von "start_storage"                Dictionary
        ├── enthält "store_id"
        └── enthält "job_ids"
            ↓
stores_by_id["start"] = start_storage-Dictionary
```

#### Tatsächliche Aufrufe für die Liste `corridor_storages`

Später erhält die Funktion diesen Wert:

```python
value = [
    {
        "corridor_id": "Corridor 1.1",
        "main": {
            "store_id": "Corridor 1.1 main",
            "job_ids": [],
        },
        "left": {
            "store_id": "Corridor 1.1 left",
            "job_ids": [],
        },
    }
]
```

`value` ist eine Liste. Deshalb läuft dieser Code:

```python
for nested_value in value:
    collect_store_states(nested_value)
```

Das erste Listenelement ist das Corridor-Dictionary. Dieses wird wieder über
seine `.values()` durchsucht. Dadurch werden anschließend die beiden
Store-Dictionaries `main` und `left` gefunden und eingetragen:

```text
corridor_storages-Liste
└── erstes Listenelement: Corridor-Dictionary
    ├── Wert hinter "corridor_id"
    │   └── String → nichts tun
    ├── Wert hinter "main"
    │   └── Store-Dictionary
    │       └── stores_by_id["Corridor 1.1 main"] eintragen
    └── Wert hinter "left"
        └── Store-Dictionary
            └── stores_by_id["Corridor 1.1 left"] eintragen
```

#### Gesamtablauf der Rekursion

```text
Dictionary erhalten
├── falls Store-Dictionary: in stores_by_id speichern
└── jeden enthaltenen Value erneut untersuchen

Liste erhalten
└── jedes enthaltene Element erneut untersuchen

anderen Wert erhalten
└── nichts tun und zum vorherigen Aufruf zurückkehren
```

Die Funktion ruft sich somit für enthaltene Dictionaries und Listen selbst
erneut auf. Sie bewegt sich schrittweise tiefer durch den Snapshot und kehrt
nach jedem fertigen inneren Aufruf zur vorherigen Ebene zurück.

Am Ende gibt die Methode das fertig aufgebaute Such-Dictionary zurück:

```python
return stores_by_id
```

#### Warum wird das Ergebnis benötigt?

Eine ausgewählte Pick-Aktion enthält beispielsweise:

```python
{
    "target_store_id": "start",
    "selected_job_id": "Order 1.1:0",
}
```

Damit kann `make_decision()` direkt den zugehörigen Store-Zustand finden:

```python
target_store_state = stores_by_id["start"]
```

Anschließend wird geprüft, ob sich der ausgewählte Job laut Snapshot wirklich
in diesem Store befindet:

```python
"Order 1.1:0" in target_store_state["job_ids"]
# True
```

In der aktuellen verschachtelten Snapshot-Struktur ist die Methode deshalb
notwendig. Wenn der Snapshot später selbst einen Haupt-Key `stores_by_id`
erhält, könnte diese rekursive Hilfsmethode entfernt werden.

### `select_single_action(observation)`

Aufgabe: Lässt den Generator Kandidaten für genau das Objekt in
`observation.current_object_id` erzeugen und übergibt alle Kandidaten, den
Evaluator und dieselbe objektbezogene Observation an den Selector. Der
Selector lässt jeden Kandidaten vom Evaluator bewerten und wählt anschließend
den Kandidaten mit dem höchsten Score.

```text
objektbezogene PolicyObservation für "Main robot"
        ↓
action_generator.generate_actions(observation)
        ↓
Liste aller momentan möglichen Aktionen für "Main robot"
        ↓
action_selector.select_action(
    actions,
    evaluator=action_evaluator,
    observation=observation,
    target_id="Main robot",
)
        ↓
ActionEvaluator bewertet jeden Kandidaten
        ↓
ActionSelector wählt den höchsten Score
        ↓
objektbezogene PolicyDecision
```

Ausgabe:

```python
PolicyDecision(
    actions=[
        SelectedObjectAction(
            target_id="Main robot",
            action_type="pick_main_robot",
            payload={...},
        )
    ]
)
```

`make_decision()` sammelt die objektbezogenen `SelectedObjectAction`-Objekte
zuerst in `selected_actions`. Anschließend prüft es sie gemeinsam, sammelt die
akzeptierten Aktionen in `valid_selected_actions` und erzeugt erst daraus die
globale `PolicyDecision`.

## Zusammenhang mit der Snapshot-Version

Die `GeneratorSelectorPolicy` erhält genau den Snapshot, aus dem sie ihre
Aktionen erzeugt. Sie verändert dessen `state_version` nicht und führt keine
Simulation aus:

```text
PolicySnapshot mit state_version = 14
        ↓
GeneratorSelectorPolicy.make_decision(...)
        ↓
PolicyDecision gehört zu diesem Snapshot mit Version 14
        ↓
SimulationBridge vergleicht Snapshot-Version mit ihrem aktuellen
Zustandsänderungszähler
```

Die Bridge verteilt die Entscheidung nur, wenn seit der Snapshot-Erzeugung
keine neuere Zustandsänderung gemeldet wurde.

