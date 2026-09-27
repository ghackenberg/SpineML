from __future__ import annotations

import random
from dataclasses import dataclass, fields, replace
from statistics import mean
from typing import Iterable

from .GlobalSimulationEvaluation import GlobalSimulationEvaluation, GlobalSimulationMetrics
from .HeuristicWeights import HeuristicWeights


@dataclass(frozen=True)
class WeightEvaluation:
    """Ergebnis eines Gewichtssatzes über alle verwendeten Zufalls-Seeds."""
    weights: HeuristicWeights
    objective_values: tuple[float, ...]
    mean_global_cost: float
    metrics_by_seed: tuple[GlobalSimulationMetrics, ...] = ()


@dataclass(frozen=True)
class WeightOptimizationResult:
    """Bestes Ergebnis und Gedächtnis der bisherigen Verbesserungen."""
    best_weights: HeuristicWeights
    best_mean_global_cost: float
    best_evaluation: WeightEvaluation
    evaluations: tuple[WeightEvaluation, ...]


class LocalHeuristicWeightOptimizer:
    """Vergleicht lokale Gewichtssätze über vollständige Simulationsläufe."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, simulation_runner, global_evaluation: GlobalSimulationEvaluation):
        self.simulation_runner = simulation_runner
        self.global_evaluation = global_evaluation

    # Erzeugt und vergleicht iterativ lokale Gewichtssätze über mehrere Seeds
    # und gibt das beste Optimierungsergebnis zurück.
    def optimize_iteratively(
        self,
        initial_local_weights: HeuristicWeights,
        seeds: Iterable[int],
        iterations: int = 5,
        initial_local_weight_step_fraction: float = 0.25,
        exploration_candidate_count: int = 10,
        restart_after_no_improvement: int = 2,
        stop_after_no_improvement: int | None = 6,
        # Optionale Funktion für Fortschrittsmeldungen an den Streamlit-Webserver.
        progress_callback=None,
    ) -> WeightOptimizationResult:
        """Kombiniert lokale Nachbarschaftssuche mit kontrollierter Exploration."""
        # Macht die übergebenen Seeds für alle Kandidatenläufe wiederverwendbar.
        seed_values = tuple(seeds)
        # Setzt den aktuell getesteten Gewichtssatz auf die Startgewichte.
        current_local_weights = initial_local_weights
        # Setzt die anfängliche Größe der Gewichtsänderungen fest.
        weight_step_fraction = initial_local_weight_step_fraction
        # Speichert den besten Kandidaten jeder bisher erfolgreichen Runde.
        best_solution_memory = []
        # Enthält zunächst noch keine globale beste Bewertung.
        best_evaluation = None
        # Zählt aufeinanderfolgende Runden ohne Verbesserung.
        rounds_without_improvement = 0
        # Zählt erfolglose Runden seit der letzten Verbesserung für den Abbruch.
        total_rounds_without_improvement = 0
        # Erzeugt reproduzierbare Zufallskandidaten für die Exploration.
        exploration_rng = random.Random(0)

        # Durchläuft die festgelegten Optimierungsrunden (je Runde werden
        # Gewichtskandidaten erzeugt, simuliert und verglichen) von 1 bis iterations.
        for iteration_number in range(1, iterations + 1):
            
            # Erzeugt den unveränderten Gewichtssatz sowie je Gewicht eine kleinere
            # und eine größere Variante.
            candidates = list(
                self.neighboring_weights(
                    current_local_weights,
                    weight_step_fraction,
                )
            )
            # Erweitert candidates um exploration_candidate_count zufällige lokale
            # Gewichtssätze; exploration_rng macht diese Auswahl reproduzierbar.
            candidates.extend(
                self.random_local_weight_candidates(
                    exploration_candidate_count, exploration_rng
                )
            )

            # Gibt den besten lokalen Gewichtssatz, den Mittelwert seiner gewichteten
            # Baseline-relativen Kennzahlensumme und alle Kandidatenbewertungen zurück.
            iteration_result = self.select_best_local_weight_set_across_seeds(
                candidates,
                seed_values,
                iteration_number=iteration_number,
                progress_callback=progress_callback,
            )

            # Übernimmt das beste WeightEvaluation-Objekt dieser Runde; der lokale
            # Gewichtssatz steht darin unter iteration_best.weights.
            iteration_best = iteration_result.best_evaluation

            # Prüft, ob erstmals ein Gesamtbester vorliegt oder die aktuelle
            # Runde eine kleinere mittlere gewichtete Summe erreicht.
            if (
                best_evaluation is None
                or iteration_best.mean_global_cost
                < best_evaluation.mean_global_cost
            ):
                # Übernimmt den besten Kandidaten der aktuellen Runde als Gesamtbesten.
                best_evaluation = iteration_best
                # Speichert diese verbesserte Lösung im Verlauf der Optimierung.
                best_solution_memory.append(iteration_best)
                # Verwendet dessen Gewichtssatz als Ausgangspunkt für die nächste Runde.
                current_local_weights = iteration_best.weights
                # Verkleinert die Änderungsschritte für eine genauere lokale Suche.
                weight_step_fraction /= 2.0
                # Setzt den Zähler für aufeinanderfolgende erfolglose Runden zurück.
                rounds_without_improvement = 0
                # Setzt auch den Abbruchzähler nach einer Verbesserung zurück.
                total_rounds_without_improvement = 0
            else:
                # Zählt erfolglose Runden bis zum nächsten Neustart.
                rounds_without_improvement += 1
                # Zählt erfolglose Runden bis zum endgültigen Abbruch;
                # dieser Zähler wird bei einem Neustart nicht zurückgesetzt.
                total_rounds_without_improvement += 1
                # Prüft, ob die maximal erlaubte Anzahl erfolgloser Runden erreicht ist.
                if (
                    stop_after_no_improvement is not None
                    and total_rounds_without_improvement
                    >= stop_after_no_improvement
                ):
                    # Beendet die Optimierung wegen ausbleibender Verbesserung.
                    break
                # Prüft, ob ein Neustart der lokalen Suche ausgelöst werden soll.
                if rounds_without_improvement >= restart_after_no_improvement:
                    # Verwendet die zuletzt gespeicherte verbesserte Lösung als Neustartpunkt.
                    if best_solution_memory:
                        remembered_solution = best_solution_memory[-1]
                        current_local_weights = remembered_solution.weights
                    # Ohne gespeicherte Lösung wird ein neuer zufälliger Gewichtssatz erzeugt.
                    else:
                        current_local_weights = self.random_local_weight_candidates(
                            1, exploration_rng
                        )[0]
                    # Setzt die Suchschrittweite für den Neustart auf den Anfangswert zurück.
                    weight_step_fraction = initial_local_weight_step_fraction
                    # Beginnt die Zählung erfolgloser Runden für den Neustart von vorn.
                    rounds_without_improvement = 0

        if best_evaluation is None:
            raise ValueError("iterations muss mindestens 1 sein.")

        return WeightOptimizationResult(
            best_weights=best_evaluation.weights,
            best_mean_global_cost=best_evaluation.mean_global_cost,
            best_evaluation=best_evaluation,
            evaluations=tuple(best_solution_memory),
        )

    # Erzeugt den aktuellen Gewichtssatz sowie für jedes Gewicht eine kleinere
    # und eine größere Variante innerhalb des Bereichs (0.0, 1.0].
    def neighboring_weights(
        self,
        local_weights: HeuristicWeights,
        weight_step_fraction: float,
    ) -> tuple[HeuristicWeights, ...]:
        """Erzeugt den aktuellen Gewichtssatz sowie kleinere und größere Nachbarn."""
        neighbors = [local_weights]
        for weight_field in fields(local_weights):
            field_name = weight_field.name
            current_value = float(getattr(local_weights, field_name))     
            step = weight_step_fraction
            lower_value = max(1e-6, current_value - step)
            higher_value = min(1.0, current_value + step)
            neighbors.append(replace(local_weights, **{field_name: lower_value}))
            neighbors.append(replace(local_weights, **{field_name: higher_value}))
        return tuple(neighbors)

    # Erzeugt candidate_count vollständige lokale Gewichtssätze mit Zufallswerten.
    # wait_action_gewicht wird auf (0.0, 0.1] begrenzt; rng sorgt für Reproduzierbarkeit.
    def random_local_weight_candidates(
        self,
        candidate_count: int,
        rng: random.Random,
    ) -> tuple[HeuristicWeights, ...]:
        """Erzeugt zufällige lokale Gewichtssätze für die Exploration."""
        candidates = []
        for _ in range(candidate_count):
            values = {}
            for weight_field in fields(HeuristicWeights):
                field_name = weight_field.name
                random_fraction = rng.random()
                random_value = 1e-6 + random_fraction * (1.0 - 1e-6)
                # Hält das Gewicht für Warteaktionen deutlich kleiner als andere Gewichte.
                if field_name == "wait_action_gewicht":
                    random_value = 1e-6 + random_fraction * (0.1 - 1e-6)
                values[field_name] = random_value

            # Fasst alle Zufallswerte zu einem vollständigen lokalen Gewichtssatz zusammen.
            candidate = HeuristicWeights(**values)
            # Fügt den vollständigen Gewichtssatz der Kandidatenliste hinzu.
            candidates.append(candidate)
        return tuple(candidates)

    # Bewertet jeden lokalen Gewichtskandidaten über alle Seeds und wählt
    # den Kandidaten mit der niedrigsten mittleren gewichteten Summe.
    def select_best_local_weight_set_across_seeds(
        self,
        local_weight_candidates: Iterable[HeuristicWeights],
        seeds: Iterable[int],
        iteration_number: int = 0,
        progress_callback=None,
    ) -> WeightOptimizationResult:
        """Vergleicht Gewichtskandidaten über alle Seeds und gibt den besten zurück."""
        seed_values = tuple(seeds)
        evaluations = []
        candidate_list = tuple(local_weight_candidates)
        total_candidates = len(candidate_list)

        # Durchläuft jeden vollständigen lokalen Gewichtssatz und nummeriert ihn ab 1.
        for candidate_number, local_weights in enumerate(candidate_list, start=1):

            # Meldet nur den Beginn der Kandidatenbewertung an den Streamlit-Webserver;
            # die Optimierungsentscheidung wird dadurch nicht verändert.
            if progress_callback is not None:
                progress_callback(iteration_number, None, candidate_number, total_candidates)
            # Bewertet den aktuell getesteten lokalen Gewichtssatz über alle Seeds;
            # dieser Kandidat ist noch nicht zwingend der beste.
            evaluation = self.evaluate_local_weights_across_seeds(
                local_weights,
                seed_values,
            )
            evaluations.append(evaluation)
            # Meldet das fertige Bewertungsergebnis dieses Kandidaten an den Streamlit-Webserver.
            if progress_callback is not None:
                progress_callback(iteration_number, evaluation, candidate_number, total_candidates)
        # Startet mit dem Ergebnis des ersten lokalen Gewichtssatzes als vorläufigem Besten.
        best_evaluation = evaluations[0]

        # Vergleicht alle Ergebnisse und sucht die niedrigste mittlere gewichtete relative Summe.
        for evaluation in evaluations:
            # Ersetzt den bisher besten Kandidaten, wenn dieser Kandidat besser ist.
            if evaluation.mean_global_cost < best_evaluation.mean_global_cost:
                best_evaluation = evaluation
        return WeightOptimizationResult(
            best_weights=best_evaluation.weights,
            best_mean_global_cost=best_evaluation.mean_global_cost,
            best_evaluation=best_evaluation,
            evaluations=tuple(evaluations),
        )

    # Simuliert einen lokalen Gewichtssatz mit allen Seeds, berechnet pro Seed
    # die gewichtete relative Summe und bildet daraus den Mittelwert.
    def evaluate_local_weights_across_seeds(
        self,
        local_weights: HeuristicWeights,
        seeds: Iterable[int],
    ) -> WeightEvaluation:
        """Simuliert einen lokalen Gewichtssatz und bildet sein mittleres Ergebnis."""
        objective_values = []
        metrics_by_seed = []
        for seed in seeds:
            # Startet die Simulation mit dem lokalen Gewichtssatz und diesem Seed.
            # metrics enthält danach die rohen globalen Kennzahlen ohne Baseline-Skalierung.
            metrics = self.simulation_runner(local_weights, seed)
            
            metrics_by_seed.append(metrics)
            # Berechnet die gewichtete Summe der globalen Kennzahlen relativ zur Baseline.
            weighted_relative_sum = (
                self.global_evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                    metrics
                )
            )
            objective_values.append(weighted_relative_sum)
        # Bündelt die gewichtete Summe jedes Seeds in einem unveränderlichen Tupel.
        objective_values_tuple = tuple(objective_values)
        mean_global_cost = mean(objective_values_tuple)
        # Erzeugt ein WeightEvaluation-Objekt für den aktuell getesteten lokalen
        # Gewichtssatz und dessen Ergebnisse über alle Seeds.
        return WeightEvaluation(
            # Speichert den aktuell getesteten vollständigen lokalen Gewichtssatz.
            weights=local_weights,
            # Speichert die gewichtete relative Summe der globalen Kennzahlen für jeden Seed.
            objective_values=objective_values_tuple,
            # (Summe Seed 1 + Summe Seed 2 + ...) / Anzahl der Seeds
            mean_global_cost=mean_global_cost,
            # Speichert die rohen globalen Kennzahlen für jeden einzelnen Seed.
            metrics_by_seed=tuple(metrics_by_seed),
        )
