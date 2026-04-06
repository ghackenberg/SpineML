import salabim as sim
import matplotlib.pyplot as plt

from ..Configuration import Layout, Scenario

from .SimCorridor import SimCorridor
from .SimRobotMain import SimRobotMain


class SimLayout(sim.Component):
    def __init__(self, layout: Layout, scenario: Scenario, controller=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.layout = layout
        self.controller = controller

        # Grid for visualization
        sim.Animate3dGrid(x_range=range(-20, 20), y_range=range(-20, 20))

        # Start and end storage boxes
        y = 2 + len(layout.corridors) / 1.15
        # ... start
        self.store_start = sim.Store("start", capacity=layout.storage_capacity, env=self.env)
        sim.Animate3dBox(x_len=3, y_len=1, z_len=1, color="yellow", x=0, y=y, z=0.5)
        # ... end
        self.store_end = sim.Store("end", capacity=layout.storage_capacity, env=self.env)
        sim.Animate3dBox(x_len=3, y_len=1, z_len=1, color="yellow", x=0, y=-y, z=0.5)

        # Start and end vertical boxes /Erstellung
        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="red", x=0, y=y, z=1.625)
        sim.Animate3dBox(x_len=0.25, y_len=0.25, z_len=1.5, color="red", x=0, y=-y, z=1.625)

        # Main horizontal box/ Erstellung
        sim.Animate3dBox(x_len=0.25, y_len=y * 2 + 0.25, z_len=0.25, color="red", x=0, y=0, z=2.5)

        # Corridors
        self.sim_corridors: list[SimCorridor] = []
        corridor_num = 0
        for corridor in layout.corridors:
            y = (corridor_num + 0.5 - len(layout.corridors) / 2) * 2
            self.sim_corridors.append(SimCorridor(corridor, y, controller=self.controller, env=self.env))
            corridor_num = corridor_num + 1

        # Main robot
        self.sim_main_robot = SimRobotMain(
            layout,
            scenario,
            self.store_start,
            self.store_end,
            self.sim_corridors,
            0,
            2.5,
            controller=self.controller,
            env=self.env,
        )

        sim.AnimateText(text=lambda: f"layout start queue: {self.store_start.length()}", x=20, y=70, text_anchor="nw", font="narrow", fontsize=12)
        sim.AnimateText(text=lambda: f"layout end queue: {self.store_end.length()}", x=20, y=92, text_anchor="nw", font="narrow", fontsize=12)


    def _corridor_queues_text(self) -> str:
        if len(self.sim_corridors) == 0:
            return "corridor queues: none"

        total_main = 0
        total_left = 0
        total_right = 0
        parts = []

        for sc in self.sim_corridors:
            main_len = sc.store_main.length()
            left_len = sc.store_left.length()
            right_len = sc.store_right.length()

            total_main += main_len
            total_left += left_len
            total_right += right_len

            parts.append(f"{sc.corridor.name}(m/l/r={main_len}/{left_len}/{right_len})")

        return (
            f"corridor queues main/left/right total={total_main}/{total_left}/{total_right}: "
            + ", ".join(parts)
        )

    def _machine_store_queues_text(self) -> str:
        sim_machines = []
        for sc in self.sim_corridors:
            sim_machines.extend(sc.sim_arm_left.sim_machines)
            sim_machines.extend(sc.sim_arm_right.sim_machines)

        if len(sim_machines) == 0:
            return "machine stores in/out: none"

        total_in = sum(sm.store_in.length() for sm in sim_machines)
        total_out = sum(sm.store_out.length() for sm in sim_machines)
        parts = [
            f"{sm.machine.name}(in/out={sm.store_in.length()}/{sm.store_out.length()})"
            for sm in sim_machines
        ]

        return (
            f"machine stores in/out total={total_in}/{total_out}: "
            + ", ".join(parts)
        )

    def robotCount(self):
        cnt = 1
        for sim_corridor in self.sim_corridors:
            cnt = cnt + sim_corridor.robotCount()
        return cnt

    def machineCount(self):
        cnt = 0
        for sim_corridor in self.sim_corridors:
            cnt = cnt + sim_corridor.machineCount()
        return cnt

    def robotUtilization(self):
        cnt = self.robotCount()
        utl = self.sim_main_robot.utilization() / cnt
        for sim_corridor in self.sim_corridors:
            if sim_corridor.robotCount() > 0:
                utl = utl + sim_corridor.robotUtilization() * sim_corridor.robotCount() / cnt
        return utl

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

    def printStatistics(self):
        print(f"{self.layout.name}:")
        self.sim_main_robot.printStatistics()
        for sim_corridor in self.sim_corridors:
            sim_corridor.printStatistics()

    def plot(self):
        plt.figure(self.layout.name)

        # Draw chart
        bar_width = 0.15

        # Main robot subplot
        plt.subplot(2, 3, (1, 4))
        col = 1
        plt.bar(col * bar_width, self.sim_main_robot.utilization() * 100, width=bar_width, label='Main robot')
        col = col + 1
        plt.xticks([])
        plt.xlabel('Robot')
        plt.ylabel('Utilization (in %)')
        plt.title('Main robot utilization')
        plt.legend()

        # Corridor robot submit
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

        # Machines subplot
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

    def plotFull(self, legend=False):
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

        # Main robot
        plt.subplot(rows, columns, 1)
        self.sim_main_robot.plot(legend)

        # Corridors
        row = 1
        for sim_corridor in self.sim_corridors:
            # Left arm
            col = 1
            if len(sim_corridor.sim_arm_left.sim_machines) > 0:
                # Robot
                plt.subplot(rows, columns, row * columns + col)
                sim_corridor.sim_arm_left.sim_arm_robot.plot(legend)
                col = col + 1
                # Machines
                for sim_machine in sim_corridor.sim_arm_left.sim_machines:
                    plt.subplot(rows, columns, row * columns + col)
                    sim_machine.plot(legend)
                    col = col + 1
            # Right arm
            col = 1 if left == 0 else left + 2
            if len(sim_corridor.sim_arm_right.sim_machines) > 0:
                # Robot
                plt.subplot(rows, columns, row * columns + col)
                sim_corridor.sim_arm_right.sim_arm_robot.plot(legend)
                col = col + 1
                # Machines
                for sim_machine in sim_corridor.sim_arm_right.sim_machines:
                    plt.subplot(rows, columns, row * columns + col)
                    sim_machine.plot(legend)
                    col = col + 1
            row = row + 1

        plt.show()









