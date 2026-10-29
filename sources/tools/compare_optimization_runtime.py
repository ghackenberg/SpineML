"""Vergleicht vollständige Optimierungsläufe sequenziell und im Prozesspool."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


DEFAULT_OUTPUT = Path("optimization_timing_comparison.json")
PROGRESS_INTERVAL_SECONDS = 5.0


def _write_json(path: Path, payload: dict) -> None:
    """Ersetzt den Bericht atomar, damit ein vorhandenes Teilergebnis erhalten bleibt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as output:
            temporary_path = Path(output.name)
            json.dump(payload, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _validate_report(report, execution_mode: str) -> dict:
    """Verlangt einen vollständigen, JSON-kompatiblen Workflowbericht."""
    required = {
        "execution_mode", "max_workers", "elapsed_seconds", "phase_seconds",
        "simulation_count", "configuration", "results",
    }
    if not isinstance(report, dict) or not required.issubset(report):
        raise RuntimeError("Der Optimierungslauf hat keinen vollständigen run_report geliefert.")
    if report["execution_mode"] != execution_mode:
        raise RuntimeError("Der gemeldete Ausführungsmodus stimmt nicht mit dem Auftrag überein.")
    elapsed = report["elapsed_seconds"]
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed <= 0
    ):
        raise RuntimeError("Der Workflowbericht enthält keine gültige positive Gesamtlaufzeit.")
    if not isinstance(report["phase_seconds"], dict):
        raise RuntimeError("Die Phasenlaufzeiten fehlen im Workflowbericht.")
    if not isinstance(report["configuration"], dict):
        raise RuntimeError("Die gemeinsame Laufkonfiguration fehlt im Workflowbericht.")
    if (
        isinstance(report["simulation_count"], bool)
        or not isinstance(report["simulation_count"], int)
        or report["simulation_count"] < 0
    ):
        raise RuntimeError("Die Zahl der Simulationsläufe ist ungültig.")
    # Eine eigene Datenkopie verhindert nachträgliche Änderungen durch den Hintergrundthread.
    return json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))


def _run_child_mode(args) -> int:
    """Nutzt denselben App-Workflow, ohne Webserver oder Oberfläche zu starten."""
    state = {}
    try:
        # Erst hier importieren: --help und Spawn benötigen keine GUI-Bibliotheken.
        sources_directory = str(Path(__file__).resolve().parents[1])
        if sys.path[:1] != [sources_directory]:
            sys.path.insert(0, sources_directory)
        from apps import heuristic_optimization_app as optimization

        model_file = args.model
        if model_file is None:
            model_file = os.environ.get("SPINEML_MODEL_FILE", optimization.EXAMPLE_FILE)
        model_path = optimization._resolve_model_path(model_file)
        print(f"\nModus: {args._mode}; Modell: {model_path}", flush=True)
        optimization._start_optimization(
            state, str(model_path), execution_mode=args._mode, timing_context="headless",
        )
        next_progress_at = time.monotonic()
        while state.get("running", False):
            now = time.monotonic()
            if now >= next_progress_at:
                phase = state.get("phase") or "Workflow wird vorbereitet ..."
                print(f"[{args._mode}] {phase}", flush=True)
                next_progress_at = now + PROGRESS_INTERVAL_SECONDS
            time.sleep(0.2)

        # running wird von der App erst nach dem vollständigen Pool-Shutdown gelöscht.
        if state.get("error"):
            raise RuntimeError(state["error"])
        report = _validate_report(state.get("run_report"), args._mode)
        _write_json(args._report, {"status": "complete", "report": report})
        print(
            f"[{args._mode}] Gesamt: {report['elapsed_seconds']:.3f} s; "
            f"Simulationsläufe: {report['simulation_count']}; "
            f"Prozesse: {report['max_workers']}",
            flush=True,
        )
        return 0
    except (Exception, KeyboardInterrupt) as error:
        message = "Vergleich unterbrochen." if isinstance(error, KeyboardInterrupt) else str(error)
        _write_json(args._report, {
            "status": "failed", "execution_mode": args._mode, "error": message,
        })
        print(f"[{args._mode}] Fehler: {message}", file=sys.stderr, flush=True)
        return 130 if isinstance(error, KeyboardInterrupt) else 1


def _first_difference(expected, actual, path: str) -> str | None:
    """Benennt die erste Abweichung, ohne große Ergebnislisten im Terminal auszugeben."""
    if expected == actual:
        return None
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return f"{path}: unterschiedliche Schlüssel"
        for key in expected:
            difference = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference is not None:
                return difference
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}: unterschiedliche Listenlängen"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            difference = _first_difference(expected_item, actual_item, f"{path}[{index}]")
            if difference is not None:
                return difference
    return f"{path}: {expected!r} != {actual!r}"


