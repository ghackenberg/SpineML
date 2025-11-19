from SpineML import *

# Create machine types (name)

mt1 = MachineType('Machine type 1')
mt2 = MachineType('Machine type 2')
mt3 = MachineType('Machine type 3')

# Create tool types (name, mount time, unmount time, total life units)

tt1 = ToolType('Tool type 1', 2, 3, 10)
tt2 = ToolType('Tool type 2', 1, 2, 9)
tt3 = ToolType('Tool type 3', 3, 4, 12)

# Create product types (name, length, width, depth, weight)

pt1 = ProductType('Product type 1', 12, 12, 12, 5)
pt2 = ProductType('Product type 2', 12, 24, 11, 10)
pt3 = ProductType('Product type 3', 14, 15, 15, 6)
pt4 = ProductType('Product type 4', 22, 23, 12, 7)
pt5 = ProductType('Product type 5', 22, 23, 12, 7)
pt6 = ProductType('Product type 6', 12, 24, 11, 10)

# Create operation types (name, duration, consumed life units, defect probability, machine type, tool type, consumed product type, produced product type)

OperationType('Operation 1', 1, 4, 0.15, mt1, tt1, pt1, pt2)
OperationType('Operation 2', 1, 3, 0.20, mt1, tt2, pt3, pt2)
OperationType('Operation 3', 1, 5, 0.11, mt2, tt3, pt2, pt4)
OperationType('Operation 4', 1, 6, 0.11, mt2, tt2, pt2, pt5)
OperationType('Operation 5', 1, 2, 0.11, mt3, tt1, pt2, pt6)

# Create scenarios (name)

s1 = Scenario('Scenario 1')
s2 = Scenario('Scenario 2')
s3 = Scenario('Scenario 3')

# Create orders (name, quantity, earliest start time, latest end time, product type, scenario)

# ... scenario 1
o1_1 = Order("Order 1.1", 30, 11, 20, pt6, s1)
o1_2 = Order("Order 1.2", 40, 15, 30, pt2, s1)
# ... scenario 2
o2_1 = Order("Order 2.1", 400, 25, 30, pt2, s2)
# ... scenario 3
o3_1 = Order("Order 3.1", 500, 15, 20, pt4, s3)
o3_2 = Order("Order 3.2", 300, 25, 30, pt5, s3)

# Create layouts (name, storage out time, storage in time)

l1 = Layout('Layout 1', 10, 5)
l2 = Layout('Layout 2', 11, 3)
l3 = Layout('Layout 3', 11, 3)

# Create corridors (name, storage capacity, storage out time, storage in time, layout)

# ... layout 1
c1_1 = Corridor("Corridor 1.1", 500, 2, 3, l1)
c1_2 = Corridor("Corridor 1.2", 350, 2, 3, l1)
c1_3 = Corridor("Corridor 1.3", 200, 2, 3, l1)
# ... layout 2
c2_1 = Corridor("Corridor 2.1", 150, 2, 3, l2)
c2_2 = Corridor("Corridor 2.2", 150, 2, 3, l2)
# ... layout 3
c3_1 = Corridor("Corridor 3.1", 350, 2, 3, l3)
c3_2 = Corridor("Corridor 3.2", 120, 2, 3, l3)
c3_3 = Corridor("Corridor 3.3", 150, 2, 3, l3)
c3_4 = Corridor("Corridor 3.4", 300, 2, 3, l3)

# Create machines (name, machine type, corridor, left)

# ... layout 1 / corridor 1
Machine('Machine 1.1.1', mt1, c1_1, True)
Machine('Machine 1.1.2', mt1, c1_1, False)
# ... layout 1 / corridor 2
Machine('Machine 1.2.1', mt2, c1_2, True)
Machine('Machine 1.2.2', mt3, c1_2, False)
# ... layout 1 / corridor 3
Machine('Machine 1.3.1', mt1, c1_3, True)
Machine('Machine 1.3.2', mt1, c1_3, False)

# ... layout 2 / corridor 1
Machine('Machine 2.1.1', mt1, c2_1, True)
Machine('Machine 2.1.2', mt1, c2_1, True)
Machine('Machine 2.1.3', mt3, c2_1, True)
Machine('Machine 2.1.4', mt2, c2_1, False)
# ... layout 2 / corridor 2
Machine('Machine 2.2.1', mt1, c2_2, True)

# ... layout 3 / corridor 1
Machine('Machine 3.1.1', mt1, c3_1, True)
Machine('Machine 3.1.2', mt1, c3_1, True)
Machine('Machine 3.1.3', mt1, c3_1, False)
# ... layout 3 / corridor 2
Machine('Machine 3.2.1', mt3, c3_2, True)
Machine('Machine 3.2.2', mt2, c3_2, False)
Machine('Machine 3.2.3', mt2, c3_2, False)
# ... layout 3 / corridor 3
# ... layout 3 / corridor 4
Machine('Machine 3.4.1', mt3, c3_4, True)

# Visualize

visualizeRoute(l1, o1_1)

# Simulate

simulate(l1, s1)
