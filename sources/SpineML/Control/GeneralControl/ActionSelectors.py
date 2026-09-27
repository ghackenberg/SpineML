from __future__ import annotations

import random
from typing import Any

from ..Interface.InterfaceTypes import (
    ActionEvaluator,
    ActionSelector,
    PolicyDecision,
    PolicyObservation,
    is_wait_action,
)


class BaselineActionSelector(ActionSelector):
    # Toleranz für Aktionen, deren Bewertung nahe am besten Ergebnis liegt.
    SCORE_TOLERANCE = 0.05
    # Wahrscheinlichkeit, gelegentlich eine fast gleich gute Alternative zu testen.
    EXPLORATION_EPSILON = 0.10
    # Bereitet alle Kandidaten vor, bewertet sie und gibt die ausgewählte Aktion zurück.
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

        # Speichert jede vorbereitete Aktion gemeinsam mit ihrer Bewertung.
        evaluated_actions = []

        # Ergänzt zuerst dynamische Payload-Werte und bewertet danach jeden Kandidaten.
        for action in actions:
            prepared_action = evaluator.prepare_action_candidate(
                action,
                observation,
            )
            score = evaluator.evaluate_action(prepared_action, observation)
            evaluated_action = (prepared_action, score)
            evaluated_actions.append(evaluated_action)

        # Ermittelt den höchsten Score aller vorbereiteten Aktionen.
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
        if near_best_actions and random.random() < self.EXPLORATION_EPSILON:
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
            selected_action = random.choice(exploratory_actions or best_actions)
        else:
            # Wenn keine Exploration stattfindet, wird zufällig eine exakt beste Aktion gewählt.
            selected_action = random.choice(best_actions)
        # Verpackt die Auswahl als PolicyDecision für das Zielobjekt.
        return PolicyDecision.with_single_selected_action(
            selected_action,
            target_id,
        )
