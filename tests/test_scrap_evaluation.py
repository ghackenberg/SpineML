from dataclasses import fields

import pytest

from SpineML.Control.GeneralControl.ActionGenerators import SpineActionGenerator
from SpineML.Control.GeneralControl.ActionSelectors import BaselineActionSelector
from SpineML.Control.HeuristicControl.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import PolicyObservation


def make_scrap_observation(current_time, severity=0.8):
    job = {
        "object_type": "order_job",
        "general_state": "defect",
        "completed_time": None,
        "due_state": None,
        "defect_product_state_before": "raw",
        "defect_severity": severity,
        "time": current_time,
        "latest_end_time": 10.0,
    }
    return PolicyObservation(
        {
            "time": current_time,
            "simulation_object_states_by_id": {"job": job},
        },
        "job",
    )


@pytest.mark.parametrize("current_time", [0.0, 10.0, 11.0, 100.0])
def test_scrap_score_is_constant_regardless_of_deadline(current_time):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_scrap_observation(current_time)

    score = evaluator.evaluate_action(
        {"action_type": "job_scrap", "payload": {}}, observation
    )

    assert score == 1.0


def test_scrap_score_does_not_require_time_or_deadline():
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = PolicyObservation(
        {
            "simulation_object_states_by_id": {
                "job": {"object_type": "order_job", "general_state": "defect"},
            },
        },
        "job",
    )

    score = evaluator.evaluate_action(
        {"action_type": "job_scrap", "payload": {}}, observation
    )

    assert score == 1.0


@pytest.mark.parametrize("severity", [0.0, 0.0005, 0.6, 0.99])
def test_scrap_remains_the_only_candidate_and_is_selected(severity):
    observation = make_scrap_observation(11.0, severity)
    actions = SpineActionGenerator().generate_actions(observation)
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())

    assert len(actions) == 1
    assert actions[0]["action_type"] == "job_scrap"

    decision = BaselineActionSelector().select_action(
        actions, evaluator=evaluator, observation=observation, target_id="job"
    )

    assert len(decision.actions) == 1
    assert decision.actions[0].target_id == "job"
    assert decision.actions[0].action_type == "job_scrap"


def test_scrap_has_no_heuristic_weights():
    weight_names = {field.name for field in fields(HeuristicWeights)}

    assert "job_scrap_weight" not in weight_names
    assert "deadline_pressure_scrap_bonus_weight" not in weight_names
