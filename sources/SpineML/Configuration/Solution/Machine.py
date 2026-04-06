class Machine:

    """Representation of machines."""

    DIMENSION_PROCESSING_TIME_FACTOR = 0.01

    from ..Definition import MachineType, ProductType
    
    from .Corridor import Corridor

    def __init__(
        self,
        name: str,
        machine_type: MachineType,
        corridor: Corridor,
        left: bool,
        storage_capacity: int | float,
        storage_out_time: int | float,
        storage_in_time: int | float,
    ) -> None:

        # Remember properties
        self.name = name
        self.machine_type = machine_type
        self.corridor = corridor
        self.left = left
        self.storage_capacity = storage_capacity
        self.storage_out_time = storage_out_time
        self.storage_in_time = storage_in_time

        # Remember relations
        machine_type.machines.append(self)  # appending machinetype to the list
        if left:
            corridor.machines_left.append(self)
        else:
            corridor.machines_right.append(self)

        # Remember instance
        MACHINES.append(self)

    def __repr__(self) -> str:

        return f"{self.name}"

    def dimension_processing_time(self, product_type: ProductType) -> float:

        return (
            product_type.length + product_type.width + product_type.depth
        ) * self.DIMENSION_PROCESSING_TIME_FACTOR

MACHINES: list[Machine] = []
