from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GlobalSimulationMetrics:
    """Global metrics of a fully completed simulation run."""

    makespan: float
    total_tardiness: float
    total_transport_time: float = 0.0
    tool_change_time: float = 0.0
    blocking_time: float = 0.0
    rework_job_count: float = 0.0
    scrap_job_count: float = 0.0
    unfinished_jobs: int = 0
    total_jobs: int = 0
    completed_jobs: int = 0
    intact_jobs: int = 0
    defect_jobs: int = 0
    downgraded_job_count: float = 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def completion_rate(self) -> float:
        return self.completed_jobs / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def intact_rate(self) -> float:
        return self.intact_jobs / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def unfinished_rate(self) -> float:
        return self.unfinished_jobs / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def rework_rate(self) -> float:
        return self.rework_job_count / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def scrap_rate(self) -> float:
        return self.scrap_job_count / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def defect_rate(self) -> float:
        return self.defect_jobs / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def downgrade_rate(self) -> float:
        return (
            self.downgraded_job_count / self.total_jobs
            if self.total_jobs
            else 0.0
        )


@dataclass(frozen=True)
class GlobalSimulationWeights:
    """Weights of the global objective function to minimize."""

    makespan: float
    total_tardiness: float
    total_transport_time: float
    tool_change_time: float
    blocking_time: float
    rework_job_penalty: float
    scrap_job_penalty: float
    unfinished_jobs: float
    defect_job_penalty: float = 0.0
    non_intact_penalty: float = 0.0
    downgrade_job_penalty: float = 0.0


class GlobalSimulationEvaluation:
    """Calculate global cost from the metrics of a simulation run."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        weights: GlobalSimulationWeights,
        baseline_reference_values: dict[str, float] | None = None,
    ):
        self.weights = weights
        self.baseline_reference_values = (
            dict(baseline_reference_values)
            if baseline_reference_values is not None
            else None
        )

    # Berechnet aus den Baseline-Kennzahlen Referenzwerte für die spätere
    # relative Skalierung.
    def calculate_baseline_reference_values(
        self,
        metrics_by_seed: Iterable[GlobalSimulationMetrics],
    ) -> dict[str, float]:
        # Übernimmt die globalen Kennzahlen aller Baseline-Seeds als Tupel.
        baseline_metrics = tuple(metrics_by_seed)
        if not baseline_metrics:
            raise ValueError(
                "At least one run is required to calculate baseline reference "
                "values."
            )

        # Verwendet den eigenen Baseline-Mittelwert als Referenz; null ist
        # als Divisor nicht zulässig.
        def mean_value(attribute_name: str) -> float:
            total_value = 0.0
            for metrics in baseline_metrics:
                metric_value = getattr(metrics, attribute_name)
                total_value += float(metric_value)

            baseline_mean = total_value / len(baseline_metrics)
            if baseline_mean == 0.0:
                raise ValueError(
                    f"The baseline mean {attribute_name} must not be zero."
                )
            return baseline_mean

        # Speichert für jede globale Zeitkennzahl ihren Referenzwert aus der Baseline.
        self.baseline_reference_values = {
            "makespan": mean_value("makespan"),
            "total_tardiness": mean_value("total_tardiness"),
            "total_transport_time": mean_value("total_transport_time"),
            "tool_change_time": mean_value("tool_change_time"),
            "blocking_time": mean_value("blocking_time"),
        }
        # Gibt eine Kopie der berechneten Baseline-Referenzwerte zurück.
        return dict(self.baseline_reference_values)

    # Normalisiert die globalen Kennzahlen für die anschließende Kostenberechnung.
    def metrics_relative_to_baseline(
        self,
        metrics: GlobalSimulationMetrics,
    ) -> dict[str, float]:
        """Scale time values relative to the baseline and keep quality rates direct."""
        if self.baseline_reference_values is None:
            raise RuntimeError(
                "Baseline reference values are missing. Call "
                "calculate_baseline_reference_values(...) first or pass "
                "baseline_reference_values explicitly."
            )

        time_values = {
            "makespan": metrics.makespan,
            "total_tardiness": metrics.total_tardiness,
            "total_transport_time": metrics.total_transport_time,
            "tool_change_time": metrics.tool_change_time,
            "blocking_time": metrics.blocking_time,
        }

        relative_metrics = {}
        # Skaliert jede Zeitkennzahl relativ zu ihrem Baseline-Referenzwert.
        for name, value in time_values.items():
            reference_value = self.baseline_reference_values[name]
            relative_value = value / reference_value

            # Verhindert negative relative Werte.
            if relative_value < 0.0:
                relative_value = 0.0

            # Speichert den relativen Wert unter demselben Kennzahlnamen.
            relative_metrics[name] = relative_value
        relative_metrics.update(
            {
                "rework_rate": max(0.0, metrics.rework_rate),
                "scrap_rate": max(0.0, metrics.scrap_rate),
                "defect_rate": max(0.0, metrics.defect_rate),
                "non_intact_rate": max(0.0, 1.0 - metrics.intact_rate),
                "unfinished_rate": max(0.0, metrics.unfinished_rate),
                "downgrade_rate": max(0.0, metrics.downgrade_rate),
            }
        )
        return relative_metrics

    # Berechnet eine vergleichbare weighted Summe der relativ zur Baseline
    # skalierten Kennzahlen für den Vergleich verschiedener weight sets.
    def calculate_weighted_sum_of_metrics_relative_to_baseline(
        self,
        metrics: GlobalSimulationMetrics,
    ) -> float:
        relative_metrics = self.metrics_relative_to_baseline(metrics)
        return (
            self.weights.makespan * relative_metrics["makespan"]
            + self.weights.total_tardiness * relative_metrics["total_tardiness"]
            + self.weights.total_transport_time
            * relative_metrics["total_transport_time"]
            + self.weights.tool_change_time * relative_metrics["tool_change_time"]
            + self.weights.blocking_time * relative_metrics["blocking_time"]
            + self.weights.rework_job_penalty
            * relative_metrics["rework_rate"]
            + self.weights.scrap_job_penalty
            * relative_metrics["scrap_rate"]
            + self.weights.unfinished_jobs * relative_metrics["unfinished_rate"]
            + self.weights.defect_job_penalty * relative_metrics["defect_rate"]
            + self.weights.non_intact_penalty * relative_metrics["non_intact_rate"]
            + self.weights.downgrade_job_penalty
            * relative_metrics["downgrade_rate"]
        )
