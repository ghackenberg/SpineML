"""Lädt die Fabrikkonfiguration und liefert Layout und Szenario zurück."""

from __future__ import annotations

from pathlib import Path
import runpy
from typing import TYPE_CHECKING, Any

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


def _find_layout_and_scenario(model: dict[str, Any]) -> tuple[Layout, Scenario]:
    """Gibt die Variablen layout und scenario aus der Konfiguration zurück."""
    layout = model["layout"]
    scenario = model["scenario"]
    return layout, scenario


# Lädt die Beispieldatei und gibt das ausgewählte Layout und Szenario als Tupel zurück.
def load_layout_and_scenario(model_path: str | Path) -> tuple[Layout, Scenario]:
    path = _resolve_model_path(model_path)       # Pfad zur Beispieldatei finden
    model = _load_model(path)                    # Konfiguration laden: Dictionary mit Variablen
    return _find_layout_and_scenario(model)      # Daraus (layout, scenario) zurückgeben
