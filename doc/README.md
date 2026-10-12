# SpineML – Umgesetzte Erweiterungen

**Dokumentationsregel:** Jeder `python`-Block unten enthält nur Zeilen, die im
aktuellen Quellcode unter `sources/` implementiert sind. Gekürzte Blöcke sind
als Quellcode-Auszug gedacht und deshalb nicht immer allein ausführbar.
Hypothetische Python-Zuweisungen und erfundene Platzhalterwerte werden nicht
als Python-Code verwendet. Reine Ablaufbilder und Rechenbeispiele sind als
`text` gekennzeichnet.

## 1. Erweiterte Fabrikkonfiguration

### Layout

Das Layout wurde um eine Kapazität für die Lager erweitert:

```text
storage_capacity
```

Die Kapazität wird für das Startlager und das Endlager verwendet. Beide sind
getrennte Stores. Bei `storage_capacity=10` kann jeder Store bis zu 10 Jobs
enthalten.

### Maschine

Eine konkrete Maschine kann zusätzlich enthalten:

```text
input_storage_capacity     Kapazität des Eingangspuffers
output_storage_capacity    Kapazität des Ausgangspuffers
tool_types                 erlaubte Werkzeugtypen
processing_speed_factor    Bearbeitungsgeschwindigkeit
dummy_tool_mount_time      Montagezeit des Schutzwerkzeugs
dummy_tool_unmount_time    Demontagezeit des Schutzwerkzeugs
```

Die beiden Werte werden im tatsächlichen Konstruktor der Maschine übergeben:

```python
def __init__(
    self,
    name: str,
    machine_type: MachineType,
    corridor: Corridor,
    left: bool,
    input_storage_capacity: int,
    output_storage_capacity: int,
    tool_types: list[ToolType] | None = None,
    processing_speed_factor: float = 1.0,
) -> None:
```

Wenn keine Werkzeugliste angegeben ist, werden die Werkzeugtypen des
Maschinentyps übernommen. Eingangspuffer und Ausgangspuffer werden getrennt
konfiguriert und können unterschiedliche Kapazitäten besitzen.

## 2. Diskrete Simulation

Die Simulation basiert auf Salabim und bildet Layout, Korridore, Roboter,
Maschinen, Stores und Jobs als Laufzeitobjekte ab. Der Simulationseinstieg kann
zusätzlich eine Policy, eine Bridge, eine Endzeit und eine
Animationsgeschwindigkeit erhalten. Er erzeugt die Simulationsumgebung,
startet die Laufzeitkomponenten, führt den Lauf aus und gibt anschließend
Statistiken und Diagramme aus.

### Begrenzte Puffer

Die folgenden Kapazitäten werden direkt an Salabim-Stores weitergegeben:

Ein Korridor erzeugt drei Laufzeit-Stores:

```text
corridor.store_main
corridor.store_left
corridor.store_right
```

Alle drei verwenden `corridor.storage_capacity`. Die `storage_out_time` und
`storage_in_time` des Corridors werden bei den Pick- und Place-Aktionen der
Korridorarm-Roboter verwendet. Beim Start- und Endlager verwendet der
Main-Roboter die entsprechenden Zeiten des Layouts.

Ist ein Store voll, kann ein Transport nicht abgelegt werden. Der Roboter oder
die Maschine wartet, bis wieder Kapazität vorhanden ist. Diese Situation kann
als Blockierungszeit ausgewertet werden.

### Job-Lebenszyklus

Jeder `SimOrderJob` speichert seinen vollständigen Laufzeitstatus:

```text
location                 aktueller Aufenthaltsort des Jobs
                         (z. B. Store, Roboter oder Maschine)
selected_operation       nächste geplante Operation
selected_machine         nächste geplante Maschine
processing_state       Produktionszustand
general_state            intakt, defect oder ausschuss
due_state                None, "on-time" oder "late"
defect_severity        Schweregrad eines Defekts
defect_operation         Operation, die den Defekt verursacht hat
defect_machine            Maschine, die den Defekt verursacht hat
defect_recovery_strategy gewählte Qualitätsstrategie
defect_count             Anzahl erkannter Defekte
rework_count         Anzahl der Nacharbeitsschritte
scrap_count          Anzahl der Ausschussentscheidungen
downgraded                True, wenn der Job herabgestuft wurde
downgrade_product_type    der akzeptierte niedrigere Produkttyp
completed_time           Abschlusszeitpunkt
```

Qualitätsereignisse bleiben auch nach einer erfolgreichen Nacharbeit
gespeichert. `defect_operation` und `defect_machine` bleiben deshalb die
historische Ursache des Defekts. Sie sind nicht mit `selected_operation` und
`selected_machine` zu verwechseln: Die `selected_*`-Felder beschreiben den
nächsten geplanten Bearbeitungsschritt.

Ein einzelner Job wird erst ab seiner konfigurierten frühesten Startzeit
freigegeben. Nach dem Ablegen im Endlager wird für diesen Job anhand des
spätesten Endtermins `due_state` gesetzt: `"on-time"`, wenn sein Abschluss
rechtzeitig war, oder `"late"`, wenn er zu spät war. Die globale
`total_tardiness` wird anschließend getrennt davon pro Auftrag aus dem
spätesten Abschluss seiner Jobs berechnet.

### Defekt- und Terminstatus im Quellcode

Bei einem Defekt setzt `SimOrderJob.mark_defective(...)` den Zustand und die
historischen Felder. Die Policy schreibt `selected_operation` und
`selected_machine` bei der nächsten Aktion in die Payload. Diese Werte werden
also nicht mit erfundenen Beispielzuweisungen dokumentiert, sondern direkt aus
der Payload übernommen.

`selected_operation` und `selected_machine` bedeuten also „nächster geplanter
Schritt“. `defect_operation` und `defect_machine` bedeuten „wo der Defekt
entstanden ist“.

`earliest_start_time` und `latest_end_time` stammen aus `Order`. Der Job wird
erst ab `earliest_start_time` freigegeben. Beim Abschluss vergleicht die
Steuerung die tatsächliche Simulationszeit mit `latest_end_time` und setzt das
Payload-Feld `due_state` entsprechend auf `"on-time"` oder `"late"`.

`due_state` gehört zum einzelnen Job. Bei einem Auftrag mit mehreren Jobs
verwendet die globale Tardiness-Berechnung anschließend den spätesten
Abschluss dieser Jobs.

`due_state` wird in `SpineActionGenerator.create_completion_actions_for_job()`
berechnet und als Payload-Feld gesetzt. `SimOrderJob.process()` speichert dieses
Payload anschließend mit `self.due_state.set(...)`:

```python
        if current_state["completed_time"] > current_state["latest_end_time"]:
            due_state = "late"
        else:
            due_state = "on-time"

        return [
            {
                "action_type": "complete_job",
                "payload": {
                    "due_state": due_state,
                    "finish_process": True,
                },
            }
        ]
```

Die globale Tardiness wird dagegen nicht aus `due_state` addiert. Sie wird in
`collect_global_metrics()` aus den tatsächlichen Abschlusszeiten gebildet. Der
folgende Ausschnitt ist direkt aus dem Quellcode übernommen:

```python
        total_tardiness = 0.0
        unfinished_jobs = 0
        rework_job_count = 0.0
        scrap_job_count = 0.0
        downgraded_job_count = 0.0
        intact_jobs = 0
        defect_jobs = 0
        order_completion_times = {}
        unfinished_orders = set()

        for job in jobs:
            if getattr(job, "defect_count", 0) > 0:
                defect_jobs += 1
            if getattr(job, "downgraded", False):
                downgraded_job_count += 1.0
            if job.completed_time is None:
                unfinished_jobs += 1
                unfinished_orders.add(job.order.name)
                continue
            else:
                completed_times.append(float(job.completed_time))
                if job.general_state.get() == "intact":
                    intact_jobs += 1
                completion_time = float(job.completed_time)

            order_name = job.order.name
            order_completion_times[order_name] = max(
                completion_time,
                order_completion_times.get(order_name, 0.0),
            )

            rework_job_count += (
                1.0 if getattr(job, "rework_count", 0) > 0 else 0.0
            )
            scrap_job_count += float(getattr(job, "scrap_count", 0))

        for order in {job.order for job in jobs}:
            if order.name in unfinished_orders:
                continue
            completion_time = order_completion_times.get(order.name)
            if completion_time is None:
                continue
            total_tardiness += max(
                0.0,
                completion_time - float(order.latest_end_time),
            )
```

Beispiel mit einem Auftrag und zwei Jobs:

```text
Job 1: completed_time = 640
Job 2: completed_time = 670
Auftrag: latest_end_time = 650

letzter Abschluss = max(640, 670) = 670
Tardiness         = max(0, 670 - 650) = 20
```

Beispiel mit zwei Aufträgen:

```text
Auftrag A: letzter Abschluss 670, Deadline 650 → 20
Auftrag B: letzter Abschluss 700, Deadline 720 →  0

total_tardiness = 20 + 0 = 20
```

### Werkzeugzustände

Werkzeugwechsel, Montage, Demontage und Werkzeuglebensdauer werden
in `SimMachine.execute_process_action()` verarbeitet. Die Maschine speichert
die verbleibende Werkzeuglebensdauer und wartet die Montage- beziehungsweise
Demontagezeit ab. Für den Laufabschluss gibt es zusätzlich `SimMachineShutdown`:

```python
class SimMachineShutdown(sim.Component):
    def process(self):
        if self.machine.dummy_tool_mounted:
            return

        if self.machine.tool_type is not None:
            self.machine.state.set("unmounting")
            yield self.hold(self.machine.tool_type.unmount_time)
            self.machine.tool_type = None

        self.machine.state.set("mounting")
        yield self.hold(self.machine.machine.dummy_tool_mount_time)
        self.machine.dummy_tool_mounted = True
        self.machine.state.set("waiting")
```

`simulate()` erzeugt diese Shutdown-Komponente nur, wenn `till == sim.inf` und
der Lauf nicht bereits durch `SimCompletionWatcher` beendet wurde. Das ist die
konkrete Bedingung im aktuellen Code.

### Automatisches Simulationsende

`sim.SimulationStopped` ist keine eigene SpineML-Klasse. Sie wird von der
verwendeten Salabim-Bibliothek bereitgestellt (`salabim.py`, Klasse
`SimulationStopped`, eine Exception). SpineML löst diese Exception aus, wenn
alle Jobs fertig sind:

```python
class SimCompletionWatcher(sim.Component):
    def __init__(self, sim_orders, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sim_orders = sim_orders
        self.jobs = []
        for order in self.sim_orders:
            for job in order.sim_jobs:
                self.jobs.append(job)

    def process(self):
        while True:
            all_jobs_finished = True
            for job in self.jobs:
                if not job.process_finished:
                    all_jobs_finished = False
                    break

            if len(self.jobs) > 0 and all_jobs_finished:
                raise sim.SimulationStopped
            yield self.hold(1.0)
```

`SimScenario` erzeugt zuerst alle `SimOrderJob`-Objekte und danach den Watcher.
Der Watcher sammelt die Job-Referenzen deshalb einmal in `__init__`. In jeder
weiteren Simulationszeiteinheit prüft `process()` nur noch das aktuelle
`process_finished`-Attribut jedes gespeicherten Jobs. Dieses wird vorher vom
jeweiligen `SimOrderJob` gesetzt, sobald die Payload
`"finish_process": True` enthält.

`simulate()` fängt das normale Fertig-Signal ab:

```python
    completed_by_watcher = False
    try:
        env.run(till=till)
    except sim.SimulationStopped:
        completed_by_watcher = True
```

#### Zuständigkeiten im Ablauf


| Aufgabe                                    | Zuständig                                                     |
| :------------------------------------------- | :--------------------------------------------------------------- |
| Mögliche Aktionen erzeugen                | `SpineActionGenerator`                                         |
| Aktionen bewerten                          | `LocalHeuristicActionEvaluator`                              |
| Eine Aktion auswählen und übergeben      | `GeneratorSelectorPolicy` und `SimulationBridge`               |
| Die ausgewählte Aktion ausführen         | `SimOrderJob`, `SimMachine` oder `SimRobot`                    |
| Prüfen, ob alle Jobs fertig sind          | `SimCompletionWatcher`                                         |
| Das Simulationsende signalisieren          | `SimCompletionWatcher` mit `sim.SimulationStopped`             |
| Das Signal abfangen und Kennzahlen sammeln | `simulate()` oder `SpineMLSimulationRunner`                    |
| Schutzwerkzeug am Ende montieren           | `SimMachineShutdown`                                           |

Der headless `SpineMLSimulationRunner` fängt dieselbe Exception ebenfalls ab
und ruft danach `collect_global_metrics(...)` auf. Dadurch wird
`SimulationStopped` nicht als Fehler behandelt, sondern als Signal:
„Alle Jobs sind fertig; jetzt Kennzahlen sammeln.“

SimCompletionWatcher
→ raise sim.SimulationStopped
→ env.run(...) wird sofort beendet
→ except sim.SimulationStopped wird ausgeführt
→ pass ignoriert das Signal
→ collect_global_metrics(...) berechnet die Kennzahlen

### Roboter und Transporte

#### Pick- und Place-Aktionen

Der Main-Roboter und jeder Korridorarm fordern über die `SimulationBridge` eine
Aktion an. Danach wird je nach `action_type` die passende Pick-, Place- oder
Warte-Methode ausgeführt. Die Policy entscheidet also, *was* passieren soll;
der Roboter führt die Bewegung und den Transport aus.

Der Entscheidungszyklus des Main-Roboters ist im Quellcode:

```python
while True:
    yield self.bridge.request_action(self)
    action = yield self.bridge.action(self)

    if action.action_type == "pick_main_robot":
        yield from self.execute_pick_action(action)
    elif action.action_type == "place_main_robot":
        yield from self.execute_place_action(action)
    elif action.action_type == "wait_main_robot":
        yield self.hold(1.0)
```

9Der Korridorarm verwendet denselben Ablauf mit seinen eigenen Aktionstypen:

```python
while True:
    yield self.bridge.request_action(self)
    action = yield self.bridge.action(self)

    if action.action_type == "pick_corridor_arm_robot":
        yield from self.execute_pick_action(action)
    elif action.action_type == "place_corridor_arm_robot":
        yield from self.execute_place_action(action)
    elif action.action_type == "wait_corridor_arm_robot":
        yield self.hold(1.0)
```

#### Prüfung eines Pick-Jobs

Eine Prüfung gibt es weiterhin. Entfernt wurde nur die frühere Auswahl eines
Ersatzjobs durch den Simulationsroboter.

Eine Policy-Entscheidung basiert auf einer Beobachtung. Zwischen dieser
Beobachtung und der Ausführung kann ein anderer Roboter den Job bereits
entnommen haben. `take_selected_job_from_store()` prüft deshalb den aktuellen
Inhalt des Stores. Ist der ausgewählte Job nicht mehr vorhanden, wird bei einem
nichtleeren Store **kein anderer Job** ausgewählt. Die veraltete Aktion wird
abgebrochen; anschließend fordert der Roboter eine neue Entscheidung der
Steuerung an.

Die Beobachtung ist nur eine Momentaufnahme. Ein möglicher Ablauf ist:

```text
Zeitpunkt 1: Der Store enthält Job A und Job B. Die Policy wählt Job A.
Zeitpunkt 2: Ein anderer Roboter nimmt Job A bereits aus dem Store.
Zeitpunkt 3: Der erste Roboter möchte die Pick-Aktion für Job A ausführen.
```

Darum wird der Store unmittelbar vor dem Pick erneut geprüft:

```text
Job A ist noch vorhanden  → Job A wird genommen.
Job A ist verschwunden     → Die Pick-Aktion wird abgebrochen.
Store ist leer             → Die Pick-Aktion wird ebenfalls abgebrochen.
```

Diese Prüfung ist nur eine technische Absicherung gegen eine veraltete
Entscheidung. Sie wählt niemals selbst einen Ersatzjob. Die nächste Jobauswahl
kommt ausschließlich von der Steuerung.

```python
selected_job = action.payload["selected_job"]
current_items = target_store.as_list()
if selected_job not in current_items:
    return None

def is_selected_job(item):
    if item is selected_job:
        return True
    return False

job = yield self.from_store(
    target_store,
    filter=is_selected_job,
)
return job
```

Die beiden Robotertypen prüfen das Ergebnis der Methode. Bei `None` wird die
veraltete Pick-Aktion beendet; beim nächsten Durchlauf fordert der Roboter eine
neue Aktion an. Nur die Steuerung darf dann den nächsten Job auswählen:

```python
job: SimOrderJob | None = yield from self.take_selected_job_from_store(action, target_store)
if job is None:
    return
```

Beim Pick ist `target_store` der Store, **aus dem** der Job genommen wird. Beim
Place ist `target_store` der Store, **in den** der Job gelegt wird. Der Name ist
also für beide Aktionen gleich, die Bedeutung ergibt sich aus der Aktion.

#### Korridor über Objekt oder Namen auflösen

Der Main-Roboter berechnet den Listenindex eines konfigurierten Korridors. Die
Methode akzeptiert entweder dasselbe Objekt oder einen Korridor mit demselben
Namen:

```python
corridor_name = getattr(corridor, "name", None)
for index, configured_corridor in enumerate(self.layout.corridors):
    if configured_corridor is corridor:
        return index
    if corridor_name is not None and configured_corridor.name == corridor_name:
        return index
raise ValueError(
    f"Corridor {corridor_name!r} gehört nicht zum Layout "
    f"{self.layout.name!r}."
)



Simulation ändert sich
→ Bridge erstellt Beobachtung
→ Main-Roboter wird beobachtet
→ selected_machine wird gelesen
→ deren corridor wird gesucht
→ configured_corridor_index() liefert den Index
```

Für Laufzeitkorridore gibt es zusätzlich `simulation_corridor_index()`. Diese
Methode vergleicht das Laufzeitobjekt selbst oder den Namen des darin enthaltenen
konfigurierten Korridors. So wird nicht fälschlich nur die Python-Objektidentität
vorausgesetzt.

Die `SimulationBridge` übersetzt vorher die von der Policy verwendete ID, zum
Beispiel `sim_corridor_id`, in das echte `SimCorridor`-Objekt. Ebenso wird
`target_store_id` in den echten Salabim-Store übersetzt.

#### Schutz für minimierte 3D-Fenster

Der Schutz befindet sich in `sources/SpineML/simulate.py`. Vor dem eigentlichen
Salabim-Zeichnen wird die Fensterhöhe abgefragt:

```python
def draw_with_zero_size_guard(animation, time):
    window_height = glut.glutGet(glut.GLUT_WINDOW_HEIGHT)
    if window_height <= 0:
        return
    return draw(animation, time)
```

Bei einer Fensterhöhe von `0` wird nur das Zeichnen übersprungen. Dadurch wird
kein OpenGL-Aufruf mit einer ungültigen Fenstergröße ausgeführt. Die Simulation,
die Aktionen der Roboter und die Kennzahlen werden davon nicht verändert. Der
Schutz wird nur bei `animate=True` aktiviert.

