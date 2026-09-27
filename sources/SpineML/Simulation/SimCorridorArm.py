import salabim as sim

from ..Configuration import Corridor, Machine
from ..Control import SimulationBridge

from .SimMachine import SimMachine
from .SimRobotCorridorArm import SimRobotCorridorArm

class SimCorridorArm(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(
        self,
        corridor: Corridor,
        machines: list[Machine],
        direction: str,
        store_in: sim.Store,
        store_out_arm: sim.Store,
        store_out_main: sim.Store,
        bridge: SimulationBridge,
        dx: float,
        y: float,
        *args,
        max_product_weight: float = 1.0,
        max_product_volume: float = 1.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.corridor = corridor
        self.machines = machines
        
        self.direction = direction

        self.sim_machines: list[SimMachine] = []
        machine_num = 0
        for machine in machines:
            machine_x = (3 + machine_num * 2) * dx
            sim_machine = SimMachine(
                machine,
                bridge,
                machine_x,
                y,
                max_product_weight=max_product_weight,
                max_product_volume=max_product_volume,
                env=self.env,
            )
            self.sim_machines.append(sim_machine)
            machine_num = machine_num + 1

        if len(machines) != 0:
            self.sim_arm_robot = SimRobotCorridorArm(corridor, machines, direction, store_in, store_out_arm, store_out_main, self.sim_machines, bridge, dx, y, env=self.env)

        if len(machines) != 0:
            x_len = len(machines) * 2 + 0.26
            x = (0.86 + x_len / 2) * dx
            sim.Animate3dBox(x_len=x_len, y_len=0.25, z_len=0.25, color="green", x=x, y=y, z=2.5)

        if len(machines) != 0:
            sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="green", x=dx, y=y, z=1.625)
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        if len(self.machines) != 0:
            self.sim_arm_robot.printStatistics()
        for sim_machine in self.sim_machines:
            sim_machine.printStatistics()
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def robotCount(self):
        if self.machineCount() > 0:
            return 1
        else:
            return 0

    # Führt die Funktion mit den übergebenen Werten aus.
    def machineCount(self):
        return len(self.sim_machines)
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def robotUtilization(self):
        if self.machineCount() > 0:
            return self.sim_arm_robot.utilization()
        else:
            return 1

    # Führt die Funktion mit den übergebenen Werten aus.
    def machineUtilization(self):
        cnt = self.machineCount()
        if cnt > 0:
            utl = 0
            for sim_machine in self.sim_machines:
                utl = utl + sim_machine.utilization() / cnt
            return utl
        else:
            return 1
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def plot(self):
        pass

