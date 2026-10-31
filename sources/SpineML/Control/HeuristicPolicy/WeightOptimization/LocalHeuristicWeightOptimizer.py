from __future__ import annotations

import random
from dataclasses import dataclass, fields, replace
from statistics import mean
from typing import Iterable

from ..HeuristicPolicyFactory import HeuristicPolicyFactory
from ..HeuristicWeights import HeuristicWeights
from ....GlobalEvaluation.GlobalSimulationEvaluation import (
    GlobalSimulationEvaluation,
    GlobalSimulationMetrics,
)
from ....SimulationExecution.ParallelSimulationRunner import SimulationRunRequest


@dataclass(frozen=True)
class WeightEvaluation:
    """Ein Gewichtssatz mit Kennzahlen je Seed, Bewertungszahlen und ihrem Mittelwert."""
    weights: HeuristicWeights
    objective_values: tuple[float, ...]
    mean_global_cost: float
    metrics_by_seed: tuple[GlobalSimulationMetrics, ...] = ()


@dataclass(frozen=True)
class WeightOptimizationResult:
    """Bester Gewichtssatz, seine Bewertung und die gespeicherten Gewichtssatzbewertungen."""
    best_weights: HeuristicWeights
    best_mean_global_cost: float
    best_evaluation: WeightEvaluation
    evaluations: tuple[WeightEvaluation, ...]


