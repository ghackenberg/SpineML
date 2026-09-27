class Order:

    """Representation of orders as part of scenarios for evaluation."""

    from ..Definition import ProductType
    
    from .Scenario import Scenario

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str, quantity: int, earliest_start_time: int, latest_end_time: int, product_type: ProductType, scenario: Scenario) -> None:
        
        self.name = name
        self.quantity = quantity
        self.earliest_start_time = earliest_start_time
        self.latest_end_time = latest_end_time
        self.product_type = product_type
        self.scenario = scenario

        product_type.orders.append(self)
        scenario.orders.append(self)

        ORDERS.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:
        return self.name

ORDERS: list[Order] = []

