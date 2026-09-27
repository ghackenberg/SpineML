from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GlobalSimulationMetrics:
    """Globale Kennzahlen eines vollständig ausgeführten Simulationslaufs."""

    makespan: float
    total_tardiness: float
    total_transport_time: float = 0.0
    tool_change_time: float = 0.0
    blocking_time: float = 0.0
    nacharbeit_job_count: float = 0.0
    ausschuss_job_count: float = 0.0
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
        return self.nacharbeit_job_count / self.total_jobs if self.total_jobs else 0.0

    @property
    # Führt die Funktion mit den übergebenen Werten aus.
    def scrap_rate(self) -> float:
        return self.ausschuss_job_count / self.total_jobs if self.total_jobs else 0.0

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
    """Gewichte der zu minimierenden globalen Zielfunktion."""

    makespan: float
    total_tardiness: float
    total_transport_time: float
    tool_change_time: float
    blocking_time: float
    nacharbeit_job_penalty: float
    ausschuss_job_penalty: float
    unfinished_jobs: float
    defect_job_penalty: float = 0.0
    non_intact_penalty: float = 0.0
    downgrade_job_penalty: float = 0.0


class GlobalSimulationEvaluation:
    """Berechnet globale Kosten aus den Kennzahlen eines Simulationslaufs."""

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
                "Für die Berechnung der Baseline-Referenzwerte wird mindestens "
                "ein Lauf benötigt."
            )

        # Berechnet den Mittelwert eines ausgewählten globalen Kennzahlenfelds
        # über alle Baseline-Simulationsläufe.
        def mean_value(attribute_name: str) -> float:
            total_value = 0.0
            for metrics in baseline_metrics:
                metric_value = getattr(metrics, attribute_name)
                total_value += float(metric_value)

            return total_value / len(baseline_metrics)

        mean_makespan = mean_value("makespan")
        # Verwendet den mittleren Baseline-Makespan, mindestens jedoch 1.0,
        # damit die spätere relative Skalierung sicher durch einen positiven Wert teilt.
        baseline_makespan_reference_value = max(mean_makespan, 1.0)

        # Liefert den Baseline-Mittelwert eines Zeitwerts; bei null wird der
        # Fallback verwendet, damit später nicht durch null geteilt wird.
        def time_scale(attribute_name: str) -> float:
            baseline_mean = mean_value(attribute_name)
            if baseline_mean > 0.0:
                return baseline_mean
            return baseline_makespan_reference_value

        # Speichert für jede globale Zeitkennzahl ihren Referenzwert aus der Baseline.
        self.baseline_reference_values = {
            # Mittlerer Baseline-Makespan, mindestens 1.0.
            "makespan": baseline_makespan_reference_value,
            "total_tardiness": time_scale("total_tardiness"),
            "total_transport_time": time_scale("total_transport_time"),
            "tool_change_time": time_scale("tool_change_time"),
            "blocking_time": time_scale("blocking_time"),
        }
        # Gibt eine Kopie der berechneten Baseline-Referenzwerte zurück.
        return dict(self.baseline_reference_values)

    # Normalisiert die globalen Kennzahlen für die anschließende Kostenberechnung.
    def metrics_relative_to_baseline(
        self,
        metrics: GlobalSimulationMetrics,
    ) -> dict[str, float]:
        """Skaliert Zeitwerte relativ zur Baseline und übernimmt Qualitätsraten direkt."""
        if self.baseline_reference_values is None:
            raise RuntimeError(
                "Baseline-Referenzwerte fehlen. Zuerst "
                "calculate_baseline_reference_values(...) aufrufen oder "
                "baseline_reference_values ausdrücklich übergeben."
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

    # Berechnet eine vergleichbare gewichtete Summe der relativ zur Baseline
    # skalierten Kennzahlen für den Vergleich verschiedener Gewichtssätze.
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
            + self.weights.nacharbeit_job_penalty
            * relative_metrics["rework_rate"]
            + self.weights.ausschuss_job_penalty
            * relative_metrics["scrap_rate"]
            + self.weights.unfinished_jobs * relative_metrics["unfinished_rate"]
            + self.weights.defect_job_penalty * relative_metrics["defect_rate"]
            + self.weights.non_intact_penalty * relative_metrics["non_intact_rate"]
            + self.weights.downgrade_job_penalty
            * relative_metrics["downgrade_rate"]
        )
