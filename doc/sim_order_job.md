# SimOrderJob

Python-Datei: `sources/SpineML/Simulation/SimOrderJob.py`

## Position im Ablauf

```text
SimOrder erzeugt für jede zu produzierende Produkteinheit einer Order
einen eigenen SimOrderJob
    │
    ▼
SimOrderJob.__init__()
├── speichert Layout, Szenario, Order, Nummer und Start-Store
├── initialisiert Produkt-, Termin- und Defektzustände
└── registriert sich bei der SimulationBridge
    │
    ▼
SimOrderJob.process()
├── fordert eine Aktion bei der Bridge an
├── wartet in seinem persönlichen Action-Store
├── empfängt eine SimulationAction
├── übernimmt deren aufgelöste Payload-Werte
└── führt die Jobaktion aus
```

Konkretes Beispiel:

```python
order.quantity = 2
```

Dann erzeugt `SimOrder` zwei einzelne Jobobjekte:

```text
Order 1.1
├── SimOrderJob "Order 1.1:0" → erste zu produzierende Produkteinheit
└── SimOrderJob "Order 1.1:1" → zweite zu produzierende Produkteinheit
```

Jeder `SimOrderJob` repräsentiert damit genau ein einzelnes Produkt
beziehungsweise Werkstück aus der Menge der Order.

`SimOrderJob` ist eine echte Salabim-Simulationskomponente:

```python
class SimOrderJob(sim.Component):
```

Sie befindet sich auf der Simulationsseite. Die Policy erhält niemals dieses
echte Objekt, sondern nur das vom `SimulationObjectObserver` erzeugte
ID-basierte Zustands-Dictionary.

## Kommunikation mit der SimulationBridge

```text
SimOrderJob
└── request_action(self)
    ├── Bridge markiert den Job als wartend
    ├── Bridge erzeugt einen PolicyTrigger
    └── Trigger gelangt in policy_trigger_store
        │
        ▼
SimulationBridge.process()
├── erzeugt PolicyObservation
├── Policy erzeugt eine konfliktfreie PolicyDecision
├── Bridge löst IDs in echte Objekte auf
└── Bridge legt SimulationAction in den persönlichen Action-Store
        │
        ▼
SimOrderJob
└── action = yield self.bridge.action(self)
```

## Registrierung

Im Konstruktor wird der Job einmal registriert:

```python
self.bridge.register(
    f"{self.order.name}:{self.number}",
    self,
)
```

Konkretes Beispiel:

```text
order.name = "Order 1.1"
number     = 0
```

Die beiden Zahlen in der Code-ID `"Order 1.1"` folgen in den Beispieldateien
dieser Namenskonvention:

```text
Order 1.1
      │ │
      │ └── erste Order innerhalb des Szenarios
      └─── erstes Szenario
```

Weitere Beispiele:

```text
Order 1.2 → zweite Order im ersten Szenario
Order 2.1 → erste Order im zweiten Szenario
Order 3.2 → zweite Order im dritten Szenario
```

Diese Bedeutung ist eine menschlich gewählte Konvention. Der Konstruktor von
`Order` zerlegt oder validiert die Zahlen nicht. Er speichert lediglich:

```python
self.name = name
```

Ein Name wie `"Order poliertes Werkstück"` ist daher ebenfalls erlaubt.

Die zusätzliche Jobnummer steht nach dem Doppelpunkt:

```text
Order 1.1:0
      │ │ │
      │ │ └── erster erzeugter SimOrderJob dieser Order
      │ └─── erste Order im Szenario
      └──── erstes Szenario
```

Die Jobzählung beginnt bei `0`. Bei einer Ordermenge von zwei entstehen:

```text
Order 1.1:0
Order 1.1:1
```

Für das oben gezeigte `number = 0` ergibt sich bei der Bridge-Registrierung:

```python
policy_object_id = "Order 1.1:0"
simulation_object = sim_order_job
```

Die Bridge baut dabei unter anderem auf:

```text
policy_object_id_to_simulation_object
└── "Order 1.1:0" → SimOrderJob (simorderjob.0)

simulation_object_to_policy_object_id
└── SimOrderJob (simorderjob.0) → "Order 1.1:0"

sim_action_stores
└── SimOrderJob (simorderjob.0) → persönlicher Action-Store
```

Der `store_start` wird bei diesem `register()`-Aufruf nicht erneut registriert.
Der Job registriert hier nur sich selbst und erhält seinen persönlichen
Action-Store.

## Konstruktor

```python
def __init__(
    self,
    layout: Layout,
    scenario: Scenario,
    order: Order,
    number: int,
    store_start: sim.Store,
    bridge: SimulationBridge,
    *args,
    **kwargs,
):
```

