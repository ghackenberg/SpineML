

import salabim as sim  # Importiert Salabim; sim.inf bezeichnet ein unbegrenztes Zeitlimit.

from SpineML import (  # Importiert die Modellklassen und den Simulationsstart aus SpineML.
    Corridor,  # Beschreibt einen Seitenkorridor mit Puffern und Maschinen.
    Layout,  # Beschreibt den Fabrikaufbau mit Lagern und Korridoren.
    Machine,  # Beschreibt eine konkrete Maschine mit Position und Pufferkapazitäten.
    MachineType,  # Gruppiert Maschinen, die dieselben Operationstypen ausführen können.
    OperationType,  # Beschreibt eine Bearbeitung vom Eingangsprodukt zum Ausgangsprodukt.
    Order,  # Beschreibt einen Auftrag mit Menge, frühestem Start und Deadline.
    ProductType,  # Beschreibt Rohmaterial, Zwischenprodukte und Endprodukte.
    Scenario,  # Fasst die zu simulierenden Produktionsaufträge zusammen.
    ToolType,  # Beschreibt ein Werkzeug mit Wechselzeiten und Lebensdauer.
    simulate,  # Startet die Simulation eines Layouts und eines Szenarios.
)  # Beendet den mehrzeiligen Import.


# Maschinentyp für die Grundbearbeitung.
basic = MachineType("Basic machining")
# Maschinentyp für die Präzisionsbearbeitung.
precision = MachineType("Precision machining")
# Maschinentyp für das Bohren.
drilling = MachineType("Drilling")
# Maschinentyp für die Endbearbeitung.
finishing = MachineType("Finishing")

# Schruppwerkzeug: Montagezeit 3, Demontagezeit 2, Lebensdauer 48 Einheiten.
rough_tool = ToolType("Roughing tool", 3, 2, 48)


# Fräswerkzeug: Montagezeit 2, Demontagezeit 2, Lebensdauer 32 Einheiten.
milling_tool = ToolType("Milling tool", 2, 2, 32)


# Präzisionswerkzeug: Montagezeit 3, Demontagezeit 3, Lebensdauer 36 Einheiten.
precision_tool = ToolType("Precision tool", 3, 3, 36)


# Bohrwerkzeug: Montagezeit 1, Demontagezeit 2, Lebensdauer 28 Einheiten.
drill_tool = ToolType("Drill tool", 1, 2, 28)


# Polierwerkzeug: Montagezeit 2, Demontagezeit 2, Lebensdauer 40 Einheiten.
polishing_tool = ToolType("Polishing tool", 2, 2, 40)


# Rohteil A: Länge 12, Breite 12, Tiefe 12, Gewicht 5.
blank_a = ProductType("Blank A", 12, 12, 12, 5)
# Rohteil B: Länge 14, Breite 14, Tiefe 12, Gewicht 6.
blank_b = ProductType("Blank B", 14, 14, 12, 6)
# Grundkörper: Länge 16, Breite 16, Tiefe 12, Gewicht 6.
base_body = ProductType("Base body", 16, 16, 12, 6)
# Gefräster Körper: Länge 18, Breite 16, Tiefe 12, Gewicht 7.
milled_body = ProductType("Milled body", 18, 16, 12, 7)
# Gebohrter Körper: Länge 16, Breite 18, Tiefe 12, Gewicht 7.
drilled_body = ProductType("Drilled body", 16, 18, 12, 7)
# Fertiges Gehäuse: Länge 18, Breite 16, Tiefe 12, Gewicht 7.
finished_housing = ProductType("Finished housing", 18, 16, 12, 7)
# Fertiger Halter: Länge 16, Breite 18, Tiefe 12, Gewicht 7.
finished_bracket = ProductType("Finished bracket", 16, 18, 12, 7)
# Poliertes Teil: Länge 16, Breite 16, Tiefe 12, Gewicht 6.
polished_part = ProductType("Polished part", 16, 16, 12, 6)

# Die Bearbeitungswege unterscheiden sich in Dauer und Werkzeugverbrauch.
# Die Defektwahrscheinlichkeit wird unten je Maschine festgelegt, nicht je Operation.


# Rohteil A -> Schruppen mit Schruppwerkzeug -> Grundkörper; Dauer 3, Werkzeugverbrauch 8.
OperationType("Rough blank A", 3, 8, basic, rough_tool, blank_a, base_body)
# Rohteil A -> Präzisionsbearbeitung mit Präzisionswerkzeug -> Grundkörper; Dauer 7, Werkzeugverbrauch 4.
OperationType("Precision blank A", 7, 4, precision, precision_tool, blank_a, base_body)
# Rohteil B -> Schruppen mit Fräswerkzeug -> Grundkörper; Dauer 5, Werkzeugverbrauch 6.
OperationType("Rough blank B", 5, 6, basic, milling_tool, blank_b, base_body)

