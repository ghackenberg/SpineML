class MachineType:

    """Representation of machine types."""

    from .ToolType import ToolType

    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, name: str) :

        from .OperationType import OperationType
        
        from ..Solution import Machine

        self.name = name

        self.machines: list[Machine] = []
        self.operations: list[OperationType] = []

        MACHINE_TYPES.append(self)  

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:

        return f"{self.name}"

    # Führt die Funktion mit den übergebenen Werten aus.
    def computeToolTypes(self) -> list[ToolType]:

        """Compute tool types for this machine type from operation types."""

        from .ToolType import ToolType

        tool_types: list[ToolType] = []
        for process_step in self.operations:
            if process_step.tool_type not in tool_types:
                tool_types.append(process_step.tool_type)
        return tool_types
    
MACHINE_TYPES: list[MachineType] = []