### Eingaben


| Parameter     | Bedeutung                                        |
| --------------- | -------------------------------------------------- |
| `layout`      | Layout, in dem der Job produziert wird           |
| `scenario`    | Simulationsszenario des Jobs                     |
| `order`       | Konfigurierte Order, zu der der Job gehört      |
| `number`      | Nummer dieses einzelnen Jobs innerhalb der Order |
| `store_start` | Echter Salabim-Start-Store                       |
| `bridge`      | Gemeinsame`SimulationBridge`                     |

## Zustandsattribute

### Identität und Verknüpfungen

```text
layout
├── Typ: Layout
└── Wert: genau das Layout-Konfigurationsobjekt, in dem dieser Job simuliert wird

scenario
├── Typ: Scenario
└── Wert: genau das Szenario-Konfigurationsobjekt, zu dem die Order gehört

order
├── Typ: Order
└── Wert: genau die Order mit Name, Menge, Terminen und Zielprodukttyp

number
├── Typ: int
├── Werte: 0, 1, 2, ...
└── Bedeutung: nullbasierte Nummer dieses Jobs innerhalb der Order

store_start
├── Typ: sim.Store
└── Wert: echter Start-Store, in den der Job bei release_job gelegt wird

bridge
├── Typ: SimulationBridge
└── Wert: gemeinsame Bridge für Anforderung, Meldung und Aktionszustellung
```

### Normaler Jobzustand

```text
released
├── Typ: bool
├── Anfangswert: False
├── False → Job wurde noch nicht für die Produktion freigegeben
└── True  → Job wurde von der Policy freigegeben

queue_priority
├── Typ: float
├── Anfangswert: 0.0
├── aktueller Baseline-Wertebereich: 0.0 <= Wert < 1.0
├── Bedeutung: Prioritätswert beim Einlagern in Stores/Warteschlangen
├── erste Vergabe durch release_job
└── danach bei jedem neuen Store-Eintritt durch Place- oder Process-Aktion erneuert

completed_time
├── Typ: float | None
├── Anfangswert: None
├── None  → Job ist noch nicht fertig
└── float → Simulationszeit der Fertigstellung, gesetzt durch mark_finished()

selected_operation
├── Typ: OperationType | None
├── Anfangswert: None
├── None          → aktuell keine nächste Operation geplant
└── OperationType → echte konfigurierte Operation des nächsten Schritts

selected_machine
├── Typ: Machine | None
├── Anfangswert: None
├── None    → aktuell keine nächste Maschine geplant
└── Machine → echte konfigurierte Maschine des nächsten Schritts

processing_state
├── Typ: sim.State
├── Anfangswert: "unconfigured"
└── ProductType-Name → aktueller Bearbeitungszustand, zum Beispiel
    "Rohes Werkstück", "Geschliffenes Werkstück" oder "Poliertes Werkstück"

general_state
├── Typ: sim.State
├── Anfangswert: "intact"
├── "intact"    → kein aktueller Qualitätsfehler
├── "defect"    → Job ist aktuell defekt und benötigt eine Entscheidung
└── "scrap" → Job wird nicht weiter produziert

due_state
├── Typ: sim.State
├── Anfangswert: None
└── Bedeutung: Terminbewertung; `due` bedeutet Fälligkeit beziehungsweise Terminlage

    Mögliche Werte:
    ├── None
    │   └── Job wurde noch nicht fertiggestellt oder noch nicht terminlich bewertet
    ├── "on-time"
    │   └── rechtzeitig fertig: completed_time <= latest_end_time
    └── "late"
        └── verspätet fertig: completed_time > latest_end_time
```

Da `general_state` die Zustände `intact`, `defect` und `scrap` vollständig
abbildet, gibt es keine zusätzlichen Bool-Attribute für Defekt und Ausschuss.
Dadurch können keine widersprüchlichen Kombinationen entstehen.

### Sonder- und Defektzustand

