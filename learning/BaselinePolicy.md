# BaselinePolicy-Notizen

Code-Datei: [BaselinePolicy.py](../sources/SpineML/Control/BaselinePolicy.py)

Diese Datei ist absichtlich einfach formatiert, damit der Markdown-Editor sie sauber anzeigen kann.

Schema pro Methode:

- Input: Was bekommt die Methode?
- Output: Was gibt die Methode zurueck?
- Bedeutung: Welche Regel steckt dahinter?

## Konkretes Grundbeispiel

Viele Methoden bekommen indirekt ein `PolicyObservation` Objekt.

Das ist kein normales Dict, sondern ein kleines Objekt mit zwei wichtigen Informationen:

- `observation.simulation_snapshot`
- `observation.current_object_id`

Konkreter Input:

```
observation = PolicyObservation(
        current_object_id="Order 1:0",
        simulation_snapshot={
            "time": 12.0,
            "states_by_id": {
                "Order 1:0": {
                    "object_type": "order_job",
                    "object_id": "Order 1:0",
                    "job_id": "Order 1:0",
                    "number": 0,
                    "time": 12.0,
                    "product_state": "unconfigured",
                    "target_product_type": ProductType("Fertigteil"),
                    "quantity": 1,
                    "earliest_start_time": 10.0,
                    "latest_end_time": 100.0,
                    "released": False,
                    "priority_assigned": False,
                    "queue_priority": 0.0,
                    "selected_operation": None,
                    "selected_machine": None,
                    "completed_time": None,
                    "due_state": "unknown",
                    "cancelled": False,
                    "downgraded": False,
                    "downgrade_product_type": None,
                    "defective": False,
                    "defect_detected_time": None,
                    "defect_operation": None,
                    "defect_machine": None,
                    "defect_product_state_before": None,
                    "defect_product_state_target": None,
                    "defect_severity": None,
                    "defect_recovery_strategy": None,
                    "action_store_empty": True,
                    "last_report_time": 12.0,
                },
                "Machine 1.1.1": {
                    "object_type": "machine",
                    "object_id": "Machine 1.1.1",
                    "machine_name": "Machine 1.1.1",
                    "state": "waiting",
                    "current_job": None,
                    "has_current_job": False,
                    "mounted_tool_type": ToolType("Bohrer"),
                    "mounted_tool_type_name": "Bohrer",
                    "input_storage": {
                        "store_name": "Machine 1.1.1 input",
                        "count": 0,
                        "available_capacity": 10,
                    },
                    "output_storage": {
                        "store_name": "Machine 1.1.1 output",
                        "count": 0,
                        "available_capacity": 10,
                    },
                    "action_store_empty": True,
                    "last_report_time": 11.5,
                },
                "Main robot": {
                    "object_type": "main_robot",
                    "object_id": "Main robot",
                    "robot_name": "Main robot",
                    "current_job": None,
                    "is_empty": True,
                    "is_loaded": False,
                    "move_state": "waiting",
                    "load_state": "empty",
                    "action_store_empty": True,
                    "last_report_time": 11.0,
                },
            },
        }
    )
```

Wichtig:

- `states_by_id` ist das aeussere Dict.
- Der aeussere Key ist die `object_id`, z.B. `Order 1:0`.
- Der aeussere Value ist das innere Dict mit dem Zustand dieses Objekts.
- `current_object_id` sagt, fuer welches Objekt gerade eine Einzelentscheidung getroffen wird.
- Die Policy sieht IDs und Zustandsdaten.
- Die echten Simulationsobjekte bleiben bei der Bridge.

## Konkretes Action-Output-Beispiel

Wenn die Policy fuer `Order 1:0` eine Aktion erzeugt, kommt am Ende so etwas heraus:

