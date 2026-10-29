from __future__ import annotations

from dataclasses import dataclass, field
import random

from .HeuristicActionSelector import HeuristicActionSelector
from .HeuristicPolicy import HeuristicPolicy
from .HeuristicWeights import HeuristicWeights
from .LocalHeuristicActionEvaluator import LocalHeuristicActionEvaluator


@dataclass(frozen=True)
class HeuristicPolicyFactory:
    """Erstellt je Seed eine frische heuristische Policy mit diesem Gewichtssatz."""

    weights: HeuristicWeights = field(default_factory=HeuristicWeights)

    def __post_init__(self) -> None:
        if not isinstance(self.weights, HeuristicWeights):
            raise TypeError("weights muss ein HeuristicWeights-Satz sein.")

    def __call__(self, seed: int) -> HeuristicPolicy:
        return HeuristicPolicy(
            action_evaluator=LocalHeuristicActionEvaluator(self.weights),
            action_selector=HeuristicActionSelector(rng=random.Random(seed)),
        )