```text
downgraded
├── Typ: bool
├── Anfangswert: False
├── False → keine Herabstufung
└── True  → Job wurde auf einen niedrigeren Produkttyp herabgestuft

downgrade_product_type
├── Typ: ProductType | None
├── Anfangswert: None
├── None        → kein herabgestuftes Zielprodukt
└── ProductType → echtes Konfigurationsobjekt des neuen Zielprodukts

defect_detected_time
├── Typ: float | None
├── Anfangswert: None
├── None  → noch kein Defekt erkannt
└── float → Simulationszeitpunkt der Defekterkennung

defect_operation
├── Typ: OperationType | None
├── Anfangswert: None
├── None          → keine Defektoperation gespeichert
└── OperationType → Operation, bei der der Defekt entstand

defect_machine
├── Typ: Machine | None
├── Anfangswert: None
├── None    → keine Defektmaschine gespeichert
└── Machine → Maschine, auf der der Defekt entstand

defect_product_state_before
├── Typ: str | None
├── Anfangswert: None
├── None → kein Defektkontext gespeichert
└── str  → ProductType-Name unmittelbar vor der fehlgeschlagenen Operation

defect_product_state_target
├── Typ: str | None
├── Anfangswert: None
├── None → kein Defektkontext gespeichert
└── str  → ProductType-Name, den die Operation erzeugen sollte

defect_severity
├── Typ: float | None
├── Anfangswert: None
├── None  → kein Schweregrad vorhanden
└── float → Wert von 0.0 einschließlich bis 1.0 ausschließlich

defect_recovery_strategy
├── Typ: str | None
├── Anfangswert: None
└── Bedeutung: von der Policy gewählte Behandlung des Defekts

    Mögliche Werte:
    ├── None → noch keine Defektstrategie gewählt
    ├── "rework_on_defect_machine" → dieselbe Operation auf derselben Maschine wiederholen
    ├── "rework_on_alternative_machine" → neue Route ab Zustand vor dem Defekt planen
    ├── "downgrade" → Zielprodukt auf niedrigeren ProductType setzen
    └── "scrap" → Job abbrechen und als Ausschuss behandeln
```

Diese Attribute bleiben auf dem echten `SimOrderJob`. Der
`SimulationObjectObserver.observe_order_job()` liest ihre Werte und erzeugt
daraus reine Policy-Daten und IDs.

## process()

### Position im Ablauf

```text
while True
├── 1. yield bridge.request_action(self)
├── 2. action = yield bridge.action(self)
├── 3. Payload-Werte in den Jobzustand übernehmen
├── 4. optional bis release_time warten
├── 5. optional Job in target_store legen
├── 6. bei release_job Zustandsänderung melden und passivieren
└── 7. bei finish_process=True die Schleife beenden
```

### Aktionsanforderung und Warten

#### Erstes yield: PolicyTrigger in den Bridge-Store legen

```python
yield self.bridge.request_action(self)
```

**Dieses `yield` wartet nur darauf, dass der `PolicyTrigger` in den
`policy_trigger_store` gelegt wird. Es wartet nicht auf eine Policyentscheidung
und nicht auf eine Action.**

`request_action(self)` markiert den Job zuerst als wartend. Danach erzeugt
`notify_state_change(self)` einen `PolicyTrigger` und gibt eine
`to_store(...)`-Anforderung zurück.

```text
SimOrderJob
└── yield bridge.request_action(self)
    ├── Job wird in sim_objects_waiting_for_action aufgenommen
    ├── PolicyTrigger wird erzeugt
    ├── PolicyTrigger wird in policy_trigger_store gelegt
    └── yield endet, sobald dieses Einlegen abgeschlossen ist
```

Das erste `yield` wartet ausschließlich darauf, dass der erzeugte
`PolicyTrigger` in den `policy_trigger_store` der Bridge gelegt wird.

```text
yield self.bridge.request_action(self)
└── wartet nur bis:
    PolicyTrigger befindet sich im policy_trigger_store
    │
    └── erstes yield ist beendet
        └── SimOrderJob führt die nächste Codezeile aus
```

Das erste `yield` wartet nicht auf:

```text
├── die Erzeugung des Policy-Snapshots
├── die Policyentscheidung
├── die Erzeugung einer SimulationAction
└── das Einlegen einer SimulationAction in den persönlichen Action-Store
```

Auf die `SimulationAction` wartet erst die unmittelbar folgende Codezeile:

```python
action = yield self.bridge.action(self)
```

#### Zweites yield: auf die ausführbare SimulationAction warten

```python
action = yield self.bridge.action(self)
```

`bridge.action(self)` erzeugt eine `from_store(...)`-Anforderung für den
persönlichen Action-Store dieses Jobs.

```text
persönlicher Action-Store ist leer
└── SimOrderJob bleibt bei yield bridge.action(self) blockiert
    │
    ▼
Bridge verarbeitet den PolicyTrigger
└── PolicyObservation → PolicyDecision → SimulationAction
    │
    ▼
Bridge legt SimulationAction in den persönlichen Job-Action-Store
    │
    ▼
from_store-Anforderung wird erfüllt
└── zweites yield endet
    └── action enthält die empfangene SimulationAction
```