### Prozessabläufe der Laufzeitobjekte

Die Laufzeitobjekte arbeiten jetzt in einem wiederholten
Entscheidungszyklus. Sie führen nicht selbstständig eine fest vorgegebene
Route aus, sondern fordern für den nächsten Schritt eine Aktion an.

Der Job-Prozess:

```text
Aktion bei der Bridge anfordern
→ Aktion und Zustandsänderungen übernehmen
→ freigegebenen oder wartenden Job weiter beobachten
→ Nacharbeit, Herabstufung oder Ausschuss behandeln
→ bei finish_process den Job beenden
```

Der Maschinen-Prozess:

```text
Maschinenzustand melden
→ Job aus dem Eingangspuffer aufnehmen
→ Werkzeug vorbereiten oder wechseln
→ ausgewählte Operation bearbeiten
→ Defekt und Defektschweregrad bestimmen
→ Job in den Ausgangspuffer legen
```

#### Was bedeutet „Defekt und Defektschweregrad bestimmen“?

Nach der Bearbeitung prüft die Maschine den Job mit einem eigenen
Zufallsgenerator. Der relevante Code lautet:

```python
defect_severity = None

quality_key = (
    f"{self.QUALITY_SEED}|{job.scenario.name}|{job.order.name}|"
    f"{job.number}|{operation.name}|{job.rework_count}"
).encode("utf-8")

quality_rng = random.Random(
    int.from_bytes(
        hashlib.sha256(quality_key).digest()[:8],
        "big",
    )
)

if quality_rng.random() < operation.defect_probability:
    defect_severity = quality_rng.random()
```

Die Ausführung ist nacheinander:

1. `defect_severity = None` bedeutet: Zunächst wurde kein Defekt gefunden.
2. `quality_key` verbindet den Simulations-Seed mit Szenario, Auftrag, Job,
   Operation und Nacharbeitszähler. Jeder Prüfversuch bekommt dadurch einen
   eindeutigen Schlüssel. gleicher Job und gleicher Nacharbeitszähler → gleiches Ergebnis
3. SHA-256 wandelt diesen Schlüssel in eine feste Zahl um. Diese Zahl startet
   `quality_rng`, einen eigenen Zufallsgenerator für genau diese Prüfung.
4. Der erste Aufruf von `quality_rng.random()` entscheidet über den Defekt.
   Die Zahl liegt zwischen `0` und `1`. Ist sie kleiner als
   `operation.defect_probability`, entsteht ein Defekt.
5. Nur bei einem Defekt wird eine zweite Zufallszahl erzeugt. Sie wird als
   `defect_severity` zwischen `0` (leicht) und `1` (schwer) gespeichert.

Beispiel: Bei `defect_probability = 0.20` führt der erste Wert `0.13` zu
einem Defekt; der zweite Wert `0.74` ist dann dessen Schweregrad. Der erste
Wert `0.67` führt dagegen zu keinem Defekt, und `defect_severity` bleibt
`None`. Der Nacharbeitszähler sorgt dafür, dass erneute Bearbeitungen eine
neue, aber mit demselben Seed reproduzierbare Prüfung erhalten.

Der Main-Roboter-Prozess:

```text
Aktion anfordern
→ Job aus Start- oder Corridor-Store aufnehmen
→ zum Ziel bewegen
→ Job in Corridor-Store oder Endlager ablegen
→ Ein- und Auslagerungszeit abwarten
```

Der Korridorarm-Roboter-Prozess:

```text
Aktion anfordern
→ Job aus dem Corridor-Eingang oder Maschinen-Ausgang aufnehmen
→ Job zur nächsten Maschine, zum anderen Arm oder zum Main-Store bewegen
→ Job ablegen
→ nächste Aktion anfordern
```

Wenn keine ausführbare Aktion möglich ist, führt das Objekt eine Warteaktion
aus und wird danach erneut bewertet. Dadurch können sich Entscheidungen nach
Kapazitätsänderungen, abgeschlossener Bearbeitung oder einem Qualitätsereignis
ändern.

### Warum der Job nicht mehr `passivate()` und `activate()` verwendet

`wait_job` ist in der aktuellen Implementierung keine dauerhafte
Passivierung. Der Job bleibt im Entscheidungszyklus und wartet nur eine kurze
Zeit:

```python
if action.action_type == "wait_job":
    yield self.hold(1.0)
    continue
```

Danach läuft die `while`-Schleife weiter und fordert erneut eine Aktion an.
Auch beim Warten auf eine Aktion der Bridge wird der Job nicht passiviert,
sondern wartet auf seinem persönlichen Action-Store:

```python
yield self.bridge.request_action(self)
action = yield self.bridge.action(self)
```

Die frühere Variante mit `passivate()` und `activate()` wurde deshalb aus
`SimOrderJob` entfernt. `mark_finished()` speichert jetzt nur noch den
Abschlusszeitpunkt; `mark_defective()` speichert nur noch die Defektangaben.

## 3. Steuerungsarchitektur

Unter `sources/SpineML/Control/` gibt es eine eigene Steuerungsschicht mit vier Bereichen:

```text
Interface/        → gemeinsame Datentypen und Verträge
GeneralControl/   → erzeugt, bewertet und wählt Aktionen
SimulationBridge/ → vermittelt Zustände und Aktionen
HeuristicControl/ → bewertet und optimiert mit Heuristik
```

Der Ablauf einer Entscheidung ist:

```text
Simulationsobjekt fordert eine Aktion an
→ Bridge erstellt eine Beobachtung
→ Generator erzeugt mögliche Aktionen
→ Evaluator berechnet ihre Bewertungen
→ Selector wählt eine Aktion
→ Bridge liefert die Aktion an das Simulationsobjekt
→ Aktion wird in Salabim ausgeführt
```

Die Policy arbeitet mit stabilen IDs und einfachen Dictionaries. Erst die
Bridge löst diese IDs in die tatsächlichen Simulationsobjekte auf.

### Nachrichten und Entscheidungsablauf

Für die Kommunikation gibt es einheitliche Zustands- und Aktionsnachrichten:

```text
CurrentSimulationState → Zustand eines Jobs, einer Maschine oder eines Roboters
PolicyTrigger          → meldet den Bedarf einer neuen Entscheidung
PolicyObservation      → gemeinsamer Fabrikzustand für die Policy
PolicyDecision         → ausgewählte abstrakte Aktion
SimulationAction       → ausführbare Aktion für ein Salabim-Objekt
```

Die Bridge registriert alle steuerbaren Objekte und deren Stores. Jedes Objekt
besitzt einen eigenen Aktionskanal. Mehrere gleichzeitige Trigger werden in
einer gemeinsamen Beobachtung verarbeitet. Vor der Zustellung wird die
Zustandsversion geprüft, damit keine veraltete Entscheidung ausgeführt wird.
Eine Pick-Aktion reserviert ihren Job außerdem für diese gemeinsame
Entscheidungsrunde. Dadurch können nicht zwei Roboter gleichzeitig denselben
Job aufnehmen. Inhaltlich gleiche unmittelbare Aktionen werden nur einmal als
Kandidat bewertet.

### Beobachtungen

Die Policy erhält einen gemeinsamen Snapshot mit:

```text
aktuelle Simulationszeit
Zustand aller registrierten Jobs
Zustand aller Maschinen und Roboter
Inhalte und Kapazitäten der Stores
statisches Konfigurationsmodell
Zustandsversion
```

Dadurch kann eine Entscheidung den Zustand der gesamten Fabrik
berücksichtigen.

Die Beobachtungen enthalten außerdem konkrete Daten:

```text
Job       → Position, Qualitätszustand, Termin, nächste Operation und Maschine
Maschine  → Zustand, Werkzeug, Werkzeuglebensdauer und Pufferkapazitäten
Roboter   → Position, Bewegung, Ladezustand, Ziel-Store und aktueller Job
Modell    → Produkte, Operationen, Werkzeuge, Maschinen, Korridore und Layouts
```

Das statische Modell wird als ID-basiertes Dictionary bereitgestellt. Dadurch
arbeitet die Policy mit Daten und IDs und nicht mit direkten Salabim-Objekten.

### Aktionen und Routen

Der `SpineActionGenerator` berechnet aus Produktzustand und Layout mögliche
Operationen- und Maschinenfolgen. Daraus entstehen Aktionen für:

```text
Job freigeben oder warten
Main-Roboter aufnehmen oder ablegen lassen
Korridorarm-Roboter aufnehmen oder ablegen lassen
Job auf einer Maschine aufnehmen oder bearbeiten
Nacharbeit auf derselben Maschine
Nacharbeit auf einer alternativen Maschine
Produktherabstufung
Ausschuss
```

Ein `ActionSelector` bewertet alle Kandidaten und wählt den höchsten Score.
Bei gleichen Scores wird der Seed verwendet. Zusätzlich kann eine fast gleich
gute produktive Alternative mit kleiner Wahrscheinlichkeit exploriert werden.
Eine Warteaktion wird nicht bevorzugt, wenn eine technisch mögliche produktive
Aktion vorhanden ist. Eine vom `ActionSelector` ausgewählte Warteaktion wird
jedoch nicht nachträglich durch die Simulation oder Policy ersetzt.

Bei Nacharbeit werden nur technisch mögliche Routen angeboten. Die defekte
Maschine wird bei einer alternativen Maschinenroute ausgeschlossen.

## 4. Qualität und reproduzierbare Zufallswelten

Vor jedem Simulationslauf wird ein Seed gesetzt. Für einen Job und eine
Operation wird ein fester Schlüssel aus Seed, Szenario, Auftrag, Jobnummer,
Operation und Nacharbeitszähler gebildet.

Dieser Schlüssel erzeugt reproduzierbare Pseudozufallswerte für:

```text
Defekt ja/nein
Defektschweregrad
```

Bei gleichem Seed erhält derselbe Job dieselben Qualitätsereignisse. Die
Steuerung kann danach entscheiden, ob Nacharbeit, Herabstufung oder Ausschuss
folgt.

Ein Job kann einen Defekt auf der ursprünglichen Maschine nacharbeiten oder
eine alternative Maschine verwenden. Ist keine zulässige Nacharbeit möglich,
kann der Job herabgestuft oder als Ausschuss beendet werden. Die Zähler und
Statuswerte für Defekte, Nacharbeit, Herabstufung und Ausschuss bleiben im Job
erhalten. Für die globalen Nacharbeits- und Herabstufungsquoten wird ein Job
jeweils höchstens einmal gezählt, auch wenn mehrere Aktionen stattgefunden
haben.

Maschinen und Roboter erhalten zusätzlich reproduzierbare
Geschwindigkeitsabweichungen. Dadurch entstehen unterschiedliche, aber
wiederholbare Simulationsverläufe für verschiedene Seeds.

Die Bearbeitungsdauer wird nicht nur aus der Operationsdauer übernommen. Sie
berücksichtigt außerdem Produktgewicht, Produktvolumen,
Maschinengeschwindigkeitsfaktor und eine kleine reproduzierbare
Laufvariation. Ein einmaliger reproduzierbarer Startup-Verzug kann zusätzlich
unterschiedliche Maschinenengpässe erzeugen.

## 5. Globale Kennzahlen und Zielfunktion

Der headless Simulationsrunner führt einen vollständigen Lauf für einen
Gewichtssatz und einen Seed aus und sammelt pro Lauf:

```text
makespan
total_tardiness
total_transport_time
tool_change_time
blocking_time
rework_rate
scrap_rate
defect_rate
downgrade_rate
intact_rate
unfinished_rate
```

Zusätzlich werden Anzahlwerte für alle Jobs gesammelt:

```text
total_jobs
completed_jobs
unfinished_jobs
intact_jobs
defect_jobs
rework_job_count
scrap_job_count
downgraded_job_count
```

Bei mehreren Seeds bleibt jede Kennzahl zunächst einem einzelnen Seed
zugeordnet. Für die Optimierung werden die globalen Kosten danach über alle
Seeds gemittelt.

Aus den Jobzählungen werden zusätzlich Abschluss-, Intakt-, Defekt-,
Nacharbeits-, Ausschuss-, Herabstufungs- und Unfertigenraten abgeleitet.

Die Qualitätskennzahlen werden als Raten ausgewertet. Zeitkennzahlen werden
durch dynamisch aus der Baseline bestimmte Skalen geteilt. Anschließend werden
die normalisierten Kennzahlen mit den globalen Gewichten multipliziert und zu
einem globalen Kostenwert addiert.

Die Zeit-Skalen werden als Mittelwerte der Baseline-Läufe berechnet. Wenn ein
Zeitmittelwert null ist, wird eine positive Fallback-Skala verwendet, damit
keine Division durch null entsteht. Qualitätsraten werden direkt verwendet und
nicht durch statische Skalen geteilt.

Die Baseline berechnet diese Skalen einmal mit allen verwendeten Seeds. Die
Kandidaten während der Optimierung und der abschließende optimierte Lauf
verwenden dieselben Skalen; dadurch bleibt der Kostenvergleich innerhalb
dieses Optimierungslaufs konsistent.

Die Zielfunktion kann Zeit, Verspätung, Transport, Werkzeugwechsel,
Blockierung, Nacharbeit, Ausschuss, Defekte, unfertige Jobs und nicht-intakte
Jobs unterschiedlich gewichten.

Die Tardiness wird pro Auftrag anhand des spätesten Jobabschlusses berechnet.
Der Makespan beschreibt den Zeitraum vom ersten Produktionsstart bis zum
letzten Abschluss.

## 6. Heuristische Steuerung und Optimierung

`HeuristicWeights` enthält die lokalen Gewichte der Aktionsbewertung.
`LocalHeuristicActionEvaluator` berechnet damit einen Score für jeden
technisch möglichen Aktionskandidaten.

Bewertet werden unter anderem:

```text
EDD- und Queue-Priorität
freie Pufferkapazität
Transport- und Einlagerungszeit
Bearbeitungsdauer
passendes Werkzeug und verbleibende Werkzeuglebensdauer
Nacharbeitszeit und erwartete Reparaturqualität
Zeit bis zur Auftragsdeadline
```

Für die Nacharbeitsbewertung werden Operationsdauer, Produktgewicht,
Produktvolumen und Werkzeugverbrauch relativ zu den jeweiligen Maximalwerten
des geladenen Fabrikmodells normiert. Daraus entstehen vergleichbare
Schätzungen für Zeitaufwand, Qualitätsrisiko und Nacharbeitskosten.

`LocalHeuristicWeightOptimizer` testet mehrere lokale Gewichtssätze:

```text
Startgewichtssatz erzeugen
→ Nachbar- und Explorationskandidaten erzeugen
→ jeden Kandidaten mit mehreren Seeds simulieren
→ globale Kosten je Seed berechnen
→ Mittelwert über die Seeds bilden
→ besten Kandidaten der Runde übernehmen
→ mehrere Optimierungsrunden durchführen
```

Eine Optimierungsrunde prüft mehrere lokale Gewichtssätze. Jeder Kandidat wird
mit jedem verwendeten Seed simuliert. Der Kandidat mit dem niedrigsten
Mittelwert der globalen Kosten wird als bester Kandidat der Runde übernommen.
Die Gewichtsschrittweite wird nach einer Verbesserung verkleinert. Nach
mehreren erfolglosen Runden kann ein Neustart erfolgen; bei zu vielen
erfolglosen Runden wird die Suche beendet.

Die aktuelle Suche verwendet zwei Seeds, zwei Optimierungsrunden, eine
anfängliche Gewichtsschrittweite von 0,40 und drei zusätzliche
Explorationskandidaten pro Runde. Nach zwei erfolglosen Runden wird ein
Neustart versucht; nach vier erfolglosen Runden wird die Suche beendet.

Das Ergebnis enthält:

```python
@dataclass(frozen=True)
class WeightOptimizationResult:
    best_weights: HeuristicWeights
    best_mean_global_cost: float
    evaluations: tuple[WeightEvaluation, ...]
```

## 7. Allgemeiner Optimierungsstarter

`sources/optimization.py` stellt einen allgemeinen Startpunkt für die
Examples bereit.

Die auswählbare Modelldatei wird geladen, ohne dass die Modelldatei dabei
bereits selbst eine Simulation oder Visualisierung startet. Layout und
Szenario werden aus dem Modell ermittelt. Der dazugehörige Optimierer wird für
das ausgewählte Modell zwischengespeichert. Die Oberfläche wird lokal mit
Streamlit ausgeführt und zeigt:

```text
aktuellen Status
Optimierungsrunde
aktuellen Kandidaten
Fortschritt
Kostenkurve
Kennzahlenkurven
Baseline und optimierte Ergebnisse
```

Beim Start werden die Baseline mit den Ausgangsgewichten und danach die
Kandidaten der heuristischen Suche berechnet. Nach der Suche wird der beste
Gewichtssatz erneut mit allen Seeds simuliert. Anschließend werden Baseline
und optimierte Steuerung in einer gemeinsamen Tabelle und in Diagrammen
verglichen.

Die Baseline-Simulation kalibriert dabei zuerst die dynamischen Zeit-Skalen
für die Zielfunktion. Diese Kalibrierung wird nicht bei jedem Kandidaten neu
erstellt.

Der allgemeine Starter erkennt im geladenen Beispiel den Aufruf
`simulate(layout, scenario)`, übernimmt daraus Layout und Szenario und lädt
das Beispiel ohne dessen eigene Simulation oder Visualisierung zu starten.
Ein Kompatibilitätsstarter kann dadurch für unterschiedliche Examples
verwendet werden; das ausgewählte Example wird über eine zentrale
Dateivariable festgelegt.

Die Berechnung läuft in einem Hintergrund-Thread, während die Oberfläche den
Sitzungszustand regelmäßig aktualisiert. Bei einem Fehler wird die Meldung im
Webinterface angezeigt; nach Abschluss wird der Thread beendet und das
Ergebnis im Sitzungszustand gespeichert.

Die laufenden Werte liegen im Streamlit-Sitzungszustand und werden während
der Optimierung aktualisiert.

## 8. Examples

Die Examples verwenden die erweiterten Konfigurationsdaten und die neuen
Maschinenpuffer. Example 0 bildet mehrere mögliche Produktionswege und
Maschinenfolgen ab. Example 1, 2 und 4 wurden an die zusätzlichen Layout- und
Maschinenparameter angepasst.

Example 3 beschreibt eine konkrete Gehäusefertigung mit drei Maschinentypen,
zwei Korridoren, acht Maschinen und vier Aufträgen mit jeweils zwei Jobs.
Die Dateien sind nach ihrer Aufgabe getrennt:

```text
sources/examples/normal/
    example-0.py
    example-1.py
    example-2.py
    example-3.py
    example-3b-quality.py
    example-4.py

sources/examples/optimization/
    example-0-optimize.py
    example-3-optimize.py
    example-3b-quality-optimize.py
```

