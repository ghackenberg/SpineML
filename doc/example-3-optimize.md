# Example 3: Kompatibilitätsstarter

Die eigentliche Optimierung steht nicht mehr in dieser Datei. Sie wurde nach
`sources/optimization.py` verschoben, damit dieselbe Oberfläche jedes
SpineML-Example optimieren kann.

## Example 3 starten

```powershell
.venv\Scripts\python.exe sources\optimization.py
```

Der Kompatibilitätsstarter setzt vor dem Start automatisch:

```python
os.environ.setdefault("SPINEML_MODEL_FILE", "example-3.py")
```

Die bisherige Datei `sources/examples/optimization/example-3-optimize.py` ist nur noch ein
Kompatibilitätsstarter. Sie setzt das Modell auf `example-3.py` und ruft
`optimization.main()` auf.

## Andere Examples

```powershell
.venv\Scripts\python.exe sources\optimization.py
```

Für ein anderes Example wird `EXAMPLE_FILE` vor dem Play-Button geändert.

Die vollständige Erklärung der Prozesse, Methoden, konkreten Eingaben und
Rückgaben, Seeds, Kandidaten und Ergebnisse steht in
[optimization_methods.md](optimization_methods.md). Die Übersichtsseite ist
[optimization.md](optimization.md).
