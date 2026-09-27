import salabim as sim

from .Configuration import (
    Layout,
    Scenario,
)
from .Control import Policy, SimulationBridge
from .Simulation import SimLayout, SimMachineShutdown, SimScenario


# Führt die Funktion mit den übergebenen Werten aus.
def guard_zero_sized_salabim_3d_window():
    """Skip OpenGL drawing while a closing or minimized window has no height."""
    from OpenGL import GLUT as glut
    from salabim.salabim import _AnimateIntro

    draw = _AnimateIntro.draw
    if getattr(draw, "_spineml_zero_size_guard", False):
        return

    # Führt die Funktion mit den übergebenen Werten aus.
    def draw_with_zero_size_guard(animation, time):
        window_height = glut.glutGet(glut.GLUT_WINDOW_HEIGHT)
        if window_height <= 0:
            return
        return draw(animation, time)

    draw_with_zero_size_guard._spineml_zero_size_guard = True
    _AnimateIntro.draw = draw_with_zero_size_guard

# Führt die Funktion mit den übergebenen Werten aus.
def simulate(
    layout: Layout,
    scenario: Scenario,
    animate=True,
    till=sim.inf,
    policy: Policy | None = None,
    bridge: SimulationBridge | None = None,
    animation_speed=5,
):
    sim.yieldless(False)

    env = sim.Environment(time_unit='hours')

    if animate:
        guard_zero_sized_salabim_3d_window()
        env.width(950)
        env.height(768)
        env.position((960, 100))
        env.width3d(950)
        env.height3d(768)
        env.position3d((0, 100))
        env.show_camera_position(True)
        env.show_camera_position(over3d=True)
        env.view(x_eye=0, y_eye=15, z_eye=5)
        env.animation_parameters(
            animate=True,
            animate3d=True,
            speed=animation_speed,
            show_fps=True,
            show_time=True,
        )
    bridge = bridge if bridge is not None else SimulationBridge(policy, env=env)
    sim_layout = SimLayout(layout, scenario, bridge, env=env)
    sim_scenario = SimScenario(layout, scenario, sim_layout.store_start, bridge, env=env)
    completed_by_watcher = False
    try:
        env.run(till=till)
    except sim.SimulationStopped:
        completed_by_watcher = True

    if till == sim.inf and not completed_by_watcher:
        for sim_machine in sim_layout.simMachines():
            SimMachineShutdown(sim_machine, env=env)
        env.run()

    sim_scenario.printStatistics()
    sim_layout.printStatistics()

    sim_scenario.plot()
    sim_layout.plot()

