import pytest

from SpineML.Control.HeuristicControl.HeuristicWeights import HeuristicWeights
from SpineML.Control.HeuristicControl.LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)
from SpineML.Control.Interface.InterfaceTypes import PolicyObservation


WAITING_ACTORS = [
    ("order_job", "wait_job"),
    ("main_robot", "wait_main_robot"),
    ("corridor_arm_robot", "wait_corridor_arm_robot"),
    ("machine", "wait_machine"),
]


def make_wait_observation(actor_type, current_time, *, defective=False):
    job = {
        "object_type": "order_job",
        "general_state": "defect" if defective else "next_product_state",
        "time": current_time,
        "latest_end_time": 1000.0,
    }
    actor = job if actor_type == "order_job" else {
        "object_type": actor_type,
        "current_job_summary": job,
    }
    return PolicyObservation(
        {
            "time": current_time,
            "simulation_object_states_by_id": {"actor": actor},
        },
        "actor",
    )


@pytest.mark.parametrize("actor_type, action_type", WAITING_ACTORS)
@pytest.mark.parametrize(
    "current_time, expected_score",
    [
        (0.0, 1.0 - 0.5 / 1001.0),
        (998.0, 5.0 / 6.0),
        (1000.0, 0.5),
        (1001.0, 0.25),
        (2000.0, 0.5 / 1001.0),
    ],
)
def test_normal_wait_uses_one_minus_edd(
    actor_type, action_type, current_time, expected_score
):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_wait_observation(actor_type, current_time)

    score = evaluator.evaluate_action(
        {"action_type": action_type, "payload": {}}, observation
    )

    assert score == pytest.approx(expected_score)


@pytest.mark.parametrize("actor_type, action_type", WAITING_ACTORS)
@pytest.mark.parametrize("deadline_is_missing", [False, True])
def test_wait_without_deadline_keeps_default_score(
    actor_type, action_type, deadline_is_missing
):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_wait_observation(actor_type, 998.0)
    actor = observation.simulation_configuration_snapshot[
        "simulation_object_states_by_id"
    ]["actor"]
    job = actor if actor_type == "order_job" else actor["current_job_summary"]
    if deadline_is_missing:
        del job["latest_end_time"]
    else:
        job["latest_end_time"] = None

    score = evaluator.evaluate_action(
        {"action_type": action_type, "payload": {}}, observation
    )

    assert score == pytest.approx(0.01)


@pytest.mark.parametrize("actor_type, action_type", WAITING_ACTORS[1:])
def test_wait_without_job_keeps_default_score(actor_type, action_type):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_wait_observation(actor_type, 998.0)
    del observation.simulation_configuration_snapshot[
        "simulation_object_states_by_id"
    ]["actor"]["current_job_summary"]

    score = evaluator.evaluate_action(
        {"action_type": action_type, "payload": {}}, observation
    )

    assert score == pytest.approx(0.01)


@pytest.mark.parametrize(
    "current_time, expected_score",
    [
        (998.0, 5.0 / 6.0),
        (1000.0, 0.3),
        (1001.0, 0.05),
        (1002.0, -1.0 / 30.0),
        (2000.0, 0.5 / 1001.0 - 0.2),
    ],
)
def test_defect_wait_keeps_deadline_penalty(current_time, expected_score):
    evaluator = LocalHeuristicActionEvaluator(HeuristicWeights())
    observation = make_wait_observation("order_job", current_time, defective=True)

    score = evaluator.evaluate_action(
        {"action_type": "wait_job", "payload": {}}, observation
    )

    assert score == pytest.approx(expected_score)
