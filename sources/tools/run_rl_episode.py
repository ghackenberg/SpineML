"""Führt eine Episode über die Gymnasium-Schnittstelle aus, ohne NN-Training."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from time import perf_counter

SOURCES_DIRECTORY = Path(__file__).resolve().parents[1]
if sys.path[:1] != [str(SOURCES_DIRECTORY)]:
    sys.path.insert(0, str(SOURCES_DIRECTORY))


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Der Wert muss größer als 0 sein.")
    return number


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Der Seed muss mindestens 0 sein.")
    return number


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Der Wert muss endlich und größer als 0 sein.")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RL-Umgebung prüfen, noch kein trainiertes neuronales Netz.",
    )
    parser.add_argument(
        "--model", type=Path,
        help="Modelldatei; Standard: EXAMPLE_FILE aus heuristic_optimization_app.py (example-5.py).",
    )
    parser.add_argument(
        "--seed", type=nonnegative_int, default=1,
        help="Nichtnegativer Episoden-Seed (Standard: 1).",
    )
    parser.add_argument(
        "--policy", choices=("random", "heuristic"), default="random",
        help="Debug-Auswahl: zufällige Nicht-Warteaktion oder vorhandene Heuristik.",
    )
    parser.add_argument(
        "--max-decisions", type=positive_int, default=100000,
        help="Abbruchgrenze für Entscheidungen (Standard: 100000).",
    )
    parser.add_argument(
        "--max-simulation-time", type=positive_float, default=10000.0,
        help="Abbruchgrenze der simulierten Zeit (Standard: 10000).",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Speichert Konfiguration, Baseline und Episodenergebnis als JSON.",
    )
    args = parser.parse_args()

    # --help beendet sich bereits oben: Gymnasium bleibt eine optionale Abhängigkeit.
    try:
        from SpineML.Control.RLPolicy.SpineRLEnv import SpineRLEnv
    except ModuleNotFoundError as error:
        if error.name == "gymnasium":
            parser.error("Gymnasium fehlt. Zuerst installieren: python -m pip install -e '.[rl]'")
        raise

    from dataclasses import asdict

    # Nur Konfiguration/Funktionen importieren; keine Streamlit-Anwendung starten.
    from apps import heuristic_optimization_app as optimization_config
    from SpineML.Control.HeuristicPolicy.HeuristicActionSelector import (
        HeuristicActionSelector,
    )
    from SpineML.Control.HeuristicPolicy.HeuristicWeights import HeuristicWeights
    from SpineML.Control.HeuristicPolicy.HeuristicPolicyFactory import HeuristicPolicyFactory
    from SpineML.Control.HeuristicPolicy.LocalHeuristicActionEvaluator import (
        LocalHeuristicActionEvaluator,
    )
    from SpineML.SimulationExecution.SimulationRunner import SimulationRunner
    from SpineML.SimulationExecution.ModelLoader import load_layout_and_scenario
    from SpineML.SimulationInterface.InterfaceTypes import is_wait_action

    started_at = perf_counter()
    model_file = args.model if args.model is not None else optimization_config.EXAMPLE_FILE
    model_path = optimization_config._resolve_model_path(model_file)
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    baseline_seeds = tuple(optimization_config.SEEDS)
    if not baseline_seeds:
        parser.error("heuristic_optimization_app.SEEDS darf für die Reward-Kalibrierung nicht leer sein.")
    evaluation = optimization_config._global_evaluation()
    weights = HeuristicWeights()

    print("RL-Umgebung prüfen, noch kein trainiertes neuronales Netz.", flush=True)
    print(f"Modell: {model_path.name}; Debug-Policy: {args.policy}; Seed: {args.seed}.")
    print(
        f"Zuerst separate vollständige Heuristik-Baseline für Seeds {baseline_seeds}; "
        "diese Läufe sind noch keine RL-Episode.",
        flush=True,
    )
    baseline_started_at = perf_counter()
    layout, scenario = load_layout_and_scenario(model_path)
    baseline_runner = SimulationRunner(layout, scenario)
    baseline_policy_factory = HeuristicPolicyFactory(weights)
    baseline_metrics = []
    for seed in baseline_seeds:
        print(f"  Baseline mit Seed {seed} ...", flush=True)
        policy = baseline_policy_factory(seed)
        baseline_metrics.append(baseline_runner.run_policy(policy, seed))
    references = evaluation.calculate_baseline_reference_values(baseline_metrics)
    baseline_seconds = perf_counter() - baseline_started_at
    print(f"Baseline abgeschlossen nach {baseline_seconds:.3f} s.", flush=True)

    selection_rng = random.Random(args.seed)
    selector = HeuristicActionSelector(rng=selection_rng)
    evaluator = LocalHeuristicActionEvaluator(weights)
    action_counts: Counter[str] = Counter()
    decisions = 0
    total_reward = 0.0
    terminated = False
    truncated = False
    episode_started_at = perf_counter()

    # Ein aktives Environment pro Prozess; close() räumt auch bei Fehlern auf.
    environment = SpineRLEnv(
        model_path,
        evaluation,
        max_decisions=args.max_decisions,
        max_simulation_time=args.max_simulation_time,
    )
    try:
        observation, info = environment.reset(seed=args.seed)
        observation_shapes = {
            name: list(value.shape) for name, value in observation.items()
        }
        print(f"Numerische Beobachtungsformen: {observation_shapes}", flush=True)
        while not terminated and not truncated:
            candidates = info["candidates"]
            valid_indices = [
                index for index, allowed in enumerate(environment.action_masks())
                if bool(allowed)
            ]
            if not valid_indices:
                raise RuntimeError("Die laufende RL-Episode bietet keine gültige Aktion an.")

            if args.policy == "random":
                productive_indices = [
                    index for index in valid_indices
                    if not is_wait_action(candidates[index]["action_type"])
                ]
                selected_index = selection_rng.choice(productive_indices or valid_indices)
            else:
                # Nur Debug-Vergleich: Der Selector nutzt die bestehende Heuristik,
                # nicht die numerische Beobachtung eines noch untrainierten Netzes.
                decision = selector.select_action(
                    [candidates[index] for index in valid_indices],
                    evaluator=evaluator,
                    observation=info["policy_observation"],
                    target_id=info["current_object_id"],
                )
                if len(decision.actions) != 1:
                    raise RuntimeError("Die Debug-Heuristik muss genau eine Aktion auswählen.")
                selected_action = decision.actions[0]
                selected_index = next(
                    (
                        index for index in valid_indices
                        if candidates[index]["action_type"] == selected_action.action_type
                        and candidates[index]["payload"] == selected_action.payload
                    ),
                    None,
                )
                if selected_index is None:
                    raise RuntimeError("Die Debug-Heuristik hat keinen angebotenen Kandidaten gewählt.")

            action_counts[candidates[selected_index]["action_type"]] += 1
            observation, reward, terminated, truncated, info = environment.step(selected_index)
            decisions += 1
            total_reward += float(reward)
            if decisions % 1000 == 0:
                print(
                    f"  {decisions} Entscheidungen; simulierte Zeit "
                    f"{info['simulation_time']:.3f}.",
                    flush=True,
                )

    finally:
        environment.close()

    episode_seconds = perf_counter() - episode_started_at
    report = {
        "purpose": "RL environment smoke/debug run; no trained neural network",
        "model_file": model_path.name,
        "model_sha256": model_sha256,
        "seed": args.seed,
        "policy": args.policy,
        "max_decisions": args.max_decisions,
        "max_simulation_time": args.max_simulation_time,
        "global_weights": asdict(evaluation.weights),
        "baseline": {
            "seeds": list(baseline_seeds),
            "reference_values": references,
            "elapsed_seconds": baseline_seconds,
            "metrics_by_seed": [
                {"seed": seed, "metrics": asdict(metrics)}
                for seed, metrics in zip(baseline_seeds, baseline_metrics)
            ],
        },
        "episode": {
            "decisions": decisions,
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "simulation_time": info["simulation_time"],
            "reward": total_reward,
            "reward_reason": info["reward_reason"],
            "global_cost": info["global_cost"],
            "metrics": info["metrics"],
            "action_counts": dict(action_counts),
            "observation_shapes": observation_shapes,
            "elapsed_seconds": episode_seconds,
        },
        "total_elapsed_seconds": perf_counter() - started_at,
    }
    print(
        f"Episode beendet: terminated={terminated}, truncated={truncated}, "
        f"Entscheidungen={decisions}, Reward={total_reward:.6f}, "
        f"globale Kosten={info['global_cost']:.6f}, Grund={info['reward_reason']}.",
        flush=True,
    )
    print(f"Produktionskennzahlen: {json.dumps(info['metrics'], ensure_ascii=False)}")
    print(f"Episode: {episode_seconds:.3f} s; Baseline separat: {baseline_seconds:.3f} s.")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON-Bericht: {args.output.resolve()}")


if __name__ == "__main__":
    main()