```
SelectedActionPolicy(
        actions=[
            SelectedObjectAction(
                target_id="Order 1:0",
                action_type="configure_order_job",
                payload={
                    "action_type": "configure_order_job",
                    "action_category": "order_job_state",
                    "action_intent": "set_initial_product_state",
                    "product_state": "Rohteil",
                    "selected_operation": None,
                    "selected_machine": None,
                    "released": False,
                    "priority_assigned": False,
                    "queue_priority": 0.0,
                    "completed_time": None,
                    "due_state": "unknown",
                    "cancelled": False,
                    "downgraded": False,
                    "downgrade_product_type": None,
                    "defective": False,
                    "defect_detected_time": None,
                    "defect_operation": None,
                    "defect_machine": None,
                    "defect_product_state_before": None,
                    "defect_product_state_target": None,
                    "defect_severity": None,
                    "defect_recovery_strategy": None,
                },
            )
        ]
    )
```

Bedeutung:

- `SelectedActionPolicy` ist die Gesamtentscheidung der Policy.
- `actions` ist eine Liste.
- Jedes Element ist eine Aktion fuer ein Objekt.
- `target_id="Order 1:0"` sagt der Bridge, welches Simulationsobjekt diese Aktion bekommt.
- Die Bridge uebersetzt diese ID spaeter intern wieder zum echten `SimOrderJob`.

## __init__

- Input: optional `action_selector`
- Output: neues `BaselinePolicy` Objekt
- Bedeutung: setzt `self.action_selector`; wenn keiner uebergeben wird, nutzt die Policy `BaselineActionSelector`

## select_action

- Input: `PolicyObservation` mit Gesamt-Snapshot aller Objekte
- Output: `SelectedActionPolicy` mit mehreren `SelectedObjectAction`
- Bedeutung: geht ueber alle Objekte; wenn `action_store_empty=True`, wird fuer dieses Objekt eine Aktion erzeugt

Konkreter Input:

```
observation.simulation_snapshot = {
        "time": 12.0,
        "states_by_id": {
            "Order 1:0": {
                "object_type": "order_job",
                "object_id": "Order 1:0",
                "product_state": "unconfigured",
                "released": False,
                "priority_assigned": False,
                "defective": False,
                "completed_time": None,
                "due_state": "unknown",
                "action_store_empty": True,
            },
            "Machine 1.1.1": {
                "object_type": "machine",
                "object_id": "Machine 1.1.1",
                "current_job": None,
                "action_store_empty": False,
            },
        },
    }
```

Ablauf:

- Die Schleife liest zuerst `Order 1:0`.
- `action_store_empty=True`, also darf eine Aktion erzeugt werden.
- Danach liest sie `Machine 1.1.1`.
- `action_store_empty=False`, also wird diese Maschine mit `continue` uebersprungen.

Konkreter Output:

```
SelectedActionPolicy(
        actions=[
            SelectedObjectAction(
                target_id="Order 1:0",
                action_type="configure_order_job",
                payload={...},
            )
        ]
    )
```

## current_state

- Input: `PolicyObservation` mit Gesamt-Snapshot und `current_object_id`
- Bedeutung: gibt das innere Dict des aktuellen Objekts zurueck

Konkreter Input:

```
observation.current_object_id = "Order 1:0"
```

```
observation.simulation_snapshot = {
        "time": 12.0,
        "states_by_id": {
            "Order 1:0": {
                "object_type": "order_job",
                "object_id": "Order 1:0",
                "product_state": "Rohteil",
                "released": True,
            },
            "Machine 1.1.1": {
                "object_type": "machine",
                "object_id": "Machine 1.1.1",
                "state": "waiting",
            },
        },
    }
```

Zwischenschritt:

```
states_by_id = observation.simulation_snapshot["states_by_id"]
    current_object_id = observation.current_object_id
    current_state = states_by_id[current_object_id]
```

Konkreter Output:

```
{
        "object_type": "order_job",
        "object_id": "Order 1:0",
        "product_state": "Rohteil",
        "released": True,
    }
```

Wichtig:

- Die Methode nimmt direkt den Zustand mit `current_object_id`.
- Dadurch bleibt der ganze Snapshot erhalten.
- Danach kann die Policy z.B. `current_state["product_state"]` lesen.

## states_of_type

- Input: `snapshot`, `object_type`
- Beispiel-Input: `object_type="machine"`
- Output: Liste aller Objektzustaende mit `object_type == "machine"`
- Bedeutung: filtert den Gesamt-Snapshot nach Objekttyp

## is_wait_only_action

- Input: `action_type`, z.B. `wait_machine`
- Output: `True` oder `False`
- Bedeutung: prueft, ob eine Aktion nur Warten bedeutet

## select_single_action

- Input: `PolicyObservation` mit Gesamt-Snapshot und gesetzter `current_object_id`
- Output: `SelectedActionPolicy` mit einer ausgewaehlten Aktion
- Bedeutung: erzeugt moegliche Aktionen und waehlt eine davon aus

Konkreter Input:

```
observation.current_object_id = "Order 1:0"
```

```
observation.simulation_snapshot = {
        "time": 12.0,
        "states_by_id": {
            "Order 1:0": {
                "object_type": "order_job",
                "object_id": "Order 1:0",
                "product_state": "unconfigured",
                "released": False,
                "priority_assigned": False,
                "defective": False,
                "completed_time": None,
                "due_state": "unknown",
            },
            "Machine 1.1.1": {
                "object_type": "machine",
                "object_id": "Machine 1.1.1",
                "state": "waiting",
            },
        },
    }
```

Zwischenschritt:

- `current_state(...)` gibt den Zustand von `Order 1:0` zurueck.
- `generate_actions(...)` erzeugt z.B. `configure_order_job`.
- `with_clean_action_payload(...)` ergaenzt Kategorie und Intent.
- `action_selector.select_action(...)` waehlt eine Aktion aus.

Konkreter Output:

```
SelectedActionPolicy(
        actions=[
            SelectedObjectAction(
                target_id=None,
                action_type="configure_order_job",
                payload={
                    "action_type": "configure_order_job",
                    "action_category": "order_job_state",
                    "action_intent": "set_initial_product_state",
                    "product_state": "Rohteil",
                    "selected_operation": None,
                    "selected_machine": None,
                },
            )
        ]
    )
```

Wichtig:

- `target_id` ist hier noch `None`.
- Die aeussere Methode `select_action` setzt spaeter `target_id="Order 1:0"`.
- Trotzdem kann `select_single_action` den ganzen Snapshot sehen.

## generate_actions

- Input: `PolicyObservation` mit aktuellem Objekt
- Output: Liste moeglicher Action-Dicts
- Bedeutung: verzweigt nach `object_type` und Zustand zu den passenden `create_*_actions`

Konkreter Input fuer unkonfigurierten Job:

```
current_state = {
        "object_type": "order_job",
        "object_id": "Order 1:0",
        "product_state": "unconfigured",
        "released": False,
        "priority_assigned": False,
        "defective": False,
        "completed_time": None,
        "due_state": "unknown",
        "target_product_type": ProductType("Fertigteil"),
    }
```

Regel:

- Wenn `object_type == "main_robot"`: Roboter-Aktionen erzeugen.
- Wenn `object_type == "corridor_arm_robot"`: Armroboter-Aktionen erzeugen.
- Wenn `object_type == "machine"`: Maschinen-Aktionen erzeugen.
- Sonst ist es ein `order_job`.
- Wenn Job defekt ist: Defekt-Aktionen erzeugen.
- Wenn Job fertig ist: Completion-Aktion erzeugen.
- Wenn Job noch unkonfiguriert ist: Configuration-Aktion erzeugen.
- Wenn Job noch keine Prioritaet hat: Priority-Aktion erzeugen.
- Wenn Job noch nicht freigegeben ist: Release-Aktion erzeugen.
- Sonst: Wait-Aktion erzeugen.

