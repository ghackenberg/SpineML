"""Gemeinsamer Netzaufbau für die Kandidatenbewertung mit DQN und Monte Carlo."""

from __future__ import annotations

from numbers import Integral
from typing import Any

try:
    import torch as th
    from gymnasium import spaces
    from stable_baselines3.common.policies import BasePolicy
    from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
    from stable_baselines3.dqn.policies import QNetwork
    from torch import nn
except ImportError as error:
    raise ImportError(
        'Der Kandidaten-Netzaufbau benötigt die Trainingspakete: python -m pip install ".[rl-training]"'
    ) from error


def _positive_size(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} muss eine positive ganze Zahl sein.")
    return int(value)


def candidate_action_mask(observations: dict[str, th.Tensor], action_count: int) -> th.Tensor:
    """Liest die Kandidatenmaske; leere Endzustände sind hier noch erlaubt."""
    mask = observations["action_mask"].to(dtype=th.bool)
    if mask.ndim == 1:
        mask = mask.unsqueeze(0)
    if mask.ndim != 2 or mask.shape[1] != action_count:
        raise ValueError("action_mask muss eine Stelle pro Aktionskandidat haben.")
    return mask


class CandidateFeaturesExtractor(BaseFeaturesExtractor):
    """Verarbeitet Kontext, Objekte und verfügbare Aktionskandidaten."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        embedding_dim: int = 32,
        activation_fn: type[nn.Module] = nn.Tanh,
    ):
        embedding_dim = _positive_size("embedding_dim", embedding_dim)
        if not isinstance(observation_space, spaces.Dict):
            raise ValueError("Die Kandidaten-Policy benötigt einen Dict-Beobachtungsraum.")
        dimensions = {
            "context": 1, "entities": 2, "entity_mask": 1,
            "candidates": 2, "action_mask": 1,
        }
        for name, rank in dimensions.items():
            subspace = observation_space.spaces.get(name)
            if subspace is None or subspace.shape is None or len(subspace.shape) != rank:
                raise ValueError(f"Ungültige Form des Beobachtungsfelds {name!r}.")
            for size in subspace.shape:
                if size < 1:
                    raise ValueError(f"Leeres Beobachtungsfeld {name!r}.")
        max_actions, candidate_size = observation_space["candidates"].shape
        max_entities, entity_size = observation_space["entities"].shape
        if observation_space["action_mask"].shape != (max_actions,):
            raise ValueError("action_mask muss genau eine Stelle pro Kandidatenzeile haben.")
        if observation_space["entity_mask"].shape != (max_entities,):
            raise ValueError("entity_mask muss genau eine Stelle pro Entitätszeile haben.")

        # Kontext sowie Mittelwert und Maximum der Objekt- und Kandidatenmerkmale.
        summary_dim = 5 * embedding_dim
        super().__init__(
            observation_space,
            features_dim=summary_dim + max_actions * (embedding_dim + 1),
        )
        self.embedding_dim = embedding_dim
        self.max_actions = max_actions
        self.summary_dim = summary_dim

        def encoder(input_size: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Linear(input_size, embedding_dim), activation_fn(),
                nn.Linear(embedding_dim, embedding_dim), activation_fn(),
            )

        self.context_encoder = encoder(observation_space["context"].shape[0])
        self.entity_encoder = encoder(entity_size)
        self.candidate_encoder = encoder(candidate_size)

    @staticmethod
    def _pool(rows: th.Tensor, mask: th.Tensor) -> tuple[th.Tensor, th.Tensor]:
        valid = mask.to(dtype=th.bool).unsqueeze(-1)
        selected = rows.masked_fill(~valid, 0)
        count = valid.sum(dim=1).clamp_min(1).to(dtype=rows.dtype)
        mean = selected.sum(dim=1) / count
        maximum = rows.masked_fill(~valid, th.finfo(rows.dtype).min).amax(dim=1)
        maximum = maximum.masked_fill(~valid.any(dim=1), 0)
        return mean, maximum

    def forward(self, observations: dict[str, th.Tensor]) -> th.Tensor:
        if observations["context"].ndim == 1:
            batched_observations = {}
            for name, value in observations.items():
                batched_observations[name] = value.unsqueeze(0)
            observations = batched_observations
        action_mask = observations["action_mask"].to(dtype=th.bool)
        entity_mask = observations["entity_mask"].to(dtype=th.bool)
        context = self.context_encoder(observations["context"])
        # Gepaddete Zeilen tragen nichts zum Zustand bei.
        entities = observations["entities"].masked_fill(~entity_mask.unsqueeze(-1), 0)
        candidates = observations["candidates"].masked_fill(~action_mask.unsqueeze(-1), 0)
        entities = self.entity_encoder(entities)
        candidates = self.candidate_encoder(candidates)
        entity_mean, entity_max = self._pool(entities, entity_mask)
        candidate_mean, candidate_max = self._pool(candidates, action_mask)
        summary = th.cat((context, entity_mean, entity_max, candidate_mean, candidate_max), dim=1)
        candidates = candidates.masked_fill(~action_mask.unsqueeze(-1), 0)
        return th.cat((
            summary, candidates.flatten(start_dim=1), action_mask.to(dtype=context.dtype),
        ), dim=1)


class CandidateQNetwork(QNetwork):
    """Bewertet alle Kandidaten mit denselben Gewichten statt nach Slotindex."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        features_extractor: CandidateFeaturesExtractor,
        features_dim: int,
        net_arch: list[int] | None = None,
        activation_fn: type[nn.Module] = nn.Tanh,
        normalize_images: bool = False,
        hidden_dim: int = 64,
    ):
        self.hidden_dim = _positive_size("hidden_dim", hidden_dim)
        # Keinen großen, indexabhängigen Q-Head nur zum Ersetzen anlegen.
        BasePolicy.__init__(
            self, observation_space, action_space,
            features_extractor=features_extractor, normalize_images=normalize_images,
        )
        self.net_arch = []
        self.activation_fn = activation_fn
        self.features_dim = features_dim
        self.embedding_dim = features_extractor.embedding_dim
        self.summary_dim = features_extractor.summary_dim
        self.max_actions = features_extractor.max_actions
        self.q_net = nn.Sequential(
            nn.Linear(self.summary_dim + self.embedding_dim, self.hidden_dim),
            activation_fn(), nn.Linear(self.hidden_dim, 1),
        )

    def forward(self, obs: dict[str, th.Tensor]) -> th.Tensor:
        # Unmaskierte, endliche Q-Werte für Training und gewählte Aktionen.
        features = self.extract_features(obs, self.features_extractor)
        summary = features[:, :self.summary_dim]
        candidate_end = self.summary_dim + self.max_actions * self.embedding_dim
        candidates = features[:, self.summary_dim:candidate_end].reshape(
            -1, self.max_actions, self.embedding_dim,
        )
        repeated_summary = summary.unsqueeze(1).expand(-1, self.max_actions, -1)
        candidate_features = th.cat((candidates, repeated_summary), dim=2)
        return self.q_net(candidate_features).squeeze(-1)

    def _predict(self, observation: dict[str, th.Tensor], deterministic: bool = True) -> th.Tensor:
        valid = candidate_action_mask(observation, self.action_space.n)
        if not bool(valid.any(dim=1).all()):
            raise ValueError("Eine Aktionsauswahl benötigt mindestens einen gültigen Kandidaten pro Zustand.")
        q_values = self(observation)
        return q_values.masked_fill(~valid, -th.inf).argmax(dim=1).reshape(-1)

    def _get_constructor_parameters(self) -> dict[str, Any]:
        data = super()._get_constructor_parameters()
        data.update(hidden_dim=self.hidden_dim)
        return data
