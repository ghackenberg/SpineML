# SimMachine

Python-Datei: `sources/SpineML/Simulation/SimMachine.py`

## Position im Ablauf

```text
SimRobotCorridorArm
└── legt einen geplanten Job in den Maschinen-Eingangsstore
    │
    ▼
SimMachine
├── nimmt den Job aus store_in
├── rüstet oder wechselt bei Bedarf das Werkzeug
├── führt die geplante Operation aus
├── aktualisiert Produkt- und Werkzeugzustand
└── legt den Job in store_out
    │
    ▼
SimRobotCorridorArm
└── holt den bearbeiteten Job wieder ab
```

Die Maschinensteuerung erfolgt über denselben Bridge-Zyklus:

```text
SimMachine.request_action()
→ PolicyTrigger
→ PolicyObservation
→ PolicyDecision
→ Bridge-Prüfung und ID-Auflösung
→ SimulationAction im persönlichen Maschinen-Action-Store
```

`SimMachine` ist eine echte Salabim-Komponente:

```python
class SimMachine(sim.Component):
```

Sie gehört zum Simulationskern. Die Policy erhält keine Referenz auf dieses
Objekt, sondern nur ein ID-basiertes Zustands-Dictionary.

## Konstruktor

```python
def __init__(self, machine, bridge, x, y, *args, **kwargs):
```


| Parameter           | Bedeutung                                              |
| --------------------- | -------------------------------------------------------- |
| `machine`           | echtes statisches Konfigurationsobjekt dieser Maschine |
| `bridge`            | Schnittstelle zwischen Simulationskern und Policy      |
| `x`, `y`            | Position in der 3D-Visualisierung                      |
| `*args`, `**kwargs` | zusätzliche Argumente für`sim.Component`             |

Der Konstruktor erzeugt den Maschinenzustand, die Werkzeugdaten, die beiden
Stores, die Bridge-Registrierung und die 3D-Elemente. Der Produktionsablauf
befindet sich in `process()` und den beiden `execute_...`-Methoden.

## Wichtige Attribute vor der Registrierung

Diese Attribute werden im Konstruktor erzeugt, bevor sich die Maschine bei der
Bridge registriert:

```text
machine
└── echtes Konfigurationsobjekt der Maschine

state
├── Typ: sim.State
├── Anfangswert: "waiting"
└── spätere Werte: "mounting", "unmounting", "working" oder "returning"

tool_type
├── Typ: ToolType | None
├── Anfangswert: None
└── aktuell montierter Werkzeugtyp

processing_speed_factor
├── Typ: float | None
├── Anfangswert: None
├── vor der ersten Bearbeitung noch nicht durch die Policy konfiguriert
└── wird bei jeder process_machine_job-Aktion aus dem Payload übernommen

tool_types
├── Kopie von machine.tool_types
├── enthält die Werkzeugtypen dieser konkreten Maschine
└── ohne maschinenspezifische Liste: Werkzeuge aus MachineType.computeToolTypes()

remaining_life_units
└── tatsächliche verbleibende Standzeit pro ToolType

remaining_life_units_t
└── Simulationszeitpunkt des tatsächlichen Standzeitwerts

remaining_life_units_next
└── für das Bearbeitungsende geplanter Standzeitwert

remaining_life_units_next_t
└── Simulationszeitpunkt des geplanten Standzeitwerts
```

Konkreter Ablauf des Bearbeitungsgeschwindigkeitsfaktors:

```text
SimMachine.__init__()
└── processing_speed_factor = None
        ↓
Policy wählt process_machine_job
└── Generator erzeugt Kandidaten mit Faktor 0.5, 1.0 und 2.0
        ↓
Evaluator und Selector
└── bewerten und wählen eine Faktorvariante
        ↓
SimMachine.execute_process_action()
└── self.processing_speed_factor = action.payload["processing_speed_factor"]
        ↓
Simulationskern
└── duration = belastungsabhängige Basisdauer / processing_speed_factor
```

Bei jeder späteren `process_machine_job`-Aktion wird der bisherige Faktor durch
den neu von der Policy gelieferten Faktor überschrieben.

### Initialisierung der vier Standzeit-Dictionaries

Die wichtigste Namensregel lautet:

```text
ohne _next
└── tatsächlicher und aktuell gespeicherter Wert

mit _next
└── geplanter Wert nach Abschluss der laufenden Bearbeitung
```

Konkret:

```text
remaining_life_units
└── tatsächliche, aktuell vorhandene Werkzeugstandzeit

remaining_life_units_t
└── Zeitpunkt, zu dem dieser tatsächliche Wert gilt

remaining_life_units_next
└── geplante Werkzeugstandzeit nach der laufenden Bearbeitung

remaining_life_units_next_t
└── geplanter Zeitpunkt am Ende der laufenden Bearbeitung
```

Die vier Dictionaries sind am Anfang leer:

```python
self.remaining_life_units: dict[ToolType, int] = {}
self.remaining_life_units_t: dict[ToolType, float] = {}
self.remaining_life_units_next: dict[ToolType, int] = {}
self.remaining_life_units_next_t: dict[ToolType, float] = {}
```

### Konkrete Beispiele für `dict[ToolType, int]`

Die Typannotation

```python
dict[ToolType, int]
```

bedeutet:

```text
Key   = ein ToolType-Objekt
Value = eine ganze Zahl (int)
```

Konkretes Beispiel:

```python
fraeswerkzeug = ToolType(
    "Fräswerkzeug",
    mount_time=2,
    unmount_time=1,
    total_life_units=100,
)

schleifwerkzeug = ToolType(
    "Schleifwerkzeug",
    mount_time=3,
    unmount_time=1,
    total_life_units=80,
)

remaining_life_units: dict[ToolType, int] = {
    fraeswerkzeug: 100,
    schleifwerkzeug: 80,
}
```

Dabei sind `fraeswerkzeug` und `schleifwerkzeug` die Keys. Die Zahlen `100`
und `80` sind die zugehörigen `int`-Values.

```text
fraeswerkzeug   → 100 Life Units
schleifwerkzeug → 80 Life Units
```

Zugriff auf einen Wert:

```python
remaining_life_units[fraeswerkzeug]
```

Rückgabe:

```python
100
```

Wert verändern:

```python
remaining_life_units[fraeswerkzeug] = 90
```

Danach enthält das Dictionary:

```python
{
    fraeswerkzeug: 90,
    schleifwerkzeug: 80,
}
```

Die Maschine verwendet dieselbe Struktur auch für den geplanten Wert:

```python
remaining_life_units_next: dict[ToolType, int] = {
    fraeswerkzeug: 90,
    schleifwerkzeug: 80,
}
```

Hier bedeutet `fraeswerkzeug: 90`: Nach Abschluss der laufenden Bearbeitung
soll das Fräswerkzeug noch 90 Life Units besitzen.

### Konkrete Beispiele für `dict[ToolType, float]`

Bei

```python
dict[ToolType, float]
```

bleibt der Key ein `ToolType`-Objekt. Der Value ist jedoch eine Kommazahl für
einen Simulationszeitpunkt:

```python
remaining_life_units_t: dict[ToolType, float] = {
    fraeswerkzeug: 20.0,
    schleifwerkzeug: 0.0,
}

remaining_life_units_next_t: dict[ToolType, float] = {
    fraeswerkzeug: 30.0,
    schleifwerkzeug: 0.0,
}
```

Für das Fräswerkzeug ergibt sich damit:

```text
remaining_life_units[fraeswerkzeug]        = 100
remaining_life_units_t[fraeswerkzeug]      = 20.0
remaining_life_units_next[fraeswerkzeug]   = 90
remaining_life_units_next_t[fraeswerkzeug] = 30.0

Bedeutung:
Bei t=20 besitzt das Fräswerkzeug tatsächlich 100 Life Units.
Bei t=30 soll es nach der Bearbeitung noch 90 Life Units besitzen.
```

Der Key ist jeweils ein echtes `ToolType`-Objekt. Der Value ist entweder eine
Standzeit in Life Units oder eine Simulationszeit:

```text
Dictionary                         Key        Value
remaining_life_units               ToolType → aktuelle Life Units
remaining_life_units_t             ToolType → Zeitpunkt des aktuellen Werts
remaining_life_units_next          ToolType → nächster geplanter Life-Unit-Wert
remaining_life_units_next_t        ToolType → Zeitpunkt des nächsten Werts
```

