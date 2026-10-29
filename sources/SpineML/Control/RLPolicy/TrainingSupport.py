"""Gemeinsame Kalibrierung und Checkpoint-Kontexte der optionalen RL-Werkzeuge.

Factories enthalten nur serialisierbare Konfiguration, keine laufende Simulation.
Dieses Modul importiert weder PyTorch noch Stable-Baselines3 beim Laden.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
import hashlib
import math
from numbers import Integral
from pathlib import Path
import runpy
from time import perf_counter

import gymnasium as gym

from ...GlobalEvaluation.GlobalSimulationEvaluation import (
    GlobalSimulationEvaluation,
    GlobalSimulationWeights,
)
from ...SimulationExecution.ModelLoader import _resolve_model_path
from .RLObservationEncoder import (
    ACTION_TYPES,
    CANDIDATE_FEATURE_NAMES,
    CONTEXT_FEATURE_NAMES,
    ENTITY_FEATURE_NAMES,
    OBJECT_TYPES,
)
from .RLReward import RLReward


_ENVIRONMENT_DEFAULTS = {
    "max_actions": 256,
    "max_entities": 256,
    "max_decisions": 100_000,
    "max_simulation_time": 10_000.0,
    "response_timeout": 120.0,
}
_DEBUG_INFO_KEYS = frozenset(("policy_observation", "candidates", "pending_actions"))


def load_app_configuration() -> dict:
    """Liest die App-Vorgaben ohne GUI-Import oder Serverstart.

    Unter ``__mp_main__`` überspringt die App ihre GUI-Imports. Auch ihre
    Main-Guards bleiben inaktiv; ausgeführt wird nur die Konfiguration.
    """
    app_path = Path(__file__).resolve().parents[3] / "apps" / "heuristic_optimization_app.py"
    configuration = runpy.run_path(str(app_path), run_name="__mp_main__")
    evaluation = configuration["_global_evaluation"]()
    return {
        "model_file": configuration["EXAMPLE_FILE"],
        "baseline_seeds": list(configuration["SEEDS"]),
        "test_seeds": list(configuration["TEST_SEEDS"]),
        "global_weights": asdict(evaluation.weights),
    }


def _validated_seeds(seeds: Iterable[int]) -> tuple[int, ...]:
    values = tuple(seeds)
    if not values:
        raise ValueError("Mindestens ein Simulations-Seed ist erforderlich.")
    if any(isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0 for seed in values):
        raise ValueError("Simulations-Seeds müssen nichtnegative ganze Zahlen sein.")
    return tuple(int(seed) for seed in values)


def calibrate_references(
    model_file: str | Path,
    seeds: Iterable[int],
    *,
    global_evaluation: GlobalSimulationEvaluation | None = None,
    progress: Callable[[int], None] | None = None,
) -> tuple[GlobalSimulationEvaluation, dict]:
    """Kalibriert feste Referenzen mit vollständigen Standard-Heuristikläufen.

    Bei Baseline-Mittelwert null bleibt der ValueError der globalen Bewertung
    erhalten. Es gibt weder Ersatzdivisoren noch zwischengespeicherte Referenzen.
    """
    from ..HeuristicPolicy.HeuristicPolicyFactory import HeuristicPolicyFactory
    from ...SimulationExecution.ModelLoader import load_layout_and_scenario
    from ...SimulationExecution.SimulationRunner import SimulationRunner

    seeds = _validated_seeds(seeds)
    if global_evaluation is None:
        weights = load_app_configuration()["global_weights"]
    else:
        weights = asdict(global_evaluation.weights)
    evaluation = GlobalSimulationEvaluation(GlobalSimulationWeights(**weights))
    started_at = perf_counter()
    layout, scenario = load_layout_and_scenario(_resolve_model_path(model_file))
    runner = SimulationRunner(layout, scenario)
    policy_factory = HeuristicPolicyFactory()
    metrics_by_seed = []
    for seed in seeds:
        if progress is not None:
            progress(seed)
        metrics_by_seed.append(runner.run_policy(policy_factory(seed), seed))
    references = evaluation.calculate_baseline_reference_values(metrics_by_seed)
    RLReward(evaluation)  # Dieselben positiven Referenzen wie im Environment prüfen.
    return evaluation, {
        "seeds": list(seeds),
        "reference_values": references,
        "global_weights": asdict(evaluation.weights),
        "heuristic_weights": asdict(policy_factory.weights),
        "metrics_by_seed": [
            {"seed": seed, "metrics": asdict(metrics)}
            for seed, metrics in zip(seeds, metrics_by_seed)
        ],
        "elapsed_seconds": perf_counter() - started_at,
    }


def _environment_config(config: Mapping | None) -> dict:
    values = dict(_ENVIRONMENT_DEFAULTS)
    if config is not None:
        unknown = set(config) - set(values)
        if unknown:
            raise ValueError(f"Unbekannte RL-Environment-Einstellungen: {sorted(unknown)}")
        values.update(config)
    for name in ("max_actions", "max_entities", "max_decisions"):
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
            raise ValueError(f"{name} muss eine positive ganze Zahl sein.")
        values[name] = int(value)
    for name in ("max_simulation_time", "response_timeout"):
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} muss endlich und positiv sein.")
        values[name] = float(value)
    return values


def observation_schema() -> dict[str, list[str]]:
    """Speichert Feature-Namen und Reihenfolge statt nur Array-Dimensionen."""
    return {
        "context_feature_names": list(CONTEXT_FEATURE_NAMES),
        "entity_feature_names": list(ENTITY_FEATURE_NAMES),
        "candidate_feature_names": list(CANDIDATE_FEATURE_NAMES),
        "object_types": list(OBJECT_TYPES),
        "action_types": list(ACTION_TYPES),
    }


def evaluation_from_context(context: Mapping) -> GlobalSimulationEvaluation:
    """Erzeugt eine unabhängige, geprüfte Bewertung aus dem gespeicherten Kontext."""
    try:
        evaluation = GlobalSimulationEvaluation(
            GlobalSimulationWeights(**{
                name: float(value) for name, value in context["global_weights"].items()
            }),
            baseline_reference_values={
                name: float(value) for name, value in context["baseline_reference_values"].items()
            },
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Der Checkpoint-Kontext enthält keine gültige globale Bewertung.") from error
    RLReward(evaluation)
    return evaluation


def build_artifact_context(
    model_file: str | Path,
    evaluation: GlobalSimulationEvaluation,
    env_config: Mapping | None = None,
) -> dict:
    """Erzeugt den JSON-fähigen Modell-, Bewertungs- und Beobachtungskontext."""
    model_path = _resolve_model_path(model_file)
    RLReward(evaluation)
    return {
        "schema_version": 1,
        "model_file": str(model_path),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "global_weights": {name: float(value) for name, value in asdict(evaluation.weights).items()},
        "baseline_reference_values": {
            name: float(value) for name, value in evaluation.baseline_reference_values.items()
        },
        "environment": _environment_config(env_config),
        "observation_schema": observation_schema(),
    }


def validate_artifact_context(
    context: Mapping,
    model_file: str | Path | None = None,
    env_config: Mapping | None = None,
) -> Path:
    """Lehnt andere Modelle, geänderte Features und inkompatible Einstellungen ab.

    Eine explizite Modelldatei darf an einem anderen Ort liegen, muss aber
    denselben SHA256-Hash haben. Gespeicherte Gewichte und Referenzen bleiben
    unverändert; aktuelle App-Vorgaben ersetzen sie nicht.
    """
    if isinstance(context.get("schema_version"), bool) or context.get("schema_version") != 1:
        raise ValueError("Nicht unterstützte schema_version im RL-Checkpoint-Kontext.")
    if context.get("observation_schema") != observation_schema():
        raise ValueError("Das Beobachtungs-Featureschema des RL-Checkpoints weicht vom Quellcode ab.")
    try:
        saved_config = context["environment"]
        if set(saved_config) != set(_ENVIRONMENT_DEFAULTS):
            raise ValueError("Der Checkpoint-Kontext muss alle Environment-Einstellungen enthalten.")
        saved_config = _environment_config(saved_config)
        saved_model = context["model_file"]
        if not isinstance(saved_model, str) or not Path(saved_model).is_absolute():
            raise ValueError("Der Checkpoint-Kontext muss den aufgelösten absoluten Modellpfad enthalten.")
        selected_model = model_file if model_file is not None else saved_model
        model_path = _resolve_model_path(selected_model)
    except (KeyError, TypeError) as error:
        raise ValueError("Die Modell-/Environment-Konfiguration des Checkpoints ist unvollständig.") from error
    if env_config is not None and saved_config != _environment_config(env_config):
        raise ValueError("Die RL-Checkpoint-Einstellungen weichen vom angeforderten Environment ab.")
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != context.get("model_sha256"):
        raise ValueError("Der Modell-SHA256 des RL-Checkpoints weicht von der aktuellen Datei ab.")
    evaluation_from_context(context)
    return model_path


class EpisodeSeedWrapper(gym.Wrapper):
    """Wechselt zyklisch durch feste Trainings-Seeds mit reproduzierbarem Offset.

    Übergebene Reset-Seeds, auch SB3s automatischer erster Seed, ersetzen die
    Trainings-Seeds nicht. Jeder Reset verwendet den nächsten konfigurierten
    Seed. Evaluationen setzen explizite Seeds direkt am unverpackten SpineRLEnv.

    Entscheidungs-/Zeitlimits sind im Trainingsziel terminale Fehlschläge mit -1.
    Deshalb werden sie für SB3 als terminated markiert, ohne TimeLimit-Value-
    Bootstrapping. Grund und Kennzahlen bleiben in info; das zugrunde liegende
    Environment behält seine Gymnasium-Trunkierungssemantik.
    """

    def __init__(self, env: gym.Env, seeds: Iterable[int], rank: int = 0, *, compact_info: bool = True):
        super().__init__(env)
        self.seeds = _validated_seeds(seeds)
        if isinstance(rank, bool) or not isinstance(rank, Integral) or rank < 0:
            raise ValueError("Der Worker-Rang muss eine nichtnegative ganze Zahl sein.")
        self.rank = int(rank)
        self.episode_index = 0
        self.compact_info = compact_info

    def _info(self, info):
        return {key: value for key, value in info.items() if key not in _DEBUG_INFO_KEYS} if self.compact_info else info

    def reset(self, *, seed=None, options=None):
        episode_seed = self.seeds[(self.rank + self.episode_index) % len(self.seeds)]
        observation, info = self.env.reset(seed=episode_seed, options=options)
        self.episode_index += 1
        return observation, self._info(info)

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)
        if truncated:
            info = {**info, "training_limit_terminated": True}
            terminated, truncated = True, False
        return observation, reward, terminated, truncated, self._info(info)

    def action_masks(self):
        return self.env.get_wrapper_attr("action_masks")()


@dataclass(frozen=True)
class EnvironmentFactory:
    """Spawn-fähiger Aufruf: genau ein aktives Salabim-Environment pro Prozess."""

    model_file: str | Path
    evaluation_context: dict
    env_config: dict
    seeds: tuple[int, ...] = (1,)
    rank: int = 0
    monitor: bool = True
    compact_info: bool = True

    def __call__(self):
        from .SpineRLEnv import SpineRLEnv

        model_path = validate_artifact_context(self.evaluation_context, self.model_file, self.env_config)
        environment = EpisodeSeedWrapper(
            SpineRLEnv(model_path, evaluation_from_context(self.evaluation_context), **_environment_config(self.env_config)),
            self.seeds,
            self.rank,
            compact_info=self.compact_info,
        )
        if self.monitor:
            # Eine normale .[rl]-Installation benötigt keine Trainingsabhängigkeiten.
            from stable_baselines3.common.monitor import Monitor

            environment = Monitor(environment)
        return environment
