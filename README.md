<p align="center">
  <img src="assets/pnumi-icon.png" alt="Pnumi icon" width="96">
</p>

<h1 align="center">Pnumi</h1>

Pnumi is an original Python/PySide6 rewrite of a Numi-style natural language calculator. It is based on public Numi documentation and intentionally omits Alfred integration and JavaScript plugin extensions.

## Features

- Natural language calculations: write expressions such as `subtotal = hotel + train + meals` and see results update beside each line.
- Variables and previous results: reuse named values and `prev` across a document.
- Unit conversions: convert lengths, time, storage, angles, and other supported units inline.
- Currency values: parse common currency symbols and codes, with rate provider support for conversions.
- Dates and times: evaluate date math, Unix timestamps, and timezone-aware time expressions.
- Functions and formatting: use math helpers such as `sqrt`, `round`, trigonometry, and base conversions like hex or binary.
- Autocomplete and highlighting: get completions for functions, units, currencies, timezones, and document variables.
- Import, export, copy, and print: move `.numi` or text documents in and out of the app from the menu.
- Light and dark themes: switch editor themes and alternating row backgrounds in settings.
- macOS app build: package Pnumi as a local macOS application with the included build script.

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
