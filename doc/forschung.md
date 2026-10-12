# Forschungsrichtung für SpineML

## Heuristik, Greedy und Dispatching Rules

Die Begriffe werden in dieser Reihenfolge betrachtet:

```text
Heuristik
    ↓
lokale Bewertungsfunktion und greedy Auswahl
    ↓
Dispatching Rules als konkrete lokale Auswahlheuristiken
    ↓
Anwendung in SpineML
```

## Was ist eine Heuristik?

Eine Heuristik ist ein Verfahren, das mit vertretbarem Rechenaufwand schnell
eine brauchbare Entscheidung oder Lösung erzeugt. Sie garantiert nicht, die
mathematisch global optimale Lösung zu finden.

Für SpineML müssen vier Begriffe unterschieden werden:

```text
1. Aktionsraum
2. lokale heuristische Bewertungsfunktion
3. lokale greedy Auswahl
4. globale Zielfunktion
```

### Beispielzustand

Eine Maschine ist frei und drei Jobs warten:

| Job | Bearbeitungszeit | Deadline |
|---|---:|---:|
| A | 8 min | 14:00 |
| B | 2 min | 16:00 |
| C | 5 min | 13:00 |

### 1. Aktionsraum

Der Aktionsraum beschreibt:

> Welche Aktionen dürfen im aktuellen Zustand überhaupt ausgewählt und
> ausgeführt werden?

Sind alle drei Jobs verfügbar, gilt:

$$
A(s)=\{\text{Job A wählen},\text{Job B wählen},\text{Job C wählen}\}
$$

Ist Job C noch nicht verfügbar, gilt:

$$
A(s)=\{\text{Job A wählen},\text{Job B wählen}\}
$$

Die Heuristik darf nur Aktionen aus dem aktuellen Aktionsraum auswählen.

```text
PolicyObservation mit aktuellem Zustand s
        ↓
SpineActionGenerator
        ↓
technisch mögliche Aktionen A(s)
```

### 2. Lokale heuristische Bewertungsfunktion

Die lokale Bewertungsfunktion bewertet jeden Kandidaten des aktuellen
Aktionsraums:

$$
h(s,a)
$$

```text
s      = aktueller Simulationszustand
a      = eine aktuell mögliche Aktion
h(s,a) = lokale Bewertung dieser Aktion in diesem Zustand
```

Bei SPT kann sie der Bearbeitungszeit entsprechen:

$$
h(s,a)=\text{Bearbeitungszeit des durch Aktion }a\text{ gewählten Jobs}
$$

Sie wird auf alle aktuell möglichen Aktionen angewendet:

```text
Job A auswählen → h(s,A) = 8
Job B auswählen → h(s,B) = 2
Job C auswählen → h(s,C) = 5
```

Da bei SPT der kleinste Wert besser ist:

$$
a^*=\arg\min_{a\in A(s)}h(s,a)=B
$$

SpineML maximiert dagegen einen Score. Eine zu minimierende Bearbeitungszeit
kann deshalb negiert werden:

$$
\operatorname{score}(s,a)=-h(s,a)
$$

Eine lokale Bewertungsfunktion kann mehrere Kriterien unterschiedlich
gewichten:

$$
h_{\mathbf w}(s,a)
=
w_1h_1(s,a)+w_2h_2(s,a)+\dots+w_nh_n(s,a)
$$

```text
lokaler Aktionsscore
├── Jobpriorität
├── erwartete Bearbeitungszeit
├── erwartete Transportzeit
├── Deadline-Risiko
├── Werkzeugwechsel
└── freie Kapazität des Ziel-Stores
```

Der `LocalHeuristicActionEvaluator` berechnet den lokalen Score jedes Kandidaten.
Der `BaselineActionSelector` wählt anschließend den Kandidaten mit dem
höchsten Score.

### 3. Lokale greedy Auswahl

In jedem Entscheidungszyklus wird gewählt:

$$
a^*=\arg\max_{a\in A(s)}\operatorname{score}(s,a)
$$

```text
aktueller Aktionsraum
├── Aktion A → Score 72
├── Aktion B → Score 91
└── Aktion C → Score 65
        ↓
Aktion B wird unmittelbar ausgewählt
```