Danach läuft die Schleife einmal über jeden Werkzeugtyp, der für diese konkrete
Maschine in `machine.tool_types` konfiguriert wurde:

```python
for tool_type in self.tool_types:
    self.remaining_life_units[tool_type] = tool_type.total_life_units
    self.remaining_life_units_t[tool_type] = self.env.now()
    self.remaining_life_units_next[tool_type] = tool_type.total_life_units
    self.remaining_life_units_next_t[tool_type] = self.env.now()
```

Zeile für Zeile passiert für jeden `tool_type` Folgendes:

```text
1. remaining_life_units[tool_type] = total_life_units
   └── Das neue Werkzeug beginnt mit seiner vollständigen Standzeit.

2. remaining_life_units_t[tool_type] = env.now()
   └── Speichert, zu welcher Simulationszeit dieser aktuelle Wert gilt.

3. remaining_life_units_next[tool_type] = total_life_units
   └── Zu Beginn ist auch der nächste geplante Wert noch die volle Standzeit.

4. remaining_life_units_next_t[tool_type] = env.now()
   └── Aktueller und nächster Wert gelten anfangs zum selben Zeitpunkt.
```

### Konkretes Initialisierungsbeispiel

Angenommen, die Simulation befindet sich bei `env.now() == 0.0` und die
Maschine kann zwei Werkzeuge verwenden:

```text
Fräswerkzeug
└── total_life_units = 100

Schleifwerkzeug
└── total_life_units = 80

self.tool_types = [Fräswerkzeug, Schleifwerkzeug]
```

Vor der Schleife:

```python
remaining_life_units = {}
remaining_life_units_t = {}
remaining_life_units_next = {}
remaining_life_units_next_t = {}
```

Erster Schleifendurchlauf:

```text
tool_type = Fräswerkzeug

remaining_life_units[Fräswerkzeug]        = 100
remaining_life_units_t[Fräswerkzeug]      = 0.0
remaining_life_units_next[Fräswerkzeug]   = 100
remaining_life_units_next_t[Fräswerkzeug] = 0.0
```

Zweiter Schleifendurchlauf:

```text
tool_type = Schleifwerkzeug

remaining_life_units[Schleifwerkzeug]        = 80
remaining_life_units_t[Schleifwerkzeug]      = 0.0
remaining_life_units_next[Schleifwerkzeug]   = 80
remaining_life_units_next_t[Schleifwerkzeug] = 0.0
```

Nach der gesamten Schleife enthalten die vier Dictionaries:

```python
remaining_life_units = {
    Fräswerkzeug: 100,
    Schleifwerkzeug: 80,
}

remaining_life_units_t = {
    Fräswerkzeug: 0.0,
    Schleifwerkzeug: 0.0,
}

remaining_life_units_next = {
    Fräswerkzeug: 100,
    Schleifwerkzeug: 80,
}

remaining_life_units_next_t = {
    Fräswerkzeug: 0.0,
    Schleifwerkzeug: 0.0,
}
```

### Warum gibt es einen aktuellen und einen nächsten Wert?

Beim Start einer Bearbeitung kennt die Maschine beide Punkte:

```text
Beginn der Bearbeitung bei t=20
└── Fräswerkzeug besitzt 100 Life Units

Geplantes Ende der Bearbeitung bei t=30
└── Fräswerkzeug wird noch 90 Life Units besitzen
```

Dafür werden die Werte so gesetzt:

```python
remaining_life_units[Fräswerkzeug] = 100
remaining_life_units_t[Fräswerkzeug] = 20.0
remaining_life_units_next[Fräswerkzeug] = 90
remaining_life_units_next_t[Fräswerkzeug] = 30.0
```

Die von `create_tool_life_bar_length_function(...)` erzeugte Funktion kann
zwischen diesen beiden Punkten interpolieren. Dadurch wird der
Standzeitbalken während der Bearbeitung schrittweise kleiner:

```text
t=20 → 100 Life Units
t=25 → ungefähr 95 Life Units in der Animation
t=30 → 90 Life Units
```

Die Zwischenwerte dienen nur der Animation. Nach `yield hold(duration)` wird
der Endwert `90` als neuer tatsächlicher Wert gespeichert.

## Visualisierung

Die 3D-Visualisierung besteht aus mehreren `sim.Animate3dBox`-Objekten. Diese
Boxen simulieren nicht die Maschinenlogik. Sie stellen lediglich den aktuellen
Zustand der Maschine grafisch dar.

### Schematischer Aufbau der Maschine

```text
                  grüner vertikaler Aufbau
                            │
                            ▼
                ┌────────────────────┐
                │ obere weiße Platte │  ← oberer Tool support
          ┌─────┴────────────────────┴─────┐
          │ hellgraue obere Machine-Box    │
          │                                │
          │   blau  blau  blau  blau       │  ← Toolbars
          │                                │
          └───────────┬──────────┬─────────┘
                      │  untere  │           ← untere weiße Platte
                ┌─────┴──────────┴─────┐
                │ hellgraue untere     │
                │ Machine-Box          │
                │                      │
                │ ──────────────────── │  ← Life-Bar
                │ ──────────────────── │  ← Life-Bar
                │ ──────────────────── │  ← Life-Bar
                │ ──────────────────── │  ← Life-Bar
                └──────────────────────┘
```

Zuordnung der Farben:

```text
grün
└── vertikaler Maschinenaufbau

weiß beziehungsweise durch Beleuchtung grau
└── beide Boxen des Tool support

hellgrau (`lightgray`)
├── obere Machine-Box
└── untere Machine-Box

blau
└── Toolbar für jeden verfügbaren Werkzeugtyp

dynamisch grau, grün, gelb, orange oder rot
└── Life-Bar für den Zustand und die Standzeit eines Werkzeugtyps
```

Die mit `color="white"` definierten Tool-support-Boxen können in der 3D-Ansicht
auf ihren Seitenflächen grau aussehen. Das entsteht durch Beleuchtung und
Schattierung. Die beiden Machine-Boxen verwenden dagegen ausdrücklich
`color="lightgray"`.

### Vertikaler Maschinenaufbau

```python
sim.Animate3dBox(
    x_len=0.25,
    y_len=0.25,
    z_len=1.20,
    color="green",
    x=x,
    y=y,
    z=1.80,
)
```

Diese grüne Box stellt den vertikalen Teil der Maschine dar:

```text
x_len, y_len, z_len
└── Größe der Box in den drei Raumrichtungen

color
└── Farbe der Box

x, y, z
└── Position der Box im 3D-Modell
```

### Werkzeughalterung

Zwei weiße Boxen bilden die Halterung für die angezeigten Werkzeuge:

```python
sim.Animate3dBox(..., color="white", ...)
sim.Animate3dBox(..., color="white", ...)
```

Sie haben keine eigene Zustandslogik und dienen ausschließlich der optischen
Darstellung.

### Toolbars

Für jeden möglichen Werkzeugtyp wird eine kleine blaue Box erzeugt:

```python
m = 0
for tool_type in self.tool_types:
    sim.Animate3dBox(
        x_len=0.05,
        y_len=0.05,
        z_len=0.18,
        color="blue",
        x=x + m,
        y=y + 0.25,
        z=1.10,
    )
    m = m + 0.1
```

Konkretes Beispiel mit drei Werkzeugtypen:

```text
erster Werkzeugtyp  → m=0.0 → Position x
zweiter Werkzeugtyp → m=0.1 → Position x+0.1
dritter Werkzeugtyp → m=0.2 → Position x+0.2
```

`m` sorgt dafür, dass die Werkzeuganzeigen nebeneinander und nicht an derselben
Position gezeichnet werden.

### Life-Bars

Für jeden Werkzeugtyp wird außerdem ein Standzeitbalken erzeugt:

```python
z = 0.70
for tool_type in self.tool_types:
    x_len = self.create_tool_life_bar_length_function(tool_type)
    color = self.create_tool_life_bar_color_function(tool_type)
    sim.Animate3dBox(
        x_len=x_len,
        y_len=0.01,
        z_len=0.07,
        color=color,
        x=x,
        y=y + 0.4379,
        z=z,
    )
    z = z - 0.08
```

```text
x_len
└── von create_tool_life_bar_length_function(tool_type) erzeugte Funktion

color
└── von create_tool_life_bar_color_function(tool_type) erzeugte Funktion

z = z - 0.08
└── setzt jeden Werkzeugbalken etwas unter den vorherigen Balken
```

