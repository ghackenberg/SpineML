"""Example 3B: alternative operation durations and lower-risk machines.

The layout and orders of Example 3 remain unchanged. Machines in the second
corridor have lower defect probabilities. Additional operations provide
alternative durations; defect risk belongs only to the selected machine.
"""

import runpy
from pathlib import Path

_base = runpy.run_path(
    str(Path(__file__).resolve().with_name("example-3.py"))
)
globals().update(_base)

OperationType("Operation 1 Alternative", 5, 4, mt1, tt1, pt1, pt2)
OperationType("Operation 2 Alternative", 7, 3, mt1, tt2, pt3, pt2)
OperationType("Operation 3 Alternative", 11, 5, mt2, tt3, pt2, pt4)
OperationType("Operation 4 Alternative", 6, 6, mt2, tt2, pt2, pt5)
OperationType("Operation 5 Alternative", 13, 2, mt3, tt1, pt2, pt6)

_quality_probabilities = {
    "Machine 3.2.1": 0.10,
    "Machine 3.2.2": 0.12,
    "Machine 3.2.3": 0.10,
    "Machine 3.2.4": 0.12,
}
for _machine in c3_2.machines_left + c3_2.machines_right:
    _machine.defect_probability = _quality_probabilities[_machine.name]

if __name__ == "__main__":
    simulate(l3, s3, till=sim.inf, animation_speed=5)
