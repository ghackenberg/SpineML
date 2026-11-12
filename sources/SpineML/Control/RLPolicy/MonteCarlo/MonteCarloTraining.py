"""Erstellt Tianshous Trainer und getrennte Simulationsprozesse."""

from dataclasses import dataclass
import json
import math
import os
from time import perf_counter

import gymnasium as gym
import torch
from tianshou.algorithm.modelfree.reinforce import DiscreteActorPolicy, Reinforce
from tianshou.algorithm.optim import AdamOptimizerFactory
from tianshou.data import Collector, VectorReplayBuffer
from tianshou.env import SubprocVectorEnv
from tianshou.trainer import OnPolicyTrainer, OnPolicyTrainerParams


class _EpisodeInfo(gym.Wrapper):
    """Übergibt Abschlusskennzahlen in einer gleichbleibenden info-Struktur."""

    def reset(self, **kwargs):
        self.started_at = perf_counter()
        observation, _ = self.env.reset(**kwargs)
        return observation, {"episode_summary": ""}

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)
        summary = ""
        if terminated or truncated:
            info = dict(info)
            info["worker_pid"] = os.getpid()
            info["episode_elapsed_seconds"] = perf_counter() - self.started_at
            summary = json.dumps(info, allow_nan=False)
        return observation, reward, terminated, truncated, {"episode_summary": summary}


@dataclass(frozen=True)
class _ProcessEnvironment:
    """Erzeugt eine Umgebung im Worker-Prozess."""

    factory: object

    def __call__(self):
        torch.set_num_threads(1)
        return _EpisodeInfo(self.factory())


class CompleteEpisodeCollector(Collector):
    """Verhindert das Lernen aus überschriebenen oder unfertigen Episoden."""

    def collect(self, *args, **kwargs):
        statistics = super().collect(*args, **kwargs)
        if len(self.buffer) != statistics.n_collected_steps:
            raise RuntimeError(
                "Der Sammelpuffer ist zu klein für die vollständigen Episoden. "
                "--buffer-size erhöhen oder --episodes-per-update verringern. "
                "Mit diesen unvollständigen Daten wurde nicht trainiert."
            )
        if len(self.buffer.unfinished_index()):
            raise RuntimeError("REINFORCE darf hier nur aus vollständigen Episoden lernen.")
        return statistics


def create_algorithm(model):
    """Verbindet den Actor mit Tianshous unveränderter REINFORCE-Lernregel."""
    policy = DiscreteActorPolicy(
        actor=model.policy,
        action_space=model.action_space,
        observation_space=model.observation_space,
    )
    return Reinforce(
        policy=policy,
        gamma=1.0,
        return_standardization=False,
        optim=AdamOptimizerFactory(lr=model.learning_rate),
    )


def create_collector(model, total_episodes):
    """Startet die Simulationsprozesse und erstellt den Episodensammler."""
    worker_count = min(len(model.episode_factories), total_episodes, model.episodes_per_update)
    if model.buffer_capacity < worker_count:
        raise ValueError("--buffer-size benötigt mindestens einen Platz pro Worker.")
    factories = []
    for factory in model.episode_factories[:worker_count]:
        factories.append(_ProcessEnvironment(factory))

    environments = SubprocVectorEnv(factories, context="spawn")
    try:
        buffer = VectorReplayBuffer(
            model.buffer_capacity, worker_count, ignore_obs_next=True,
        )
        return CompleteEpisodeCollector(
            model.algorithm,
            environments,
            buffer,
            on_episode_done_hook=model._record_episode,
        )
    except BaseException:
        environments.close()
        raise


def create_trainer(model, collector, total_episodes):
    """Legt Episoden pro Sammlung und Minibatches pro Lernphase fest."""
    parameters = OnPolicyTrainerParams(
        training_collector=collector,
        collection_step_num_env_steps=None,
        collection_step_num_episodes=min(model.episodes_per_update, total_episodes),
        max_epochs=math.ceil(total_episodes / model.episodes_per_update),
        epoch_num_steps=1,
        batch_size=model.batch_size,
        update_step_num_repetitions=1,
        verbose=False,
        show_progress=False,
    )
    trainer = OnPolicyTrainer(model.algorithm, parameters)
    trainer.reset()
    return trainer
