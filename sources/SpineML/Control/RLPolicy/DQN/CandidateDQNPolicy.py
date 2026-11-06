"""Verbindet den gemeinsamen Kandidaten-Netzaufbau mit Stable-Baselines3-DQN."""

from __future__ import annotations

from typing import Any

try:
    import torch as th
    from gymnasium import spaces
    from stable_baselines3.common.type_aliases import Schedule
    from stable_baselines3.dqn.policies import DQNPolicy
    from torch import nn
except ImportError as error:
    raise ImportError(
        'Die Kandidaten-DQN-Policy benötigt die Trainingspakete: python -m pip install ".[rl-training]"'
    ) from error

# Der Netzaufbau wird auch von Monte Carlo verwendet.
from ..Shared.CandidateQNetwork import (
    CandidateFeaturesExtractor,
    CandidateQNetwork,
    _positive_size,
    candidate_action_mask,
)


class CandidateDQNPolicy(DQNPolicy):
    """DQN-Policy mit gemeinsamem Kandidaten-Scorer und maskierter Auswahl."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        lr_schedule: Schedule,
        *,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
        activation_fn: type[nn.Module] = nn.Tanh,
        normalize_images: bool = False,
        optimizer_class: type[th.optim.Optimizer] = th.optim.Adam,
        optimizer_kwargs: dict[str, Any] | None = None,
    ):
        self.embedding_dim = _positive_size("embedding_dim", embedding_dim)
        self.hidden_dim = _positive_size("hidden_dim", hidden_dim)
        if not isinstance(action_space, spaces.Discrete) or action_space.start != 0:
            raise ValueError("Die Kandidaten-Policy benötigt Discrete-Aktionen ab Index 0.")
        if not isinstance(observation_space, spaces.Dict):
            raise ValueError("Die Kandidaten-Policy benötigt einen Dict-Beobachtungsraum.")
        candidates = observation_space.spaces.get("candidates")
        if (candidates is None or candidates.shape is None or len(candidates.shape) != 2
                or candidates.shape[0] != action_space.n):
            raise ValueError("Aktionsraum und Kandidatenzahl müssen übereinstimmen.")
        super().__init__(
            observation_space, action_space, lr_schedule,
            net_arch=[], activation_fn=activation_fn,
            features_extractor_class=CandidateFeaturesExtractor,
            features_extractor_kwargs={"embedding_dim": self.embedding_dim, "activation_fn": activation_fn},
            normalize_images=normalize_images,
            optimizer_class=optimizer_class, optimizer_kwargs=optimizer_kwargs,
        )

    def make_q_net(self) -> CandidateQNetwork:
        # Online- und Targetnetz erhalten getrennte Merkmalsextraktoren.
        net_args = self._update_features_extractor(self.net_args, features_extractor=None)
        return CandidateQNetwork(**net_args, hidden_dim=self.hidden_dim).to(self.device)

    def _get_constructor_parameters(self) -> dict[str, Any]:
        data = super()._get_constructor_parameters()
        for name in ("net_arch", "features_extractor_class", "features_extractor_kwargs"):
            data.pop(name, None)
        data.update(embedding_dim=self.embedding_dim, hidden_dim=self.hidden_dim)
        return data
