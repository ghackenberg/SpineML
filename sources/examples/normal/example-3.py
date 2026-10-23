import salabim as sim

from SpineML import *

mt1 = MachineType('BasicMachiningCenter')
mt2 = MachineType('PrecisionMachiningCenter')
mt3 = MachineType('PolishingCenter')


tt1 = ToolType('MillingTool', 2, 3, 10)
tt2 = ToolType('DrillingTool', 1, 2, 9)
tt3 = ToolType('PrecisionTool', 3, 4, 12)

pt1 = ProductType('BlankTypeA', 12, 12, 12, 5)
pt2 = ProductType('MachinedBaseBody', 12, 24, 11, 10)
pt3 = ProductType('BlankTypeB', 14, 15, 15, 6)
pt4 = ProductType('MilledHousing', 22, 23, 12, 7)
pt5 = ProductType('DrilledHousing', 22, 23, 12, 7)
pt6 = ProductType('PolishedFinishedPart', 12, 24, 11, 10)

OperationType('BasicMachiningBlankA', 2, 4, mt1, tt1, pt1, pt2)
OperationType('BasicMachiningBlankB', 4, 3, mt1, tt2, pt3, pt2)
OperationType('PrecisionMilling', 7, 5, mt2, tt3, pt2, pt4)
OperationType('PrecisionDrilling', 3, 6, mt2, tt2, pt2, pt5)
OperationType('FinalPolishing', 9, 2, mt3, tt1, pt2, pt6)

s3 = Scenario('Shift 3 - HousingProduction')

o3_1 = Order("HousingBatchA - Milling", 2, 15, 650, pt4, s3)
o3_2 = Order("HousingBatchB - Drilling", 2, 25, 680, pt5, s3)
o3_3 = Order("FinishedPartBatchC - Polishing", 2, 11, 620, pt6, s3)
o3_4 = Order("BaseBodyBatchD", 2, 19, 670, pt2, s3)

l3 = Layout('Layout 3', 11, 3, 1000)

c3_1 = Corridor("Corridor 3.1", 2, 3, 6, l3)
c3_2 = Corridor("Corridor 3.2", 2, 7, 9, l3)

Machine('Machine 3.1.1', mt1, c3_1, True, 10, 10, defect_probability=0.50)
Machine('Machine 3.1.2', mt2, c3_1, False, 8, 8, defect_probability=0.45)
Machine('Machine 3.1.3', mt3, c3_1, True, 7, 7, defect_probability=0.48)
Machine('Machine 3.1.4', mt1, c3_1, False, 7, 7, defect_probability=0.55)
Machine('Machine 3.2.1', mt1, c3_2, True, 10, 10, defect_probability=0.50)
Machine('Machine 3.2.2', mt2, c3_2, False, 10, 10, defect_probability=0.50)
Machine('Machine 3.2.3', mt3, c3_2, True, 7, 7, defect_probability=0.48)
Machine('Machine 3.2.4', mt2, c3_2, False, 7, 7, defect_probability=0.45)

if __name__ == "__main__":
    simulate(l3, s3, till=sim.inf, animation_speed=5)
