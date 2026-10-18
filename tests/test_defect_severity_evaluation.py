import pytest

from SpineML.Control.HeuristicControl.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import PolicyObservation


@pytest.mark.parametrize("severity", [-0.2, 0.0, 0.2, 0.5, 0.99, 1.2])
def test_downgrade_uses_severity_without_clamping(severity):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    job = {
        "object_type": "order_job",
        "general_state": "defect",
        "time": 5.0,
        "latest_end_time": 10.0,
        "defect_severity": severity,
    }
    observation = PolicyObservation(
        {
            "time": 5.0,
            "simulation_object_states_by_id": {"job": job},
        },
        "job",
    )

    score = evaluator.evaluate_action(
        {"action_type": "downgrade_product", "payload": {}},
        observation,
    )

    assert score == pytest.approx(severity)


@pytest.mark.parametrize("current_time, expected", [(8.0, False), (10.0, True), (11.0, True)])
def test_deadline_reached_checks_current_time(current_time, expected):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())

    assert evaluator.is_deadline_reached({
        "time": current_time,
        "latest_end_time": 10.0,
    }) is expected


@pytest.mark.parametrize("current_time, expected_score", [(8.0, 0.4), (10.0, 0.7), (11.0, 0.7)])
def test_downgrade_bonus_starts_at_deadline(current_time, expected_score):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    job = {
        "object_type": "order_job",
        "general_state": "defect",
        "time": current_time,
        "latest_end_time": 10.0,
        "defect_severity": 0.4,
    }
    observation = PolicyObservation(
        {
            "time": current_time,
            "simulation_object_states_by_id": {"job": job},
        },
        "job",
    )

    assert evaluator.evaluate_action(
        {"action_type": "downgrade_product", "payload": {}}, observation
    ) == pytest.approx(expected_score)


def test_downgrade_uses_configured_deadline_bonus_weight():
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights(
        product_downgrade_defect_severity_weight=0.6,
        deadline_reached_downgrade_bonus_weight=0.2,
    ))
    job = {
        "object_type": "order_job",
        "general_state": "defect",
        "time": 11.0,
        "latest_end_time": 10.0,
        "defect_severity": 0.4,
    }
    observation = PolicyObservation(
        {
            "time": 11.0,
            "simulation_object_states_by_id": {"job": job},
        },
        "job",
    )

    assert evaluator.evaluate_action(
        {"action_type": "downgrade_product", "payload": {}}, observation
    ) == pytest.approx(0.55)
