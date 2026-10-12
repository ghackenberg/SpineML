# HeuristicControl

Python-Ordner: **sources/SpineML/Control/HeuristicControl/**

## Position im Ablauf

~~~text
HeuristicWeights
└── lokale Gewichte eines Versuchs
        ↓
LocalHeuristicActionEvaluator
└── bewertet während der Simulation jede mögliche Aktion
        ↓
vollständiger Simulationslauf
        ↓
GlobalSimulationMetrics
└── globale Kennzahlen des vollständigen Laufs
        ↓
GlobalSimulationEvaluation
└── berechnet die globalen Kosten Z
        ↓
LocalHeuristicWeightOptimizer
└── vergleicht Gewichtssätze und behält den besten
~~~

Der **LocalHeuristicActionEvaluator** ist der aktive
Standard-Evaluator der **GeneratorSelectorPolicy**.

~~~text
GeneratorSelectorPolicy
└── action_evaluator = LocalHeuristicActionEvaluator(
        HeuristicWeights()
    )
        ↓
BaselineActionSelector.select_action(
    evaluator=action_evaluator
)
        ↓
evaluator.prepare_action_candidate(...)
        ↓
evaluator.evaluate_action(...)
~~~

## HeuristicWeights

~~~python
weights = HeuristicWeights(
    queue_priority=0.4,
    pick_shortest_processing_time=0.2,
    pick_source_storage_time=0.1,
    pick_short_transport_time=0.3,
)
~~~

Diese Werte gewichten lokale Kriterien. Sie sind nicht die Gewichte der
globalen Zielfunktion. Die lokalen Kriterien und Gewichte liegen im Bereich
von `0.0` bis `1.0`. Die Gewichte einer Aktionsgruppe ergeben möglichst
zusammen `1.0`.

## GlobalSimulationMetrics und globale Zielfunktion

~~~python
metrics = GlobalSimulationMetrics(
    makespan=100.0,
    total_tardiness=10.0,
    total_transport_time=20.0,
    tool_change_time=4.0,
    blocking_time=2.0,
    nacharbeit_job_penalty=1.0,
    job_scrap_weight=0.0,
)

global_weights = GlobalSimulationWeights(
    makespan=2.0,
    total_tardiness=5.0,
    total_transport_time=1.0,
)

global_evaluation = GlobalSimulationEvaluation(global_weights)
global_cost = global_evaluation.evaluate(metrics)
~~~

Die globale Zielfunktion wird minimiert.

## SpineMLSimulationRunner

Der konkrete Runner verbindet einen Gewichtssatz mit einem vollständigen
headless SpineML-Simulationslauf:

~~~python
runner = SpineMLSimulationRunner(
    layout=l1,
    scenario=s1,
)

metrics = runner(
    HeuristicWeights(),
    seed=1,
)
~~~

~~~text
Gewichte und Seed empfangen
        ↓
neue Salabim-Environment erzeugen
        ↓
LocalHeuristicActionEvaluator mit den Gewichten erzeugen
        ↓
GeneratorSelectorPolicy und SimulationBridge erzeugen
        ↓
SpineML-Simulation vollständig ohne Fenster ausführen
        ↓
globale Kennzahlen sammeln
        ↓
GlobalSimulationMetrics zurückgeben
~~~

Gemessen werden Makespan, Gesamtverspätung, Transportzeit,
Werkzeugwechselzeit, Nacharbeit, Ausschuss und nicht fertiggestellte Jobs.

## LocalHeuristicWeightOptimizer

Der `LocalHeuristicWeightOptimizer` optimiert ausschließlich `HeuristicWeights`.
`GlobalSimulationWeights` werden an `GlobalSimulationEvaluation` übergeben und
bleiben während dieses Suchlaufs unverändert. Sie bestimmen die globale
Zielfunktion, mit der die Ergebnisse vollständiger Simulationsläufe verglichen
werden. Eine Änderung dieser globalen Gewichte ändert daher das Optimierungsziel
und erfordert einen neuen Optimierungslauf.

Der Optimierer erhält den konkreten SpineML-Runner:

~~~python
runner = SpineMLSimulationRunner(l1, s1)
global_evaluation = GlobalSimulationEvaluation(global_weights)
optimizer = LocalHeuristicWeightOptimizer(
    simulation_runner=runner,
    global_evaluation=global_evaluation,
)
~~~

Konkrete Verwendung:

~~~python
candidates = [
    HeuristicWeights(queue_priority=0.2),
    HeuristicWeights(queue_priority=0.4),
    HeuristicWeights(queue_priority=0.6),
]

optimizer = LocalHeuristicWeightOptimizer(
    simulation_runner=runner,
    global_evaluation=global_evaluation,
)

result = optimizer.optimize(
    weight_candidates=candidates,
    seeds=[1, 2, 3],
)
~~~

Das Ergebnis enthält:

~~~text
WeightOptimizationResult
├── best_weights
├── best_mean_global_cost
└── evaluations
    └── pro Gewichtssatz:
        ├── objective_values für alle Seeds
        └── mean_global_cost
~~~

## Iterative Verbesserung

Der Optimierer kann die lokalen Gewichte selbst schrittweise verändern:

~~~python
result = optimizer.optimize_iteratively(
    initial_local_weights=HeuristicWeights(),
    seeds=[1, 2, 3],
    iterations=5,
    initial_local_weight_step_fraction=0.25,
)
~~~

~~~text
aktueller bester Gewichtssatz
        ↓
für jedes Gewicht:
├── kleineren Nachbarwert erzeugen
└── größeren Nachbarwert erzeugen
        ↓
jeden Kandidaten über vollständige Simulationen bewerten
        ↓
global besten Kandidaten übernehmen
        ↓
Schrittweite verkleinern
        ↓
nächste Iteration
~~~

## Äußere Wiederholung

~~~text
Gewichtssatz 1
├── Simulation mit Seed 1
├── Simulation mit Seed 2
└── Simulation mit Seed 3
        ↓
mittlere globale Kosten

Gewichtssatz 2
├── Simulation mit Seed 1
├── Simulation mit Seed 2
└── Simulation mit Seed 3
        ↓
mittlere globale Kosten

alle Mittelwerte vergleichen
        ↓
Gewichtssatz mit den kleinsten globalen Kosten zurückgeben
~~~

Jeder vollständige Simulationslauf verwendet einen festen lokalen
Gewichtssatz. Die Gewichte werden erst zwischen vollständigen Läufen
verglichen und verändert.

