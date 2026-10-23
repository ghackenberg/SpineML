from __future__ import annotations

import random

import salabim as sim

from ...Configuration import (
    Layout,
    Scenario,
)
from ...Simulation import SimLayout, SimScenario
from ...Simulation.SimMachine import SimMachine
from ..GeneralControl.ActionSelectors import BaselineActionSelector
from ..GeneralControl.GeneratorSelectorPolicy import GeneratorSelectorPolicy
from ..Interface.InterfaceTypes import Policy
from ..SimulationBridge.SimulationBridge import SimulationBridge
from .GlobalSimulationEvaluation import GlobalSimulationMetrics
from .HeuristicWeights import HeuristicWeights
from .LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)


class SpineMLSimulationRunner:
    """Run a headless SpineML simulation with heuristic weights or any Policy."""

    # Speichert Layout, Szenario und die maximale Simulationszeit für spätere Läufe.
    def __init__(
        self,
        layout: Layout,
        scenario: Scenario,
        till: float = sim.inf,
    ):
        self.layout = layout
        self.scenario = scenario
        self.till = till

    # Erstellt die heuristische Policy für einen Gewichtssatz und einen Seed.
    def __call__(
        self,
        weights: HeuristicWeights,
        seed: int,
    ) -> GlobalSimulationMetrics:
        evaluator = LocalHeuristicActionEvaluator(weights)
        policy = GeneratorSelectorPolicy(
            action_evaluator=evaluator,
            action_selector=BaselineActionSelector(rng=random.Random(seed)),
        )
        return self.run_policy(policy, seed)

    def run_policy(self, policy: Policy, seed: int) -> GlobalSimulationMetrics:
        """Führt die übergebene Policy über dieselbe Bridge aus und misst die Ergebnisse."""
        sim.yieldless(False)
     
        # Setzt den Python-Zufallszahlengenerator auf diesen Seed für reproduzierbare Zufallswerte.
        random.seed(seed)
        # Übergibt den Seed an SimMachine für reproduzierbare Defect- und Qualitätsereignisse.
        SimMachine.QUALITY_SEED = int(seed)

        env = sim.Environment(time_unit="hours", random_seed=seed)
        bridge = SimulationBridge(policy, env=env)
        sim_layout = SimLayout(
            self.layout,
            self.scenario,
            bridge,
            env=env,
        )
        sim_scenario = SimScenario(
            self.layout,
            self.scenario,
            sim_layout.store_start,
            bridge,
            env=env,
        )

       
        # Startet die Salabim-Simulation bis zur festgelegten Endzeit oder bis
        # die SimCompletionWatcher-Komponente alle Jobs als fertig erkennt.
        try:
            # Führt alle Simulationsprozesse bis self.till aus.
            env.run(till=self.till)
        # Behandelt das kontrollierte, normale Ende durch SimulationStopped.
        except sim.SimulationStopped:
            # Bei diesem normalen Simulationsende ist keine Fehlermeldung nötig.
            pass
        # Sammelt nach dem normalen Laufende oder dem kontrollierten
        # SimulationStopped die globalen Kennzahlen und gibt sie zurück.
        metrics = self.collect_global_metrics(
            # Übergibt das Laufzeit-Layout mit Maschinen, Stores und Robotern.
            sim_layout,
            # Übergibt das Laufzeit-Szenario mit Aufträgen und Jobs.
            sim_scenario,
            # Übergibt die tatsächliche Simulationsendzeit.
            env.now(),
        )

        # A run with unfinished jobs must not be reused as a valid
        # optimization result.
        if metrics.unfinished_jobs > 0:
            raise RuntimeError(
                "The simulation ended while "
                f"{metrics.unfinished_jobs} job(s) were still unfinished."
            )

        return metrics

    # Sammelt Job-, Zeit-, Qualitäts- und Betriebsdaten und erstellt daraus
    # die globalen Kennzahlen des abgeschlossenen Simulationslaufs.
    def collect_global_metrics(
        self,
        sim_layout: SimLayout,
        sim_scenario: SimScenario,
        simulation_end_time: float,
    ) -> GlobalSimulationMetrics:
        jobs = []
        for sim_order in sim_scenario.sim_orders:
            jobs.extend(sim_order.sim_jobs)

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
            # Gesamtanzahl der Defekte und Nacharbeiten über alle Jobs aufsummieren.
            total_defect_count += job.defect_count
            total_rework_count += job.rework_count
            # Prüft, ob der Job noch keinen Abschlusszeitpunkt besitzt.
            if job.completed_time is None:
                # Unfertige Jobs haben noch keinen auswertbaren Abschlusszeitpunkt.
                unfinished_jobs += 1
                # Skip completion processing for this unfinished job.
                continue

            # Speichert die Abschlusszeit dieses Jobs für den Makespan.
            completion_time = float(job.completed_time)
            completed_times.append(completion_time)
            # Endzustände getrennt zählen; jeder abgeschlossene Job zählt einmal.
            final_state = job.general_state.get()
            if final_state == "intact":
                if job.downgraded:
                    downgraded_job_count += 1
                else:
                    intact_jobs += 1
            elif final_state == "scrap":
                scrap_job_count += 1

            # Jeder abgeschlossene Job zählt einzeln gegenüber der Deadline
            # seines Auftrags. Frühe Abschlüsse gleichen keine Verspätung aus.
            total_tardiness += max(
                0.0,
                completion_time - float(job.order.latest_end_time),
            )

            # Zählt für die Nacharbeitsquote abgeschlossene Jobs mit mindestens einer Nacharbeit.
            # Mehrere Nacharbeiten am selben Job erhöhen diesen Zähler trotzdem nur um 1.
            if job.rework_count > 0:
                rework_job_count += 1

        if jobs:
            production_start_time = min(
                float(job.order.earliest_start_time)
                for job in jobs
            )
        else:
            production_start_time = 0.0

        # Wenn mindestens ein Job fertig ist, endet der Makespan beim spätesten
        # Abschlusszeitpunkt eines fertigen Jobs.
        if completed_times:
            makespan = max(
                0.0,
                max(completed_times) - production_start_time,
            )
        # Wenn kein Job fertig ist, wird das Simulationsende als Endpunkt verwendet.
        else:
            makespan = max(
                0.0,
                float(simulation_end_time) - production_start_time,
            )

        robots = [sim_layout.sim_main_robot]
        for sim_corridor in sim_layout.sim_corridors:
            if sim_corridor.sim_arm_left.machineCount() > 0:
                robots.append(sim_corridor.sim_arm_left.sim_arm_robot)
            if sim_corridor.sim_arm_right.machineCount() > 0:
                robots.append(sim_corridor.sim_arm_right.sim_arm_robot)

        total_transport_time = 0.0
        for robot in robots:
            total_transport_time += robot.state_move.value.value_duration(
                "moving_x"
            )
            total_transport_time += robot.state_move.value.value_duration(
                "moving_y"
            )
            total_transport_time += robot.state_move.value.value_duration(
                "moving_z"
            )

        tool_change_time = 0.0
        for machine in sim_layout.simMachines():
            tool_change_time += machine.state.value.value_duration("mounting")
            tool_change_time += machine.state.value.value_duration(
                "unmounting"
            )

        return GlobalSimulationMetrics(
            # Produktionsdauer vom frühesten erlaubten Auftragsstart bis zum letzten Jobabschluss.
            # Ohne abgeschlossenen Job wird stattdessen das Simulationsende verwendet.
            makespan=makespan,
            # Summe der positiven Verspätungszeiten aller abgeschlossenen Jobs.
            total_tardiness=total_tardiness,
            # Summe der Bewegungszeiten aller Roboter in X-, Y- und Z-Richtung.
            total_transport_time=total_transport_time,
            # Summe der Werkzeug-Montage- und Demontagezeiten aller Maschinen.
            tool_change_time=tool_change_time,
            # Anzahl abgeschlossener Jobs mit mindestens einer Nacharbeit; jeder Job zählt einmal.
            rework_job_count=rework_job_count,
            # Anzahl abgeschlossener Jobs mit dem Endzustand 'scrap' (Ausschuss).
            scrap_job_count=scrap_job_count,
            # Anzahl der Jobs ohne Abschlusszeitpunkt.
            unfinished_jobs=unfinished_jobs,
            # Gesamtzahl der Jobs im Szenario.
            total_jobs=len(jobs),
            # Anzahl der Jobs mit einem Abschlusszeitpunkt.
            completed_jobs=len(completed_times),
            # Anzahl abgeschlossener Jobs mit Endzustand 'intact', ohne Herabstufung.
            intact_jobs=intact_jobs,
            # Gesamtzahl erkannter Defekte über alle Jobs, auch mehrere Defekte pro Job.
            total_defect_count=total_defect_count,
            # Summe der Nacharbeitszähler aller Jobs, auch mehrere Nacharbeiten pro Job.
            total_rework_count=total_rework_count,
            # Anzahl abgeschlossener, herabgestufter Jobs mit Endzustand 'intact'.
            downgraded_job_count=downgraded_job_count,
        )
