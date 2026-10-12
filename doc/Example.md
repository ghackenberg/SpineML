# Normales Example

Python-Datei: **sources/examples/normal/example-0.py**

## Aufgabe

Das normale Example erzeugt die Fabrikkonfiguration und führt genau einen visualisierten Simulationslauf aus.

## Start

~~~powershell
python sources/examples/normal/example-0.py
~~~

## Vollständiger Ablauf und beteiligte Python-Dateien

~~~text
sources/examples/normal/example-0.py
└── erzeugt die konkrete Konfiguration
    └── sources/SpineML/simulate.py
        └── erzeugt Salabim-Umgebung und Laufzeitobjekte
            ├── Simulation/SimOrderJob.py
            ├── Simulation/SimRobotMain.py
            ├── Simulation/SimRobotCorridorArm.py
            └── Simulation/SimMachine.py
                    │
                    │ request_action(...)
                    ▼
            Control/SimulationBridge/SimulationBridge.py
                    │
                    │ PolicyObservation
                    ▼
            Control/GeneralControl/GeneratorSelectorPolicy.py
                    │
                    ├── Control/GeneralControl/ActionGenerators.py
                    │   └── technisch mögliche Aktionen
                    │
                    ├── Control/HeuristicControl/
                    │   ├── HeuristicWeights.py
                    │   └── LocalHeuristicActionEvaluator.py
                    │       └── Aktionen vorbereiten, bewerten und gewichten
                    │
                    └── Control/GeneralControl/ActionSelectors.py
                        └── Aktion mit dem höchsten Score auswählen
                                │
                                │ PolicyDecision
                                ▼
            Control/SimulationBridge/SimulationBridge.py
                    │ IDs in echte Laufzeitobjekte umwandeln
                    │ SimulationAction erzeugen
                    ▼
            persönlicher Action-Store des Simulationsobjekts
                    │
                    ▼
            Simulationsobjekt führt die Aktion aus
                    │
                    │ neue Aktionsanforderung oder Zustandsmeldung
                    └──────────────────────────────► SimulationBridge
~~~

## Policy-Entscheidung im Detail

Dieser Abschnitt erklärt ausschließlich den mittleren Teil des Diagramms:

~~~text
PolicyObservation
        ↓
GeneratorSelectorPolicy.py
        ├── ActionGenerators.py
        ├── LocalHeuristicActionEvaluator.py
        └── ActionSelectors.py
        ↓
PolicyDecision
~~~

### `Control/GeneralControl/GeneratorSelectorPolicy.py`

Die `GeneratorSelectorPolicy` ist die Verbindung zwischen Generator, Evaluator und Selector.

Sie erhält von der Bridge eine globale `PolicyObservation`. Diese enthält den vollständigen Snapshot aller Simulationsobjekte und des Konfigurationsmodells.

Für jedes Objekt mit `is_waiting_for_action = True` erzeugt sie eine objektbezogene `PolicyObservation`:

~~~text
globale PolicyObservation
└── current_object_id = None
        ↓
wartendes Objekt „Main robot“
        ↓
objektbezogene PolicyObservation
└── current_object_id = "Main robot"
~~~

Danach ruft sie für dieses Objekt Generator und Selector auf. Am Ende sammelt sie die ausgewählten Objektaktionen in einer gemeinsamen `PolicyDecision`.

### `Control/GeneralControl/ActionGenerators.py`

Verwendete Klasse: `SpineActionGenerator`

~~~text
objektbezogene PolicyObservation
        ↓
SpineActionGenerator.generate_actions(...)
        ↓
Liste technisch möglicher Aktionskandidaten
~~~

Der Generator beantwortet ausschließlich: **Welche Aktionen sind in diesem Zustand technisch möglich?**

Beispielsweise erzeugt er für einen leeren Main-Roboter mehrere Pick-Kandidaten aus dem Start-Store und den Corridor-Main-Stores. Er wählt keinen Kandidaten aus und berechnet nicht, welcher Kandidat am besten ist.

### `Control/HeuristicControl/HeuristicWeights.py`

`HeuristicWeights` enthält die Gewichte der lokalen Bewertungsformel, beispielsweise für Queue-Priorität, Bewegungsgeschwindigkeit, Bearbeitungsgeschwindigkeit, Store-Kapazität und Werkzeugrüstung.

Beim normalen `example-0.py` werden diese Gewichte während des Laufs nicht optimiert. Es werden die beim Erzeugen des Evaluators übergebenen Werte benutzt.

### `Control/HeuristicControl/LocalHeuristicActionEvaluator.py`

Verwendete Klasse: `LocalHeuristicActionEvaluator`

Das ist der im normalen Example tatsächlich aktive Evaluator. Er bereitet jeden
Kandidaten vor, verwendet die `HeuristicWeights` und berechnet anschließend
dessen lokalen Score.

~~~text
technisch möglicher Kandidat
        ↓
prepare_action_candidate(...)
└── queue_priority, movement_speed oder processing_speed_factor ergänzen
        ↓
evaluate_action(...)
└── gewichtete Merkmale auswerten
        ↓
numerischen Score zurückgeben
~~~

Der Evaluator erzeugt keine technische Aktion und wählt keine Aktion aus. Er beantwortet: **Wie gut ist dieser technisch mögliche Kandidat nach der aktuellen Heuristik?**

Im aktiven Ablauf wird dafür ausschließlich der `LocalHeuristicActionEvaluator`
verwendet.

### `Control/GeneralControl/ActionSelectors.py`

Verwendete Klasse: `BaselineActionSelector`

Der Selector erhält alle vom Generator erzeugten Kandidaten. Für jeden Kandidaten ruft er den aktiven Evaluator auf und merkt sich dessen Score.

~~~text
Kandidat A → Score 12
Kandidat B → Score 25
Kandidat C → Score 18
                ↓
höchster Score = 25
                ↓
Kandidat B wird ausgewählt
~~~

Haben mehrere Kandidaten denselben höchsten Score, wählt der Selector zufällig einen dieser gleich bewerteten Kandidaten. Die ausgewählte Aktion wird als `SelectedObjectAction` in einer `PolicyDecision` zurückgegeben.

## Zusammenspiel der Dateien

~~~text
GeneratorSelectorPolicy
        ↓
SpineActionGenerator
└── erzeugt technisch mögliche Aktionskandidaten
        ↓
LocalHeuristicActionEvaluator
├── bereitet jeden Kandidaten für die Bewertung vor
    ├── ergänzt queue_priority
    ├── ergänzt movement_speed
    └── ergänzt processing_speed_factor
└── berechnet mithilfe der HeuristicWeights den Score jedes Kandidaten
        ↓
BaselineActionSelector
└── wählt den Kandidaten mit dem höchsten Score
        ↓
GeneratorSelectorPolicy
└── sammelt die gewählten Objektaktionen in einer globalen PolicyDecision
~~~

Kurz gesagt:

~~~text
ActionGenerator                    = technisch mögliche Aktionen erzeugen
LocalHeuristicActionEvaluator = Kandidaten vorbereiten und Score berechnen
BaselineActionSelector             = höchsten Score auswählen
~~~