Die Dateien im Ordner `normal` starten jeweils einen einzelnen normalen
Simulationslauf. Die Dateien im Ordner `optimization` sind nur kurze Starter;
die eigentliche Optimierungslogik liegt zentral in `sources/optimization.py`.
Für Example 3 gibt es zusätzlich:

```text
examples/normal/example-3b-quality.py
    Qualitätsvariante mit schnellem und qualitätsorientiertem Prozess

examples/optimization/example-3-optimize.py
    kompatibler Starter für die Optimierung

examples/optimization/example-3b-quality-optimize.py
    kompatibler Starter für die Qualitätsvariante

examples/optimization/example-0-optimize.py
    kompatibler Starter für die Optimierung von Example 0
```

Der allgemeine Optimierungsstarter kann die Modelldatei laden und die
Simulation mit Baseline- und optimierten Gewichten ausführen.

## 9. Aufgeräumte Bestandteile

Im Vergleich zum lokalen `main` wurde folgende alte Funktion entfernt:

```text
separate calculate.py-Routenlogik
zusätzliche Produktzustandszyklus-Prüfung
```

`optimization_dashboard.py` und `recursion_path_search_example.py` waren im
lokalen `main` nicht vorhanden und werden deshalb nicht als Änderungen dieses
Vergleichs gezählt.

Die Routenberechnung liegt jetzt im `SpineActionGenerator`, und die
Entscheidungslogik ist über die Policy-Schnittstelle erreichbar.

Die folgenden Abschnitte beschreiben die Implementierung vollständig nach
Eingabe, Verarbeitung und Ausgabe der einzelnen Bausteine.

## 10. Konfigurationsobjekte: Eingaben und gespeicherte Daten

Alle Konfigurationsklassen erzeugen normale Python-Objekte. Zusätzlich werden
die erzeugten Objekte in globalen Listen gesammelt. Dadurch können Simulation
und Policy später alle ProductTypes, OperationTypes, Machines, Tools,
Corridors und Layouts aus dem Modell aufbauen.

### ProductType

```python
class ProductType:
    def __init__(self, name: str, length: int, width: int, depth: int, weight: int) -> None:
```

Die Eingaben sind Name, Abmessungen und Gewicht. Das Objekt speichert diese
fünf Werte sowie Listen der Operationen, die den Produkttyp verbrauchen oder
erzeugen, und der Aufträge, die ihn benötigen.

### ToolType

```python
class ToolType:
    def __init__(self, name: str, mount_time: int, unmount_time: int, total_life_units: int) :
```

Gespeichert werden Name, Montagezeit, Demontagezeit und gesamte
Werkzeuglebensdauer. Jede Operation, die dieses Werkzeug benötigt, wird in
seiner Operationsliste registriert.

### MachineType

```python
class MachineType:
    def __init__(self, name: str) :
```

Ein Maschinentyp speichert seine Maschinen und Operationen. Die Methode
`computeToolTypes()` durchsucht die zugeordneten Operationen und gibt jeden
benötigten Werkzeugtyp genau einmal zurück. Das ist die automatische
Werkzeugliste für eine konkrete Maschine, wenn dort keine eigene Liste
angegeben wird.

### OperationType

```python
class OperationType:
    def __init__(self, name: str, duration: int, consumes_life_units: int, defect_probability: float, machine_type: MachineType, tool_type: ToolType, consumes_product_type: ProductType, produces_product_type: ProductType) -> None:
```

Eine Operation beschreibt eine Produktumwandlung. Sie benötigt einen
Maschinentyp und ein Werkzeug, verbraucht einen Produkttyp und erzeugt einen
anderen Produkttyp. Beim Erzeugen wird die Operation automatisch beim
Maschinentyp, Werkzeug, Eingangsprodukt und Ausgangsprodukt registriert.

### Scenario und Order

```python
class Scenario:
    def __init__(self, name: str) -> None:

class Order:
    def __init__(self, name: str, quantity: int, earliest_start_time: int, latest_end_time: int, product_type: ProductType, scenario: Scenario) -> None:
```

Ein Szenario enthält seine Aufträge. Ein Auftrag speichert Menge, früheste
Startzeit, spätesten Endtermin, Zielprodukt und Szenario. In der Laufzeit wird
aus jedem Auftrag mit `quantity` einzelnen Jobs jeweils ein eigenes
`SimOrderJob` erzeugt.

### Layout

```python
class Layout:
    def __init__(self, name: str, storage_out_time: int, storage_in_time: int, storage_capacity: int) -> None:
```

Das Layout speichert seine Lagerzeiten und die Kapazität. Die Kapazität wird
später separat an Startlager und Endlager übergeben. Das Layout enthält außerdem
seine Korridorliste.

### Corridor

```python
class Corridor:
    def __init__(self, name: str, storage_capacity: int, storage_out_time: int, storage_in_time: int, layout: Layout) -> None:
```

Der Korridor speichert Kapazität, Einlagerungszeit, Auslagerungszeit und seine
Zugehörigkeit zum Layout. Maschinen werden getrennt in `machines_left` und
`machines_right` eingetragen.

### Machine

```python
class Machine:
    def __init__(
        self,
        name: str,
        machine_type: MachineType,
        corridor: Corridor,
        left: bool,
        input_storage_capacity: int,
        output_storage_capacity: int,
        tool_types: list[ToolType] | None = None,
        processing_speed_factor: float = 1.0,
    ) -> None:
```

Die Maschine speichert ihre Position im Korridor, zwei voneinander unabhängige
Pufferkapazitäten, erlaubte Werkzeuge und den Geschwindigkeitsfaktor. Zusätzlich
besitzt jede Maschine ein Schutzwerkzeug mit einer Montage- und Demontagezeit
von jeweils einer Zeiteinheit. Wird `tool_types` nicht übergeben, liefert
`machine_type.computeToolTypes()` die Werkzeugliste.

## 11. Vollständiger Ablauf eines Simulationslaufs

### Eingabe und Ausgabe von `simulate`

```python
def simulate(
    layout: Layout,
    scenario: Scenario,
    animate=True,
    till=sim.inf,
    policy: Policy | None = None,
    bridge: SimulationBridge | None = None,
    animation_speed=5,
):
```

Eingaben sind ein konfiguriertes Layout, ein Szenario und optional eine Policy,
eine bereits vorhandene Bridge, eine Endzeit und die Animationsgeschwindigkeit.
Die Methode liefert keinen Kennzahlenwert zurück. Sie erzeugt und startet die
Salabim-Umgebung, führt die Prozesse aus, druckt Statistiken und erstellt die
Plots.

Intern geschieht Folgendes:

```text
Salabim-Modus setzen
→ Environment mit Zeiteinheit Stunden erzeugen
→ optional Fenster und 3D-Animation konfigurieren
→ SimulationBridge erzeugen oder übernommene Bridge verwenden
→ SimLayout erzeugen
   → Startlager, Endlager, Korridore, Maschinen und Roboter erzeugen
→ SimScenario erzeugen
   → Aufträge und Jobs erzeugen
   → CompletionWatcher erzeugen
→ env.run(till)
→ SimulationStopped als normales Fertig-Signal behandeln
→ optional Maschinen mit Schutzwerkzeug zurücksetzen
→ Statistiken und Diagramme ausgeben
```

Wenn `animate=False` verwendet wird, wird keine 3D-Darstellung geöffnet. Der
headless Runner verwendet genau diesen Simulationskern ohne Animation.

### SimLayout

`SimLayout(layout, scenario, bridge)` erhält Layout, Szenario und Bridge.
Erzeugt werden:

```text
store_start  mit layout.storage_capacity
store_end    mit layout.storage_capacity
für jeden Corridor ein SimCorridor
ein SimRobotMain
```

`simMachines()` liefert eine flache Liste aller Laufzeitmaschinen aus beiden
Korridorseiten. Diese Liste wird für Werkzeug-, Blockierungs- und
Abschlussauswertungen verwendet.

### SimCorridor und SimCorridorArm

`SimCorridor` erzeugt für jeden Korridor drei Stores:

```text
store_main
store_left
store_right
```

Alle drei erhalten `corridor.storage_capacity`. Für die linke und rechte Seite
wird jeweils ein `SimCorridorArm` erzeugt. Ein Arm erzeugt seine
`SimMachine`-Objekte und – falls Maschinen vorhanden sind – einen
`SimRobotCorridorArm`.

### SimScenario und SimOrder

`SimScenario` läuft über `scenario.orders` und erzeugt für jeden Auftrag einen
`SimOrder`. `SimOrder` läuft über `order.quantity` und erzeugt die einzelnen
`SimOrderJob`-Komponenten. Deshalb bedeutet eine Auftragsmenge von zwei nicht
eine zweite Simulation, sondern zwei unabhängige Jobs desselben Auftrags.

### SimCompletionWatcher

Der Watcher prüft regelmäßig `process_finished` aller Jobs. Wenn mindestens ein
Job existiert und alle Jobs fertig sind, löst er `sim.SimulationStopped` aus.
`SimulationStopped` stammt aus Salabim und wird von SpineML nur ausgelöst und
abgefangen. Der Runner fängt dieses Signal ab und behandelt es nicht als
Fehler. Dadurch endet ein vollständiger Lauf automatisch, auch wenn
`till=sim.inf` gesetzt ist.

### Was entscheidet die Steuerung, was entscheidet die Simulation?

Die Policy beziehungsweise der ActionGenerator und der ActionEvaluator wählen
die nächste Produktionsaktion: Freigabe, Transport, Bearbeitung, Warten,
Nacharbeit, Ausschuss oder den Abschluss eines Jobs. Die `Sim*`-Komponenten
führen diese gewählte Aktion aus und prüfen dabei technische Bedingungen wie
Store-Kapazität, Bewegungsdauer und Werkzeuglebensdauer.

Das Ende ist deshalb zweistufig:

1. Die Steuerung erzeugt für jeden fertigen Job eine `complete_job`-Aktion mit
   `"finish_process": True`.
2. Der rein technische `SimCompletionWatcher` erkennt, dass alle Jobs dieses
   Kennzeichen besitzen, und löst `sim.SimulationStopped` aus.

`SimMachineShutdown` ist keine Policy-Entscheidung und keine Produktionsaktion.
Sie ist eine optionale technische Aufräumkomponente, die am Ende ein
Schutzwerkzeug montiert. Die aktuelle Implementierung ist daher nicht völlig
„dumm“ im Sinn eines passiven Datenmodells: Sie enthält weiterhin die
physikalische Ausführung und die Abschlussüberwachung. „Dumm“ bedeutet hier,
dass sie keine Produktionsroute oder Gewichtungsentscheidung selbst auswählt;
diese Entscheidung kommt aus der Steuerung.

Der konkrete Datenfluss ist:

```text
SimulationBridge fragt die Policy nach einer Aktion
→ ActionGenerator erzeugt mögliche Aktionen
→ ActionEvaluator bewertet diese Aktionen
→ Policy/Selector wählt eine Aktion
→ Bridge übergibt die gewählte Aktion an die passende Sim*-Komponente
→ Sim*-Komponente führt sie aus und aktualisiert den Zustand
→ Zustand wird wieder beobachtet
→ nächster Entscheidungszyklus
```

Beim Abschluss eines Jobs ergänzt die Steuerung `finish_process=True`. Erst
danach erkennt der `SimCompletionWatcher`, dass alle Jobs fertig sind, und
beendet den Lauf über `sim.SimulationStopped`. Das Shutdown-Aufräumen ist davon
getrennt und wird nicht von der Policy ausgewählt.

## 12. Laufzeitprozess eines Jobs

### Eingabe

`SimOrderJob` erhält Layout, Szenario, Auftrag, Jobnummer, Start-Store und
Bridge. Beim Erzeugen werden alle Laufzeitfelder mit Anfangswerten belegt:

```text
released = False
location = "start_storage"
processing_state = "unconfigured"
general_state = "intact"
due_state = None
completed_time = None
process_finished = False
downgraded = False
downgrade_product_type = None
defect_count = 0
rework_count = 0
scrap_count = 0
```

### Entscheidungszyklus

Der Job-Prozess arbeitet dauerhaft in dieser Schleife:

```text
Bridge um eine Aktion bitten
→ eigene SimulationAction aus dem persönlichen Action-Store lesen
→ Payload-Felder in die eigenen Attribute übernehmen
→ optional auf release_time warten
→ optional in target_store ablegen
→ Aktion ausführen
→ Zustandsänderung melden
→ eine Zeiteinheit warten
→ nächste Aktion anfordern
```

Die Payload kann Operation, Maschine, Produktionszustand, Qualitätszustand,
Terminstatus, Freigabe, Priorität, Abschlusszeitpunkt und Defektinformationen
enthalten. Der Job wird bei `wait_job`, Freigabe und Nacharbeitsentscheidungen
nicht beendet, sondern später erneut bewertet.

### Freigabe

Eine `release_job`-Aktion setzt den ersten Produktionszustand, markiert den Job
als freigegeben und verwendet:

```text
release_time = max(aktuelle Simulationszeit, earliest_start_time)
```

Vor diesem Zeitpunkt bleibt der Job im Startlager und wird nicht bearbeitet.

### Abschluss

Bei `complete_job` setzt die Aktion den Terminstatus. Der Main-Roboter ruft
`mark_finished()` auf, setzt `completed_time` auf die aktuelle Simulationszeit
und legt den Job ins Endlager. Erst eine Payload mit `finish_process=True` setzt
`process_finished=True` und beendet den Job-Prozess.

## 13. Laufzeitprozess einer Maschine

### Eingabe und Konstruktion

`SimMachine` erhält eine konfigurierte Maschine, Bridge und Position. Sie
erzeugt zwei echte Salabim-Stores:

```text
store_in   mit machine.input_storage_capacity
store_out  mit machine.output_storage_capacity
```

Für jedes erlaubte Werkzeug werden aktuelle, vorherige und nächste
Lebensdauereinheiten gespeichert. Diese Werte werden auch für die animierten
Lebensdauerbalken verwendet.

### Maschinenprozess

```text
store_out prüfen
→ bei fehlender Kapazität Zustand "blocked" setzen
→ Bridge um eine Aktion bitten
→ Job aus store_in aufnehmen oder warten
→ Werkzeug vorbereiten
→ Operation ausführen
→ Qualitätsereignis bestimmen
→ Job in store_out ablegen
→ current_job löschen
→ nächste Aktion anfordern
```

Die Maschine verarbeitet nur eine Operation, die in der Place-Aktion bereits
für diesen Job und diese Maschine ausgewählt wurde. Die Maschine würfelt die
Route nicht erneut.

### Werkzeugwechsel

Die Action-Payload enthält eine der folgenden Setup-Entscheidungen:

```text
keep_tool
unmount_dummy_tool_and_mount_tool
unmount_and_mount_tool
replace_tool_same_type
```

Beim ersten Werkzeug wird zunächst das Schutzwerkzeug demontiert. Bei einem
anderen Werkzeug wird das bisherige Werkzeug demontiert und das neue montiert.
Wenn die verbleibende Lebensdauer nicht ausreicht, wird ein neues Werkzeug
gleichen Typs eingesetzt. Montage- und Demontagezeiten zählen zur
Werkzeugwechselzeit.

### Bearbeitungsdauer

Für ein Produkt wird zunächst das Volumen berechnet:

```text
volume = length × width × depth
```

Die tatsächliche Dauer ist:

```text
operation.duration
× (1 + 0,5 × (product.weight / max_product_weight)
     + 0,5 × (volume / max_product_volume))
÷ processing_speed_factor
× processing_variation
```

`max_product_weight` und `max_product_volume` werden einmal aus allen Produkten
des aktuellen Szenarios berechnet und an alle Maschinen weitergegeben. Der
Größenfaktor liegt dadurch zwischen `1.0` und `2.0`: Gewicht und Volumen können
die Grunddauer jeweils höchstens um 50 Prozent erhöhen.

`processing_speed_factor` wird im Simulationslauf gleichverteilt aus dem
geschlossenen Bereich `[0.45, 2.00]` gezogen. `processing_variation` ist eine
zusätzliche reproduzierbare Zufallszahl zwischen `0.90` und `1.10`. Ein
einmaliger `startup_delay` zwischen `0` und `4` Zeiteinheiten kann vor der
ersten Bearbeitung auftreten.

### Maschinenabschluss

Wenn ein Lauf das konfigurierte Ende `till` erreicht, ohne zuvor durch den
`SimCompletionWatcher` beendet worden zu sein, erzeugt `simulate()` für jede
Maschine ein `SimMachineShutdown`-Objekt. Dieses demontiert gegebenenfalls das
aktuelle Werkzeug, montiert das Schutzwerkzeug und setzt den Maschinenzustand
auf `waiting`. Ein durch den CompletionWatcher bereits mit
`SimulationStopped` beendeter Headless-Lauf wird vorher beendet; der
`SpineMLSimulationRunner` sammelt dann direkt seine Kennzahlen.

## 14. Laufzeitprozess der Roboter

### Gemeinsame SimRobot-Funktionen

`SimRobot` speichert Position, Zielposition, Ladezustand und Bewegungszustand.
`SimRobotMain` legt seine konfigurierte Grundgeschwindigkeit auf `2.0` und
`SimRobotCorridorArm` auf `1.5` fest. Die Methoden `move_x`, `move_y` und
`move_z` verwenden diese Geschwindigkeit intern. Die effektive Geschwindigkeit
lautet:

```text
effektive Geschwindigkeit
= konfigurierte Geschwindigkeit × movement_speed_multiplier
```

Der Multiplikator wird pro Lauf reproduzierbar zwischen `0.95` und `1.05`
gezogen. Nach jeder Bewegung wird der Animationszeitpunkt auf die erreichte
Position zurückgesetzt. Dadurch extrapoliert die Visualisierung nicht über das
Bewegungsziel hinaus.

Die Robotergeschwindigkeit ist eine Eigenschaft des Simulationskerns. Eine
Robotergeschwindigkeit wird deshalb nicht mehr in einer Policy-Aktion
übergeben. Die Observation darf die konfigurierte Geschwindigkeit weiterhin
anzeigen, damit der Evaluator die voraussichtliche Transportzeit schätzen kann;
die Policy kann sie aber nicht verändern.

`take_selected_job_from_store()` prüft vor dem eigentlichen Pick, ob der von
der Policy ausgewählte Job noch im Store liegt. Falls die Entscheidung wegen
eines alten Snapshots veraltet ist, wird kein anderer Job ausgewählt. Die
veraltete Pick-Aktion endet und der Roboter fordert eine neue Entscheidung der
Steuerung an.

### SimRobotMain

Der Main-Roboter hat eine konfigurierte Bewegungsgeschwindigkeit von `2.0`.
Sein Ablauf besteht aus:

```text
Startlager oder Corridor-Main-Store auswählen
→ zum Store fahren
→ Job aufnehmen
→ storage_out_time abwarten
→ zum Zielkorridor, zur anderen Arm-Seite oder zum Endlager fahren
→ storage_in_time abwarten
→ Job ablegen
→ nächste Aktion anfordern
```

