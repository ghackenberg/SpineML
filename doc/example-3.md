# Example 3 – Erklärung des Fabrikmodells

Die Datei `sources/examples/normal/example-3.py` beschreibt eine Gehäusefertigungs-Schicht.
Sie erstellt das Modell und startet beim direkten Aufruf die Visualisierung.
Die Optimierung wird separat über `optimization.py` gestartet. Der frühere
Starter `sources/examples/optimization/example-3-optimize.py` bleibt als
Kompatibilitätsstarter bestehen.

```text
Maschinentypen und Werkzeuge
→ Produkte und Operationen
→ ein Szenario und seine Aufträge
→ ein Layout und seine Korridore
→ Maschinen
```

## 1. Importe

```python
import salabim as sim
from SpineML import *
```

`salabim` stellt die Simulationsumgebung bereit. `SpineML` macht die Modellklassen `MachineType`,
`ToolType`, `ProductType`,
`OperationType`, `Scenario`, `Order`, `Layout`, `Corridor` und `Machine`
verfügbar.

## 2. Typen erstellen

```python
mt1 = MachineType('Grundbearbeitungszentrum')
tt1 = ToolType('Fräswerkzeug', 2, 3, 10)
pt1 = ProductType('Rohling Typ A', 12, 12, 12, 5)
```

Maschinentypen haben nur einen Namen. Werkzeuge besitzen Montagezeit,
Demontagezeit und Lebensdauer. Produkte besitzen Länge, Breite, Tiefe und
Gewicht. Die übrigen Typen werden analog angelegt.

## 3. Operationen

```python
OperationType('Grundbearbeitung Rohling A', 2, 4, 0.50, mt1, tt1, pt1, pt2)
```

Eine Operation beschreibt Bearbeitungsdauer, Werkzeugverbrauch,
Defektwahrscheinlichkeit, benötigte Maschinentype, Werkzeug sowie Eingangs-
und Ausgangsprodukt. Maschinen fallen nicht aus; nur Produkte können bei der
Bearbeitung defekt werden.

## 4. Szenario und Aufträge

```python
s3 = Scenario('Schicht 3 – Gehäusefertigung')
o3_1 = Order("Gehäuse Los A – Fräsen", 2, 15, 650, pt4, s3)
```

Ein Auftrag enthält Name, Menge, frühesten Start, Deadline, Produkttyp und
Szenario. Alle vier Aufträge haben direkt die Menge `2`, also insgesamt acht
Jobs. Tardiness wird pro Auftrag anhand des spätesten fertigen Jobs berechnet,
nicht für jeden Job einzeln.

## 5. Layout und Korridore

```python
l3 = Layout('Layout 3', 11, 3, 1000)
c3_1 = Corridor("Corridor 3.1", 2, 3, 6, l3)
```

Example 3 verwendet ein Layout mit zwei Korridoren. Korridore gehören zu einem
Layout und haben eigene Kapazitäten sowie Ein- und Auslagerungszeiten.
Begrenzte Kapazitäten können Staus und Blockierungen erzeugen.

## 6. Maschinen

```python
Machine('Machine 3.1.1', mt1, c3_1, True, 10)
```

Example 3 verwendet acht Maschinen, vier pro Korridor. Eine Maschine erhält
Name, Maschinentyp, Korridor, Seite und Eingangskapazität. Jede Maschine
bearbeitet nur einen Job gleichzeitig. Mehrere Maschinen desselben Typs bieten
alternative Entscheidungen für die Heuristik oder RL-Policy.

Die Ausgangskapazität kann separat angegeben werden. Die Policy darf diese
Kapazitäten und die festen Geschwindigkeiten nicht verändern.

## 7. Direkter Start

```python
if __name__ == "__main__":
    simulate(l3, s3, till=sim.inf, animation_speed=1)
```

Dieser Block läuft nur, wenn `example-3.py` direkt gestartet wird. Beim Laden
durch `optimization.py` werden nur die Modellobjekte geladen; die eigentliche
Simulation startet erst über den headless Runner.
Der Lauf endet automatisch, sobald alle Jobs vollständig verarbeitet oder als
Ausschuss abgeschlossen sind. Die interaktive Optimierung verwendet denselben
Modellumfang und ebenfalls die Completion-Bedingung.

## Zusammenfassung

## Aktuelle vollständige Konfiguration

### Importe

```python
import salabim as sim
```

`sim.inf` bedeutet: bis zum regulären Ende der Simulation laufen.

