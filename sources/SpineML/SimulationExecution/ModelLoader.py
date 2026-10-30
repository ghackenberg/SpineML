"""Lädt die Fabrikkonfiguration und liefert Layout und Szenario zurück."""

from __future__ import annotations

import ast
from pathlib import Path
import runpy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..Configuration import Layout, Scenario


# parents[0] = SimulationExecution, parents[1] = SpineML, parents[2] = sources.
SOURCES_DIRECTORY = Path(__file__).resolve().parents[2]
NORMAL_EXAMPLES_DIRECTORY = SOURCES_DIRECTORY / "examples" / "normal"


def _resolve_model_path(model_file: str | Path) -> Path:
    """Prüft den Dateipfad oder den exakten Dateinamen im Beispielordner."""
    path = Path(model_file)
    if path.suffix != ".py":
        raise ValueError("Bitte den vollständigen Dateinamen angeben, z. B. example-5.py.")
    if not path.is_file():
        path = NORMAL_EXAMPLES_DIRECTORY / path
    if not path.is_file():
        raise FileNotFoundError(f"Modelldatei nicht gefunden: {model_file}")
    return path.resolve()


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
    path = _resolve_model_path(model_path)       # Pfad zur Beispieldatei finden
    model = _load_model(path)                    # Konfiguration laden: Dictionary mit Variablen
    return _find_layout_and_scenario(model, path) # Daraus (layout, scenario) zurückgeben