Für Start- und Endlager stammen die Zeiten aus dem Layout. Für einen Korridor
stammen sie aus dem Corridor. Die Y-Positionen des Startlagers, Endlagers und
der Korridore werden aus der Korridoranzahl berechnet.

### SimRobotCorridorArm

Ein Corridor-Arm hat eine konfigurierte Bewegungsgeschwindigkeit von `1.5`.
Er kann Jobs aus seinem Corridor-Eingangsstore oder aus einem
Maschinen-Ausgangsstore aufnehmen. Danach kann er den Job:

```text
in den Eingang einer Maschine derselben Seite legen
an den anderen Arm weitergeben
in den zentralen Corridor-Main-Store legen
```

Der zentrale Main-Store liegt bei `x=0`; die seitlichen Eingangs-Stores liegen
am Zugriffspunkt des Arms. Für Corridor-Stores werden die konfigurierten
Ein- und Auslagerungszeiten abgewartet.

## 15. Steuerungsschnittstelle und Nachrichten

Die Policy bekommt keine direkten Salabim-Objekte. Sie arbeitet mit IDs,
Zahlen, Texten, Booleans, Listen und Dictionaries. Erst die Bridge übersetzt
Policy-IDs zurück in Laufzeitobjekte.

### Beobachtung eines Simulationsobjekts

`SimulationObjectObserver.observe_simulation_object(sender, time)` erkennt den
Objekttyp und ruft die passende Beobachtungsmethode auf. Unterstützt werden
Jobs, Maschinen, der Main-Roboter und Corridor-Arm-Roboter.

### Job-Observation

Die Job-Observation enthält unter anderem:

```text
object_type, object_id, job_id, order_id, number
layout_id, scenario_id, target_product_type_id
target_product_length, target_product_width, target_product_depth
target_product_weight, quantity
earliest_start_time, latest_end_time, released
downgraded, downgrade_product_type_id, queue_priority
processing_state, general_state, due_state
defect_detected_time, defect_operation_id, defect_machine_id
defect_product_state_before, defect_product_state_target
defect_severity, defect_recovery_strategy, waiting_for_recovery_transport
completed_time, location, selected_operation_id, selected_machine_id
```

### Maschinen-Observation

Sie enthält:

```text
machine_name, machine_type_id, corridor_id, left
state, is_idle, has_current_job, can_process_current_job
processing_speed_factor, mounted_tool_type_id, dummy_tool_mounted
tool_type_names, remaining_life_units_by_tool
required_tool_type_id, required_tool_mount_time
required_tool_unmount_time, consumed_life_units
remaining_life_units_before_operation
required_tool_total_life_units, has_enough_tool_life
needs_tool_change, input_storage, output_storage
```

### Roboter-Observations

Main- und Corridor-Arm-Roboter melden Position, Bewegungszustand,
Ladezustand, Bewegungsgeschwindigkeit, aktuellen Job, nächste Operation,
nächste Maschine, Store-IDs, Store-Positionen und alle erreichbaren
Store-Inhalte. Der Main-Roboter meldet Layout-Lagerzeiten; ein Corridor-Arm
meldet die Zeiten seines Corridors.

### Store-Observation

Für jeden Store werden `store_id`, Anzahl, Kapazität, freie Kapazität,
Leerzustand, vorhandene Job-IDs, Prioritäten und Zustände der enthaltenen Jobs
gemeldet. Die Policy kann daher vor jeder Place-Aktion prüfen, ob der Ziel-Store
noch Kapazität besitzt.

### Policy-Nachrichten

```text
PolicyObservation
    gemeinsamer Snapshot plus optional aktuelle Objekt-ID

PolicyTrigger
    event_id, sender_id, state_version, time

SelectedObjectAction
    target_id, action_type, payload mit Policy-IDs

PolicyDecision
    Liste der ausgewählten SelectedObjectActions

SimulationAction
    event_id, echtes Zielobjekt, Quelltrigger, action_type, time, Payload
```

`ActionGenerator`, `ActionEvaluator`, `ActionSelector` und `Policy` sind
abstrakte Schnittstellen. Konkrete Implementierungen müssen ihre jeweiligen
Methoden bereitstellen.

### Statisches Konfigurationsmodell

`ConfigurationObjectObserver` baut einmalig ein ID-basiertes Modell mit:

```text
product_types_by_id
operations_by_id
machines_by_id
tools_by_id
corridors_by_id
layouts_by_id
configuration_maxima
```

Zusätzlich zu Namen und Beziehungen enthält das Modell Produktabmessungen,
Gewicht, Operationsdauer, Werkzeugverbrauch, Defektwahrscheinlichkeit,
Maschinenpuffer, Schutzwerkzeugzeiten, Corridor-Kapazitäten und Lagerzeiten.
`configuration_maxima` enthält maximale Operationsdauer,
Werkzeugverbrauch, Produktgewicht und Produktvolumen. Diese Werte werden für
vergleichbare Nacharbeits-Schätzungen verwendet.

## 16. SimulationBridge: interner Datenfluss

### Registrierung

`register(policy_object_id, simulation_object, stores)` legt drei Beziehungen
an:

```text
Policy-ID → echtes Simulationsobjekt
echtes Simulationsobjekt → Policy-ID
echtes Simulationsobjekt → persönlicher Action-Store
```

Übergebene Stores werden zusätzlich über ihre Namen registriert:

```text
Store-ID → echter Salabim-Store
```

`register_corridor()` registriert einen Corridor für die ID-Auflösung und seine
Stores, benötigt aber keinen persönlichen Action-Store. Beide
Registrierungsfunktionen rufen `can_register_policy_object()` auf. Ist eine
Policy-ID oder das konkrete Objekt bereits registriert, wird kein zweiter
Eintrag angelegt.

### Aktionsanforderung

Wenn ein Simulationsobjekt `request_action(self)` aufruft, passiert Folgendes:

```text
Objekt in sim_objects_waiting_for_action eintragen
→ Zustandsversionszähler erhöhen
→ PolicyTrigger erzeugen
→ Trigger in policy_trigger_store ablegen
```

`notify_state_change()` kann auch ohne neue Aktionsanforderung aufgerufen
werden, wenn sich zum Beispiel ein Store-Inhalt, ein Jobstatus oder ein
Maschinenstatus geändert hat.

### Bridge-Prozess

`SimulationBridge.process()` arbeitet in dieser Reihenfolge:

```text
ersten PolicyTrigger aus dem Trigger-Store lesen
→ Trigger derselben Simulationszeit sammeln
→ globalen Snapshot erstellen
→ PolicyDecision berechnen lassen
→ Snapshot-Version erneut prüfen
→ bei veralteter Version Snapshot und Entscheidung wiederholen
→ IDs der Entscheidung auf echte Objekte auflösen
→ SimulationActions erzeugen
→ jede Aktion in den persönlichen Action-Store ihres Ziels legen
```

Alle Objekte, die gleichzeitig eine Entscheidung benötigen, werden in einer
gemeinsamen Policy-Entscheidung berücksichtigt. Ein Job, der in derselben
Runde bereits durch einen Pick reserviert wurde, wird aus weiteren Pick-
Entscheidungen ausgeschlossen.

### ID-Auflösung

`policy_payload_id_mappings()` beschreibt, wie Payload-Schlüssel umgewandelt
werden:

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

Die Policy sieht zum Beispiel nur `selected_machine_id="Machine A"`. Die
SimulationAction enthält danach das echte `Machine`- beziehungsweise
`SimMachine`-Objekt.

## 17. ActionGenerator: alle Aktionsgruppen

`SpineActionGenerator.generate_actions(observation)` gibt eine Liste von
Aktions-Dictionaries zurück. Zuerst wird das aktuelle Objekt aus
`states_by_id` gelesen. Danach entscheidet der Objekttyp, welche Gruppe von
Aktionen erzeugt wird.

### Job-Aktionen

Ein Job kann diese Aktionen erhalten:

```text
release_job
wait_job
complete_job
job_rework_on_defect_machine
job_rework_on_alternative_machine
downgrade_product
job_scrap
```

Die Reihenfolge der Prüfung ist:

```text
bereits abgeschlossen, aber Termin noch nicht bewertet?
→ complete_job

general_state == "defect"?
→ Recovery-, Herabstufungs- oder Ausschussaktionen

noch nicht released?
→ release_job plus wait_job

sonst
→ wait_job
```

### Robot- und Maschinenaktionen

```text
Main-Roboter:
    pick_main_robot, place_main_robot, wait_main_robot

Corridor-Arm:
    pick_corridor_arm_robot, place_corridor_arm_robot,
    wait_corridor_arm_robot

Maschine:
    pick_machine_job, process_machine_job, wait_machine
```

Für jeden Job in einem Quell-Store wird ein eigener Pick-Kandidat mit
`selected_job_id` erzeugt. Place-Kandidaten enthalten Ziel-Store, nächste
Operation, nächste Maschine und gegebenenfalls Lagerzeiten.

### Routenberechnung

Die Routenberechnung arbeitet rekursiv mit den Daten des Snapshots:

```text
aktueller Produkttyp und Zielprodukttyp
→ alle möglichen Operationsfolgen suchen
→ für jede Operation Maschinen mit passendem Maschinentyp suchen
→ Layout und erlaubte Werkzeuge prüfen
→ alle gültigen Maschinenfolgen erzeugen
→ unmittelbare Place-Aktion auswählen
```

`calculate_operation_sequences_between()` sucht vorwärts zwischen zwei
Produkttypen. `calculate_operation_sequences()` sucht rückwärts alle
Operationsfolgen, die einen Zielprodukttyp erzeugen.
`calculate_machine_sequences_from_operation_sequence()` ersetzt jede
Operation durch alle kompatiblen Maschinen im Layout.

Eine Operation darf beim Place nur auf einer technisch passenden Maschine
landen. Die ausgewählte Operation und Maschine werden im Job gespeichert und
beim Maschinen-Pick wiederverwendet. Ein späterer Maschinen-Pick würfelt die
Route nicht erneut.

Vor der Rückgabe entfernt `generate_actions()` doppelte unmittelbare Aktionen.
Das verhindert, dass dieselbe Place-Aktion mehrfach bewertet wird, nur weil sie
über verschiedene vollständige Routen erreichbar ist.

### Nacharbeit und Defektaktionen

Ein Defekt ist technisch nacharbeitbar, wenn gilt:

```text
0.001 ≤ defect_severity < 0.6
```

Dann werden – soweit Kapazität und Maschinenzustand es erlauben – Nacharbeit
auf der Defektmaschine, Nacharbeit auf einer alternativen Maschine,
Herabstufung und Warten angeboten. Bei der alternativen Route wird die
Defektmaschine ausdrücklich ausgeschlossen.

Ist der Defekt nicht technisch reparierbar, wird keine Nacharbeit angeboten;
der Job erhält eine Ausschussaktion. Bei einer laufenden Recovery wartet der
Job, bis er wieder transportiert werden kann.

## 18. ActionSelector und GeneratorSelectorPolicy

### BaselineActionSelector

`select_action(actions, evaluator, observation, target_id)` führt folgende
Schritte aus:

```text
für jede Aktion Payload vorbereiten
→ Score mit dem Evaluator berechnen
→ maximalen Score bestimmen
→ alle exakt besten Aktionen sammeln
→ gelegentlich eine fast gleich gute produktive Aktion explorieren
→ bei mehreren Gleichständen seeded zufällig auswählen
→ PolicyDecision mit der gewählten Aktion zurückgeben
```

Die Toleranz für fast gleiche Aktionen beträgt `0.05`. Die
Explorationswahrscheinlichkeit beträgt `0.10`. Warteaktionen werden bei der
Exploration verworfen, wenn eine produktive Alternative verfügbar ist. Da der
Runner den Zufallsseed vor dem Lauf setzt, ist auch die Auswahl
reproduzierbar.

### GeneratorSelectorPolicy

`GeneratorSelectorPolicy` verbindet standardmäßig:

```text
SpineActionGenerator
LocalHeuristicActionEvaluator
BaselineActionSelector
```

`make_decision(snapshot)` läuft über alle Objekte, deren Zustand
`is_waiting_for_action=True` ist. Für jedes Objekt wird eine eigene
`PolicyObservation` erstellt, Aktionen werden erzeugt und eine Aktion wird
ausgewählt. Anschließend werden die ausgewählten Aktionen gemeinsam geprüft.

Ein Job darf in einer Runde nur einmal durch eine Pick-Aktion reserviert
werden. Dadurch können Main-Roboter und Corridor-Arm nicht beide denselben
Job aus demselben Snapshot auswählen.

`select_single_action()` erzeugt die Kandidaten für genau ein Objekt und gibt
die vom `ActionSelector` getroffene Entscheidung zurück. Es gibt keine
nachträgliche Auswahl eines Ersatzkandidaten.

## 19. Lokale Heuristik: Gewichte und Scores

### HeuristicWeights

Ein `HeuristicWeights`-Objekt ist ein lokaler Gewichtssatz. Die Felder sind:

```text
complete_job
wait_action
queue_priority
pick_source_storage_time
pick_short_transport_time
machine_pick_processing_time
machine_pick_tool_match
machine_pick_tool_life
target_store_capacity
place_target_storage_time
place_short_transport_time
place_machine_queue
place_shortest_processing_time
release_edd
rework_defect_machine_deadline_penalty_weight
rework_alternative_machine_deadline_penalty_weight
downgrade_product
wait_defect_job
job_scrap
rework_not_allowed_downgrade_bonus_weight
deadline_pressure_scrap_bonus_weight
deadline_missed_wait_penalty
rework_defect_machine_deadline_penalty_weight
rework_alternative_machine_deadline_penalty_weight
defect_edd
defect_repair_quality
```

Die Gewichte beschreiben lokale Entscheidungen innerhalb eines
Simulationsschritts. Sie sind nicht identisch mit den globalen Kosten-
Gewichten.

Die im Launcher verwendeten Ausgangswerte sind:


| Gewicht                                       | Ausgangswert | Bedeutung                                   |
| ----------------------------------------------- | -------------: | --------------------------------------------- |
| `complete_job`                                |         1.00 | fertigen Job sofort abschließen            |
| `wait_action`                                 |         0.00 | normale Warteaktion                         |
| `queue_priority`                              |         0.40 | EDD-/Warteschlangenpriorität               |
| `pick_source_storage_time`                    |         0.10 | kurze Auslagerungszeit                      |
| `pick_short_transport_time`                   |         0.30 | kurzer Weg zur Quelle                       |
| `machine_pick_processing_time`                |         0.15 | kurze nächste Bearbeitung                  |
| `machine_pick_tool_match`                     |         0.15 | bereits montiertes Werkzeug                 |
| `machine_pick_tool_life`                      |         0.10 | ausreichende Restlebensdauer                |
| `target_store_capacity`                       |         0.20 | freier Zielpuffer                           |
| `place_target_storage_time`                   |         0.15 | kurze Einlagerungszeit                      |
| `place_short_transport_time`                  |         0.25 | kurzer Weg zum Ziel                         |
| `place_machine_queue`                         |         0.25 | kurze Maschinenwarteschlange                |
| `place_shortest_processing_time`              |         0.15 | kurze Zieloperation                         |
| `release_edd`                                 |         0.70 | Termin-Dringlichkeit bei Freigabe           |
| `rework_defect_machine_deadline_penalty_weight`                   |         1.00 | Nacharbeit auf Ursprungsmaschine            |
| `rework_alternative_machine_deadline_penalty_weight`             |         0.80 | Nacharbeit auf Alternativmaschine           |
| `downgrade_product`                         |         0.40 | Herabstufung eines Defektjobs               |
| `wait_defect_job`                             |         0.20 | Warten bei Defekt                           |
| `job_scrap`                               |         0.00 | Ausschussentscheidung                       |
| `rework_not_allowed_downgrade_bonus_weight`      |         0.40 | Bonus für Herabstufung ohne Nacharbeit     |
| `deadline_pressure_scrap_bonus_weight`           |         0.50 | Ausschussbonus bei Termin-Dringlichkeit     |
| `deadline_missed_wait_penalty`                |         0.20 | Warteabzug bei verpasster Deadline          |
| `rework_defect_machine_deadline_penalty_weight`       |         0.00 | Nacharbeit auf Defektmaschine nicht erlaubt |
| `rework_alternative_machine_deadline_penalty_weight` |         0.00 | Nacharbeit alternativ nicht erlaubt         |
| `defect_edd`                                  |         0.20 | EDD-Anteil in Defektentscheidungen          |
| `defect_repair_quality`                       |         0.10 | erwartete Reparaturqualität                |

Alle Ausgangswerte liegen zwischen `0.0` und `1.0`. Der Optimierer verändert
diese Werte, begrenzt sie weiterhin auf diesen Bereich und übergibt jeden
vollständigen Satz unverändert an den lokalen Evaluator.

### Vorbereitung eines Aktionskandidaten

`prepare_action_candidate(action, observation)` kopiert Aktion und Payload.
Danach ergänzt die Methode:

```text
Pick-Aktion       → queue_priority aus EDD
Robot-Aktion      → keine Geschwindigkeit; SimRobot verwendet seinen eigenen Wert
Maschinenprozess  → processing_speed_factor
```

Die Aktion wird vorbereitet zurückgegeben; das ursprüngliche Dictionary wird
nicht verändert.

### EDD- und Queue-Priorität

`calculate_edd_priority(latest_end_time, current_time)` gibt eine Dringlichkeit
zwischen `0` und `1` zurück. Bei einer zukünftigen Deadline wird verwendet:

```text
0,5 / (1 + verbleibende Zeit)
```

Bei einer bereits überschrittenen Deadline wird verwendet:

```text
0,5 + 0,5 × überfällige Zeit / (1 + überfällige Zeit)
```

`evaluate_queue_priority()` multipliziert diese Priorität mit
`weights.queue_priority`.

### Pick-Score

Ein Roboter-Pick besteht aus:

```text
Queue-Priorität
+ Score für kurze storage_out_time
+ Score für kurze Transportzeit
```

Die Zeit-Scores haben die Form:

```text
1 / (1 + Zeit) × passendes Gewicht
```

Ein Maschinen-Pick verwendet zusätzlich Shortest-Processing-Time,
Werkzeugübereinstimmung und verbleibende Werkzeuglebensdauer.

### Place-Score

Ein Place-Score enthält:

```text
freier Anteil des Ziel-Stores
+ kurze storage_in_time
+ kurze Transportzeit
+ kurze Maschinenwarteschlange
+ kurze nächste Operation
```

Der freie Kapazitätsanteil ist:

```text
available_capacity / capacity
```

Die Queue- und Operationsscores werden mit `1/(1+x)` absteigend normiert.

### Freigabe-Score

Die Freigabe eines Jobs wird ausschließlich aus der EDD-Dringlichkeit
berechnet:

```text
EDD-Score × release_edd
```

### Defekt-Score

