class OperationType:

    """Representation of operation types."""

    from .ToolType import ToolType
    from .MachineType import MachineType
    from .ProductType import ProductType

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str, duration: int, consumes_life_units: int, defect_probability: float, machine_type: MachineType, tool_type: ToolType, consumes_product_type: ProductType, produces_product_type: ProductType) -> None:
        
        self.name = name
        self.duration = duration
        self.consumes_life_units = consumes_life_units
        self.defect_probability = defect_probability
        self.machine_type = machine_type
        self.tool_type = tool_type
        self.consumes_product_type = consumes_product_type
        self.produces_product_type = produces_product_type

        machine_type.operations.append(self)
        tool_type.operations.append(self)
        consumes_product_type.consuming_operations.append(self)
        produces_product_type.producing_operations.append(self)

        OPERATION_TYPES.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:
        
        return f"{self.name}"

OPERATION_TYPES: list[OperationType] = []

