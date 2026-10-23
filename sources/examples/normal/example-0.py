from SpineML import *


mt1 = MachineType('PolishingMachine')
mt2 = MachineType('GrindingMachine')
mt3 = MachineType('MillingMachine')


tt1 = ToolType('PolishingTool', 2, 3, 25)
tt2 = ToolType('GrindingTool', 1, 2, 25)
tt3 = ToolType('MillingTool', 2, 2, 25)
tt4 = ToolType('FinePolishingTool', 2, 3, 30)
tt5 = ToolType('CoarsePolishingTool', 3, 3, 35)
tt6 = ToolType('SoftPolishingTool', 1, 2, 20)
tt7 = ToolType('HardPolishingTool', 3, 4, 40)


pt1 = ProductType('RawWorkpiece', 12, 12, 12, 100)
pt2 = ProductType('PolishedWorkpiece', 12, 24, 11, 10)
pt3 = ProductType('GroundWorkpiece', 14, 15, 15, 6)
pt4 = ProductType('MilledWorkpiece', 13, 16, 14, 7)
pt5 = ProductType('MilledAndGroundWorkpiece', 13, 18, 13, 8)
pt6 = ProductType('PolishingStage1', 13, 18, 13, 8)
pt7 = ProductType('PolishingStage2', 13, 18, 13, 8)
pt8 = ProductType('PolishingStage3', 13, 18, 13, 8)
pt9 = ProductType('PolishingStage4', 13, 18, 13, 8)


OperationType('PrePolishRawWorkpiece', 1, 3, mt1, tt1, pt1, pt6)

OperationType('GrindRawWorkpiece', 1, 10, mt2, tt2, pt1, pt3)
OperationType('PrePolishGroundWorkpiece', 1, 3, mt1, tt1, pt3, pt6)

OperationType('MillRawWorkpiece', 1, 10, mt3, tt3, pt1, pt4)
OperationType('GrindMilledWorkpiece', 1, 10, mt2, tt2, pt4, pt5)
OperationType('PrePolishMilledAndGroundWorkpiece', 1, 3, mt1, tt1, pt5, pt6)

OperationType('PolishingStage1Fine', 1, 4, mt1, tt4, pt6, pt7)
OperationType('PolishingStage2Coarse', 1, 5, mt1, tt5, pt7, pt8)
OperationType('PolishingStage3Soft', 1, 4, mt1, tt6, pt8, pt9)
OperationType('PolishingStage4Hard', 1, 5, mt1, tt7, pt9, pt2)


s1 = Scenario('ExampleScenarioWithThreeProductionRoutes')


o1_1 = Order("OrderPolishedWorkpiece", 2, 11, 90, pt2, s1)


l1 = Layout('ExampleLayout', 10, 5, 1000)


c1_1 = Corridor("MachiningCorridor", 200, 2, 3, l1)


Machine(
    'PolishingMachine A',
    mt1,
    c1_1,
    True,
    10,
    10,
    tool_types=[tt1, tt4, tt5, tt6, tt7],
    defect_probability=0.05,
)
Machine('PolishingMachine B', mt1, c1_1, False, 10, 10, tool_types=[tt1], defect_probability=0.05)
Machine('GrindingMachine A', mt2, c1_1, True, 10, 10, defect_probability=0.20)
Machine('GrindingMachine B', mt2, c1_1, False, 10, 10, defect_probability=0.10)
Machine('MillingMachine A', mt3, c1_1, True, 10, 10, defect_probability=0.10)
Machine('MillingMachine B', mt3, c1_1, False, 10, 10, defect_probability=0.10)


simulate(l1, s1, True)
