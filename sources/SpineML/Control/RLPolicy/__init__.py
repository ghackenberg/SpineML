"""Optionale RL-Umgebung; bestehende Heuristiken benötigen dieses Paket nicht."""

from importlib.util import find_spec

from .Shared.RLCandidatePolicy import DecisionRequest, RLCandidatePolicy
from .Shared.RLObservationEncoder import RLObservationEncoder
from .Shared.RLReward import RLReward

if find_spec("gymnasium") is not None:
    from .Shared.SpineRLEnv import SpineRLEnv

__all__ = ["DecisionRequest", "RLCandidatePolicy", "RLObservationEncoder", "RLReward", "SpineRLEnv"]


def __getattr__(name):
    # Kandidatenadapter und Encoder sind auch ohne das optionale Gymnasium nutzbar.
    if name == "SpineRLEnv":
        from .Shared.SpineRLEnv import SpineRLEnv
        globals()[name] = SpineRLEnv
        return SpineRLEnv
    raise AttributeError(name)
