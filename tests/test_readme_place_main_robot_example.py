import pytest

from SpineML.Control.GeneralControl.ActionGenerators import SpineActionGenerator
from SpineML.Control.GeneralControl.ActionSelectors import BaselineActionSelector
from SpineML.Control.HeuristicControl.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import PolicyObservation


def make_store(store_id, count):
    return {
        "store_id": store_id,
        "capacity": 10,
        "count": count,
        "available_capacity": 10 - count,
        "has_capacity": count < 10,
    }


def make_observation():
    job = {
        "job_id": "job",
        "general_state": "intact",
        "downgraded": False,
        "processing_state": "raw",
        "target_product_type_name": "finished",
        "latest_end_time": 10.0,
    }
    robot = {
        "object_type": "main_robot",
        "object_id": "robot",
        "layout_id": "layout",
        "current_job_id": "job",
        "current_job_summary": job,
        "x": 0.0,
        "y": -5.0,
        "z": 1.25,
        "movement_speed": 2.0,
        "corridor_storages": [
            {
                "corridor_id": "corridor_A",
                "left": make_store("Puffer A", 6),
                "right": make_store("Puffer A right", 0),
            },
            {
                "corridor_id": "corridor_B",
                "left": make_store("Puffer B", 8),
                "right": make_store("Puffer B right", 0),
            },
        ],
    }
    machines = {
        machine_id: {
            "machine_type_id": "machine_type",
            "layout_id": "layout",
            "corridor_id": corridor_id,
            "left": True,
            "tool_type_ids": ["tool"],
        }
        for machine_id, corridor_id in (
            ("Maschine A", "corridor_A"),
            ("Maschine B", "corridor_B"),
        )
    }
    return PolicyObservation(
        {
            "time": 11.0,
            "configuration_model": {
                "operations_by_id": {
                    "operation": {
                        "duration": 4.0,
                        "machine_type_id": "machine_type",
                        "tool_type_id": "tool",
                        "consumed_life_units": 1.0,
                        "consumes_product_type_id": "raw",
                        "produces_product_type_id": "finished",
                    },
                },
                "machines_by_id": machines,
                "corridors_by_id": {
                    "corridor_A": {"storage_in_time": 1.0},
                    "corridor_B": {"storage_in_time": 1.0},
                },
                "layouts_by_id": {
                    "layout": {"corridor_ids": ["corridor_A", "corridor_B"]},
                },
            },
            "simulation_object_states_by_id": {
                "robot": robot,
                "Maschine A": {
                    "object_type": "machine",
                    "object_id": "Maschine A",
                    "input_storage": make_store("Maschine A in", 3),
                },
                "Maschine B": {
                    "object_type": "machine",
                    "object_id": "Maschine B",
                    "input_storage": make_store("Maschine B in", 0),
                },
            },
            "store_positions_by_id": {
                "Puffer A": {"x": 0.0, "y": 3.0, "z": 1.25},
                "Puffer B": {"x": 0.0, "y": -3.0, "z": 1.25},
            },
        },
        "robot",
    )


def test_generator_creates_the_two_readme_place_candidates():
    actions = SpineActionGenerator().generate_actions(make_observation())
    place_actions = [action for action in actions if action["action_type"] == "place_main_robot"]

    assert len(place_actions) == 2
    assert {
        (action["payload"]["target_store_id"], action["payload"]["selected_machine_id"])
        for action in place_actions
    } == {("Puffer A", "Maschine A"), ("Puffer B", "Maschine B")}
    assert all(
        action["payload"]["selected_operation_id"] == "operation"
        for action in place_actions
    )
    assert all(action["payload"]["storage_in_time"] == 1.0 for action in place_actions)
    assert [action["action_type"] for action in actions].count("wait_main_robot") == 1


@pytest.mark.parametrize(
    "target_store_id, expected_parts, expected_score",
    [
        ("Puffer A", [0.4, 0.2, 0.5, 0.25, 0.2], 0.2975),
        ("Puffer B", [0.2, 0.5, 0.5, 1.0, 0.2], 0.52),
    ],
)
def test_readme_parts_and_scores_match_the_real_evaluator(
    target_store_id, expected_parts, expected_score,
):
    observation = make_observation()
    weights = HeuristicWeights()
    evaluator = LocalHeuristicActionEvaluator(weights)
    action = next(
        action for action in SpineActionGenerator().generate_actions(observation)
        if action["payload"].get("target_store_id") == target_store_id
    )
    parts = [
        evaluator.target_store_capacity_value(action, observation),
        evaluator.transport_time_value(action, observation),
        evaluator.place_target_storage_time_value(action),
        evaluator.place_machine_queue_value(action, observation),
        evaluator.place_processing_time_value(action, observation),
    ]
    active_weights = [
        weights.target_store_free_capacity_weight,
        weights.place_short_transport_time_weight,
        weights.place_target_storage_time_weight,
        weights.place_machine_queue_length_weight,
        weights.place_operation_duration_weight,
    ]

    assert parts == pytest.approx(expected_parts)
    assert active_weights == pytest.approx([0.2, 0.25, 0.15, 0.25, 0.15])
    assert sum(active_weights) == pytest.approx(1.0)
    assert evaluator.evaluate_action(action, observation) == pytest.approx(expected_score)


@pytest.mark.parametrize("random_draw", [0.0, 1.0])
def test_readme_target_b_wins_even_with_exploration(monkeypatch, random_draw):
    monkeypatch.setattr(
        "SpineML.Control.GeneralControl.ActionSelectors.random.random",
        lambda: random_draw,
    )
    observation = make_observation()
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    actions = SpineActionGenerator().generate_actions(observation)
    wait_action = next(action for action in actions if action["action_type"] == "wait_main_robot")

    assert evaluator.evaluate_action(wait_action, observation) == pytest.approx(0.25)
    decision = BaselineActionSelector().select_action(
        actions, evaluator=evaluator, observation=observation, target_id="robot",
    )

    assert len(decision.actions) == 1
    assert decision.actions[0].action_type == "place_main_robot"
    assert decision.actions[0].payload["target_store_id"] == "Puffer B"


def test_full_target_b_is_not_generated_again():
    observation = make_observation()
    robot = observation.simulation_configuration_snapshot[
        "simulation_object_states_by_id"
    ]["robot"]
    robot["corridor_storages"][1]["left"].update(make_store("Puffer B", 10))

    actions = SpineActionGenerator().generate_actions(observation)

    assert {
        action["payload"]["target_store_id"]
        for action in actions if action["action_type"] == "place_main_robot"
    } == {"Puffer A"}
