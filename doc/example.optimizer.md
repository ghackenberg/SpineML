# Example-Optimierung

Python-Datei: **sources/examples/optimization/example-0-optimize.py**

> Hinweis: Die Optimierungslogik liegt inzwischen zentral in
> **sources/optimization.py**. Dieses Dokument beschreibt ältere Example-0-
> Details. Für den aktuellen Ablauf und die Auswahl beliebiger Examples siehe
> [optimization.md](optimization.md).

## Aufgabe

Diese Datei verwendet die Fabrikkonfiguration aus Example 0 für eine
automatische Suche nach besseren lokalen Heuristik-Gewichten.

Sie öffnet keine 3D-Visualisierung, weil viele vollständige Simulationen
nacheinander ausgeführt werden.

## Heuristik, Nebenbedingungen und Zielfunktion im Projekt

Eine **Heuristik** ist eine **praktische Näherungsregel**.

Zum Beispiel ist **SPT (Shortest Processing Time)** eine solche einfache Regel:

> **Bearbeite den Job mit der kürzesten Bearbeitungszeit zuerst.**

Du löst dabei  **nicht das gesamte Optimierungsproblem mathematisch optimal** . Stattdessen verwendest du eine einfache Regel, die häufig schnell zu einer guten Lösung führt.

Sie bewertet eine
aktuell mögliche Aktion schnell, ohne alle zukünftigen Produktionsabläufe zu
berechnen. Beispiele sind EDD für dringende Jobs, SPT für kurze Operationen
oder eine Bewertung kurzer Transportwege. Eine Heuristik liefert deshalb eine
gute Entscheidungsrichtung, garantiert aber kein global optimales Ergebnis.

Für die Optimierung arbeiten im Projekt vier Teile zusammen:

```text
ActionGenerator
    → wendet technische Nebenbedingungen an
    → erzeugt nur technisch mögliche Aktionskandidaten

LocalHeuristicActionEvaluator
    → wendet lokale heuristische Bewertungsregeln an
    → gibt jeder möglichen Aktion einen lokalen Score

GlobalSimulationEvaluation
    → wendet die globale Zielfunktion an
    → bewertet das Ergebnis eines vollständigen Simulationslaufs

LocalHeuristicWeightOptimizer
    → verändert lokale HeuristicWeights
    → führt Läufe aus und vergleicht ihre globalen Zielfunktionswerte
```

Die `GlobalSimulationWeights` werden dabei nicht verändert. Sie bleiben während
der Optimierung konstant und legen fest, wie wichtig die globalen Ergebnisse
eines vollständigen Simulationslaufs sind, zum Beispiel Verspätung gegenüber
Transportzeit. Der Optimierer verändert nur die lokalen Gewichte, führt die
Simulation aus und berechnet anschließend mit den festen globalen Gewichten
den Vergleichswert. Ändert man die globalen Gewichte, erhält man somit eine
andere Zielfunktion und muss die lokalen Gewichte erneut bewerten.

### Herkunft der globalen Gewichte

Für dieses Beispiel werden die globalen Gewichte als feste fachliche Vorgaben
angenommen. Sie werden nicht durch den `LocalHeuristicWeightOptimizer` gelernt,
sondern beispielsweise von der Produktionsleitung, dem Controlling, der
Logistik oder dem Qualitätsmanagement festgelegt. Damit wird ausgedrückt,
welche globalen Unternehmensziele wichtiger sind, etwa Termintreue gegenüber
Transportkosten. Der Optimierer sucht anschließend lokale Aktionsgewichte,
die unter diesen festgelegten Unternehmenszielen gute Simulationsergebnisse
erzeugen.

### Nebenbedingungen

Nebenbedingungen legen fest, welche Aktionen überhaupt zulässig sind. Sie sind
vor allem in
`sources/SpineML/Control/GeneralControl/ActionGenerators.py` zu finden. Beispiele:

```text
keine freie Store-Kapazität
    → keine Place-Aktion erzeugen

keine gültige Maschinenroute
    → keine Route beziehungsweise keine Place-Aktion erzeugen

Maschine nicht verfügbar
    → keine Nacharbeitsaktion auf dieser Maschine erzeugen

technisch nicht nacharbeitbarer Defekt
    → nur Ausschuss oder Warten erzeugen
```

