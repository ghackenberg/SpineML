# SpineML

## Erweiterung auf eine austauschbare Controller-Architektur

Im Projekt wurde die Steuerungslogik von der eigentlichen Simulationslogik getrennt.
Ziel dieser Erweiterung ist es, unterschiedliche Steuerungsverfahren einsetzen zu können, ohne den Simulationskern für Roboter, Maschinen, Queues und Layouts jeweils neu anpassen zu müssen.

Die zentrale Idee ist:

- der Simulationskern beschreibt nur noch Zustände und Ausführung
- der Controller liest den Systemzustand periodisch ein
- die eigentliche Entscheidungslogik liegt in austauschbaren Policies
- Maschinen und Roboter führen nur noch die vom Controller erzeugten Commands aus

Damit entsteht eine klarere Schnittstelle zwischen Steuerung und Simulation und gleichzeitig eine Grundlage für spätere heuristische oder lernbasierte Verfahren.

## Überblick über die neue Struktur

Die Erweiterung konzentriert sich auf das Paket `sources/SpineML/controller/`.
Dort wurde die Steuerung in vier Bausteine aufgeteilt:

- `types.py`
- `calculate.py`
- `policy.py`
- `controller.py`
- `default_controller.py`

Zusätzlich wurde der Simulationskern im Ordner `sources/SpineML/Simulation/` so angepasst, dass Roboter und Maschinen ihre Entscheidungen nicht mehr selbst treffen, sondern Commands aus actor-spezifischen Command-Stores verarbeiten.

## Controller-Module

### `types.py`

`types.py` definiert die Datenschnittstelle zwischen Controller und Simulation.
Hier werden die Objekte beschrieben, mit denen der Controller arbeitet.

Dazu gehören insbesondere:

- `JobKey`
  - eindeutige Identifikation einer Produktionseinheit über Szenario, Order und Jobnummer
- `JobPlanningRequest`
  - Anfrage an die Routing-Logik für die Planung eines Jobs
- `JobPlan`
  - Ergebnis der Jobplanung mit `operation_sequence` und `machine_sequence`
- `JobHeadObservation`
  - detaillierte Beobachtung eines Jobs am Kopf einer Queue
- `QueueObservation`
  - Beobachtung einer Queue mit Länge und Head-Job
- `SystemObservation`
  - vollständige Beobachtung des Systems aus Sicht des Controllers
- `DispatchCommand`
  - allgemeiner Command an einen Actor
- `MainRobotCommand`, `ArmRobotCommand`, `MachineCommand`
  - konkrete Commands für die jeweiligen Actoren

Diese Typen bilden die eigentliche Schnittstelle zwischen Simulationskern und Steuerungslogik.

### `calculate.py`

`calculate.py` enthält die Logik zur Berechnung möglicher Operations- und Maschinenfolgen.
Diese Funktionen gehören fachlich zur Routing-Logik und werden von Routing-Policies genutzt.

Hier wird also berechnet:

- welche Operationsfolgen für ein Produkt möglich sind
- welche Maschinenfolgen für eine Operationsfolge im gegebenen Layout möglich sind

### `policy.py`

`policy.py` definiert die austauschbaren Steuerungsschnittstellen.

Es gibt zwei zentrale Policy-Arten:

- `RoutingPolicy`
  - plant einen einzelnen Job beim Erzeugen
  - liefert ein `JobPlan`
- `DispatchPolicy`
  - entscheidet im laufenden Betrieb, welche Commands als Nächstes erzeugt werden sollen

Zusätzlich gibt es:

- `RuleBasedDispatchPolicy`
  - ein regelbasiertes Gerüst für Dispatching
  - zerlegt die Gesamtentscheidung in kleinere Teilentscheidungen:
    - `decide_main_robot_pick(...)`
    - `decide_main_robot_place(...)`
    - `decide_arm_robot_pick(...)`
    - `decide_arm_robot_place(...)`
    - `decide_machine_process(...)`

Damit muss eine neue Dispatch-Strategie nicht zwingend die gesamte Methode `decide(...)` selbst schreiben, sondern kann auf diesem Gerüst aufbauen.

### `controller.py`

`controller.py` enthält den eigentlichen Laufzeit-Controller.

Die zentrale Klasse ist:

- `PolicyController`

`PolicyController` ist selbst eine `salabim.Component` und übernimmt die Vermittlung zwischen Simulation und Policies.

Seine Aufgaben sind:

- Speichern der aktiven `RoutingPolicy`
- Speichern der aktiven `DispatchPolicy`
- Beobachten aller relevanten Simulationsobjekte
- Umwandeln von Simulationszuständen in typed observations
- periodisches Aufrufen der Dispatch-Logik
- Verteilen der resultierenden Commands auf die jeweiligen Actoren