#### Konkrete SimulationAction, die hier empfangen und verarbeitet wird

Für `Order 1.1:0` kann das zweite `yield` beispielsweise folgende echte
`SimulationAction` aus dem persönlichen Action-Store erhalten. Die laufenden
Eventnummern können sich je nach Simulationslauf unterscheiden; Aufbau und
Datentypen entsprechen dem tatsächlich verarbeiteten Objekt:

```python
action = SimulationAction(
    event_id="action_9",
    target=sim_order_job_0,  # echtes Objekt: SimOrderJob (simorderjob.0)
    source_policy_trigger_id="policy_trigger_8",
    action_type="release_job",
    time=0.0,
    payload={
        "processing_state": "Rohes Werkstück",
        "queue_priority": 0.8,
        "release_time": 0.0,
        "target_store_id": "start",
        "target_store": start_store,  # echtes Objekt: Store (start)
        "released": True,
    },
)
```

Dabei sind `target_store_id` und `target_store` absichtlich beide vorhanden:

```text
target_store_id = "start"
└── reine ID aus der Policy

target_store = Store("start")
└── von der Bridge aufgelöstes echtes Salabim-Store-Objekt
```

Nach Ende des zweiten `yield` steht genau dieses Objekt in der Variablen
`action`. Der `SimOrderJob.process()` verarbeitet es anschließend so:

```python
# 1. Bearbeitungsstartzustand setzen.
if "processing_state" in action.payload:
    self.processing_state.set(action.payload["processing_state"])

# 2. Anfangspriorität setzen.
if "queue_priority" in action.payload:
    self.queue_priority = action.payload["queue_priority"]

# 3. Job als freigegeben markieren.
if "released" in action.payload:
    self.released = action.payload["released"]

# 4. Falls nötig bis zum Freigabezeitpunkt warten.
if "release_time" in action.payload:
    release_time = action.payload["release_time"]
    if release_time > self.env.now():
        yield self.hold(release_time - self.env.now())

# 5. Den echten Job mit der Anfangspriorität in den Start-Store legen.
if "target_store" in action.payload:
    yield self.to_store(
        action.payload["target_store"],
        self,
        priority=self.queue_priority,
    )

# 6. Zustandsänderung melden und den Job passivieren.
if action.action_type == "release_job":
    yield self.bridge.notify_state_change(self)
    yield self.passivate()
```

Konkretes Ergebnis:

```text
vor der Action
├── self.released = False
├── self.processing_state = "unconfigured"
├── self.queue_priority = 0.0
└── Start-Store enthält Order 1.1:0 nicht

nach der Action
├── self.released = True
├── self.processing_state = "Rohes Werkstück"
├── self.queue_priority = 0.8
├── Start-Store enthält SimOrderJob (simorderjob.0)
└── der Job ist passiviert und wartet auf seine spätere Aktivierung
```

Kurzfassung:

```text
yield request_action(self)
└── wartet auf erfolgreiches Einlegen des PolicyTriggers

yield bridge.action(self)
└── wartet auf eine SimulationAction im persönlichen Action-Store
```

### Verarbeitung des Payloads

`process()` entscheidet die meisten Zustandsänderungen nicht selbst. Die Bridge
hat die Policy-IDs bereits aufgelöst; der Job übernimmt vorhandene Payload-Felder.

#### Grundregel der einzelnen if-Anweisungen

Die Bedingungen sind fast ausschließlich einzelne `if`-Anweisungen und keine
zusammenhängende `if/elif/else`-Kette:

```text
Action kommt beim Job an
│
├── prüfe erstes if
├── prüfe zweites if
├── prüfe drittes if
├── prüfe viertes if
└── ... prüfe alle weiteren if-Anweisungen
```

Deshalb können bei einer Action mehrere Bedingungen gleichzeitig wahr sein.
Jeder passende Block wird in der Reihenfolge des Codes ausgeführt.

Beispiel:

```python
action.payload = {
    "released": True,
    "queue_priority": 0.8,
}
```

Alle drei Bedingungen sind wahr. Das Ergebnis ist:

```text
self.released          = True
self.queue_priority    = 0.8
```

#### Vollständige Reihenfolge der while-Schleife

```text
while True
│
├── 1. Aktionsanforderung melden
│   └── yield bridge.request_action(self)
│       └── wartet nur auf das Einlegen des PolicyTriggers
│
├── 2. Auf ausführbare Action warten
│   └── action = yield bridge.action(self)
│       └── action ist danach eine SimulationAction
│
├── 3. alle vorhandenen Payload-Felder nacheinander übernehmen
│
├── 4. gegebenenfalls bis release_time warten
│
├── 5. gegebenenfalls den Job in target_store legen
│
├── 6. release_job melden und Job passivieren
│
├── 7. bei finish_process=True die Schleife mit break beenden
│
└── andernfalls beginnt der nächste Schleifendurchlauf
```