Die Nacharbeitsgrenze wird zusätzlich über
`is_nacharbeit_allowed(...)` geprüft. Das ist die zeitliche und wirtschaftliche
Nebenbedingung für Nacharbeit.

### Zielfunktionen

Die globale Zielfunktion befindet sich in
`sources/SpineML/Control/HeuristicControl/GlobalSimulationEvaluation.py`.
Sie kombiniert Kennzahlen des vollständigen Simulationslaufs:

```text
globale Kosten
= makespan × Gewicht
 + Verspätung × Gewicht
 + Transportzeit × Gewicht
 + Werkzeugwechsel × Gewicht
 + Blockierungszeit × Gewicht
 + Nacharbeitskosten × Gewicht
 + Ausschusskosten × Gewicht
 + unfertige Jobs × Gewicht
```

Die Optimierung minimiert diesen Wert. Ein kleinerer globaler Wert bedeutet,
dass der komplette Simulationslauf nach den festgelegten Unternehmenszielen
besser war. Die lokalen Heuristiken entscheiden also einzelne Aktionen; die
globale Zielfunktion beurteilt anschließend die Gesamtwirkung dieser vielen
Entscheidungen.

### Globale Kennzahlen und Herkunft ihrer Gewichte


| Kennzahl               | Was wird gemessen?                                                                   | Typische fachliche Herkunft des Gewichts                                  |
| ------------------------ | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `makespan`             | Verstrichene Zeit vom frühesten Auftragsstart bis zum letzten abgeschlossenen Job | Produktionsleitung: Durchlaufzeit und Kapazitätsauslastung               |
| `total_tardiness`      | Summe aller Überschreitungen der Job-Deadlines                                      | Produktionsplanung und Kunden-/Auftragsmanagement: Termintreue            |
| `total_transport_time` | Gesamte Zeit aller Roboter- und Materialtransporte                                   | Logistik und Fabrikplanung: kurze Materialwege                            |
| `tool_change_time`     | Gesamte Zeit für Werkzeugwechsel an Maschinen                                       | Produktionsleitung und Instandhaltung: weniger Rüst- und Wechselzeit     |
| `blocking_time`        | Zeit, in der Maschinen wegen blockierter Ein-/Ausgänge nicht weiterarbeiten können | Produktionsleitung: Vermeidung von Stillstand und Blockierung             |
| `rework_job_count` | Anzahl der Jobs mit Nacharbeitsstrategie                                            | Qualitätsmanagement und Controlling: Nacharbeitsaufwand begrenzen        |
| `scrap_job_count`  | Anzahl der als Ausschuss verworfenen Jobs                                           | Qualitätsmanagement und Controlling: Material- und Wertverlust vermeiden |
| `unfinished_jobs`      | Anzahl der Jobs, die am Simulationsende nicht fertig sind                            | Produktionsleitung: vollständige Auftragserfüllung sicherstellen        |

Die Abteilungen liefern also die fachliche Priorität. Diese Priorität wird als
`GlobalSimulationWeights` ausgedrückt. Ein höheres Gewicht bedeutet, dass eine
zusätzliche Einheit dieser Kennzahl die globalen Kosten stärker erhöht.

Beispiel:

```text
GlobalSimulationWeights.total_tardiness = 5.0
GlobalSimulationWeights.total_transport_time = 1.0
```

Eine zusätzliche Zeiteinheit Verspätung zählt damit fünfmal so stark wie eine
zusätzliche Zeiteinheit Transportzeit. Die Werte sind feste Unternehmens-
vorgaben und werden im normalen Optimierungslauf nicht verändert.

### Mathematische Formeln für Bewertung und Optimierung

Für einen Aktionskandidaten werden die gewichteten Teilbewertungen addiert:

```text
S_lokal(a) = Σᵢ gewichtᵢ × kriteriumᵢ(a)
```

Die lokalen Regeln und ihre konkreten Teilscore-Formeln sind:

```text
EDD: urgency = calculate_edd_priority(latest_end_time, current_time)
     Early Due Date: Je dringender die Deadline, desto höher der Score.

SPT: processing_time_score = 1 / (1 + operation_duration)
     Shortest Processing Time: Je kürzer die Bearbeitungsdauer,
     desto höher der Score.

Transport:
    distance = |Δx| + |Δy| + |Δz|
    transport_time = distance / movement_speed
    transport_time_score = 1 / (1 + transport_time)

Kapazität:
    capacity_score = available_capacity / capacity

Queue:
    queue_score = 1 / (1 + queue_length)

Tool-Matching:
    1, wenn das benötigte Werkzeug bereits montiert ist, sonst 0

Tool-Leben:
    tool_life_score = min(1, remaining_life / consumed_life)
```

Jeder Teilscore wird mit seinem Gewicht aus `HeuristicWeights` multipliziert.
Der lokale Aktionsscore ist die Summe der jeweils relevanten gewichteten
Teilscores:

```text
S_lokal(a) = Σᵢ (Teilscoreᵢ(a) × HeuristicWeightᵢ)
```

### Übersicht der lokalen Bewertungsregeln


| Regel                       | Bedeutung                                                                    | Verwendung                    |
| ----------------------------- | ------------------------------------------------------------------------------ | ------------------------------- |
| EDD                         | Dringlichkeit bis zur Deadline                                               | Release, Pick, Defektaktionen |
| Queue-Priorität            | Priorität des Jobs                                                          | Pick-Aktionen                 |
| SPT                         | Kürzere Bearbeitungszeit wird bevorzugt                                     | Maschinen-Pick und Place      |
| Transportzeit               | Kürzere Roboterfahrt wird bevorzugt                                         | Roboter-Pick und Place        |
| Quell-/Ziel-Store-Zeit      | Kürzere Ein- oder Auslagerung wird bevorzugt                                | Pick bzw. Place               |
| Zielkapazität              | Mehr freier Platz wird bevorzugt                                             | Place                         |
| Maschinen-Queue             | Kürzere Maschinenwarteschlange wird bevorzugt                               | Place                         |
| Werkzeug-Matching           | Bereits montiertes passendes Werkzeug wird bevorzugt                         | Maschinen-Pick                |
| Werkzeuglebensdauer         | Ausreichende Restlebensdauer wird bevorzugt                                  | Maschinen-Pick                |
| Nacharbeitskosten           | Günstigere Nacharbeit wird bevorzugt                                        | Defektaktionen                |
| Reparaturwahrscheinlichkeit | Erfolgreiche Nacharbeit wird bevorzugt                                       | Defektaktionen                |
| Deadline-Druck              | Bei dringenden Jobs verändern sich Ausschuss-, Warte- und Nacharbeitsscores | Defektaktionen                |

Kurz als Entscheidungsregel:

```text
EDD / Queue-Priorität
    → dringende Jobs erhalten einen höheren Score
SPT
    → kürzere nächste Operationen erhalten einen höheren Score
Transportzeit
    → kürzere Roboterwege erhalten einen höheren Score
Entnahme- und Einlagerungszeit
    → kürzere Store-Zeiten erhalten einen höheren Score
freie Store-Kapazität
    → ein weniger voller Ziel-Store erhält einen höheren Score
Maschinenqueue
    → eine kürzere Maschinenwarteschlange erhält einen höheren Score
Werkzeug-Matching
    → ein bereits montiertes benötigtes Werkzeug erhält einen Bonus
Werkzeuglebensdauer
    → ausreichende verbleibende Lebensdauer erhält einen höheren Score
```

Nebenbedingungen können formal als Indikatorfunktion geschrieben werden:

```text
zulässig(a) = 1, wenn alle technischen Bedingungen erfüllt sind
             0, sonst
```

Nur Aktionen mit `zulässig(a) = 1` werden vom Generator erzeugt. Beispiele
sind freie Store-Kapazität, eine verfügbare Maschine und eine gültige Route.
Für Nacharbeit gilt zusätzlich:

```text
remaining_time > 0
und nacharbeit_cost <= MAX_NACHARBEIT_COST
```

Die globale Zielfunktion kombiniert die Kennzahlen eines vollständigen Laufs:

```text
Z = w_makespan × makespan
  + w_tardiness × total_tardiness
  + w_transport × total_transport_time
  + w_tool × tool_change_time
  + w_blocking × blocking_time
  + w_repair × rework_job_count
  + w_scrap × scrap_job_count
  + w_unfinished × unfinished_jobs
```

Der Optimizer minimiert den mittleren Zielfunktionswert über mehrere Seeds:

```text
θ* = argmin_θ (1 / Anzahl Seeds) × Σ Z(θ, seed)
```

### Was bedeutet „Seed“?

Seed = Startwert/Initialisierungswert für einen Zufallszahlengenerator. Ausgangspunkt aus dem die Zahlenfolge entsteht

Ein `Seed` ist der feste Startwert des Zufallszahlengenerators. Die Simulation
verwendet daraus eine reproduzierbare Folge von Zufallszahlen, zum Beispiel für
Defekte oder andere zufällige Ereignisse.

```text
gleicher Seed   → gleiche Zufallsfolge → unter gleichen Bedingungen gleiches Ergebnis
anderer Seed    → andere Zufallsfolge  → anderes mögliches Szenario
```

Beispiel:

```python
seeds = [1, 2, 3]
```

Der Gewichtssatz wird dabei dreimal simuliert. Anschließend wird der Mittelwert
der drei globalen Zielfunktionswerte gebildet. Dadurch wird ein Gewichtssatz
nicht nur anhand eines einzelnen Zufallsszenarios beurteilt.

So bewerten lokale Regeln einzelne Aktionen, während die globale Zielfunktion
die Gesamtwirkung dieser Entscheidungen über den gesamten Simulationslauf
bewertet.

## Lokale heuristische Bewertungsregeln

EDD und die übrigen Regeln sind lokale heuristische Bewertungsregeln:

- lokal: Sie bewerten die unmittelbar anstehende Aktion.
- heuristisch: Sie verwenden einfache Näherungsregeln und garantieren kein global optimales Ergebnis.
- Bewertungsregel: Sie berechnen einen Score für jeden aktuellen Aktionskandidaten.

```text
EDD / Queue-Priorität
    → dringende Jobs erhalten einen höheren Score
SPT
    → kürzere nächste Operationen erhalten einen höheren Score
Transportzeit
    → kürzere Roboterwege erhalten einen höheren Score
Entnahme- und Einlagerungszeit
    → kürzere Store-Zeiten erhalten einen höheren Score
freie Store-Kapazität
    → ein weniger voller Ziel-Store erhält einen höheren Score
Maschinenqueue
    → eine kürzere Maschinenwarteschlange erhält einen höheren Score
Werkzeug-Matching
    → ein bereits montiertes benötigtes Werkzeug erhält einen Bonus
Werkzeuglebensdauer
    → ausreichende verbleibende Lebensdauer erhält einen höheren Score
```

Die Regel liefert zunächst einen Teilscore. Dieser wird mit dem zugehörigen
`HeuristicWeights`-Wert multipliziert und anschließend mit den anderen
Teilbewertungen zum Aktions-Gesamtscore addiert.

Anschließend werden die aktuell verfügbaren Aktionen miteinander verglichen und die Aktion mit dem höchsten Gesamtscore ausgewählt.

## Unterschied der Gewichtstypen

```text
HeuristicWeights
→ bestimmen den Einfluss lokaler Regeln
→ werden während jeder einzelnen Aktionsentscheidung verwendet

GlobalSimulationWeights
→ bestimmen den Einfluss globaler Simulationskennzahlen
→ werden erst nach einem vollständigen Simulationslauf verwendet
```

Beispiel:

```text
lokaler EDD-Teilscore × HeuristicWeights.queue_priority
    → beeinflusst, welcher Job jetzt ausgewählt wird

GlobalSimulationWeights.total_tardiness × gesamte Verspätung
    → beeinflusst, wie gut der abgeschlossene Simulationslauf war
```

## Was bedeutet „Gewichte optimieren“?

Ein Gewichtssatz ist eine konkrete Kombination aller lokalen
`HeuristicWeights`. Diese Gewichte bestimmen während eines Simulationslaufs,
wie stark EDD, Transport, Kapazität, Werkzeugkriterien und die übrigen lokalen
Regeln in den Aktionsscores zählen.

