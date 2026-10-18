from copy import deepcopy
from types import SimpleNamespace

import pytest

from SpineML.Control.HeuristicControl.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import (
    ConfigurationObjectObserver,
    PolicyObservation,
)


def make_observation(action_type, remaining_life, consumed_life):
    operation = SimpleNamespace(
        name="operation",
        duration=4.0,
        consumes_life_units=consumed_life,
        defect_probability=0.0,
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
    machine = {
        "object_id": "machine",
        "object_type": "machine",
        "corridor_id": "corridor",
        "mounted_tool_type_id": "tool",
        "remaining_life_units_by_tool": {"tool": remaining_life},
        "input_storage": {
            "store_id": "machine in",
            "count": 2,
            "job_summaries": [{
                "job_id": "job",
                "selected_operation_id": "operation",
                "latest_end_time": 10.0,
            }],
        },
    }
    job = {
        "object_type": "order_job",
        "general_state": "defect",
        "location": "start_storage",
        "time": 10.0,
        "latest_end_time": 20.0,
    }
    snapshot = {
        "time": 10.0,
        "configuration_model": model,
        "simulation_object_states_by_id": {
            "machine": machine,
            "job": job,
            "arm": {
                "object_type": "corridor_arm_robot",
                "corridor_id": "corridor",
                "movement_speed": 1.5,
            },
        },
        "store_positions_by_id": {
            "start_storage": {"x": 0, "y": 0, "z": 0},
            "machine in": {"x": 3, "y": 0, "z": 0},
        },
    }
    if action_type == "pick_machine_job":
        current_object_id = "machine"
        payload = {"selected_job_id": "job", "target_store_id": "machine in"}
    else:
        current_object_id = "job"
        payload = {
            "selected_operation_id": "operation",
            "selected_machine_id": "machine",
        }
    return (
        PolicyObservation(snapshot, current_object_id),
        {"action_type": action_type, "payload": payload},
    )


@pytest.mark.parametrize("action_type", [
    "pick_machine_job",
    "job_rework_on_defect_machine",
    "job_rework_on_alternative_machine",
])
@pytest.mark.parametrize("remaining_life", [-1.0, 0.0, 4.0, 20.0])
@pytest.mark.parametrize("consumed_life", [0.0, 2.0])
@pytest.mark.parametrize("mounted_tool_id", ["tool", "other_tool", None])
def test_tool_reserve_uses_consumption_from_configuration_observer(
    action_type, remaining_life, consumed_life, mounted_tool_id,
):
    weights = HeuristicWeights()
    evaluator = LocalHeuristicActionEvaluator(weights)
    observation, action = make_observation(
        action_type, remaining_life, consumed_life,
    )
    observation.simulation_configuration_snapshot[
        "simulation_object_states_by_id"
    ]["machine"]["mounted_tool_type_id"] = mounted_tool_id
    prepared_action = evaluator.prepare_action_candidate(action, observation)
    tool_match_value = 1.0 if mounted_tool_id == "tool" else 0.0

    if action_type == "pick_machine_job":
        parts = [
            (0.5, weights.queue_priority_weight),
            (0.2, weights.machine_pick_operation_duration_weight),
            (tool_match_value, weights.machine_pick_tool_match_weight),
        ]
        reserve_weight = weights.machine_pick_tool_reserve_weight
    else:
        parts = [
            (1 / 3, weights.defect_recovery_machine_queue_length_weight),
            (tool_match_value, weights.defect_recovery_tool_match_weight),
        ]
        parts.append((1 / 3, weights.defect_recovery_transport_time_weight))
        reserve_weight = weights.defect_recovery_tool_reserve_weight

    if consumed_life > 0:
        reserve_value = remaining_life / (remaining_life + consumed_life)
        parts.append((reserve_value, reserve_weight))
    expected_score = sum(value * weight for value, weight in parts) / sum(
        weight for _, weight in parts
    )

    assert evaluator.evaluate_action(prepared_action, observation) == pytest.approx(
        expected_score,
    )


@pytest.mark.parametrize("action_type", [
    "pick_machine_job",
    "job_rework_on_defect_machine",
    "job_rework_on_alternative_machine",
])
def test_operation_requires_tool_type_id(action_type):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation, action = make_observation(action_type, 4.0, 2.0)
    del observation.simulation_configuration_snapshot[
        "configuration_model"
    ]["operations_by_id"]["operation"]["tool_type_id"]
    prepared_action = evaluator.prepare_action_candidate(action, observation)

    with pytest.raises(KeyError, match="tool_type_id"):
        evaluator.evaluate_action(prepared_action, observation)


@pytest.mark.parametrize("action_type", [
    "job_rework_on_defect_machine",
    "job_rework_on_alternative_machine",
])
@pytest.mark.parametrize("distance", [0.0, 1.5, 6.0])
def test_both_rework_types_include_actual_transport_distance(action_type, distance):
    weights = HeuristicWeights()
    evaluator = LocalHeuristicActionEvaluator(weights)
    observation, action = make_observation(action_type, 4.0, 2.0)
    observation.simulation_configuration_snapshot[
        "store_positions_by_id"
    ]["machine in"]["x"] = distance
    transport_value = 1.0 / (1.0 + distance / 1.5)
    expected_score = (
        (1.0 / 3.0) * weights.defect_recovery_machine_queue_length_weight
        + transport_value * weights.defect_recovery_transport_time_weight
        + weights.defect_recovery_tool_match_weight
        + (2.0 / 3.0) * weights.defect_recovery_tool_reserve_weight
    ) / (
        weights.defect_recovery_machine_queue_length_weight
        + weights.defect_recovery_transport_time_weight
        + weights.defect_recovery_tool_match_weight
        + weights.defect_recovery_tool_reserve_weight
    )

    assert evaluator.evaluate_action(action, observation) == pytest.approx(expected_score)


@pytest.mark.parametrize("action_type", [
    "job_rework_on_defect_machine",
    "job_rework_on_alternative_machine",
])
def test_both_rework_types_omit_transport_when_position_is_unknown(action_type):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation, action = make_observation(action_type, 4.0, 2.0)
    del observation.simulation_configuration_snapshot[
        "store_positions_by_id"
    ]["machine in"]

    assert evaluator.evaluate_action(action, observation) == pytest.approx(13.0 / 21.0)


@pytest.mark.parametrize("current_time", [8.0, 10.0, 11.0])
def test_rework_types_have_equal_scores_for_equal_conditions(current_time):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation, defect_action = make_observation("job_rework_on_defect_machine", 4.0, 2.0)
    snapshot = observation.simulation_configuration_snapshot
    snapshot["time"] = current_time
    states = snapshot["simulation_object_states_by_id"]
    states["job"]["time"] = current_time
    states["job"]["latest_end_time"] = 10.0
    states["alternative"] = deepcopy(states["machine"])
    states["alternative"]["object_id"] = "alternative"
    states["alternative"]["input_storage"]["store_id"] = "alternative in"
    snapshot["store_positions_by_id"]["alternative in"] = dict(
        snapshot["store_positions_by_id"]["machine in"]
    )
    alternative_action = {
        "action_type": "job_rework_on_alternative_machine",
        "payload": {
            "selected_operation_id": "operation",
            "selected_machine_id": "alternative",
        },
    }

    assert evaluator.evaluate_action(defect_action, observation) == pytest.approx(
        evaluator.evaluate_action(alternative_action, observation)
    )
