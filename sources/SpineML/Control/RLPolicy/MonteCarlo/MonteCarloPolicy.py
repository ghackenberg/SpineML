"""Actor-Netz für das Monte-Carlo-Verfahren REINFORCE von Tianshou."""

from __future__ import annotations

from numbers import Integral
from typing import Any

import numpy as np
import torch
from gymnasium import spaces
from torch import nn


def positive_integer(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} muss eine positive ganze Zahl sein.")
    return int(value)


def _create_encoder(input_size: int, embedding_size: int) -> nn.Sequential:
    """Wandelt Merkmale in einen Vektor mit fester Länge um."""
    return nn.Sequential(
        nn.Linear(input_size, embedding_size),
        nn.Tanh(),
        nn.Linear(embedding_size, embedding_size),
        nn.Tanh(),
    )


class MonteCarloPolicy(nn.Module):
    """Tianshou-Actor mit gepooltem Kontext und einem slotunabhängigen Scorer.

    Die Maske wird vor der Wahrscheinlichkeitsverteilung angewendet. Ein leerer
    Endzustand darf gespeichert, aber niemals für eine Aktionswahl benutzt werden.
    """

    def __init__(
        self,
        observation_space: spaces.Dict,
        action_space: spaces.Discrete,
        embedding_dim: int = 32,
        hidden_dim: int = 64,
    ):
        super().__init__()
        self.embedding_dim = positive_integer("embedding_dim", embedding_dim)
        self.hidden_dim = positive_integer("hidden_dim", hidden_dim)
        if not isinstance(observation_space, spaces.Dict):
            raise ValueError("REINFORCE benötigt einen Dict-Beobachtungsraum.")
        if not isinstance(action_space, spaces.Discrete) or action_space.start != 0:
            raise ValueError("REINFORCE benötigt Discrete-Aktionen ab Index 0.")
        # Erwartete Datenform für die Prüfung: 1 = Zahlenliste, 2 = Tabelle.
        ranks = {
            "context": 1,      # Allgemeine Informationen zur aktuellen Entscheidung.
            "entities": 2,     # Eine Zeile pro Job, Roboter oder Maschine; Spalten sind Merkmale.
            "entity_mask": 1,  # Welche Objektzeilen sind echt und welche nur Auffüllplätze?
            "candidates": 2,   # Eine Zeile pro angebotener Aktion; Spalten sind Merkmale.
            "action_mask": 1,  # Welche Kandidatenplätze sind echt und welche leer?
        }
        if set(observation_space.spaces) != set(ranks):
            raise ValueError("Der Beobachtungsraum muss die fünf Kandidatenfelder enthalten.")
        for name, rank in ranks.items():
            shape = observation_space[name].shape
            if shape is None or len(shape) != rank:
                raise ValueError(f"Ungültige Form des Beobachtungsfeldes {name!r}.")
            for size in shape:
                if size < 1:
                    raise ValueError(f"Leeres Beobachtungsfeld {name!r}.")
        self.shapes = {}
        for name in ranks:
            self.shapes[name] = observation_space[name].shape
        self.max_actions, candidate_size = self.shapes["candidates"]
        max_entities, entity_size = self.shapes["entities"]
        if self.shapes["action_mask"] != (self.max_actions,) or action_space.n != self.max_actions:
            raise ValueError("Aktionsraum, Kandidaten und action_mask müssen gleich groß sein.")
        if self.shapes["entity_mask"] != (max_entities,):
            raise ValueError("entity_mask muss eine Stelle pro Entitätszeile haben.")

        self.context_encoder = _create_encoder(self.shapes["context"][0], self.embedding_dim)
        self.entity_encoder = _create_encoder(entity_size, self.embedding_dim)
        self.candidate_encoder = _create_encoder(candidate_size, self.embedding_dim)
        # Kontext + Mittelwert/Maximum beider Mengen + der einzelne Kandidat.
        self.scorer = nn.Sequential(
            nn.Linear(6 * self.embedding_dim, self.hidden_dim),
            nn.Tanh(),
            nn.Linear(self.hidden_dim, 1),
        )

    @property
    def device(self) -> torch.device:
        return next(self.parameters()).device

    def set_training_mode(self, mode: bool) -> None:
        self.train(mode)

    @staticmethod
    def _pool(rows: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # Nur belegte Zeilen gehen in Mittelwert und Maximum ein.
        row_mask = mask.unsqueeze(-1)
        row_sum = rows.masked_fill(~row_mask, 0).sum(dim=1)
        row_count = row_mask.sum(dim=1).clamp_min(1)
        mean = row_sum / row_count
        maximum = rows.masked_fill(~row_mask, -torch.inf).amax(dim=1)
        maximum = maximum.masked_fill(~row_mask.any(dim=1), 0)
        return mean, maximum

    def _observations(self, observation: Any) -> dict[str, torch.Tensor]:
        result = {}
        try:
            unbatched = np.ndim(observation["context"]) == 1
            for name, shape in self.shapes.items():
                value = torch.as_tensor(observation[name], device=self.device)
                if unbatched:
                    value = value.unsqueeze(0)
                if value.ndim != len(shape) + 1 or tuple(value.shape[1:]) != shape:
                    raise ValueError(f"Falsche Form im Beobachtungsfeld {name!r}.")
                if name.endswith("_mask"):
                    if not bool(((value == 0) | (value == 1)).all()):
                        raise ValueError(f"{name} darf nur 0 und 1 enthalten.")
                    value = value.bool()
                else:
                    value = value.float()
                result[name] = value
        except (KeyError, TypeError) as error:
            raise ValueError("Unvollständige Kandidatenbeobachtung.") from error
        batch_size = result["context"].shape[0]
        for value in result.values():
            if value.shape[0] != batch_size:
                raise ValueError("Alle Beobachtungsfelder benötigen dieselbe Batchgröße.")
        return result

    def logits(self, observation: Any) -> torch.Tensor:
        values = self._observations(observation)
        action_mask = values["action_mask"]
        if not bool(action_mask.any(dim=1).all()):
            raise ValueError("Eine Aktionswahl benötigt mindestens einen gültigen Kandidaten.")
        entity_mask = values["entity_mask"]
        entities = values["entities"].masked_fill(~entity_mask.unsqueeze(-1), 0)
        candidates = values["candidates"].masked_fill(~action_mask.unsqueeze(-1), 0)
        for value in (values["context"], entities, candidates):
            if not bool(torch.isfinite(value).all()):
                raise ValueError("Aktive Beobachtungsmerkmale müssen endlich sein.")
        context = self.context_encoder(values["context"])
        entity_features = self.entity_encoder(entities)
        candidate_features = self.candidate_encoder(candidates)
        entity_mean, entity_maximum = self._pool(entity_features, entity_mask)
        candidate_mean, candidate_maximum = self._pool(candidate_features, action_mask)
        summary = torch.cat((
            context, entity_mean, entity_maximum, candidate_mean, candidate_maximum,
        ), dim=1)
        # Jeder Kandidat erhält denselben Kontext und seine eigenen Merkmale.
        context_per_candidate = summary.unsqueeze(1).expand(-1, self.max_actions, -1)
        combined_features = torch.cat((context_per_candidate, candidate_features), dim=2)
        logits = self.scorer(combined_features).squeeze(-1)
        # Ungültige Kandidaten erhalten exakt Wahrscheinlichkeit 0.
        return logits.masked_fill(~action_mask, -torch.inf)

    def forward(self, obs: Any, state: Any = None, info: Any = None):
        return self.logits(obs), state
