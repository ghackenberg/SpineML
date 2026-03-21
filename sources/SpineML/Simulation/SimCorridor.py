import salabim as sim

from ..Configuration import Corridor

from .SimCorridorArm import SimCorridorArm


class SimCorridor(sim.Component):
    def __init__(self, corridor: Corridor, y: float, controller=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.corridor = corridor
        self.controller = controller

        # Machines
        machines_left = corridor.machines_left
        machines_right = corridor.machines_right

        # Corridor stores
        store_main = sim.Store("Store main", env=self.env)
        store_left = sim.Store("Store left", env=self.env)
        store_right = sim.Store("Store right", env=self.env)

        self.store_main = store_main
        self.store_left = store_left
        self.store_right = store_right

        # Left and right arms
        self.sim_arm_left = SimCorridorArm(
            corridor,
            machines_left,
            "left",
            store_left,
            store_right,
            store_main,
            +1,
            y,
            controller=self.controller,
            env=self.env,
        )
        self.sim_arm_right = SimCorridorArm(
            corridor,
            machines_right,
            "right",
            store_right,
            store_left,
            store_main,
            -1,
            y,
            controller=self.controller,
            env=self.env,
        )

        # Corridor storage vertical box
        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="red", x=0, y=y, z=1.625)

        # Corridor storage box
        sim.Animate3dBox(x_len=3, y_len=1, z_len=1, color='orange', x=0, y=y, z=0.5)

    def printStatistics(self):
        print(f" - {self.corridor.name}:")
        self.sim_arm_left.printStatistics()
        self.sim_arm_right.printStatistics()

    def robotCount(self):
        return self.sim_arm_left.robotCount() + self.sim_arm_right.robotCount()

    def machineCount(self):
        return self.sim_arm_left.machineCount() + self.sim_arm_right.machineCount()

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

    def plot(self):
        pass