Der Defektschweregrad wird als erwartete
Nacharbeits-Fehlschlagswahrscheinlichkeit verwendet. Die Nacharbeitskosten
enthalten gleich gewichtet:

```text
normierte Operationsdauer, Produktdaten und Volumen
normierter Werkzeugverbrauch
Defektschweregrad
```

Nacharbeit wird zeitlich nur zugelassen, wenn noch Zeit bis zur Deadline
verbleibt. Herabstufung, Ausschuss und Warten erhalten eigene Grundscores,
Deadline-Boni und Deadline-Abzüge.

Eine `process_machine_job`-Aktion erhält keinen zusätzlichen lokalen Score.
Der Generator lässt sie nur zu, wenn Operation, Werkzeug, Maschine und
Ausgangspuffer technisch zulässig sind; die Auswahl fand bereits beim
Maschinen-Pick statt.

## 20. Qualität und reproduzierbarer Zufall im Detail

### Zwei getrennte Zufallswerte

Nach der Bearbeitungszeit erzeugt die Maschine einen eigenen Zufalls-
Generator. Der konkrete Code sieht so aus:

```python
defect_severity = None

quality_key = (
    f"{self.QUALITY_SEED}|{job.scenario.name}|{job.order.name}|"
    f"{job.number}|{operation.name}|{job.rework_count}"
).encode("utf-8")

quality_rng = random.Random(
    int.from_bytes(
        hashlib.sha256(quality_key).digest()[:8],
        "big",
    )
)
```

Die einzelnen Zeilen bedeuten:

```text
defect_severity = None
    Am Anfang ist noch kein Defekt festgestellt.

quality_key = ...
    Aus Seed, Szenario, Auftrag, Jobnummer, Operation und
    Nacharbeitszähler wird ein eindeutiger Textschlüssel gebaut.

.encode("utf-8")
    Der Text wird in Bytes umgewandelt, weil SHA-256 Bytes erwartet.

hashlib.sha256(...)
    Erstellt aus diesem Schlüssel einen festen Hashwert.

int.from_bytes(..., "big")
    Wandelt die ersten acht Hash-Bytes in eine ganze Zahl um.

random.Random(...)
    Erstellt damit einen eigenen Zufallsgenerator nur für diese
    Qualitätsprüfung.
```

Der Vorteil des eigenen Schlüssels ist die Reproduzierbarkeit: Derselbe Seed,
derselbe Job, dieselbe Operation und derselbe Nacharbeitsversuch erzeugen
wieder denselben Zufallsablauf. Der Qualitätszufall verändert dabei nicht den
allgemeinen Zufallsstrom der restlichen Simulation. Der
`rework_count` sorgt dafür, dass der erste Versuch (`0`) und spätere
Nacharbeitsversuche (`1`, `2`, ...) unterschiedliche, aber weiterhin
reproduzierbare Prüfungen erhalten.

Danach wird entschieden, ob überhaupt ein Defekt entsteht und wie schwer er
ist:

```python
if quality_rng.random() < operation.defect_probability:
    defect_severity = quality_rng.random()
```

Dabei passiert Folgendes:

1. Der erste Aufruf von `quality_rng.random()` liefert eine Zahl zwischen `0`
   (einschließlich) und `1` (ausschließlich). Ist sie kleiner als
   `operation.defect_probability`, entsteht ein Defekt.
2. Nur wenn ein Defekt entstanden ist, liefert der zweite Aufruf eine weitere
   Zahl zwischen `0` und `1`. Diese Zahl wird als `defect_severity`
   gespeichert: nahe `0` bedeutet leicht, nahe `1` bedeutet schwer.
3. Ist die erste Zahl nicht kleiner als die Wahrscheinlichkeit, bleibt
   `defect_severity` `None`; die Bearbeitung gilt dann als intakt.

Beispiel: Bei `defect_probability = 0.20` bedeutet ein erster Zufallswert von
`0.13` einen Defekt (13 % < 20 %). Der zweite Wert `0.74` ist dann der
Schweregrad. Ein erster Wert von `0.67` erzeugt dagegen keinen Defekt.

Ein Schweregrad unter `0.001` wird als kein relevanter Defekt behandelt. Bei
gleichem Schlüssel sind deshalb Defektentscheidung und Schweregrad gleich,
auch wenn sich die Transportreihenfolge der Simulation ändert.

### Bedeutung des Nacharbeitszählers

Der `rework_count` ist Teil des Schlüssels. Die erste Ausführung einer
Operation verwendet zum Beispiel den Schlüssel mit `rework_count=0`. Wird
dieselbe Operation nach einem Defekt erneut ausgeführt, verwendet sie
`rework_count=1`. Ein weiterer Versuch verwendet `2`.

Dadurch sind wiederholte Bearbeitungen derselben Job-Operation unterscheidbare
und dennoch reproduzierbare Zufallsereignisse. Der Zähler ändert nicht die
globale Vergleichbarkeit der Steuerungen: Beide Läufe erhalten für denselben
Job, Seed und Nacharbeitsversuch denselben Schlüssel.

### Qualitätszustände

```text
general_state
    intakt → normale Bearbeitung erfolgreich
    defect → Defekt wurde erkannt und benötigt eine Entscheidung
    ausschuss → Job wird als Ausschuss beendet

processing_state
    Name des aktuellen Produktzustands

defect_recovery_strategy
    Nacharbeit auf Defektmaschine
    Nacharbeit auf alternativer Maschine
    Herabstufung
    Ausschuss
```

Bei erfolgreicher Nacharbeit wird der Bearbeitungszustand wieder auf den
Zustand vor der defekten Operation gesetzt. Die historischen Felder
`defect_count`, `rework_count` und `defect_operation` bleiben trotzdem
erhalten.

### Qualitätsentscheidungen

```text
reparierbarer Defekt
→ Defektmaschine prüfen
→ alternative Maschinenroute prüfen
→ Herabstufung anbieten
→ Warten anbieten

nicht reparierbarer Defekt
→ Ausschussaktion anbieten
```

Die Defektmaschine wird bei der alternativen Nacharbeitsroute entfernt. Die
Nacharbeitsaktion wird gezählt, sobald die Policy sie auswählt. Ein Job kann
deshalb mehrere Versuche besitzen; die globale Nacharbeits-Jobquote zählt ihn
dennoch nur einmal.

## 21. Globale Kennzahlen: Eingabe, Berechnung und Ausgabe

### GlobalSimulationMetrics

Ein `SpineMLSimulationRunner` gibt pro Kombination aus Gewichtssatz und Seed
ein `GlobalSimulationMetrics`-Objekt zurück:

```python
@dataclass(frozen=True)
class GlobalSimulationMetrics:
    makespan: float
    total_tardiness: float
    total_transport_time: float = 0.0
    tool_change_time: float = 0.0
    blocking_time: float = 0.0
    rework_job_count: float = 0.0
    scrap_job_count: float = 0.0
    unfinished_jobs: int = 0
    total_jobs: int = 0
    completed_jobs: int = 0
    intact_jobs: int = 0
    defect_jobs: int = 0
    downgraded_job_count: float = 0.0
```

Die daraus abgeleiteten Raten lauten:

```text
completion_rate = completed_jobs / total_jobs
intact_rate     = intact_jobs / total_jobs
unfinished_rate = unfinished_jobs / total_jobs
rework_rate     = rework_job_count / total_jobs
scrap_rate      = scrap_job_count / total_jobs
defect_rate     = defect_jobs / total_jobs
downgrade_rate  = downgraded_job_count / total_jobs
```

Bei `total_jobs=0` werden die Raten als `0.0` zurückgegeben, damit keine
Division durch null entsteht.

### Zählregeln

```text
defect_jobs
    jeder Job mit defect_count > 0, auch wenn er später repariert wurde

intact_jobs
    nur abgeschlossene Jobs mit general_state == "intact"

unfinished_jobs
    Jobs ohne completed_time

rework_job_count
    jeder Job mit rework_count > 0 höchstens einmal

scrap_job_count
    Anzahl der Ausschussentscheidungen

downgraded_job_count
    jeder Job mit downgraded == True höchstens einmal
```

### Tardiness

Die Verspätung wird pro Auftrag, nicht pro einzelnem Job berechnet. Für jeden
Auftrag wird die späteste Abschlusszeit seiner Jobs gespeichert:

```text
tardiness_order = max(0, letzter Jobabschluss - latest_end_time)
```

Alle vollständig abgeschlossenen Aufträge werden zu `total_tardiness`
addiert. Ein Auftrag mit mindestens einem unfertigen Job erhält keine
künstliche Abschlusszeit. Er wird stattdessen über `unfinished_rate` bewertet.

Die Berechnung läuft intern in zwei Schritten:

```text
1. Für jeden Auftrag den spätesten Abschluss seiner Jobs bestimmen
2. Verspätung dieses Auftrags berechnen und zu total_tardiness addieren
```

Für einen Auftrag mit der Deadline `latest_end_time = 650` und zwei Jobs gilt
beispielsweise:

```text
Job 1 completed_time = 640
Job 2 completed_time = 670
spätester Abschluss   = 670

Tardiness dieses Auftrags = max(0, 670 - 650) = 20
```

Der erste Job ist zwar rechtzeitig, aber der Auftrag ist erst vollständig
fertig, wenn auch sein letzter Job abgeschlossen ist. Deshalb wird nicht der
Durchschnitt und nicht die Summe der Jobabschlusszeiten verwendet, sondern
der größte Abschlusszeitpunkt des Auftrags.

Bei mehreren Aufträgen wird jeder Auftrag mit seiner eigenen Deadline
berechnet und anschließend addiert:

```text
Auftrag A: spätester Abschluss 670, Deadline 650 → 20
Auftrag B: spätester Abschluss 700, Deadline 720 →  0

total_tardiness = 20 + 0 = 20
```

Existiert bei einem Auftrag noch kein vollständiger Abschluss aller Jobs, wird
dieser Auftrag bei `total_tardiness` übersprungen. Die fehlenden Jobs werden
separat über `unfinished_jobs` beziehungsweise `unfinished_rate` bestraft.
`due_state` bleibt trotzdem eine Kennzahl jedes einzelnen Jobs;
`total_tardiness` ist die zusammengefasste globale Kennzahl der vollständig
abgeschlossenen Aufträge.

### Makespan

```text
production_start = früheste earliest_start_time aller Jobs
makespan = max(0, spätester Jobabschluss - production_start)
```

Wenn kein Job fertig ist, wird statt des spätesten Abschlusses die
Simulationsendzeit verwendet.

### Transport-, Werkzeug- und Blockierungszeit

```text
total_transport_time
    Summe der Roboterdauern in moving_x, moving_y und moving_z

tool_change_time
    Summe der Maschinendauern in mounting und unmounting

blocking_time
    Summe der Maschinendauern im Zustand blocked
```

### Globale Kosten

`GlobalSimulationEvaluation.evaluate(metrics)` gibt eine einzelne
Kosten-Zahl zurück. Kleine Kosten sind besser. Vor der Gewichtung werden fünf
Zeitwerte geteilt:

```text
makespan / scale_makespan
total_tardiness / scale_total_tardiness
total_transport_time / scale_total_transport_time
tool_change_time / scale_tool_change_time
blocking_time / scale_blocking_time
```

Die Qualitätsraten werden direkt verwendet:

```text
rework_rate
scrap_rate
defect_rate
1 - intact_rate
unfinished_rate
downgrade_rate
```

Anschließend werden alle Werte mit `GlobalSimulationWeights` multipliziert
und addiert:

```text
5 × makespan
+ 4 × total_tardiness
+ 1 × total_transport_time
+ 1 × tool_change_time
+ 1 × blocking_time
+ 3 × rework_rate
+ 4 × scrap_rate
+ 20 × unfinished_rate
+ 3 × defect_rate
+ 3 × non_intact_rate
+ 3 × downgrade_rate
```

Die tatsächlichen Zeitwerte in dieser Darstellung sind bereits durch ihre
Skalen geteilt.

### Dynamische Normalisierung

`calibrate_from_baseline(metrics_by_seed)` erhält mindestens ein
`GlobalSimulationMetrics`-Objekt. Für jeden Zeitwert wird der arithmetische
Mittelwert über alle Baseline-Seeds gebildet. Der Makespan dient als positive
Fallback-Skala:

```text
fallback_time_scale = max(mean_makespan, 1.0)
```

Ist ein anderer Zeitmittelwert positiv, wird dieser verwendet. Ist er null,
wird `fallback_time_scale` verwendet. Die Ausgabe ist ein Dictionary mit
genau fünf Einträgen:

```python
        self.normalization_scales = {
            "makespan": fallback_time_scale,
            "total_tardiness": time_scale("total_tardiness"),
            "total_transport_time": time_scale("total_transport_time"),
            "tool_change_time": time_scale("tool_change_time"),
            "blocking_time": time_scale("blocking_time"),
        }
        return dict(self.normalization_scales)
```

Die Skalen werden nur bei der Baseline berechnet und danach von allen
Kandidaten und vom optimierten Abschlusslauf gemeinsam verwendet.

## 22. Optimierungsdaten und Suchalgorithmus

### SpineMLSimulationRunner

```python
    def __call__(
        self,
        weights: HeuristicWeights,
        seed: int,
    ) -> GlobalSimulationMetrics:
        sim.yieldless(False)

        random.seed(seed)
        SimMachine.QUALITY_SEED = int(seed)
```

Die Eingabe ist ein lokaler `HeuristicWeights`-Satz und eine ganze Seed-Zahl.
Der Runner setzt `random.seed(seed)` und
`SimMachine.QUALITY_SEED=seed`, erzeugt Environment, Policy, Bridge, Layout
und Szenario und führt den Lauf aus. Die Ausgabe ist genau ein
`GlobalSimulationMetrics`-Objekt für diesen einen Seed.

Der Runner ist headless: Er verwendet keine 3D-Animation und gibt keinen
Browserzustand zurück. Die Kennzahlen werden erst nach dem Lauf aus den
Simulationsobjekten gesammelt.

### WeightEvaluation

Eine `WeightEvaluation` beschreibt genau einen lokalen Gewichtssatz, der mit
allen Seeds ausgeführt wurde:

```python
@dataclass(frozen=True)
class WeightEvaluation:
    weights: HeuristicWeights
    objective_values: tuple[float, ...]
    mean_global_cost: float
    metrics_by_seed: tuple[GlobalSimulationMetrics, ...] = ()
```

`objective_values` enthält eine Kosten-Zahl pro Seed. `mean_global_cost` ist
deren arithmetischer Mittelwert. `metrics_by_seed` enthält die nicht
aggregierten Rohkennzahlen für die Anzeige und Diagnose.

### WeightOptimizationResult

Das Gesamtergebnis lautet:

```python
@dataclass(frozen=True)
class WeightOptimizationResult:
    best_weights: HeuristicWeights
    best_mean_global_cost: float
    evaluations: tuple[WeightEvaluation, ...]
```

`best_weights` ist der beste lokale Satz. `best_mean_global_cost` ist dessen
mittlere globale Kosten-Zahl über alle Seeds. `evaluations` speichert die
Bewertungen, die bisher eine Verbesserung des besten Ergebnisses dargestellt
haben. Es ist deshalb nicht zwingend eine Liste aller getesteten Kandidaten.

### Nachbarschaftskandidaten

`neighboring_weights(current_weights, step_fraction)` erzeugt:

```text
aktueller Gewichtssatz
für jedes Gewicht ein Kandidat mit kleinerem Wert
für jedes Gewicht ein Kandidat mit größerem Wert
```

Jeder Wert wird auf den Bereich `[0.0, 1.0]` begrenzt. Bei 26 lokalen
Gewichtsfeldern entstehen 55 Nachbarschaftskandidaten: der aktuelle Satz plus
zwei Varianten pro Feld.

### Explorationskandidaten

`random_local_weight_candidates(candidate_count, rng)` erzeugt vollständig
neue Gewichtssätze. Jedes Feld erhält einen Zufallswert zwischen `0.0` und
`1.0`. Das Feld `wait_action` wird zusätzlich mit `0.1` multipliziert, damit
Warten nicht alle produktiven Aktionen dominiert. Die Exploration verwendet
einen eigenen, stabilen Zufallsgenerator.

### Bewertung über Seeds

`evaluate_local_weights_across_seeds(weights, seeds)` führt für jeden Seed
folgende Schritte aus:

```text
simulation_runner(weights, seed)
→ GlobalSimulationMetrics
→ global_evaluation.evaluate(metrics)
→ Kosten und Metrics für diesen Seed speichern
```

Am Ende wird der Mittelwert über die Seed-Kosten gebildet und als
`WeightEvaluation` zurückgegeben.

### Eine Optimierungsrunde

`select_best_local_weight_set_across_seeds(...)` erhält alle Kandidaten einer
Runde. Für jeden Kandidaten wird der Callback zuerst mit `evaluation=None`
aufgerufen. Danach werden beide Seeds simuliert und der Callback mit der
vollständigen `WeightEvaluation` aufgerufen. Innerhalb der Runde gewinnt der
Kandidat mit dem kleinsten `mean_global_cost`.

Bei den aktuellen Parametern gilt:

```text
Seeds                         [1, 2]
Optimierungsrunden            2
anfängliche Schrittweite     0.40
Explorationskandidaten        3
Nachbarn pro Runde            55
Kandidaten pro Runde          58
Neustart nach                 2 erfolglosen Runden
Ende nach                     4 erfolglosen Runden
```

### Iterativer Suchablauf

`optimize_iteratively(...)` arbeitet so:

```text
Startgewichtssatz übernehmen
→ Nachbarn und Exploration erzeugen
→ alle Kandidaten über alle Seeds bewerten
→ besten Kandidaten der Runde wählen
→ wenn besser: als globalen Besten speichern
   und Schrittweite halbieren
→ wenn nicht besser: erfolglose Runde zählen
→ nach zwei erfolglosen Runden zum besten Satz zurückkehren
   und Schrittweite zurücksetzen
→ nach vier erfolglosen Runden abbrechen
→ WeightOptimizationResult zurückgeben
```

Eine Optimierungsrunde bedeutet somit nicht eine einzige Simulation. Eine
Runde enthält viele Kandidaten, und jeder Kandidat wird mit jedem Seed
simuliert.

## 23. Allgemeiner Optimierungsstarter: genaue Aufrufreihenfolge

### Zwei Prozesse

Beim Start aus dem Terminal oder über den Play-Button entstehen zwei
unterschiedliche Python-Prozesse:

```text
Prozess 1: normale Python-Datei
    → ruft main() auf
    → startet den Streamlit-Befehl mit subprocess.run(...)
    → wartet auf Prozess 2

Prozess 2: Streamlit-Python-Prozess
    → lädt die Optimierungsdatei erneut
    → erkennt die laufende Streamlit-Umgebung
    → baut das Webinterface
    → führt Optimierung und Simulation aus
```

Es sind keine zwei Threads. Jeder Prozess besitzt seine eigene Prozess-ID.
Der Browser ist nur die Anzeige und führt keinen Python-Code aus. Er verbindet
sich mit dem lokalen Streamlit-Webserver.

