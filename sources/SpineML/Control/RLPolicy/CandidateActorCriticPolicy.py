from __future__ import annotations

from functools import partial
from numbers import Integral
from typing import Any

import numpy as np

try:
    import torch as th
    from gymnasium import spaces
    from sb3_contrib.common.maskable.distributions import MaskableDistribution
    from sb3_contrib.common.maskable.policies import MaskableMultiInputActorCriticPolicy
    from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
    from stable_baselines3.common.type_aliases import Schedule
    from torch import nn
except ImportError as error:
    raise ImportError(
        'Die Kandidaten-NN-Policy benötigt die Trainingspakete: python -m pip install ".[rl-training]"'
    ) from error


def _positive_size(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} muss eine positive ganze Zahl sein.")
    return int(value)


class CandidateFeaturesExtractor(BaseFeaturesExtractor):
    """Geteilte Zeilenencoder und maskierte, reihenfolgeinvariante Zustands-Pools."""

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
            if any(size < 1 for size in subspace.shape):
                raise ValueError(f"Leeres Beobachtungsfeld {name!r}.")
        max_actions, candidate_size = observation_space["candidates"].shape
        max_entities, entity_size = observation_space["entities"].shape
        if observation_space["action_mask"].shape != (max_actions,):
            raise ValueError("action_mask muss genau eine Stelle pro Kandidatenzeile haben.")
        if observation_space["entity_mask"].shape != (max_entities,):
            raise ValueError("entity_mask muss genau eine Stelle pro Entitätszeile haben.")

        # Kontext + Mittelwert/Maximum beider Mengen; Zeilen bleiben separat erhalten.
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
        selected = th.where(valid, rows, th.zeros_like(rows))
        count = valid.sum(dim=1).clamp_min(1).to(dtype=rows.dtype)
        mean = selected.sum(dim=1) / count
        maximum = rows.masked_fill(~valid, th.finfo(rows.dtype).min).amax(dim=1)
        maximum = th.where(valid.any(dim=1), maximum, th.zeros_like(maximum))
        return mean, maximum

    def forward(self, observations: dict[str, th.Tensor]) -> th.Tensor:
        # predict()/Rollout-Puffer liefern Batches; direkte Tensoraufrufe dürfen unbatched sein.
        if observations["context"].ndim == 1:
            observations = {name: value.unsqueeze(0) for name, value in observations.items()}
        action_mask = observations["action_mask"].to(dtype=th.bool)
        entity_mask = observations["entity_mask"].to(dtype=th.bool)
        context = self.context_encoder(observations["context"])
        # Padding wird bereits vor dem Encoder entfernt, auch bei später verändertem Füllwert.
        entities = self.entity_encoder(th.where(
            entity_mask.unsqueeze(-1), observations["entities"],
            th.zeros_like(observations["entities"]),
        ))
        candidates = self.candidate_encoder(th.where(
            action_mask.unsqueeze(-1), observations["candidates"],
            th.zeros_like(observations["candidates"]),
        ))
        entity_mean, entity_max = self._pool(entities, entity_mask)
        candidate_mean, candidate_max = self._pool(candidates, action_mask)
        summary = th.cat((context, entity_mean, entity_max, candidate_mean, candidate_max), dim=1)
        candidates = th.where(action_mask.unsqueeze(-1), candidates, th.zeros_like(candidates))
        return th.cat((
            summary, candidates.flatten(start_dim=1), action_mask.to(dtype=context.dtype),
        ), dim=1)


class _CandidateLatentExtractor(nn.Module):
    """Trennt zeilenweise Actor-Eingaben von der gepoolten Critic-Eingabe."""

    def __init__(
        self,
        features_extractor: CandidateFeaturesExtractor,
        hidden_dim: int,
        activation_fn: type[nn.Module],
    ):
        super().__init__()
        self.max_actions = features_extractor.max_actions
        self.embedding_dim = features_extractor.embedding_dim
        self.summary_dim = features_extractor.summary_dim
        self.latent_dim_pi = self.summary_dim + self.embedding_dim + 1
        self.latent_dim_vf = hidden_dim
        self.value_net = nn.Sequential(nn.Linear(self.summary_dim, hidden_dim), activation_fn())

    def forward_actor(self, features: th.Tensor) -> th.Tensor:
        summary = features[:, :self.summary_dim]
        candidate_end = self.summary_dim + self.max_actions * self.embedding_dim
        candidates = features[:, self.summary_dim:candidate_end].reshape(
            -1, self.max_actions, self.embedding_dim,
        )
        mask = features[:, candidate_end:].unsqueeze(-1)
        return th.cat((candidates, summary.unsqueeze(1).expand(-1, self.max_actions, -1), mask), dim=2)

    def forward_critic(self, features: th.Tensor) -> th.Tensor:
        return self.value_net(features[:, :self.summary_dim])

    def forward(self, features: th.Tensor) -> tuple[th.Tensor, th.Tensor]:
        return self.forward_actor(features), self.forward_critic(features)


