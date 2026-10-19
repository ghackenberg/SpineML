from types import SimpleNamespace

import optimization
from SpineML.Control.GeneralControl import RandomPolicy
from SpineML.Control.HeuristicControl import GlobalSimulationMetrics, HeuristicWeights


def test_benchmark_uses_three_controls_and_held_out_seeds_with_fixed_references(monkeypatch):
    assert set(optimization.SEEDS).isdisjoint(optimization.BENCHMARK_SEEDS)
    monkeypatch.setattr(optimization, "BENCHMARK_SEEDS", [101, 102])
    calls = []
    policies = []
    metrics = GlobalSimulationMetrics(makespan=10, total_tardiness=2)

    class Runner:
        def __call__(self, weights, seed):
            calls.append(("heuristic", weights, seed))
            return metrics

        def run_policy(self, policy, seed):
            assert isinstance(policy, RandomPolicy)
            policies.append(policy)
            calls.append(("random", None, seed))
            return metrics

    references = {"makespan": 10.0}
    state = {"baseline_reference_values": references}
    optimizer = SimpleNamespace(
        simulation_runner=Runner(),
        global_evaluation=SimpleNamespace(
            calculate_weighted_sum_of_metrics_relative_to_baseline=lambda value: value.makespan / references["makespan"],
        ),
    )
    best = HeuristicWeights(release_edd_weight=0.8)

    benchmark = optimization._benchmark_policies(state, optimizer, best)

    assert list(benchmark) == ["Random", "Heuristic (default)", "Heuristic (optimized)"]
    assert [seed for _, _, seed in calls] == [101, 102, 101, 102, 101, 102]
    assert len({id(policy) for policy in policies}) == 2
    assert calls[2][1] == HeuristicWeights()
    assert calls[4][1] is best
    assert state["baseline_reference_values"] is references
    for rows in benchmark.values():
        assert [row["Seed"] for row in rows] == [101, 102]
        assert all(row["Weighted sum of metrics relative to baseline"] == 1.0 for row in rows)


def test_comparison_table_and_chart_include_all_three_controls(monkeypatch):
    metrics = {
        "Seed": 101,
        "Makespan": 10.0,
        "Tardiness": 2.0,
        "Transport time": 4.0,
        "Unfinished jobs": 0,
        "Intact rate (%)": 100.0,
        "Defect rate (%)": 0.0,
        "Scrap rate (%)": 0.0,
        "Rework rate (%)": 0.0,
        "Downgrade rate (%)": 0.0,
        "Weighted sum of metrics relative to baseline": 1.0,
    }
    labels = ["Random", "Heuristic (default)", "Heuristic (optimized)"]
    frames = []
    charts = []
    monkeypatch.setattr(optimization.st, "subheader", lambda *args: None)
    monkeypatch.setattr(optimization.st, "caption", lambda *args: None)
    monkeypatch.setattr(optimization.st, "dataframe", lambda frame, **kwargs: frames.append(frame))
    monkeypatch.setattr(optimization.st, "altair_chart", lambda chart, **kwargs: charts.append(chart))

    optimization.compare_baseline_optimized({label: [metrics] for label in labels})

    assert set(frames[0]["Control"]) == set(labels)
    assert set(charts[0].data["Control"]) == set(labels)
    assert charts[0].to_dict()["encoding"]["color"]["field"] == "Control"
