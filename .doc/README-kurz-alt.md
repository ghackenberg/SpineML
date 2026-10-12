# Technische Codeübersicht

Dieser Ordner enthält persönliche, nicht von Git verfolgte Lern- und Architekturnotizen zu SpineML.

## Steuerungsarchitektur

```text
PolicyObservation
        ↓
GeneratorSelectorPolicy
        ├── SpineActionGenerator
        │   └── erzeugt technisch mögliche Aktionskandidaten
        ├── LocalHeuristicActionEvaluator
        │   └── bereitet Kandidaten vor und berechnet lokale Scores
        └── ActionSelector
            └── wählt anhand der Bewertung eine Aktion aus
        ↓
PolicyDecision
```

## Dateien

- [InterfaceTypes](interface_types.md)
- [GeneratorSelectorPolicy](generator_selector_policy.md)
- [SpineActionGenerator](action_generator.md)
- [LocalHeuristicActionEvaluator](local_heuristic_action_evaluator.md)
- [SpineMLSimulationRunner](SpineMLSimulationRunner.md)
- [OperationType](OperationType.md)
- [LocalHeuristicWeightOptimizer](LocalHeuristicWeightOptimizer.md)
- [ActionSelector](action_selectors.md)
- [SimulationBridge](simulation_bridge.md)
- [SimOrderJob](sim_order_job.md)
- [SimRobotMain](sim_robot_main.md)
- [SimRobotCorridorArm](sim_robot_corridor_arm.md)
- [SimMachine](sim_machine.md)
- [Policy-Datenstrukturen](policy_data.md)

Die abstrakten Schnittstellen und gemeinsamen Datentypen befinden sich zusammen
in `sources/SpineML/Control/InterfaceTypes.py`.

## Einheitliches Methodenschema

Jede dokumentierte Methode soll nach diesem Schema beschrieben werden:

```text
Methode
├── Aufgabe
├── Eingabe
├── Verarbeitung
└── Ausgabe
```