# Grundkörper -> Fräsen mit Fräswerkzeug -> Gefräster Körper; Dauer 8, Werkzeugverbrauch 8.
OperationType("Basic housing milling", 8, 8, basic, milling_tool, base_body, milled_body)
# Grundkörper -> Präzisionsfräsen mit Präzisionswerkzeug -> Gefräster Körper; Dauer 5, Werkzeugverbrauch 5.
OperationType("Precision housing milling", 5, 5, precision, precision_tool, base_body, milled_body)
# Rohteil B -> Direktbearbeitung mit Schruppwerkzeug -> Gefräster Körper; Dauer 12, Werkzeugverbrauch 9.
OperationType("Direct housing from blank B", 12, 9, basic, rough_tool, blank_b, milled_body)

# Grundkörper -> Bohren mit Bohrwerkzeug -> Gebohrter Körper; Dauer 9, Werkzeugverbrauch 6.
OperationType("Basic bracket drilling", 9, 6, basic, drill_tool, base_body, drilled_body)
# Grundkörper -> Bohren mit Bohrwerkzeug -> Gebohrter Körper; Dauer 4, Werkzeugverbrauch 4.
OperationType("Specialist bracket drilling", 4, 4, drilling, drill_tool, base_body, drilled_body)

# Gefräster Körper -> Endbearbeitung mit Polierwerkzeug -> Fertiges Gehäuse; Dauer 6, Werkzeugverbrauch 4.
OperationType("Housing finishing", 6, 4, finishing, polishing_tool, milled_body, finished_housing)
# Gebohrter Körper -> Endbearbeitung mit Polierwerkzeug -> Fertiger Halter; Dauer 4, Werkzeugverbrauch 3.
OperationType("Bracket finishing", 4, 3, finishing, polishing_tool, drilled_body, finished_bracket)
# Gebohrter Körper -> Präzisions-Endbearbeitung mit Präzisionswerkzeug -> Fertiger Halter; Dauer 7, Werkzeugverbrauch 2.
OperationType("Precision bracket finishing", 7, 2, precision, precision_tool, drilled_body, finished_bracket)
# Grundkörper -> Polieren mit Polierwerkzeug -> Poliertes Teil; Dauer 8, Werkzeugverbrauch 4.
OperationType("Base body polishing", 8, 4, finishing, polishing_tool, base_body, polished_part)

# Legt das Szenario für die folgenden acht Aufträge mit insgesamt 24 Jobs an.
scenario = Scenario("Mixed production - 24 jobs")

# Jeder Auftrag enthält drei Jobs mit gemeinsamem frühestem Start und gemeinsamer Deadline.
# Drei fertige Gehäuse: frühester Start 0, Deadline 60.
Order("Housing batch A", 3, 0, 60, finished_housing, scenario)
# Drei fertige Halter: frühester Start 6, Deadline 90.
Order("Bracket batch A", 3, 6, 90, finished_bracket, scenario)
# Drei polierte Teile: frühester Start 12, Deadline 110.
Order("Polished batch A", 3, 12, 110, polished_part, scenario)
# Drei weitere fertige Gehäuse: frühester Start 18, Deadline 130.
Order("Housing batch B", 3, 18, 130, finished_housing, scenario)
# Drei weitere fertige Halter: frühester Start 24, Deadline 150.
Order("Bracket batch B", 3, 24, 150, finished_bracket, scenario)
# Drei weitere polierte Teile: frühester Start 30, Deadline 170.
Order("Polished batch B", 3, 30, 170, polished_part, scenario)
# Drei weitere fertige Gehäuse: frühester Start 36, Deadline 200.
Order("Housing batch C", 3, 36, 200, finished_housing, scenario)
# Drei weitere fertige Halter: frühester Start 42, Deadline 230.
Order("Bracket batch C", 3, 42, 230, finished_bracket, scenario)

# Fabriklayout: Auslagerzeit 3, Einlagerzeit 2 und Lagerkapazität 500 Jobs.
layout = Layout("Mixed production - three corridors", 3, 2, 500)

# Naher Seitenkorridor: Pufferkapazität 6, Auslagerzeit 2, Einlagerzeit 3.
near = Corridor("Near corridor", 6, 2, 3, layout)
# Mittlerer Seitenkorridor: Pufferkapazität 4, Auslagerzeit 4, Einlagerzeit 2.
middle = Corridor("Middle corridor", 4, 4, 2, layout)
# Entfernter Seitenkorridor: Pufferkapazität 8, Auslagerzeit 6, Einlagerzeit 4.
far = Corridor("Far corridor", 8, 6, 4, layout)

