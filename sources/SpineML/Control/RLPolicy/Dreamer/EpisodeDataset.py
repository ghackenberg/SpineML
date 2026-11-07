"""Behält alle gesammelten Lern-Episoden auf der Festplatte statt im Arbeitsspeicher."""

from pathlib import Path
import pickle

from .SequenceReplay import SequenceReplay


class EpisodeDataset:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        if any(self.directory.iterdir()):
            raise ValueError("Der Ordner für Weltmodell-Daten muss neu oder leer sein.")
        self.episodes = []
        self.transition_count = 0
        self.oversized_episode = False

    def __len__(self):
        return len(self.episodes)

    def add(self, episode):
        steps = SequenceReplay.validate_episode(episode)
        path = self.directory / f"episode_{len(self.episodes) + 1:06d}.pkl"
        with path.open("xb") as stream:
            pickle.dump(episode, stream, protocol=pickle.HIGHEST_PROTOCOL)
        self.episodes.append({"path": path, "steps": steps})
        self.transition_count += steps

    def sample_sequences(self, batch_size, sequence_length, rng):
        if not self.episodes:
            raise ValueError("Die Weltmodell-Daten enthalten noch keine vollständige Lern-Episode.")
        windows = []
        loaded = {}
        for window_index in range(batch_size):
            if window_index == 0:
                # Auch in dieser Datengruppe ist die seltene Endbelohnung vertreten.
                episode_index = int(rng.integers(len(self.episodes)))
                entry = self.episodes[episode_index]
                start = max(0, entry["steps"] - sequence_length)
            else:
                start = int(rng.integers(self.transition_count))
                for episode_index, entry in enumerate(self.episodes):
                    if start < entry["steps"]:
                        break
                    start -= entry["steps"]
            if episode_index not in loaded:
                # Nur selbst gespeicherte Pickle-Dateien öffnen.
                with entry["path"].open("rb") as stream:
                    loaded[episode_index] = pickle.load(stream)
            episode = loaded[episode_index]
            stop = min(start + sequence_length, entry["steps"])
            windows.append({
                "observations": episode["observations"][:stop + 1],
                "actions": episode["actions"][:stop],
                "rewards": episode["rewards"][:stop],
                "terminated": episode["terminals"][:stop],
                "truncated": episode["truncations"][:stop],
                "train_start": start,
            })
        return windows
