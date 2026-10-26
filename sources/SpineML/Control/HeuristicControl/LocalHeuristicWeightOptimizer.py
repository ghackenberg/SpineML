from __future__ import annotations

import random
from dataclasses import dataclass, fields, replace
from statistics import mean
from typing import Iterable

from .GlobalSimulationEvaluation import GlobalSimulationEvaluation, GlobalSimulationMetrics
from .HeuristicWeights import HeuristicWeights


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
        # Optionale Funktion, die Beginn und Ergebnis jeder Gewichtssatzprüfung erhält.
        progress_callback=None,
    ) -> WeightOptimizationResult:
        """Verbindet Varianten einzelner Gewichte mit zusätzlichen Zufallsgewichtssätzen."""
        # Speichert die Seeds, damit jeder Gewichtssatz mit denselben Seeds geprüft wird.
        seed_values = tuple(seeds)
        # Ausgangssatz, aus dem die Varianten der ersten Iteration erstellt werden.
        current_local_weights = initial_local_weights
        # Betrag, der zu einem Gewicht addiert oder davon abgezogen wird.
        weight_step_fraction = initial_local_weight_step_fraction
        # Speichert die beste Bewertung der ersten Iteration und spätere Verbesserungen.
        best_solution_memory = []
        # Zu Beginn ist noch kein bester Gewichtssatz ausgewählt.
        best_evaluation = None
        # Neustart-Zähler: Iterationen ohne Verbesserung seit der letzten Verbesserung
        # oder dem letzten Neustart.
        iterations_without_improvement = 0
        # Abbruch-Zähler: Iterationen ohne Verbesserung seit der letzten Verbesserung.
        # Ein Neustart setzt diesen Zähler nicht zurück.
        total_iterations_without_improvement = 0
        # Eigener Zufallszahlengenerator für zusätzliche zufällige Gewichtssätze.
        # Fester Seed 0: Jeder neue Optimierungsaufruf beginnt mit derselben Zufallszahlenfolge.
        # Dies ist unabhängig von den Seeds für die Produktionsläufe.
        exploration_rng = random.Random(0)

        # Führt höchstens iterations Iterationen aus; die Abbruchprüfung unten
        # kann die Suche bereits früher beenden.
        for iteration_number in range(1, iterations + 1):
            
            # Behält den aktuellen Gewichtssatz und ergänzt Varianten für jedes einzelne Gewicht.
            candidates = list(
                self.neighboring_weights(
                    current_local_weights,
                    weight_step_fraction,
                )
            )
            # Ergänzt exploration_candidate_count zufällige vollständige Gewichtssätze.
            candidates.extend(
                self.random_local_weight_candidates(
                    exploration_candidate_count, exploration_rng
                )
            )

            # Prüft jeden unterschiedlichen Gewichtssatz mit allen Seeds und wählt
            # den Satz mit der kleinsten mittleren globalen Bewertungszahl.
            iteration_result = self.select_best_local_weight_set_across_seeds(
                candidates,
                seed_values,
                iteration_number=iteration_number,
                progress_callback=progress_callback,
            )

            # Bewertung des besten Gewichtssatzes dieser Iteration.
            # Den zugehörigen Gewichtssatz enthält iteration_best.weights.
            iteration_best = iteration_result.best_evaluation

            # Vergleicht den besten Gewichtssatz dieser Iteration mit dem besten aus vorherigen Iterationen.
            if (
                best_evaluation is None
                or iteration_best.mean_global_cost
                < best_evaluation.mean_global_cost
            ):
                # Übernimmt das Ergebnis dieser Iteration als bisher beste Bewertung.
                best_evaluation = iteration_best
                # Merkt sich diese neue beste Bewertung für den Ergebnisverlauf.
                best_solution_memory.append(iteration_best)
                # Neuer Ausgangssatz für die Varianten der nächsten Iteration.
                current_local_weights = iteration_best.weights
                # Halbiert die Schrittweite für kleinere Änderungen am besten Gewichtssatz.
                weight_step_fraction /= 2.0
                # Beide Zähler beginnen nach der ersten Auswahl oder einer Verbesserung bei 0.
                iterations_without_improvement = 0
                total_iterations_without_improvement = 0
            else:
                # Diese Iteration hat keinen kleineren Mittelwert geliefert.
                # Der bisher beste Gewichtssatz bleibt erhalten.
                # Zählt diese Iteration für einen möglichen Neustart.
                iterations_without_improvement += 1
                # Zählt dieselbe Iteration für den endgültigen Abbruch.
                total_iterations_without_improvement += 1
                # Prüft die Abbruchgrenze vor einem möglichen Neustart.
                # stop_after_no_improvement=None deaktiviert diese Abbruchgrenze.
                if (
                    stop_after_no_improvement is not None
                    and total_iterations_without_improvement
                    >= stop_after_no_improvement
                ):
                    # Beendet die Suche ohne weitere Iteration.
                    break
                # Prüft, ob die Neustartgrenze erreicht ist.
                if iterations_without_improvement >= restart_after_no_improvement:
                    # Ausgangspunkt bleibt der zuletzt gespeicherte beste Gewichtssatz.
                    if best_solution_memory:

                        #best_solution_memory speichert die erste beste Bewertung und
                        # danach nur neue Verbesserungen. Deshalb enthält das letzte Element
                        # den bisher besten Gewichtssatz.
                        remembered_solution = best_solution_memory[-1]
                        current_local_weights = remembered_solution.weights
                    # Ohne gespeicherte beste Bewertung dient ein Zufallssatz als Ausgangspunkt.
                    else:
                        #erzeugt einen vollständigen zufälligen Gewichtssatz. Dabei erhält jedes Gewicht einen Zufallswert.
                        random_weight_sets = self.random_local_weight_candidates(
                            candidate_count=1,
                            rng=exploration_rng,
                        )
                        current_local_weights = random_weight_sets[0]
                    # Setzt die Schrittweite auf ihren Anfangswert zurück.
                    weight_step_fraction = initial_local_weight_step_fraction
                    # Neustart-Zähler zurück auf 0; der Abbruch-Zähler zählt weiter.
                    iterations_without_improvement = 0

        # Ohne ausgeführte Iteration gibt es kein bestes Ergebnis.
        if best_evaluation is None:
            raise ValueError("iterations muss mindestens 1 sein.")

        return WeightOptimizationResult(
            best_weights=best_evaluation.weights,
            best_mean_global_cost=best_evaluation.mean_global_cost,
            best_evaluation=best_evaluation,
            # Nur die erste beste Bewertung und spätere Verbesserungen,
            # nicht sämtliche geprüften Gewichtssätze aller Iterationen.
            evaluations=tuple(best_solution_memory),
        )

    # Erzeugt den aktuellen Gewichtssatz und zwei Varianten pro Gewicht.
    # Pro Variante wird nur dieses eine Gewicht neu gesetzt; die übrigen bleiben unverändert.
    def neighboring_weights(
        self,
        local_weights: HeuristicWeights,
        weight_step_fraction: float,
    ) -> tuple[HeuristicWeights, ...]:
        """Bildet Varianten durch Addieren oder Abziehen der Schrittweite."""
        neighbors = [local_weights]
        for weight_field in fields(local_weights):
            field_name = weight_field.name
            current_value = float(getattr(local_weights, field_name))     
            step = weight_step_fraction
            # Die Minus-Variante wird nach unten auf 0.000001 begrenzt,
            # die Plus-Variante nach oben auf 1.0.
            # An einer Grenze kann eine Variante mit dem Ausgangssatz identisch sein.
            lower_value = max(1e-6, current_value - step)
            higher_value = min(1.0, current_value + step)
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
        """Zieht neue Gewichtswerte unabhängig vom Ausgangssatz und der Schrittweite."""
        candidates = []
        for _ in range(candidate_count):
            values = {}
            for weight_field in fields(HeuristicWeights):
                field_name = weight_field.name
                random_fraction = rng.random()
                # Zufallsbereich von 0.000001 bis 1.0.
                random_value = 1e-6 + random_fraction * (1.0 - 1e-6)
                # Für wait_action_weight gilt die Obergrenze 0.1 statt 1.0.
                if field_name == "wait_action_weight":
                    random_value = 1e-6 + random_fraction * (0.1 - 1e-6)
                values[field_name] = random_value

            # Erstellt einen vollständigen Gewichtssatz aus den gezogenen Werten.
            candidate = HeuristicWeights(**values)
            candidates.append(candidate)
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
        """Gibt den besten Gewichtssatz und alle Gewichtssatzbewertungen dieses Aufrufs zurück."""
        # Hält dieselben Seeds für alle Gewichtssatzprüfungen verfügbar.
        seed_values = tuple(seeds)
        evaluations = []
        # Entfernt doppelte vollständige Gewichtssätze aus der Kandidatenauswahl.
        # Das erste Vorkommen jedes Gewichtssatzes bleibt in der ursprünglichen Reihenfolge erhalten.
        candidate_list = tuple(dict.fromkeys(local_weight_candidates))
        # Anzahl der unterschiedlichen Gewichtssätze in diesem Aufruf.
        total_candidates = len(candidate_list)

        # Prüft die Gewichtssätze nacheinander; ihre Nummerierung beginnt bei 1.
        for candidate_number, local_weights in enumerate(candidate_list, start=1):

            # Meldet Streamlit, welcher Gewichtssatz jetzt mit allen Seeds simuliert und bewertet wird.
            # Dafür wird progress() aus optimization.py aufgerufen; die Funktion aktualisiert state.
            # Gemeldet werden die Iteration, die Gewichtssatznummer und die Anzahl der Sätze dieser Iteration.
            # None bedeutet: Für diesen Gewichtssatz liegt noch kein Bewertungsergebnis vor.
            if progress_callback is not None:
                progress_callback(iteration_number, None, candidate_number, total_candidates)

            # Für diesen einen festen Gewichtssatz: einen vollständigen Produktionslauf pro Seed ausführen.
            # Für jeden Lauf eine globale Bewertungszahl berechnen.
            # Danach den Durchschnitt dieser Bewertungszahlen über alle Seeds bilden.(Für diesen einen festen Gewichtssatz)
            # evaluation.mean_global_cost enthält diesen Durchschnitt für diesen einen Gewichtssatz.
            evaluation = self.evaluate_local_weights_across_seeds(
                local_weights,
                seed_values,
            )
            # Speichert das Ergebnis auch dann, wenn dieser Gewichtssatz nicht der beste ist.
            evaluations.append(evaluation)
            # Meldet dieselben Fortschrittsangaben, jetzt mit der fertigen Bewertung statt None.
            if progress_callback is not None:
                progress_callback(iteration_number, evaluation, candidate_number, total_candidates)
        # Startet den Vergleich mit dem Ergebnis des ersten Gewichtssatzes.
        best_evaluation = evaluations[0]

        # Wählt den kleinsten Mittelwert. Bei Gleichstand bleibt der zuerst geprüfte Satz.
        for evaluation in evaluations:
            # Ein kleinerer Mittelwert bedeutet eine bessere globale Bewertung.
            if evaluation.mean_global_cost < best_evaluation.mean_global_cost:
                best_evaluation = evaluation
        return WeightOptimizationResult(
            best_weights=best_evaluation.weights,
            best_mean_global_cost=best_evaluation.mean_global_cost,
            best_evaluation=best_evaluation,
            # Sämtliche Gewichtssatzbewertungen dieses Aufrufs, nicht nur Verbesserungen.
            evaluations=tuple(evaluations),
        )

    # Führt für einen Gewichtssatz einen Produktionslauf pro Seed aus.
    # Berechnet je Lauf eine globale Bewertungszahl und danach deren Mittelwert.
    def evaluate_local_weights_across_seeds(
        self,
        local_weights: HeuristicWeights,
        seeds: Iterable[int],
    ) -> WeightEvaluation:
        """Bewertet einen Gewichtssatz anhand vollständiger Produktionsläufe mit allen Seeds."""
        objective_values = []
        metrics_by_seed = []
        for seed in seeds:
            # Der Runner startet einen vollständigen Produktionslauf mit diesem Gewichtssatz
            # und Seed. Er liefert die Produktionskennzahlen, noch keine globale Bewertungszahl.
            metrics = self.simulation_runner(local_weights, seed)
            
            metrics_by_seed.append(metrics)
            # Berechnet aus den Kennzahlen die globale Bewertungszahl dieses Laufs.
            weighted_relative_sum = (
                self.global_evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                    metrics
                )
            )
            objective_values.append(weighted_relative_sum)
        # Eine globale Bewertungszahl je Seed, in derselben Reihenfolge wie die Seeds.
        objective_values_tuple = tuple(objective_values)
        # Arithmetischer Mittelwert dieser Bewertungszahlen über alle Seeds.
        mean_global_cost = mean(objective_values_tuple)
        # Bündelt den geprüften Gewichtssatz, seine Ergebnisse je Seed und den Mittelwert.
        return WeightEvaluation(
            # Der geprüfte vollständige lokale Gewichtssatz.
            weights=local_weights,
            # Eine globale Bewertungszahl pro Seed.
            objective_values=objective_values_tuple,
            # Summe der globalen Bewertungszahlen geteilt durch die Anzahl der Seeds.
            mean_global_cost=mean_global_cost,
            # Die Produktionskennzahlen jedes Laufs, in derselben Reihenfolge wie die Seeds.
            metrics_by_seed=tuple(metrics_by_seed),
        )
