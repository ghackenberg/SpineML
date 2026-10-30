"""Verwendet ein gespeichertes Kandidaten-NN als Simulations-Policy.

Nur eigene/vertraute Checkpoints laden: das SB3-ZIP enthält Python-Objekte.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from numbers import Integral
from pathlib import Path
import random

import numpy as np

from ...SimulationInterface.InterfaceTypes import Policy, PolicyDecision, PolicyObservation
from .RLCandidatePolicy import DecisionRequest, RLCandidatePolicy
from .RLObservationEncoder import RLObservationEncoder


def _validate_options(deterministic: bool, seed: int) -> int:
    if not isinstance(deterministic, bool):
        raise TypeError("deterministic muss ein boolescher Wert sein.")
    if isinstance(seed, bool) or not isinstance(seed, Integral) or not 0 <= seed < 2**64:
        raise ValueError("seed muss eine ganze Zahl zwischen 0 und 2**64-1 sein.")
    return int(seed)


class TrainedCandidatePolicy(Policy):
    """Lädt manifest.json und model.zip und lässt das NN Kandidaten auswählen."""

    def __init__(
        self,
        run_directory: str | Path,
        *,
        model_file: str | Path | None = None,
        deterministic: bool = True,
        seed: int = 0,
        device: str = "cpu",
    ):
        seed = _validate_options(deterministic, seed)
        try:
            import torch as th
            from gymnasium import spaces
            from sb3_contrib import MaskablePPO
            from stable_baselines3.common.utils import get_device
            from .CandidateActorCriticPolicy import CandidateActorCriticPolicy
            from .TrainingSupport import validate_artifact_context
        except ImportError as error:
            raise ImportError(
                'Die trainierte Policy benötigt: python -m pip install ".[rl-training]"'
            ) from error

        self.run_directory = Path(run_directory).resolve()
        manifest_path = self.run_directory / "manifest.json"
        checkpoint_path = self.run_directory / "model.zip"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Ungültiges JSON-Manifest: {manifest_path}") from error
        if not isinstance(manifest, dict) or manifest.get("algorithm") != "MaskablePPO":
            raise ValueError("Das Manifest muss einen MaskablePPO-Trainingslauf beschreiben.")
        context = manifest.get("artifact_context")
        if not isinstance(context, Mapping):
            raise ValueError("Im Manifest fehlt ein gültiger artifact_context.")
        # Der Runner muss dieselbe geprüfte Fabrikkonfiguration verwenden.
        self.model_path = validate_artifact_context(context, model_file=model_file)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Der NN-Checkpoint fehlt: {checkpoint_path}")
        self.artifact_context = context
        self._decision_count = 0
        self.deterministic = deterministic
        self.encoder = RLObservationEncoder(
            max_actions=context["environment"]["max_actions"],
            max_entities=context["environment"]["max_entities"],
        )

        selected_device = get_device(device)
        if selected_device.type not in ("cpu", "cuda"):
            raise ValueError("Die isolierte NN-Vorhersage unterstützt device='cpu' oder CUDA.")
        self._rng_devices = []
        if selected_device.type == "cuda":
            device_index = selected_device.index
            if device_index is None:
                device_index = th.cuda.current_device()
            self._rng_devices.append(device_index)
        # Laden und Vorhersagen dürfen den Zufall der Simulation nicht verändern.
        # seed=None verhindert SB3s globales Python-/NumPy-Seeding beim Laden.
        python_rng = random.getstate()
        numpy_rng = np.random.get_state()
        try:
            with th.random.fork_rng(devices=self._rng_devices):
                self.model = MaskablePPO.load(checkpoint_path, device=selected_device, seed=None)
        finally:
            random.setstate(python_rng)
            np.random.set_state(numpy_rng)
        if not isinstance(self.model.policy, CandidateActorCriticPolicy):
            raise ValueError("Der Checkpoint enthält keine CandidateActorCriticPolicy.")

        expected_observation_space = spaces.Dict({
            "context": spaces.Box(-1.0, 1.0, (self.encoder.context_size,), np.float32),
            "entities": spaces.Box(
                -1.0, 1.0,
                (self.encoder.max_entities, self.encoder.entity_feature_size), np.float32,
            ),
            "entity_mask": spaces.MultiBinary(self.encoder.max_entities),
            "candidates": spaces.Box(
                -1.0, 1.0,
                (self.encoder.max_actions, self.encoder.candidate_feature_size), np.float32,
            ),
            "action_mask": spaces.MultiBinary(self.encoder.max_actions),
        })
        if (self.model.observation_space != expected_observation_space
                or self.model.action_space != spaces.Discrete(self.encoder.max_actions)):
            raise ValueError("Beobachtungs-/Aktionsraum des Checkpoints passt nicht zum Manifest.")
        self.model.policy.set_training_mode(False)
        self._cpu_rng_state = th.Generator(device="cpu").manual_seed(seed).get_state()
        self._cuda_rng_state = (
            th.Generator(device=selected_device).manual_seed(seed).get_state()
            if self._rng_devices else None
        )
        self._candidate_policy = RLCandidatePolicy(self._select_candidate)

    def _select_candidate(self, request: DecisionRequest) -> int:
        import torch as th

        if self._decision_count >= self.artifact_context["environment"]["max_decisions"]:
            raise RuntimeError("Die trainierte Policy hat ihr gespeichertes Entscheidungslimit erreicht.")
        observation = self.encoder.encode(request)
        masks = observation["action_mask"].astype(bool, copy=True)
        # predict erhält ausschließlich frisch erzeugte numerische Kopien.
        with th.random.fork_rng(devices=self._rng_devices):
            th.set_rng_state(self._cpu_rng_state)
            if self._rng_devices:
                th.cuda.set_rng_state(self._cuda_rng_state, self._rng_devices[0])
            action, _ = self.model.predict(
                {name: value.copy() for name, value in observation.items()},
                action_masks=masks,
                deterministic=self.deterministic,
            )
            self._cpu_rng_state = th.get_rng_state()
            if self._rng_devices:
                self._cuda_rng_state = th.cuda.get_rng_state(self._rng_devices[0])
        selected = np.asarray(action)
        if selected.size != 1:
            raise ValueError("Das NN muss genau einen Kandidatenindex liefern.")
        index = selected.item()
        if (isinstance(index, bool) or not isinstance(index, Integral)
                or not 0 <= index < len(masks) or not masks[index]):
            raise ValueError("Das NN hat einen ungültigen Kandidatenindex geliefert.")
        self._decision_count += 1
        return int(index)

    def make_decision(self, observation: PolicyObservation) -> PolicyDecision:
        current_time = float(observation.simulation_configuration_snapshot["time"])
        if current_time >= self.artifact_context["environment"]["max_simulation_time"]:
            raise RuntimeError("Die trainierte Policy hat ihr gespeichertes Simulationszeitlimit erreicht.")
        return self._candidate_policy.make_decision(observation)


@dataclass(frozen=True)
class TrainedPolicyFactory:
    """Picklebare Factory für frische NN-Policies je Simulationslauf und Seed."""

    run_directory: str | Path
    deterministic: bool = True
    device: str = "cpu"

    def __post_init__(self) -> None:
        _validate_options(self.deterministic, 0)
        object.__setattr__(self, "run_directory", str(Path(self.run_directory).resolve()))

    def __call__(self, seed: int) -> TrainedCandidatePolicy:
        return TrainedCandidatePolicy(
            self.run_directory,
            deterministic=self.deterministic,
            seed=seed,
            device=self.device,
        )