Technisch wichtig ist dabei:

- jeder Actor besitzt einen eigenen `cmd_store`
- der Controller verwaltet eine Zuordnung `actor_id -> cmd_store`
- neue Commands werden über diese Zuordnung an den richtigen Actor geschickt

Der `PolicyController` enthält dafür insbesondere:

- Statusfunktionen für Jobs, Roboter und Maschinen
- `read_status()` zum Erzeugen eines `SystemObservation`
- `build_commands()` zum Aufruf der aktiven Dispatch-Policy
- `process()` als periodische Controller-Schleife

Die Schleife läuft konzeptionell so:

1. Systemzustand lesen
2. aktive Policy aufrufen
3. Commands erzeugen
4. Commands in die passenden `cmd_store`s legen
5. kurzes Intervall warten
6. erneut beginnen

### `default_controller.py`

`default_controller.py` enthält die erste konkrete Standardimplementierung.

Hier werden definiert:

- `DefaultRoutingPolicy`
- `DefaultDispatchPolicy`
- `DefaultController`

Die aktuelle Baseline arbeitet wie folgt:

- `DefaultRoutingPolicy`
  - berechnet mögliche Operations- und Maschinenfolgen
  - wählt daraus eine gültige Folge aus
- `DefaultDispatchPolicy`
  - entscheidet für freie Main-Roboter, Arm-Roboter und Maschinen, welcher nächste Command erzeugt werden soll
- `DefaultController`
  - kombiniert diese beiden Policies mit dem `PolicyController`

Damit ist bereits eine lauffähige, aber austauschbare Standard-Steuerung vorhanden.

## Zusammenspiel mit dem Simulationskern

Die neue Architektur funktioniert nur, weil der Simulationskern im Ordner `sources/SpineML/Simulation/` angepasst wurde.

Die wichtigste Änderung ist:

- Simulationskomponenten führen aus
- der Controller entscheidet

Früher lag Entscheidungslogik stärker in den Simulationsklassen selbst.
Jetzt ist sie in den Policies ausgelagert.

## Änderungen im `Simulation`-Ordner

### `SimOrderJob`

`SimOrderJob` wurde so erweitert, dass jeder Job bereits beim Erzeugen geplant wird.

Beim Erzeugen eines Jobs passiert jetzt:

1. Aufbau eines `JobPlanningRequest`
2. Aufruf von `controller.plan_job(...)`
3. Speichern des zurückgegebenen `JobPlan`

Dadurch erhält jede Produktionseinheit ihre eigene:

- `operation_sequence`
- `machine_sequence`

Diese Route ist also nicht mehr implizit im Simulationskern versteckt, sondern wird explizit über die Routing-Policy festgelegt.

### `SimOrder` und `SimScenario`

`SimOrder` und `SimScenario` wurden so angepasst, dass sie den Controller an die erzeugten Unterobjekte weiterreichen.

Damit gilt:

- `SimScenario` erzeugt `SimOrder`
- `SimOrder` erzeugt `SimOrderJob`
- der Controller wird entlang dieser Struktur nach unten durchgereicht

So ist sichergestellt, dass jeder erzeugte Job direkt bei seiner Entstehung geplant werden kann.

### `SimMachine`

`SimMachine` wurde wesentlich verändert.

Die Maschine besitzt jetzt:

- einen eigenen `cmd_store`
- einen Status, ob gerade ein Command aktiv verarbeitet wird
- die Logik zur Ausführung eines `MachineCommand`

Die Maschine entscheidet also nicht mehr selbst, welchen Job sie verarbeiten soll.
Stattdessen:

1. wartet sie auf einen Command im `cmd_store`
2. liest den Command
3. holt den passenden Job aus `store_in`
4. prüft über `job_key`, ob Command und Job zusammenpassen
5. führt Toolwechsel und Bearbeitung entsprechend des Commands aus
6. legt den bearbeiteten Job in `store_out`

Damit ist die Maschine zu einem ausführenden Actor geworden.

### `SimRobotMain`

Auch der Main-Roboter besitzt jetzt:

- einen eigenen `cmd_store`
- eine Command-Ausführungslogik für `MainRobotCommand`

Er erhält vom Controller also nicht mehr nur indirekt eine Situation, sondern einen expliziten Befehl:

- wo er einen Job aufnehmen soll
- wohin er ihn transportieren soll

Der Main-Roboter:

1. liest einen Command aus dem `cmd_store`
2. fährt zum angegebenen Quellort
3. holt den passenden Job
4. prüft die Job-Identität über `job_key`
5. fährt zum Zielort
6. legt den Job dort ab

### `SimRobotCorridorArm`

Der Arm-Roboter im Korridor wurde analog umgestellt.

Auch er besitzt jetzt:

