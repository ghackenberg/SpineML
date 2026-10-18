from types import SimpleNamespace

import pytest

from SpineML.Control.GeneralControl.ActionSelectors import BaselineActionSelector
from SpineML.Control.HeuristicControl.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import (
    ConfigurationObjectObserver,
    PolicyObservation,
)


def make_rework_observation(current_time):
    operation = SimpleNamespace(
        name="operation",
        duration=4.0,
        consumes_life_units=5.0,
        defect_probability=0.1,
        machine_type=SimpleNamespace(name="machine_type"),
        tool_type=SimpleNamespace(name="tool"),
        consumes_product_type=SimpleNamespace(name="raw"),
        produces_product_type=SimpleNamespace(name="finished"),
    )
    model = ConfigurationObjectObserver.build_policy_configuration_model(
        product_types=[],
        operation_types=[operation],
        machines=[],
        tool_types=[],
        corridors=[],
        layouts=[],
    )
    states = {
        "job": {
            "object_type": "order_job",
            "general_state": "defect",
            "time": current_time,
            "latest_end_time": 10.0,
            "location": "source",
        },
        "arm": {
            "object_type": "corridor_arm_robot",
            "corridor_id": "corridor",
            "movement_speed": 1.0,
        },
    }
    for machine_id, queue_length in [("defect_machine", 9), ("alternative_machine", 2)]:
        states[machine_id] = {
            "object_type": "machine",
            "object_id": machine_id,
            "corridor_id": "corridor",
            "input_storage": {"count": queue_length},
            "mounted_tool_type_id": None,
            "remaining_life_units_by_tool": {"tool": 5.0},
        }
    return PolicyObservation(
        {
            "time": current_time,
            "configuration_model": model,
            "simulation_object_states_by_id": states,
            "store_positions_by_id": {
                "source": {"x": 0, "y": 0, "z": 0},
                "alternative_machine in": {"x": 1, "y": 0, "z": 0},
            },
        },
        "job",
    )


def rework_action(action_type, machine_id):
    return {
        "action_type": action_type,
        "payload": {
            "selected_operation_id": "operation",
            "selected_machine_id": machine_id,
        },
    }


@pytest.mark.parametrize(
    "action_type, machine_id, score_before_penalty",
    [
        ("job_rework_on_defect_machine", "defect_machine", 13.0 / 70.0),
        ("job_rework_on_alternative_machine", "alternative_machine", 1.0 / 3.0),
    ],
)
@pytest.mark.parametrize("current_time", [8.0, 10.0, 11.0])
def test_rework_returns_score_minus_penalty_without_clamping(
    action_type, machine_id, score_before_penalty, current_time
):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_rework_observation(current_time)
    expected_score = score_before_penalty - (0.5 if current_time >= 10.0 else 0.0)

    score = evaluator.evaluate_action(
        rework_action(action_type, machine_id), observation
    )

    assert score == pytest.approx(expected_score)


@pytest.mark.parametrize("random_draw", [0.0, 1.0])
def test_selector_preserves_ranking_of_negative_defect_scores(monkeypatch, random_draw):
    monkeypatch.setattr(
        "SpineML.Control.GeneralControl.ActionSelectors.random.random",
        lambda: random_draw,
    )
    monkeypatch.setattr(
        "SpineML.Control.GeneralControl.ActionSelectors.random.choice",
        lambda candidates: candidates[0],
    )
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_rework_observation(11.0)
    actions = [
        rework_action("job_rework_on_defect_machine", "defect_machine"),
        rework_action("job_rework_on_alternative_machine", "alternative_machine"),
    ]

    decision = BaselineActionSelector().select_action(
        actions, evaluator=evaluator, observation=observation, target_id="job"
    )

    assert len(decision.actions) == 1
    assert decision.actions[0].target_id == "job"
    assert decision.actions[0].action_type == "job_rework_on_alternative_machine"
