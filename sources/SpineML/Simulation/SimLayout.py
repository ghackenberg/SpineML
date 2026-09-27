import salabim as sim
import matplotlib.pyplot as plt

from ..Configuration import Layout, Scenario
from ..Control import SimulationBridge

from .SimCorridor import SimCorridor
from .SimRobotMain import SimRobotMain


class SimLayout(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
    def __init__(self, layout: Layout, scenario: Scenario, bridge: SimulationBridge, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.layout = layout
        self.controller = controller

        self.max_product_weight = 1.0
        self.max_product_volume = 1.0
        for order in scenario.orders:
            product = order.product_type
            product_volume = product.length * product.width * product.depth
            self.max_product_weight = max(
                self.max_product_weight,
                float(product.weight),
            )
            self.max_product_volume = max(
                self.max_product_volume,
                float(product_volume),
            )

        sim.Animate3dGrid(x_range=range(-20, 20), y_range=range(-20, 20))

        y = 2 + len(layout.corridors) / 1.15
        self.store_start = sim.Store("start", env=self.env, capacity=layout.storage_capacity)
        sim.Animate3dBox(x_len=3, y_len=1, z_len=1, color="yellow", x=0, y=y, z=0.5)
        self.store_end = sim.Store("end", env=self.env, capacity=layout.storage_capacity)
        sim.Animate3dBox(x_len=3, y_len=1, z_len=1, color="yellow", x=0, y=-y, z=0.5)

        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="red", x=0, y=y, z=1.625)
        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="red", x=0, y=-y, z=1.625)

        sim.Animate3dBox(x_len=0.25, y_len=y*2+0.25, z_len=0.25, color="red", x=0, y=0, z=2.5)

        self.sim_corridors: list[SimCorridor] = []
        corridor_num = 0
        for corridor in layout.corridors:
            y = (corridor_num + 0.5 - len(layout.corridors) / 2) * 2
            self.sim_corridors.append(
                SimCorridor(
                    corridor,
                    bridge,
                    y,
                    max_product_weight=self.max_product_weight,
                    max_product_volume=self.max_product_volume,
                    env=self.env,
                )
            )
            corridor_num = corridor_num + 1

        self.sim_main_robot = SimRobotMain(layout, scenario, self.store_start, self.store_end, self.sim_corridors, bridge, 0, 2.5, env=self.env)
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def robotCount(self):
        cnt = 1
        for sim_corridor in self.sim_corridors:
            cnt = cnt + sim_corridor.robotCount()
        return cnt
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def machineCount(self):
        cnt = 0
        for sim_corridor in self.sim_corridors:
            cnt = cnt + sim_corridor.machineCount()
        return cnt

    # Führt die Funktion mit den übergebenen Werten aus.
    def simMachines(self):
        """Return all runtime SimMachine components in this layout."""
        machines = []
        for sim_corridor in self.sim_corridors:
            machines.extend(sim_corridor.sim_arm_left.sim_machines)
            machines.extend(sim_corridor.sim_arm_right.sim_machines)
        return machines
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def robotUtilization(self):
        cnt = self.robotCount()
        utl = self.sim_main_robot.utilization() / cnt
        for sim_corridor in self.sim_corridors:
            if sim_corridor.robotCount() > 0:
                utl = utl + sim_corridor.robotUtilization() * sim_corridor.robotCount() / cnt
        return utl

    # Führt die Funktion mit den übergebenen Werten aus.
    def machineUtilization(self):
        cnt = self.machineCount()
        if cnt > 0:
            utl = 0
            for sim_corridor in self.sim_corridors:
                if sim_corridor.machineCount() > 0:
                    utl = utl + sim_corridor.machineUtilization() * sim_corridor.machineCount() / cnt
            return utl
        else:
            return 1

    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        print(
            f"{self.layout.name}: Anfangslager={self.store_start.count()} Jobs, "
            f"Endlager={self.store_end.count()} Jobs"
        )
        self.sim_main_robot.printStatistics()
        for sim_corridor in self.sim_corridors:
            sim_corridor.printStatistics()
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def plot(self):
        plt.figure(self.layout.name)

        bar_width = 0.15
        
        plt.subplot(2, 3, (1, 4))
        col = 1
        plt.bar(col * bar_width, self.sim_main_robot.utilization() * 100, width=bar_width, label='Main robot')
        col = col + 1
        plt.xticks([])
        plt.xlabel('Robot')
        plt.ylabel('Utilization (in %)')
        plt.title('Main robot utilization')
        plt.legend()

        plt.subplot(2, 3, (2, 3))
        col = 1
        for sim_corridor in self.sim_corridors:
            plt.bar(col * bar_width, sim_corridor.robotUtilization() * 100, width=bar_width, label=sim_corridor.corridor.name)
            col = col + 1
        plt.xticks([])
        plt.xlabel('Corridor')
        plt.ylabel('Utilization (in %)')
        plt.title('Corridor robot utilization')
        plt.legend()

        plt.subplot(2, 3, (5, 6))
        col = 1
        for sim_corridor in self.sim_corridors:
            plt.bar(col * bar_width, sim_corridor.machineUtilization() * 100, width=bar_width, label=sim_corridor.corridor.name)
            col = col + 1
        plt.xticks([])
        plt.xlabel('Corridor')
        plt.ylabel('Utilization (in %)')
        plt.title('Machine utilization')
        plt.legend()

        plt.show()

    # Führt die Funktion mit den übergebenen Werten aus.
    def plotFull(self, legend = False):
        plt.figure('Layout')

        rows = len(self.sim_corridors) + 1

        left = 0
        right = 0

        for sim_corridor in self.sim_corridors:
            left = max(left, len(sim_corridor.sim_arm_left.sim_machines))
            right = max(right, len(sim_corridor.sim_arm_right.sim_machines))

        if left > 0 and right > 0:
            columns = left + right + 2
        elif left > 0:
            columns = left + 1
        elif right > 0:
            columns = right + 1
        else:
            columns = 1

        plt.subplot(rows, columns, 1)
        self.sim_main_robot.plot(legend)

        row = 1
        for sim_corridor in self.sim_corridors:
            col = 1
            if len(sim_corridor.sim_arm_left.sim_machines) > 0:
                plt.subplot(rows, columns, row * columns + col)
                sim_corridor.sim_arm_left.sim_arm_robot.plot(legend)
                col = col + 1
                for sim_machine in sim_corridor.sim_arm_left.sim_machines:
                    plt.subplot(rows, columns, row * columns + col)
                    sim_machine.plot(legend)
                    col = col + 1
            col = 1 if left == 0 else left + 2
            if len(sim_corridor.sim_arm_right.sim_machines) > 0:
                plt.subplot(rows, columns, row * columns + col)
                sim_corridor.sim_arm_right.sim_arm_robot.plot(legend)
                col = col + 1
                for sim_machine in sim_corridor.sim_arm_right.sim_machines:
                    plt.subplot(rows, columns, row * columns + col)
                    sim_machine.plot(legend)
                    col = col + 1
            row = row + 1

        plt.show()

