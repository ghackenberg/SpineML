from dataclasses import fields

import pytest

from SpineML.Control.HeuristicControl.HeuristicWeights import (
    DEFAULT_DEADLINE_DOWNGRADE_SCORE_MIN,
    DEFAULT_DEADLINE_REWORK_SCORE_MAX,
    DEFAULT_DEADLINE_WAIT_SCORE_MAX,
    EDD_AT_DEADLINE,
    SCORE_MAX,
    HeuristicWeights,
)
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import PolicyObservation


REWORK_ACTIONS = [
    "job_rework_on_defect_machine",
    "job_rework_on_alternative_machine",
]


def make_observation(
    current_time, severity=0.4, *, queue_length=0, mounted_tool="tool",
    remaining_life=9.0, transport_distance=0.0,
):
    return PolicyObservation(
        {
            "time": current_time,
            "configuration_model": {
                "operations_by_id": {
                    "operation": {
                        "tool_type_id": "tool",
                        "consumed_life_units": 1.0,
                    },
                },
            },
            "simulation_object_states_by_id": {
                "job": {
                    "object_type": "order_job",
                    "general_state": "defect",
                    "time": current_time,
                    "latest_end_time": 10.0,
                    "defect_severity": severity,
                    "location": "source",
                },
                "machine": {
                    "object_type": "machine",
                    "object_id": "machine",
                    "corridor_id": "corridor",
                    "input_storage": {"count": queue_length},
                    "mounted_tool_type_id": mounted_tool,
                    "remaining_life_units_by_tool": {"tool": remaining_life},
                },
                "arm": {
                    "object_type": "corridor_arm_robot",
                    "corridor_id": "corridor",
                    "movement_speed": 1.0,
                },
            },
            "store_positions_by_id": {
                "source": {"x": 0.0, "y": 0.0, "z": 0.0},
                "machine in": {"x": transport_distance, "y": 0.0, "z": 0.0},
            },
        },
        "job",
    )


def test_default_defect_parameters_are_derived_from_score_targets():
    weights = HeuristicWeights()

    assert weights.rework_defect_machine_deadline_penalty_weight == pytest.approx(
        SCORE_MAX - DEFAULT_DEADLINE_REWORK_SCORE_MAX
    )
    assert weights.rework_alternative_machine_deadline_penalty_weight == pytest.approx(
        SCORE_MAX - DEFAULT_DEADLINE_REWORK_SCORE_MAX
    )
    assert weights.deadline_missed_wait_penalty_weight == pytest.approx(
        SCORE_MAX - EDD_AT_DEADLINE - DEFAULT_DEADLINE_WAIT_SCORE_MAX
    )
    assert weights.deadline_missed_wait_penalty_weight == pytest.approx(0.2)
    assert weights.product_downgrade_defect_severity_weight == pytest.approx(0.5)
    assert weights.deadline_reached_downgrade_bonus_weight == pytest.approx(0.5)
    assert (
        weights.product_downgrade_defect_severity_weight
        + weights.deadline_reached_downgrade_bonus_weight
    ) == pytest.approx(1.0)


def test_score_targets_are_not_optimizable_weight_fields():
    weight_fields = fields(HeuristicWeights)

    assert len(weight_fields) == 25
    assert all(field.name.endswith("_weight") for field in weight_fields)


@pytest.mark.parametrize("current_time", [10.0, 11.0, 12.0, 1000.0])
def test_defect_wait_cannot_exceed_default_deadline_target(current_time):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_observation(current_time)

    score = evaluator.evaluate_action(
        {"action_type": "wait_job", "payload": {}}, observation,
    )

    edd = evaluator.calculate_edd_priority(10.0, current_time)
    assert edd >= EDD_AT_DEADLINE
    assert score <= DEFAULT_DEADLINE_WAIT_SCORE_MAX + 1e-12
    if current_time == 10.0:
        assert score == pytest.approx(DEFAULT_DEADLINE_WAIT_SCORE_MAX)


@pytest.mark.parametrize("action_type", REWORK_ACTIONS)
@pytest.mark.parametrize("current_time", [10.0, 11.0])
@pytest.mark.parametrize(
    "queue_length, mounted_tool, remaining_life, transport_distance",
    [
        (0, "tool", 1e12, 0.0),
        (0, "tool", 9.0, 2.0),
        (3, "tool", 0.0, 0.0),
        (3, None, 0.0, 2.0),
    ],
)
def test_both_rework_types_obey_default_deadline_target(
    action_type, current_time, queue_length, mounted_tool, remaining_life,
    transport_distance,
):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_observation(
        current_time, queue_length=queue_length, mounted_tool=mounted_tool,
        remaining_life=remaining_life, transport_distance=transport_distance,
    )
    action = {
        "action_type": action_type,
        "payload": {
            "selected_operation_id": "operation",
            "selected_machine_id": "machine",
        },
    }

    score = evaluator.evaluate_action(action, observation)

    assert score <= DEFAULT_DEADLINE_REWORK_SCORE_MAX + 1e-12
    base_score = evaluator.evaluate_defect_recovery_action(
        action_type, action, observation, deadline_reached=False,
    )
    assert score == pytest.approx(base_score - 0.5)


@pytest.mark.parametrize("current_time", [9.0, 10.0, 11.0])
@pytest.mark.parametrize("severity", [0.0, 0.001, 0.2, 0.4, 0.599, 1.0])
def test_default_downgrade_bonus_matches_affine_score_rule(current_time, severity):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_observation(current_time, severity)

    score = evaluator.evaluate_action(
        {"action_type": "downgrade_product", "payload": {}}, observation,
    )

    if current_time < 10.0:
        assert score == pytest.approx(severity)
    else:
        bonus = DEFAULT_DEADLINE_DOWNGRADE_SCORE_MIN * (1.0 - severity)
        assert score == pytest.approx(severity + bonus)
        assert DEFAULT_DEADLINE_DOWNGRADE_SCORE_MIN <= score <= SCORE_MAX
        if severity > 0.0:
            assert score > DEFAULT_DEADLINE_REWORK_SCORE_MAX


@pytest.mark.parametrize("severity", [-0.2, 1.2])
def test_deadline_downgrade_formula_does_not_clamp_inputs(severity):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())

    score = evaluator.evaluate_action(
        {"action_type": "downgrade_product", "payload": {}},
        make_observation(10.0, severity),
    )

    assert score == pytest.approx(severity + 0.5 * (1.0 - severity))
