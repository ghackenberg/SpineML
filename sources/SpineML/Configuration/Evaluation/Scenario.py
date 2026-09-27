class Scenario:

    """Representation of scenarios for evaluation."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str) -> None:

        from .Order import Order

        self.name = name

        self.orders: list[Order] = []

        SCENARIOS.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:
        
        return f"{self.name}"

SCENARIOS: list[Scenario] = []