### `main()`

`main()` erhält keine Argumente und gibt normalerweise `None` zurück. Sie
kopiert die Umgebungsvariablen, setzt einen Startmarker und startet sinngemäß:

```text
python -m streamlit run optimization.py
```

`subprocess.run(...)` wartet, bis der gestartete Streamlit-Prozess beendet
wird. Die ursprüngliche Datei wird danach mit `raise SystemExit` beendet,
damit sie nicht versehentlich noch einmal die Oberfläche aufbaut.

Die Startbedingung prüft zwei Fälle:

```text
st.runtime.exists() == False
    → Datei wurde außerhalb von Streamlit gestartet

SPINEML_STREAMLIT_STARTED != "1"
    → noch kein Streamlit-Kindprozess gestartet
```

Im Streamlit-Kindprozess ist `st.runtime.exists()` wahr. Deshalb startet dieser
Prozess keinen dritten Server.

### Auswahl und Laden des Examples

Die zentrale Modelldatei wird aus der Dateivariable beziehungsweise aus
`SPINEML_MODEL_FILE` gelesen. `_resolve_model_path(model_file)` nimmt Text
oder ein `Path`-Objekt und gibt einen absoluten `.py`-Pfad zurück.

Im aktuellen Launcher ist die Standardauswahl konkret:

```python
EXAMPLE_FILE = "example-2.py"
```

Diese eine Variable kann auf `example-0.py`, `example-3.py`,
`example-3b-quality.py` oder ein anderes kompatibles Example geändert werden.
Der Play-Button benötigt kein Dateinamen-Argument; er verwendet diese Variable
oder den gesetzten Wert von `SPINEML_MODEL_FILE`.

Akzeptiert werden zum Beispiel:

```text
example3
example-3
example_3.py
```

Ohne absoluten Pfad wird im aktuellen Arbeitsordner und im `sources`-Ordner
gesucht. Fehlt die Datei, wird `FileNotFoundError` mit den geprüften Pfaden
ausgelöst.

`_load_model(model_path)` lädt die Datei mit `runpy.run_path(...)`. Die Ausgabe
ist ein Dictionary aller globalen Namen des Examples, also unter anderem
Layouts, Szenarien, Aufträge, Maschinen, Operationen und Funktionen.

Während des Ladens ersetzt `_suppress_model_visualization()` die Funktion
`SpineML.simulate` kurz durch eine leere Funktion. Damit wird nur die
Konfiguration definiert. Nach dem Laden wird die echte Funktion wiederhergestellt.

`_find_layout_and_scenario(model, model_path)` liest den Quelltext, sucht mit
dem Python-Syntaxbaum einen Aufruf von `simulate(...)` und liest dessen erste
beiden Argumentnamen. Diese Namen werden im Modelldictionary nachgeschlagen und als Tupel
`(layout, scenario)` zurückgegeben. Gibt es keinen passenden Aufruf, wird nur
bei genau einem Layout und genau einem Szenario automatisch ausgewählt; sonst
entsteht ein Fehler wegen nicht eindeutiger Auswahl.

### `create_optimizer`

`create_optimizer(model_file, model_stamp)` verbindet geladene Konfiguration,
Runner und globale Bewertung:

```text
Modelldatei auflösen
→ Modelldefinition laden
→ Layout und Szenario auswählen
→ SpineMLSimulationRunner erzeugen
→ globale GlobalSimulationEvaluation erzeugen
→ LocalHeuristicWeightOptimizer zurückgeben
```

`model_stamp` ist nur ein Cache-Schlüssel, zum Beispiel die Änderungszeit der
Datei. `@st.cache_resource` speichert das erzeugte Python-Objekt serverseitig,
damit es bei einem normalen Streamlit-Rerun nicht neu erzeugt werden muss.
Der Cache ist kein Browser-Dictionary und wird nicht automatisch im
Webinterface angezeigt.

### `_streamlit_app()`

Die Streamlit-Funktion wird im zweiten Prozess aufgerufen. Sie:

```text
Modelldatei bestimmen
→ Pfad auflösen
→ cached Optimizer holen
→ Titel und Example anzeigen
→ optimization_state in st.session_state anlegen, falls nicht vorhanden
→ Startbutton anzeigen
→ laufenden Zustand oder fertige Ergebnisse anzeigen
```

Der Sitzungszustand enthält:

```python
if "optimization_state" not in st.session_state:
    st.session_state.optimization_state = {
        "running": False,
        "iteration": 0,
        "candidate": 0,
        "total_candidates": 0,
        "costs": [],
        "metrics": [],
        "result": None,
        "benchmark": None,
        "normalization_scales": {},
        "phase": "",
        "error": None,
    }
```

Das Dictionary liegt im Python-Prozess auf dem Server. Der Browser sieht nur
die Werte, die Streamlit mit `write`, `info`, Diagrammen oder Tabellen ausgibt.

### Startbutton und `_start_optimization`

Der Button ist mit `disabled=state["running"]` und
`on_click=_start_optimization` verbunden. Beim Klick übergibt Streamlit den
aktuellen State und Optimizer an den Callback.

`_start_optimization(state, optimizer)` setzt zuerst den alten Lauf zurück:

```text
running=True
iteration=0
candidate=0
total_candidates=0
costs leeren
metrics leeren
result=None
benchmark=None
normalization_scales leeren
phase leeren
error=None
```

Danach werden `progress()` und `worker()` definiert und ein Thread gestartet:

```python
threading.Thread(target=worker, daemon=True).start()
```

`daemon=True` macht den Thread zu einem Hintergrundthread des Streamlit-
Prozesses. Er ist kein zweiter Prozess. Der Thread verhindert beim Beenden des
Streamlit-Prozesses nicht künstlich das Programmende.

### `worker()`

Der Worker erhält keine eigenen Argumente. Er verwendet die Variablen, die
`_start_optimization` in seinem äußeren Bereich bereitstellt. Die Reihenfolge
ist:

```text
1. Phase auf Baseline setzen
2. _run_benchmark(HeuristicWeights(), calibrate_normalization=True)
3. Baseline-Skalen im globalen Evaluator speichern
4. optimize_iteratively(...) ausführen
5. best_weights aus dem Result verwenden
6. _run_benchmark(best_weights, calibrate_normalization=False)
7. Baseline- und Optimiert-Zeilen in benchmark speichern
8. bei Fehler error setzen
9. in finally running=False setzen
```

Die Ausgaben werden in `state` geschrieben. Der Worker gibt selbst keinen
Wert zurück.

### `_run_benchmark`

```python
def _run_benchmark(state, optimizer, weights, calibrate_normalization=False):
    metrics_by_seed = []
```

Die Eingabe besteht aus dem Sitzungs-Dictionary, dem Optimizer, einem lokalen
Gewichtssatz und dem Schalter für die Baseline-Kalibrierung. Für `SEEDS=[1,2]`
passiert:

```text
Seed 1 mit weights simulieren
→ (1, metrics_seed_1) speichern

Seed 2 mit weights simulieren
→ (2, metrics_seed_2) speichern
```

Bei `calibrate_normalization=True` werden beide Metrics-Objekte an
`calibrate_from_baseline()` übergeben. Danach wird das zurückgegebene
Skalen-Dictionary in `state["normalization_scales"]` gespeichert.

Für jeden Seed wird eine eigene Tabellenzeile erstellt:

```python
        row = {
            "Seed": seed,
            "Makespan": metrics.makespan,
            "Tardiness": metrics.total_tardiness,
            "Transportzeit": metrics.total_transport_time,
            "Unfertige Jobs": metrics.unfinished_jobs,
            "Intaktquote (%)": metrics.intact_rate * 100.0,
            "Defektquote (%)": metrics.defect_rate * 100.0,
            "Ausschussquote (%)": metrics.scrap_rate * 100.0,
            "Nacharbeitsquote (%)": metrics.rework_rate * 100.0,
            "Herabstufungsquote (%)": metrics.downgrade_rate * 100.0,
            "Globale Kosten": optimizer.global_evaluation.evaluate(metrics),
        }
        rows.append(row)
```

Die Rückgabe enthält bei zwei Seeds zwei Tabellenzeilen. Beide Zeilen gehören
zu demselben übergebenen Gewichtssatz; der Seed ist nur die jeweilige
Zufallswelt. Die Prozentwerte werden nur für die Anzeige mit `100` multipliziert.
Die Kostenfunktion verwendet weiterhin Raten zwischen `0.0` und `1.0`.

### `progress`

Der Optimierer ruft `progress(iteration, evaluation, candidate, total_candidates)` vor und nach jedem Kandidaten auf.

```text
iteration
    Nummer der aktuellen Optimierungsrunde

candidate
    Nummer des gerade geprüften lokalen Gewichtssatzes

total_candidates
    Anzahl aller Gewichtssätze in dieser Runde

evaluation
    None vor der fertigen Simulation oder WeightEvaluation danach
```

Zuerst werden die drei Zähler in `state` geschrieben. Bei `evaluation=None`
endet die Methode dort. Bei einer fertigen Evaluation wird
`mean_global_cost` an `state["costs"]` angehängt. Aus den Metrics aller Seeds
wird zusätzlich eine Mittelwertzeile für `state["metrics"]` gebildet.

Beispiel für einen Kandidaten mit zwei Seeds:

```text
Seed 1 Kosten = 14.10
Seed 2 Kosten = 13.80
→ mean_global_cost = 13.95
```

Danach stehen die echten Werte in `state["costs"]` und `state["metrics"]`.
Die Methode erzeugt diese Einträge im Quellcode über `evaluation` und
`_mean_metric(...)`; es werden hier keine erfundenen Zahlen oder Platzhalter
als Python-Code gezeigt.

### Streamlit-Anzeigeplätze

Während `state["running"]` wahr ist, werden mit `st.empty()` leere
Anzeigeplätze erzeugt:

```text
status
iteration
candidate
progress_bar
cost_chart
metric_chart
delta_chart
latest
```

Diese Objekte sind Streamlit-Elemente, keine Attribute von
`optimization_state`. `status.info(...)` zeigt einen Infohinweis, `write(...)`
schreibt Text, `progress(...)` zeichnet den Balken und die Diagrammfunktionen
füllen ihre jeweiligen Platzhalter. Nach jeder Aktualisierung wartet die
Oberfläche `0.5` Sekunden und liest den State erneut.

Wenn die Berechnung fertig ist, wird `running=False`. Dann wird statt der
laufenden Platzhalter der Ergebnisbereich angezeigt: Erfolgsmeldung, Kosten-
und Kennzahlendiagramme, beste Gewichte, beste Kosten, Normalisierungsskalen
und Benchmark.

### Diagrammfunktionen

```text
globale_kosten_pro_kandidat(costs, container)
    aus Kostenliste ein DataFrame bilden und mittlere Kosten je Kandidat
    als interaktives Altair-Liniendiagramm zeichnen

mittlere_kennzahlen_pro_kandidat(metrics, container)
    Kennzahlenzeilen in langes Format umformen und je Kennzahl eine Kurve
    über alle Kandidaten zeichnen

kennzahlenabweichung_gegen_kandidat_1(metrics, container)
    pro Kennzahl (Kandidat - Kandidat 1) / |Kandidat 1| × 100 berechnen
    und als Abweichungskurve anzeigen; bei Basiswert 0 wird 0 verwendet

vergleich_baseline_optimiert(benchmark)
    Baseline- und Optimiert-Zeilen zusammenführen, Mittelwerte je Steuerung
    bilden, Tabelle anzeigen und je Kennzahl ein Seed-Diagramm zeichnen
```

Alle vier Funktionen zeichnen in Streamlit und geben keinen Datenwert zurück.
Das ursprüngliche Eingabe-Dictionary beziehungsweise die Eingabelisten werden
nicht als Ergebnis ersetzt.

## 24. Examples und ihre konkreten Inhalte

### Example 0

Example 0 enthält drei mögliche Produktionswege:

```text
Rohes Werkstück → direkte Polierfolge
Rohes Werkstück → Schleifen → Polierfolge
Rohes Werkstück → Fräsen → Schleifen → Polierfolge
```

Die Polierfolge besteht aus mehreren Stufen mit unterschiedlichen Werkzeugen.
Mehrere Maschinen desselben Typs erzeugen alternative Maschinenfolgen. Eine
Maschine kann dabei eine eigene Werkzeugliste besitzen.

### Example 1

Example 1 enthält zwei Szenarien, drei Layouts und mehrere Korridore. Die
Maschinen werden mit getrennten Eingang- und Ausgangskapazitäten erzeugt. Die
Konfiguration eignet sich dadurch für Tests von unterschiedlichen Layouts und
Auftragsmengen.

### Example 2

Example 2 enthält vier Maschinentypen, drei Szenarien, drei Layouts und mehrere
alternative Operationen. Auch hier besitzen die konkreten Maschinen eigene
Eingangs- und Ausgangspuffer.

### Example 3

Example 3 beschreibt eine Gehäusefertigung:

```text
3 Maschinentypen
3 Werkzeugtypen
6 Produkttypen
5 Operationen
1 Schichtszenario
4 Aufträge mit jeweils 2 Jobs
2 Korridore
8 Maschinen
```

Die Aufträge bilden Fräsen, Bohren, Polieren und die Bearbeitung eines
Grundkörpers ab. Jede konkrete Maschine erhält die Kapazitäten ihrer Eingangs-
und Ausgangspuffer.

### Example 3B

`example-3b-quality.py` lädt die Fabrikkonfiguration von Example 3 und ergänzt
für die Produktumwandlungen alternative Qualitätsoperationen:

```text
schnelle Operation
    kürzere Dauer, höhere Defektwahrscheinlichkeit

Quality-Operation
    längere Dauer, niedrigere Defektwahrscheinlichkeit
```

Die Qualitätsvariante verwendet weiterhin dieselben acht Jobs. Dadurch kann
die Policy zwischen Produktionszeit und Qualitätsrisiko entscheiden.

### Example 4

Example 4 erzeugt die Fabrik parametrisch mit acht Korridoren. Jeder Korridor
erhält vier Maschinen auf der linken und vier Maschinen auf der rechten Seite.
Die Anzahl der Korridore und Maschinen wird über Konstanten gesteuert.

### Optimierungsstarter

Die kompatiblen Starter setzen die Modelldatei zentral und rufen danach den
allgemeinen Optimierungsablauf auf:

```text
examples/optimization/example-0-optimize.py          → Example 0
examples/optimization/example-3-optimize.py          → Example 3
examples/optimization/example-3b-quality-optimize.py → Example 3B
```

Der allgemeine Starter benötigt nicht für jedes Example eine eigene
Optimierungslogik. Er lädt das ausgewählte Modell, findet Layout und Szenario,
führt Baseline und heuristische Optimierung aus und zeigt die Ergebnisse.

## 25. Technische Schutzmaßnahmen und Laufzeitdaten

### Laufzeit-Animation

Die Salabim-Animation zeigt Layout, Stores, Maschinen, Werkzeugbalken und
Roboter. Die Balkenlänge eines Werkzeugs wird aus der verbleibenden
Lebensdauer interpoliert. Die Balkenfarbe zeigt unter anderem unmontierte,
montierende, demontierende und aktive Werkzeuge.

Wenn ein minimiertes oder geschlossenes 3D-Fenster eine Höhe von `0` meldet,
überspringt der OpenGL-Schutz die Zeichenoperation. Dadurch wird der
headless- oder Abschlusslauf nicht durch einen Fensterfehler beendet.

### Statistik-Plots

Für Szenario, Auftrag und Maschine werden Zustandsdauern in Matplotlib-
Diagrammen gesammelt. Dazu gehören unter anderem Warte-, Montage-,
Demontage-, Arbeits- und Rückgabezustände. Die Laufzeitkennzahlen des
headless Runners werden unabhängig davon aus denselben Salabim-Zuständen
berechnet.

## 26. Projektunterstützung und aufgeräumte Bestandteile

Die Paketbeschreibung ermöglicht die Installation des Projekts als Python-
Paket. Die Abhängigkeiten decken Simulation, Salabim, 3D-Animation,
Visualisierung, Streamlit und optionale Testausführung ab.

Nicht mehr im produktiven Ablauf verwendet wird:

```text
separate calculate.py-Routenberechnung
zusätzliche Produktzustandszyklus-Prüfung
```

Die Dateien `optimization_dashboard.py` und
`recursion_path_search_example.py` gehörten nicht zum lokalen `main`-Stand.

Die Routenberechnung liegt jetzt beim ActionGenerator. Die Entscheidungen
laufen über die Policy-/Bridge-Schnittstelle. Die Simulation selbst führt nur
noch die von der Policy gelieferten ausführbaren Aktionen aus.

## 27. Kompakte Gesamthierarchie

```text
Example-Datei
├── ProductType, ToolType, MachineType, OperationType
├── Scenario und Order
├── Layout, Corridor und Machine
└── simulate(layout, scenario)

simulate / SpineMLSimulationRunner
├── Environment
├── SimulationBridge
├── SimLayout
│   ├── SimRobotMain
│   ├── SimCorridor
│   │   ├── SimRobotCorridorArm
│   │   └── SimMachine
│   └── Stores
└── SimScenario
    ├── SimOrder
    │   └── SimOrderJob
    └── SimCompletionWatcher

SimulationBridge
├── Snapshot aus allen Laufzeitobjekten
├── PolicyObservation
├── GeneratorSelectorPolicy
│   ├── SpineActionGenerator
│   ├── LocalHeuristicActionEvaluator
│   └── BaselineActionSelector
├── PolicyDecision
└── SimulationAction je Zielobjekt

Optimierungsstarter
├── Baseline mit Ausgangsgewichten
├── Kalibrierung der Zeit-Skalen
├── Kandidaten über mehrere Seeds
├── best_weights und best_mean_global_cost
├── optimierter Abschlusslauf
└── Tabellen und Diagramme im Streamlit-Webinterface
```

Damit sind die fachlich implementierten Erweiterungen, ihre Eingaben,
internen Verarbeitungsschritte und Rückgaben an einer Stelle dokumentiert.

## 28. Vollständiges Methodenregister

Die folgenden Übersichten nennen die im Projekt vorhandenen wesentlichen
Methoden mit ihrer Eingabe, ihrer internen Aufgabe und ihrer Ausgabe. Eine
Methode mit der Ausgabe `None` verändert also entweder den Simulationszustand
oder zeichnet etwas, statt einen neuen Datenwert zurückzugeben.

### 28.1 Konfiguration


