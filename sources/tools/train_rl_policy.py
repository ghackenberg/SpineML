"""Trainiert die Q-Bewertung der Aktionskandidaten mit DQN oder Monte Carlo."""

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
        raise argparse.ArgumentTypeError("Der Wert darf nicht negativ sein.")
    return number


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Der Wert muss endlich und positiv sein.")
    return number


def probability(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError("Die Wahrscheinlichkeit muss zwischen 0 und 1 liegen.")
    return number


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--algorithm", choices=("dqn", "monte-carlo"), default="dqn", help="Lernverfahren; Standard: DQN.")
    parser.add_argument("--model", type=Path, help="Modelldatei; Standard: Beispiel der Optimierungsanwendung.")
    parser.add_argument("--output", type=Path, help="Neuer oder leerer Ausgabeordner; Standard: rl_runs/dqn oder rl_runs/monte_carlo.")
    available_workers = os.cpu_count()
    if not available_workers:
        available_workers = 1
    default_workers = min(available_workers, 4)
    parser.add_argument("--workers", type=positive_int, default=default_workers, help="Getrennte Simulationsprozesse; Standard: höchstens 4.")
    dqn_options = parser.add_argument_group("Nur DQN")
    dqn_options.add_argument("--steps", type=positive_int, default=100_000, help="Mindestens so viele externe Entscheidungen sammeln; Standard: 100000.")
    dqn_options.add_argument("--buffer-size", type=positive_int, default=5000, help="Maximale Zahl gespeicherter Übergänge, über alle Worker zusammen.")
    dqn_options.add_argument("--learning-starts", type=nonnegative_int, default=1000, help="Zunächst so viele neue Entscheidungen sammeln, dann lernen.")
    dqn_options.add_argument("--train-freq", type=positive_int, default=4, help="Neue Schritte je Worker vor der nächsten Lernphase.")
    dqn_options.add_argument("--gradient-steps", type=positive_int, default=4, help="Gewichtsanpassungen aus zufälligen Replay-Batches je Lernphase.")
    mc_options = parser.add_argument_group("Nur Monte Carlo")
    mc_options.add_argument("--episodes", type=positive_int, default=100, help="Genau so viele vollständige Episoden ausführen; Standard: 100.")
    mc_options.add_argument("--epochs", type=positive_int, default=4, help="Trainingsdurchgänge über die ausgewählten Replay-Episoden.")
    mc_options.add_argument("--mc-replay-episodes", type=positive_int, default=8, help="Höchstens so viele vollständige Episoden im Replay Buffer behalten.")
    mc_options.add_argument("--mc-replay-transitions", type=positive_int, default=10000, help="Zusätzliches Übergangslimit für den Episodenspeicher; eine größere einzelne Episode bleibt vollständig erhalten.")
    mc_options.add_argument("--mc-train-every-episodes", type=positive_int, default=4, help="Nach so vielen neu eingetroffenen Episoden trainieren, ohne auf andere Worker zu warten.")
    mc_options.add_argument("--mc-replay-sample-episodes", type=positive_int, default=4, help="Höchstens so viele gespeicherte Episoden je Lernphase auswählen.")
    parser.add_argument("--batch-size", type=positive_int, default=64)
    parser.add_argument("--learning-rate", type=positive_float, default=0.0001)
    dqn_options.add_argument("--target-update-interval", type=positive_int, default=1000, help="Target-Gewichte ungefähr alle so vielen Entscheidungen nachführen.")
    parser.add_argument("--exploration-fraction", type=positive_float, default=0.3, help="Anteil des Trainings, in dem Epsilon sinkt: DQN nach Entscheidungen, Monte Carlo nach Episoden.")
    parser.add_argument("--exploration-initial-eps", type=probability, default=1.0)
    parser.add_argument("--exploration-final-eps", type=probability, default=0.05)
    parser.add_argument("--save-replay-buffer", action="store_true", help="Replay Buffer am Ende zusätzlich als replay_buffer.pkl speichern; kann groß werden.")
    parser.add_argument("--train-seeds", type=nonnegative_int, nargs="+", default=list(range(1, 11)))
    parser.add_argument("--baseline-seeds", type=nonnegative_int, nargs="+", help="Standard: SEEDS der Optimierungsanwendung.")
    parser.add_argument("--evaluation-seeds", type=nonnegative_int, nargs="+", help="Reservierte Test-Seeds; Standard: TEST_SEEDS der Anwendung.")
    parser.add_argument("--seed", type=nonnegative_int, default=0, help="Seed für Netzinitialisierung, Exploration und Replay-Stichproben.")
    parser.add_argument("--max-decisions", type=positive_int, default=10_000)
    parser.add_argument("--max-simulation-time", type=positive_float, default=10_000.0)
    parser.add_argument("--max-actions", type=positive_int, default=256)
    parser.add_argument("--max-entities", type=positive_int, default=256)
    parser.add_argument("--checkpoint-every", type=positive_int, help="Abstand gespeicherter Zwischenstände: DQN in Entscheidungen (Standard 10000), Monte Carlo in Episoden (Standard 10).")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu", help="Nur das Netz; die Salabim-Simulation bleibt auf der CPU.")
    args = parser.parse_args()

    dqn_only_flags = (
        "--steps", "--buffer-size", "--learning-starts", "--train-freq",
        "--gradient-steps", "--target-update-interval",
    )
    mc_only_flags = (
        "--episodes", "--epochs", "--mc-replay-episodes", "--mc-replay-transitions",
        "--mc-train-every-episodes", "--mc-replay-sample-episodes",
    )
    forbidden_flags = mc_only_flags
    if args.algorithm == "monte-carlo":
        forbidden_flags = dqn_only_flags
    for argument in sys.argv[1:]:
        option = argument.split("=", 1)[0]
        if option in forbidden_flags:
            parser.error(f"{option} gehört nicht zu --algorithm {args.algorithm}.")
    if args.checkpoint_every is None:
        args.checkpoint_every = 10_000
        if args.algorithm == "monte-carlo":
            args.checkpoint_every = 10
    if args.algorithm == "dqn" and args.buffer_size < args.workers:
        parser.error("--buffer-size muss mindestens so groß wie --workers sein.")
    if args.algorithm == "monte-carlo":
        if args.exploration_initial_eps <= 0 or args.exploration_final_eps <= 0:
            parser.error("Monte Carlo benötigt positive Epsilon-Werte, damit alle gültigen Aktionen eine Auswahlwahrscheinlichkeit haben.")
    if args.exploration_fraction > 1.0:
        parser.error("--exploration-fraction muss größer als 0 und höchstens 1 sein.")
    if len(set(args.train_seeds)) != len(args.train_seeds):
        parser.error("--train-seeds darf keine doppelten Seeds enthalten.")
    if args.seed + args.workers - 1 >= 2**32:
        parser.error("Der Trainings-Seed einschließlich Worker-Offsets muss kleiner als 2**32 sein.")
    if args.output is None:
        args.output = Path("rl_runs/dqn")
        if args.algorithm == "monte-carlo":
            args.output = Path("rl_runs/monte_carlo")
    output = args.output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("Der Ausgabeordner muss neu oder leer sein; vorhandene Modelle werden nicht überschrieben.")

    try:
        import numpy as np
        import torch
        from stable_baselines3.common.callbacks import BaseCallback
        from stable_baselines3.common.logger import configure
        from stable_baselines3.common.vec_env import SubprocVecEnv
        from SpineML.Control.RLPolicy.DQN.CandidateDQN import CandidateDQN
        from SpineML.Control.RLPolicy.DQN.CandidateDQNPolicy import CandidateDQNPolicy
        from SpineML.Control.RLPolicy.MonteCarlo.CandidateMonteCarlo import CandidateMonteCarlo, CandidateMonteCarloPolicy
        from SpineML.Control.RLPolicy.Shared.TrainingSupport import (
            EnvironmentFactory, build_artifact_context, calibrate_references, load_app_configuration,
        )
    except ImportError as error:
        parser.error(f'Trainingspakete fehlen oder sind nicht ladbar. Installieren: python -m pip install -e ".[rl-training]"\n{error}')
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("--device cuda wurde gewählt, aber diese PyTorch-Installation erkennt keine CUDA-GPU.")
    torch.set_num_threads(1)
    configuration = load_app_configuration()
    baseline_seeds = args.baseline_seeds
    if not baseline_seeds:
        baseline_seeds = configuration["baseline_seeds"]
    evaluation_seeds = args.evaluation_seeds
    if not evaluation_seeds:
        evaluation_seeds = configuration["test_seeds"]
    if set(evaluation_seeds) & (set(args.train_seeds) | set(baseline_seeds)):
        parser.error("Die Test-Seeds müssen von Trainings- und Baseline-Seeds getrennt sein.")
    if len(set(evaluation_seeds)) != len(evaluation_seeds) or len(set(baseline_seeds)) != len(baseline_seeds):
        parser.error("Baseline- und Test-Seed-Listen dürfen jeweils keine Duplikate enthalten.")
    started_at = perf_counter()
    model_file = args.model
    if not model_file:
        model_file = configuration["model_file"]
    print("Referenzen aus vollständigen Standardheuristik-Läufen berechnen ...", flush=True)

    def print_baseline_progress(seed: int) -> None:
        print(f"  Baseline-Seed {seed}", flush=True)

    evaluation, baseline_report = calibrate_references(
        model_file, baseline_seeds,
        progress=print_baseline_progress,
    )
    env_config = {
        "max_actions": args.max_actions, "max_entities": args.max_entities,
        "max_decisions": args.max_decisions, "max_simulation_time": args.max_simulation_time,
        "response_timeout": 120.0,
    }
    context = build_artifact_context(model_file, evaluation, env_config)
    output.mkdir(parents=True, exist_ok=True)
    hyperparameters = {
        "batch_size": args.batch_size, "learning_rate": args.learning_rate,
        "exploration_fraction": args.exploration_fraction,
        "exploration_initial_eps": args.exploration_initial_eps,
        "exploration_final_eps": args.exploration_final_eps,
        "gamma": 1.0, "seed": args.seed,
    }
    algorithm_name = "DQN"
    policy_name = "CandidateDQNPolicy"
    requested_budget = {"requested_timesteps": args.steps}
    if args.algorithm == "dqn":
        hyperparameters.update({
            "buffer_size": args.buffer_size, "learning_starts": args.learning_starts,
            "train_freq": args.train_freq, "gradient_steps": args.gradient_steps,
            "target_update_interval": args.target_update_interval, "tau": 1.0,
        })
    else:
        algorithm_name = "MonteCarlo"
        policy_name = "CandidateMonteCarloPolicy"
        requested_budget = {"requested_episodes": args.episodes}
        hyperparameters.update({
            "epochs": args.epochs,
            "replay_episodes": args.mc_replay_episodes,
            "replay_transitions": args.mc_replay_transitions,
            "train_every_episodes": args.mc_train_every_episodes,
            "replay_sample_episodes": args.mc_replay_sample_episodes,
        })
    versions = {}
    for name in ("torch", "stable-baselines3", "gymnasium", "SpineML"):
        versions[name] = importlib.metadata.version(name)
    manifest = {
        "algorithm": algorithm_name, "policy_class": policy_name,
        "artifact_context": context, "baseline": baseline_report,
        "train_seeds": args.train_seeds, "evaluation_seeds": evaluation_seeds,
        "workers": args.workers,
        "policy_kwargs": {"embedding_dim": 32, "hidden_dim": 64},
        "hyperparameters": hyperparameters,
        "training_limit_semantics": "terminal failure (-1); no timeout value bootstrap",
        "save_replay_buffer": args.save_replay_buffer,
        "versions": versions,
    }
    manifest.update(requested_budget)
    if args.algorithm == "monte-carlo":
        manifest["monte_carlo_mode"] = "asynchronous_off_policy_episode_replay"
        manifest["monte_carlo_correction"] = "self_normalised_future_action_importance_weights"
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
                if args.algorithm == "monte-carlo":
                    event["policy_version"] = info.get("policy_version")
                    event["worker_pid"] = info.get("worker_pid")
                    event["worker_id"] = info.get("worker_id")
                    event["episode_epsilon"] = info.get("episode_epsilon")
                    event["episode_elapsed_seconds"] = info.get("episode_elapsed_seconds")
                episodes.append(event)
                with (output / "episodes.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                print(f"Episode {len(episodes)}: Seed {event['seed']}, abgeschlossen={event['completed']}, Reward={event['reward']:.5f}, Kosten={event['global_cost']:.5f}", flush=True)
            checkpoint_count = self.num_timesteps
            checkpoint_name = f"checkpoint_{checkpoint_count}.zip"
            if args.algorithm == "monte-carlo":
                checkpoint_count = len(episodes)
                checkpoint_name = f"checkpoint_episodes_{checkpoint_count}.zip"
            if checkpoint_count >= self.next_checkpoint:
                self.model.save(output / checkpoint_name)
                self.next_checkpoint = (checkpoint_count // args.checkpoint_every + 1) * args.checkpoint_every
            return True

    vector_env = None
    model = None
    report = None
    interrupted = False
    training_started_at = perf_counter()
    try:
        factories = []
        for rank in range(args.workers):
            factory = EnvironmentFactory(
                context["model_file"], context, env_config, tuple(args.train_seeds), rank,
            )
            factories.append(factory)
        if args.algorithm == "dqn":
            vector_env = SubprocVecEnv(factories, start_method="spawn")
            observation_bytes = 0
            for space in vector_env.observation_space.spaces.values():
                observation_bytes += math.prod(space.shape) * np.dtype(space.dtype).itemsize
            effective_capacity = (args.buffer_size // args.workers) * args.workers
            replay_gib = 2 * observation_bytes * effective_capacity / 1024**3
            print(f"Replay: ungefähr {replay_gib:.2f} GiB für Zustände und Folgezustände im CPU-Arbeitsspeicher.", flush=True)
            model = CandidateDQN(
                CandidateDQNPolicy, vector_env,
                policy_kwargs=manifest["policy_kwargs"], device=args.device, verbose=1,
                **hyperparameters,
            )
        else:
            # Diese Umgebung liefert nur die Eingabegrößen; simuliert wird in eigenen Workern.
            vector_env = factories[0]()
            model = CandidateMonteCarlo(
                CandidateMonteCarloPolicy, vector_env, episode_factories=factories,
                policy_kwargs=manifest["policy_kwargs"], device=args.device, verbose=1,
                **hyperparameters,
            )
        model.set_logger(configure(str(output), ["stdout", "csv"]))
        if args.algorithm == "dqn":
            new_decisions_per_collection = args.workers * args.train_freq
            print(f"DQN: {args.workers} Simulationsprozesse, {new_decisions_per_collection} neue Entscheidungen je Sammelabschnitt, danach {args.gradient_steps} Replay-Updates ab Entscheidung {args.learning_starts}.", flush=True)
        else:
            active_workers = min(args.workers, args.episodes)
            print(f"Monte Carlo: genau {args.episodes} Episoden mit bis zu {active_workers} unabhängigen Simulationsprozessen; nach je {args.mc_train_every_episodes} fertigen Episoden mit bis zu {args.mc_replay_sample_episodes} Replay-Episoden trainieren. Solange Episoden übrig sind, starten fertige Worker sofort mit dem neuesten verfügbaren Netzstand neu.", flush=True)
        try:
            if args.algorithm == "dqn":
                model.learn(total_timesteps=args.steps, callback=TrainingProgress(), log_interval=1)
            else:
                model.learn(total_episodes=args.episodes, callback=TrainingProgress())
        except KeyboardInterrupt:
            interrupted = True
            print("Training unterbrochen; aktuellen Modellstand speichern ...", flush=True)
        model.save(output / "model.zip")
        if args.save_replay_buffer:
            model.save_replay_buffer(output / "replay_buffer.pkl")
        completed = []
        for episode in episodes:
            if episode["completed"]:
                completed.append(episode)
        mean_completed_global_cost = None
        if completed:
            costs = []
            for item in completed:
                costs.append(item["global_cost"])
            mean_completed_global_cost = sum(costs) / len(completed)
        status = "finished"
        if interrupted:
            status = "interrupted"
        report = {
            "status": status, "algorithm": algorithm_name,
            "actual_timesteps": int(model.num_timesteps),
            "episodes": len(episodes), "completed_episodes": len(completed),
            "limit_episodes": len(episodes) - len(completed),
            "mean_completed_global_cost": mean_completed_global_cost,
            "baseline_elapsed_seconds": baseline_report["elapsed_seconds"],
            "gradient_updates": int(model._n_updates),
            "exploration_rate": float(model.exploration_rate),
        }
        report.update(requested_budget)
        if args.algorithm == "dqn":
            report["replay_transitions"] = int(model.replay_buffer.size() * model.n_envs)
        else:
            report["completed_batches"] = int(model.completed_batches)
            report["collected_transitions"] = int(model.collected_transitions)
            report["policy_version"] = int(model.policy_version)
            report["replay_episodes"] = len(model.replay_buffer)
            report["replay_transitions"] = int(model.replay_buffer.transition_count)
            report["replay_oversized_episode"] = bool(model.replay_buffer.oversized_episode)
            report["last_return_min"] = model.last_return_min
            report["last_return_max"] = model.last_return_max
            report["last_loss"] = model.last_loss
            report["last_importance_ess"] = model.last_importance_ess
            report["last_importance_max_weight"] = model.last_importance_max_weight
            report["worker_pids"] = sorted(model.worker_pids)
    except BaseException as error:
        actual_timesteps = 0
        if model is not None:
            actual_timesteps = int(model.num_timesteps)
        report = {"status": "failed", "error": f"{type(error).__name__}: {error}",
                  "actual_timesteps": actual_timesteps,
                  "episodes": len(episodes), "baseline_elapsed_seconds": baseline_report["elapsed_seconds"]}
        report.update(requested_budget)
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
