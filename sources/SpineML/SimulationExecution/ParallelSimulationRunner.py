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

    def __post_init__(self) -> None:
        if not callable(self.policy_factory):
            raise TypeError("policy_factory muss aus einem Seed eine neue Policy erstellen.")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("seed muss eine ganze Zahl sein.")


@dataclass(frozen=True)
class SimulationRunResult:
    """Produktionskennzahlen, Laufzeit und Prozess-ID eines fertigen Laufs."""

    metrics: GlobalSimulationMetrics
    elapsed_seconds: float
    worker_pid: int


# Jeder Prozess verwendet seinen eigenen Runner.
_worker_runner: SimulationRunner | None = None


def _initialize_simulation_worker(model_file: str) -> None:
    """Lädt die Fabrikkonfiguration einmal pro Prozess."""
    global _worker_runner

    layout, scenario = load_layout_and_scenario(model_file)
    _worker_runner = SimulationRunner(layout, scenario)


def _execute_simulation_request(request: SimulationRunRequest) -> SimulationRunResult:
    if _worker_runner is None:
        raise RuntimeError("Der Simulationsworker wurde noch nicht initialisiert.")

    started_at = time.perf_counter()
    # Die Factory muss zwischen Prozessen übertragbar sein und eine neue Policy erstellen.
    policy = request.policy_factory(request.seed)
    if not callable(getattr(policy, "make_decision", None)):
        raise TypeError("policy_factory muss eine Policy mit make_decision() liefern.")
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
            max_workers = os.cpu_count() or 1
            if os.name == "nt":
                max_workers = min(max_workers, 61)
        if not isinstance(max_workers, int) or isinstance(max_workers, bool):
            raise TypeError("max_workers muss eine ganze Zahl oder None sein.")
        if max_workers < 1:
            raise ValueError("max_workers muss mindestens 1 sein.")
        if os.name == "nt" and max_workers > 61:
            raise ValueError("Unter Windows sind höchstens 61 Worker erlaubt.")

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
        batch = tuple(requests)
        if any(not isinstance(request, SimulationRunRequest) for request in batch):
            raise TypeError("requests darf nur SimulationRunRequest-Objekte enthalten.")
        if on_completed is not None and not callable(on_completed):
            raise TypeError("on_completed muss aufrufbar oder None sein.")
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
        results: dict[int, SimulationRunResult] = {}
        try:
            for index, request in enumerate(batch):
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
        return tuple(results[index] for index in range(len(batch)))

    def run_policy_factory(
        self, policy_factory: Callable[[int], Policy], seed: int
    ) -> GlobalSimulationMetrics:
        """Führt eine Policy aus; ihre Factory wird im Poolprozess aufgerufen."""
        request = SimulationRunRequest(policy_factory=policy_factory, seed=seed)
        return self.run_many((request,))[0].metrics

    def close(self) -> None:
        """Schließt den Pool einmalig und wartet auf bereits laufende Aufträge."""
        if self._closed:
            return
        self._closed = True
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> ParallelSimulationRunner:
        if self._closed:
            raise RuntimeError("Der ParallelSimulationRunner wurde bereits geschlossen.")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
