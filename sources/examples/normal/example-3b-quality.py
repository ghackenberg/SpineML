"""Example 3B: gleiche Fabrik, aber alternative Qualitätsrouten.

Die normale Example-3-Konfiguration bleibt unverändert. Für jede wichtige
Produktumwandlung werden zusätzliche Operationen angeboten: eine schnelle
Route mit höherem Defektrisiko und eine langsamere Qualitätsroute.
"""

import runpy
from pathlib import Path

_base = runpy.run_path(
    str(Path(__file__).resolve().with_name("example-3.py"))
)
globals().update(_base)

OperationType("Operation 1 Quality", 5, 4, 0.10, mt1, tt1, pt1, pt2)
OperationType("Operation 2 Quality", 7, 3, 0.12, mt1, tt2, pt3, pt2)
OperationType("Operation 3 Quality", 11, 5, 0.10, mt2, tt3, pt2, pt4)
OperationType("Operation 4 Quality", 6, 6, 0.12, mt2, tt2, pt2, pt5)
OperationType("Operation 5 Quality", 13, 2, 0.10, mt3, tt1, pt2, pt6)

if __name__ == "__main__":
    simulate(l3, s3, till=sim.inf, animation_speed=5)
