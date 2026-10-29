"""Trainiert eine maskierte neuronale Kandidatenauswahl mit MaskablePPO."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter

SOURCES_DIRECTORY = Path(__file__).resolve().parents[1]
if sys.path[:1] != [str(SOURCES_DIRECTORY)]:
    sys.path.insert(0, str(SOURCES_DIRECTORY))


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Der Wert muss mindestens 1 sein.")
    return number


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Der Seed darf nicht negativ sein.")
    return number


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Der Wert muss endlich und positiv sein.")
    return number


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Modelldatei; Standard: Beispiel der Optimierungsanwendung.")
    parser.add_argument("--output", type=Path, default=Path("rl_runs/ppo"), help="Neuer oder leerer Ausgabeordner.")
    parser.add_argument("--steps", type=positive_int, default=100_000, help="Mindestens so viele externe Entscheidungen insgesamt trainieren.")
    parser.add_argument("--workers", type=positive_int, default=min(os.cpu_count() or 1, 4), help="Getrennte Simulationsprozesse; Standard: höchstens 4.")
    parser.add_argument("--rollout-steps", type=positive_int, default=256, help="Entscheidungen je Prozess und PPO-Update.")
    parser.add_argument("--batch-size", type=positive_int, default=64)
    parser.add_argument("--epochs", type=positive_int, default=10)
    parser.add_argument("--learning-rate", type=positive_float, default=0.0003)
    parser.add_argument("--train-seeds", type=nonnegative_int, nargs="+", default=list(range(1, 11)))
    parser.add_argument("--baseline-seeds", type=nonnegative_int, nargs="+", help="Standard: SEEDS der Optimierungsanwendung.")
    parser.add_argument("--evaluation-seeds", type=nonnegative_int, nargs="+", help="Reservierte Test-Seeds; Standard: TEST_SEEDS der Anwendung.")
    parser.add_argument("--seed", type=nonnegative_int, default=0, help="Seed für Netzinitialisierung und PPO-Zufall.")
    parser.add_argument("--max-decisions", type=positive_int, default=10_000)
    parser.add_argument("--max-simulation-time", type=positive_float, default=10_000.0)
    parser.add_argument("--max-actions", type=positive_int, default=256)
    parser.add_argument("--max-entities", type=positive_int, default=256)
    parser.add_argument("--checkpoint-every", type=positive_int, default=10_000, help="Regelmäßiger Checkpoint nach ungefähr so vielen Entscheidungen.")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu", help="Nur das Netz; die Salabim-Simulation bleibt auf der CPU.")
    args = parser.parse_args()

    samples_per_update = args.workers * args.rollout_steps
    if args.rollout_steps < 2:
        parser.error("--rollout-steps muss mindestens 2 sein.")
    if args.batch_size < 2 or args.batch_size > samples_per_update or samples_per_update % args.batch_size:
        parser.error("--batch-size muss mindestens 2 sein und workers * rollout-steps ohne Rest teilen.")
    if len(set(args.train_seeds)) != len(args.train_seeds):
        parser.error("--train-seeds darf keine doppelten Seeds enthalten.")
    if args.seed + args.workers - 1 >= 2**32:
        parser.error("Der PPO-Seed einschließlich Worker-Offsets muss kleiner als 2**32 sein.")
    output = args.output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("Der Ausgabeordner muss neu oder leer sein; vorhandene Modelle werden nicht überschrieben.")

    try:
        import torch
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.callbacks import BaseCallback
        from stable_baselines3.common.logger import configure
        from stable_baselines3.common.vec_env import SubprocVecEnv
        from SpineML.Control.RLPolicy.CandidateActorCriticPolicy import CandidateActorCriticPolicy
        from SpineML.Control.RLPolicy.TrainingSupport import (
            EnvironmentFactory, build_artifact_context, calibrate_references, load_app_configuration,
        )
    except ImportError as error:
        parser.error(f'Trainingspakete fehlen oder sind nicht ladbar. Installieren: python -m pip install -e ".[rl-training]"\n{error}')
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("--device cuda wurde gewählt, aber diese PyTorch-Installation erkennt keine CUDA-GPU.")
    torch.set_num_threads(1)
    configuration = load_app_configuration()
    baseline_seeds = args.baseline_seeds or configuration["baseline_seeds"]
    evaluation_seeds = args.evaluation_seeds or configuration["test_seeds"]
    if set(evaluation_seeds) & (set(args.train_seeds) | set(baseline_seeds)):
        parser.error("Die Test-Seeds müssen von Trainings- und Baseline-Seeds getrennt sein.")
    if len(set(evaluation_seeds)) != len(evaluation_seeds) or len(set(baseline_seeds)) != len(baseline_seeds):
        parser.error("Baseline- und Test-Seed-Listen dürfen jeweils keine Duplikate enthalten.")
    started_at = perf_counter()
    model_file = args.model or configuration["model_file"]
    print("Referenzen aus vollständigen Standardheuristik-Läufen berechnen ...", flush=True)
    evaluation, baseline_report = calibrate_references(
        model_file, baseline_seeds,
        progress=lambda seed: print(f"  Baseline-Seed {seed}", flush=True),
    )
    env_config = {
        "max_actions": args.max_actions, "max_entities": args.max_entities,
        "max_decisions": args.max_decisions, "max_simulation_time": args.max_simulation_time,
        "response_timeout": 120.0,
    }
    context = build_artifact_context(model_file, evaluation, env_config)
    output.mkdir(parents=True, exist_ok=True)
    hyperparameters = {
        "n_steps": args.rollout_steps, "batch_size": args.batch_size, "n_epochs": args.epochs,
        "learning_rate": args.learning_rate, "gamma": 1.0, "gae_lambda": 1.0,
        "ent_coef": 0.01, "seed": args.seed,
    }
    manifest = {
        "algorithm": "MaskablePPO", "policy_class": "CandidateActorCriticPolicy",
        "artifact_context": context, "baseline": baseline_report,
        "train_seeds": args.train_seeds, "evaluation_seeds": evaluation_seeds,
        "workers": args.workers, "requested_timesteps": args.steps,
        "policy_kwargs": {"embedding_dim": 32, "hidden_dim": 64},
        "hyperparameters": hyperparameters,
        "training_limit_semantics": "terminal failure (-1); no timeout value bootstrap",
        "versions": {name: importlib.metadata.version(name) for name in ("torch", "stable-baselines3", "sb3-contrib", "gymnasium", "SpineML")},
    }
    write_json(output / "manifest.json", manifest)
    episodes: list[dict] = []

    class TrainingProgress(BaseCallback):
        def __init__(self):
            super().__init__()
            self.next_checkpoint = args.checkpoint_every

        def _on_step(self) -> bool:
            for info, done in zip(self.locals["infos"], self.locals["dones"]):
                if not done or "episode" not in info:
                    continue
                event = {
                    "timesteps": int(self.num_timesteps), "seed": info.get("episode_seed"),
                    "decisions": info.get("decision_count"), "reward": float(info["episode"]["r"]),
                    "global_cost": float(info["global_cost"]), "metrics": info["metrics"],
                    "completed": info.get("reward_reason") == "completed",
                    "limit_reason": info.get("truncation_reason"),
                }
                episodes.append(event)
                with (output / "episodes.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                print(f"Episode {len(episodes)}: Seed {event['seed']}, abgeschlossen={event['completed']}, Reward={event['reward']:.5f}, Kosten={event['global_cost']:.5f}", flush=True)
            if self.num_timesteps >= self.next_checkpoint:
                self.model.save(output / f"checkpoint_{self.num_timesteps}.zip")
                self.next_checkpoint = (self.num_timesteps // args.checkpoint_every + 1) * args.checkpoint_every
            return True

    vector_env = None
    model = None
    report = None
    interrupted = False
    training_started_at = perf_counter()
    try:
        factories = [EnvironmentFactory(context["model_file"], context, env_config, tuple(args.train_seeds), rank) for rank in range(args.workers)]
        # Auch bei einem Worker: Salabim bleibt vom Lernprozess getrennt.
        vector_env = SubprocVecEnv(factories, start_method="spawn")
        model = MaskablePPO(
            CandidateActorCriticPolicy, vector_env,
            policy_kwargs=manifest["policy_kwargs"], device=args.device, verbose=1,
            **hyperparameters,
        )
        model.set_logger(configure(str(output), ["stdout", "csv"]))
        print(f"Training: {args.workers} Simulationsprozesse, {samples_per_update} Entscheidungen je PPO-Update, mindestens {args.steps} Entscheidungen insgesamt.", flush=True)
        try:
            model.learn(total_timesteps=args.steps, callback=TrainingProgress())
        except KeyboardInterrupt:
            interrupted = True
            print("Training unterbrochen; aktuellen Modellstand speichern ...", flush=True)
        model.save(output / "model.zip")
        completed = [episode for episode in episodes if episode["completed"]]
        report = {
            "status": "interrupted" if interrupted else "finished",
            "requested_timesteps": args.steps, "actual_timesteps": int(model.num_timesteps),
            "episodes": len(episodes), "completed_episodes": len(completed),
            "limit_episodes": len(episodes) - len(completed),
            "mean_completed_global_cost": sum(item["global_cost"] for item in completed) / len(completed) if completed else None,
            "baseline_elapsed_seconds": baseline_report["elapsed_seconds"],
        }
    except BaseException as error:
        report = {"status": "failed", "error": f"{type(error).__name__}: {error}",
                  "requested_timesteps": args.steps,
                  "actual_timesteps": int(model.num_timesteps) if model is not None else 0,
                  "episodes": len(episodes), "baseline_elapsed_seconds": baseline_report["elapsed_seconds"]}
        raise
    finally:
        try:
            if vector_env is not None:
                vector_env.close()
        except BaseException as error:
            # Ausschließlich die von diesem Vektor-Environment gestarteten Prozesse aufräumen.
            for connection in getattr(vector_env, "remotes", ()):
                try:
                    connection.close()
                except OSError:
                    pass
            for process in getattr(vector_env, "processes", ()):
                if process.is_alive():
                    process.terminate()
                process.join(timeout=10)
            if report is not None:
                report["status"] = "failed"
                report["shutdown_error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            if report is not None:
                report["training_elapsed_seconds"] = perf_counter() - training_started_at
                report["total_elapsed_seconds"] = perf_counter() - started_at
                write_json(output / "training_report.json", report)
    print(f"Modell und Konfiguration gespeichert: {output}", flush=True)
    print(f'Prüfen: python sources/tools/evaluate_rl_policy.py --run-dir "{output}"', flush=True)
    if not episodes:
        print("Hinweis: Noch keine Episode beendet; dieser kurze Lauf weist noch keine erlernte Produktionsstrategie nach.", flush=True)


if __name__ == "__main__":
    main()
