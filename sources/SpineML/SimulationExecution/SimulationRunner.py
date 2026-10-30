"""Führt eine übergebene Policy aus und sammelt die Produktionskennzahlen."""

from __future__ import annotations

import random

import salabim as sim

from ..Configuration import Layout, Scenario
from ..Simulation import SimLayout, SimScenario
from ..Simulation.SimMachine import SimMachine
from ..SimulationInterface.InterfaceTypes import Policy
from ..SimulationInterface.SimulationBridge import SimulationBridge
from ..GlobalEvaluation.GlobalSimulationEvaluation import GlobalSimulationMetrics


class SimulationRunner:
    """Führt eine übergebene Policy ohne 3D-Anzeige aus und sammelt Kennzahlen."""

    def __init__(self, layout: Layout, scenario: Scenario, till: float = sim.inf):
        self.layout = layout
        self.scenario = scenario
        self.till = till

    def run_policy(self, policy: Policy, seed: int) -> GlobalSimulationMetrics:
        """Startet eine Simulation mit dieser Policy und diesem Seed."""
        sim.yieldless(False)

        # Reproduzierbarer Simulations- und Qualitätszufall.
        random.seed(seed)
        SimMachine.QUALITY_SEED = int(seed)

        env = sim.Environment(time_unit="hours", random_seed=seed)
        bridge = SimulationBridge(policy, env=env)
        sim_layout = SimLayout(self.layout, self.scenario, bridge, env=env)
        sim_scenario = SimScenario(
            self.layout,
            self.scenario,
            sim_layout.store_start,
            bridge,
            env=env,
        )
        try:
            env.run(till=self.till)
        except sim.SimulationStopped:
            # Der CompletionWatcher beendet fertige Läufe kontrolliert.
            pass
        metrics = self.collect_global_metrics(sim_layout, sim_scenario, env.now())

        # Unfertige Läufe dürfen nicht als gültiges Optimierungsergebnis gelten.
        if metrics.unfinished_jobs > 0:
            raise RuntimeError(
                "The simulation ended while "
                f"{metrics.unfinished_jobs} job(s) were still unfinished."
            )

        return metrics

    def collect_global_metrics(
        self,
        sim_layout: SimLayout,
        sim_scenario: SimScenario,
        simulation_end_time: float,
    ) -> GlobalSimulationMetrics:
        """Liest Produktionskennzahlen aus Jobs, Robotern und Maschinen."""
        jobs = [job for order in sim_scenario.sim_orders for job in order.sim_jobs]

        completed_times = []
        total_tardiness = 0.0
        unfinished_jobs = 0
        rework_job_count = 0
        scrap_job_count = 0
        downgraded_job_count = 0
        intact_jobs = 0
        total_defect_count = 0
        total_rework_count = 0

        for job in jobs:
            # Ereignisse zählen auch bei unfertigen Jobs, Abschlusskennzahlen nicht.
            total_defect_count += job.defect_count
            total_rework_count += job.rework_count
            if job.completed_time is None:
                unfinished_jobs += 1
                continue

            completion_time = float(job.completed_time)
            completed_times.append(completion_time)
            # Herabgestufte intakte Jobs werden getrennt gezählt.
            final_state = job.general_state.get()
            if final_state == "intact":
                if job.downgraded:
                    downgraded_job_count += 1
                else:
                    intact_jobs += 1
            elif final_state == "scrap":
                scrap_job_count += 1

            # Verspätung pro Job; frühe Abschlüsse gleichen keine Verspätung aus.
            total_tardiness += max(
                0.0,
                completion_time - float(job.order.latest_end_time),
            )

            # Für die Nacharbeitsquote zählt jeder abgeschlossene Job höchstens einmal.
            if job.rework_count > 0:
                rework_job_count += 1

        production_start_time = min(
            (float(job.order.earliest_start_time) for job in jobs),
            default=0.0,
        )
        # Ohne abgeschlossenen Job dient das Simulationsende als Endpunkt.
        production_end_time = (
            max(completed_times) if completed_times else float(simulation_end_time)
        )
        makespan = max(0.0, production_end_time - production_start_time)

        robots = [sim_layout.sim_main_robot]
        for sim_corridor in sim_layout.sim_corridors:
            for arm in (sim_corridor.sim_arm_left, sim_corridor.sim_arm_right):
                if arm.machineCount() > 0:
                    robots.append(arm.sim_arm_robot)

        total_transport_time = 0.0
        for robot in robots:
            for state in ("moving_x", "moving_y", "moving_z"):
                total_transport_time += robot.state_move.value.value_duration(state)

        tool_change_time = 0.0
        for machine in sim_layout.simMachines():
            for state in ("mounting", "unmounting"):
                tool_change_time += machine.state.value.value_duration(state)

        return GlobalSimulationMetrics(
            makespan=makespan,
            total_tardiness=total_tardiness,
            total_transport_time=total_transport_time,
            tool_change_time=tool_change_time,
            rework_job_count=rework_job_count,
            scrap_job_count=scrap_job_count,
            unfinished_jobs=unfinished_jobs,
            total_jobs=len(jobs),
            completed_jobs=len(completed_times),
            intact_jobs=intact_jobs,
            total_defect_count=total_defect_count,
            total_rework_count=total_rework_count,
            downgraded_job_count=downgraded_job_count,
        )