Nach der Ausführung entsteht ein neuer Simulationszustand. Beim nächsten
Ereignis werden ein neuer Aktionsraum und neue lokale Bewertungen erzeugt.

### 4. Globale Zielfunktion

Die globale Zielfunktion bewertet das Ergebnis der gesamten Folge lokaler
Entscheidungen über einen vollständigen Simulationslauf.

```text
globale Kennzahlen
├── Makespan
├── Gesamtverspätung
├── durchschnittliche Durchlaufzeit
├── gesamte Transportzeit
├── Werkzeugwechsel
├── Energieverbrauch
├── Blockierungszeit
└── Nacharbeits- und Ausschusskosten
```

Sie kann mehrere globale Kennzahlen unterschiedlich gewichten:

$$
Z=v_1Z_1+v_2Z_2+\dots+v_mZ_m
$$

Zum Beispiel:

$$
Z=
5\cdot\text{Gesamtverspätung}
+2\cdot\text{Makespan}
+1\cdot\text{gesamte Transportzeit}
$$

Bei einer Minimierungsaufgabe ist ein kleinerer Wert von $Z$ besser.

### Lokale Bewertung und globale Zielfunktion

```text
lokale Bewertungsfunktion h_w(s,a)
└── bewertet eine aktuell mögliche Aktion
        ↓
Selector wählt eine Aktion
        ↓
Simulation führt sie aus
        ↓
neuer Zustand und weitere lokale Entscheidungen
        ↓
Simulation beendet
        ↓
globale Zielfunktion Z
└── bewertet alle Entscheidungen zusammen
```

- Die lokale Bewertungsfunktion steuert die Entscheidungen während der
  Simulation.
- Die globale Zielfunktion misst nach dem Lauf die Qualität der gesamten
  entstandenen Lösung.
- Die lokalen Kriterien und Gewichte werden so gestaltet, dass die wiederholten
  lokalen Entscheidungen möglichst gute globale Ergebnisse erzeugen.

### Äußere Optimierungsschleife für lokale Gewichte

Sollen die lokalen Gewichte automatisch verbessert werden, wird eine äußere
Schleife um vollständige Simulationsläufe benötigt:

```text
lokale Gewichte w festlegen
        ↓
vollständige Simulation starten
        ↓
bei jedem Entscheidungszyklus:
├── Aktionsraum erzeugen
├── Kandidaten mit h_w(s,a) bewerten
└── lokal greedy die beste Aktion auswählen
        ↓
Simulation beendet
        ↓
globale Zielfunktion Z(w) berechnen
        ↓
Gewichte verändern
        ↓
nächsten vollständigen Simulationslauf starten
```

Der äußere Optimierer sucht:

$$
\mathbf w^*=\arg\min_{\mathbf w}Z(\mathbf w)
$$

| Lauf | Gewicht Priorität | Gewicht Transportzeit | globale Kosten $Z$ |
|---|---:|---:|---:|
| 1 | 1 | 1 | 520 |
| 2 | 3 | 1 | 430 |
| 3 | 3 | 2 | 390 |

Bei einer Minimierung liefert Lauf 3 bisher das beste Ergebnis.

Die Gewichte werden nicht vom `ActionSelector` selbst verbessert. Dafür ist
ein äußerer Optimierer erforderlich, beispielsweise Grid Search, Random Search,
Bayesian Optimization oder ein genetischer Algorithmus.

Enthält die Simulation Zufall, sollte derselbe Gewichtsvektor mit mehreren
Zufalls-Seeds getestet und über den durchschnittlichen globalen
Zielfunktionswert verglichen werden.

## Was bedeutet greedy?

Greedy bedeutet:

> Bei jedem Entscheidungsschritt wird die lokal beste aktuell verfügbare
> Aktion gewählt, ohne alle zukünftigen Konsequenzen vollständig zu
> untersuchen.

Für die drei Jobs mit den Bearbeitungszeiten 8, 3 und 5 wählt SPT den Job mit
der Bearbeitungszeit 3. Das ist eine greedy Entscheidung, weil unmittelbar der
momentan beste Kandidat gewählt wird.

### Greedy in der SpineML-Architektur

