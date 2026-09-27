"""Kompatibilitätsstarter für die Optimierung von Example 0."""

import os
from pathlib import Path
import runpy

os.environ.setdefault("SPINEML_MODEL_FILE", "example-0.py")

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "optimization.py"),
        run_name="__main__",
    )