Die erzeugten Längen- und Farbfunktionen speichern für jeden Balken ihren
eigenen `tool_type`. Salabim kann beide anschließend bei jedem
Animationszeitpunkt mit der aktuellen Zeit aufrufen.

### `create_tool_life_bar_length_function()`: Längenfunktion erzeugen

```python
def create_tool_life_bar_length_function(self, tool_type):
    def tool_life_bar_length(animation_time):
        # Balkenlänge berechnen
        ...

    return tool_life_bar_length
```

Die äußere Methode erhält einen `tool_type` und gibt eine neue Funktion zurück:

```text
Eingabe
└── tool_type

Rückgabe
└── tool_life_bar_length(animation_time)
```

`x_len` enthält deshalb keine feste Zahl, sondern die zurückgegebene Funktion:

```python
x_len = self.create_tool_life_bar_length_function(tool_type)
```

Salabim ruft sie später mit der aktuellen Animationszeit auf:

```python
x_len(animation_time)
```

Die innere Funktion berechnet dann die sichtbare Balkenlänge für den bereits
gespeicherten Werkzeugtyp.
Wenn aktueller und geplanter Zeitpunkt gleich sind, ist keine Bearbeitung mit
einem zeitlichen Übergang geplant:

```python
return remaining_life_units / total_life_units * 0.4
```

### Interpolationsformel

Während einer laufenden Bearbeitung verwendet die innere Funktion diese Formel:

```python
return (
    rtlu
    + (rtlu_next - rtlu)
    * (animation_time - rtlu_t)
    / (rtlu_next_t - rtlu_t)
) / tool_type.total_life_units * 0.4
```

Die Variablen bedeuten:

```text
rtlu          → tatsächliche Life Units am Anfang
rtlu_next     → geplante Life Units am Ende
rtlu_t        → Anfangszeitpunkt
rtlu_next_t   → geplanter Endzeitpunkt
animation_time → aktuell dargestellter Animationszeitpunkt
```

Die Berechnung lässt sich so lesen:

```text
vergangene Bearbeitungszeit
────────────────────────── = Bearbeitungsfortschritt zwischen 0 und 1
gesamte geplante Bearbeitungszeit
```

```text
aktuelle Life Units
+ geplante Life-Unit-Änderung × Bearbeitungsfortschritt
= interpolierte Life Units
```

```text
interpolierte Life Units
──────────────────────── × maximale Balkenlänge 0.4
gesamte Life Units
```

Dadurch wird der Balken während der Bearbeitung kontinuierlich kleiner.

### `create_tool_life_bar_color_function()`: Farbfunktion erzeugen

```python
def create_tool_life_bar_color_function(self, tool_type):
    def tool_life_bar_color(animation_time):
        # Balkenfarbe bestimmen
        ...

    return tool_life_bar_color
```

Die äußere Methode erhält einen `tool_type` und gibt die zugehörige
Farbfunktion zurück:

```text
Eingabe
└── tool_type

Rückgabe
└── tool_life_bar_color(animation_time)
```

Verwendung in der Visualisierung:

```python
color = self.create_tool_life_bar_color_function(tool_type)
```

`color` enthält keine feste Farbe. Salabim ruft die gespeicherte Funktion
später wiederholt auf. Die Funktion wählt die Farbe abhängig vom Werkzeug und
vom aktuellen Maschinenzustand:

Der Parameter `animation_time` wird von Salabim übergeben, ist für die aktuelle
Farblogik aber nicht erforderlich. Er bleibt in der Signatur, damit die
Funktion als zeitabhängige Salabim-Animationsfunktion verwendet werden kann.

```text
Werkzeug ist nicht montiert
└── grau

Werkzeug ist montiert und Maschine demontiert es
└── orange

Das neue Werkzeug ist ausgewählt, aber noch nicht fertig montiert
└── mounting → gelb

Werkzeug ist montiert und wird gerade verbraucht
└── state == "working" → rot

Die Bearbeitung mit dem montierten Werkzeug ist beendet
└── grün
```

Die Farbe wird jetzt direkt aus dem Maschinenzustand bestimmt. Die geplanten
Zeitpunkte `remaining_life_units_t` und `remaining_life_units_next_t` werden
nur noch für die animierte Balkenlänge verwendet, nicht für die Farbe.

Die Bedingungen werden von oben nach unten geprüft. Durch jedes `return` wird
genau eine Farbe ausgegeben:

```python
if tool_type != self.tool_type:
    return "gray"
if self.state.get() == "unmounting":
    return "orange"
if self.state.get() == "mounting":
    return "yellow"
if self.state.get() == "working":
    return "red"
return "green"
```


| Reihenfolge | Bedingung                     | Farbe  | Bedeutung                                                      |
| ------------: | ------------------------------- | -------- | ---------------------------------------------------------------- |
|           1 | `tool_type != self.tool_type` | Grau   | Dieses Werkzeug ist nicht montiert.                            |
|           2 | `state == "unmounting"`       | Orange | Das montierte Werkzeug wird demontiert.                        |
|           3 | `state == "mounting"`         | Gelb   | Das neue Werkzeug ist ausgewählt; die Montage läuft noch.    |
|           4 | `state == "working"`          | Rot    | Die Maschine bearbeitet mit dem montierten Werkzeug einen Job. |
|           5 | keine vorherige Bedingung     | Grün  | `working` ist beendet; das Werkzeug bleibt montiert.           |

Die Zeitstempel stehen bewusst nicht mehr in diesen Bedingungen. Sie verändern
nur die Länge des Life-Bars.

Warum erreicht das neue Werkzeug überhaupt die gelbe Bedingung? Der Code setzt
es bereits zu Beginn der Montage als aktuelles `self.tool_type`:

```python
self.state.set("mounting")
self.tool_type = tool_type
yield self.hold(self.tool_type.mount_time)
```

Während des `hold(...)` gilt deshalb gleichzeitig:

```text
tool_type == self.tool_type
└── die graue Bedingung ist False

state == "mounting"
└── die gelbe Bedingung ist True
```

Das bedeutet nur, dass dieses Werkzeug jetzt als aktuelles Werkzeug ausgewählt
ist. Die physische Montage ist während der gelben Phase noch nicht beendet.

Beim ersten Einsetzen eines Werkzeugs ist der typische Ablauf:

```text
grau
└── Werkzeug ist nicht montiert
    ↓
gelb
└── Werkzeug ist noch demontiert; die Montage läuft
    ↓
rot
└── Maschine bearbeitet den Job
    ↓
grün
└── Bearbeitung ist beendet und Werkzeug bleibt montiert
```

Bei einem Werkzeugwechsel ist der Ablauf für das bisher montierte Werkzeug:

```text
grün
└── vorherige Bearbeitung ist beendet; das Werkzeug ist noch montiert
    ↓
orange
└── bisheriges Werkzeug wird demontiert
    ↓
grau
└── bisheriges Werkzeug ist nicht mehr montiert
```

Das neu eingesetzte Werkzeug durchläuft währenddessen:

```text
grau → gelb → rot → grün
```

### Hellgrauer Maschinenkörper

Zum Schluss erzeugen zwei hellgraue Boxen den eigentlichen sichtbaren
Maschinenkörper:

```python
sim.Animate3dBox(..., color="lightgray", ...)
sim.Animate3dBox(..., color="lightgray", ...)
```

Gesamtaufbau:

```text
SimMachine-Visualisierung
├── grüne vertikale Box
├── weiße Werkzeughalterung
├── blaue Toolbar pro Werkzeugtyp
├── dynamischer Life-Bar pro Werkzeugtyp
│   ├── Länge durch create_tool_life_bar_length_function()
│   └── Farbe durch create_tool_life_bar_color_function()
└── zwei hellgraue Boxen für den Maschinenkörper
```

## Registrierung

Die Policy-ID enthält den Konfigurationsnamen und die Maschinenseite:

```python
machine_side = "left" if self.machine.left else "right"
self.policy_id = f"SimMachine:{self.machine.name}:{machine_side}"
```

Beispiel:

```text
"SimMachine:Machine 1.1.1:left"
```

Diese Policy-ID ist nur ein `str`. Sie ist kein echtes `SimMachine`-Objekt:

```text
"SimMachine:Machine 1.1.1:left"
└── Typ: str
    └── reine ID für Snapshot, PolicyDecision und Bridge-Zuordnung

SimMachine (simmachine.0)
└── Typ: SimMachine beziehungsweise sim.Component
    └── echtes laufendes Simulationsobjekt
```

