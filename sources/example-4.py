from SpineML import *

# Layout parameters

NUM_CORRIDORS = 8

NUM_MACHINES_LEFT = 4
NUM_MACHINES_RIGHT = 4

# Create machine types (name)

mt1 = MachineType('Machine type 1')

# Create tool types (name, mount time, unmount time, total life units)

tt1 = ToolType('Tool type 1', 2, 3, 10)
tt2 = ToolType('Tool type 2', 1, 2, 9)

# Create product types (name, length, width, depth, weight)

pt1 = ProductType('Product type 1', 12, 12, 12, 5)
pt2 = ProductType('Product type 2', 12, 24, 11, 10)
pt3 = ProductType('Product type 3', 14, 15, 15, 6)

# Create operation types (name, duration, consumed life units, defect probability, machine type, tool type, consumed product type, produced product type)

o1 = OperationType('Operation 1', 1, 5, 0.15, mt1, tt1, pt1, pt2)
o2 = OperationType('Operation 2', 1, 4, 0.20, mt1, tt2, pt1, pt3)

# Create scenarios (name)

scenario1 = Scenario('Scenario 1')

# Create orders (name, quantity, earliest start time, latest end time, product type, scenario)

o1_1 = Order("Order 1.1", 10, 11, 20, pt2, scenario1)
o1_2 = Order("Order 1.2", 10, 11, 20, pt3, scenario1)

# Create layouts (name, storage out time, storage in time)

l1 = Layout('Layout 1', 10, 5)

# Create corridors (name, storage capacity, storage out time, storage in time, layout)

for i in range(NUM_CORRIDORS):
    Corridor(f"Corridor {i + 1}", 200, 2, 3, l1)

# Create machines (name, machine type, corridor, left)

for i in range(NUM_CORRIDORS):
    for j in range(NUM_MACHINES_LEFT):
        Machine(f'Machine 1.{i + 1}.{j + 1}.left', mt1, CORRIDORS[i], True)
    for j in range(NUM_MACHINES_RIGHT):
        Machine(f'Machine 1.{i + 1}.{j + 1}.right', mt1, CORRIDORS[i], False)

# Visualize

visualizeRoute(l1, o1_1)

# Simulate

simulate(l1, scenario1, True)
