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
