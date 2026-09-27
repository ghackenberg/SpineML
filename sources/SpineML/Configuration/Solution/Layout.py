class Layout:

    """Representation of layouts with corridors."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str, storage_out_time: int, storage_in_time: int, storage_capacity: int) -> None:

        from .Corridor import Corridor
        
        self.name = name
        self.storage_out_time = storage_out_time
        self.storage_in_time = storage_in_time
        self.storage_capacity = storage_capacity
        
        self.corridors: list[Corridor] = []
        
        LAYOUTS.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:

        return f"{self.name}"
    
LAYOUTS: list[Layout] = []

