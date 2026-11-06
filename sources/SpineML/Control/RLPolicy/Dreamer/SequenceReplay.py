"""Speichert ganze Episoden und wählt Lernfenster mit unverfälschtem Vorlauf."""

from collections import deque
import math

from ..Shared.CandidateQNetwork import _positive_size


class SequenceReplay:
    def __init__(self, max_episodes=8, max_transitions=10_000):
        self.max_episodes = _positive_size("replay_episodes", max_episodes)
        self.max_transitions = _positive_size("replay_transitions", max_transitions)
        self.episodes = deque()
        self.transition_count = 0
        self.oversized_episode = False

    def __len__(self):
        return len(self.episodes)

    def add(self, episode):
        steps = len(episode["actions"])
        if steps < 1 or len(episode["observations"]) != steps + 1:
            raise ValueError("Eine Dreamer-Episode benötigt T Aktionen und T+1 Beobachtungen.")
        for name in ("rewards", "terminals", "truncations"):
            if len(episode[name]) != steps:
                raise ValueError(f"Das Episodenfeld {name} muss T Einträge enthalten.")
        for index in range(steps):
            if not math.isfinite(episode["rewards"][index]):
                raise ValueError("Belohnungen müssen endlich sein.")
            finished = episode["terminals"][index] or episode["truncations"][index]
            if finished != (index == steps - 1):
                raise ValueError("Nur der letzte Übergang darf und muss eine Episode beenden.")
        self.episodes.append(episode)
        self.transition_count += steps
        while len(self.episodes) > 1 and (
            len(self.episodes) > self.max_episodes or self.transition_count > self.max_transitions
        ):
            oldest = self.episodes.popleft()
            self.transition_count -= len(oldest["actions"])
        # Eine zu große einzelne Episode bleibt vollständig statt abgeschnitten.
        self.oversized_episode = self.transition_count > self.max_transitions

    def sample_sequences(self, batch_size, sequence_length, rng):
        if not self.episodes:
            raise ValueError("Der Sequenzspeicher enthält noch keine vollständige Episode.")
        windows = []
        for window_index in range(batch_size):
            if window_index == 0:
                # Mindestens ein Fenster enthält die seltene Belohnung am Episodenende.
                episode_index = int(rng.integers(len(self.episodes)))
                selected_episode = self.episodes[episode_index]
                start = max(0, len(selected_episode["actions"]) - sequence_length)
            else:
                # Die anderen Fenster können an jedem gespeicherten Übergang beginnen.
                start = int(rng.integers(self.transition_count))
                selected_episode = None
                for episode in self.episodes:
                    if start < len(episode["actions"]):
                        selected_episode = episode
                        break
                    start -= len(episode["actions"])
            stop = min(start + sequence_length, len(selected_episode["actions"]))
            windows.append({
                "observations": selected_episode["observations"][:stop + 1],
                "actions": selected_episode["actions"][:stop],
                "rewards": selected_episode["rewards"][:stop],
                "terminated": selected_episode["terminals"][:stop],
                "truncated": selected_episode["truncations"][:stop],
                "train_start": start,
            })
        # Das Netz rekonstruiert sein Gedächtnis am echten Reset, nicht am Fensterrand.
        return windows
