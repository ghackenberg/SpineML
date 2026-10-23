from types import SimpleNamespace

import pytest

from SpineML.Control.HeuristicControl import SpineMLSimulationRunner


def make_job(*, defects=0, reworks=0, state="intact", downgraded=False, completed_time=12.0):
    return SimpleNamespace(
        order=SimpleNamespace(earliest_start_time=0.0, latest_end_time=10.0),
        completed_time=completed_time,
        general_state=SimpleNamespace(get=lambda: state),
        downgraded=downgraded,
        defect_count=defects,
        rework_count=reworks,
    )


def collect(jobs):
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
    return SpineMLSimulationRunner(None, None).collect_global_metrics(
        layout, scenario, simulation_end_time=100.0,
    )


@pytest.mark.parametrize(("counts", "expected"), [
    ([0, 0], 0), ([3, 2, 0], 5), ([5, 0, 4], 9),
])
def test_all_defect_events_are_summed_instead_of_counting_affected_jobs(counts, expected):
    metrics = collect([make_job(defects=count) for count in counts])

    assert metrics.total_defect_count == expected
    assert not hasattr(metrics, "defect_jobs")
    assert not hasattr(metrics, "defect_rate")


def test_collecting_metrics_does_not_modify_or_accumulate_job_counters():
    job = make_job(defects=3, reworks=2)

    first = collect([job])
    second = collect([job])

    assert first == second
    assert first.total_defect_count == job.defect_count == 3
    assert first.total_rework_count == job.rework_count == 2


def test_rework_event_total_and_affected_job_count_remain_distinct():
    metrics = collect([
        make_job(reworks=3), make_job(reworks=2), make_job(),
    ])

    assert metrics.total_rework_count == 5
    assert metrics.rework_job_count == 2
    assert metrics.rework_rate == pytest.approx(2 / 3)


def test_completed_quality_outcomes_are_mutually_exclusive():
    metrics = collect([
        make_job(),
        make_job(downgraded=True),
        make_job(state="scrap"),
        make_job(state="scrap", downgraded=True),
        make_job(downgraded=True, completed_time=None),
        make_job(completed_time=None),
    ])

    assert metrics.intact_jobs == 1
    assert metrics.downgraded_job_count == 1
    assert metrics.scrap_job_count == 2
    assert metrics.completed_jobs == 4
    assert metrics.unfinished_jobs == 2
    assert metrics.total_jobs == 6
    assert (
        metrics.intact_jobs + metrics.downgraded_job_count + metrics.scrap_job_count
        == metrics.completed_jobs
    )


def test_scrap_jobs_are_counted_from_final_state_not_scrap_decision_history():
    scrap_job = make_job(state="scrap")
    intact_job = make_job()
    intact_job.scrap_count = 9

    metrics = collect([scrap_job, intact_job])

    assert not hasattr(scrap_job, "scrap_count")
    assert metrics.scrap_job_count == 1
    assert metrics.scrap_rate == 0.5


def test_unfinished_job_events_count_but_do_not_create_final_outcomes():
    metrics = collect([
        make_job(defects=3, reworks=2, state="defect", completed_time=None),
    ])

    assert metrics.total_defect_count == 3
    assert metrics.total_rework_count == 2
    assert metrics.completed_jobs == 0
    assert metrics.unfinished_jobs == 1
    assert metrics.intact_jobs == metrics.downgraded_job_count == metrics.scrap_job_count == 0


def test_empty_run_has_zero_event_counts_and_zero_final_outcomes():
    metrics = collect([])

    assert metrics.total_defect_count == metrics.total_rework_count == 0
    assert metrics.intact_jobs == metrics.downgraded_job_count == metrics.scrap_job_count == 0
    assert metrics.rework_job_count == 0
