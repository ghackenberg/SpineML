from __future__ import annotations

from dataclasses import asdict
import math

from ...GlobalEvaluation.GlobalSimulationEvaluation import (
    GlobalSimulationEvaluation,
    GlobalSimulationMetrics,
    GlobalSimulationWeights,
)


class RLReward:
    """Bewertet erst das Episodenende mit den bestehenden globalen Produktionszielen."""

    reward_range = (-1.0, 1.0)
    _REFERENCE_NAMES = (
        "makespan",
        "total_tardiness",
        "total_transport_time",
        "tool_change_time",
    )

    def __init__(self, global_evaluation: GlobalSimulationEvaluation) -> None:
        # Eigene Kopien verhindern, dass spätere Baseline- oder Gewichtsänderungen
        # des aufrufenden Optimierers die Belohnung einer Episode verändern.
        weight_values = {}
        for name, value in asdict(global_evaluation.weights).items():
            try:
                numeric_value = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Das globale Gewicht {name!r} muss endlich und nichtnegativ sein."
                ) from error
            if not math.isfinite(numeric_value) or numeric_value < 0.0:
                raise ValueError(
                    f"Das globale Gewicht {name!r} muss endlich und nichtnegativ sein."
                )
            weight_values[name] = numeric_value

        references = global_evaluation.baseline_reference_values
        if references is None:
            raise ValueError(
                "RLReward benötigt feste positive Baseline-Referenzwerte. "
                "Vorher calculate_baseline_reference_values(...) auf der "
                "GlobalSimulationEvaluation aufrufen oder ihre vier "
                "baseline_reference_values ausdrücklich übergeben."
            )

        reference_values = {}
        for name in self._REFERENCE_NAMES:
            if name not in references:
                raise ValueError(
                    f"Der Baseline-Referenzwert {name!r} fehlt. "
                    "RLReward benötigt alle vier Zeitreferenzen vor Episodenbeginn."
                )
            try:
                numeric_value = float(references[name])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Der Baseline-Referenzwert {name!r} muss endlich und größer als 0 sein."
                ) from error
            if not math.isfinite(numeric_value) or numeric_value <= 0.0:
                raise ValueError(
                    f"Der Baseline-Referenzwert {name!r} muss endlich und größer als 0 sein."
                )
            reference_values[name] = numeric_value

        self._evaluation = GlobalSimulationEvaluation(
            GlobalSimulationWeights(**weight_values),
            baseline_reference_values=reference_values,
        )

    def evaluate(
        self,
        metrics: GlobalSimulationMetrics,
        *,
        terminated: bool,
        truncated: bool,
    ) -> tuple[float, dict[str, float | str]]:
        """Liefert eine positive Abschlussbelohnung oder -1 bei externem Abbruch."""
        if not terminated and not truncated:
            raise ValueError(
                "RLReward.evaluate() ist nur für das Episodenende vorgesehen; "
                "Zwischenschritte erhalten im Environment die Belohnung 0."
            )
        if terminated and metrics.unfinished_jobs > 0:
            raise ValueError(
                "Eine erfolgreich beendete Episode darf keine unfertigen Jobs enthalten."
            )

        global_cost = float(
            self._evaluation.calculate_weighted_sum_of_metrics_relative_to_baseline(
                metrics
            )
        )
        if not math.isfinite(global_cost) or global_cost < 0.0:
            raise ValueError("Die globalen RL-Kosten müssen endlich und nichtnegativ sein.")

        if truncated:
            # Jeder endliche vollständige Lauf bleibt strikt besser als ein Abbruch.
            return -1.0, {
                "global_cost": global_cost,
                "reward_reason": "truncated",
            }

        # Die monotone Umrechnung erhält die Rangfolge der unveränderten globalen Kosten.
        return 1.0 / (1.0 + global_cost), {
            "global_cost": global_cost,
            "reward_reason": "completed",
        }