# Jeder Korridor enthält alle vier Maschinentypen; True bedeutet links, False rechts.
# Die Eingangs- und Ausgangspufferkapazitäten geben jeweils die Anzahl der Jobs an.
# Die zugelassenen Werkzeugtypen werden für jede Maschine ausdrücklich angegeben.
# Nahe Grundbearbeitungsmaschine links: Eingang 2, Ausgang 2, Defektwahrscheinlichkeit 18 %.
Machine("Near basic", basic, near, True, 2, 2, tool_types=[rough_tool, milling_tool, drill_tool], defect_probability=0.18)
# Nahe Präzisionsmaschine links: Eingang 3, Ausgang 2, Defektwahrscheinlichkeit 10 %.
Machine("Near precision", precision, near, True, 3, 2, tool_types=[precision_tool], defect_probability=0.10)
# Nahe Bohrmaschine rechts: Eingang 2, Ausgang 2, Defektwahrscheinlichkeit 8 %.
Machine("Near drill", drilling, near, False, 2, 2, tool_types=[drill_tool], defect_probability=0.08)
# Nahe Endbearbeitungsmaschine rechts: Eingang 2, Ausgang 2, Defektwahrscheinlichkeit 10 %.
Machine("Near finishing", finishing, near, False, 2, 2, tool_types=[polishing_tool], defect_probability=0.10)

# Mittlere Grundbearbeitungsmaschine links: Eingang 3, Ausgang 2, Defektwahrscheinlichkeit 14 %.
Machine("Middle basic", basic, middle, True, 3, 2, tool_types=[rough_tool, milling_tool, drill_tool], defect_probability=0.14)
# Mittlere Bohrmaschine links: Eingang 2, Ausgang 2, Defektwahrscheinlichkeit 6 %.
Machine("Middle drill", drilling, middle, True, 2, 2, tool_types=[drill_tool], defect_probability=0.06)
# Mittlere Präzisionsmaschine rechts: Eingang 2, Ausgang 2, Defektwahrscheinlichkeit 6 %.
Machine("Middle precision", precision, middle, False, 2, 2, tool_types=[precision_tool], defect_probability=0.06)
# Mittlere Endbearbeitungsmaschine rechts: Eingang 3, Ausgang 2, Defektwahrscheinlichkeit 8 %.
Machine("Middle finishing", finishing, middle, False, 3, 2, tool_types=[polishing_tool], defect_probability=0.08)

# Entfernte Präzisionsmaschine links: Eingang 4, Ausgang 2, Defektwahrscheinlichkeit 4 %.
Machine("Far precision", precision, far, True, 4, 2, tool_types=[precision_tool], defect_probability=0.04)
# Entfernte Endbearbeitungsmaschine links: Eingang 3, Ausgang 2, Defektwahrscheinlichkeit 5 %.
Machine("Far finishing", finishing, far, True, 3, 2, tool_types=[polishing_tool], defect_probability=0.05)
# Entfernte Grundbearbeitungsmaschine rechts: Eingang 4, Ausgang 2, Defektwahrscheinlichkeit 8 %.
Machine("Far basic", basic, far, False, 4, 2, tool_types=[rough_tool, milling_tool, drill_tool], defect_probability=0.08)
# Entfernte Bohrmaschine rechts: Eingang 3, Ausgang 2, Defektwahrscheinlichkeit 3 %.
Machine("Far drill", drilling, far, False, 3, 2, tool_types=[drill_tool], defect_probability=0.03)


# Startet nur beim direkten Ausführen der Datei, nicht beim Laden durch die Optimierung.
if __name__ == "__main__":
    # Produktionswege: Produkt -> (Operation) -> Produkt; "oder" kennzeichnet alternative Operationen.
    # Fertiges Gehäuse:
    # Rohteil A -> (Schruppen oder Präzisionsbearbeitung) -> Grundkörper
    #           -> (Fräsen oder Präzisionsfräsen) -> Gefräster Körper
    #           -> (Endbearbeitung) -> Fertiges Gehäuse.
    # Rohteil B -> (Schruppen) -> Grundkörper
    #           -> (Fräsen oder Präzisionsfräsen) -> Gefräster Körper
    #           -> (Endbearbeitung) -> Fertiges Gehäuse.
    # Rohteil B -> (Direktbearbeitung) -> Gefräster Körper
    #           -> (Endbearbeitung) -> Fertiges Gehäuse.

    # Fertiger Halter:
    # Rohteil A -> (Schruppen oder Präzisionsbearbeitung) -> Grundkörper
    #           -> (Bohren auf der Grundbearbeitungsmaschine oder auf der Bohrmaschine) -> Gebohrter Körper
    #           -> (Endbearbeitung oder Präzisions-Endbearbeitung) -> Fertiger Halter.
    # Rohteil B -> (Schruppen) -> Grundkörper
    #           -> (Bohren auf der Grundbearbeitungsmaschine oder auf der Bohrmaschine) -> Gebohrter Körper
    #           -> (Endbearbeitung oder Präzisions-Endbearbeitung) -> Fertiger Halter.

    # Poliertes Teil:
    # Rohteil A -> (Schruppen oder Präzisionsbearbeitung) -> Grundkörper
    #           -> (Polieren) -> Poliertes Teil.
    # Rohteil B -> (Schruppen) -> Grundkörper -> (Polieren) -> Poliertes Teil.


    # Startet die Simulation mit Visualisierung, ohne festes Zeitlimit und mit Animationsgeschwindigkeit 5.
    simulate(layout, scenario, till=sim.inf, animation_speed=5)
