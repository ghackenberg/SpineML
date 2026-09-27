from SpineML import *


mt1 = MachineType('Machine type 1')
mt2 = MachineType('Machine type 2')
mt3 = MachineType('Machine type 3')


tt1 = ToolType('Tool type 1', 2, 3, 10)
tt2 = ToolType('Tool type 2', 1, 2, 9)
tt3 = ToolType('Tool type 3', 3, 4, 12)


pt1 = ProductType('Product type 1', 12, 12, 12, 5)
pt2 = ProductType('Product type 2', 12, 24, 11, 10)
pt3 = ProductType('Product type 3', 14, 15, 15, 6)
pt4 = ProductType('Product type 4', 33, 12, 22, 17)


OperationType('Operation 1', 1, 5, 0.15,mt1, tt1, pt1, pt2)
OperationType('Operation 2', 1, 4, 0.20, mt2, tt2, pt4, pt1)
OperationType('Operation 3', 1, 6, 0.11, mt3, tt3, pt3, pt4)


s1 = Scenario('Scenario 1')
s2 = Scenario('Scenario 2')


o1_1 = Order("Order 1.1", 10, 11, 20, pt1, s1)
o2_1 = Order("Order 2.1", 500, 25, 26, pt2, s2)
o2_2 = Order("Order 2.2", 400, 14, 16, pt2, s2)


l1 = Layout('Layout 1', 10, 5, 1000)
l2 = Layout('Layout 2', 11, 7, 1000)
l3 = Layout('Layout 3', 11, 3, 1000)


c1_1 = Corridor("Corridor 1.1", 200, 3, 4, l1)
c1_2 = Corridor("Corridor 1.2", 150, 1, 2, l1)
c2_1 = Corridor("Corridor 2.1", 300, 2, 3, l2)
c2_2 = Corridor("Corridor 2.2", 200, 1, 1, l2)
c3_1 = Corridor("Corridor 3.1", 200, 1, 1, l3)
c3_2 = Corridor("Corridor 3.2", 300, 1, 1, l3)
c3_3 = Corridor("Corridor 3.3", 200, 1, 1, l3)


Machine('Machine 1.1.1', mt3, c1_1, True, 10, 10)
Machine('Machine 1.1.2', mt2, c1_1, True, 10, 10)
Machine('Machine 1.1.3', mt1, c1_1, False, 10, 10)
Machine('Machine 1.2.1', mt3, c1_2, True, 10, 10)
Machine('Machine 1.2.2', mt2, c1_2, True, 10, 10)
Machine('Machine 1.2.3', mt1, c1_2, False, 10, 10)

Machine('Machine 2.1.1', mt3, c2_1, True, 10, 10)
Machine('Machine 2.1.2', mt2, c2_1, True, 10, 10)
Machine('Machine 2.2.1', mt1, c2_2, True, 10, 10)

Machine('Machine 3.1.1', mt1, c3_1, True, 10, 10)
Machine('Machine 3.2.1', mt3, c3_2, True, 10, 10)
Machine('Machine 3.3.1', mt2, c3_3, True, 10, 10)


simulate(l1, s1)
