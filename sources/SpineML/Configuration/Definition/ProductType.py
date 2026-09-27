class ProductType:

    """Representation of raw material, intermediate products, and end products."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        name: str,
        length: int,
        width: int,
        depth: int,
        weight: int,
    ) -> None:

        from .OperationType import OperationType

        from ..Evaluation import Order
        
        self.name = name
        self.length = length
        self.width = width
        self.depth = depth
        self.weight = weight

        self.consuming_operations: list[OperationType] = []
        self.producing_operations: list[OperationType] = []
        self.orders: list[Order] = []

        PRODUCT_TYPES.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:

        return f"{self.name}"
PRODUCT_TYPES: list[ProductType] = []
