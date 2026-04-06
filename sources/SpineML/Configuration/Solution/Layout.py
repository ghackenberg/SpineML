class Layout:

    """Representation of layouts with corridors."""

    def __init__(
        self,
        name: str,
        storage_out_time: int,
        storage_in_time: int,
        storage_capacity: int | float,
    ) -> None:

        from .Corridor import Corridor
        
        # Remember properties
        self.name = name
        self.storage_capacity = storage_capacity
        self.storage_out_time = storage_out_time
        self.storage_in_time = storage_in_time
        
        # Remember relations
        self.corridors: list[Corridor] = []
        
        # Remember instance
        LAYOUTS.append(self)

    def __repr__(self) -> str:

        return f"{self.name}"
    
LAYOUTS: list[Layout] = []