### Bedeutung von `Machine 1.1.1`

Die drei Zahlen folgen in den Beispieldateien dieser Namenskonvention:

```text
Machine 1.1.1
        │ │ │
        │ │ └── erste Maschine in diesem Corridor
        │ └──── erster Corridor in diesem Layout
        └────── erstes Layout
```

Weitere Beispiele:

```text
Machine 1.1.2
└── zweite Maschine im ersten Corridor des ersten Layouts

Machine 1.2.1
└── erste Maschine im zweiten Corridor des ersten Layouts

Machine 2.3.1
└── erste Maschine im dritten Corridor des zweiten Layouts
```

Diese Zahlen werden nicht von `Machine` zerlegt oder berechnet. Sie sind eine
menschlich gewählte Konvention im Konfigurationsnamen `machine.name`.

Die vollständige Policy-ID ergänzt Typ und Seite:

```text
SimMachine:Machine 1.1.1:left
│          │             │
│          │             └── Maschine steht auf der linken Corridor-Seite
│          └──────────────── Konfigurationsname der Maschine
└─────────────────────────── Typpräfix für die Policy-ID
```

Bei einer rechten Maschine endet die ID entsprechend mit:

```text
:right
```

Registrierung:

```python
self.bridge.register(
    self.policy_id,
    self,
    stores=[self.store_in, self.store_out],
)
```

Dadurch entstehen:

```text
policy_object_id_to_simulation_object
└── Key:   "SimMachine:Machine 1.1.1:left"  ← Policy-ID vom Typ str
    Value: SimMachine (simmachine.0)         ← echtes Simulationsobjekt

simulation_object_to_policy_object_id
└── Key:   SimMachine (simmachine.0)         ← echtes Simulationsobjekt
    Value: "SimMachine:Machine 1.1.1:left"  ← Policy-ID vom Typ str

sim_action_stores
└── Key:   SimMachine (simmachine.0)                  ← echtes Simulationsobjekt
    Value: Store (simmachine.0 simulation actions)    ← echter persönlicher sim.Store

policy_store_id_to_simulation_store
├── Key:   "Machine 1.1.1 in"               ← Policy-Store-ID vom Typ str
│   Value: Store (Machine 1.1.1 in)           ← echter store_in
│
└── Key:   "Machine 1.1.1 out"              ← Policy-Store-ID vom Typ str
    Value: Store (Machine 1.1.1 out)          ← echter store_out
```

### Bedeutung von `in` und `out`

```text
"Machine 1.1.1 in"
└── ID des Eingangs-Stores dieser Maschine
    └── dort wartet ein Job vor dem Pick durch die Maschine

"Machine 1.1.1 out"
└── ID des Ausgangs-Stores dieser Maschine
    └── dort liegt ein Job nach der Bearbeitung
```

Auch die Store-IDs sind nur Strings. `store_in` und `store_out` selbst sind
dagegen echte Salabim-Store-Objekte und bleiben auf der Simulationsseite der
Bridge.

## Was sieht die Policy von der Maschine?

`SimulationObjectObserver.observe_machine(...)` liest die echte Maschine und
erzeugt ein `dict[str, object]` aus reinen Zustandsdaten und IDs:

```text
Maschinenbeobachtung
├── object_id, machine_name und machine_type_id
├── corridor_id und left
├── state, is_idle und has_current_job
├── current_job_id und current_job_summary
├── mounted_tool_type_id
├── remaining_life_units_by_tool nach Werkzeug-ID
├── next_operation_id und next_machine_id
├── required_tool_type_id
├── has_enough_tool_life und needs_tool_change
├── input_storage und output_storage
└── is_waiting_for_action (von der Bridge ergänzt)
```

Die Policy erhält dadurch keine echte `SimMachine`, keine echten Jobs, Stores
oder Konfigurationsobjekte.

## process()

### Position im Ablauf

```text
while True
├── bridge.request_action(self)
├── action = bridge.action(self)
├── pick_machine_job    → execute_pick_action(...)
└── process_machine_job → execute_process_action(...)
```

Die beiden `yield`-Anweisungen haben unterschiedliche Aufgaben:

```text
yield bridge.request_action(self)
└── meldet den Entscheidungsbedarf und legt einen PolicyTrigger ab

action = yield bridge.action(self)
└── wartet auf eine SimulationAction im persönlichen Action-Store
```

Erst wenn die aktuelle Pick- oder Bearbeitungsaktion vollständig beendet ist,
beginnt die Schleife erneut und die Maschine fordert eine neue Aktion an.

## execute_pick_action()

```python
def execute_pick_action(self, action):
```

Diese Methode wird von `process()` aufgerufen, wenn die empfangene
`SimulationAction` diesen Aktionstyp besitzt:

```python
action.action_type == "pick_machine_job"
```

Konkrete aufgelöste Aktion:

```python
SimulationAction(
    target=sim_machine,
    action_type="pick_machine_job",
    payload={
        "target_store_id": "Machine 1.1.1 in",
        "selected_job_id": "Order 1.1:0",
        "target_store": machine_input_store,
        "selected_job": sim_order_job,
    },
    # weitere Attribute
)
```

Ausführung:

```text
selected_job und target_store aus dem aufgelösten Payload lesen
→ exakt dieses Objekt mit from_store(..., filter=...) entnehmen
→ current_job = entnommener Job
```

`from_store(..., filter=...)` entnimmt gezielt genau den von der Policy über
`selected_job_id` gewählten Job. Die Bridge hat diese ID vorher zum echten
`selected_job` aufgelöst.

### `from_store()` mit einer Filterfunktion

Der vollständige Code lautet:

```python
job = yield self.from_store(
    target_store,
    filter=lambda item, selected_job=selected_job: item is selected_job,
)
```

Ohne Filter würde die Maschine einen verfügbaren Job aus dem Store anfordern:

```python
job = yield self.from_store(target_store)
```

Mit `filter=...` darf Salabim dagegen ausschließlich das konkrete
`selected_job`-Objekt entnehmen.

Der Lambda-Ausdruck:

```python
lambda item, selected_job=selected_job: item is selected_job
```

entspricht dieser normalen Funktion:

```python
def is_selected_job(item, selected_job=selected_job):
    return item is selected_job
```

Die beiden Parameter haben unterschiedliche Herkunft:

```text
item
└── wird später von Salabim für jedes geprüfte Store-Objekt übergeben

selected_job=selected_job
└── speichert beim Erzeugen der Filterfunktion den zuvor ausgewählten Job
```

Konkretes Beispiel:

```text
target_store
├── SimOrderJob A
├── SimOrderJob B  ← selected_job
└── SimOrderJob C

Filter für Job A
└── A is B → False

Filter für Job B
└── B is B → True
    └── genau Job B wird aus dem Store entnommen
```

`is` prüft die Objektidentität:

```text
item is selected_job
└── True nur dann, wenn beide Variablen auf exakt dasselbe Python-Objekt zeigen
```

Zwei unterschiedliche Jobs mit denselben Attributwerten würden nicht
akzeptiert, weil sie nicht dasselbe Objekt sind.

Das `yield` steuert das Warten auf die Store-Anforderung:

```text
selected_job befindet sich im target_store
└── Filter liefert True
    └── Job wird entnommen
        └── yield endet
            └── Variable job enthält selected_job

selected_job befindet sich noch nicht im target_store
└── kein Store-Objekt erfüllt den Filter
    └── SimMachine bleibt bei yield blockiert
        └── andere Simulationskomponenten können weiterlaufen
            └── sobald selected_job eintrifft, kann die Anforderung erfüllt werden
```

`SimMachine` führt dafür keine eigenen `ValueError`-Prüfungen mehr aus. Die
Korrektheit der ID-Auflösung, Reservierung und Aktionsauswahl wird außerhalb
dieser Simulationskomponente sowie durch Tests abgesichert.

```text
vor dem Pick
├── store_in enthält Order 1.1:0
└── current_job = None

nach dem Pick
├── store_in enthält Order 1.1:0 nicht mehr
└── current_job = SimOrderJob("Order 1.1:0")
```

## execute_process_action()

```python
def execute_process_action(self, action):
```

Diese Methode wird von `process()` aufgerufen, wenn die empfangene
`SimulationAction` diesen Aktionstyp besitzt:

```python
action.action_type == "process_machine_job"
```

### Konkretes Beispiel einer empfangenen SimulationAction

Vor der Bridge enthält die ausgewählte Policyaktion nur IDs und reine Daten:

