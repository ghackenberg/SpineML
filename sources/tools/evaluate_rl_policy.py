"""Lädt ein Kandidaten-DQN und vergleicht es auf unbenutzten Test-Seeds."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
import sys
from time import perf_counter

SOURCES_DIRECTORY = Path(__file__).resolve().parents[1]
if sys.path[:1] != [str(SOURCES_DIRECTORY)]:
    sys.path.insert(0, str(SOURCES_DIRECTORY))


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Test-Seeds dürfen nicht negativ sein.")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="Trainingsordner mit manifest.json und model.zip.")
    parser.add_argument("--checkpoint", default="model.zip", help="Dateiname eines Checkpoints im Trainingsordner.")
    parser.add_argument("--model", type=Path, help="Identische Modelldatei an einem anderen Speicherort.")
    parser.add_argument("--seeds", type=nonnegative_int, nargs="+", help="Standard: reservierte Test-Seeds aus manifest.json.")
    parser.add_argument("--output", type=Path, help="Standard: evaluation.json im Trainingsordner.")
    parser.add_argument("--optimized-weights", type=Path, help="Optional: JSON mit HeuristicWeights oder optimization_result.best_weights.")
    parser.add_argument("--skip-comparisons", action="store_true", help="Nur das RL-Modell ausführen, ohne Zufall und Standardheuristik.")
    parser.add_argument("--explore", "--stochastic", dest="explore", action="store_true", help="Epsilon-greedy mit der gespeicherten Explorationsrate; sonst den höchsten gültigen Q-Wert wählen.")
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    checkpoint = directory / args.checkpoint
    if Path(args.checkpoint).name != args.checkpoint:
        parser.error("--checkpoint muss ein Dateiname innerhalb des Trainingsordners sein.")
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        parser.error(f"Trainingskonfiguration nicht lesbar: {error}")
    if not isinstance(manifest, dict):
        parser.error("Das Manifest muss einen DQN-Trainingslauf beschreiben.")
    if manifest.get("algorithm") == "MaskablePPO":
        parser.error("Alte PPO-Checkpoints sind mit der DQN-Auswertung nicht kompatibel; ein DQN-Trainingslauf ist erforderlich.")
    if manifest.get("algorithm") != "DQN" or manifest.get("policy_class") != "CandidateDQNPolicy":
        parser.error("Das Manifest muss DQN mit CandidateDQNPolicy beschreiben.")
    seeds = args.seeds
    if not seeds:
        seeds = manifest.get("evaluation_seeds", [])
    if not isinstance(seeds, list) or not seeds:
        parser.error("Test-Seeds müssen ganze Zahlen zwischen 0 und 2**64-1 sein.")
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
            parser.error("Test-Seeds müssen ganze Zahlen zwischen 0 und 2**64-1 sein.")
    if len(set(seeds)) != len(seeds):
        parser.error("Mindestens ein Test-Seed ist erforderlich; keine Duplikate verwenden.")
    training_seeds = set(manifest["train_seeds"]) | set(manifest["baseline"]["seeds"])
    if set(seeds) & training_seeds:
        parser.error("Für diesen Vergleich sind nur Seeds außerhalb von Training und Baseline zulässig.")
    if not checkpoint.is_file():
        parser.error(f"Modell-Checkpoint fehlt: {checkpoint}")
    try:
        import numpy as np
        import torch
        from SpineML.Control.RLPolicy.CandidateDQN import CandidateDQN
        from SpineML.Control.RLPolicy.CandidateDQNPolicy import CandidateDQNPolicy
        from SpineML.Control.RLPolicy.SpineRLEnv import SpineRLEnv
        from SpineML.Control.RLPolicy.TrainingSupport import evaluation_from_context, validate_artifact_context
        from SpineML.Control.RandomPolicy.RandomPolicy import RandomPolicy
        from SpineML.Control.HeuristicPolicy.HeuristicPolicyFactory import HeuristicPolicyFactory
        from SpineML.Control.HeuristicPolicy.HeuristicWeights import HeuristicWeights
        from SpineML.GlobalEvaluation.GlobalSimulationEvaluation import GlobalSimulationMetrics
        from SpineML.SimulationExecution.ModelLoader import load_layout_and_scenario
        from SpineML.SimulationExecution.SimulationRunner import SimulationRunner
    except ImportError as error:
        parser.error(f'Trainingspakete fehlen. Installieren: python -m pip install -e ".[rl-training]"\n{error}')
    torch.set_num_threads(1)
    context = manifest["artifact_context"]
    model_path = validate_artifact_context(context, args.model)
    evaluation = evaluation_from_context(context)
    optimized_weights = None
    optimized_source = None
    if args.optimized_weights:
        try:
            raw_weights = args.optimized_weights.read_bytes()
            values = json.loads(raw_weights)
            if "optimization_result" in values:
                values = values["optimization_result"]["best_weights"]
            elif "best_weights" in values:
                values = values["best_weights"]
            optimized_weights = HeuristicWeights(**values)
            optimized_source = {"file": str(args.optimized_weights.resolve()),
                                "sha256": hashlib.sha256(raw_weights).hexdigest(),
                                "weights": asdict(optimized_weights)}
        except (OSError, ValueError, TypeError, KeyError) as error:
            parser.error(f"Optimierter Gewichtssatz nicht lesbar: {error}")
    output = directory / "evaluation.json"
    if args.output:
        output = args.output.resolve()
    if output == directory / "manifest.json" or output.suffix == ".zip":
        parser.error("Ein Auswertungsbericht darf weder Manifest noch Modell-Checkpoint ersetzen.")
    output.parent.mkdir(parents=True, exist_ok=True)
    python_rng = random.getstate()
    numpy_rng = np.random.get_state()
    try:
        with torch.random.fork_rng(devices=[]):
            network = CandidateDQN.load(checkpoint, device="cpu", seed=None)
    finally:
        random.setstate(python_rng)
        np.random.set_state(numpy_rng)
    if not isinstance(network.policy, CandidateDQNPolicy):
        parser.error("Der Checkpoint enthält keine CandidateDQNPolicy.")
    environment = SpineRLEnv(model_path, evaluation, **context["environment"])
    if network.observation_space != environment.observation_space or network.action_space != environment.action_space:
        environment.close()
        parser.error("Beobachtungs- oder Aktionsraum passt nicht zur gespeicherten Konfiguration.")
    results = []
    started_at = perf_counter()

    def save_progress() -> None:
        # Bei einem späteren Fehler bleiben schon abgeschlossene Läufe als Teilbericht erhalten.
        partial = {"status": "in_progress", "checkpoint": str(checkpoint),
                   "test_seeds": seeds, "artifact_context": context,
                   "optimized_weights_source": optimized_source, "runs": results,
                   "elapsed_seconds": perf_counter() - started_at}
        output.write_text(json.dumps(partial, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save_progress()
    try:
        for seed in seeds:
            # Exploration erhält einen eigenen Zufallsstrom je Test-Seed.
            policy_python_rng = random.Random(seed).getstate()
            policy_numpy_rng = np.random.RandomState(np.random.SeedSequence(seed).generate_state(4)).get_state()
            policy_torch_rng = torch.Generator(device="cpu").manual_seed(seed).get_state()
            run_started_at = perf_counter()
            observation, info = environment.reset(seed=seed)
            terminated = False
            truncated = False
            reward_total = 0.0
            while not terminated and not truncated:
                python_rng = random.getstate()
                numpy_rng = np.random.get_state()
                try:
                    random.setstate(policy_python_rng)
                    np.random.set_state(policy_numpy_rng)
                    with torch.random.fork_rng(devices=[]):
                        torch.set_rng_state(policy_torch_rng)
                        action, _ = network.predict(observation, deterministic=not args.explore)
                        policy_torch_rng = torch.get_rng_state()
                    policy_python_rng = random.getstate()
                    policy_numpy_rng = np.random.get_state()
                finally:
                    random.setstate(python_rng)
                    np.random.set_state(numpy_rng)
                observation, reward, terminated, truncated, info = environment.step(int(np.asarray(action).item()))
                reward_total += float(reward)
            results.append({
                "policy": "RL (trained)", "seed": seed, "terminated": bool(terminated),
                "truncated": bool(truncated), "reward": reward_total,
                "global_cost": float(info["global_cost"]), "metrics": info["metrics"],
                "decisions": info["decision_count"], "limit_reason": info.get("truncation_reason"),
                "elapsed_seconds": perf_counter() - run_started_at,
            })
            save_progress()
            print(f"RL, Seed {seed}: abgeschlossen={terminated}, Reward={reward_total:.5f}, Kosten={info['global_cost']:.5f}", flush=True)
    finally:
        environment.close()

    if not args.skip_comparisons:
        # Erst nach close(): im selben Prozess darf nur eine Simulation aktiv sein.
        layout, scenario = load_layout_and_scenario(model_path)

        class ComparisonRunner(SimulationRunner):
            last_metrics = None

            def collect_global_metrics(self, sim_layout, sim_scenario, simulation_end_time):
                self.last_metrics = super().collect_global_metrics(sim_layout, sim_scenario, simulation_end_time)
                return self.last_metrics

        runner = ComparisonRunner(layout, scenario, till=context["environment"]["max_simulation_time"])
        comparisons = [("Random", RandomPolicy), ("Heuristic (default)", HeuristicPolicyFactory())]
        if optimized_weights is not None:
            comparisons.append(("Heuristic (optimized)", HeuristicPolicyFactory(optimized_weights)))
        for name, factory in comparisons:
            for seed in seeds:
                run_started_at = perf_counter()
                runner.last_metrics = None
                try:
                    metrics = runner.run_policy(factory(seed), seed)
                except RuntimeError:
                    # Nur ein reguläres Zeitlimit mit erfassten unfertigen Jobs ist ein Abbruch.
                    # Andere Simulationsfehler bleiben echte Fehler und werden weitergegeben.
                    if runner.last_metrics is None or runner.last_metrics.unfinished_jobs == 0:
                        raise
                    metrics = runner.last_metrics
                completed = metrics.unfinished_jobs == 0
                cost = evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(metrics)
                limit_reason = None
                if not completed:
                    limit_reason = "max_simulation_time"
                results.append({"policy": name, "seed": seed, "terminated": completed, "truncated": not completed,
                                "limit_reason": limit_reason,
                                "global_cost": cost, "metrics": asdict(metrics), "elapsed_seconds": perf_counter() - run_started_at})
                save_progress()
                print(f"{name}, Seed {seed}: abgeschlossen={completed}, Kosten={cost:.5f}", flush=True)

    summary = []
    metric_names = ("makespan", "total_tardiness", "total_transport_time", "tool_change_time", "rework_rate", "scrap_rate", "downgrade_rate")
    policy_names = []
    for item in results:
        if item["policy"] not in policy_names:
            policy_names.append(item["policy"])
    for name in policy_names:
        runs = []
        for item in results:
            if item["policy"] == name:
                runs.append(item)
        complete = []
        for item in runs:
            if item["terminated"]:
                complete.append(item)
        metrics = []
        for item in complete:
            metrics.append(GlobalSimulationMetrics(**item["metrics"]))
        mean_global_cost = None
        mean_metrics = None
        # Teilweise abgebrochene Testreihen dürfen keinen günstigen Mittelwert vortäuschen.
        if len(complete) == len(runs):
            costs = []
            for item in complete:
                costs.append(item["global_cost"])
            mean_global_cost = mean(costs)
            mean_metrics = {}
            for key in metric_names:
                values = []
                for item in metrics:
                    values.append(getattr(item, key))
                mean_metrics[key] = mean(values)
        summary.append({
            "policy": name, "runs": len(runs), "completed_runs": len(complete),
            "truncated_runs": len(runs) - len(complete),
            "mean_global_cost": mean_global_cost,
            "mean_metrics": mean_metrics,
        })
    report = {"status": "finished", "checkpoint": str(checkpoint), "model_sha256": context["model_sha256"],
              "test_seeds": seeds, "deterministic": not args.explore,
              "exploration_rate": float(network.exploration_rate),
              "artifact_context": context, "optimized_weights_source": optimized_source,
              "summary": summary, "runs": results,
              "elapsed_seconds": perf_counter() - started_at}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("\nVergleich (Mittelwerte nur, wenn sämtliche Test-Seeds abgeschlossen wurden):")
    for item in summary:
        cost = "nicht verfügbar"
        if item["mean_global_cost"] is not None:
            cost = f"{item['mean_global_cost']:.6f}"
        print(f"{item['policy']}: {item['completed_runs']}/{item['runs']} abgeschlossen, mittlere Kosten={cost}")
    print(f"Bericht: {output}")


if __name__ == "__main__":
    main()