Konkreter Output:

```
[
        {
            "action_type": "configure_order_job",
            "payload": {
                "selected_operation": None,
                "selected_machine": None,
                "product_state": "Rohteil",
            },
        }
    ]
```

## select_order_job_defect_action

- Input: defekter `order_job`
- Output: ausgewaehlte Defekt-Recovery-Aktion
- Beispiel-Output: `order_job_reparieren`
- Bedeutung: bevorzugt Reparieren/Neuplanen/Herabstufen/Warten/Abbrechen; bei sehr schwerem Defekt Abbrechen

## select_order_job_completion_action

- Input: fertiggestellter `order_job`
- Output: `complete_order_job`
- Bedeutung: waehlt Aktion zur Bewertung von `due_state`

## select_order_job_configuration_action

- Input: unkonfigurierter `order_job`
- Output: `configure_order_job`
- Bedeutung: waehlt Start-Produktzustand

## select_order_job_priority_action

- Input: Job ohne Prioritaet
- Output: `prioritize_order_job`
- Bedeutung: waehlt Aktion, die `queue_priority` setzt

## select_order_job_release_action

- Input: Job mit Prioritaet, aber noch nicht freigegeben
- Output: `release_order_job`
- Bedeutung: gibt Job fuer Produktion frei

## select_order_job_reconfiguration_action

- Input: Job, dessen Produktionsweg neu geplant werden soll
- Output: `order_job_produktionsweg_neuplanen`
- Bedeutung: setzt geplante Operation und Maschine zurueck

## select_order_job_cancellation_action

- Input: Job, der abgebrochen werden soll
- Output: `order_job_abbrechen`
- Bedeutung: setzt Job auf `cancelled` und `due_state="not-applicable"`

## select_order_job_wait_action

- Input: `order_job`
- Output: `wait_job`
- Bedeutung: Job wartet auf Steuerungsentscheidung

## select_main_robot_task_action

- Input: `main_robot`
- Output: Pick- oder Place-Aktion
- Bedeutung: leerer Roboter pickt; beladener Roboter legt ab

## select_main_robot_pick_action

- Input: leerer Hauptroboter
- Output: `pick_main_robot`
- Bedeutung: waehlt Pick-Aktion aus Startlager oder Korridorpuffer

## select_main_robot_place_action

- Input: beladener Hauptroboter
- Output: `place_main_robot`
- Bedeutung: waehlt Ablage in Endlager oder Korridorpuffer

## select_main_robot_wait_action

- Input: Hauptroboter
- Output: `wait_main_robot`
- Bedeutung: Hauptroboter wartet

## select_corridor_arm_robot_task_action

- Input: Seitenkorridor-Roboter
- Output: Pick- oder Place-Aktion
- Bedeutung: leerer Arm pickt; beladener Arm legt ab

## select_corridor_arm_robot_pick_action

- Input: leerer Armroboter
- Output: `pick_corridor_arm_robot`
- Bedeutung: pickt aus Arm-Input oder Maschinen-Output

## select_corridor_arm_robot_place_action

- Input: beladener Armroboter
- Output: `place_corridor_arm_robot`
- Bedeutung: legt in Maschine, anderen Arm-Puffer oder Main-Robot-Puffer ab

## select_corridor_arm_robot_wait_action

- Input: Armroboter
- Output: `wait_corridor_arm_robot`
- Bedeutung: Armroboter wartet

## select_machine_task_action

- Input: Maschine
- Output: Pick- oder Process-Aktion
- Bedeutung: leere Maschine nimmt Job; beladene Maschine bearbeitet Job

## select_machine_pick_action

- Input: leere Maschine
- Output: `pick_machine_job`
- Bedeutung: Maschine nimmt passenden Job aus Eingangspuffer

## select_machine_process_action

- Input: Maschine mit aktuellem Job
- Output: `process_machine_job`
- Bedeutung: Maschine fuehrt geplante Operation aus

