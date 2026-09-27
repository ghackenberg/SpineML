class Machine:

    """Representation of machines."""

    DIMENSION_PROCESSING_TIME_FACTOR = 0.01

    from ..Definition import MachineType
    from ..Definition import ProductType
    from ..Definition import ToolType
    
    from .Corridor import Corridor

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        name: str,
        machine_type: MachineType,
        corridor: Corridor,
        left: bool,
        input_storage_capacity: int,
        output_storage_capacity: int,
        tool_types: list[ToolType] | None = None,
        processing_speed_factor: float = 1.0,
    ) -> None:

        self.name = name
        self.machine_type = machine_type
        self.corridor = corridor
        self.left = left
        self.input_storage_capacity = input_storage_capacity
        self.output_storage_capacity = output_storage_capacity
        self.processing_speed_factor = processing_speed_factor
        self.dummy_tool_mount_time = 1.0
        self.dummy_tool_unmount_time = 1.0
        self.tool_types = (
            list(tool_types)
            if tool_types is not None
            else machine_type.computeToolTypes()
        )

        machine_type.machines.append(self)  
        if left:
            corridor.machines_left.append(self)
        else:
            corridor.machines_right.append(self)

        MACHINES.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:

        return f"{self.name}"

    def dimension_processing_time(self, product_type: ProductType) -> float:

        return (
            product_type.length + product_type.width + product_type.depth
        ) * self.DIMENSION_PROCESSING_TIME_FACTOR

MACHINES: list[Machine] = []
