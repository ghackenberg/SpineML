from SpineML import *


mt1 = MachineType('Poliermaschine')
mt2 = MachineType('Schleifmaschine')
mt3 = MachineType('Fräsmaschine')


tt1 = ToolType('Polierwerkzeug', 2, 3, 25)
tt2 = ToolType('Schleifwerkzeug', 1, 2, 25)
tt3 = ToolType('Fräswerkzeug', 2, 2, 25)
tt4 = ToolType('Polierwerkzeug fein', 2, 3, 30)
tt5 = ToolType('Polierwerkzeug grob', 3, 3, 35)
tt6 = ToolType('Polierwerkzeug weich', 1, 2, 20)
tt7 = ToolType('Polierwerkzeug hart', 3, 4, 40)


pt1 = ProductType('Rohes Werkstück', 12, 12, 12, 100)
pt2 = ProductType('Poliertes Werkstück', 12, 24, 11, 10)
pt3 = ProductType('Geschliffenes Werkstück', 14, 15, 15, 6)
pt4 = ProductType('Gefrästes Werkstück', 13, 16, 14, 7)
pt5 = ProductType('Gefrästes und geschliffenes Werkstück', 13, 18, 13, 8)
pt6 = ProductType('Polierstufe 1', 13, 18, 13, 8)
pt7 = ProductType('Polierstufe 2', 13, 18, 13, 8)
pt8 = ProductType('Polierstufe 3', 13, 18, 13, 8)
pt9 = ProductType('Polierstufe 4', 13, 18, 13, 8)


OperationType('Rohes Werkstück vorpolieren', 1, 3, 0.05, mt1, tt1, pt1, pt6)

OperationType('Rohes Werkstück schleifen', 1, 10, 0.20, mt2, tt2, pt1, pt3)
OperationType('Geschliffenes Werkstück vorpolieren', 1, 3, 0.05, mt1, tt1, pt3, pt6)

OperationType('Rohes Werkstück fräsen', 1, 10, 0.10, mt3, tt3, pt1, pt4)
OperationType('Gefrästes Werkstück schleifen', 1, 10, 0.10, mt2, tt2, pt4, pt5)
OperationType('Gefrästes und geschliffenes Werkstück vorpolieren', 1, 3, 0.05, mt1, tt1, pt5, pt6)

OperationType('Polierstufe 1 feinpolieren', 1, 4, 0.05, mt1, tt4, pt6, pt7)
OperationType('Polierstufe 2 grobpolieren', 1, 5, 0.05, mt1, tt5, pt7, pt8)
OperationType('Polierstufe 3 weichpolieren', 1, 4, 0.05, mt1, tt6, pt8, pt9)
OperationType('Polierstufe 4 hartpolieren', 1, 5, 0.05, mt1, tt7, pt9, pt2)


s1 = Scenario('Beispielszenario mit drei Produktionswegen')


o1_1 = Order("Auftrag poliertes Werkstück", 2, 11, 90, pt2, s1)


l1 = Layout('Beispiellayout', 10, 5, 1000)


c1_1 = Corridor("Bearbeitungskorridor", 200, 2, 3, l1)


Machine(
    'Poliermaschine A',
    mt1,
    c1_1,
    True,
    10,
    10,
    tool_types=[tt1, tt4, tt5, tt6, tt7],
)
Machine('Poliermaschine B', mt1, c1_1, False, 10, 10, tool_types=[tt1])
Machine('Schleifmaschine A', mt2, c1_1, True, 10, 10)
Machine('Schleifmaschine B', mt2, c1_1, False, 10, 10)
Machine('Fräsmaschine A', mt3, c1_1, True, 10, 10)
Machine('Fräsmaschine B', mt3, c1_1, False, 10, 10)


simulate(l1, s1, True)
