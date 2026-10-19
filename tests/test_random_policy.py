from copy import deepcopy
import random

import pytest

from SpineML.Control.GeneralControl import RandomPolicy
from SpineML.Control.Interface.InterfaceTypes import ActionGenerator, PolicyObservation


class FixedGenerator(ActionGenerator):
    def __init__(self, actions_by_object):
        self.actions_by_object = actions_by_object
        self.observed_ids = []

    def generate_actions(self, observation):
        self.observed_ids.append(observation.current_object_id)
        return self.actions_by_object[observation.current_object_id]


def action(action_type, **payload):
    return {"action_type": action_type, "payload": payload}


def observation(**waiting_by_object):
    return PolicyObservation({
        "simulation_object_states_by_id": {
            object_id: {"is_waiting_for_action": waiting}
            for object_id, waiting in waiting_by_object.items()
        },
    })


@pytest.mark.parametrize("wait_type", [
    "wait_job", "wait_machine", "wait_main_robot", "wait_corridor_arm_robot",
])
def test_wait_is_only_selected_when_no_productive_candidate_exists(wait_type):
    productive = action("release_job")
    waiting = action(wait_type)
    generator = FixedGenerator({"actor": [waiting, productive]})
    policy = RandomPolicy(seed=7, action_generator=generator)

    for _ in range(30):
        assert policy.make_decision(observation(actor=True)).actions[0].action_type == "release_job"

    generator.actions_by_object["actor"] = [waiting]
    assert policy.make_decision(observation(actor=True)).actions[0].action_type == wait_type


def test_uniform_candidate_choice_matches_seeded_rng_without_using_global_random():
    candidates = [action("place_main_robot", target_store_id=target) for target in ("A", "B", "C")]
    generator = FixedGenerator({"actor": [*candidates, action("wait_main_robot")]})
    policy = RandomPolicy(seed=42, action_generator=generator)
    expected_rng = random.Random(42)

    # Keine Bewertungsdaten oder Deadlines sind für die Zufallsauswahl erforderlich.
    for _ in range(60):
        random.random()
        selected = policy.make_decision(observation(actor=True)).actions[0]
        assert selected.payload == expected_rng.choice(candidates)["payload"]


@pytest.mark.parametrize("pick_type", [
    "pick_machine_job", "pick_main_robot", "pick_corridor_arm_robot",
])
def test_picks_use_neutral_priority_and_do_not_modify_generator_candidates(pick_type):
    candidate = action(pick_type, selected_job_id="job", queue_priority=-0.9)
    original = deepcopy(candidate)
    policy = RandomPolicy(seed=1, action_generator=FixedGenerator({"actor": [candidate]}))

    selected = policy.make_decision(observation(actor=True)).actions[0]

    assert selected.payload == {"selected_job_id": "job", "queue_priority": 0.0}
    assert candidate == original


@pytest.mark.parametrize("alternative", ["other_job", None])
def test_batch_does_not_pick_same_job_twice_and_uses_remaining_candidates(alternative):
    second_actions = [action("pick_main_robot", selected_job_id="job"), action("wait_main_robot")]
    if alternative is not None:
        second_actions.append(action("pick_main_robot", selected_job_id=alternative))
    policy = RandomPolicy(seed=1, action_generator=FixedGenerator({
        "first": [action("pick_machine_job", selected_job_id="job")],
        "second": second_actions,
    }))

    selected = policy.make_decision(observation(first=True, second=True)).actions

    assert len(selected) == 2
    assert selected[0].payload["selected_job_id"] == "job"
    if alternative is None:
        assert selected[1].action_type == "wait_main_robot"
    else:
        assert selected[1].payload["selected_job_id"] == alternative


def test_empty_candidates_and_non_waiting_objects_are_skipped():
    generator = FixedGenerator({"empty": []})
    policy = RandomPolicy(seed=1, action_generator=generator)

    assert policy.make_decision(observation(empty=True, busy=False)).actions == []
    assert generator.observed_ids == ["empty"]


def test_conflicting_pick_without_wait_candidate_is_skipped():
    generator = FixedGenerator({
        "first": [action("pick_main_robot", selected_job_id="job")],
        "second": [action("pick_machine_job", selected_job_id="job")],
    })
    result = RandomPolicy(seed=1, action_generator=generator).make_decision(
        observation(first=True, second=True)
    )
    assert [selected.target_id for selected in result.actions] == ["first"]