```python
SelectedObjectAction(
    target_id="SimMachine:Machine 1.1.1:left",
    action_type="process_machine_job",
    payload={
        "operation_id": "Operation 1",
        "planned_machine_id": "Machine 1.1.1",
        "tool_type_id": "Tool Type 1",
        "total_life_units": 25,
        "consumed_life_units": 10,
        "remaining_life_units_before_operation": 25,
        "processing_speed_factor": 1.0,
        "tool_setup_action": "unmount_and_mount_tool",
        "target_store_id": "Machine 1.1.1 out",
    },
)
```

Kurzerklärung der einzelnen Zeilen:

```text
SelectedObjectAction(...)
└── eine von der Policy ausgewählte Aktion für genau ein Zielobjekt

target_id = "SimMachine:Machine 1.1.1:left"
└── Policy-ID der SimMachine, welche die Aktion ausführen soll

action_type = "process_machine_job"
└── die Maschine soll ihren aktuell geladenen Job bearbeiten

payload
└── Dictionary mit allen Parametern, die für die Bearbeitung benötigt werden

operation_id = "Operation 1"
└── Policy-ID der auszuführenden Operation

planned_machine_id = "Machine 1.1.1"
└── Policy-ID der Maschine, die für diese Operation eingeplant wurde

tool_type_id = "Tool Type 1"
└── Policy-ID des Werkzeugs, das die Operation benötigt

total_life_units = 25
└── maximale Standzeit eines neuen Werkzeugs dieses Typs

consumed_life_units = 10
└── Werkzeugstandzeit, die diese Bearbeitung verbraucht

remaining_life_units_before_operation = 25
└── noch vorhandene Werkzeugstandzeit vor Beginn dieser Bearbeitung

processing_speed_factor = 1.0
└── in diesem Beispiel von Evaluator und Selector gewählter Faktor

tool_setup_action = "unmount_and_mount_tool"
└── aktuelles Werkzeug demontieren und benötigtes Werkzeug montieren

target_store_id = "Machine 1.1.1 out"
└── Policy-ID des Stores, in den der Job nach der Bearbeitung gelegt wird
```

In diesem Beispiel verbleiben nach der Bearbeitung:

```text
remaining_life_units nach der Bearbeitung
= remaining_life_units_before_operation - consumed_life_units
= 25 - 10
= 15
```

Die Bridge löst die IDs in echte Simulations- und Konfigurationsobjekte auf.
Bei `SimMachine.execute_process_action()` kommt beispielsweise diese
`SimulationAction` an:

```python
SimulationAction(
    event_id="action_17",
    target=sim_machine_1_1_1,
    source_policy_trigger_id="policy_trigger_16",
    action_type="process_machine_job",
    time=42.5,
    payload={
        # Unveränderte Policy-IDs
        "operation_id": "Operation 1",
        "planned_machine_id": "Machine 1.1.1",
        "tool_type_id": "Tool Type 1",
        "target_store_id": "Machine 1.1.1 out",

        # Von der Bridge ergänzte echte Objekte
        "operation": operation_1,
        # Konfigurationsobjekt der realen SimMachine
        "planned_machine": sim_machine_1_1_1.machine,
        "tool_type": tool_type_1,
        "target_store": machine_1_1_1_store_out,

        # Für die Ausführung benötigte reine Werte
        "total_life_units": 25,
        "consumed_life_units": 10,
        "remaining_life_units_before_operation": 25,
        "processing_speed_factor": 1.0,
        "tool_setup_action": "unmount_and_mount_tool",
    },
)
```

Die äußeren Attribute bedeuten:

```text
event_id
└── eindeutige ID dieser SimulationAction

target
└── echte SimMachine, welche die Aktion ausführen soll

source_policy_trigger_id
└── PolicyTrigger, aus dessen Entscheidungszyklus die Aktion stammt

action_type
└── "process_machine_job"

time
└── Simulationszeit, zu der die Bridge die Aktion erzeugt hat

payload
└── alle Parameter für Werkzeugrüstung und Bearbeitung
```

Die Payload-Felder bedeuten:


| Payload-Key               | Konkreter Beispielwert       | Bedeutung                                                                |
| --------------------------- | ------------------------------ | -------------------------------------------------------------------------- |
| `operation_id`            | `"Operation 1"`              | Policy-ID der Operation                                                  |
| `operation`               | echtes`OperationType`-Objekt | von der Bridge aufgelöste Operation                                     |
| `planned_machine_id`      | `"Machine 1.1.1"`            | Policy-ID der geplanten Maschine                                         |
| `planned_machine`         | echtes`Machine`-Objekt       | von der Bridge aufgelöste Maschinenkonfiguration                        |
| `tool_type_id`            | `"Tool Type 1"`              | Policy-ID des benötigten Werkzeugs                                      |
| `tool_type`               | echtes`ToolType`-Objekt      | von der Bridge aufgelöster Werkzeugtyp                                  |
| `total_life_units`        | `25`                         | gesamte Standzeit eines neuen Werkzeugs                                  |
| `consumed_life_units`     | `10`                         | Verbrauch durch diese Operation                                          |
| `remaining_life_units_before_operation` | `25`                  | Standzeit vor dieser Bearbeitung                                         |
| `processing_speed_factor` | `1.0`                        | von Evaluator und Selector gewählter Bearbeitungsgeschwindigkeitsfaktor |
| `tool_setup_action`       | `"unmount_and_mount_tool"`   | altes Werkzeug demontieren und neues montieren                           |
| `target_store_id`         | `"Machine 1.1.1 out"`        | Policy-ID des Ausgangsstores                                             |
| `target_store`            | echter`sim.Store`            | Ziel für den bearbeiteten Job                                           |

Nach dem Auslesen entstehen in der Methode diese lokalen Variablen:

```python
job = self.current_job
operation = action.payload["operation"]
tool_type = action.payload["tool_type"]
total_life_units = action.payload["total_life_units"]
consumed_life_units = action.payload["consumed_life_units"]
remaining_life_units_before_operation = action.payload[
    "remaining_life_units_before_operation"
]
self.processing_speed_factor = action.payload["processing_speed_factor"]
```

Die Methode setzt voraus, dass `pick_machine_job` zuvor einen `current_job`
gesetzt hat. Diese Reihenfolge wird vom Generator, Selector, der Bridge und den
zugehörigen Tests abgesichert; `SimMachine` erzeugt dafür keinen eigenen
`ValueError`.

### Werkzeugrüstung

```text
tool_setup_action = "keep_tool"
└── aktuelles Werkzeug weiterverwenden

tool_setup_action = "unmount_dummy_tool_and_mount_tool"
└── Blindwerkzeug demontieren und erstes Bearbeitungswerkzeug montieren

tool_setup_action = "unmount_and_mount_tool"
└── altes Werkzeug demontieren und neues montieren

tool_setup_action = "replace_tool_same_type"
└── verschlissenes Werkzeug durch gleichartigen Typ ersetzen
```

Die vier Fälle decken alle aktuell vorgesehenen Kombinationen ab:


| Aktuelles Werkzeug | Richtiger Werkzeugtyp? | Standzeit ausreichend? | `tool_setup_action`                   |
| -------------------- | -----------------------: | -----------------------: | --------------------------------------- |
| Blindwerkzeug      |                     – |                     – | `"unmount_dummy_tool_and_mount_tool"` |
| vorhanden          |                   Nein |                     – | `"unmount_and_mount_tool"`            |
| vorhanden          |                     Ja |                     Ja | `"keep_tool"`                         |
| vorhanden          |                     Ja |                   Nein | `"replace_tool_same_type"`            |

### Reihenfolge der drei if-Blöcke

Die drei `if`-Blöcke werden nicht parallel ausgeführt. Python bearbeitet sie
von oben nach unten. Ein `yield self.hold(...)` unterbricht den Prozess für die
angegebene Simulationszeit. Nach dieser Zeit setzt Python die Ausführung an der
nächsten Codezeile fort und prüft anschließend den nächsten `if`-Block.

```text
1. erster if-Block
   └── gegebenenfalls Blindwerkzeug demontieren
          │
          │ yield hold(dummy_tool_unmount_time)
          ▼
2. zweiter if-Block
   └── gegebenenfalls vorhandenes Bearbeitungswerkzeug demontieren
          │
          │ yield hold(tool_type.unmount_time)
          ▼
3. dritter if-Block
   └── gegebenenfalls benötigtes Bearbeitungswerkzeug montieren
          │
          │ yield hold(tool_type.mount_time)
          ▼
   Bearbeitung fortsetzen
```

