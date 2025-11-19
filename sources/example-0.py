from SpineML import *

# Create machine types (name)

mt1 = MachineType('Machine type 1')
mt2 = MachineType('Machine type 2')

# Create tool types (name, mount time, unmount time, total life units)

tt1 = ToolType('Tool type 1', 2, 3, 25)
tt2 = ToolType('Tool type 2', 1, 2, 25)

# Create product types (name, length, width, depth, weight)

pt1 = ProductType('Product Type 1', 12, 12, 12, 5)
pt2 = ProductType('Product Type 2', 12, 24, 11, 10)
pt3 = ProductType('Product Type 3', 14, 15, 15, 6)

# Create operation types (name, duration, consumed life units, defect probability, machine type, tool type, consumed product type, produced product type)

OperationType('Operation 1', 1, 10, 0.15, mt1, tt1, pt1, pt2)
OperationType('Operation 2', 1, 10, 0.20, mt2, tt2, pt1, pt3)

# Create scenarios (name)

s1 = Scenario('Scenario 1')

# Create orders (name, quantity, earliest start time, latest end time, product type, scenario)

o1_1 = Order("Order 1.1", 5, 11, 20, pt2, s1)
o1_2 = Order("Order 1.2", 5, 11, 20, pt3, s1)

# Create layouts (name, storage out time, storage in time)

l1 = Layout('Layout 1', 10, 5)

# Create corridors (name, storage capacity, storage out time, storage in time, layout)

c1_1 = Corridor("Corridor 1.1", 200, 2, 3, l1)

# Create machines (name, machine type, corridor, left)

Machine('Machine 1.1.1', mt1, c1_1, True)
Machine('Machine 1.1.2', mt2, c1_1, False)

# Visualize

visualizeRoute(l1, o1_1)

# Simulate

simulate(l1, s1, True)
