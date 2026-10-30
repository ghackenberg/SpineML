"""Lädt die Fabrikkonfiguration und liefert Layout und Szenario zurück."""

from __future__ import annotations

import ast
from pathlib import Path
import re
import runpy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..Configuration import Layout, Scenario


# parents[0] = SimulationExecution, parents[1] = SpineML, parents[2] = sources.
SOURCES_DIRECTORY = Path(__file__).resolve().parents[2]
EXAMPLES_DIRECTORY = SOURCES_DIRECTORY / "examples"
NORMAL_EXAMPLES_DIRECTORY = EXAMPLES_DIRECTORY / "normal"
OPTIMIZATION_EXAMPLES_DIRECTORY = EXAMPLES_DIRECTORY / "optimization"


def _resolve_model_path(model_file: str | Path) -> Path:
    """Sucht die Python-Datei und gibt ihren absoluten Pfad zurück."""
    requested = Path(model_file)
    names = [requested]

    # Erkennt zusätzlich example5 und example_5 als Schreibweisen von example-5.
    match = re.fullmatch(r"example[-_]?(\d+)(\.py)?", requested.name, re.IGNORECASE)
    if match:
        normalized = requested.with_name(f"example-{match.group(1)}{requested.suffix}")
        if normalized != requested:
            names.append(normalized)

    searched = []
    for name in names:
        folders = (Path(),) if name.is_absolute() else (
            Path.cwd(), SOURCES_DIRECTORY,
            NORMAL_EXAMPLES_DIRECTORY, OPTIMIZATION_EXAMPLES_DIRECTORY,
        )
        for folder in folders:
            path = folder / name
            if not path.suffix:
                path = path.with_suffix(".py")
            searched.append(str(path))
            if path.suffix == ".py" and path.is_file():
                return path.resolve()

    raise FileNotFoundError(
        f"Beispieldatei {model_file!r} nicht gefunden. Gesucht wurde in:\n"
        + "\n".join(searched)
    )


def _load_model(model_path: Path) -> dict[str, object]:
    """Führt die Beispieldatei aus und gibt ihre globalen Variablen zurück."""
    # Der Simulationsstart muss in der Datei unter if __name__ == "__main__": stehen.
    # run_name="spine_model" sorgt dafür, dass dieser Block beim Laden nicht läuft.
    return runpy.run_path(str(model_path), run_name="spine_model")


def _find_layout_and_scenario(
    model: dict[str, object],
    model_path: Path,
) -> tuple[Layout, Scenario]:
    """Wählt Layout und Szenario aus und gibt sie als Tupel zurück."""
    from ..Configuration import Layout, Scenario

    # Liest simulate(layout, scenario) im Quelltext, ohne diesen erneut auszuführen.
    tree = ast.parse(model_path.read_text(encoding="utf-8"), filename=str(model_path))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "simulate":
                calls.append(node)
    calls.sort(key=lambda call: (call.lineno, call.col_offset))

    for call in calls:
        if len(call.args) < 2:
            continue
        layout_name, scenario_name = call.args[:2]
        if not isinstance(layout_name, ast.Name) or not isinstance(scenario_name, ast.Name):
            continue
        layout = model.get(layout_name.id)
        scenario = model.get(scenario_name.id)
        if isinstance(layout, Layout) and isinstance(scenario, Scenario):
            return layout, scenario

    # Ohne passenden simulate-Aufruf muss jeweils genau ein Objekt vorhanden sein.
    layouts = [value for value in model.values() if isinstance(value, Layout)]
    scenarios = [value for value in model.values() if isinstance(value, Scenario)]
    if len(layouts) == 1 and len(scenarios) == 1:
        return layouts[0], scenarios[0]

    raise ValueError(
        "Layout und Szenario sind nicht eindeutig: "
        f"{len(layouts)} Layout-Einträge und {len(scenarios)} Szenario-Einträge gefunden. "
        "Bei mehreren Paaren muss simulate(layout, scenario) die gewünschten Variablen angeben."
    )


# Lädt die Beispieldatei und gibt das ausgewählte Layout und Szenario als Tupel zurück.
def load_layout_and_scenario(model_path: str | Path) -> tuple[Layout, Scenario]:
    """Datei finden, Konfiguration laden und (layout, scenario) zurückgeben."""
    path = _resolve_model_path(model_path)
    model = _load_model(path)
    return _find_layout_and_scenario(model, path)
