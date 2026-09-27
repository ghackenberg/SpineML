import salabim as sim

from ..Configuration import Corridor
from ..Control import SimulationBridge

from .SimCorridorArm import SimCorridorArm


class SimCorridor(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        corridor: Corridor,
        bridge: SimulationBridge,
        y: float,
        *args,
        max_product_weight: float = 1.0,
        max_product_volume: float = 1.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.corridor = corridor
        self.controller = controller

        machines_left = corridor.machines_left
        machines_right = corridor.machines_right

        store_main = sim.Store(f"{corridor.name} main", env=self.env, capacity=corridor.storage_capacity)
        store_left = sim.Store(f"{corridor.name} left", env=self.env, capacity=corridor.storage_capacity)
        store_right = sim.Store(f"{corridor.name} right", env=self.env, capacity=corridor.storage_capacity)

        self.store_main = store_main
        self.store_left = store_left
        self.store_right = store_right

        bridge.register_corridor(
            corridor.name,
            self,
            stores=[self.store_main, self.store_left, self.store_right],
        )

        self.sim_arm_left = SimCorridorArm(
            corridor,
            machines_left,
            "left",
            store_left,
            store_right,
            store_main,
            bridge,
            +1,
            y,
            max_product_weight=max_product_weight,
            max_product_volume=max_product_volume,
            env=self.env,
        )
        self.sim_arm_right = SimCorridorArm(
            corridor,
            machines_right,
            "right",
            store_right,
            store_left,
            store_main,
            bridge,
            -1,
            y,
            max_product_weight=max_product_weight,
            max_product_volume=max_product_volume,
            env=self.env,
        )

        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="red", x=0, y=y, z=1.625)

        sim.Animate3dBox(x_len=3, y_len=1, z_len=1, color='orange', x=0, y=y, z=0.5)
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        self.sim_arm_left.printStatistics()
        self.sim_arm_right.printStatistics()

    # Führt die Funktion mit den übergebenen Werten aus.
    def robotCount(self):
        return self.sim_arm_left.robotCount() + self.sim_arm_right.robotCount()
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def machineCount(self):
        return self.sim_arm_left.machineCount() + self.sim_arm_right.machineCount()
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def robotUtilization(self):
        left_cnt = self.sim_arm_left.robotCount()
        right_cnt = self.sim_arm_right.robotCount()
        left_utl = self.sim_arm_left.robotUtilization()
        right_utl = self.sim_arm_right.robotUtilization()
        if left_cnt > 0 and right_cnt > 0:
            return (left_utl * left_cnt + right_utl * right_cnt) / (left_cnt + right_cnt)
        elif left_cnt > 0:
            return left_utl
        elif right_cnt > 0:
            return right_utl
        else:
            return 1

    # Führt die Funktion mit den übergebenen Werten aus.
    def machineUtilization(self):
        left_cnt = self.sim_arm_left.machineCount()
        right_cnt = self.sim_arm_right.machineCount()
        left_utl = self.sim_arm_left.machineUtilization()
        right_utl = self.sim_arm_right.machineUtilization()
        if left_cnt > 0 and right_cnt > 0:
            return (left_utl * left_cnt + right_utl * right_cnt) / (left_cnt + right_cnt)
        elif left_cnt > 0:
            return left_utl
        elif right_cnt > 0:
            return right_utl
        else:
            return 1
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def plot(self):
        pass
    

