<p align="center">
  <img src="assets/pnumi-icon.png" alt="Pnumi icon" width="96">
</p>

<h1 align="center">Pnumi</h1>

Pnumi is an original Python/PySide6 rewrite of a Numi-style natural language calculator. It is based on public Numi documentation and intentionally omits Alfred integration and JavaScript plugin extensions.

## Screenshots

Light theme:

![Pnumi light theme with example trip planning calculations, unit conversions, date conversion, and base conversion](assets/screenshots/pnumi-light.png)

Dark theme:

![Pnumi dark theme with example trip planning calculations, unit conversions, date conversion, and base conversion](assets/screenshots/pnumi-dark.png)

## Run

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pnumi
```

## Test

```sh
.venv/bin/pytest
```

## Build macOS App

```sh
./scripts/build_macos_app.sh
```
