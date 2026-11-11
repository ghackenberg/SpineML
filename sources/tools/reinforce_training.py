"""Verbindet den REINFORCE-Trainer mit Dateien und Fortschrittsmeldungen."""

from __future__ import annotations

import csv
import importlib.metadata
import json
from pathlib import Path
from time import perf_counter


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def train_reinforce(args, context: dict, baseline_report: dict, started_at: float) -> None:
    import torch

    from SpineML.Control.RLPolicy.MonteCarlo.ReinforceModel import ReinforceModel
    from SpineML.Control.RLPolicy.Shared.TrainingSupport import EnvironmentFactory

    output = args.output.resolve()
    active_workers = min(args.workers, args.episodes, args.episodes_per_update)
    factories = []
    for rank in range(active_workers):
        factories.append(EnvironmentFactory(
            context["model_file"], context, context["environment"],
            tuple(args.train_seeds), rank,
        ))

    # Nur die Ein- und Ausgabegrößen lesen; echte Episoden laufen in eigenen Prozessen.
    environment = factories[0]()
    try:
        model = ReinforceModel(
            environment.observation_space, environment.action_space, factories,
            learning_rate=args.learning_rate,
            batch_size=args.batch_size,
            episodes_per_update=args.episodes_per_update,
            buffer_capacity=args.buffer_size,
            max_decisions=args.max_decisions,
            device=args.device,
            seed=args.seed,
        )
    finally:
        environment.close()

    versions = {}
    for name in ("torch", "tianshou", "gymnasium", "SpineML"):
        versions[name] = importlib.metadata.version(name)
    runtime = {
        "requested_device": args.device,
        "actual_device": str(model.device),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": None,
    }
    if model.device.type == "cuda":
        runtime["gpu_name"] = torch.cuda.get_device_name(model.device)
    manifest = {
        "algorithm": "TianshouREINFORCE",
        "policy_class": "ReinforcePolicy",
        "checkpoint_file": "model.pt",
        "artifact_context": context,
        "baseline": baseline_report,
        "train_seeds": args.train_seeds,
        "evaluation_seeds": args.evaluation_seeds,
        "workers": active_workers,
        "requested_workers": args.workers,
        "requested_episodes": args.episodes,
        "policy_kwargs": {"embedding_dim": 32, "hidden_dim": 64},
        "hyperparameters": {
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "gamma": 1.0,
            "episodes_per_update": args.episodes_per_update,
            "buffer_size": model.buffer_capacity,
            "seed": args.seed,
        },
        "trainer": "tianshou.trainer.OnPolicyTrainer",
        "learning_rule": "tianshou.algorithm.modelfree.reinforce.Reinforce",
        "training_mode": "on_policy_complete_episodes",
        "training_limit_semantics": "terminal failure (-1); no timeout value bootstrap",
        "versions": versions,
        "runtime": runtime,
    }
    _write_json(output / "manifest.json", manifest)
    episodes = []
    progress = {"next_checkpoint": args.checkpoint_every}
    training_started_at = perf_counter()
    report = None

    def on_episode(info: dict) -> None:
        event = {
            "episode": len(episodes) + 1,
            "timesteps": int(info["timesteps"]),
            "seed": int(info["episode_seed"]),
            "decisions": int(info["decision_count"]),
            "reward": float(info["reward"]),
            "global_cost": float(info["global_cost"]),
            "metrics": info["metrics"],
            "completed": info.get("reward_reason") == "completed",
            "limit_reason": info.get("truncation_reason"),
        }
        if info.get("worker_pid") is not None:
            event["worker_pid"] = int(info["worker_pid"])
        episodes.append(event)
        with (output / "episodes.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        print(f"Episode {event['episode']}/{args.episodes}: Seed {event['seed']}, "
              f"abgeschlossen={event['completed']}, Reward={event['reward']:.5f}, "
              f"Kosten={event['global_cost']:.5f}", flush=True)

    def on_update(current_model, event: dict) -> None:
        # Zwischenstände erst nach der Gewichtsänderung speichern.
        path = output / "progress.csv"
        write_header = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=(
                "episodes", "timesteps", "gradient_updates", "last_loss",
            ))
            if write_header:
                writer.writeheader()
            writer.writerow(event)
        print(f"REINFORCE-Lernphase: {event['episodes']} Episoden gesammelt, "
              f"{event['gradient_updates']} Gewichtsänderungen.", flush=True)
        if current_model.episodes_collected >= progress["next_checkpoint"]:
            count = current_model.episodes_collected
            current_model.save(output / f"checkpoint_episodes_{count}.pt")
            progress["next_checkpoint"] = (count // args.checkpoint_every + 1) * args.checkpoint_every

    print(f"Tianshou REINFORCE: {args.episodes} neue Episoden mit bis zu {active_workers} "
          f"Simulationsprozessen; nach jeweils höchstens {args.episodes_per_update} "
          "Episoden lernen. Kein Wiederverwenden älterer Trainingsphasen.", flush=True)
    print(f"Netzberechnungen auf {model.device}; PyTorch {torch.__version__}.", flush=True)
    interrupted = False
    try:
        try:
            model.learn(args.episodes, on_episode=on_episode, on_update=on_update)
        except KeyboardInterrupt:
            interrupted = True
            print("Training unterbrochen; aktuellen Netzstand speichern ...", flush=True)
        model.save(output / "model.pt")
        completed = []
        for episode in episodes:
            if episode["completed"]:
                completed.append(episode)
        mean_cost = None
        if completed:
            total_cost = 0.0
            for episode in completed:
                total_cost += episode["global_cost"]
            mean_cost = total_cost / len(completed)
        status = "finished"
        if interrupted:
            status = "interrupted"
        report = {
            "status": status,
            "algorithm": "TianshouREINFORCE",
            "requested_episodes": args.episodes,
            "episodes": len(episodes),
            "completed_episodes": len(completed),
            "limit_episodes": len(episodes) - len(completed),
            "actual_timesteps": int(model.num_timesteps),
            "gradient_updates": int(model.gradient_updates),
            "last_loss": model.last_loss,
            "worker_pids": sorted(model.worker_pids),
            "mean_completed_global_cost": mean_cost,
        }
    except BaseException as error:
        report = {
            "status": "failed", "algorithm": "TianshouREINFORCE",
            "error": f"{type(error).__name__}: {error}",
            "requested_episodes": args.episodes, "episodes": len(episodes),
            "actual_timesteps": int(model.num_timesteps),
        }
        raise
    finally:
        if report is not None:
            report["runtime"] = runtime
            report["baseline_elapsed_seconds"] = baseline_report["elapsed_seconds"]
            report["training_elapsed_seconds"] = perf_counter() - training_started_at
            report["total_elapsed_seconds"] = perf_counter() - started_at
            _write_json(output / "training_report.json", report)
    print(f"Modell und Berichte gespeichert: {output}", flush=True)
    print(f'Prüfen: python sources/tools/evaluate_rl_policy.py --run-dir "{output}"', flush=True)
