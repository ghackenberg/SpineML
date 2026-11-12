"""Schreibt Manifest, Lernfortschritt und Abschlussbericht des Trainings."""

from __future__ import annotations

import csv
import importlib.metadata
import json
from pathlib import Path
from time import perf_counter


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_manifest(args, context: dict, baseline_report: dict, model, active_workers: int) -> dict:
    """Hält Konfiguration und Laufzeitumgebung vor der ersten Lernphase fest."""
    import torch

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
        "policy_class": "MonteCarloPolicy",
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
    write_json(args.output.resolve() / "manifest.json", manifest)
    return runtime


class MonteCarloReports:
    """Gemeinsamer Zustand der beiden Rückmeldungen: Episoden und Speicherintervall."""

    def __init__(self, args, runtime: dict, baseline_report: dict, started_at: float):
        self.output = args.output.resolve()
        self.requested_episodes = args.episodes
        self.checkpoint_every = args.checkpoint_every
        self.next_checkpoint = args.checkpoint_every
        self.episodes = []
        self.runtime = runtime
        self.baseline_elapsed_seconds = baseline_report["elapsed_seconds"]
        self.started_at = started_at
        self.training_started_at = perf_counter()

    def on_episode(self, info: dict) -> None:
        event = {
            "episode": len(self.episodes) + 1,
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
        self.episodes.append(event)
        with (self.output / "episodes.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        print(f"Episode {event['episode']}/{self.requested_episodes}: Seed {event['seed']}, "
              f"abgeschlossen={event['completed']}, Reward={event['reward']:.5f}, "
              f"Kosten={event['global_cost']:.5f}", flush=True)

    def on_update(self, model, event: dict) -> None:
        path = self.output / "progress.csv"
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
        # Nur nach einer Gewichtsänderung speichern; übersprungene Intervalle nicht nachholen.
        if model.episodes_collected >= self.next_checkpoint:
            count = model.episodes_collected
            model.save(self.output / f"checkpoint_episodes_{count}.pt")
            self.next_checkpoint = (count // self.checkpoint_every + 1) * self.checkpoint_every

    def finished_report(self, model, interrupted: bool) -> dict:
        completed = []
        for episode in self.episodes:
            if episode["completed"]:
                completed.append(episode)
        mean_cost = None
        if completed:
            total_cost = 0.0
            for episode in completed:
                total_cost += episode["global_cost"]
            mean_cost = total_cost / len(completed)
        status = "interrupted" if interrupted else "finished"
        return {
            "status": status,
            "algorithm": "TianshouREINFORCE",
            "requested_episodes": self.requested_episodes,
            "episodes": len(self.episodes),
            "completed_episodes": len(completed),
            "limit_episodes": len(self.episodes) - len(completed),
            "actual_timesteps": int(model.num_timesteps),
            "gradient_updates": int(model.gradient_updates),
            "last_loss": model.last_loss,
            "worker_pids": sorted(model.worker_pids),
            "mean_completed_global_cost": mean_cost,
        }

    def failed_report(self, model, error: BaseException) -> dict:
        return {
            "status": "failed", "algorithm": "TianshouREINFORCE",
            "error": f"{type(error).__name__}: {error}",
            "requested_episodes": self.requested_episodes,
            "episodes": len(self.episodes),
            "actual_timesteps": int(model.num_timesteps),
        }

    def write_report(self, report: dict) -> None:
        report["runtime"] = self.runtime
        report["baseline_elapsed_seconds"] = self.baseline_elapsed_seconds
        report["training_elapsed_seconds"] = perf_counter() - self.training_started_at
        report["total_elapsed_seconds"] = perf_counter() - self.started_at
        write_json(self.output / "training_report.json", report)