## select_machine_wait_action

- Input: Maschine
- Output: `wait_machine`
- Bedeutung: Maschine wartet

## select_random_action

- Input: Liste von Aktionen
- Output: `SelectedActionPolicy`
- Bedeutung: bereinigt Payloads und waehlt ohne harte Bevorzugung aus

## select_preferred_action

- Input: Liste von Aktionen
- Output: `SelectedActionPolicy`
- Bedeutung: bereinigt Payloads und bevorzugt ausfuehrbare Aktionen

## selected_policy_action

- Input: ein Action-Dict
- Output: `SelectedActionPolicy`
- Bedeutung: verpackt eine einzelne Aktion als Policy-Entscheidung

## with_clean_action_payload

- Input: Action-Dict, z.B. `{"action_type": "process_machine_job", "payload": {...}}`
- Output: Action-Dict mit ergaenzter Payload
- Ergaenzt: `action_type`, `action_category`, `action_intent`, Namen, Store-Infos, Wartezeit
- Bedeutung: normalisiert Aktionen, bevor sie ausgewaehlt oder gesendet werden

## action_category

- Input: `action_type`
- Output: Kategorie wie `transport`, `machine_processing`, `wait`, `order_job_state`
- Bedeutung: ordnet Aktionen grob ein

## action_intent

- Input: `action_type` und `payload`
- Output: Text wie `pick_from_start_storage`
- Bedeutung: beschreibt die Absicht der Aktion

## store_has_items

- Input: Store
- Output: `True`, wenn `store.as_list()` nicht leer ist
- Bedeutung: prueft, ob ein Store Teile/Jobs enthaelt

## store_has_capacity

- Input: Store
- Output: `True`, wenn `available_quantity() > 0`
- Bedeutung: prueft, ob noch freier Platz im Store ist

## store_jobs

- Input: Store
- Output: Liste der Store-Inhalte
- Bedeutung: gibt Jobs aus einem Store zurueck

## job_id

- Input: Job mit `order.name` und `number`
- Output: String, z.B. `Order 1:0`
- Bedeutung: baut stabile Job-ID

## complete_order_job_payload

- Input: `current_state` und partielle `payload`
- Output: vollstaendige Payload mit allen wichtigen Job-Attributen
- Bedeutung: verhindert unvollstaendige Job-Aktionsnachrichten

Konkreter Input:

```
current_state = {
        "layout": Layout("Layout 1"),
        "scenario": Scenario("Scenario 1"),
        "order": Order("Order 1"),
        "number": 0,
        "released": False,
        "priority_assigned": False,
        "queue_priority": 0.0,
        "selected_operation": None,
        "selected_machine": None,
        "product_state": "unconfigured",
        "completed_time": None,
        "due_state": "unknown",
        "cancelled": False,
        "downgraded": False,
        "downgrade_product_type": None,
        "defective": False,
        "defect_detected_time": None,
        "defect_operation": None,
        "defect_machine": None,
        "defect_product_state_before": None,
        "defect_product_state_target": None,
        "defect_severity": None,
        "defect_recovery_strategy": None,
    }
```

```
payload = {
        "released": True,
    }
```

Konkreter Output:

```
{
        "layout": Layout("Layout 1"),
        "scenario": Scenario("Scenario 1"),
        "order": Order("Order 1"),
        "number": 0,
        "released": True,
        "priority_assigned": False,
        "queue_priority": 0.0,
        "selected_operation": None,
        "selected_machine": None,
        "product_state": "unconfigured",
        "completed_time": None,
        "due_state": "unknown",
        "cancelled": False,
        "downgraded": False,
        "downgrade_product_type": None,
        "defective": False,
        "defect_detected_time": None,
        "defect_operation": None,
        "defect_machine": None,
        "defect_product_state_before": None,
        "defect_product_state_target": None,
        "defect_severity": None,
        "defect_recovery_strategy": None,
    }
```