Die ersten beiden Blöcke haben keine technische Parallelität und auch keine
besondere Python-Priorität. Ihre Wirkung entsteht allein dadurch, dass sie vor
dem Montageblock stehen. Je nach Aktionswert werden bestimmte Blöcke wahr:


| `tool_setup_action`                   | 1. Blindwerkzeug demontieren | 2. Werkzeug demontieren | 3. Werkzeug montieren |
| --------------------------------------- | -----------------------------: | ------------------------: | ----------------------: |
| `"unmount_dummy_tool_and_mount_tool"` |                           Ja |                    Nein |                    Ja |
| `"unmount_and_mount_tool"`            |                         Nein |                      Ja |                    Ja |
| `"replace_tool_same_type"`            |                         Nein |                      Ja |                    Ja |
| `"keep_tool"`                         |                         Nein |                    Nein |                  Nein |

Beispiel für die erste Bearbeitung:

```text
tool_setup_action = "unmount_dummy_tool_and_mount_tool"
        ↓
erster if-Block ist True
        ↓
Blindwerkzeug demontieren und dabei Simulationszeit vergehen lassen
        ↓
zweiter if-Block ist False
        ↓
dritter if-Block ist True
        ↓
Bearbeitungswerkzeug montieren und dabei Simulationszeit vergehen lassen
```

Beispiel für einen normalen Werkzeugwechsel:

```text
tool_setup_action = "unmount_and_mount_tool"
        ↓
erster if-Block ist False
        ↓
zweiter if-Block ist True
        ↓
altes Bearbeitungswerkzeug demontieren
        ↓
dritter if-Block ist True
        ↓
neues Bearbeitungswerkzeug montieren
```

### Fortsetzung nach der Werkzeugrüstung bis zum Methodenende

Nach den drei Rüst-`if`-Blöcken läuft `execute_process_action()` sequenziell
weiter.

#### 1. Bearbeitungsdauer berechnen

```python
product = job.order.product_type
volume = product.length * product.width * product.depth
duration = operation.duration * (
    1.0
    + 0.01 * product.weight
    + 0.00005 * volume
) / self.processing_speed_factor
self.state.set("working")
```

```text
product
└── Produkttyp des aktuell geladenen Jobs

volume
└── Produktvolumen aus Länge × Breite × Tiefe

processing_speed_factor
└── beim Simulationsstart None; danach von jeder process_machine_job-Aktion gesetzt

duration
└── tatsächliche Bearbeitungsdauer aus Basisdauer, Gewicht, Volumen und Faktor

state = "working"
└── die Maschine beginnt mit der Bearbeitung
```

```text
processing_speed_factor = 0.5 → doppelte Bearbeitungsdauer
processing_speed_factor = 1.0 → normale Bearbeitungsdauer
processing_speed_factor = 2.0 → halbe Bearbeitungsdauer
```

Der `SpineActionGenerator` erzeugt alle drei Faktorvarianten. Evaluator und
Selector wählen eine davon. Der Simulationskern berechnet daraus die
tatsächliche `duration` und führt anschließend `hold(duration)` aus.

Beim Erzeugen der `SimMachine` ist noch keine Bearbeitung konfiguriert:

```python
self.processing_speed_factor: float | None = None
```

Erst beim Empfang einer `process_machine_job`-Aktion wird der enthaltene Wert
gespeichert:

```python
self.processing_speed_factor = action.payload["processing_speed_factor"]
```

Der aktuelle `SpineActionGenerator` erzeugt für jede
`process_machine_job`-Basisaktion drei Kandidaten:

```python
MACHINE_PROCESSING_SPEED_FACTORS = (0.5, 1.0, 2.0)

processing_speed_factor = 0.5
processing_speed_factor = 1.0
processing_speed_factor = 2.0
```

Der Evaluator bewertet diese Varianten und der Selector wählt eine davon aus.

#### 2. Werkzeugstandzeit für die laufende Animation vorbereiten

```python
self.remaining_life_units[tool_type] = remaining_life_units
self.remaining_life_units_t[tool_type] = self.env.now()
self.remaining_life_units_next[tool_type] = (
    remaining_life_units - consumed_life_units
)
self.remaining_life_units_next_t[tool_type] = self.env.now() + duration
```

Konkretes Beispiel:

```text
aktuelle Simulationszeit = 20
duration                 = 4
remaining_life_units     = 25
consumed_life_units      = 10

remaining_life_units[tool_type]      = 25
remaining_life_units_t[tool_type]    = 20
remaining_life_units_next[tool_type] = 15
remaining_life_units_next_t[tool_type] = 24
```

Damit kennt die Visualisierung zwei Punkte:

```text
t = 20 → Werkzeugstandzeit 25
t = 24 → Werkzeugstandzeit 15
```

Zwischen diesen Punkten wird der Life-Bar während der Bearbeitung kontinuierlich
interpoliert. `next` bezeichnet hier den geplanten Wert am Bearbeitungsende.

#### 3. Bearbeitung in Simulationszeit ausführen

```python
yield self.hold(duration)
```

Die `SimMachine` ist für `duration` Simulationsstunden im Zustand `working`
gebunden. Andere Simulationskomponenten können währenddessen ihre eigenen
Ereignisse ausführen. Nach Ablauf der Dauer wird der Maschinenprozess an der
nächsten Zeile fortgesetzt.

#### 4. Bearbeitung beenden

```python
self.state.set("returning")
```

Die eigentliche Bearbeitungszeit ist beendet. Anschließend wird entschieden,
ob die Operation einen Defekt erzeugt hat.

#### 5. Defekt oder erfolgreiche Bearbeitung bestimmen

```python
defect_severity = None

quality_key = (
    f"{self.QUALITY_SEED}|{job.scenario.name}|{job.order.name}|"
    f"{job.number}|{operation.name}|{job.rework_count}"
).encode("utf-8")

quality_rng = random.Random(
    int.from_bytes(hashlib.sha256(quality_key).digest()[:8], "big")
)

if quality_rng.random() < operation.defect_probability:
    defect_severity = quality_rng.random()

if defect_severity is not None and defect_severity >= 0.001:
    job.mark_defective(
        operation=operation,
        machine=self.machine,
        product_state_before=operation.consumes_product_type.name,
        product_state_target=operation.produces_product_type.name,
        defect_severity=defect_severity,
    )
else:
    job.processing_state.set(operation.produces_product_type.name)
    job.general_state.set("intact")
    if job.defect_recovery_strategy in {
        "rework_on_defect_machine",
        "rework_on_alternative_machine",
    }:
        job.defect_recovery_strategy = None
```

##### Was ist `QUALITY_SEED`?


```python
Seed 2, Auftrag A, Job 0, Bohren
→ erste Zufallszahl: 0.31
→ Defekt entsteht
→ zweite Zufallszahl: 0.78
→ Defektschweregrad = 0.78

Wird exakt dieselbe Simulation erneut ausgeführt, erhält dieser Job bei dieser Operation wieder das gleiche Ergebnis.

  Baseline:
Job 0 + Bohren + Seed 2 → Defekt, Schweregrad 0.78

Optimiert:
Job 0 + Bohren + Seed 2 → Defekt, Schweregrad 0.78
```

In der Klasse steht zunächst:

```python
class SimMachine(sim.Component):
    QUALITY_SEED = 0
```

Die `0` ist nur der Standardwert. `QUALITY_SEED` ist eine Klassenvariable und
kein Konstruktorparameter. Der Optimierungs-Runner setzt sie vor dem Aufbau
eines Simulationslaufs auf den gewünschten Seed:

```python
SimMachine.QUALITY_SEED = int(seed)
```

Bei `seed = 2` verwenden danach alle Maschinen dieses Laufs den Wert `2`.
Der Maschinenkonstruktor setzt ihn nicht wieder auf `0` zurück.

Der Seed verursacht selbst keinen Defekt. Er beeinflusst lediglich die
reproduzierbare Zufallszahl. Vereinfacht ist der Seed die Nummer einer
bestimmten Zufallswelt:

```text
Seed 1 → Zufallswelt 1
Seed 2 → Zufallswelt 2
Seed 3 → Zufallswelt 3
```

Beim direkten Start von `example-3.py` wird der Optimierungs-Runner nicht
verwendet. In diesem Fall bleibt der Standardwert `0` bestehen. Bei der
Optimierung setzt der Runner den Wert für jeden Seed-Lauf neu.

