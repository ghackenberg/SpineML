from __future__ import annotations

import random
from typing import Any

from ...SimulationInterface.InterfaceTypes import (
    ActionEvaluator,
    ActionSelector,
    PolicyDecision,
    PolicyObservation,
    is_wait_action,
)


class HeuristicActionSelector(ActionSelector):
    # Toleranz für Aktionen, deren Bewertung nahe am besten Ergebnis liegt.
    SCORE_TOLERANCE = 0.05
    # Wahrscheinlichkeit, gelegentlich eine fast gleich gute Alternative zu testen.
    EXPLORATION_EPSILON = 0.10

    def __init__(self, rng: random.Random | None = None):
        # Ein eigener Generator trennt Policy-Zufall von Simulationszufall.
        self.random = rng if rng is not None else random

    # Bewertet die erzeugten Kandidaten und gibt die ausgewählte Aktion zurück.
    def select_action(
        self,
        actions: list[dict[str, Any]],
        *,
        evaluator: ActionEvaluator,
        observation: PolicyObservation,
        target_id: str,
    ) -> PolicyDecision:
        # Ohne Kandidaten kann für dieses Objekt keine Aktion ausgewählt werden.
        if len(actions) == 0:
            return PolicyDecision([])

        # Speichert jede Aktion unverändert gemeinsam mit ihrer Bewertung.
        evaluated_actions = []

        # Der Generator hat alle Payload-Werte bereits eingetragen.
        for action in actions:
            score = evaluator.evaluate_action(action, observation)
            evaluated_action = (action, score)
            evaluated_actions.append(evaluated_action)

        # Ermittelt den höchsten Score aller Kandidaten.
        max_score = evaluated_actions[0][1]

        for evaluated_action in evaluated_actions:
            score = evaluated_action[1]
            if score > max_score:
                max_score = score

        # Sammelt die exakt besten und die fast gleich guten Aktionen.
        best_actions = []
        near_best_actions = []

        for evaluated_action in evaluated_actions:
            action = evaluated_action[0]
            score = evaluated_action[1]

            # Nimmt die Aktion auf, wenn sie exakt den höchsten Score besitzt.
            if score == max_score:
                best_actions.append(action)
            # Nimmt die Aktion auf, wenn ihr Score mindestens den Schwellenwert erreicht;
            if score >= max_score - self.SCORE_TOLERANCE:
                near_best_actions.append(action)

        # Exploration: Mit kleiner Wahrscheinlichkeit wird eine produktive Alternative getestet.
        if near_best_actions and self.random.random() < self.EXPLORATION_EPSILON:
            exploratory_actions = []
            # Entfernt die exakt besten Aktionen, damit nur echte Alternativen erkundet werden.
            for action in near_best_actions:
                if action not in best_actions:
                    exploratory_actions.append(action)
            productive_alternatives = []
            # Bevorzugt ausführbare Aktionen gegenüber reinen Warteaktionen.
            for action in exploratory_actions:
                if not is_wait_action(action["action_type"]):
                    productive_alternatives.append(action)
            # Verwendet die gefilterten produktiven Aktionen, wenn mindestens eine vorhanden ist.
            if productive_alternatives:
                exploratory_actions = productive_alternatives
            # Wählt eine erkundete Alternative; falls keine existiert, eine exakt beste Aktion.
            selected_action = self.random.choice(exploratory_actions or best_actions)
        else:
            # Wenn keine Exploration stattfindet, wird zufällig eine exakt beste Aktion gewählt.
            selected_action = self.random.choice(best_actions)
        # Verpackt die Auswahl als PolicyDecision für das Zielobjekt.
        return PolicyDecision.with_single_selected_action(
            selected_action,
            target_id,
        )
