from __future__ import annotations

from dataclasses import dataclass
import random

from .HeuristicActionSelector import HeuristicActionSelector
from .HeuristicPolicy import HeuristicPolicy
from .HeuristicWeights import HeuristicWeights
from .LocalHeuristicActionEvaluator import LocalHeuristicActionEvaluator


@dataclass(frozen=True)
class HeuristicPolicyFactory:
    """Erstellt je Seed eine frische heuristische Policy mit diesem Gewichtssatz."""

    weights: HeuristicWeights = HeuristicWeights()

    def __call__(self, seed: int) -> HeuristicPolicy:
        return HeuristicPolicy(
            action_evaluator=LocalHeuristicActionEvaluator(self.weights),
            action_selector=HeuristicActionSelector(rng=random.Random(seed)),
        )
