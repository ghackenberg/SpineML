import math
import random
from collections import Counter
from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

from SpineML.Control.HeuristicControl import (
    GlobalSimulationMetrics,
    HeuristicWeights,
    LocalHeuristicWeightOptimizer,
)


def make_optimizer():
    calls = []

    def runner(weights, seed):
        calls.append((weights, seed))
        return GlobalSimulationMetrics(
            makespan=weights.release_edd_weight + seed,
            total_tardiness=0.0,
        )

    evaluation = SimpleNamespace(
        calculate_weighted_sum_of_metrics_relative_to_baseline=lambda metrics: metrics.makespan,
    )
    return LocalHeuristicWeightOptimizer(runner, evaluation), calls


def test_identical_weight_sets_are_evaluated_once_with_every_seed():
    optimizer, calls = make_optimizer()
    first = HeuristicWeights()
    second = replace(first, release_edd_weight=0.4)
    candidates = (candidate for candidate in (
        first, replace(first), first, second, replace(second), second,
    ))

    result = optimizer.select_best_local_weight_set_across_seeds(
        candidates, iter((1, 2)),
    )

    assert calls == [(first, 1), (first, 2), (second, 1), (second, 2)]
    assert [item.weights for item in result.evaluations] == [first, second]
    assert result.evaluations[0].objective_values == pytest.approx((1.7, 2.7))
    assert result.evaluations[1].mean_global_cost == pytest.approx(1.9)
    assert result.best_weights is second


def test_first_seen_order_and_progress_use_only_distinct_weight_sets():
    optimizer, _ = make_optimizer()
    first = HeuristicWeights(release_edd_weight=0.4)
    second = HeuristicWeights()
    progress = []

    result = optimizer.select_best_local_weight_set_across_seeds(
        [first, replace(first), second, first, replace(second)],
        [7],
        iteration_number=4,
        progress_callback=lambda *args: progress.append(args),
    )

    assert result.evaluations[0].weights is first
    assert result.evaluations[1].weights is second
    assert progress == [
        (4, None, 1, 2),
        (4, result.evaluations[0], 1, 2),
        (4, None, 2, 2),
        (4, result.evaluations[1], 2, 2),
    ]


@pytest.mark.parametrize("field_name", [field.name for field in fields(HeuristicWeights)])
def test_a_difference_in_any_weight_keeps_both_sets(field_name):
    optimizer, calls = make_optimizer()
    first = HeuristicWeights()
    second = replace(first, **{field_name: getattr(first, field_name) / 2.0})

    result = optimizer.select_best_local_weight_set_across_seeds(
        [first, replace(first), second, replace(second)], [1, 2],
    )

    assert [item.weights for item in result.evaluations] == [first, second]
    assert calls == [(first, 1), (first, 2), (second, 1), (second, 2)]


def test_close_but_different_weight_values_are_not_rounded_or_merged():
    optimizer, calls = make_optimizer()
    first = HeuristicWeights()
    second = replace(
        first, release_edd_weight=math.nextafter(first.release_edd_weight, 1.0),
    )

    result = optimizer.select_best_local_weight_set_across_seeds(
        [first, second, replace(second)], [1, 2],
    )

    assert len(result.evaluations) == 2
    assert len(calls) == 4


def test_default_first_round_evaluates_53_sets_instead_of_54_entries():
    optimizer, calls = make_optimizer()
    initial = HeuristicWeights()
    neighbors = optimizer.neighboring_weights(initial, 0.4)
    random_sets = optimizer.random_local_weight_candidates(3, random.Random(0))

    result = optimizer.select_best_local_weight_set_across_seeds(
        neighbors + random_sets, [1, 2],
    )

    assert len(neighbors + random_sets) == 54
    assert len(result.evaluations) == 53
    assert len(calls) == 106
    assert set(Counter(weights for weights, _ in calls).values()) == {2}
    assert result.evaluations[0].weights is initial


def test_combined_duplicates_are_removed_per_round_without_cross_round_cache(monkeypatch):
    optimizer, calls = make_optimizer()
    initial = HeuristicWeights()
    progress = []
    monkeypatch.setattr(
        optimizer,
        "neighboring_weights",
        lambda current, step: (current, replace(current)),
    )
    monkeypatch.setattr(
        optimizer,
        "random_local_weight_candidates",
        lambda count, rng: tuple(replace(initial) for _ in range(count)),
    )

    result = optimizer.optimize_iteratively(
        initial,
        seeds=[1, 2],
        iterations=2,
        exploration_candidate_count=3,
        progress_callback=lambda *args: progress.append(args),
    )

    assert calls == [(initial, 1), (initial, 2), (initial, 1), (initial, 2)]
    assert {(iteration, count) for iteration, _, _, count in progress} == {(1, 1), (2, 1)}
    assert result.best_weights is initial


def test_two_default_sized_rounds_can_have_53_then_54_distinct_candidates():
    optimizer, calls = make_optimizer()
    target = optimizer.random_local_weight_candidates(3, random.Random(0))[0]
    progress = []

    def runner(weights, seed):
        calls.append((weights, seed))
        distance = sum(
            abs(getattr(weights, field.name) - getattr(target, field.name))
            for field in fields(HeuristicWeights)
        )
        return GlobalSimulationMetrics(makespan=1.0 + distance, total_tardiness=0.0)

    optimizer.simulation_runner = runner

    result = optimizer.optimize_iteratively(
        HeuristicWeights(),
        seeds=[1, 2],
        iterations=2,
        initial_local_weight_step_fraction=0.4,
        exploration_candidate_count=3,
        progress_callback=lambda *args: progress.append(args),
    )

    assert {(iteration, count) for iteration, _, _, count in progress} == {(1, 53), (2, 54)}
    assert len(calls) == 107 * 2
    assert result.best_weights == target