Wichtig:

- Nur `released` wurde aus `payload` ueberschrieben.
- Alle anderen Werte kommen aus `current_state`.

## with_complete_order_job_payloads

- Input: `observation` und Liste von OrderJob-Aktionen
- Output: Aktionen mit vollstaendigen Payloads
- Bedeutung: wendet `complete_order_job_payload` auf jede Aktion an

## estimate_defect_repairable

- Input: `current_state["defect_severity"]`
- Output: `True`, wenn Schweregrad gesetzt und kleiner als `0.7`
- Bedeutung: einfache Heuristik, ob Defekt reparierbar ist

Konkrete Beispiele:

- Input: `{"defect_severity": 0.2}` -> Output: `True`
- Input: `{"defect_severity": 0.69}` -> Output: `True`
- Input: `{"defect_severity": 0.7}` -> Output: `False`
- Input: `{"defect_severity": 0.9}` -> Output: `False`
- Input: `{"defect_severity": None}` -> Output: `False`

## estimate_rework_time

- Input: Defektoperation und Schweregrad
- Output: geschaetzte Reparaturzeit oder `None`
- Bedeutung: je schwerer der Defekt, desto laenger die Nacharbeit

## estimate_rework_success_probability

- Input: Schweregrad
- Output: Erfolgswahrscheinlichkeit
- Bedeutung: je hoeher der Schweregrad, desto niedriger die Erfolgswahrscheinlichkeit

## estimate_rework_cost

- Input: Defektoperation und Schweregrad
- Output: geschaetzte Reparaturkosten oder `None`
- Bedeutung: Kostenheuristik fuer Reparatur

## estimate_scrap_cost

- Input: Ziel-Produkttyp
- Output: geschaetzte Ausschusskosten oder `None`
- Bedeutung: Kostenheuristik fuer Abbruch/Ausschuss

## estimate_slack_time

- Input: `latest_end_time` und aktuelle `time`
- Output: Restzeit
- Beispiel: `100 - 80 = 20`
- Bedeutung: berechnet zeitlichen Spielraum

## estimate_downgrade_quality_score

- Input: Schweregrad
- Output: Qualitaetsscore nach Herabstufung oder `None`
- Bedeutung: schaetzt, ob Herabstufung sinnvoll ist

## machine_available_for_rework

- Input: Maschinen-Observation mit Input- und Output-Storage
- Output: `True`, wenn beide Puffer freie Kapazitaet haben
- Bedeutung: Reparaturmaschine ist nur nutzbar, wenn Ein- und Ausgang nicht voll sind

Konkreter Input:

```
machine_observation = {
        "object_type": "machine",
        "object_id": "Machine 1.1.1",
        "input_storage": {
            "store_name": "Machine 1.1.1 input",
            "available_capacity": 1,
        },
        "output_storage": {
            "store_name": "Machine 1.1.1 output",
            "available_capacity": 2,
        },
    }
```

Konkreter Output:

```
True
```

Gegenbeispiel:

```
input_storage.available_capacity = 0 -> Output False
    output_storage.available_capacity = 0 -> Output False
```

## defect_machine_observation

- Input: `current_state` mit `defect_machine`, plus Snapshot
- Output: Observation der Defektmaschine oder `None`
- Bedeutung: findet im Snapshot die Maschine, auf der der Defekt passiert ist

## find_defect_reconfiguration_routes

- Input: aktueller Produktzustand und Zielprodukttyp
- Output: alternative Routen
- Bedeutung: sucht neue Produktionswege nach Defekt

## can_rework_defect

- Input: Defektzustand, Recovery-Produkttyp, Snapshot
- Output: `True` oder `False`
- Bedeutung: prueft, ob Reparieren moeglich ist

## can_reconfigure_defect

- Input: Defektzustand und Recovery-Produkttyp
- Output: `True`, wenn alternative Route existiert
- Bedeutung: prueft, ob Produktionsweg neu geplant werden kann