#### Alle Payload-if-Anweisungen mit konkreten möglichen Werten

Die folgenden Beispiele verwenden die echten Bezeichnungen aus `example-0.py`.
`Operation` und `Machine` bezeichnen nach der Auflösung durch die Bridge echte
Konfigurationsobjekte und nicht nur Strings.

```text
1. if "selected_operation" in action.payload:
   Payload: "selected_operation" = Operation("Rohes Werkstück schleifen")
   Ergebnis: self.selected_operation zeigt auf diese echte Operation.

2. if "selected_machine" in action.payload:
   Payload: "selected_machine" = Machine("Schleifmaschine A")
   Ergebnis: self.selected_machine zeigt auf diese echte Maschine.

3. if "processing_state" in action.payload:
   Payload: "processing_state" = "Rohes Werkstück"
   Ergebnis: self.processing_state.get() == "Rohes Werkstück"

4. if "general_state" in action.payload:
   Payload: "general_state" = "defect"
   Ergebnis: self.general_state.get() == "defect"

5. if "due_state" in action.payload:
   Payload: "due_state" = "on-time"
   Ergebnis: self.due_state.get() == "on-time"
   Weitere mögliche Werte: "late" oder None.

6. if "released" in action.payload:
   Payload: "released" = True
   Ergebnis: self.released == True

7. if "downgraded" in action.payload:
   Payload: "downgraded" = True
   Ergebnis: self.downgraded == True.

8. if "downgrade_product_type" in action.payload:
   Payload: "downgrade_product_type" = ProductType("Geschliffenes Werkstück")
   Ergebnis: self.downgrade_product_type zeigt auf diesen echten Produkttyp.

9. if "queue_priority" in action.payload:
    Payload: "queue_priority" = 0.8
    Ergebnis: self.queue_priority == 0.8; dieser Wert wird beim Einlagern
    als Store-Priorität verwendet.

10. if "completed_time" in action.payload:
    Payload: "completed_time" = 74.215
    Ergebnis: self.completed_time == 74.215.

11. if "defect_detected_time" in action.payload:
    Payload: "defect_detected_time" = 50.841
    Ergebnis: self.defect_detected_time == 50.841.

12. if "defect_operation" in action.payload:
    Payload: "defect_operation" = Operation("Rohes Werkstück schleifen")
    Ergebnis: Der Job merkt sich, bei welcher echten Operation der Defekt entstand.

13. if "defect_machine" in action.payload:
    Payload: "defect_machine" = Machine("Schleifmaschine A")
    Ergebnis: Der Job merkt sich, auf welcher echten Maschine der Defekt entstand.

14. if "defect_product_state_before" in action.payload:
    Payload: "defect_product_state_before" = "Rohes Werkstück"
    Ergebnis: Der Produktzustand vor der fehlerhaften Bearbeitung ist gespeichert.

15. if "defect_product_state_target" in action.payload:
    Payload: "defect_product_state_target" = "Geschliffenes Werkstück"
    Ergebnis: Der vorgesehene Produktzustand nach der Bearbeitung ist gespeichert.

16. if "defect_severity" in action.payload:
    Payload: "defect_severity" = 0.35
    Ergebnis: self.defect_severity == 0.35.

17. if "defect_recovery_strategy" in action.payload:
    Payload: "defect_recovery_strategy" = "rework_on_defect_machine"
    Ergebnis: Der Job soll die betroffene Operation auf der Defektmaschine
    erneut als Nacharbeit ausführen.
```

#### Konkreter Fall: Nacharbeit auf Schleifmaschine A

Die Policy sendet zunächst IDs. Die Bridge löst Operation und Maschine auf.
Beim `SimOrderJob` kann danach beispielsweise dieses Payload ankommen:

```python
action.payload = {
    "selected_operation_id": "Rohes Werkstück schleifen",
    "selected_operation": operation_rohes_werkstueck_schleifen,
    "selected_machine_id": "Schleifmaschine A",
    "selected_machine": schleifmaschine_a,
    "processing_state": "Rohes Werkstück",
    "defect_recovery_strategy": "rework_on_defect_machine",
}
```

In diesem einen Schleifendurchlauf sind vier für den Job relevante
`if`-Bedingungen wahr und werden nacheinander ausgeführt:

```text
if "selected_operation" ...
└── self.selected_operation = Operation("Rohes Werkstück schleifen")

if "selected_machine" ...
└── self.selected_machine = Machine("Schleifmaschine A")

if "processing_state" ...
└── self.processing_state = "Rohes Werkstück"

if "defect_recovery_strategy" ...
└── self.defect_recovery_strategy = "rework_on_defect_machine"
```

Die Keys mit dem Suffix `_id` bleiben als nachvollziehbare Policy-Daten im
Payload. Verarbeitet werden in diesen `if`-Blöcken die von der Bridge ergänzten
Keys `selected_operation` und `selected_machine` mit den echten Objekten.

`processing_state` und `general_state` werden unabhängig voneinander gelesen:

```python
if "processing_state" in action.payload:
    self.processing_state.set(action.payload["processing_state"])

if "general_state" in action.payload:
    self.general_state.set(action.payload["general_state"])
```

Wenn beide Keys vorhanden sind, werden beide `if`-Blöcke ausgeführt. Dadurch
kann ein Job beispielsweise gleichzeitig ein geschliffenes Werkstück und
defekt sein:

```text
processing_state = "Geschliffenes Werkstück"
general_state      = "defect"
```

#### Vollständige Zuordnungstabelle

```text
Payload-Key                    wird gespeichert in
selected_operation            self.selected_operation
selected_machine              self.selected_machine
processing_state            self.processing_state
general_state                 self.general_state
due_state                     self.due_state
released                      self.released
downgraded                    self.downgraded
downgrade_product_type        self.downgrade_product_type
queue_priority                self.queue_priority
completed_time                self.completed_time
defect_detected_time          self.defect_detected_time
defect_operation              self.defect_operation
defect_machine                self.defect_machine
defect_product_state_before   self.defect_product_state_before
defect_product_state_target   self.defect_product_state_target
defect_severity             self.defect_severity
defect_recovery_strategy      self.defect_recovery_strategy
```

Ein Feld wird nur verändert, wenn der entsprechende Key im Payload vorhanden
ist. Alle anderen Jobattribute behalten ihren bisherigen Wert. Enthält ein
Payload mehrere dieser Keys, werden alle zugehörigen einzelnen `if`-Blöcke
nacheinander ausgeführt.

## Jobaktionen

Der Generator kann für einen Job unter anderem diese Aktionstypen erzeugen:

```text
release_job
complete_job
job_rework_on_defect_machine
job_rework_on_alternative_machine
downgrade_product
job_scrap
wait_job
```

Die meisten Jobaktionen unterscheiden sich durch ihre Payload-Felder. Der Job
übernimmt alle im Payload vorhandenen Werte. Bei einigen Aktionen ändert sich
zusätzlich der Ausführungszustand seines eigenen `SimOrderJob.process()`.

### passivate() und activate() bei Jobaktionen

`passivate()` pausiert nur den eigenen Prozess des Jobs. Das Jobobjekt bleibt
vorhanden und kann weiterhin von Robotern transportiert oder von Maschinen
bearbeitet werden.

Der Hauptgrund für die Passivierung nach `release_job` ist: Der Job befindet
sich ab diesem Zeitpunkt in der Produktion und benötigt während des normalen
Produktionsablaufs keine eigenen Jobaktionen mehr. Stattdessen benötigen die
Roboter Aktionen für den Transport und die Maschinen Aktionen für die
Bearbeitung. Die Policy steuert den Job in dieser Zeit somit indirekt über die
Roboter- und Maschinenaktionen.

```text
Vor release_job
└── eine gemeinsame release_job-Aktion ist erforderlich
    ├── Bearbeitungsstartzustand setzen
    ├── Anfangspriorität setzen
    └── Job freigeben

Nach release_job
└── der Job befindet sich in der Produktion
    ├── Jobprozess ist passiv
    ├── Roboter erhalten Transportaktionen
    └── Maschinen erhalten Bearbeitungsaktionen
```

Nur wenn ein Defekt erkannt wird oder der Job fertiggestellt wurde, benötigt
der Job wieder eine eigene Policyentscheidung. Dann wird sein Prozess durch
`mark_defective(...)` beziehungsweise `mark_finished()` aktiviert.

### Defekter Job beim Abschluss im Endlager

Eine Nacharbeit kann gewählt werden, solange sich der Job noch in der
Produktion befindet. Er wird nach der Defektentscheidung wieder passiviert,
damit Roboter und Maschinen die ausgewählte Nacharbeit ausführen können.

Beginnt der Main-Robot dagegen das Ablegen im Endlager, ruft er
`mark_finished()` auf und setzt dadurch `completed_time`. Ab diesem Zeitpunkt
hat `complete_job` Vorrang vor weiteren Defektaktionen:

