from types import SimpleNamespace

import pytest

from SpineML.Control.HeuristicControl import SpineMLSimulationRunner


def make_order(name="order", deadline=10.0):
    return SimpleNamespace(name=name, earliest_start_time=0.0, latest_end_time=deadline)


def make_job(order, completion_time):
    return SimpleNamespace(
        order=order,
        completed_time=completion_time,
        general_state=SimpleNamespace(get=lambda: "intact"),
    )


def collect_metrics(jobs):
    # Nur die Jobauswertung testen; Roboter- und Maschinenzeiten bleiben null.
    layout = SimpleNamespace(
        sim_main_robot=SimpleNamespace(
            state_move=SimpleNamespace(
                value=SimpleNamespace(value_duration=lambda state: 0.0),
            ),
        ),
        sim_corridors=[],
        simMachines=lambda: [],
    )
    scenario = SimpleNamespace(sim_orders=[SimpleNamespace(sim_jobs=jobs)])
    runner = SpineMLSimulationRunner(layout=None, scenario=None)
    return runner.collect_global_metrics(layout, scenario, simulation_end_time=100.0)


@pytest.mark.parametrize(("completion_times", "deadline", "expected_tardiness"), [
    ([8.0, 12.0, 15.0], 10.0, 7.0),
    ([8.0, 9.0, 10.0], 10.0, 0.0),
    ([11.0, 11.0, 11.0], 10.0, 3.0),
    ([9.75, 10.25, 11.5], 10.0, 1.75),
    ([0.0, 1.0], 0.0, 1.0),
])
def test_total_tardiness_sums_each_jobs_positive_lateness(
    completion_times, deadline, expected_tardiness,
):
    order = make_order(deadline=deadline)
    jobs = [make_job(order, time) for time in completion_times]

    metrics = collect_metrics(jobs)

    assert metrics.total_tardiness == pytest.approx(expected_tardiness)
    assert metrics.completed_jobs == len(jobs)
    assert metrics.unfinished_jobs == 0
    assert metrics.makespan == pytest.approx(max(completion_times))


def test_each_job_uses_its_own_orders_deadline():
    first_order = make_order("first", deadline=10.0)
    second_order = make_order("second", deadline=20.0)
    jobs = [
        make_job(first_order, 8.0),
        make_job(first_order, 12.0),
        make_job(second_order, 21.0),
        make_job(second_order, 24.0),
    ]

    metrics = collect_metrics(jobs)

    assert metrics.total_tardiness == pytest.approx(0.0 + 2.0 + 1.0 + 4.0)


def test_finished_job_counts_even_if_another_job_of_the_order_is_unfinished():
    order = make_order(deadline=10.0)

    metrics = collect_metrics([make_job(order, 12.0), make_job(order, None)])

    assert metrics.total_tardiness == pytest.approx(2.0)
    assert metrics.completed_jobs == 1
    assert metrics.unfinished_jobs == 1


def test_no_jobs_produce_zero_total_tardiness():
    assert collect_metrics([]).total_tardiness == 0.0