Der Optimizer verändert nicht direkt einzelne Aktionen. Stattdessen vergleicht
er verschiedene Gewichtssätze über vollständige Simulationsläufe:

```text
Gewichtssatz einsetzen
    ↓
komplette Simulation ausführen
    ↓
globale Kennzahlen messen
    ↓
globale Zielfunktion berechnen
    ↓
Kosten mit anderen Gewichtssätzen vergleichen
```

Ein Gewichtssatz ist besser, wenn seine globale Zielfunktion kleiner ist. Die
globale Zielfunktion kann beispielsweise kurze Durchlaufzeit, geringe
Verspätung, wenig Transport, wenige Werkzeugwechsel und wenig Ausschuss
gleichzeitig berücksichtigen.

## Wie werden neue Gewichtssätze erzeugt?

`optimize_iteratively(...)` startet mit einem initialen Gewichtssatz. Für jedes
Gewicht werden zwei Nachbarn gebildet:

```text
aktueller Wert - Schrittweite
aktueller Wert
aktueller Wert + Schrittweite
```

Alle Werte bleiben im Bereich `0.0` bis `1.0`. Bei 26 lokalen Gewichten ergibt
das pro Iteration:

```text
1 aktueller Gewichtssatz
+ 27 Varianten mit kleinerem Einzelgewicht
+ 27 Varianten mit größerem Einzelgewicht
= 55 Nachbarschaftssätze
```

Zusätzlich werden pro Iteration zehn zufällige Gewichtssätze erzeugt. Damit
bleibt die Suche nicht auf die unmittelbare Umgebung des aktuellen Satzes
beschränkt (Exploration). Der bisher global beste Satz wird gespeichert. Nur
wenn sich dieser verbessert, wird die Schrittweite halbiert. Nach zwei Runden
ohne Verbesserung erfolgt ein zufälliger Neustart.

`Exploitation` bedeutet hier: Die Suche prüft gezielt die Nachbarn des bisher
besten lokalen Gewichtssatzes. `Exploration` bedeutet: Zufällige Kandidaten und
Neustarts untersuchen auch weit entfernte Bereiche des Gewichtsraums. Der
Optimierer kombiniert damit beide Strategien, statt nur immer in derselben
kleinen Umgebung weiterzusuchen.

## Start

~~~powershell
python sources/examples/optimization/example-0-optimize.py
~~~

## Gesamtablauf

1. Fabrikkonfiguration erstellen
   ├── Maschinen
   ├── Werkzeuge
   ├── Produkte
   ├── Operationen
   ├── Auftrag
   ├── Layout
   └── Korridor
2. Klassen importieren
3. `SpineMLSimulationRunner` erstellen

   SpineMLSimulationRunner startet einen vollständigen Simulationslauf mit:

   - einem konkreten lokalen HeuristicWeights-Satz
   - einem festgelegten seed
   - derselben Fabrikkonfiguration aus Example 0

Der Runner verändert die Gewichte nicht. Er verwendet den übergebenen Gewichtssatz während des gesamten Laufs und gibt danach die globalen Kennzahlen zurück.

4. `GlobalSimulationEvaluation` erstellen
   → bewertet die globalen Simulationsergebnisse
5. `LocalHeuristicWeightOptimizer` erstellen
   → verbindet Runner und globale Bewertung
6. `optimize_iteratively(...)` aufrufen
   → hier startet die eigentliche Optimierung

Danach läuft für jeden erzeugten Gewichtssatz eine vollständige Simulation
ohne Visualisierung. Die globalen Kennzahlen werden erfasst, mit den festen
`GlobalSimulationWeights` bewertet und anschließend miteinander verglichen.

## Lokale Gewichte

Die lokalen Gewichte beeinflussen den Score der einzelnen
Aktionskandidaten:

