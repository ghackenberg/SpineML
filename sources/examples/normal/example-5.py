"""Larger control benchmark: 24 jobs, alternative routes and shared machines.

Select EXAMPLE_FILE = "example-5.py" in sources/optimization.py to compare
Random, the default heuristic and the weight set found by the optimizer.
This model does not change the policies, their scores or the search settings.
"""

import salabim as sim

from SpineML import (
    Corridor,
    Layout,
    Machine,
    MachineType,
    OperationType,
    Order,
    ProductType,
    Scenario,
    ToolType,
    simulate,
)


# Several machine types can perform the same product transformation.
basic = MachineType("Basic machining")
precision = MachineType("Precision machining")
drilling = MachineType("Drilling")
finishing = MachineType("Finishing")

rough_tool = ToolType("Roughing tool", 3, 2, 48)
milling_tool = ToolType("Milling tool", 2, 2, 32)
precision_tool = ToolType("Precision tool", 3, 3, 36)
drill_tool = ToolType("Drill tool", 1, 2, 28)
polishing_tool = ToolType("Polishing tool", 2, 2, 40)

blank_a = ProductType("Blank A", 12, 12, 12, 5)
blank_b = ProductType("Blank B", 14, 14, 12, 6)
base_body = ProductType("Base body", 16, 16, 12, 6)
milled_body = ProductType("Milled body", 18, 16, 12, 7)
drilled_body = ProductType("Drilled body", 16, 18, 12, 7)
finished_housing = ProductType("Finished housing", 18, 16, 12, 7)
finished_bracket = ProductType("Finished bracket", 16, 18, 12, 7)
polished_part = ProductType("Polished part", 16, 16, 12, 6)

# Duration, tool consumption and defect probability differ between routes.
# Lower defect risk is a simulation property, not an extra heuristic criterion.
OperationType("Rough blank A", 3, 8, 0.18, basic, rough_tool, blank_a, base_body)
OperationType("Precision blank A", 7, 4, 0.08, precision, precision_tool, blank_a, base_body)
OperationType("Rough blank B", 5, 6, 0.14, basic, milling_tool, blank_b, base_body)

OperationType("Basic housing milling", 8, 8, 0.15, basic, milling_tool, base_body, milled_body)
OperationType("Precision housing milling", 5, 5, 0.10, precision, precision_tool, base_body, milled_body)
OperationType("Direct housing from blank B", 12, 9, 0.20, basic, rough_tool, blank_b, milled_body)

OperationType("Basic bracket drilling", 9, 6, 0.14, basic, drill_tool, base_body, drilled_body)
OperationType("Specialist bracket drilling", 4, 4, 0.08, drilling, drill_tool, base_body, drilled_body)

OperationType("Housing finishing", 6, 4, 0.10, finishing, polishing_tool, milled_body, finished_housing)
OperationType("Bracket finishing", 4, 3, 0.10, finishing, polishing_tool, drilled_body, finished_bracket)
OperationType("Precision bracket finishing", 7, 2, 0.06, precision, precision_tool, drilled_body, finished_bracket)
OperationType("Base body polishing", 8, 4, 0.10, finishing, polishing_tool, base_body, polished_part)

scenario = Scenario("Mixed production - 24 jobs")

# Orders overlap: each row creates three jobs with a common release and deadline.
Order("Housing batch A", 3, 0, 60, finished_housing, scenario)
Order("Bracket batch A", 3, 6, 90, finished_bracket, scenario)
Order("Polished batch A", 3, 12, 110, polished_part, scenario)
Order("Housing batch B", 3, 18, 130, finished_housing, scenario)
Order("Bracket batch B", 3, 24, 150, finished_bracket, scenario)
Order("Polished batch B", 3, 30, 170, polished_part, scenario)
Order("Housing batch C", 3, 36, 200, finished_housing, scenario)
Order("Bracket batch C", 3, 42, 230, finished_bracket, scenario)

layout = Layout("Mixed production - three corridors", 3, 2, 500)

near = Corridor("Near corridor", 6, 2, 3, layout)
middle = Corridor("Middle corridor", 4, 4, 2, layout)
far = Corridor("Far corridor", 8, 6, 4, layout)

# Each corridor has all four machine types, but different buffer capacities
# and machine positions. Input and output capacities are job counts.
Machine("Near basic", basic, near, True, 2, 2)
Machine("Near precision", precision, near, True, 3, 2)
Machine("Near drill", drilling, near, False, 2, 2)
Machine("Near finishing", finishing, near, False, 2, 2)

Machine("Middle basic", basic, middle, True, 3, 2)
Machine("Middle drill", drilling, middle, True, 2, 2)
Machine("Middle precision", precision, middle, False, 2, 2)
Machine("Middle finishing", finishing, middle, False, 3, 2)

Machine("Far precision", precision, far, True, 4, 2)
Machine("Far finishing", finishing, far, True, 3, 2)
Machine("Far basic", basic, far, False, 4, 2)
Machine("Far drill", drilling, far, False, 3, 2)


if __name__ == "__main__":
    simulate(layout, scenario, till=sim.inf, animation_speed=5)
