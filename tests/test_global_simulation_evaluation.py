from dataclasses import fields, replace

import pytest

from SpineML.Control.HeuristicControl import (
    GlobalSimulationEvaluation,
    GlobalSimulationMetrics,
    GlobalSimulationWeights,
)


TIME_METRICS = (
    "makespan",
    "total_tardiness",
    "total_transport_time",
    "tool_change_time",
    "blocking_time",
)


def make_metrics(**overrides):
    values = {name: 1.0 for name in TIME_METRICS}
    values.update(overrides)
    return GlobalSimulationMetrics(**values)


def make_evaluation():
    return GlobalSimulationEvaluation(
        GlobalSimulationWeights(
            makespan=5.0,
            total_tardiness=4.0,
            total_transport_time=1.0,
            tool_change_time=1.0,
            blocking_time=1.0,
            rework_job_penalty=3.0,
            scrap_job_penalty=4.0,
            downgrade_job_penalty=3.0,
        )
    )


@pytest.mark.parametrize("makespan", [0.001, 0.5, 1.0, 10.0])
def test_positive_baseline_makespan_is_used_unchanged(makespan):
    evaluation = make_evaluation()
    metrics = make_metrics(makespan=makespan)

    references = evaluation.calculate_baseline_reference_values([metrics])

    assert references["makespan"] == pytest.approx(makespan)
    assert evaluation.metrics_relative_to_baseline(metrics)["makespan"] == pytest.approx(1.0)


def test_makespan_reference_is_the_mean_across_baseline_seeds():
    evaluation = make_evaluation()
    baseline_metrics = [
        make_metrics(makespan=0.2),
        make_metrics(makespan=0.8),
    ]

    references = evaluation.calculate_baseline_reference_values(baseline_metrics)
    candidate = make_metrics(makespan=0.4)

    assert references["makespan"] == pytest.approx(0.5)
    assert evaluation.metrics_relative_to_baseline(candidate)["makespan"] == pytest.approx(0.8)


@pytest.mark.parametrize("metric_name", TIME_METRICS)
def test_zero_baseline_mean_of_any_time_metric_raises_value_error(metric_name):
    evaluation = make_evaluation()
    baseline_metrics = [
        make_metrics(**{metric_name: 0.0}),
        make_metrics(**{metric_name: 0.0}),
    ]

    with pytest.raises(ValueError, match=f"baseline mean {metric_name} must not be zero"):
        evaluation.calculate_baseline_reference_values(baseline_metrics)

    assert evaluation.baseline_reference_values is None


@pytest.mark.parametrize("metric_name", TIME_METRICS)
def test_individual_zero_value_is_allowed_when_the_baseline_mean_is_positive(metric_name):
    evaluation = make_evaluation()
    baseline_metrics = [
        make_metrics(**{metric_name: 0.0}),
        make_metrics(**{metric_name: 0.6}),
    ]

    references = evaluation.calculate_baseline_reference_values(baseline_metrics)

    assert references[metric_name] == pytest.approx(0.3)


def test_each_time_reference_is_its_own_unchanged_baseline_mean():
    evaluation = make_evaluation()
    baseline_metrics = [
        GlobalSimulationMetrics(
            makespan=0.4,
            total_tardiness=0.02,
            total_transport_time=0.2,
            tool_change_time=0.01,
            blocking_time=0.03,
        ),
        GlobalSimulationMetrics(
            makespan=0.6,
            total_tardiness=0.04,
            total_transport_time=0.4,
            tool_change_time=0.03,
            blocking_time=0.07,
        ),
    ]

    references = evaluation.calculate_baseline_reference_values(baseline_metrics)

    assert references == pytest.approx({
        "makespan": 0.5,
        "total_tardiness": 0.03,
        "total_transport_time": 0.3,
        "tool_change_time": 0.02,
        "blocking_time": 0.05,
    })


def test_zero_mean_error_does_not_replace_existing_references():
    evaluation = make_evaluation()
    original_references = evaluation.calculate_baseline_reference_values([make_metrics()])

    with pytest.raises(ValueError, match="baseline mean blocking_time must not be zero"):
        evaluation.calculate_baseline_reference_values([make_metrics(blocking_time=0.0)])

    assert evaluation.baseline_reference_values == original_references


def test_empty_baseline_still_raises_value_error():
    with pytest.raises(ValueError, match="At least one run is required"):
        make_evaluation().calculate_baseline_reference_values([])


def test_global_weights_contain_only_the_eight_selected_objectives():
    assert {field.name for field in fields(GlobalSimulationWeights)} == {
        *TIME_METRICS,
        "rework_job_penalty",
        "scrap_job_penalty",
        "downgrade_job_penalty",
    }


def test_relative_metrics_and_readme_example_use_only_scored_objectives():
    evaluation = make_evaluation()
    evaluation.calculate_baseline_reference_values([
        make_metrics(makespan=9.0, total_tardiness=4.0,
                     total_transport_time=8.0, tool_change_time=2.0),
        make_metrics(makespan=11.0, total_tardiness=4.0,
                     total_transport_time=8.0, tool_change_time=2.0),
    ])
    metrics = GlobalSimulationMetrics(
        makespan=8.0, total_tardiness=2.0, total_transport_time=6.0,
        tool_change_time=1.0, blocking_time=0.0,
        rework_job_count=10, scrap_job_count=20, downgraded_job_count=10,
        total_jobs=100, completed_jobs=100, intact_jobs=80, defect_jobs=40,
    )

    assert evaluation.metrics_relative_to_baseline(metrics) == pytest.approx({
        "makespan": 0.8,
        "total_tardiness": 0.5,
        "total_transport_time": 0.75,
        "tool_change_time": 0.5,
        "blocking_time": 0.0,
        "rework_rate": 0.1,
        "scrap_rate": 0.2,
        "downgrade_rate": 0.1,
    })
    assert evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
        metrics
    ) == pytest.approx(8.65)


@pytest.mark.parametrize("changes", [
    {"defect_jobs": 10},
    {"intact_jobs": 0},
    {"completed_jobs": 9, "unfinished_jobs": 1},
])
def test_information_and_completion_counts_do_not_add_objective_penalties(changes):
    evaluation = make_evaluation()
    evaluation.calculate_baseline_reference_values([make_metrics()])
    metrics = make_metrics(total_jobs=10, completed_jobs=10, intact_jobs=10)
    expected = evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(metrics)

    assert evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
        replace(metrics, **changes)
    ) == expected


@pytest.mark.parametrize(("metric_name", "increase", "expected_cost_increase"), [
    ("makespan", 0.5, 2.5),
    ("total_tardiness", 0.5, 2.0),
    ("total_transport_time", 0.5, 0.5),
    ("tool_change_time", 0.5, 0.5),
    ("blocking_time", 0.5, 0.5),
    ("rework_job_count", 1, 0.3),
    ("scrap_job_count", 1, 0.4),
    ("downgraded_job_count", 1, 0.3),
])
def test_each_retained_objective_still_changes_the_cost(
    metric_name, increase, expected_cost_increase,
):
    evaluation = make_evaluation()
    evaluation.calculate_baseline_reference_values([make_metrics()])
    metrics = make_metrics(total_jobs=10, completed_jobs=10, intact_jobs=10)
    before = evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(metrics)
    changed = replace(metrics, **{metric_name: getattr(metrics, metric_name) + increase})

    after = evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(changed)

    assert after - before == pytest.approx(expected_cost_increase)