| Baustein                         | Eingabe                                                                                                        | Interne Verarbeitung                                                                                                                                   | Ausgabe             |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| `ProductType(...)`               | Name, Länge, Breite, Tiefe, Gewicht                                                                           | Speichert Produktdaten, registriert das Objekt global und bereitet Listen für verbrauchende/erzeugende Operationen und Aufträge vor.                 | Produktobjekt       |
| `ToolType(...)`                  | Name, Montagezeit, Demontagezeit, Lebensdauer                                                                  | Speichert Werkzeugdaten, registriert das Werkzeug global und sammelt zugehörige Operationen.                                                          | Werkzeugobjekt      |
| `MachineType(...)`               | Name                                                                                                           | Registriert den Maschinentyp und legt Maschinen-/Operationslisten an.                                                                                  | Maschinentyp        |
| `MachineType.computeToolTypes()` | keine                                                                                                          | Durchsucht die zugeordneten Operationen, entfernt doppelte Werkzeugtypen und erzeugt die automatisch passende Werkzeugliste.                           | Liste von`ToolType` |
| `OperationType(...)`             | Name, Dauer, Verbrauch, Defektwahrscheinlichkeit, Maschinen-/Werkzeugtyp sowie Eingangs-/Ausgangsprodukt       | Speichert die Produktumwandlung und registriert sie bei Maschinentyp, Werkzeug und beiden Produkttypen.                                                | Operationsobjekt    |
| `Scenario(...)`                  | Name                                                                                                           | Registriert ein Szenario und legt dessen Auftragsliste an.                                                                                             | Szenarioobjekt      |
| `Order(...)`                     | Name, Menge, frühester Start, spätestes Ende, Zielprodukt, Szenario                                          | Speichert Termin- und Produktdaten, hängt den Auftrag an das Szenario an und registriert ihn global.                                                  | Auftragsobjekt      |
| `Layout(...)`                    | Name, Auslagerungszeit, Einlagerungszeit, Lagerkapazität                                                      | Speichert Layout-Lagerdaten und legt eine leere Corridorliste an.                                                                                      | Layoutobjekt        |
| `Corridor(...)`                  | Name, Kapazität, Aus-/Einlagerungszeit, Layout                                                                | Speichert Corridor-Daten, hängt den Corridor ans Layout und führt getrennte Listen für linke und rechte Maschinen.                                  | Corridorobjekt      |
| `Machine(...)`                   | Name, Maschinentyp, Corridor, Seite, Eingangs-/Ausgangskapazität, optionale Werkzeuge, Geschwindigkeitsfaktor | Speichert Puffer und Maschinenparameter, ordnet die Maschine Typ, Corridor und Seite zu und verwendet bei fehlender Werkzeugliste`computeToolTypes()`. | Maschinenobjekt     |

Die globalen Listen (`PRODUCT_TYPES`, `TOOL_TYPES`, `MACHINE_TYPES`,
`OPERATION_TYPES`, `SCENARIOS`, `ORDERS`, `LAYOUTS`, `CORRIDORS`,
`MACHINES`) enthalten genau die während des Ladens erzeugten
Konfigurationsobjekte. Die Bridge liest diese Listen, baut daraus aber für die
Policy ein ID-basiertes Modell mit einfachen Dictionaries.

### 28.2 Simulationskern


| Methode                                                      | Eingabe                                                                                 | Verarbeitung                                                                                                                        | Ausgabe                                        |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `guard_zero_sized_salabim_3d_window()`                       | keine                                                                                   | Ersetzt Salabims Zeichenfunktion durch einen einmalig geschützten Wrapper, der bei Fensterhöhe`<= 0` nicht zeichnet.              | `None`; globale Zeichenfunktion ist geschützt |
| `simulate(...)`                                              | Layout, Szenario,`animate`, Endzeit, optionale Policy/Bridge, Animationsgeschwindigkeit | Erzeugt Environment und Laufzeitobjekte, startet Salabim, behandelt`SimulationStopped`, druckt Statistiken und erzeugt Plots.       | `None`                                         |
| `SimLayout(...)`                                             | Layout, Szenario, Bridge                                                                | Erzeugt Start-/End-Store, alle`SimCorridor` und den Main-Roboter.                                                                   | Laufzeit-Layoutobjekt                          |
| `SimLayout.robotCount()`                                     | keine                                                                                   | Zählt Main-Roboter plus alle vorhandenen Corridor-Arme.                                                                            | Ganzzahl                                       |
| `SimLayout.machineCount()`                                   | keine                                                                                   | Summiert Maschinen über alle Korridore.                                                                                            | Ganzzahl                                       |
| `SimLayout.simMachines()`                                    | keine                                                                                   | Flacht linke und rechte Laufzeitmaschinen aller Korridore in eine Liste ab.                                                         | Liste von`SimMachine`                          |
| `SimLayout.robotUtilization()` / `machineUtilization()`      | keine                                                                                   | Bildet die gewichtete Nutzung über Roboter beziehungsweise Maschinen; bei leerer Menge wird`1` zurückgegeben.                     | `float`                                        |
| `SimLayout.printStatistics()`                                | keine                                                                                   | Gibt Layout-Storefüllstände und untergeordnete Statistiken aus.                                                                   | `None`                                         |
| `SimLayout.plot()`                                           | keine                                                                                   | Zeichnet Main-Roboter-, Corridor- und Maschinennutzung mit Matplotlib.                                                              | `None`                                         |
| `SimLayout.plotFull(legend)`                                 | optionales Legendenflag                                                                 | Erzeugt ein Unterdiagramm für Main-Roboter sowie jeden Arm und jede Maschine.                                                      | `None`                                         |
| `SimCorridor(...)`                                           | Corridor und Bridge, Y-Position                                                         | Erzeugt`store_main`, `store_left`, `store_right`, registriert sie und baut linke/rechte `SimCorridorArm` auf.                       | Laufzeit-Corridorobjekt                        |
| `SimCorridor.robotCount()` / `machineCount()`                | keine                                                                                   | Summiert die Zähler beider Seiten.                                                                                                 | Ganzzahl                                       |
| `SimCorridor.robotUtilization()` / `machineUtilization()`    | keine                                                                                   | Bildet eine nach Objektzahl gewichtete Nutzung beider Seiten; ohne Objekte`1`.                                                      | `float`                                        |
| `SimCorridor.printStatistics()`                              | keine                                                                                   | Delegiert an beide Arme.                                                                                                            | `None`                                         |
| `SimCorridor.plot()`                                         | keine                                                                                   | Ist aktuell ein reservierter, leerer Plot-Hook.                                                                                     | `None`                                         |
| `SimCorridorArm(...)`                                        | Corridor, Maschinenliste, Richtung, drei Stores, Bridge, Position                       | Erzeugt pro Maschine ein`SimMachine` und bei mindestens einer Maschine einen Arm-Roboter.                                           | Laufzeit-Armobjekt                             |
| `SimCorridorArm.robotCount()` / `machineCount()`             | keine                                                                                   | Gibt einen Roboter zurück, wenn Maschinen vorhanden sind, und zählt die Maschinenliste.                                           | Ganzzahl                                       |
| `SimCorridorArm.robotUtilization()` / `machineUtilization()` | keine                                                                                   | Gibt Arm- beziehungsweise Mittelwertnutzung der Maschinen zurück; ohne Maschinen`1`.                                               | `float`                                        |
| `SimCorridorArm.printStatistics()`                           | keine                                                                                   | Delegiert an Arm-Roboter (falls vorhanden) und Maschinen.                                                                           | `None`                                         |
| `SimCorridorArm.plot()`                                      | keine                                                                                   | Ist aktuell ein reservierter, leerer Plot-Hook.                                                                                     | `None`                                         |
| `SimScenario(...)`                                           | Layout, Szenario, Start-Store, Bridge                                                   | Erzeugt für jeden Auftrag ein`SimOrder` und einen `SimCompletionWatcher`.                                                          | Laufzeit-Szenarioobjekt                        |
| `SimScenario.printStatistics()` / `plot(legend)`             | optionales Legendenflag bei Plot                                                        | Delegiert an Aufträge und erstellt Auftrag-Unterdiagramme.                                                                         | `None`                                         |
| `SimCompletionWatcher.process()`                             | keine direkten Argumente                                                                | Prüft jede Zeiteinheit, ob mindestens ein Job existiert und alle`process_finished` sind; dann wird `SimulationStopped` ausgelöst. | beendet den Lauf durch Salabim-Signal          |
| `SimOrder(...)`                                              | Layout, Szenario, Auftrag, Start-Store, Bridge                                          | Erzeugt genau`order.quantity` Jobs und speichert sie in `sim_jobs`.                                                                 | Laufzeit-Auftrag                               |
| `SimOrder.printStatistics()` / `plot(legend)`                | optionales Legendenflag bei Plot                                                        | Delegiert Jobstatistik bzw. summiert Zustandsdauern pro Auftrag und zeichnet Balken.                                                | `None`                                         |

### 28.3 Job- und Maschinenprozesse


| Methode                                                 | Eingabe                                                         | Verarbeitung                                                                                                                                                                      | Ausgabe                                  |
| --------------------------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `SimOrderJob.process()`                                 | keine direkten Argumente                                        | Fordert wiederholt eine Aktion an, übernimmt deren Payload, wartet auf Freigabezeiten, legt Jobs in Stores, zählt Recovery/Ausschuss und beendet erst bei`finish_process=True`. | laufender Salabim-Prozess                |
| `SimOrderJob.mark_finished()`                           | keine                                                           | Setzt`completed_time` auf `env.now()`. Der Job wird nicht passiviert und muss deshalb nicht aktiviert werden.                                                                     | `None`                                   |
| `SimOrderJob.mark_defective(...)`                       | Operation, Maschine, Zustände, Schweregrad                     | Erhöht`defect_count`, setzt `general_state="defect"` und speichert alle Defektinformationen.                                                                                     | `None`                                   |
| `SimOrderJob.printStatistics()`                         | keine                                                           | Formatiert Bearbeitungs-, Qualitäts-, Herabstufungs- und Terminstatus.                                                                                                           | `None`/Text für die Statistikdelegation |
| `SimMachine(...)`                                       | konfigurierte Maschine, Bridge, Position                        | Erzeugt Eingangs-/Ausgangs-Stores mit Kapazität, Werkzeuglebensdauern, Geschwindigkeits-/Startupvariation, Schutzwerkzeugstatus und Bridge-Registrierung.                        | Laufzeit-Maschine                        |
| `SimMachine.process()`                                  | keine direkten Argumente                                        | Meldet`blocked` bei vollem Ausgang, fordert Aktionen an und delegiert Pick, Prozess oder Warten.                                                                                  | laufender Salabim-Prozess                |
| `SimMachine.execute_pick_action(action)`                | ausführbare Pick-Action                                        | Entnimmt den von der Steuerung ausgewählten Job aus dem Eingangs-Store, speichert Priorität und setzt`current_job`.                                                             | laufender Generator                      |
| `SimMachine.execute_process_action(action)`             | Operation, Werkzeug, Lebensdauer, Setup- und Ziel-Store-Payload | Führt Setupzeiten aus, berechnet Dauer, arbeitet, erzeugt deterministisches Qualitätsereignis, aktualisiert Produkt-/Werkzeugzustand und legt den Job im Ausgangs-Store ab.     | laufender Generator                      |
| `SimMachine.create_tool_life_bar_length_function(tool)` | Werkzeug                                                        | Erstellt die zeitabhängige Interpolationsfunktion für die Balkenlänge.                                                                                                         | Callable für Salabim                    |
| `SimMachine.create_tool_life_bar_color_function(tool)`  | Werkzeug                                                        | Erstellt die Funktion für grau/grün/gelb/orange/rot abhängig von Werkzeug- und Maschinenzustand.                                                                               | Callable für Salabim                    |
| `SimMachine.utilization()`                              | keine                                                           | Berechnet Arbeitsanteil aus Warte-, Montage-, Demontage-, Arbeits- und Rückgabezeiten.                                                                                           | `float`                                  |
| `SimMachine.plot(legend)`                               | optionales Legendenflag                                         | Zeichnet Zustandsdauern als Balken.                                                                                                                                               | `None`                                   |
| `SimMachineShutdown.process()`                          | keine direkten Argumente                                        | Demontiert das Produktionswerkzeug, montiert das Schutzwerkzeug und setzt die Maschine zurück.                                                                                   | laufender Salabim-Prozess                |

Die Maschinenzustände `waiting`, `blocked`, `mounting`, `unmounting`,
`working` und `returning` werden über Salabim-Zustände geführt. Eine volle
Ausgangskapazität verhindert eine neue Bearbeitung, weil der Job sonst nicht
aus der Maschine ausgelagert werden könnte.

### 28.4 Roboterprozesse


| Methode                                                                                                    | Eingabe                                     | Verarbeitung                                                                                                                         | Ausgabe                                     |
| ------------------------------------------------------------------------------------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `SimRobot(...)`                                                                                            | Label, Einrückung, Startkoordinaten, Farbe | Speichert Position und Lade-/Bewegungszustände und zieht einen reproduzierbaren Geschwindigkeitsmultiplikator.                      | Basis-Roboter                               |
| `SimRobot.x_func/y_func/z_func(t)`                                                                         | Animationszeit                              | Interpoliert die Position vom letzten Start- zum Zielzeitpunkt; bei gleicher Zeit bleibt sie konstant.                               | Koordinate als`float`                       |
| `SimRobot.take_selected_job_from_store(action, store)`                                                     | Action mit`selected_job`, Ziel-Store        | Prüft, ob der ausgewählte Job noch vorhanden ist. Bei einer veralteten Action wird kein Ersatzjob ausgewählt und`None` geliefert. | laufender Generator, liefert Job oder`None` |
| `SimRobot.move_x/move_y/move_z(target, speed)`                                                             | Zielkoordinate, Geschwindigkeit             | Berechnet effektive Geschwindigkeit, setzt Bewegungszustand, hält die Fahrtdauer und setzt danach die Position fest.                | laufender Generator                         |
| `SimRobot.utilization()`                                                                                   | keine                                       | Teilt Bewegungsdauer durch Bewegungs- plus Wartezeit.                                                                                | `float`                                     |
| `SimRobot.plot(legend)`                                                                                    | optionales Legendenflag                     | Zeichnet Lade- und Bewegungszustandsdauern.                                                                                          | `None`                                      |
| `SimRobotMain.calculate_storage_y_position()`                                                              | keine                                       | Berechnet die Y-Position der Layout-Lager aus der Corridoranzahl.                                                                    | `float`                                     |
| `SimRobotMain.calculate_corridor_y_position(index)`                                                        | Corridorindex                               | Berechnet dessen Y-Position relativ zur Corridoranzahl.                                                                              | `float`                                     |
| `SimRobotMain.configured_corridor_index(corridor)`                                                         | Corridorobjekt oder Namensobjekt            | Sucht den Corridor im Layout über Namen, nicht nur über Objektidentität.                                                          | Ganzzahl                                    |
| `SimRobotMain.simulation_corridor_index(sim_corridor)`                                                     | Laufzeit-Corridor                           | Sucht den zugehörigen Laufzeitindex.                                                                                                | Ganzzahl                                    |
| `SimRobotMain.move_to_start_storage/move_to_corridor_storage/move_to_end_storage(...)`                     | Zielobjekt/-index, Geschwindigkeit          | Führt die nötigen X-/Y-/Z-Bewegungen aus.                                                                                          | laufender Generator                         |
| `SimRobotMain.move_down_to_storage(speed)` / `move_up_from_storage(speed)`                                 | Geschwindigkeit                             | Fährt zur festen Pick-/Place-Höhe`z=1.25` beziehungsweise zurück zur Transporthöhe `z=2.5`.                                      | laufender Generator                         |
| `SimRobotMain.execute_pick_action(action)`                                                                 | Main-Pick-Action                            | Fährt zum Start- oder Corridor-Store, wartet`storage_out_time`, nimmt einen Job und speichert ihn als `current_job`.                | laufender Generator                         |
| `SimRobotMain.execute_place_action(action)`                                                                | Main-Place-Action                           | Fährt zum Ziel-Corridor, zur anderen Seite oder ins Endlager, wartet`storage_in_time`, setzt Auswahlfelder und legt den Job ab.     | laufender Generator                         |
| `SimRobotMain.process()`                                                                                   | keine direkten Argumente                    | Wiederholt Bridge-Anforderung und delegiert Pick, Place oder Wait.                                                                   | laufender Salabim-Prozess                   |
| `SimRobotCorridorArm.compute_machine_x(index)`                                                             | Maschinenindex                              | Berechnet X-Position der Maschine auf der Armseite.                                                                                  | `float`                                     |
| `SimRobotCorridorArm.move_to_corridor_storage_x/move_to_machine_storage(...)`                              | optional Index, Geschwindigkeit             | Fährt horizontal zum Corridor- beziehungsweise Maschinenzugriff.                                                                    | laufender Generator                         |
| `SimRobotCorridorArm.move_down_to_corridor_storage/move_down_to_machine_storage/move_up_from_storage(...)` | Geschwindigkeit                             | Führt vertikale Armbewegungen aus.                                                                                                  | laufender Generator                         |
| `SimRobotCorridorArm.execute_pick_action(action)`                                                          | Arm-Pick-Action                             | Nimmt einen Job aus Corridor-Eingang oder Maschinen-Ausgang, wartet gegebenenfalls Auslagerungszeit und setzt`current_job`.          | laufender Generator                         |
| `SimRobotCorridorArm.execute_place_action(action)`                                                         | Arm-Place-Action                            | Legt in Maschinen-Eingang, anderen Arm oder zentralen Main-Store ab, wartet Einlagerungszeit und leert den Arm.                      | laufender Generator                         |
| `SimRobotCorridorArm.process()`                                                                            | keine direkten Argumente                    | Wiederholt Bridge-Anforderung und delegiert Pick, Place oder Wait.                                                                   | laufender Salabim-Prozess                   |

### 28.5 Beobachtung, Policy und Bridge

`SimulationObjectObserver` übersetzt Laufzeitobjekte in reine Python-Daten.
Die Methoden `observe_order_job`, `observe_main_robot`,
`observe_corridor_arm_robot`, `observe_machine` und `observe_store` liefern
jeweils Dictionaries. Sie enthalten keine Salabim-Objekte, sondern IDs,
Zahlen, Zustände und verschachtelte Job-/Store-Zusammenfassungen.

`observe_job_summary(job)` liefert für einen geladenen Job eine kleine
Zusammenfassung oder bei `None` ebenfalls `None`. `job_id(job)` erzeugt die
stabile Form `Auftragsname:Jobnummer`.

`ConfigurationObjectObserver.build_policy_configuration_model(...)` erhält
die globalen Konfigurationslisten und gibt das vollständige ID-Modell zurück.
Dabei werden zusätzlich `configuration_maxima` für Operationsdauer,
Werkzeugverbrauch, Produktgewicht und Produktvolumen gebildet.

Die Nachrichtenklassen haben folgende konkrete Rollen:

```text
PolicyObservation(snapshot, current_object_id)
    unveränderliche Sicht eines Policy-Aufrufs

PolicyTrigger(event_id, sender_id, state_version, time)
    Nachricht eines wartenden oder geänderten Laufzeitobjekts

SelectedObjectAction(target_id, action_type, payload)
    abstrakte, ID-basierte Policy-Auswahl

PolicyDecision(actions)
    Liste ausgewählter abstrakter Aktionen

SimulationAction(event_id, target, source_trigger, action_type, time, payload)
    ausführbare Aktion mit echten Laufzeitobjekten
```