```text
Defekt während der Produktion
└── Defektentscheidung
    ├── Nacharbeit → passivate() → zurück in den Produktionsablauf
    ├── Herabstufung → passivate() → Transport zum Endlager
    └── Ausschuss → passivate() → Transport zum Endlager

Main-Robot führt place_main_robot zum Endlager aus
├── mark_finished() setzt completed_time
├── Jobprozess wird aktiviert
├── complete_job wird ausgewählt
└── finish_process=True → break
```

Dadurch bleibt auch ein Job mit `general_state = "defect"` nicht dauerhaft
bei `passivate()` im Endlager hängen.

Diese Absicherung liegt an zwei Stellen der Steuerung:

```text
SpineActionGenerator.generate_actions(...)
└── completed_time ist gesetzt und due_state ist None
    └── erzeugt complete_job

LocalHeuristicActionEvaluator.evaluate_action(...)
└── bewertet complete_job mit der höchsten Abschlusspriorität

BaselineActionSelector.select_action(...)
└── wählt die vom Evaluator höchstbewertete Aktion
```

Die Defektstrategie-Aktion mit anschließendem `passivate()` wird in diesem
Abschlusszustand daher nicht mehr ausgewählt.

Wichtig: Im aktuellen Code wird `mark_finished()` unmittelbar vor der
optionalen Einlagerungszeit und vor `to_store(end_store, ...)` aufgerufen.
Technisch bedeutet `completed_time` daher: Der Main-Robot hat den
Endlager-Ablauf begonnen. Es bedeutet nicht zwingend, dass der Job bereits im
Store liegt.

`activate()` setzt einen zuvor passivierten Jobprozess unmittelbar hinter
`yield self.passivate()` fort. Danach beginnt der nächste Schleifendurchlauf
und der Job fordert eine neue Jobaktion an.


| Jobaktion oder Ereignis                           | Zustand des Jobprozesses danach                                              |
| --------------------------------------------------- | ------------------------------------------------------------------------------ |
| `release_job`                                     | meldet die Änderung und wird mit`passivate()` passiv                        |
| normaler Transport oder normale Bearbeitung       | bleibt passiv; Roboter und Maschinen handeln                                 |
| `mark_defective(...)`                             | aktiviert den passiven Job für eine Defektentscheidung                      |
| Nacharbeits-, Herabstufungs- oder Ausschussaktion | meldet die Änderung und wird wieder passiv                                  |
| `mark_finished()`                                 | aktiviert den passiven Job für`complete_job`                                |
| `complete_job` mit `finish_process=True`          | `break` beendet den Jobprozess endgültig                                    |
| `wait_job`                                        | keine Action wird zugestellt; der Job wartet weiter bei`bridge.action(self)` |

```text
Job startet aktiv
└── release_job
    ├── Startzustand und Anfangspriorität setzen
    └── Job freigeben
    └── passivate()
        │
        ├── Transport und Bearbeitung durch Roboter/Maschinen
        │
        ├── Defekt
        │   └── mark_defective() → activate()
        │       └── Defektentscheidung → passivate()
        │
        └── Endlager erreicht
            └── mark_finished() → activate()
                └── complete_job → break
```

Kurzregel:

```text
Der Job benötigt selbst eine Jobaktion
└── Jobprozess ist aktiv

Roboter oder Maschine arbeitet mit dem Job
└── Jobprozess ist passiv

Job ist vollständig abgeschlossen
└── Jobprozess endet mit break
```

### Verhalten bei wait_job

In der aktuellen Architektur wird eine ausgewählte `wait_job`-Aktion von der
Bridge vor der Zustellung herausgefiltert:

```python
selected_action_policy = PolicyDecision([
    action
    for action in selected_action_policy.actions
    if not is_wait_action(action.action_type)
])
```

Dadurch erhält der Job keine `SimulationAction` für `wait_job`:

```text
Policy wählt wait_job
└── Bridge erkennt den Präfix wait_
    └── wait_job wird nicht in den persönlichen Action-Store gelegt
        └── SimOrderJob bleibt bei yield bridge.action(self) blockiert
```

Der Job bleibt in `sim_objects_waiting_for_action`. Sobald ein späterer
`PolicyTrigger` einen neuen Entscheidungszyklus auslöst, enthält der Snapshot
für diesen Job weiterhin:

```python
"is_waiting_for_action": True
```

`wait_job` besitzt aktuell keine eigene Wartezeit und keinen Retry-Timer. Wenn
kein weiterer Trigger entsteht, bleibt der Job unbegrenzt blockiert.

