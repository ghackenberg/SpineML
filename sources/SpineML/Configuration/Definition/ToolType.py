class ToolType:

    """Representation of tool types."""

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str, mount_time: int, unmount_time: int, total_life_units: int) :

        from .OperationType import OperationType

        self.name = name
        self.mount_time = mount_time
        self.unmount_time = unmount_time
        self.total_life_units = total_life_units

        self.operations: list[OperationType] = []

        TOOL_TYPES.append(self)

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:

        return f"{self.name}"

TOOL_TYPES: list[ToolType] = []