- einen eigenen `cmd_store`
- eine Ausführungslogik für `ArmRobotCommand`

Er kann damit explizit vom Controller angewiesen werden:

- einen Job aus dem Korridor-Store oder Maschinen-Output zu holen
- ihn in einen Maschinen-Input oder in einen Ausgangsstore zu legen

### `SimCorridorArm`, `SimCorridor`, `SimLayout`

Diese Strukturklassen wurden so angepasst, dass sie den Controller an die von ihnen erzeugten Maschinen- und Roboterobjekte weiterreichen.

Sie selbst treffen dabei keine Steuerungsentscheidungen, sondern sorgen dafür, dass:

- alle Actor korrekt erzeugt werden
- jeder Actor Zugriff auf den Controller bzw. seine Commands erhält

### `SimRobot`

`SimRobot` bleibt die gemeinsame Basisklasse für Roboter.

Dort liegt weiterhin:

- Bewegungslogik
- Interpolation für Animation
- Auslastungsberechnung
- Plot- und Statistikfunktionalität

Die eigentliche Entscheidung, welcher Transport als Nächstes erfolgen soll, liegt aber nicht mehr hier.

## Einbindung über `simulate.py`

Auch der Simulationsstart wurde an die neue Architektur angepasst.

In `simulate.py` wird nun:

1. ein Controller erzeugt
2. ein Layout erzeugt
3. ein Szenario erzeugt
4. die Menge aller Maschinen, Jobs, Main-Roboter und Arm-Roboter gesammelt
5. diese Actoren an den Controller angehängt
6. die Simulation gestartet

Standardmäßig wird dabei der `DefaultController` verwendet.

Wichtig ist:

- `simulate.py` nimmt eine `controller_class` entgegen
- dadurch kann statt des `DefaultController` auch eine andere Controllerklasse eingesetzt werden

Genau dadurch wird die Steuerungslogik austauschbar.

## Zusammenspiel mit den Actoren

Die Actoren im Simulationskern sind jetzt klar in die Controller-Architektur eingebunden.

Das Zusammenspiel ist:

1. der Controller beobachtet das System
2. die aktive Policy entscheidet auf Basis dieser Beobachtung
3. daraus entstehen Commands
4. Commands werden in actor-spezifische `cmd_store`s gelegt
5. der jeweilige Actor führt den Command aus

Das bedeutet konkret:

- der Controller entscheidet
- die Actoren führen aus

Diese Trennung ist die wichtigste architektonische Änderung des Refactorings.

## Warum die Architektur jetzt austauschbar ist

Die neue Architektur erlaubt es, die Entscheidungslogik auszutauschen, ohne die Simulationslogik neu zu schreiben.

Das gilt, weil:

- der Simulationskern nur noch typed observations liefert
- der Controller nur noch typed commands verschickt
- die Policies allein bestimmen, wie geplant und dispatcht wird

Wenn also eine neue Strategie ausprobiert werden soll, muss nicht `SimMachine`, `SimRobotMain` oder `SimRobotCorridorArm` umgeschrieben werden.
Stattdessen reicht es, neue Policy-Klassen zu implementieren.

## Bedeutung für heuristische Verfahren

Durch diese Trennung ist die Grundlage geschaffen, um neue Steuerungsverfahren einzusetzen.

Das betrifft insbesondere:

- heuristische Routing-Verfahren
- heuristische Dispatching-Verfahren
- Greedy-Strategien
- score-basierte Prioritätsregeln
- später auch aufwendigere Optimierungs- oder Lernverfahren

Technisch bedeutet das:

- eine neue Routing-Heuristik wird als neue `RoutingPolicy` implementiert
- eine neue Dispatch-Heuristik wird als neue `DispatchPolicy` oder als neue Unterklasse von `RuleBasedDispatchPolicy` implementiert

Die Simulation selbst bleibt dabei unverändert.

## Zusammenfassung

Mit der Erweiterung auf eine austauschbare Controller-Architektur wurde die Steuerung von SpineML klar vom Simulationskern getrennt.

Die wichtigsten Ergebnisse sind:

- ein neues `controller`-Modul als klare Steuerungsschicht
- typed observations und typed commands als definierte Schnittstelle
- ein periodisch laufender `PolicyController`
- actor-spezifische `cmd_store`s für Main-Roboter, Arm-Roboter und Maschinen
- eine Standard-Baseline mit `DefaultRoutingPolicy` und `DefaultDispatchPolicy`
- angepasste Simulationsklassen, die Commands ausführen statt selbst zu entscheiden
- eine Architektur, die gezielt für spätere heuristische Erweiterungen vorbereitet ist

Damit ist die Grundlage geschaffen, unterschiedliche Steuerungsstrategien systematisch mit demselben Simulationskern zu vergleichen.
