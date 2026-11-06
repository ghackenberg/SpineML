"""Speichert vollständige Episoden und berechnet ihre Off-Policy-Gewichte."""

from __future__ import annotations

import math
from numbers import Integral

import numpy as np


def discounted_returns(rewards: list[float], gamma: float) -> list[float]:
    """Berechnet die tatsächlich erhaltene Restbelohnung jeder Entscheidung."""
    if not math.isfinite(gamma) or not 0.0 <= gamma <= 1.0:
        raise ValueError("gamma muss endlich sein und zwischen 0 und 1 liegen.")
    returns = [0.0] * len(rewards)
    remaining_return = 0.0
    for index in range(len(rewards) - 1, -1, -1):
        reward = float(rewards[index])
        if not math.isfinite(reward):
            raise ValueError("Die Belohnungen müssen endlich sein.")
        remaining_return = reward + gamma * remaining_return
        returns[index] = remaining_return
    return returns


def suffix_log_importance_weights(target_probabilities, behavior_probabilities) -> np.ndarray:
    """Berechnet das Wahrscheinlichkeitsverhältnis des weiteren Episodenverlaufs."""
    target = np.asarray(target_probabilities, dtype=np.float64)
    behavior = np.asarray(behavior_probabilities, dtype=np.float64)
    if target.ndim != 1 or behavior.ndim != 1 or target.shape != behavior.shape:
        raise ValueError("Beide Wahrscheinlichkeitslisten müssen dieselbe eindimensionale Form haben.")
    if not np.isfinite(target).all() or ((target < 0) | (target > 1)).any():
        raise ValueError("Zielwahrscheinlichkeiten müssen endlich sein und zwischen 0 und 1 liegen.")
    if not np.isfinite(behavior).all() or ((behavior <= 0) | (behavior > 1)).any():
        raise ValueError("Die damalige Wahrscheinlichkeit jeder gewählten Aktion muss positiv sein.")

    log_weights = np.zeros(len(target), dtype=np.float64)
    remaining_log_weight = 0.0
    for index in range(len(target) - 1, -1, -1):
        # Q(s, a) setzt die aktuelle Aktion bereits voraus: nur spätere Aktionen zählen.
        log_weights[index] = remaining_log_weight
        if target[index] == 0.0:
            remaining_log_weight = -math.inf
        elif remaining_log_weight != -math.inf:
            remaining_log_weight += math.log(target[index]) - math.log(behavior[index])
    return log_weights


def normalise_log_weights(log_weights) -> np.ndarray:
    """Normiert die Gewichte stabil auf Summe 1, ohne Quotienten abzuschneiden."""
    # Diese Selbstnormierung ist bei endlich vielen Daten nicht unverzerrt.
    # Stark unterschiedliche Policies können weiterhin wenige Einträge dominieren lassen.
    values = np.asarray(log_weights, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("Die logarithmischen Gewichte müssen eine eindimensionale Liste sein.")
    if np.isnan(values).any() or np.isposinf(values).any():
        raise ValueError("Logarithmische Gewichte dürfen weder NaN noch positiv unendlich sein.")
    weights = np.zeros(len(values), dtype=np.float64)
    if not len(values):
        return weights
    maximum = float(values.max())
    if maximum == -math.inf:
        return weights
    # Derselbe Faktor kürzt sich bei der Normierung heraus; große Produkte laufen nicht über.
    weights = np.exp(values - maximum)
    return weights / weights.sum()


def effective_sample_size(weights) -> float:
    """Zeigt, wie viele gleich gewichtete Einträge den Gewichten ungefähr entsprechen."""
    values = np.asarray(weights, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Die Gewichte müssen endlich, nichtnegativ und eindimensional sein.")
    if not len(values):
        return 0.0
    maximum = float(values.max())
    if maximum == 0.0:
        return 0.0
    scaled = values / maximum
    return float(scaled.sum() ** 2 / np.square(scaled).sum())


class EpisodeReplayBuffer:
    """Behält ganze Episoden; bei Platzmangel wird die älteste Episode entfernt."""

    def __init__(self, max_episodes: int = 8, max_transitions: int = 10_000):
        for name, value in (("max_episodes", max_episodes), ("max_transitions", max_transitions)):
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
                raise ValueError(f"{name} muss eine positive ganze Zahl sein.")
        self.max_episodes = int(max_episodes)
        self.max_transitions = int(max_transitions)
        self.episodes: list[dict] = []
        self.transition_count = 0
        self.evicted_episodes = 0
        self.oversized_episode = False

    def __len__(self) -> int:
        return len(self.episodes)

    def add(self, episode: dict) -> int:
        """Übernimmt eine beendete Episode und gibt die Anzahl verdrängter Episoden zurück."""
        if not episode.get("terminated", False) and not episode.get("truncated", False):
            raise ValueError("In den Replay Buffer gehören nur beendete Episoden.")
        fields = ("observations", "actions", "rewards", "behavior_probabilities")
        for name in fields:
            if name not in episode:
                raise ValueError(f"Der Episode fehlt {name!r}.")
        transition_count = len(episode["actions"])
        if transition_count == 0:
            raise ValueError("Eine gespeicherte Episode benötigt mindestens eine Entscheidung.")
        for name in fields:
            if len(episode[name]) != transition_count:
                raise ValueError("Zustände, Aktionen, Belohnungen und Wahrscheinlichkeiten müssen zusammenpassen.")
        probabilities = np.asarray(episode["behavior_probabilities"], dtype=np.float64)
        if (probabilities.ndim != 1 or not np.isfinite(probabilities).all()
                or ((probabilities <= 0.0) | (probabilities > 1.0)).any()):
            raise ValueError("Die damaligen Auswahlwahrscheinlichkeiten müssen zwischen 0 und 1 liegen und positiv sein.")
        rewards = np.asarray(episode["rewards"], dtype=np.float64)
        if rewards.ndim != 1 or not np.isfinite(rewards).all():
            raise ValueError("Die gespeicherten Belohnungen müssen endlich sein.")

        # Die Daten bleiben unverändert; sie werden nach der Übergabe nur noch gelesen.
        self.episodes.append(episode)
        self.transition_count += transition_count
        evicted = 0
        while len(self.episodes) > self.max_episodes or (
            self.transition_count > self.max_transitions and len(self.episodes) > 1
        ):
            oldest_episode = self.episodes.pop(0)
            self.transition_count -= len(oldest_episode["actions"])
            evicted += 1
        self.evicted_episodes += evicted
        # Eine einzelne zu lange Episode bleibt vollständig erhalten, statt ihren Verlauf abzuschneiden.
        self.oversized_episode = self.transition_count > self.max_transitions
        return evicted

    def sample_episodes(self, count: int, rng: np.random.Generator) -> list[dict]:
        """Zieht vollständige Episoden ohne Wiederholung mit dem Zufallsgenerator des Lerners."""
        if isinstance(count, bool) or not isinstance(count, Integral) or count < 1:
            raise ValueError("Die Anzahl gezogener Episoden muss positiv sein.")
        selected = []
        if not self.episodes:
            return selected
        indices = rng.choice(len(self.episodes), size=min(int(count), len(self.episodes)), replace=False)
        for index in indices:
            selected.append(self.episodes[int(index)])
        return selected