~~~text
HeuristicWeights
├── queue_priority
├── pick_source_storage_time
├── pick_short_transport_time
├── machine_pick_processing_time
├── machine_pick_tool_match
├── machine_pick_tool_life
├── target_store_capacity
├── place_target_storage_time
├── place_short_transport_time
├── place_machine_queue
├── place_shortest_processing_time
├── release_edd
├── rework_defect_machine_deadline_penalty_weight
├── rework_alternative_machine_deadline_penalty_weight
├── downgrade_product
├── wait_defect_job
├── job_scrap
├── rework_not_allowed_downgrade_bonus_weight
├── deadline_pressure_scrap_bonus_weight
├── deadline_missed_wait_penalty
├── rework_defect_machine_deadline_penalty_weight
├── rework_alternative_machine_deadline_penalty_weight
├── defect_edd
└── defect_repair_quality
~~~

Innerhalb eines vollständigen Simulationslaufs bleiben diese Werte fest.
Zwischen zwei vollständigen Läufen darf der Optimierer sie verändern.

## SpineMLSimulationRunner

Für jeden Gewichtssatz und Seed führt der Runner eine neue Simulation aus:

~~~text
SpineMLSimulationRunner(weights, seed)
├── neue Salabim-Environment
├── LocalHeuristicActionEvaluator(weights)
├── GeneratorSelectorPolicy
├── SimulationBridge
├── SimLayout
├── SimScenario
└── vollständiger headless Simulationslauf
~~~

## Globale Kennzahlen

Nach jedem vollständigen Lauf werden erfasst:

~~~text
GlobalSimulationMetrics
├── makespan
├── total_tardiness
├── total_transport_time
├── tool_change_time
├── blocking_time
├── rework_job_count
├── scrap_job_count
└── unfinished_jobs
~~~

## Globale Zielfunktion

Die globalen Gewichte bestimmen, wie stark jede Laufkennzahl in die globalen
Kosten eingeht:

~~~python
GlobalSimulationWeights(
    makespan=2.0,
    total_tardiness=5.0,
    total_transport_time=1.0,
    tool_change_time=1.0,
    blocking_time=1.0,
    nacharbeit_job_penalty=1.0,
    job_scrap_weight=1.0,
    unfinished_jobs=1_000.0,
)
~~~

Die globale Zielfunktion wird minimiert:

~~~text
kleinere globale Kosten
└── besseres Gesamtergebnis des Simulationslaufs
~~~

## Aktuelle Optimierungseinstellung

### LocalHeuristicWeightOptimizer

Der `LocalHeuristicWeightOptimizer` erhält den Runner und die globale Bewertung.
Er verändert nur die lokalen `HeuristicWeights`. Die globalen Gewichte bleiben
fest und werden nur verwendet, um die Ergebnisse der einzelnen Läufe zu
vergleichen.

~~~python
result = optimizer.optimize_iteratively(
    initial_local_weights=HeuristicWeights(),
    seeds=[1, 2, 3],
    iterations=5,
    initial_local_weight_step_fraction=0.25,
    exploration_candidate_count=10,
    restart_after_no_improvement=2,
)
~~~

Die Parameter bedeuten:

| Parameter | Bedeutung |
|---|---|
| `initial_local_weights` | Ausgangssatz der lokalen Aktionsgewichte |
| `seeds` | Zufallsszenarien, unter denen jeder Gewichtssatz getestet wird |
| `iterations` | Anzahl der Suchrunden |
| `initial_local_weight_step_fraction` | anfängliche Größe der Änderung an einem lokalen Gewicht |
| `exploration_candidate_count` | zufällige Kandidaten je Runde für entfernte Suchbereiche |
| `restart_after_no_improvement` | erfolglose Runden bis zum zufälligen Neustart |

Der Aufruf arbeitet anschließend so:

~~~text
initiale HeuristicWeights
        ↓
kleinere und größere Nachbarwerte erzeugen
        ↓
jeden Kandidaten mit jedem Seed simulieren
        ↓
GlobalSimulationMetrics sammeln
        ↓
GlobalSimulationEvaluation.evaluate(metrics)
        ↓
globale Kosten vergleichen
        ↓
besten lokalen Gewichtssatz übernehmen
~~~

Bei einer Verbesserung wird die Schrittweite kleiner. Ohne Verbesserung bleibt
sie zunächst erhalten; nach mehreren erfolglosen Runden wird ein neuer zufälliger
Ausgangspunkt gewählt.

Bei 26 lokalen Gewichten erzeugt eine Iteration:

