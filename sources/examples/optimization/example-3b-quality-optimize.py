"""Kompatibilitätsstarter für die Optimierung von Example 3B."""

import os
from pathlib import Path
import runpy

os.environ["SPINEML_MODEL_FILE"] = "example-3b-quality.py"


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "optimization.py"),
        run_name="__main__",
    )