## can_wait_defect

- Input: Defektzustand und Wartezeit
- Output: `True`, wenn genug Zeit bleibt
- Bedeutung: prueft, ob Warten erlaubt ist

## can_downgrade_defect

- Input: Defektzustand, Recovery-Produkttyp, Reparierbarkeit
- Output: `True` oder `False`
- Bedeutung: prueft, ob Herabstufen sinnvoll ist

## can_cancel_defect

- Input: Defektzustand und Machbarkeit anderer Recovery-Strategien
- Output: `True` oder `False`
- Bedeutung: prueft, ob Abbrechen sinnvoll ist

## create_pick_actions_for_store

- Input: Action-Typ, Store-Typ, Store, Zusatzpayload
- Output: Pick-Aktionen fuer Jobs in diesem Store
- Bedeutung: Hilfsmethode fuer Roboter/Maschinen-Pick-Aktionen

## product_type_from_name

- Input: Produktname
- Output: `ProductType` oder `None`
- Bedeutung: sucht Produkttyp anhand des Namens

## selectable_routes_for_job

- Input: Job und Layout
- Output: moegliche Routen mit `operation_sequence`, `machine_sequence`, `next_operation`, `next_machine`
- Bedeutung: berechnet moegliche naechste Produktionswege fuer einen Job

## create_order_job_defect_actions

- Input: defekter OrderJob
- Output: Liste moeglicher Recovery-Aktionen
- Beispiele: `order_job_reparieren`, `order_job_produktionsweg_neuplanen`, `downgrade_product`, `order_job_abbrechen`, `wait_job`
- Bedeutung: erzeugt Handlungsspielraum fuer Defektfall

Konkreter Input:

```
current_state = {
        "object_type": "order_job",
        "object_id": "Order 1:0",
        "product_state": "defect",
        "defective": True,
        "defect_detected_time": 30.0,
        "defect_operation": OperationType("Bohren"),
        "defect_machine": Machine("Bohrmaschine 1"),
        "defect_product_state_before": "Rohteil",
        "defect_product_state_target": "Gebohrt",
        "defect_severity": 0.4,
        "defect_recovery_strategy": None,
        "latest_end_time": 100.0,
        "time": 30.0,
    }
```

Moeglicher Output:

```
[
        {
            "action_type": "order_job_reparieren",
            "payload": {
                "defective": False,
                "product_state": "Rohteil",
                "defect_recovery_strategy": "reparieren",
            },
        },
        {
            "action_type": "order_job_produktionsweg_neuplanen",
            "payload": {
                "selected_operation": None,
                "selected_machine": None,
                "product_state": "defect",
                "defect_recovery_strategy": "produktionsweg_neuplanen",
            },
        },
        {
            "action_type": "wait_job",
            "payload": {
                "wait_job": True,
                "defect_recovery_strategy": "warten",
            },
        },
    ]
```

Bedeutung der einzelnen Aktionen:

- `order_job_reparieren`: Defekt wird repariert, Job kann wieder weiterlaufen.
- `order_job_produktionsweg_neuplanen`: aktuelle Route wird verworfen, Policy soll neuen Weg suchen.
- `downgrade_product`: Zielprodukt wird auf niedrigeren Produkttyp gesetzt.
- `order_job_abbrechen`: Job wird abgebrochen.
- `wait_job`: noch keine endgueltige Recovery-Entscheidung.

## create_order_job_defect_cancellation_actions

- Input: defekter OrderJob
- Output: Abbruchaktion
- Bedeutung: erzeugt explizit `order_job_abbrechen`

## create_order_job_completion_actions

- Input: fertiggestellter Job
- Output: `complete_order_job`
- Bedeutung: setzt `due_state` auf `on-time` oder `late`

## create_order_job_configuration_actions

