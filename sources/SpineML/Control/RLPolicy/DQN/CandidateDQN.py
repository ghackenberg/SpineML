from __future__ import annotations

import numpy as np

try:
    import torch as th
    from stable_baselines3 import DQN
    from stable_baselines3.common.noise import ActionNoise
    from torch.nn import functional as F
except ImportError as error:
    raise ImportError(
        'Kandidaten-DQN benötigt die Trainingspakete: python -m pip install ".[rl-training]"'
    ) from error

from .CandidateDQNPolicy import CandidateDQNPolicy
from ..Shared.CandidateQNetwork import candidate_action_mask


class CandidateDQN(DQN):
    """SB3-DQN mit Maskierung bei Auswahl, Exploration und Bellman-Targets."""

    policy_aliases = {
        "CandidateDQNPolicy": CandidateDQNPolicy,
        "MultiInputPolicy": CandidateDQNPolicy,
    }

    def _setup_model(self) -> None:
        if not issubclass(self.policy_class, CandidateDQNPolicy):
            raise ValueError("CandidateDQN benötigt CandidateDQNPolicy.")
        super()._setup_model()

    def _valid_action_masks(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        # Eine Maskenzeile kennzeichnet die gültigen Kandidaten eines Zustands.
        if not isinstance(observation, dict) or "action_mask" not in observation:
            raise ValueError("Kandidaten-DQN benötigt die action_mask in der Beobachtung.")
        mask = np.asarray(observation["action_mask"], dtype=bool)
        if mask.ndim == 1:
            mask = mask[np.newaxis, :]
        if mask.ndim != 2 or mask.shape[1] != self.action_space.n:
            raise ValueError("action_mask muss eine Stelle pro Aktionskandidat haben.")
        if not bool(mask.any(axis=1).all()):
            raise ValueError("Eine Aktionsauswahl benötigt mindestens einen gültigen Kandidaten pro Zustand.")
        return mask

    def _random_valid_actions(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        # Wählt pro Zustand zufällig einen vorhandenen Kandidaten.
        masks = self._valid_action_masks(observation)
        actions = np.empty(masks.shape[0], dtype=np.int64)
        for index in range(masks.shape[0]):
            actions[index] = np.random.choice(np.flatnonzero(masks[index]))
        return actions

    def predict(
        self,
        observation: np.ndarray | dict[str, np.ndarray],
        state: tuple[np.ndarray, ...] | None = None,
        episode_start: np.ndarray | None = None,
        deterministic: bool = False,
    ) -> tuple[np.ndarray, tuple[np.ndarray, ...] | None]:
        masks = self._valid_action_masks(observation)
        actions, state = self.policy.predict(observation, state, episode_start, deterministic=True)
        if not deterministic and self.exploration_rate > 0:
            original_shape = actions.shape
            actions = actions.reshape(-1).copy()
            for index in range(masks.shape[0]):
                if np.random.random() < self.exploration_rate:
                    actions[index] = np.random.choice(np.flatnonzero(masks[index]))
            actions = actions.reshape(original_shape)
        return actions, state

    def _sample_action(
        self,
        learning_starts: int,
        action_noise: ActionNoise | None = None,
        n_envs: int = 1,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.num_timesteps < learning_starts:
            if self._last_obs is None:
                raise RuntimeError("Vor der Aktionsauswahl muss die Umgebung zurückgesetzt werden.")
            actions = self._random_valid_actions(self._last_obs)
            if actions.shape != (n_envs,):
                raise ValueError("Die Kandidatenmasken passen nicht zur Anzahl der Umgebungen.")
            return actions, actions
        return super()._sample_action(learning_starts, action_noise, n_envs)

    def train(self, gradient_steps: int, batch_size: int = 100) -> None:
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)
        losses = []
        for _ in range(gradient_steps):
            # Lädt eine zufällige Datengruppe aus dem Erfahrungsspeicher.
            replay_data = self.replay_buffer.sample(batch_size, env=self._vec_normalize_env)
            if replay_data.discounts is None:
                discounts = self.gamma
            else:
                discounts = replay_data.discounts

            with th.no_grad():
                # Berechnet das Lernziel aus Belohnung und geschätztem Folgewert.
                next_masks = candidate_action_mask(replay_data.next_observations, self.action_space.n)
                terminal = replay_data.dones.reshape(-1).to(dtype=th.bool)
                if bool((~next_masks.any(dim=1) & ~terminal).any()):
                    raise ValueError("Ein nichtterminaler Folgezustand hat keinen gültigen Kandidaten.")
                next_q_values = self.q_net_target(replay_data.next_observations)
                next_q_values = next_q_values.masked_fill(~next_masks, -th.inf).max(dim=1).values
                # Endzustände bootstrappen nie; auch leere Masken bleiben endlich.
                next_q_values = th.where(terminal, th.zeros_like(next_q_values), next_q_values)
                target_q_values = replay_data.rewards + discounts * next_q_values.reshape(-1, 1)

            actions = replay_data.actions.long()
            masks = candidate_action_mask(replay_data.observations, self.action_space.n)
            if not bool(th.gather(masks, dim=1, index=actions).all()):
                raise ValueError("Der Replay Buffer enthält eine ungültige Aktion.")
            current_q_values = self.q_net(replay_data.observations)
            current_q_values = th.gather(current_q_values, dim=1, index=actions)
            loss = F.smooth_l1_loss(current_q_values, target_q_values)
            losses.append(loss.item())

            # Passt das Hauptnetz an; das Target-Netz bleibt in diesem Schritt unverändert.
            self.policy.optimizer.zero_grad()
            loss.backward()
            th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
            self.policy.optimizer.step()

        self._n_updates += gradient_steps
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/loss", np.mean(losses))