### Parameterübersicht

```text
MachineType: Name
ToolType: Name, Montagezeit, Demontagezeit, Werkzeuglebensdauer
ProductType: Name, Länge, Breite, Tiefe, Gewicht
OperationType: Name, Dauer, Werkzeugverbrauch, Defektwahrscheinlichkeit,
               Maschinentyp, Werkzeugtyp, Eingangsprodukt, Ausgangsprodukt
Scenario: Name
Order: Name, Menge, frühester Start, spätestes Ende, Produkt, Szenario
Layout: Name, Auslagerungszeit, Einlagerungszeit, Lagerkapazität
Corridor: Name, Kapazität, Auslagerungszeit, Einlagerungszeit, Layout
Machine: Name, Maschinentyp, Korridor, linke Seite, Eingangskapazität
```

Die Aufträge `o3_1` bis `o3_4` haben jeweils die Menge `2`; zusammen sind es
acht Jobs. Die Layout-Kapazität `1000` gilt für Start- und Endlager. Die
Korridorkapazität `2` gilt für die Stores des jeweiligen Korridors.

### Maschinenfaktoren

Der Faktor wird direkt in `SimMachine` zufällig aus
`[0.45, 0.70, 1.00, 1.50, 2.00]` gewählt. Da der Optimierungsrunner den
Zufallsseed vor dem Aufbau des Simulationskerns setzt, erhalten Baseline und
optimierte Steuerung bei demselben Seed dieselben Maschinenfaktoren. Der Faktor
beeinflusst die echte Bearbeitungsdauer und damit Makespan, Tardiness und
Blockierung.

### Globale Ziele

| Faktor | Zielkennzahl |
|---|---|
| Operationsdauer und Maschinengeschwindigkeit | Makespan, Tardiness |
| Korridor- und Maschinenpuffer | Blockierungszeit, Makespan |
| Lager- und Transportzeiten | Transportzeit, Makespan |
| Werkzeugmontage und -verbrauch | Werkzeugwechselzeit |
| Defektwahrscheinlichkeit | Defektquote |
| Nacharbeit, Herabstufung, Ausschuss | Nacharbeits- und Ausschussquote |
| Deadline | Tardiness |

Die Optimierung sollte zuerst vollständige Jobs sicherstellen, danach Makespan
und Tardiness minimieren und anschließend Qualität sowie Nebenzeiten verbessern.
Die Defektquote bleibt bei gleichen Seeds vergleichbar; direkt veränderbar sind
vor allem die Entscheidungen nach einem Defekt.

## Reale Bezeichnungen und Produktionspfade

Die Variablen `pt1` bis `pt6` sind technische IDs. Für die fachliche Erklärung
können sie so gelesen werden:

| Technische ID | Reale Bezeichnung |
|---|---|
| `pt1` | Rohling Typ A |
| `pt2` | Bearbeiteter Grundkörper |
| `pt3` | Rohling Typ B |
| `pt4` | Gefrästes Gehäuse |
| `pt5` | Bohrbearbeitetes Gehäuse |
| `pt6` | Poliertes Fertigteil |

Die fünf Operationen bilden folgende Pfade:

```text
pt1 Rohling Typ A
  └─ Grundbearbeitung Rohling A ─→ pt2 Bearbeiteter Grundkörper

pt3 Rohling Typ B
  └─ Grundbearbeitung Rohling B ─→ pt2 Bearbeiteter Grundkörper

pt2 Bearbeiteter Grundkörper
  ├─ Präzisionsfräsen ─→ pt4 Gefrästes Gehäuse
  ├─ Präzisionsbohren ─→ pt5 Bohrbearbeitetes Gehäuse
  └─ Endpolitur       ─→ pt6 Poliertes Fertigteil
```

Für die vier Aufträge ergibt sich damit:

```text
Auftrag 3.1: pt2 → Operation 3 → pt4
Auftrag 3.2: pt2 → Operation 4 → pt5
Auftrag 3.3: pt2 → Operation 5 → pt6
Auftrag 3.4: pt2 → bereits gewünschtes Produkt
```

`Scenario 3` kann fachlich als `Schicht 3` verstanden werden: eine gemeinsame
Produktionsschicht mit diesen vier Aufträgen, gemeinsamen Ressourcen und
gemeinsamen Deadlines.

```text
example-3.py          = Fabrikmodell
optimization.py = allgemeiner Optimierungsablauf für alle Examples
Simulationskern       = führt gewählte Aktionen aus
```
