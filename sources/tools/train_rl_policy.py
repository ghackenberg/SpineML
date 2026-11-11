"""Trainiert Tianshou REINFORCE mit der Salabim-Fabrikumgebung."""

from __future__ import annotations

import argparse
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


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--model", type=Path, help="Standard: Beispiel der Optimierungsanwendung.")
    parser.add_argument("--output", type=Path, default=Path("rl_runs/reinforce"), help="Neuer oder leerer Ausgabeordner.")
    parser.add_argument("--episodes", type=positive_int, default=100, help="Anzahl vollständiger Episoden einschließlich möglicher Sicherheitsabbrüche.")
    available_workers = os.cpu_count() or 1
    parser.add_argument("--workers", type=positive_int, default=min(available_workers, 4), help="Getrennte Simulationsprozesse; Standard: höchstens 4.")
    parser.add_argument("--episodes-per-update", type=positive_int, help="Neue Episoden je Lernphase; Standard: min(workers, episodes).")
    parser.add_argument("--buffer-size", type=positive_int, help="Plätze für vollständige Episoden der aktuellen Lerngruppe; automatisch pro Worker bemessen. Kein alter Episoden-Replay.")
    parser.add_argument("--batch-size", type=positive_int, default=64, help="Entscheidungen je Minibatch der Gewichtsänderung.")
    parser.add_argument("--learning-rate", type=positive_float, default=0.0001)
    parser.add_argument("--train-seeds", type=nonnegative_int, nargs="+", default=list(range(1, 11)))
    parser.add_argument("--baseline-seeds", type=nonnegative_int, nargs="+", help="Standard: SEEDS der Optimierungsanwendung.")
    parser.add_argument("--evaluation-seeds", type=nonnegative_int, nargs="+", help="Reservierte Test-Seeds; Standard: TEST_SEEDS der Anwendung.")
    parser.add_argument("--seed", type=nonnegative_int, default=0, help="Seed für Netzinitialisierung und Aktionsauswahl.")
    parser.add_argument("--max-decisions", type=positive_int, default=10_000)
    parser.add_argument("--max-simulation-time", type=positive_float, default=10_000.0)
    parser.add_argument("--max-actions", type=positive_int, default=256)
    parser.add_argument("--max-entities", type=positive_int, default=256)
    parser.add_argument("--checkpoint-every", type=positive_int, default=10)
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu", help="Nur das Netz; Salabim bleibt auf der CPU.")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Tianshou 2 benötigt Python ab 3.11. Bitte die .venv-reinforce mit Python 3.12 verwenden.")
    if args.episodes_per_update is None:
        args.episodes_per_update = min(args.workers, args.episodes)
    if len(set(args.train_seeds)) != len(args.train_seeds):
        parser.error("--train-seeds darf keine doppelten Seeds enthalten.")
    if args.seed + args.workers - 1 >= 2**32:
        parser.error("Der Trainings-Seed einschließlich Worker-Offsets muss kleiner als 2**32 sein.")
    args.output = args.output.resolve()
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("Der Ausgabeordner muss neu oder leer sein; vorhandene Modelle werden nicht überschrieben.")
    return parser, args


def main() -> None:
    parser, args = parse_arguments()
    os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
    try:
        import torch
        import tianshou
        from SpineML.Control.RLPolicy.Shared.TrainingSupport import (
            build_artifact_context, calibrate_references, load_app_configuration,
        )
        from tools.reinforce_training import train_reinforce
    except ImportError as error:
        parser.error(f'Trainingspakete fehlen: python -m pip install -e ".[rl-training]"\n{error}')
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("--device cuda wurde gewählt, aber diese PyTorch-Installation erkennt keine CUDA-GPU.")
    if args.device != "cpu" and torch.cuda.is_available():
        try:
            probe = torch.empty(1, device="cuda")
            torch.cuda.synchronize()
            del probe
        except RuntimeError as error:
            parser.error(f"Die GPU ist für Berechnungen nicht verfügbar. --device cpu verwenden.\n{error}")
    torch.set_num_threads(1)
    configuration = load_app_configuration()
    if args.baseline_seeds is None:
        args.baseline_seeds = configuration["baseline_seeds"]
    if args.evaluation_seeds is None:
        args.evaluation_seeds = configuration["test_seeds"]
    for seeds in (args.baseline_seeds, args.evaluation_seeds):
        if not seeds or len(set(seeds)) != len(seeds):
            parser.error("Baseline- und Test-Seeds müssen nichtleere Listen ohne Duplikate sein.")
    for seeds in (args.train_seeds, args.baseline_seeds, args.evaluation_seeds):
        for seed in seeds:
            if not 0 <= seed < 2**64:
                parser.error("Simulations-Seeds müssen zwischen 0 und 2**64-1 liegen.")
    if set(args.evaluation_seeds) & (set(args.train_seeds) | set(args.baseline_seeds)):
        parser.error("Test-Seeds müssen von Trainings- und Baseline-Seeds getrennt sein.")
    started_at = perf_counter()
    model_file = args.model or configuration["model_file"]
    print(f"Tianshou {tianshou.__version__}: REINFORCE.", flush=True)
    print("Referenzen aus vollständigen Standardheuristik-Läufen berechnen ...", flush=True)
    evaluation, baseline_report = calibrate_references(
        model_file, args.baseline_seeds,
        progress=lambda seed: print(f"  Baseline-Seed {seed}", flush=True),
    )
    env_config = {
        "max_actions": args.max_actions, "max_entities": args.max_entities,
        "max_decisions": args.max_decisions, "max_simulation_time": args.max_simulation_time,
        "response_timeout": 120.0,
    }
    context = build_artifact_context(model_file, evaluation, env_config)
    args.output.mkdir(parents=True, exist_ok=True)
    train_reinforce(args, context, baseline_report, started_at)


if __name__ == "__main__":
    main()
