from __future__ import annotations

import random

import salabim as sim

from ...Configuration import (
    Layout,
    Scenario,
)
from ...Simulation import SimLayout, SimScenario
from ...Simulation.SimMachine import SimMachine
from ..GeneralControl.GeneratorSelectorPolicy import GeneratorSelectorPolicy
from ..SimulationBridge.SimulationBridge import SimulationBridge
from .GlobalSimulationEvaluation import GlobalSimulationMetrics
from .HeuristicWeights import HeuristicWeights
from .LocalHeuristicActionEvaluator import (
    LocalHeuristicActionEvaluator,
)


class SpineMLSimulationRunner:
    """Führt einen vollständigen headless SpineML-Lauf für Gewichte und Seed aus."""

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

    # Führt einen vollständigen Simulationslauf mit einem Gewichtssatz und Seed aus
    # und gibt die daraus berechneten globalen Kennzahlen zurück.
    def __call__(
        self,
        weights: HeuristicWeights,
        seed: int,
    ) -> GlobalSimulationMetrics:
        sim.yieldless(False)
     
        # Setzt den Python-Zufallszahlengenerator auf diesen Seed für reproduzierbare Zufallswerte.
        random.seed(seed)
        # Übergibt den Seed an SimMachine für reproduzierbare Defekt- und Qualitätsereignisse.
        SimMachine.QUALITY_SEED = int(seed)

        env = sim.Environment(time_unit="hours", random_seed=seed)
        evaluator = LocalHeuristicActionEvaluator(
            weights,
        )
        policy = GeneratorSelectorPolicy(action_evaluator=evaluator)
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

        # Ein Lauf mit unfertigen Jobs darf nicht als gültiges
        # Optimierungsergebnis weiterverwendet werden.
        if metrics.unfinished_jobs > 0:
            raise RuntimeError(
                "Die Simulation wurde beendet, obwohl noch "
                f"{metrics.unfinished_jobs} Job(s) nicht fertiggestellt waren."
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
        nacharbeit_job_count = 0.0
        ausschuss_job_count = 0.0
        downgraded_job_count = 0.0
        intact_jobs = 0
        defect_jobs = 0
        order_completion_times = {}
        unfinished_orders = set()

        for job in jobs:
            # Prüft, ob dieser Job mindestens einen erkannten Defekt hat.
            if getattr(job, "defect_count", 0) > 0:
                # Zählt den Job für die globale Defektquote höchstens einmal.
                defect_jobs += 1
            # Prüft, ob der Job als herabgestuft markiert wurde.
            if getattr(job, "downgraded", False):
                # Zählt den herabgestuften Job für die globale Herabstufungsquote.
                downgraded_job_count += 1.0
            # Prüft, ob der Job noch keinen Abschlusszeitpunkt besitzt.
            if job.completed_time is None:
                # Zählt den Job als unfertig und merkt sich den betroffenen Auftrag.
                unfinished_jobs += 1
                unfinished_orders.add(job.order.name)
                # Überspringt die Abschlussverarbeitung für diesen unfertigen Job.
                continue
            else:
                # Speichert die Abschlusszeit eines fertiggestellten Jobs.
                completed_times.append(float(job.completed_time))
                # Zählt den Job als intakt, wenn sein Produktionszustand intakt ist.
                if job.general_state.get() == "intakt":
                    intact_jobs += 1
                # Übernimmt die Abschlusszeit für die spätere Auftragsauswertung.
                completion_time = float(job.completed_time)

            # Liest den Namen des Auftrags, zu dem der aktuelle Job gehört.
            order_name = job.order.name

            # Speichert für diesen Auftrag den spätesten Abschlusszeitpunkt
            # aller bisher verarbeiteten fertigen Jobs.
            order_completion_times[order_name] = max(
                # Abschlusszeitpunkt des aktuell verarbeiteten Jobs.
                completion_time,
                # Bisher gespeicherter Zeitpunkt; 0.0 gilt beim ersten Job.
                order_completion_times.get(order_name, 0.0),
            )

            nacharbeit_job_count += (
                1.0 if getattr(job, "nacharbeit_count", 0) > 0 else 0.0
            )
            ausschuss_job_count += float(getattr(job, "ausschuss_count", 0))

        # Berechnet pro vollständig abgeschlossenem Auftrag die Verspätung anhand
        # seines spätesten Job-Abschlusses und addiert sie zu total_tardiness.
        for order in {job.order for job in jobs}:
            if order.name in unfinished_orders:
                continue
            completion_time = order_completion_times.get(order.name)
            if completion_time is None:
                continue
            # Berechnet und addiert für jeden vollständig abgeschlossenen Auftrag
            # genau einmal die positive Verspätung gegenüber latest_end_time.
            total_tardiness += max(
                0.0,
                completion_time - float(order.latest_end_time),
            )

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
        blocking_time = 0.0
        for machine in sim_layout.simMachines():
            tool_change_time += machine.state.value.value_duration("mounting")
            tool_change_time += machine.state.value.value_duration(
                "unmounting"
            )
            blocking_time += machine.state.value.value_duration("blocked")

        return GlobalSimulationMetrics(
            makespan=makespan,
            total_tardiness=total_tardiness,
            total_transport_time=total_transport_time,
            tool_change_time=tool_change_time,
            blocking_time=blocking_time,
            nacharbeit_job_count=nacharbeit_job_count,
            ausschuss_job_count=ausschuss_job_count,
            unfinished_jobs=unfinished_jobs,
            total_jobs=len(jobs),
            completed_jobs=len(completed_times),
            intact_jobs=intact_jobs,
            defect_jobs=defect_jobs,
            downgraded_job_count=downgraded_job_count,
        )