def compare_reports(sequential: dict, parallel: dict) -> dict:
    """Vergleicht semantische Ergebnisse exakt; Laufzeiten und Prozesszahlen dürfen abweichen."""
    sequential = _validate_report(sequential, "sequential")
    parallel = _validate_report(parallel, "parallel")
    comparison = {
        "configuration_equal": sequential["configuration"] == parallel["configuration"],
        "results_equal": sequential["results"] == parallel["results"],
        "simulation_count_equal": sequential["simulation_count"] == parallel["simulation_count"],
        "sequential_seconds": sequential["elapsed_seconds"],
        "parallel_seconds": parallel["elapsed_seconds"],
    }
    comparison["equal"] = all(comparison[key] for key in (
        "configuration_equal", "results_equal", "simulation_count_equal",
    ))
    if comparison["equal"]:
        sequential_seconds = sequential["elapsed_seconds"]
        parallel_seconds = parallel["elapsed_seconds"]
        comparison["speedup"] = sequential_seconds / parallel_seconds
        comparison["time_saved_percent"] = (1.0 - parallel_seconds / sequential_seconds) * 100.0
    else:
        comparison["first_difference"] = next(
            difference
            for key in ("configuration", "results", "simulation_count")
            if (difference := _first_difference(sequential[key], parallel[key], key)) is not None
        )
    return comparison


def _compare_modes(args) -> int:
    """Startet frische Koordinatoren nacheinander und sichert jeden fertigen Modus sofort."""
    execution_order = (
        ("parallel", "sequential")
        if args.order == "parallel-first"
        else ("sequential", "parallel")
    )
    output_path = args.output.resolve()
    payload = {
        "schema_version": 1,
        "status": "running",
        "execution_order": list(execution_order),
        "requested_model": str(args.model) if args.model is not None else None,
        "reports": {},
    }
    try:
        with tempfile.TemporaryDirectory(prefix="spineml-optimization-compare-") as directory:
            for mode in execution_order:
                payload["active_mode"] = mode
                _write_json(output_path, payload)
                child_report_path = Path(directory) / f"{mode}.json"
                command = [
                    sys.executable, str(Path(__file__).resolve()),
                    "--_mode", mode, "--_report", str(child_report_path),
                ]
                if args.model is not None:
                    command.extend(("--model", str(args.model)))
                print(f"Starte frischen {mode}-Koordinator ...", flush=True)
                # Vererbte Standardausgabe zeigt Fortschritt, ohne weitere UI zu starten.
                completed = subprocess.run(command, check=False)
                child_payload = (
                    json.loads(child_report_path.read_text(encoding="utf-8"))
                    if child_report_path.is_file() else {}
                )
                if completed.returncode != 0 or child_payload.get("status") != "complete":
                    raise RuntimeError(
                        f"{mode} ist fehlgeschlagen: "
                        f"{child_payload.get('error', f'Prozesscode {completed.returncode}')}"
                    )
                payload["reports"][mode] = _validate_report(child_payload.get("report"), mode)
                payload["status"] = "partial"
                payload["active_mode"] = None
                # Der erste vollständige Bericht liegt vor dem Start des zweiten dauerhaft vor.
                _write_json(output_path, payload)

        comparison = compare_reports(
            payload["reports"]["sequential"], payload["reports"]["parallel"],
        )
        payload["comparison"] = comparison
        payload["status"] = "complete" if comparison["equal"] else "mismatch"
        _write_json(output_path, payload)
        print(f"\nBericht: {output_path}")
        if not comparison["equal"]:
            print(
                f"Keine vergleichbare Beschleunigung: {comparison['first_difference']}",
                file=sys.stderr,
            )
            return 2
        print("Konfiguration, vollständige Ergebnisse und Laufzahl sind exakt gleich.")
        print(f"Sequenziell: {comparison['sequential_seconds']:.3f} s")
        print(f"Prozesspool: {comparison['parallel_seconds']:.3f} s")
        print(
            f"Speedup: {comparison['speedup']:.3f}×; "
            f"Zeitersparnis: {comparison['time_saved_percent']:.2f} %"
        )
        return 0
    except (Exception, KeyboardInterrupt) as error:
        payload["status"] = "failed"
        payload["error"] = "Vergleich unterbrochen." if isinstance(error, KeyboardInterrupt) else str(error)
        try:
            _write_json(output_path, payload)
        except OSError as write_error:
            print(f"Bericht konnte nicht aktualisiert werden: {write_error}", file=sys.stderr)
        print(f"Fehler: {payload['error']}", file=sys.stderr, flush=True)
        return 130 if isinstance(error, KeyboardInterrupt) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Misst denselben vollständigen Optimierungsworkflow sequenziell und im "
            "Prozesspool, jeweils in einem frischen Python-Prozess."
        ),
    )
    parser.add_argument("--model", type=Path, help="Beispielmodell; Standard wie in apps/heuristic_optimization_app.py.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON-Bericht (Standard: %(default)s).")
    parser.add_argument(
        "--order", choices=("sequential-first", "parallel-first"), default="sequential-first",
        help="Ausführungsreihenfolge der beiden vollständig getrennten Messungen.",
    )
    parser.add_argument("--_mode", choices=("sequential", "parallel"), help=argparse.SUPPRESS)
    parser.add_argument("--_report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (args._mode is None) != (args._report is None):
        parser.error("Die internen Argumente --_mode und --_report müssen zusammen stehen.")
    return _run_child_mode(args) if args._mode is not None else _compare_modes(args)


if __name__ == "__main__":
    raise SystemExit(main())
