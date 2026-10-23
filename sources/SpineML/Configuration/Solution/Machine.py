import hashlib
import random


class Machine:

    """Representation of machines."""

    from ..Definition import MachineType
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
        *,
        defect_probability: float | None = None,
    ) -> None:

        self.defect_probability = (
            None if defect_probability is None else float(defect_probability)
        )
        if (
            self.defect_probability is not None
            and not 0.0 <= self.defect_probability <= 1.0
        ):
            raise ValueError("Machine defect_probability must be between 0 and 1.")

        self.name = name
        self.machine_type = machine_type
        self.corridor = corridor
        self.left = left
        self.input_storage_capacity = input_storage_capacity
        self.output_storage_capacity = output_storage_capacity
        # Bearbeitungsgeschwindigkeit

        self.processing_speed_factor = 1.0
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

    def resolve_defect_probability(self, seed: int) -> float:
        """Liefert den festen Wert oder eine reproduzierbare Zufallswahrscheinlichkeit."""
        if self.defect_probability is not None:
            return self.defect_probability

        # Kombiniert Seed und Maschinenangaben zu einem Schlüssel in Byteform.
        probability_key = (
            f"machine-defect-probability|{int(seed)}|{self.corridor.layout.name}|"
            f"{self.corridor.name}|{self.name}|{self.left}"
        ).encode("utf-8")
        # Leitet aus dem Schlüssel einen festen Startwert für einen eigenen Generator ab.
        # Gleicher Schlüssel bedeutet dadurch dieselbe Zufallszahlenfolge.
        probability_rng = random.Random(
            int.from_bytes(hashlib.sha256(probability_key).digest()[:8], "big")
        )
        return probability_rng.random()

    # Führt die Funktion mit den übergebenen Werten aus.
    def __repr__(self) -> str:

        return f"{self.name}"

MACHINES: list[Machine] = []
