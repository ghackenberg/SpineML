import salabim as sim
import matplotlib.pyplot as plt

from ..util import toString

class SimRobot(sim.Component):
    def __init__(self, label: str, indent: int, x: float, y: float, z: float, color: str, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.label = label

        self.indent = indent

        self.x = x
        self.y = y
        self.z = z
        self.t = self.env.now()

        self.next_x = x
        self.next_y = y
        self.next_z = z
        self.next_t = self.env.now()

        self.state_move = sim.State("Move", value="waiting", env=self.env)
        self.state_load = sim.State("Load", value="empty", env=self.env)

        sim.Animate3dBox(x_len=0.5, y_len=0.5, z_len=0.5, color=color, edge_color='white', x=self.x_func, y=self.y_func, z=self.z_func)


    #Interpolation functions for animation
    def x_func(self, t: float):
        if self.next_t == self.t:
            return self.x
        else:
            return self.x + (self.next_x - self.x) * (t - self.t) / (self.next_t - self.t)
    
       
    #Interpolation functions for animation
    def y_func(self, t: float):
        if self.next_t == self.t:
            return self.y
        else:
            return self.y + (self.next_y - self.y) * (t - self.t) / (self.next_t - self.t)


    #Interpolation functions for animation
    def z_func(self, t: float):
        if self.next_t == self.t:
            return self.z
        else:
            return self.z + (self.next_z - self.z) * (t - self.t) / (self.next_t - self.t)


    # next_x und next_t werden hier gesetzt
    def move_x(self, next_x: float, speed: float):
        duration = abs(next_x - self.x) / speed
        self.t = self.env.now()
        self.next_x = next_x
        self.next_t = self.env.now() + duration
        self.state_move.set("moving_x")
        yield self.hold(duration)
        self.state_move.set("waiting")
        self.x = self.next_x
        

        
    def move_y(self, next_y: float, speed: float):
        duration = abs(next_y - self.y) / speed
        self.t = self.env.now()
        self.next_y = next_y
        self.next_t = self.env.now() + duration
        self.state_move.set("moving_y")
        yield self.hold(duration)
        self.state_move.set("waiting")
        self.y = self.next_y
        
    def move_z(self, next_z: float, speed: float):
        duration = abs(next_z - self.z) / speed
        self.t = self.env.now()
        self.next_z = next_z
        self.next_t = self.env.now() + duration
        self.state_move.set("moving_z")
        yield self.hold(duration)
        self.state_move.set("waiting")
        self.z = self.next_z
    
    def utilization(self):
        waiting = self.state_move.value.value_duration('waiting')

        moving_x = self.state_move.value.value_duration('moving_x')
        moving_y = self.state_move.value.value_duration('moving_y')
        moving_z = self.state_move.value.value_duration('moving_z')

        moving = moving_x + moving_y + moving_z

        total = moving + waiting

        if total > 0:
            return moving / total
        else:
            return 1
    
    def printStatistics(self):
        move_output = toString(self.state_move)
        load_output = toString(self.state_load)
        indent = ""
        for i in range(self.indent):
            indent = f"{indent}   "
        print(f"{indent} - {self.label} ({move_output}) ({load_output})")
    
    def plot(self, legend = False):        
        categories = ['Loaded', 'Empty', 'Waiting', 'Moving_x', 'Moving_y', 'Moving_z']

        loaded = self.state_load.value.value_duration('loaded')
        empty = self.state_load.value.value_duration('empty')
        waiting = self.state_move.value.value_duration('waiting')
        moving_x = self.state_move.value.value_duration('moving_x')
        moving_y = self.state_move.value.value_duration('moving_y')
        moving_z = self.state_move.value.value_duration('moving_z')

        values = [loaded, empty, waiting, moving_x, moving_y, moving_z]

        bar_width = 0.15

        # Graph
        for i in range(len(categories)):
            plt.bar(i * bar_width, values[i], width=bar_width, label=categories[i])

        # x Axis
        plt.xticks([])

        # Labels
        plt.xlabel('Robot Load and Move State')
        plt.ylabel('State Duration')
        plt.title(self.label)

        # Legend
        if legend:
            plt.legend()
