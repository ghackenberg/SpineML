import salabim as sim

from SpineML import *

mt1 = MachineType('Grundbearbeitungszentrum')
mt2 = MachineType('Praezisionsbearbeitungszentrum')
mt3 = MachineType('Polierzentrum')


tt1 = ToolType('Fräswerkzeug', 2, 3, 10)
tt2 = ToolType('Bohrwerkzeug', 1, 2, 9)
tt3 = ToolType('Praezisionswerkzeug', 3, 4, 12)

pt1 = ProductType('Rohling Typ A', 12, 12, 12, 5)
pt2 = ProductType('Bearbeiteter Grundkoerper', 12, 24, 11, 10)
pt3 = ProductType('Rohling Typ B', 14, 15, 15, 6)
pt4 = ProductType('Gefraestes Gehaeuse', 22, 23, 12, 7)
pt5 = ProductType('Bohrbearbeitetes Gehaeuse', 22, 23, 12, 7)
pt6 = ProductType('Poliertes Fertigteil', 12, 24, 11, 10)

OperationType('Grundbearbeitung Rohling A', 2, 4, 0.50, mt1, tt1, pt1, pt2)
OperationType('Grundbearbeitung Rohling B', 4, 3, 0.55, mt1, tt2, pt3, pt2)
OperationType('Praezisionsfraesen', 7, 5, 0.45, mt2, tt3, pt2, pt4)
OperationType('Praezisionsbohren', 3, 6, 0.50, mt2, tt2, pt2, pt5)
OperationType('Endpolitur', 9, 2, 0.48, mt3, tt1, pt2, pt6)

s3 = Scenario('Schicht 3 – Gehaeusefertigung')

o3_1 = Order("Gehaeuse Los A – Fraesen", 2, 15, 650, pt4, s3)
o3_2 = Order("Gehaeuse Los B – Bohren", 2, 25, 680, pt5, s3)
o3_3 = Order("Fertigteil Los C – Polieren", 2, 11, 620, pt6, s3)
o3_4 = Order("Grundkoerper Los D", 2, 19, 670, pt2, s3)

l3 = Layout('Layout 3', 11, 3, 1000)

c3_1 = Corridor("Corridor 3.1", 2, 3, 6, l3)
c3_2 = Corridor("Corridor 3.2", 2, 7, 9, l3)

Machine('Machine 3.1.1', mt1, c3_1, True, 10, 10)
Machine('Machine 3.1.2', mt2, c3_1, False, 8, 8)
Machine('Machine 3.1.3', mt3, c3_1, True, 7, 7)
Machine('Machine 3.1.4', mt1, c3_1, False, 7, 7)
Machine('Machine 3.2.1', mt1, c3_2, True, 10, 10)
Machine('Machine 3.2.2', mt2, c3_2, False, 10, 10)
Machine('Machine 3.2.3', mt3, c3_2, True, 7, 7)
Machine('Machine 3.2.4', mt2, c3_2, False, 7, 7)

if __name__ == "__main__":
    simulate(l3, s3, till=sim.inf, animation_speed=5)