##### Schritt 1: Zunächst existiert kein Defekt

```python
defect_severity = None
```

`None` bedeutet hier: Bis jetzt wurde für diese Bearbeitung kein Defekt
festgestellt.

##### Schritt 2: Eindeutigen Text für diese Bearbeitung erzeugen

```python
quality_key = (
    f"{self.QUALITY_SEED}|{job.scenario.name}|{job.order.name}|"
    f"{job.number}|{operation.name}|{job.rework_count}"
).encode("utf-8")
```

Angenommen, die Werte sind:

```text
QUALITY_SEED    = 2
Szenario        = Frühschicht
Auftragsname    = Auftrag Bremsscheiben
Jobnummer       = 0
Operation       = Bohren
Nacharbeitszähler = 0
```

Dann entsteht zuerst dieser Text:

```text
2|Frühschicht|Auftrag Bremsscheiben|0|Bohren|0
```

Die Bestandteile haben folgende Aufgabe:


| Bestandteil         | Warum er enthalten ist                                          |
| --------------------- | ----------------------------------------------------------------- |
| `QUALITY_SEED`      | ermöglicht unterschiedliche, reproduzierbare Simulationsläufe |
| `job.scenario.name` | unterscheidet verschiedene Szenarien oder Schichten             |
| `job.order.name`    | unterscheidet verschiedene Aufträge                            |
| `job.number`        | unterscheidet die Jobs desselben Auftrags                       |
| `operation.name`    | unterscheidet die Bearbeitungsschritte eines Jobs               |
| `job.rework_count` | unterscheidet Erstbearbeitung und Nacharbeitsversuche       |

`encode("utf-8")` übersetzt den Text in Bytes. Das ist notwendig, weil
`hashlib.sha256(...)` Bytes und keinen normalen Python-Text verarbeitet.

##### Schritt 3: Aus dem Text eine feste Zahl erzeugen

```python
hashlib.sha256(quality_key).digest()
```

`sha256` erzeugt einen digitalen Fingerabdruck aus `quality_key`. Derselbe
Text erzeugt immer denselben Fingerabdruck. Bereits ein anderes Szenario,
eine andere Jobnummer, Operation, Nacharbeitsnummer oder ein anderer Seed
erzeugt einen anderen Fingerabdruck.

```python
hashlib.sha256(quality_key).digest()[:8]
```

`digest()` liefert 32 Bytes. `[:8]` nimmt davon die ersten acht Bytes.

```python
int.from_bytes(..., "big")
```

Diese acht Bytes werden anschließend in eine normale ganze Zahl umgewandelt.
Vereinfacht entsteht beispielsweise:

```python
928374928374
```

Die genaue Zahl ist nicht fachlich wichtig. Wichtig ist nur: Dieselben
Eingabewerte erzeugen immer dieselbe Zahl.

##### Schritt 4: Eigenen Zufallsgenerator erzeugen

```python
quality_rng = random.Random(928374928374)
```

Im echten Code wird die zuvor berechnete Zahl direkt eingesetzt:

```python
quality_rng = random.Random(
    int.from_bytes(hashlib.sha256(quality_key).digest()[:8], "big")
)
```

`quality_rng` ist ein eigener Zufallsgenerator nur für diese Kombination aus
Seed, Szenario, Auftrag, Job, Operation und Nacharbeitsnummer. Dadurch hängt
das Defektergebnis nicht davon ab, wie viele andere Zufallszahlen die
Simulation vorher verwendet hat.

##### Schritt 5: Entscheiden, ob ein Defekt entsteht

```python
if quality_rng.random() < operation.defect_probability:
```

`quality_rng.random()` liefert eine Zahl von `0.0` bis kleiner als `1.0`.
Bei einer Defektwahrscheinlichkeit von `0.50` kann beispielsweise Folgendes
passieren:

```text
Zufallszahl            = 0.31
Defektwahrscheinlichkeit = 0.50

0.31 < 0.50 → wahr → Defekt
```

Bei einer Zufallszahl von `0.83` gilt dagegen:

```text
0.83 < 0.50 → falsch → kein Defekt
```

##### Schritt 6: Defektschweregrad bestimmen

Nur wenn die erste Zufallszahl einen Defekt ausgelöst hat, wird eine zweite
Zufallszahl erzeugt:

```python
defect_severity = quality_rng.random()
```

Beispielsweise bedeutet `0.78` einen Schweregrad von 78 Prozent. Ein Wert
kleiner als `0.001` wird als nicht relevanter Defekt behandelt.

```text
erste Zufallszahl < defect_probability
├── True
│   └── zweite Zufallszahl als Defektschweregrad erzeugen
│
└── False
    └── defect_severity bleibt None

defect_severity vorhanden und mindestens 0.001?
├── Ja  → mark_defective(...) aufrufen
└── Nein → Bearbeitung erfolgreich abschließen
```

##### Vollständiges Beispiel mit echten Zahlen aus Example 3

Für dieses Beispiel gelten folgende Werte:

```text
QUALITY_SEED = 2
Szenario     = Schicht 3 – Gehaeusefertigung
Auftrag      = Gehaeuse Los A – Fraesen
Jobnummer    = 0
Operation    = Praezisionsfraesen
Nacharbeitszähler = 0 (ursprüngliche Bearbeitung)
Defektwahrscheinlichkeit der Operation = 0.45
```

Aus diesen Werten baut Python zuerst genau diesen Text:

```text
2|Schicht 3 – Gehaeusefertigung|Gehaeuse Los A – Fraesen|0|Praezisionsfraesen|0
```

`encode("utf-8")` wandelt den Text in Bytes um. SHA-256 berechnet daraus
diesen festen Fingerabdruck:

```text
7b0436b12a2d4ad358bef9dc08c331a141cfe1cf1e826d32f61fae5ef7405e8e
```

Der Code verwendet davon nur die ersten acht Bytes:

```text
7b0436b12a2d4ad3
```

`int.from_bytes(..., "big")` wandelt diese Bytes in folgende ganze Zahl um:

```text
8864270101116701395
```

Damit entspricht der Code in diesem konkreten Fall vereinfacht:

```python
quality_rng = random.Random(8864270101116701395)
```

`random.Random(...)` erzeugt einen Pseudozufallsgenerator. „Pseudozufällig“
bedeutet: Die Zahlen sehen zufällig aus, werden aber durch einen Algorithmus
vollständig aus der Startzahl berechnet. Mit derselben Startzahl entsteht
immer dieselbe Zahlenfolge.

Die erste erzeugte Pseudozufallszahl ist:

```python
erste_zahl = quality_rng.random()

# Ergebnis:
erste_zahl = 0.04504844636372318
```

Diese Zahl entscheidet über Defekt oder kein Defekt:

```text
0.04504844636372318 < 0.45
→ wahr
→ die Operation erzeugt einen Defekt
```

Weil ein Defekt entstanden ist, ruft der Code den Generator ein zweites Mal
auf:

```python
defect_severity = quality_rng.random()

# Ergebnis:
defect_severity = 0.8116138146615316
```

Der Job erhält damit einen Defektschweregrad von ungefähr `0.8116`, also
81,16 Prozent.

Der vollständige Ablauf lautet:

```text
Seed, Szenario, Auftrag, Job, Operation und Nacharbeitszähler
              │
              ▼
quality_key als Text
"2|Schicht 3 – Gehaeusefertigung|Gehaeuse Los A – Fraesen|0|Praezisionsfraesen|0"
              │
              ▼
SHA-256-Fingerabdruck
              │
              ▼
erste 8 Bytes: 7b0436b12a2d4ad3
              │
              ▼
Startzahl: 8864270101116701395
              │
              ▼
random.Random(8864270101116701395)
erzeugt das Generator-Objekt quality_rng
              │
              ▼
quality_rng speichert intern den Anfangszustand S0
              │
              ▼
1. Aufruf: quality_rng.random()
              │
              ├── verwendet den internen Zustand S0
              ├── liefert 0.04504844636372318
              └── verschiebt den Generator auf Zustand S1
              │
              ▼
Vergleich mit der Defektwahrscheinlichkeit
0.04504844636372318 < 0.45
              │
              ├── Nein → kein Defekt
              │          defect_severity bleibt None
              │          kein zweiter .random()-Aufruf
              │
              └── Ja → Defekt
                       │
                       ▼
              2. Aufruf: quality_rng.random()
                       │
                       ├── verwendet den internen Zustand S1
                       ├── liefert die nächste Zahl 0.8116138146615316
                       └── verschiebt den Generator auf Zustand S2
                       │
                       ▼
              defect_severity = 0.8116138146615316
              Defektschweregrad ungefähr 81,16 %
```

