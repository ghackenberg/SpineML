# OperationType und Operationsmodell

Python-Datei:

`sources/SpineML/Configuration/Definition/OperationType.py`

## Aufgabe von `OperationType`

`OperationType` beschreibt einen möglichen Bearbeitungsschritt in der Fabrik.
Eine Operation legt fest:

~~~text
Name
Bearbeitungsdauer
Werkzeugverbrauch
Defektwahrscheinlichkeit
Maschinentyp
Werkzeugtyp
verbrauchter Produktzustand
erzeugter Produktzustand
~~~

Beispiel:

~~~python
OperationType(
    "Fräsen",
    5,
    2,
    0.10,
    fraesmaschine,
    fraeswerkzeug,
    rohteil,
    gefraestes_teil,
)
~~~

Diese Operation nimmt ein `rohteil`, bearbeitet es auf einer Fräsmaschine und
erzeugt ein `gefraestes_teil`.

## Konstruktor `__init__`

~~~python
def __init__(
    self,
    name,
    duration,
    consumes_life_units,
    defect_probability,
    machine_type,
    tool_type,
    consumes_product_type,
    produces_product_type,
)
~~~

### Eingaben

~~~text
name                  → Name der Operation
duration              → Dauer in Zeiteinheiten
consumes_life_units   → Werkzeugverbrauch
defect_probability    → Defektwahrscheinlichkeit zwischen 0 und 1
machine_type          → geeigneter Maschinentyp
tool_type             → benötigter Werkzeugtyp
consumes_product_type → Produktzustand vor der Operation
produces_product_type → Produktzustand nach der Operation
~~~

### Interne Wirkung

Die Werte werden im neuen Objekt gespeichert:

~~~python
self.name = name
self.duration = duration
self.consumes_life_units = consumes_life_units
self.defect_probability = defect_probability
self.machine_type = machine_type
self.tool_type = tool_type
self.consumes_product_type = consumes_product_type
self.produces_product_type = produces_product_type
~~~

Danach werden Beziehungen eingetragen:

~~~text
Maschinentyp       → kennt diese Operation
Werkzeugtyp        → kennt diese Operation
Eingangsprodukt    → kennt diese Operation als mögliche Nachfolge
Ausgangsprodukt    → kennt diese Operation als möglichen Vorgänger
OPERATION_TYPES    → enthält die Operation global
~~~

### Rückgabe

Der Konstruktor gibt kein separates Ergebnis zurück:

~~~python
operation = OperationType(...)
~~~

`operation` ist danach das neu erzeugte `OperationType`-Objekt.

## Methode `__repr__`

~~~python
def __repr__(self) -> str:
    return f"{self.name}"
~~~

### Eingabe

Python ruft die Methode automatisch auf, wenn das Objekt als Text benötigt
wird:

~~~python
str(operation)
~~~

### Ausgabe

Wenn der Name `"Fräsen"` ist:

~~~text
Fräsen
~~~

Die Methode zeigt also den Operationsnamen statt einer langen
Objektbeschreibung.

## Globale Liste `OPERATION_TYPES`

~~~python
OPERATION_TYPES = []
~~~

Bei jeder Erstellung wird die neue Operation angehängt:

~~~python
OPERATION_TYPES.append(self)
~~~

Beispiel:

~~~python
op1 = OperationType("Fräsen", ...)
op2 = OperationType("Schleifen", ...)
~~~

Danach enthält die Liste:

~~~python
[op1, op2]
~~~

## Produktionswege

Ein Produktionsweg entsteht dadurch, dass eine Operation den Produktzustand
der nächsten Operation erzeugt:

~~~text
Rohteil
  → Fräsen
Gefrästes Teil
  → Schleifen
Geschliffenes Teil
  → Polieren
Poliertes Teil
~~~

Diese normale Modellstruktur wird von der Simulation verwendet. Die frühere
zusätzliche Prüfung auf Produktzustandszyklen wie `A → B → A` wurde entfernt.
Die aktuelle Simulation startet diese Validierungsfunktion nicht mehr.

Das bedeutet: Die Examples müssen weiterhin sinnvolle gerichtete
Produktionswege definieren. Die Datei `OperationType.py` erstellt nur
Operationen und ihre Beziehungen; sie entscheidet nicht, welche Operation
während eines Entscheidungszyklus ausgewählt wird.