~~~text
1 ursprünglicher Gewichtssatz
+
27 Varianten mit kleinerem Einzelgewicht
+
27 Varianten mit größerem Einzelgewicht
=
65 Kandidaten (55 Nachbarn + 10 zufällige Kandidaten)
~~~

## Konsolenausgabe

Für jeden Kandidaten werden ausgegeben:

~~~text
Getestete lokale Gewichte
Mittlere globale Kosten
~~~

Am Ende werden ausgegeben:

~~~text
Beste lokale Gewichte
Beste mittlere globale Kosten
Anzahl bewerteter Gewichtssätze
~~~

`example-0-optimize.py` kann als Streamlit-Webinterface gestartet werden:

```powershell
streamlit run sources/examples/optimization/example-0-optimize.py
```

Nach Klick auf **Optimierung starten** zeigt die Seite sofort die aktuelle
Iteration sowie den Fortschritt des gerade simulierten Kandidaten
(`Kandidat n / Gesamtzahl`). Nach jedem vollständig bewerteten Kandidaten wird
deren mittlere globale Kosten zu den Live-Grafen hinzugefügt. Der erste Graph
zeigt jeden Kandidatenwert, der zweite die bisher beste (kleinste) globale
Kosten. Am Ende werden die besten lokalen Gewichte angezeigt.
Die Anzeige wird über Streamlit-Platzhalter im laufenden Skript aktualisiert;
die Seite wird währenddessen nicht ständig neu geladen. Dadurch bleibt die
Fabrikkonfiguration für den gesamten Optimierungslauf unverändert.

Das Beispiel begrenzt jeden Simulationslauf auf `till=100` Stunden. Ohne diese
Begrenzung würde der Salabim-Runner mit `sim.inf` auf weitere Ereignisse warten,
obwohl die eigentliche Produktion bereits beendet ist.

Die Oberfläche benötigt keinen 3D-Plot.

## Mehrere Seeds und Iterationen

Für eine aussagekräftigere Optimierung können die Einstellungen erhöht werden:

~~~python
result = optimizer.optimize_iteratively(
    initial_local_weights=HeuristicWeights(),
    seeds=[1, 2, 3],
    iterations=5,
    initial_local_weight_step_fraction=0.25,
    exploration_candidate_count=10,
    restart_after_no_improvement=2,
)
~~~

Das ergibt ungefähr:

~~~text
65 Kandidaten pro Iteration (55 Nachbarn + 10 zufällige Kandidaten)
× 3 Seeds
× 5 Iterationen
= 975 vollständige Simulationsläufe
~~~

Mehrere Seeds reduzieren den Einfluss zufälliger Defekte. Mehrere Iterationen
ermöglichen eine schrittweise Verbesserung. Zufällige Kandidaten und Neustarts
erforschen zusätzlich andere Bereiche des Gewichtsraums.

## Aktuelles Ergebnis von Example 0

Beim früheren Test erzeugten alle 19 Gewichtssätze dieselben globalen Kosten.
Die Optimierungsschleife wurde vollständig ausgeführt, aber es wurde kein
besserer Gewichtssatz gefunden.

Das bedeutet:

~~~text
Optimierung technisch ausgeführt
        ↓
Gewichtssätze verändert
        ↓
vollständige Simulationen verglichen
        ↓
keine unterschiedlichen Entscheidungen oder globalen Ergebnisse
        ↓
Standardgewichte bleiben bestes Ergebnis
~~~

Für unterschiedliche Ergebnisse benötigt das Szenario Zielkonflikte, etwa
unterschiedliche Deadlines, Bearbeitungszeiten, Transportwege,
Werkzeugwechsel oder Maschinenbelegungen.

## Unterschied zum normalen Example


| Normales Example         | Optimierungs-Example               |
| -------------------------- | ------------------------------------ |
| **example-0.py**         | **example-0-optimize.py**          |
| ein Simulationslauf      | viele Simulationsläufe            |
| 3D-Visualisierung        | keine Visualisierung               |
| feste lokale Gewichte    | veränderte lokale Gewichte        |
| lokale Aktion auswählen | lokale Gewichte global vergleichen |
| keine Gewichtssuche      | iterative Gewichtssuche            |