Die Aufrufe `quality_rng.random()` benötigen keinen Seed als Argument. Der
Seed wurde bereits beim Erzeugen von `quality_rng` übergeben und steckt danach
im internen Zustand des Generator-Objekts:

```python
# Hier wird der Generator einmal mit seiner Startzahl initialisiert:
quality_rng = random.Random(8864270101116701395)

# Diese Aufrufe holen nur noch nacheinander Zahlen aus diesem Generator:
erste_zahl = quality_rng.random()
zweite_zahl = quality_rng.random()
```

Wird ein neuer Generator mit derselben Startzahl konstruiert, beginnt er
wieder bei demselben Zustand `S0`:

```text
neuer random.Random(8864270101116701395)
→ Zustand S0
→ erster Aufruf liefert wieder 0.04504844636372318
→ zweiter Aufruf liefert wieder 0.8116138146615316
```

Wird dieselbe Kombination erneut ausgeführt, entstehen wieder genau
`0.04504844636372318` und `0.8116138146615316`. Wird beispielsweise der Seed,
das Szenario, die Jobnummer oder `rework_count` geändert, entsteht ein
anderer Fingerabdruck und damit eine andere Pseudozufallsfolge.

Falls die erste Zahl größer oder gleich `0.45` wäre, entstünde kein Defekt.
Dann würde der Code die zweite Zahl für den Defektschweregrad überhaupt nicht
abrufen und `defect_severity` bliebe `None`.

##### Warum wird das so gemacht?

Bei einem fairen Vergleich sollen Baseline und optimierte Steuerung für
dasselbe Szenario, denselben Job, dieselbe Operation und denselben
Nacharbeitsversuch dasselbe Defektergebnis erhalten. Deshalb wird die
Zufallszahl aus festen Informationen berechnet.

```text
gleicher Seed + gleiches Szenario + gleicher Auftrag
+ gleiche Jobnummer + gleiche Operation + gleicher Nacharbeitszähler
→ gleicher quality_key
→ gleiche Zufallszahlen
→ gleiches Defektergebnis
```

Ändert sich einer dieser Werte, entsteht eine andere Zufallsfolge:

```text
anderer Seed       → wahrscheinlich anderes Defektergebnis
anderes Szenario   → wahrscheinlich anderes Defektergebnis
andere Jobnummer   → wahrscheinlich anderes Defektergebnis
andere Operation   → wahrscheinlich anderes Defektergebnis
anderer Nacharbeitszähler → wahrscheinlich anderes Defektergebnis
```

Damit erhält die ursprüngliche Bearbeitung mit `rework_count = 0` eine
andere reproduzierbare Zufallsfolge als der erste Nacharbeitsversuch mit
`rework_count = 1`. Ein weiterer Versuch mit `rework_count = 2`
erhält wieder eine andere Folge. Es gibt dadurch keine feste Begrenzung der
Nacharbeitsanzahl; weiterhin entscheidet der jeweils neu erzeugte
Defektschweregrad, ob eine weitere Nacharbeit technisch möglich ist.

Der Maschinenname steht absichtlich nicht in `quality_key`. Damit verändert
die Auswahl einer anderen technisch geeigneten Maschine nicht plötzlich das
Defektergebnis derselben Job-Operation. So wird der Vergleich der
Steuerungsgewichte fairer.

#### 6. Abgearbeitete Planung aus dem Job entfernen

```python
job.selected_operation = None
job.selected_machine = None
```

Die gerade ausgeführte Operation und Maschine sind nicht mehr die nächsten
geplanten Schritte. Für eine weitere Bearbeitung kann die Policy später eine
neue Operation und Maschine bestimmen.

#### 7. Werkzeugstandzeit endgültig speichern

```python
self.remaining_life_units[tool_type] = (
    remaining_life_units - consumed_life_units
)
self.remaining_life_units_t[tool_type] = self.env.now()
self.remaining_life_units_next[tool_type] = (
    remaining_life_units - consumed_life_units
)
self.remaining_life_units_next_t[tool_type] = self.env.now()
```

Nach dem Bearbeitungsende sind aktueller und geplanter Wert identisch:

```text
vor der Bearbeitung = 25
Verbrauch            = 10
nach der Bearbeitung = 15

remaining_life_units      = 15
remaining_life_units_next = 15

ohne next → aktueller, tatsächlich erreichter Wert
mit next  → geplanter Zielwert für die Animation
```

Auch beide Zeitstempel entsprechen nun der aktuellen Simulationszeit. Damit
endet die Interpolation des Life-Bars exakt beim endgültigen Wert.

#### 8. Job in den Ausgangs-Store legen

```python
yield self.to_store(
    action.payload["target_store"],
    job,
    priority=job.queue_priority,
)
```

Der bearbeitete Job wird in den echten, von der Bridge aufgelösten
Maschinen-Ausgangs-Store gelegt. `yield` wartet, bis die Store-Anforderung
erfolgreich ausgeführt werden kann. Die `queue_priority` bestimmt seine
Priorität im Store.

#### 9. Maschine intern entladen

```python
self.current_job = None
```

Die Maschine enthält danach keinen Job mehr. `execute_process_action()` endet,
der Maschinenprozess kehrt zu seiner `while True`-Schleife zurück und fordert
bei der Bridge die nächste Aktion an.

Gesamtablauf:

```text
Werkzeugrüstung
    ↓
Bearbeitungsdauer berechnen
    ↓
Life-Bar-Zielwerte vorbereiten
    ↓
yield hold(duration)
    ↓
Defekt oder Erfolg bestimmen
    ↓
selected_operation und selected_machine zurücksetzen
    ↓
endgültige Werkzeugstandzeit speichern
    ↓
Job in target_store legen
    ↓
current_job = None
    ↓
neue Aktion bei der Bridge anfordern
```

### Blindwerkzeug am Anfang und Ende der Simulation

Die Werkzeugaufnahme befindet sich außerhalb der Produktion nie dauerhaft
ohne Einsatz. Ein Blindwerkzeug schützt die unbenutzte Werkzeugaufnahme.

```text
Simulationsanfang
└── dummy_tool_mounted = True
    └── Blindwerkzeug ist montiert

erste Bearbeitung
├── state = "unmounting"
├── Blindwerkzeug demontieren
├── state = "mounting"
└── erstes Bearbeitungswerkzeug montieren

während der Produktion
├── Bearbeitungswerkzeug beibehalten oder
└── Bearbeitungswerkzeug wechseln

natürliches Simulationsende
├── letztes Bearbeitungswerkzeug demontieren
├── Blindwerkzeug montieren
└── dummy_tool_mounted = True
```

Die Zeiten sind fest in jeder Maschinenkonfiguration hinterlegt:

```python
self.dummy_tool_mount_time = 1.0
self.dummy_tool_unmount_time = 1.0
```

Da die Simulation Stunden als Zeiteinheit verwendet, dauern sowohl die Montage
als auch die Demontage des Blindwerkzeugs jeweils eine Simulationsstunde. Diese
Werte müssen beim Erzeugen einer `Machine` nicht als Parameter angegeben werden.

Montage- und Demontagezeiten werden mit `yield hold(...)` als Simulationszeit
abgebildet.

## Zustandsfolge einer typischen Bearbeitung

```text
waiting
→ optional unmounting
→ optional mounting
→ working
→ returning
→ Corridor-Arm holt Job aus store_out
→ waiting
```

Das Zurücksetzen auf `waiting` erfolgt beim Abholen des Jobs durch
`SimRobotCorridorArm.execute_pick_action()`.

## utilization()

```text
working-Zeit
─────────────────────────────────────────────────────────────────────────────────────────────────────
waiting + mounting + unmounting + working + returning
```

Falls noch keine Zustandsdauer vorhanden ist, liefert die Methode aktuell `1`.

## Entkopplungsgrenze

```text
Policy
└── sieht Maschinen-ID, Zustandsdaten, Werkzeug-IDs und Store-Daten
    │
    ▼
SimulationBridge
└── löst Maschinen-, Job-, Store-, Operations- und Werkzeug-IDs auf
    │
    ▼
SimMachine
└── führt die Operation mit echten Laufzeit- und Konfigurationsobjekten aus
```