```text
PolicyObservation mit aktuellem Zustand
        ↓
SpineActionGenerator
└── erzeugt alle momentan technisch möglichen Aktionen
        ↓
LocalHeuristicActionEvaluator
└── berechnet für jeden Kandidaten einen Score
        ↓
BaselineActionSelector
└── wählt den Kandidaten mit dem höchsten Score
        ↓
PolicyDecision
        ↓
SimulationBridge und Simulationskern
```

## Was sind Dispatching Rules?

Dispatching Rules sind konkrete lokale Auswahlregeln:

> Welcher der aktuell verfügbaren Jobs soll als Nächstes bearbeitet werden?

```text
Aktionsraum
└── Welche Jobs können jetzt ausgewählt werden?
        ↓
Dispatching Rule
└── Nach welcher Regel wird einer davon ausgewählt?
        ↓
eine ausgewählte Aktion
```

### Konkretes Beispiel

| Job | Bearbeitungszeit | Deadline | Ankunftsreihenfolge |
|---|---:|---:|---:|
| A | 10 min | 14:00 | 1 |
| B | 3 min | 16:00 | 2 |
| C | 6 min | 13:00 | 3 |

| Dispatching Rule | Entscheidung |
|---|---|
| FIFO | Job A, weil er zuerst angekommen ist |
| SPT | Job B, weil er die kürzeste Bearbeitungszeit besitzt |
| EDD | Job C, weil er die früheste Deadline besitzt |
| Highest Priority First | Job mit der höchsten `queue_priority` |
| Least Slack Time | Job mit dem kleinsten Zeitpuffer |

### FIFO

```text
First In, First Out
└── Der zuerst eingetroffene Job wird zuerst ausgewählt.
```

### SPT

```text
Shortest Processing Time
└── Der Job mit der kürzesten erwarteten Bearbeitungszeit wird ausgewählt.
```

### EDD

```text
Earliest Due Date
└── Der Job mit der frühesten Deadline wird ausgewählt.
```

### Highest Priority First

```text
Alle verfügbaren Jobs vergleichen
└── Job mit der höchsten queue_priority auswählen.
```

### Least Slack Time

```text
Slack = Deadline - aktuelle Zeit - verbleibende Bearbeitungs- und Transportzeit
```

Der Job mit dem kleinsten Slack besitzt den geringsten zeitlichen Spielraum.

### Warum sind Dispatching Rules Heuristiken?

Dispatching Rules berechnen nicht den vollständigen Produktionsplan und
probieren nicht alle möglichen Reihenfolgen aus. Sie wenden bei jedem
Entscheidungszeitpunkt eine lokale Regel auf die aktuell verfügbaren Jobs an.

```text
Heuristik
└── greedy Online-Aktionsauswahl
    └── mögliche Dispatching Rule
        ├── FIFO
        ├── SPT
        ├── EDD
        ├── Highest Priority First
        └── Least Slack Time
```

## Verbindung zu SpineML

```text
PolicyObservation
└── aktueller dynamischer Zustand und Konfigurationsmodell
        ↓
SpineActionGenerator
└── technisch mögliche Aktionen A(s)
        ↓
LocalHeuristicActionEvaluator
└── lokale Heuristik oder Dispatching Rule als Aktionsscore
        ↓
BaselineActionSelector
└── lokal greedy den höchsten Score auswählen
        ↓
PolicyDecision
        ↓
SimulationBridge
└── ID-basierte Aktion in eine ausführbare SimulationAction umwandeln
```

Dispatching Rules sind ein sinnvoller erster Vergleichsmaßstab. Anschließend
können mehrere lokale Kriterien gewichtet und die Gewichte anhand der globalen
Zielfunktion über vollständige Simulationsläufe verbessert werden.

## Literaturhinweise

- Flexible Job-Shop Scheduling mit Transportressourcen:
  https://doi.org/10.1016/j.ejor.2023.07.036
- Flexible Job-Shop Scheduling mit mehreren Transportrobotern:
  https://doi.org/10.1016/j.cie.2016.02.024
- Genetischer Algorithmus und Dispatching Rules bei Robotertransport:
  https://doi.org/10.1016/j.ifacol.2024.09.226

