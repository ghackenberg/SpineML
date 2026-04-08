from __future__ import annotations

import salabim as sim

from .Configuration import Layout, Scenario
from .Simulation import SimLayout, SimScenario
from .controller.default_controller import DefaultController
from .controller.greedy_controller import GreedyController


DEFAULT_2D_POSITION = (960, 100)
DEFAULT_3D_POSITION = (0, 100)
DEFAULT_WINDOW_SIZE = (950, 768)


def _patch_salabim_minimized_3d_window() -> None:
    """
    Skip one 3D draw tick while the OpenGL window is minimized.

    On Windows, GLUT can temporarily report window height == 0 during
    minimize/restore, which otherwise triggers a ZeroDivisionError in salabim.
    """
    salabim_module = getattr(sim, "salabim", None)
    if salabim_module is None:
        return

    animate_intro = getattr(salabim_module, "_AnimateIntro", None)
    if animate_intro is None:
        return

    if getattr(animate_intro, "_spineml_minimize_patch", False):
        return

    original_draw = animate_intro.draw

    def _safe_draw(self, t):
        glut = getattr(salabim_module, "glut", None)
        if glut is not None:
            try:
                if glut.glutGet(glut.GLUT_WINDOW_HEIGHT) <= 0:
                    return
            except Exception:
                pass

        try:
            return original_draw(self, t)
        except ZeroDivisionError:
            return

    animate_intro.draw = _safe_draw
    animate_intro._spineml_minimize_patch = True


def _simulate_core(
    layout: Layout,
    scenario: Scenario,
    animate=True,
    till=sim.inf,
    controller_class=GreedyController,
    animate2d: bool | None = None,
    animate3d: bool | None = None,
    position2d: tuple[int, int] | None = None,
    position3d: tuple[int, int] | None = None,
):
    sim.yieldless(False)

    print("Creating simulation environment")
    env = sim.Environment(time_unit="hours")

    if animate:
        animate2d = True if animate2d is None else animate2d
        animate3d = True if animate3d is None else animate3d
        position2d = position2d or DEFAULT_2D_POSITION
        position3d = position3d or DEFAULT_3D_POSITION

        if animate3d:
            _patch_salabim_minimized_3d_window()

        if animate2d:
            env.width(DEFAULT_WINDOW_SIZE[0])
            env.height(DEFAULT_WINDOW_SIZE[1])
            env.position(position2d)

        if animate3d:
            env.width3d(DEFAULT_WINDOW_SIZE[0])
            env.height3d(DEFAULT_WINDOW_SIZE[1])
            env.position3d(position3d)
            env.show_camera_position(over3d=True)
            env.view(x_eye=0, y_eye=15, z_eye=5)

        if animate2d:
            env.show_camera_position(True)

        env.animation_parameters(animate=animate2d, animate3d=animate3d, show_fps=True)
    print("Simulation environment created")

    sim_controller = controller_class(env=env)

    print("Creating simulation components")
    sim_layout = SimLayout(layout, scenario, controller=sim_controller, env=env)
    sim_scenario = SimScenario(layout, scenario, sim_layout.store_start, controller=sim_controller, env=env)

    sim_machines = []
    sim_arm_robots = []
    for sim_corridor in sim_layout.sim_corridors:
        sim_machines.extend(sim_corridor.sim_arm_left.sim_machines)
        sim_machines.extend(sim_corridor.sim_arm_right.sim_machines)
        if sim_corridor.sim_arm_left.machineCount() > 0:
            sim_arm_robots.append(sim_corridor.sim_arm_left.sim_arm_robot)
        if sim_corridor.sim_arm_right.machineCount() > 0:
            sim_arm_robots.append(sim_corridor.sim_arm_right.sim_arm_robot)

    sim_order_jobs = []
    for sim_order in sim_scenario.sim_orders:
        sim_order_jobs.extend(sim_order.sim_jobs)

    sim_controller.attach(
        machines=sim_machines,
        order_jobs=sim_order_jobs,
        main_robots=[sim_layout.sim_main_robot],
        arm_robots=sim_arm_robots,
    )

    print("Simulation components created")
    print("Starting simulation run")
    env.run(till=till)
    print("Simulation run finished")

    sim_scenario.printStatistics()
    sim_layout.printStatistics()

    sim_scenario.plot()
    sim_layout.plot()


def simulate(
    layout: Layout,
    scenario: Scenario,
    animate=True,
    till=sim.inf,
    controller_class=GreedyController,
    animate2d: bool | None = None,
    animate3d: bool | None = None,
    position2d: tuple[int, int] | None = None,
    position3d: tuple[int, int] | None = None,
):
    _simulate_core(
        layout,
        scenario,
        animate=animate,
        till=till,
        controller_class=controller_class,
        animate2d=animate2d,
        animate3d=animate3d,
        position2d=position2d,
        position3d=position3d,
    )
