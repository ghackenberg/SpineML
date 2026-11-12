"""Bereitet das Monte-Carlo-Modell vor und startet sein Training."""

from __future__ import annotations

from tools.monte_carlo_reports import MonteCarloReports, write_manifest


def train_monte_carlo(args, context: dict, baseline_report: dict, started_at: float) -> None:
    from SpineML.Control.RLPolicy.MonteCarlo.MonteCarloModel import MonteCarloModel
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
        model = MonteCarloModel(
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

    runtime = write_manifest(args, context, baseline_report, model, active_workers)
    reports = MonteCarloReports(args, runtime, baseline_report, started_at)

    print(f"Tianshou REINFORCE: {args.episodes} neue Episoden mit bis zu {active_workers} "
          f"Simulationsprozessen; nach jeweils höchstens {args.episodes_per_update} "
          "Episoden lernen. Kein Wiederverwenden älterer Trainingsphasen.", flush=True)
    print(f"Netzberechnungen auf {model.device}; PyTorch {runtime['torch_version']}.", flush=True)
    report = None
    interrupted = False
    try:
        try:
            model.learn(args.episodes, on_episode=reports.on_episode, on_update=reports.on_update)
        except KeyboardInterrupt:
            interrupted = True
            print("Training unterbrochen; aktuellen Netzstand speichern ...", flush=True)
        model.save(output / "model.pt")
        report = reports.finished_report(model, interrupted)
    except BaseException as error:
        report = reports.failed_report(model, error)
        raise
    finally:
        if report is not None:
            reports.write_report(report)
    print(f"Modell und Berichte gespeichert: {output}", flush=True)
    print(f'Prüfen: python sources/tools/evaluate_rl_policy.py --run-dir "{output}"', flush=True)