class LocalHeuristicWeightOptimizer:
    """Sucht lokale Gewichtssätze mit einer kleinen mittleren globalen Bewertungszahl."""

    # Speichert den Runner für Simulationsläufe und die globale Bewertung ihrer Kennzahlen.
    def __init__(self, simulation_runner, global_evaluation: GlobalSimulationEvaluation):
        self.simulation_runner = simulation_runner
        self.global_evaluation = global_evaluation

    # Erstellt und prüft in mehreren Iterationen lokale Gewichtssätze.
    # Für die Auswahl zählt der Mittelwert der globalen Bewertungszahlen über die Seeds.
    def optimize_iteratively(
        self,
        initial_local_weights: HeuristicWeights,
        seeds: Iterable[int],
        iterations: int = 5,
        initial_local_weight_step_fraction: float = 0.25,
        exploration_candidate_count: int = 10,
        restart_after_no_improvement: int = 2,
        stop_after_no_improvement: int | None = 6,
        progress_callback=None,
    ) -> WeightOptimizationResult:
        seed_values = tuple(seeds)
        if not seed_values:
            raise ValueError("Mindestens ein Seed ist erforderlich.")
        current_local_weights = initial_local_weights
        weight_step_fraction = initial_local_weight_step_fraction
        # Ergebnisverlauf: erste beste Bewertung und spätere Verbesserungen.
        best_solution_memory = []
        best_evaluation = None
        # Neustart-Zähler: Iterationen ohne Verbesserung seit letzter Verbesserung/Neustart.
        iterations_without_improvement = 0
        # Abbruch-Zähler: Iterationen ohne Verbesserung seit letzter Verbesserung; kein Reset beim Neustart.
        total_iterations_without_improvement = 0
        # Reproduzierbare Zufallssätze, unabhängig von den Simulations-Seeds.
        exploration_rng = random.Random(0)

        for iteration_number in range(1, iterations + 1):
            # Nachbarvarianten und zusätzliche Zufallssätze prüfen.
            candidates = list(
                self.neighboring_weights(
                    current_local_weights,
                    weight_step_fraction,
                )
            )
            candidates.extend(
                self.random_local_weight_candidates(
                    exploration_candidate_count, exploration_rng
                )
            )

            iteration_result = self.select_best_local_weight_set_across_seeds(
                candidates,
                seed_values,
                iteration_number=iteration_number,
                progress_callback=progress_callback,
            )

            iteration_best = iteration_result.best_evaluation

            # Nur ein kleinerer Mittelwert verbessert den bisherigen besten Satz.
            if (
                best_evaluation is None
                or iteration_best.mean_global_cost < best_evaluation.mean_global_cost
            ):
                best_evaluation = iteration_best
                best_solution_memory.append(iteration_best)
                current_local_weights = iteration_best.weights
                # Auch nach der ersten Iteration: kleinere Schritte, beide Zähler auf 0.
                weight_step_fraction /= 2.0
                iterations_without_improvement = 0
                total_iterations_without_improvement = 0
            else:
                iterations_without_improvement += 1
                total_iterations_without_improvement += 1
                # Erst den Abbruch prüfen; None deaktiviert diese Grenze.
                if (
                    stop_after_no_improvement is not None
                    and total_iterations_without_improvement
                    >= stop_after_no_improvement
                ):
                    break
                if iterations_without_improvement >= restart_after_no_improvement:
                    # Der Ausgangssatz ist bereits der beste: nur wieder breiter suchen.
                    weight_step_fraction = initial_local_weight_step_fraction
                    iterations_without_improvement = 0

        if best_evaluation is None:
            raise ValueError("iterations muss mindestens 1 sein.")

        return WeightOptimizationResult(
            best_weights=best_evaluation.weights,
            best_mean_global_cost=best_evaluation.mean_global_cost,
            best_evaluation=best_evaluation,
            evaluations=tuple(best_solution_memory),
        )

    # Erzeugt den aktuellen Gewichtssatz und zwei Varianten pro Gewicht.
    # Pro Variante wird nur dieses eine Gewicht neu gesetzt; die übrigen bleiben unverändert.
    def neighboring_weights(
        self,
        local_weights: HeuristicWeights,
        weight_step_fraction: float,
    ) -> tuple[HeuristicWeights, ...]:
        neighbors = [local_weights]
        for weight_field in fields(local_weights):
            field_name = weight_field.name
            current_value = float(getattr(local_weights, field_name))
            # Erlaubter Bereich: 0.000001 bis 1.0; doppelte Sätze werden später entfernt.
            lower_value = max(1e-6, current_value - weight_step_fraction)
            higher_value = min(1.0, current_value + weight_step_fraction)
            neighbors.append(replace(local_weights, **{field_name: lower_value}))
            neighbors.append(replace(local_weights, **{field_name: higher_value}))
        return tuple(neighbors)

    # Erzeugt candidate_count vollständige Gewichtssätze mit zufälligen Werten.
    # Mehrere Gewichte können dabei gleichzeitig vom Ausgangssatz der Suche abweichen.
    def random_local_weight_candidates(
        self,
        candidate_count: int,
        rng: random.Random,
    ) -> tuple[HeuristicWeights, ...]:
        candidates = []
        for _ in range(candidate_count):
            values = {}
            for weight_field in fields(HeuristicWeights):
                field_name = weight_field.name
                upper_limit = 1.0
                if field_name == "wait_action_weight":
                    upper_limit = 0.1
                random_fraction = rng.random()
                values[field_name] = 1e-6 + random_fraction * (upper_limit - 1e-6)
            candidates.append(HeuristicWeights(**values))
        return tuple(candidates)

    # Prüft jeden unterschiedlichen Gewichtssatz mit allen Seeds und wählt
    # den Satz mit der kleinsten mittleren globalen Bewertungszahl.
    def select_best_local_weight_set_across_seeds(
        self,
        local_weight_candidates: Iterable[HeuristicWeights],
        seeds: Iterable[int],
        iteration_number: int = 0,
        progress_callback=None,
    ) -> WeightOptimizationResult:
        seed_values = tuple(seeds)
        if not seed_values:
            raise ValueError("Mindestens ein Seed ist erforderlich.")
        # Entfernt doppelte Gewichtssätze und behält die Reihenfolge bei.
        candidate_list = tuple(dict.fromkeys(local_weight_candidates))
        total_candidates = len(candidate_list)
        if not total_candidates:
            raise ValueError("Mindestens ein Gewichtssatz ist erforderlich.")

        run_many = getattr(self.simulation_runner, "run_many", None)
        if callable(run_many):
            # Alle Gewichtssatz-Seed-Paare gemeinsam ausführen lassen.
            evaluations = self._evaluate_candidates_with_run_many(
                candidate_list,
                seed_values,
                run_many,
                iteration_number,
                progress_callback,
            )
        else:
            # Ohne Prozesspool: Gewichtssätze nacheinander prüfen.
            evaluations = []
            for candidate_number, local_weights in enumerate(candidate_list, start=1):
                if progress_callback is not None:
                    progress_callback(iteration_number, None, candidate_number, total_candidates)
                evaluation = self.evaluate_local_weights_across_seeds(
                    local_weights,
                    seed_values,
                )
                evaluations.append(evaluation)
                if progress_callback is not None:
                    progress_callback(iteration_number, evaluation, candidate_number, total_candidates)
        best_evaluation = evaluations[0]

        # Wählt den kleinsten Mittelwert. Bei Gleichstand bleibt der zuerst geprüfte Satz.
        for evaluation in evaluations:
            if evaluation.mean_global_cost < best_evaluation.mean_global_cost:
                best_evaluation = evaluation
        return WeightOptimizationResult(
            best_weights=best_evaluation.weights,
            best_mean_global_cost=best_evaluation.mean_global_cost,
            best_evaluation=best_evaluation,
            evaluations=tuple(evaluations),
        )

    # Ordnet parallele Ergebnisse ihrem Gewichtssatz und ihrer Seedposition zu.
    def _evaluate_candidates_with_run_many(
        self,
        candidates: tuple[HeuristicWeights, ...],
        seeds: tuple[int, ...],
        run_many,
        iteration_number: int,
        progress_callback,
    ) -> list[WeightEvaluation]:
        seed_count = len(seeds)
        total_candidates = len(candidates)
        requests = tuple(
            SimulationRunRequest(HeuristicPolicyFactory(weights), seed)
            for weights in candidates
            for seed in seeds
        )
        # Seedpositionen statt Seedwerte als Schlüssel erhalten auch doppelte Seeds.
        metrics_by_candidate: list[dict[int, GlobalSimulationMetrics]] = [
            {} for _ in candidates
        ]
        evaluations: list[WeightEvaluation | None] = [None] * total_candidates

        if progress_callback is not None:
            progress_callback(iteration_number, None, 0, total_candidates)

        def record_completed_run(request_index, result):
            # run_many ruft diese Funktion im Elternprozess auf, nicht im Worker.
            candidate_index, seed_index = divmod(request_index, seed_count)
            candidate_metrics = metrics_by_candidate[candidate_index]
            if seed_index in candidate_metrics:
                return
            candidate_metrics[seed_index] = result.metrics
            if len(candidate_metrics) != seed_count:
                return

            # Mittelwerte immer in der ursprünglichen Seedreihenfolge berechnen.
            evaluation = self._evaluate_metrics_by_seed(
                candidates[candidate_index],
                tuple(candidate_metrics[index] for index in range(seed_count)),
            )
            evaluations[candidate_index] = evaluation
            if progress_callback is not None:
                progress_callback(
                    iteration_number,
                    evaluation,
                    candidate_index + 1,
                    total_candidates,
                )

        results = tuple(run_many(requests, on_completed=record_completed_run))
        if len(results) != len(requests):
            raise ValueError("Der Runner muss genau ein Ergebnis je Simulationsanfrage liefern.")
        # Auch Runner ohne Abschlussmeldungen unterstützen; keine Ergebnisse doppelt zählen.
        for request_index, result in enumerate(results):
            record_completed_run(request_index, result)
        return [evaluation for evaluation in evaluations if evaluation is not None]

    # Führt für einen Gewichtssatz einen Produktionslauf pro Seed aus.
    # Berechnet je Lauf eine globale Bewertungszahl und danach deren Mittelwert.
    def evaluate_local_weights_across_seeds(
        self,
        local_weights: HeuristicWeights,
        seeds: Iterable[int],
    ) -> WeightEvaluation:
        seed_values = tuple(seeds)
        if not seed_values:
            raise ValueError("Mindestens ein Seed ist erforderlich.")
        run_many = getattr(self.simulation_runner, "run_many", None)
        if callable(run_many):
            requests = tuple(
                SimulationRunRequest(HeuristicPolicyFactory(local_weights), seed)
                for seed in seed_values
            )
            results = tuple(run_many(requests))
            if len(results) != len(requests):
                raise ValueError("Der Runner muss genau ein Ergebnis je Simulationsanfrage liefern.")
            metrics_by_seed = tuple(result.metrics for result in results)
        else:
            # Jeweils einen Lauf simulieren und bewerten, bevor der nächste startet.
            metrics_by_seed = (
                self.simulation_runner.run_policy(
                    HeuristicPolicyFactory(local_weights)(seed), seed
                )
                for seed in seed_values
            )
        return self._evaluate_metrics_by_seed(local_weights, metrics_by_seed)

    # Bewertet die Kennzahlen je Seed und bildet den Mittelwert der Bewertungszahlen.
    def _evaluate_metrics_by_seed(
        self,
        local_weights: HeuristicWeights,
        metrics_by_seed: Iterable[GlobalSimulationMetrics],
    ) -> WeightEvaluation:
        ordered_metrics = []
        objective_values = []
        for metrics in metrics_by_seed:
            ordered_metrics.append(metrics)
            objective_values.append(
                self.global_evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                    metrics
                )
            )
        if not ordered_metrics:
            raise ValueError("Mindestens ein Simulationsergebnis ist erforderlich.")
        objective_values_tuple = tuple(objective_values)
        mean_global_cost = mean(objective_values_tuple)
        return WeightEvaluation(
            weights=local_weights,
            objective_values=objective_values_tuple,
            mean_global_cost=mean_global_cost,
            metrics_by_seed=tuple(ordered_metrics),
        )