- Input: unkonfigurierter Job
- Output: `configure_order_job`
- Bedeutung: setzt Start-Produktzustand

## create_order_job_priority_actions

- Input: Job ohne Prioritaet
- Output: `prioritize_order_job`
- Bedeutung: setzt `priority_assigned=True` und zufaellige `queue_priority`

## create_order_job_release_actions

- Input: freizugebender Job
- Output: `release_order_job`
- Bedeutung: setzt `released=True` und Ziel-Store auf Startlager

## create_order_job_reconfiguration_actions

- Input: Job, der neu geplant werden soll
- Output: `order_job_produktionsweg_neuplanen`
- Bedeutung: setzt `selected_operation` und `selected_machine` auf `None`

## create_order_job_cancellation_actions

- Input: Job, der abgebrochen werden soll
- Output: `order_job_abbrechen`
- Bedeutung: setzt `cancelled=True`, `product_state="cancelled"` und `due_state="not-applicable"`

## create_order_job_wait_actions

- Input: Job
- Output: `wait_job`
- Bedeutung: erzeugt Warteaktion fuer Steuerungsentscheidung

## create_main_robot_pick_actions

- Input: leerer Hauptroboter
- Output: Pick-Aktionen aus Startlager oder Korridor-Main-Stores
- Bedeutung: erzeugt moegliche Aufnahmen fuer den Hauptroboter

## create_main_robot_place_actions

- Input: beladener Hauptroboter
- Output: Place-Aktionen in Endlager oder Korridorpuffer
- Bedeutung: erzeugt moegliche Ablagen fuer den Hauptroboter

## create_main_robot_wait_actions

- Input: Hauptroboter
- Output: `wait_main_robot`
- Bedeutung: Hauptroboter wartet kurz

## create_corridor_arm_robot_pick_actions

- Input: leerer Armroboter
- Output: Pick-Aktionen aus Arm-Input oder Maschinen-Output
- Bedeutung: erzeugt moegliche Aufnahmen fuer Seitenkorridor-Roboter

## create_corridor_arm_robot_place_actions

- Input: beladener Armroboter
- Output: Place-Aktionen in Maschineninput, anderen Arm-Puffer oder Main-Robot-Puffer
- Bedeutung: erzeugt moegliche Ablagen fuer Seitenkorridor-Roboter

## create_corridor_arm_robot_wait_actions

- Input: Armroboter
- Output: `wait_corridor_arm_robot`
- Bedeutung: Armroboter wartet kurz

## create_machine_pick_actions

- Input: leere Maschine
- Output: `pick_machine_job` fuer passende Jobs im Eingangspuffer
- Bedeutung: Maschine nimmt passenden Job auf

## create_machine_process_actions

- Input: Maschine mit Job und geplanter Operation
- Output: `process_machine_job` oder `wait_machine`
- Bedeutung: erzeugt Bearbeitungsaktion inklusive Werkzeugentscheidung

## create_machine_wait_actions

- Input: Maschine
- Output: `wait_machine`
- Bedeutung: Maschine wartet kurz

## calculate_machine_sequences_from_operation_sequence

- Input: Operationsfolge und Layout
- Output: moegliche Maschinenfolgen
- Bedeutung: ordnet jeder Operation passende Maschinen im Layout zu

## calculate_machine_sequences

- Input: Ziel-Produkttyp und Layout
- Output: alle moeglichen Maschinenfolgen
- Bedeutung: berechnet Maschinenrouten fuer die Herstellung eines Produkttyps

## calculate_operation_sequences_between

- Input: Start-Produkttyp und Ziel-Produkttyp
- Output: Operationsfolgen vom Start zum Ziel
- Bedeutung: sucht Pfade im Produkt-/Operationsgraph

## calculate_operation_sequences

- Input: Ziel-Produkttyp
- Output: alle Operationsfolgen, die diesen Produkttyp herstellen koennen
- Bedeutung: berechnet Produktionswege anhand der Producing-Operations