`PolicyDecision.with_single_selected_action(action, target_id)` ist eine
Hilfsfabrik für genau eine Auswahl. `is_wait_action(action_type)` erkennt
Warteaktionen an ihrem Präfix `wait_`.


| Bridge-Methode                                              | Eingabe                                     | Ausgabe/Seiteneffekt                                                                                                            |
| ------------------------------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `SimulationBridge(...)`                                     | optionale Policy, Environment               | Erstellt Trigger-Store, Action-Stores, ID-Register, Zähler und Standard-Policy.                                                |
| `register(id, object, stores)`                              | Policy-ID, Laufzeitobjekt, optionale Stores | Registriert beide Objekt-Richtungen, persönlichen Action-Store und Store-IDs.                                                  |
| `register_corridor(id, corridor, stores)`                   | Corridor-ID, Laufzeit-Corridor, Stores      | Registriert Corridor für ID-Auflösung, aber keinen persönlichen Action-Store.                                                |
| `register_store(store)`                                     | Salabim-Store                               | Trägt den Store-Namen als Policy-ID ein; Duplikate werden ignoriert.                                                           |
| `can_register_policy_object(id, object)`                    | ID und Objekt                               | Gibt`False` bei bereits registrierter ID oder Objektidentität, sonst `True` zurück.                                           |
| `request_action(sender)`                                    | Simulationsobjekt                           | Markiert es als wartend und erzeugt über`notify_state_change` einen Trigger.                                                   |
| `notify_state_change(sender)`                               | Simulationsobjekt                           | Erhöht`state_version`, erzeugt eine monotone Trigger-ID und legt den Trigger ab.                                               |
| `build_policy_configuration_model()`                        | keine                                       | Baut einmalig das statische ID-Modell aus den globalen Listen.                                                                  |
| `build_policy_simulation_snapshot()`                        | keine                                       | Beobachtet alle registrierten Objekte und ergänzt Zeit, Zustandsversion und Warteflags.                                        |
| `create_policy_observation(triggers)`                       | optionale Triggerliste                      | Verpackt Snapshot und Trigger-IDs in`PolicyObservation`.                                                                        |
| `create_simulation_actions(decision, trigger_id)`           | PolicyDecision und Quelltrigger             | Löst alle Payload-IDs über`policy_payload_id_mappings` auf und erzeugt ausführbare Actions.                                  |
| `action(target)`                                            | Laufzeitobjekt                              | Liefert den nächsten Action-Eintrag aus dessen persönlichem Store.                                                            |
| `simulation_object_for_policy_object_id(id)`                | Policy-ID                                   | Gibt das registrierte echte Laufzeitobjekt zurück.                                                                             |
| `next_action_event_id()` / `next_policy_trigger_event_id()` | keine                                       | Erhöhen den jeweiligen Zähler und liefern stabile Ereignis-IDs.                                                               |
| `SimulationBridge.process()`                                | keine direkten Argumente                    | Sammelt zeitgleiche Trigger, erstellt Snapshot, ruft Policy auf, prüft Versionsgleichheit, löst IDs auf und verteilt Actions. |

`policy_payload_id_mappings(bridge)` ist die zentrale Übersetzungstabelle.
Sie wandelt unter anderem `target_store_id`, `selected_job_id`,
`sim_machine_id`, `sim_corridor_id`, `selected_operation_id`,
`selected_machine_id`, `downgrade_product_type_id`, `operation_id`,
`planned_machine_id` und `tool_type_id` in echte Objekte um.

Die rekursiven privaten Hilfsfunktionen
`collect_store_states`, `collect_machine_states` und
`collect_store_positions` durchsuchen verschachtelte Dictionaries und Listen
des Snapshots. Der interne Wrapper `draw_with_zero_size_guard` übernimmt
dagegen nur die Fensterhöhenprüfung vor Salabims Zeichenaufruf.

### 28.6 ActionGenerator

`SpineActionGenerator.generate_actions(observation)` ist der einzige
öffentliche Einstieg. Er ruft `_generate_actions()` auf, prüft den
Objekttyp, wählt die passende Aktionsgruppe und entfernt danach identische
unmittelbare Aktionen. Die wichtigsten Hilfsmethoden arbeiten so:

```text
current_state(observation)
    → Zustand des aktuellen Objekts aus states_by_id

states_of_type(snapshot, type)
    → alle Zustands-Dictionaries eines Objekttyps

model/product_type/operation/machine(...)
    → Zugriff auf ID-Daten des statischen Modells

store_has_items/store_has_free_capacity/store_jobs/job_id(...)
    → Store- und Job-Hilfswerte

create_pick_actions_for_store(...)
    → ein Pick-Dictionary pro Job im Store
```

Die Aktionsmethoden liefern immer eine Liste von Dictionaries mit
`action_type` und `payload`. Für Jobs sind das
`create_release_job_action`, `create_wait_actions_for_job`,
`create_completion_actions_for_job`, `create_defect_actions_for_job` und
`create_ausschuss_actions_for_job`. Für den Main-Roboter gibt es
`create_main_robot_pick_actions`, `create_main_robot_place_actions` und
`create_main_robot_wait_actions`. Für jeden Corridor-Arm gibt es
`create_corridor_arm_robot_pick_actions`,
`create_corridor_arm_robot_place_actions` und
`create_corridor_arm_robot_wait_actions`. Für Maschinen gibt es
`create_machine_pick_actions`, `create_machine_process_actions` und
`create_machine_wait_actions`.

Die Defekthilfen `defect_machine_observation`,
`machine_available_for_nacharbeit` und
`find_nacharbeit_routes_with_alternative_machine` prüfen die Defektmaschine,
ihren Zustand, ihre Puffer und alternative Routen. Sie verhindern, dass die
Defektmaschine als alternative Recovery-Maschine erneut verwendet wird.

Die Routenmethoden haben diese Ein-/Ausgaben:


| Methode                                                                          | Eingabe                            | Ausgabe                                                                          |
| ---------------------------------------------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------- |
| `calculate_operation_sequences_between(start, target, model)`                    | Produkt-IDs und Modell             | Alle vorwärts möglichen Operationslisten vom Start- zum Zielprodukt.           |
| `calculate_operation_sequences(target, model)`                                   | Zielprodukt-ID und Modell          | Alle rückwärts aufgebauten Operationslisten, die dieses Produkt erzeugen.      |
| `calculate_machine_sequences_from_operation_sequence(operations, layout, model)` | Operationsliste, Layout-ID, Modell | Alle Maschinenlisten mit passendem Typ, Layout und Werkzeug.                     |
| `calculate_machine_sequences(product, layout, model)`                            | Zielprodukt, Layout, Modell        | Deduplizierte Kombinationen aus Operations- und Maschinenfolgen.                 |
| `selectable_routes_for_job(job, layout, model)`                                  | Jobzustand und Modell              | Erlaubte normale oder gespeicherte Nacharbeitsrouten.                            |
| `find_nacharbeit_routes_with_alternative_machine(observation)`                   | Defekt-Observation                 | Recovery-Routen, deren erste Maschine nicht die Defektmaschine ist.              |
| `machine_available_for_nacharbeit(machine)`                                      | Maschinen-Observation              | `True`, wenn Maschine idle ist und beide Puffer Platz besitzen.                  |
| `nacharbeit_is_technically_possible(job)`                                        | Jobzustand                         | `True` für `0.001 <= Schweregrad < 0.6`.                                        |
| `job_cannot_use_normal_production_route(job)`                                    | Jobzustand                         | Sperrt normale Route für Defekt-/Ausschuss-/herabgestufte/unkonfigurierte Jobs. |

Bei einem geladenen Roboterjob wird zuerst geprüft, ob ein gespeichertes
`selected_operation_id`/`selected_machine_id` existiert. Dadurch wird eine
bereits getroffene Maschinenentscheidung nicht durch den nächsten Arm neu
gewürfelt. Erst wenn keine Auswahl vorhanden ist, werden alle Routen erneut
berechnet.

### 28.7 Evaluator, Selector und Policy

`LocalHeuristicActionEvaluator.__init__(weights)` speichert genau einen
`HeuristicWeights`-Satz. `prepare_action_candidate()` kopiert Action und
Payload und ergänzt Queue-Priorität, Bewegungsgeschwindigkeit oder
Bearbeitungsgeschwindigkeit. `evaluate_action()` delegiert abhängig vom
Aktionstyp an die passende Detailbewertung. Für Pick-Aktionen berechnen
`calculate_pick_edd_priority` und `read_queue_priority` die gültige
Jobpriorität; `selected_job_state` sucht dazu den ausgewählten Job.

Die Detailmethoden liefern jeweils einen `float`-Score:

```text
evaluate_release_action
    EDD-Dringlichkeit plus freie Startlager-Kapazität

evaluate_defect_action
    Nacharbeit, Alternativmaschine, Herabstufung, Ausschuss oder Warten

evaluate_pick_action
    verteilt an Robot-Pick oder Maschinen-Pick

evaluate_robot_pick_action
    Queue, storage_out_time und Transport

evaluate_machine_pick_action
    Queue, kurze Operation, Werkzeugmatch und Restlebensdauer

evaluate_place_action
    Zielkapazität, storage_in_time, Transport, Maschinenqueue und Dauer

evaluate_process_action
    0.0, weil die technische Zulassung bereits im Generator erfolgt
```

`find_store_state`, `find_machine_state`, `find_store_position` und
`selected_job_state` durchsuchen Snapshots rekursiv und lösen die Daten auf.
`calculate_edd_priority` liefert die normierte Dringlichkeit. Die Methoden
`evaluate_queue_priority`, `evaluate_pick_source_storage_time`,
`evaluate_place_target_storage_time`, `evaluate_target_store_capacity`,
`evaluate_place_machine_queue`, `evaluate_place_processing_time`,
`evaluate_transport_time` und der kompatible Alias
`evaluate_short_transport_time` berechnen die einzelnen Zeit-, Kapazitäts-
und Prioritätsteile und multiplizieren sie mit den lokalen Gewichten.
`estimate_nacharbeit_time`, `estimate_nacharbeit_cost`,
`estimate_nacharbeit_failure_probability` und
`estimate_remaining_time` liefern die Defekt-Schätzwerte.
`is_nacharbeit_allowed` prüft ausschließlich, ob noch Zeit bis zur Deadline
verbleibt; `evaluate_defect_action` verwendet danach Grundscores,
Dringlichkeitsbonus und Reparaturqualität.

Im aktiven Ablauf wird ausschließlich der gewichtete
`LocalHeuristicActionEvaluator` verwendet. Er bereitet die Kandidaten vor,
bewertet sie anhand von `HeuristicWeights` und liefert für jeden Kandidaten
einen numerischen Score.

`BaselineActionSelector.select_action(...)` erhält Kandidaten, Evaluator,
Observation und Ziel-ID. Es bereitet alle Kandidaten vor, berechnet den
höchsten Score, sammelt exakte Gleichstände, prüft die Toleranz `0.05`,
exploriert mit Wahrscheinlichkeit `0.10` eine produktive nahezu gleich gute
Alternative und wählt sonst seeded zufällig aus den besten Kandidaten.
Ausgabe ist eine `PolicyDecision`.

`GeneratorSelectorPolicy.make_decision(observation)` verarbeitet alle
wartenden Objekte des gemeinsamen Snapshots und führt danach eine globale
Pick-Reservierung durch. Ein Job darf in derselben Entscheidung höchstens
einmal gepickt werden. `select_single_action(observation)` erzeugt die
Kandidaten für genau ein Objekt und übernimmt die Auswahl des
`ActionSelector` ohne eine nachträgliche Ersatzentscheidung.

### 28.8 Globale Bewertung und Optimierer

`GlobalSimulationMetrics` ist ein unveränderlicher Datensatz pro Seed. Die
Properties `completion_rate`, `intact_rate`, `unfinished_rate`, `rework_rate`,
`scrap_rate` und `defect_rate` teilen die jeweiligen Zähler durch
`total_jobs`, beziehungsweise liefern bei null Jobs `0.0`.

`GlobalSimulationEvaluation.calibrate_from_baseline(metrics)` nimmt eine
beliebige Iterable von Baseline-Metrics, bildet je Zeitkennzahl den Mittelwert
und speichert fünf Normalisierungsskalen. `normalized_metrics(metrics)` gibt
ein Dictionary mit fünf skalierten Zeitwerten und sechs direkt verwendeten
Qualitätsraten zurück. `evaluate(metrics)` multipliziert diese elf Werte mit
`GlobalSimulationWeights` und gibt eine einzelne Kosten-Zahl zurück.

Intern summiert die Hilfsfunktion `mean_value(attribute_name)` das gewünschte
Attribut für alle Baseline-Metrics und teilt durch deren Anzahl. Die zweite
Hilfsfunktion `time_scale(attribute_name)` verwendet diesen Mittelwert, wenn
er positiv ist; bei null wird die positive Makespan-Fallback-Skala verwendet.

`SpineMLSimulationRunner.__call__(weights, seed)` ist der vollständige
Headless-Lauf: Seed setzen, Environment erzeugen, Evaluator/Policy/Bridge
aufbauen, Layout und Szenario starten, `SimulationStopped` abfangen und
`collect_global_metrics(...)` aufrufen. Die Ausgabe ist genau ein
`GlobalSimulationMetrics`.

`collect_global_metrics(...)` sammelt Jobs, Abschlusszeiten, Defekt-,
Nacharbeits-, Ausschuss- und Herabstufungszähler, berechnet Auftrags-Tardiness,
Makespan, Transport-, Werkzeugwechsel- und Blockierungszeit und erzeugt daraus
den Metrics-Datensatz.

`LocalHeuristicWeightOptimizer` stellt vier Schritte bereit:

```text
neighboring_weights(weights, step)
    → aktueller Satz plus kleiner/größer je Feld, Werte auf [0, 1] begrenzt

random_local_weight_candidates(count, rng)
    → vollständig neue Sätze; wait_action wird mit 0.1 gedämpft

evaluate_local_weights_across_seeds(weights, seeds)
    → pro Seed Runner + globale Kosten; Ausgabe WeightEvaluation

select_best_local_weight_set_across_seeds(candidates, seeds, ...)
    → alle Kandidaten bewerten, Callback auslösen, besten Kandidaten wählen

optimize_iteratively(...)
    → mehrere Runden mit Schrittweitenhalbierung, Restart und Abbruch
```

### 28.9 Launcher- und Anzeige-Funktionen


| Funktion                                                             | Eingabe                                              | Ausgabe/Verhalten                                                                                                    |
| ---------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `_resolve_model_path(model_file)`                                    | Dateiname, Alias oder`Path`                          | Absoluter vorhandener Python-Pfad oder`FileNotFoundError`.                                                           |
| `_find_layout_and_scenario(model, model_path)`                       | Modelldictionary und Quelldatei                      | Tupel`(layout, scenario)` aus AST-`simulate(...)`-Aufruf oder eindeutiger Fallback.                                  |
| `_suppress_model_visualization()`                                    | keine                                                | Contextmanager; unterdrückt während`runpy` temporär `simulate` und stellt sie danach wieder her.                 |
| `_load_model(model_path)`                                            | Pfad                                                 | Dictionary aller globalen Namen des Examples.                                                                        |
| `_global_evaluation()`                                               | keine                                                | Bewertungsobjekt mit den globalen Kosten-Gewichten.                                                                  |
| `create_optimizer(model_file, model_stamp)`                          | Modelldatei und Cache-Stempel                        | Gecachter`LocalHeuristicWeightOptimizer` für das ausgewählte Layout/Szenario.                                      |
| `_mean_metric(metrics, name)`                                        | Metrics-Iterable, Attributname                       | Arithmetischer Mittelwert eines Kennzahlenattributs.                                                                 |
| `_run_benchmark(state, optimizer, weights, calibrate_normalization)` | State, Optimierer, Gewichtssatz, Baseline-Schalter   | Simuliert jeden Seed und gibt eine Tabellenzeile pro Seed zurück.                                                   |
| `_start_optimization(state, optimizer)`                              | State und Optimierer                                 | State zurücksetzen, Worker-Thread starten; Rückgabe`None`.                                                         |
| `progress(iteration, evaluation, candidate, total_candidates)`       | Optimierungszähler und optionale Evaluation         | Aktualisiert State, Kostenliste und gemittelte Anzeige-Metrics.                                                      |
| `worker()`                                                           | keine expliziten Argumente                           | Baseline, Optimierung und Abschlussbenchmark; schreibt State und setzt am Ende`running=False`.                       |
| `main()`                                                             | keine                                                | Startet über`subprocess.run` den Streamlit-Prozess und wartet auf dessen Ende.                                      |
| `_streamlit_app()`                                                   | keine                                                | Baut die Seite, Session-State, Button, laufende Anzeige und Abschlussanzeige auf.                                    |
| `globale_kosten_pro_kandidat(costs, container)`                      | Kostenliste, optionaler Streamlit-Platzhalter        | Zeichnet ein interaktives Altair-Liniendiagramm; keine Datenrückgabe.                                               |
| `mittlere_kennzahlen_pro_kandidat(metrics, container)`               | Liste gemittelter Kennzahlen, optionaler Platzhalter | Erzeugt DataFrame/Long-Format und facettiertes Altair-Diagramm.                                                      |
| `kennzahlenabweichung_gegen_kandidat_1(metrics, container)`          | Kennzahlenliste, optionaler Platzhalter              | Berechnet relative Prozentänderungen zum ersten Kandidaten und zeichnet sie.                                        |
| `vergleich_baseline_optimiert(benchmark)`                            | Dictionary mit Baseline-/Optimiert-Zeilen            | Mittelt je Steuerung, zeigt Tabelle und Seed-Diagramme.                                                              |

In `create_optimizer()` verbindet die verschachtelte Funktion
`run_simulation(weights, seed)` den Optimierer mit dem bereits erzeugten
`SpineMLSimulationRunner`. Sie nimmt lokalen Gewichtssatz und Seed und gibt
genau das Metrics-Objekt des Runners zurück.

Die Umbenennungen der Anzeige-Funktionen verwenden absichtlich fachliche
Namen: Sie sagen direkt, ob globale Kosten, mittlere Kennzahlen,
Kennzahlenabweichungen oder der Baseline-/Optimiert-Vergleich angezeigt
werden.

### 28.10 Weitere Ausgabefunktionen

`toString(state)` nimmt einen Salabim-State, summiert seine Zustandsdauern und
gibt eine Textliste wie `waiting=40.0%, working=60.0%` zurück. Bei einer
Gesamtdauer von null wird ein Anteil von `100%` für den jeweiligen Zustand
verwendet.

`toGraphML()` liefert aktuell die minimale Zeichenkette `<graphml></graphml>`;
es ist damit ein reservierter Export-Hook, keine vollständige
Konfigurationsserialisierung.
