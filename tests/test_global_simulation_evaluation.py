import pytest

from SpineML.Control.HeuristicControl import (
    GlobalSimulationEvaluation,
    GlobalSimulationMetrics,
    GlobalSimulationWeights,
)


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
            unfinished_jobs=20.0,
        )
    )


@pytest.mark.parametrize("makespan", [0.001, 0.5, 1.0, 10.0])
def test_positive_baseline_makespan_is_used_unchanged(makespan):
    evaluation = make_evaluation()
    metrics = GlobalSimulationMetrics(makespan=makespan, total_tardiness=0.0)

    references = evaluation.calculate_baseline_reference_values([metrics])

    assert references["makespan"] == pytest.approx(makespan)
    assert evaluation.metrics_relative_to_baseline(metrics)["makespan"] == pytest.approx(1.0)


def test_makespan_reference_is_the_mean_across_baseline_seeds():
    evaluation = make_evaluation()
    baseline_metrics = [
        GlobalSimulationMetrics(makespan=0.2, total_tardiness=0.0),
        GlobalSimulationMetrics(makespan=0.8, total_tardiness=0.0),
    ]

    references = evaluation.calculate_baseline_reference_values(baseline_metrics)
    candidate = GlobalSimulationMetrics(makespan=0.4, total_tardiness=0.0)

    assert references["makespan"] == pytest.approx(0.5)
    assert evaluation.metrics_relative_to_baseline(candidate)["makespan"] == pytest.approx(0.8)


@pytest.mark.parametrize("makespans", [[0.0], [0.0, 0.0]])
def test_zero_baseline_mean_makespan_raises_value_error(makespans):
    evaluation = make_evaluation()
    baseline_metrics = [
        GlobalSimulationMetrics(makespan=value, total_tardiness=0.0)
        for value in makespans
    ]

    with pytest.raises(ValueError, match="baseline mean makespan must not be zero"):
        evaluation.calculate_baseline_reference_values(baseline_metrics)

    assert evaluation.baseline_reference_values is None


def test_other_zero_time_references_use_the_unchanged_makespan_mean():
    evaluation = make_evaluation()
    baseline_metrics = [
        GlobalSimulationMetrics(
            makespan=0.4, total_tardiness=0.0, total_transport_time=0.2,
        ),
        GlobalSimulationMetrics(
            makespan=0.6, total_tardiness=0.0, total_transport_time=0.4,
        ),
    ]

    references = evaluation.calculate_baseline_reference_values(baseline_metrics)

    assert references == pytest.approx({
        "makespan": 0.5,
        "total_tardiness": 0.5,
        "total_transport_time": 0.3,
        "tool_change_time": 0.5,
        "blocking_time": 0.5,
    })


def test_empty_baseline_still_raises_value_error():
    with pytest.raises(ValueError, match="At least one run is required"):
        make_evaluation().calculate_baseline_reference_values([])
