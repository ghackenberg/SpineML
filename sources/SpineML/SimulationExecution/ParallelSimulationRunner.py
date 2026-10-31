"""Verteilt unabhängige Policy-Simulationsläufe auf einen Prozesspool."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import multiprocessing
import os
from pathlib import Path
import time
from typing import Callable, Iterable

from ..SimulationInterface.InterfaceTypes import Policy
from ..GlobalEvaluation.GlobalSimulationEvaluation import GlobalSimulationMetrics
from .ModelLoader import _resolve_model_path, load_layout_and_scenario
from .SimulationRunner import SimulationRunner


@dataclass(frozen=True)
class SimulationRunRequest:
    """Eine Policy-Erstellung und ein Seed für einen Simulationslauf."""

    policy_factory: Callable[[int], Policy]
    seed: int


@dataclass(frozen=True)
class SimulationRunResult:
    """Produktionskennzahlen, Laufzeit und Prozess-ID eines fertigen Laufs."""

    metrics: GlobalSimulationMetrics
    elapsed_seconds: float
    worker_pid: int


# Jeder Prozess verwendet seinen eigenen Runner.
_worker_runner: SimulationRunner | None = None


# Lädt einmal pro Worker-Prozess Layout und Szenario
# und erstellt dessen eigenen Runner.
def _initialize_simulation_worker(model_file: str) -> None:
    global _worker_runner

    layout, scenario = load_layout_and_scenario(model_file)
    _worker_runner = SimulationRunner(layout, scenario)


# Erstellt die Policy und führt einen Simulationslauf mit dem Runner dieses Workers aus.
# Gibt Produktionskennzahlen, Laufzeit und die PID des Worker-Prozesses zurück.
def _execute_simulation_request(request: SimulationRunRequest) -> SimulationRunResult:
    if _worker_runner is None:
        raise RuntimeError("Der Simulationsworker wurde noch nicht initialisiert.")

    started_at = time.perf_counter()
    policy = request.policy_factory(request.seed)
    metrics = _worker_runner.run_policy(policy, request.seed)

    return SimulationRunResult(
        metrics=metrics,
        elapsed_seconds=time.perf_counter() - started_at,
        worker_pid=os.getpid(),
    )


class ParallelSimulationRunner:
    """Verteilt Simulationsläufe auf mehrere Prozesse und sammelt ihre Ergebnisse."""

    def __init__(
        self,
        model_file: str | Path,
        max_workers: int | None = None,
    ) -> None:
        self.model_path = _resolve_model_path(model_file)
        if max_workers is None:
            max_workers = os.cpu_count()
            if not max_workers:
                max_workers = 1
            if os.name == "nt":
                max_workers = min(max_workers, 61)
        self.max_workers = max_workers
        self._executor: ProcessPoolExecutor | None = None
        self._closed = False

    def run_many(
        self,
        requests: Iterable[SimulationRunRequest],
        on_completed: Callable[[int, SimulationRunResult], None] | None = None,
    ) -> tuple[SimulationRunResult, ...]:
        """Meldet fertige Läufe sofort und gibt Ergebnisse in Eingabereihenfolge zurück."""
        if self._closed:
            raise RuntimeError("Der ParallelSimulationRunner wurde bereits geschlossen.")

        # Sammelt die Simulationsaufträge; jeder enthält eine Policy-Factory und einen Seed.
        batch = tuple(requests)
        if not batch:
            return ()

        # Den Pool beim ersten Auftrag starten und für weitere Aufrufe behalten.
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_initialize_simulation_worker,
                initargs=(str(self.model_path),),
            )

        futures = {}
        results = {}
        try:
            # Übergibt jeden Simulationsauftrag an den Pool.
            for index, request in enumerate(batch):
                # Beauftragt einen Worker mit diesem Lauf;
                # der Future macht das Ergebnis nach Abschluss abrufbar.
                future = self._executor.submit(_execute_simulation_request, request)
                futures[future] = index

            # Fertige Läufe sofort melden, auch wenn frühere Aufträge noch laufen.
            for future in as_completed(futures):
                index = futures[future]
                result = future.result()
                results[index] = result
                if on_completed is not None:
                    on_completed(index, result)
        except BaseException:
            # Bereits laufende Aufträge lassen sich nicht abbrechen; close() wartet auf sie.
            for future in futures:
                future.cancel()
            raise

        # Die Rückgabe folgt der Auftragsreihenfolge, nicht der Fertigstellung.
        ordered_results = []
        for index in range(len(batch)):
            ordered_results.append(results[index])
        return tuple(ordered_results)

    def close(self) -> None:
        """Beendet den Pool und wartet auf bereits laufende Simulationen."""
        self._closed = True
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None

    def __enter__(self) -> ParallelSimulationRunner:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
