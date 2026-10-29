"""Lädt Layout und Szenario ohne einen direkten Simulationsstart."""

from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path
import re
import runpy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..Configuration import Layout, Scenario


# Die Datei liegt zwei Verzeichnisebenen unter dem Sources-Verzeichnis.
SOURCES_DIRECTORY = Path(__file__).resolve().parents[2]
EXAMPLES_DIRECTORY = SOURCES_DIRECTORY / "examples"
NORMAL_EXAMPLES_DIRECTORY = EXAMPLES_DIRECTORY / "normal"
OPTIMIZATION_EXAMPLES_DIRECTORY = EXAMPLES_DIRECTORY / "optimization"


# Sucht die Beispieldatei, ohne ihre Modelldefinition auszuführen.
def _resolve_model_path(model_file: str | Path) -> Path:
    """Findet eine Beispieldatei im Arbeitsordner oder in einem Examples-Ordner."""
    requested = Path(str(model_file))
    requested_names = [requested]

    example_number = re.fullmatch(
        r"example[-_]?(\d+)(\.py)?",
        requested.name,
        flags=re.IGNORECASE,
    )
    if example_number:
        suffix = example_number.group(2) or requested.suffix
        requested_names.append(
            requested.with_name(
                f"example-{example_number.group(1)}{suffix}"
            )
        )

    possible_paths = []
    for requested_name in requested_names:
        if requested_name.is_absolute():
            possible_paths.append(requested_name)
        else:
            possible_paths.append(Path.cwd() / requested_name)
            possible_paths.append(SOURCES_DIRECTORY / requested_name)
            possible_paths.append(NORMAL_EXAMPLES_DIRECTORY / requested_name)
            possible_paths.append(OPTIMIZATION_EXAMPLES_DIRECTORY / requested_name)

    expanded_paths = []
    for path in possible_paths:
        expanded_paths.append(path)
        if path.suffix == "":
            expanded_paths.append(path.with_suffix(".py"))

    for path in expanded_paths:
        if path.is_file() and path.suffix == ".py":
            return path.resolve()

    searched = "\n".join(str(path) for path in expanded_paths)
    raise FileNotFoundError(
        f"Beispieldatei {model_file!r} wurde nicht gefunden. Gesucht wurde in:\n{searched}"
    )


# Wählt das in einem simulate-Aufruf angegebene Layout-Szenario-Paar aus.
def _find_layout_and_scenario(
    model: dict[str, object],
    model_path: Path,
) -> tuple[Layout, Scenario]:
    """Liest und wählt die Konfiguration des Beispiels für die Optimierung."""
    from ..Configuration import Layout, Scenario

    layouts = []
    scenarios = []
    for name, value in model.items():
        if isinstance(value, Layout):
            layouts.append((name, value))
        if isinstance(value, Scenario):
            scenarios.append((name, value))

    # Die AST-Auswertung führt die Modelldatei kein zweites Mal aus.
    source = model_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(model_path))
    simulate_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "simulate":
            continue
        simulate_calls.append(node)

    simulate_calls.sort(
        key=lambda node: (
            getattr(node, "lineno", 0),
            getattr(node, "col_offset", 0),
        )
    )
    for node in simulate_calls:
        if len(node.args) < 2:
            continue
        layout_node = node.args[0]
        scenario_node = node.args[1]
        if not isinstance(layout_node, ast.Name):
            continue
        if not isinstance(scenario_node, ast.Name):
            continue

        layout = model.get(layout_node.id)
        scenario = model.get(scenario_node.id)
        if layout is not None and scenario is not None:
            return layout, scenario

    if len(layouts) == 1 and len(scenarios) == 1:
        return layouts[0][1], scenarios[0][1]

    layout_names = [name for name, value in layouts]
    scenario_names = [name for name, value in scenarios]
    raise ValueError(
        "Layout und Szenario konnten nicht eindeutig ausgewählt werden. "
        f"Layouts: {layout_names}; Szenarien: {scenario_names}. "
        "Im Beispiel muss ein simulate(layout, scenario)-Aufruf vorhanden sein."
    )


@contextmanager
# Unterdrückt den direkten Simulationsaufruf während des Modellladens.
def _suppress_model_visualization():
    """Verhindert, dass ein Beispiel beim Laden selbst eine Simulation startet."""
    import SpineML

    original_simulate = getattr(SpineML, "simulate", None)
    SpineML.simulate = lambda *args, **kwargs: None
    try:
        yield
    finally:
        if original_simulate is not None:
            SpineML.simulate = original_simulate


# Gibt wie der bisherige Lader die globalen Variablen des Modells zurück.
def _load_model(model_path: Path) -> dict[str, object]:
    """Führt nur die Modelldefinition aus und gibt deren globale Variablen zurück."""
    with _suppress_model_visualization():
        return runpy.run_path(str(model_path), run_name="spine_model")


# Öffentlicher Einstieg für direkte Läufe und die Initialisierung eines Workers.
def load_layout_and_scenario(model_path: str | Path) -> tuple[Layout, Scenario]:
    """Lädt ein Beispiel ohne Simulationsstart und liefert Layout und Szenario."""
    resolved_path = _resolve_model_path(model_path)
    model = _load_model(resolved_path)
    return _find_layout_and_scenario(model, resolved_path)
