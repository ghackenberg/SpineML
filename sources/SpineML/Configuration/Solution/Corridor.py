class Corridor:

    """Representation of corridors with machines."""

    from .Layout import Layout

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str, storage_capacity: int, storage_out_time: int, storage_in_time: int, layout: Layout) -> None:
        
        from .Machine import Machine

        self.name = name
        self.storage_capacity = storage_capacity
        self.storage_out_time = storage_out_time
        self.storage_in_time = storage_in_time
        self.layout = layout
        
        layout.corridors.append(self)
        self.machines_left: list[Machine] = []
        self.machines_right: list[Machine] = []
        
        CORRIDORS.append(self)

CORRIDORS: list[Corridor] = []

