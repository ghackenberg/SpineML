import random
import salabim as sim
import matplotlib.pyplot as plt

class SimRobot(sim.Component):
    # Initialisiert das Objekt mit seinen Eingabewerten.
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
        self.configured_movement_speed = 1.0
        self.movement_speed_multiplier = random.uniform(0.95, 1.05)
        self.movement_speed = 0.0

        self.state_move = sim.State("Move", value="waiting", env=self.env)
        self.state_load = sim.State("Load", value="empty", env=self.env)

        sim.Animate3dBox(x_len=0.5, y_len=0.5, z_len=0.5, color=color, edge_color='white', x=self.x_func, y=self.y_func, z=self.z_func)
    # Berechnet die linear interpolierte X-Position des Roboters zur Animationszeit t.
    def x_func(self, t: float):
        if self.next_t == self.t:
            return self.x
        else:
            return self.x + (self.next_x - self.x) * (t - self.t) / (self.next_t - self.t)
    # Berechnet die linear interpolierte Y-Position des Roboters zur Animationszeit t.
    def y_func(self, t: float):
        if self.next_t == self.t:
            return self.y
        else:
            return self.y + (self.next_y - self.y) * (t - self.t) / (self.next_t - self.t)
    # Berechnet die linear interpolierte Z-Position des Roboters zur Animationszeit t.
    def z_func(self, t: float):
        if self.next_t == self.t:
            return self.z
        else:
            return self.z + (self.next_z - self.z) * (t - self.t) / (self.next_t - self.t)
        
    # Führt die Funktion mit den übergebenen Werten aus.
    def take_selected_job_from_store(self, action, target_store):
        selected_job = action.payload["selected_job"]
        current_items = target_store.as_list()
        if selected_job not in current_items:
            return None

        # Prüft die angegebene Bedingung.
        def is_selected_job(item):
            if item is selected_job:
                return True
            return False

        job = yield self.from_store(
            target_store,
            filter=is_selected_job,
        )
        return job

    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_x(self, next_x: float, speed: float):
        effective_speed = speed * self.movement_speed_multiplier
        self.movement_speed = effective_speed
        duration = abs(next_x - self.x) / effective_speed
        self.t = self.env.now()
        self.next_x = next_x
        self.next_t = self.env.now() + duration
        self.state_move.set("moving_x")
        yield self.hold(duration)
        self.state_move.set("waiting")
        self.x = self.next_x
        self.t = self.env.now()
        self.next_t = self.t
        self.movement_speed = 0.0
        
    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_y(self, next_y: float, speed: float):
        effective_speed = speed * self.movement_speed_multiplier
        self.movement_speed = effective_speed
        duration = abs(next_y - self.y) / effective_speed
        self.t = self.env.now()
        self.next_y = next_y
        self.next_t = self.env.now() + duration
        self.state_move.set("moving_y")
        yield self.hold(duration)
        self.state_move.set("waiting")
        self.y = self.next_y
        self.t = self.env.now()
        self.next_t = self.t
        self.movement_speed = 0.0
        
    # Führt die angeforderte Bewegung oder Aktion aus.
    def move_z(self, next_z: float, speed: float):
        effective_speed = speed * self.movement_speed_multiplier
        self.movement_speed = effective_speed
        duration = abs(next_z - self.z) / effective_speed
        self.t = self.env.now()
        self.next_z = next_z
        self.next_t = self.env.now() + duration
        self.state_move.set("moving_z")
        yield self.hold(duration)
        self.state_move.set("waiting")
        self.z = self.next_z
        self.t = self.env.now()
        self.next_t = self.t
        self.movement_speed = 0.0
    
    # Führt die Funktion mit den übergebenen Werten aus.
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
    
    # Führt die Funktion mit den übergebenen Werten aus.
    def printStatistics(self):
        return None
    
    # Führt die Funktion mit den übergebenen Werten aus.
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

        for i in range(len(categories)):
            plt.bar(i * bar_width, values[i], width=bar_width, label=categories[i])

        plt.xticks([])

        plt.xlabel('Robot Load and Move State')
        plt.ylabel('State Duration')
        plt.title(self.label)

        if legend:
            plt.legend()