## Beispiel: Freigabe eines Jobs

Die Policy kann folgende ID-basierte Aktion auswählen:

```python
SelectedObjectAction(
    target_id="Order 1.1:0",
    action_type="release_job",
    payload={
        "release_time": 11.0,
        "target_store_id": "start",
        "released": True,
    },
)
```

Die Bridge löst `target_store_id` auf. Beim Job kommt beispielsweise an:

```python
SimulationAction(
    target=sim_order_job,
    action_type="release_job",
    payload={
        "release_time": 11.0,
        "target_store_id": "start",
        "target_store": start_store,
        "released": True,
    },
    # weitere Attribute
)
```

Der Job verarbeitet diese Aktion so:

```text
self.released = True
    │
    ├── falls env.now() < 11.0: hold bis t=11.0
    │
    ├── Job mit queue_priority in start_store legen
    │
    ├── bridge.notify_state_change(self)
    │
    └── passivate()
```

## mark_finished()

### Position und Aufruf im Projekt

```text
Generator/Selector wählt für den Main-Robot
└── place_main_robot
    └── payload.target_type = "end_storage"
        │
        ▼
SimRobotMain.process()
└── execute_place_action(action)
    └── target_type == "end_storage"
        ├── Main-Robot fährt zum Endlager
        ├── Main-Robot fährt nach unten
        ├── job.selected_operation = None
        ├── job.selected_machine = None
        └── job.mark_finished()
            ├── completed_time = env.now()
            └── falls Job passiv: job.activate()
                │
                ▼
SimOrderJob.process()
└── fordert eine neue Jobaktion an
    └── complete_job
        └── finish_process=True → break
```

Der produktive Aufruf befindet sich in:

```text
SimRobotMain.py
└── SimRobotMain.execute_place_action(...)
    └── job.mark_finished()
```

```text
Aufgabe
├── Fertigstellungszeit auf env.now() setzen
└── passiven Jobprozess aktivieren

Eingabe
└── keine

Ausgabe
└── keine direkte Rückgabe
```

Die nächste Policyentscheidung kann danach `complete_job` liefern. Dessen
Payload setzt `due_state` und enthält `finish_process=True`, wodurch
`SimOrderJob.process()` beendet wird.

## mark_defective(...)

### Position und Aufruf im Projekt

```text
SimMachine.process()
└── execute_process_action(action)
    ├── geplante Operation bearbeiten
    ├── yield hold(duration)
    └── Zufallswert < operation.defect_probability
        ├── zufälligen defect_severity erzeugen
        └── job.mark_defective(...)
            ├── operation
            ├── machine
            ├── product_state_before
            ├── product_state_target
            └── defect_severity
                │
                ▼
SimOrderJob.mark_defective(...)
├── general_state = "defect"
├── Defektkontext speichern
├── defect_recovery_strategy = None
└── falls Job passiv: job.activate()
    │
    ▼
SimOrderJob.process()
└── fordert eine Defektentscheidung an
```

Der produktive Aufruf befindet sich in:

```text
SimMachine.py
└── SimMachine.execute_process_action(...)
    └── job.mark_defective(...)
```

```text
Aufgabe
├── Job als defekt markieren
├── Defektzeit und Defektkontext speichern
├── general_state auf "defect" setzen
├── processing_state unverändert lassen
├── bisherige defect_recovery_strategy zurücksetzen
└── passiven Jobprozess aktivieren

Eingaben
├── operation
├── machine
├── product_state_before
├── product_state_target
└── defect_severity

Ausgabe
└── keine direkte Rückgabe
```

Nach der Aktivierung fordert der Job eine neue Aktion an. Die Policy kann dann
eine Nacharbeits-, Neuplanungs-, Herabstufungs-, Ausschuss- oder Warteaktion
auswählen.

## Entkopplungsgrenze

```text
SimOrderJob
└── echtes Salabim-Objekt mit echten Konfigurationsreferenzen
    │
    ▼
SimulationObjectObserver.observe_order_job(...)
└── erzeugt dict[str, object] mit IDs und reinen Zustandsdaten
    │
    ▼
PolicyObservation
└── Policy sieht keine Referenz auf SimOrderJob
```

In Gegenrichtung:

```text
SelectedObjectAction
└── enthält Job-, Store-, Operations- und Maschinen-IDs
    │
    ▼
SimulationBridge
└── löst die bereits konfliktfreien Policy-IDs auf
    │
    ▼
SimulationAction
└── enthält die für SimOrderJob ausführbaren Laufzeitdaten
```