class CandidateActorCriticPolicy(MaskableMultiInputActorCriticPolicy):
    """MaskablePPO-Policy: derselbe Actor bewertet jede tatsächlich angebotene Zeile.

    Kandidatenindizes bleiben unverändert; es gibt keine pro Index gelernten
    Aktionsgewichte. Der Critic nutzt Kontext sowie maskierte Entitäts- und
    Kandidaten-Pools, auch bei Terminalzuständen ohne wählbare Aktion.
    """

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        lr_schedule: Schedule,
        *,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
        activation_fn: type[nn.Module] = nn.Tanh,
        ortho_init: bool = True,
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
            net_arch=[], activation_fn=activation_fn, ortho_init=ortho_init,
            features_extractor_class=CandidateFeaturesExtractor,
            features_extractor_kwargs={"embedding_dim": self.embedding_dim, "activation_fn": activation_fn},
            share_features_extractor=True, normalize_images=normalize_images,
            optimizer_class=optimizer_class, optimizer_kwargs=optimizer_kwargs,
        )

    def _build_mlp_extractor(self) -> None:
        self.mlp_extractor = _CandidateLatentExtractor(
            self.features_extractor, self.hidden_dim, self.activation_fn,
        ).to(self.device)

    def _build(self, lr_schedule: Schedule) -> None:
        # Vor dem Optimizer anlegen: kein globaler Linear(latent, max_actions)-Kopf.
        self._build_mlp_extractor()
        self.action_net = nn.Sequential(
            nn.Linear(self.mlp_extractor.latent_dim_pi - 1, self.hidden_dim),
            self.activation_fn(), nn.Linear(self.hidden_dim, 1),
        )
        self.value_net = nn.Linear(self.mlp_extractor.latent_dim_vf, 1)
        if self.ortho_init:
            for module, gain in (
                (self.features_extractor, np.sqrt(2)),
                (self.mlp_extractor, np.sqrt(2)),
                (self.action_net, np.sqrt(2)), (self.value_net, 1.0),
            ):
                module.apply(partial(self.init_weights, gain=gain))
            self.action_net[-1].apply(partial(self.init_weights, gain=0.01))
        self.optimizer = self.optimizer_class(
            self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs,
        )

    def _get_action_dist_from_latent(
        self,
        latent_pi: th.Tensor,
        action_masks: np.ndarray | th.Tensor | None = None,
    ) -> MaskableDistribution:
        valid = latent_pi[..., -1].to(dtype=th.bool)
        if action_masks is not None:
            supplied = th.as_tensor(action_masks, dtype=th.bool, device=valid.device)
            if supplied.numel() != valid.numel():
                raise ValueError("action_masks hat nicht die Form des Kandidaten-Batches.")
            valid = valid & supplied.reshape(valid.shape)
        if not bool(valid.any(dim=1).all()):
            raise ValueError("Eine Aktionsverteilung benötigt mindestens einen gültigen Kandidaten pro Zustand.")
        logits = self.action_net(latent_pi[..., :-1]).squeeze(-1)
        distribution = self.action_dist.proba_distribution(action_logits=logits)
        distribution.apply_masking(valid)
        return distribution

    def forward(
        self,
        obs: dict[str, th.Tensor],
        deterministic: bool = False,
        action_masks: np.ndarray | th.Tensor | None = None,
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor]:
        features = self.extract_features(obs)
        latent_pi, latent_vf = self.mlp_extractor(features)
        distribution = self._get_action_dist_from_latent(latent_pi, action_masks)
        actions = distribution.get_actions(deterministic=deterministic)
        return (
            actions.reshape((-1, *self.action_space.shape)),
            self.value_net(latent_vf), distribution.log_prob(actions),
        )

    def evaluate_actions(
        self,
        obs: dict[str, th.Tensor],
        actions: th.Tensor,
        action_masks: np.ndarray | th.Tensor | None = None,
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor | None]:
        features = self.extract_features(obs)
        latent_pi, latent_vf = self.mlp_extractor(features)
        distribution = self._get_action_dist_from_latent(latent_pi, action_masks)
        return self.value_net(latent_vf), distribution.log_prob(actions), distribution.entropy()

    def get_distribution(
        self,
        obs: dict[str, th.Tensor],
        action_masks: np.ndarray | th.Tensor | None = None,
    ) -> MaskableDistribution:
        features = self.extract_features(obs)
        return self._get_action_dist_from_latent(self.mlp_extractor.forward_actor(features), action_masks)

    def _get_constructor_parameters(self) -> dict[str, Any]:
        data = super()._get_constructor_parameters()
        # Basisklassenparameter sind hier festgelegt, nicht zusätzliche öffentliche Optionen.
        for name in ("net_arch", "features_extractor_class", "features_extractor_kwargs"):
            data.pop(name, None)
        data.update(embedding_dim=self.embedding_dim, hidden_dim=self.hidden_dim)
        return data
