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
- Multi-sheet tabs: manage multiple calculation sheets using a top tab bar (reorderable, dynamically hidden when only a single tab is open) with session persistence.
- Light and dark themes: switch editor themes and alternating row backgrounds in settings.
- macOS and Windows app builds: package Pnumi as a local desktop application with the included build scripts.

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
.venv/bin/ruff check src tests
.venv/bin/pytest
```

## License

Pnumi is released under the MIT License. See [LICENSE](LICENSE).

## Build macOS App

```sh
./scripts/build_macos_app.sh
```

## Build Windows App

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\scripts\build_windows_app.ps1
```

## Release

Releases are built by GitHub Actions when a version tag is pushed.

1. Update the version in `pyproject.toml`.

   ```toml
   version = "0.1.1"
   ```

2. Add a matching entry to `CHANGELOG.md`.

   ```md
   ## 0.1.1 - 2026-06-16

   ### Added

   - New release notes.
   ```

3. Commit and push the changes.

   ```sh
   git add pyproject.toml CHANGELOG.md
   git commit -m "Release 0.1.1"
   git push origin main
   ```

4. Create and push a matching tag.

   ```sh
   git tag v0.1.1
   git push origin v0.1.1
   ```

The release workflow checks that the tag matches `pyproject.toml`, extracts the matching `CHANGELOG.md` entry, runs the test suite, builds the macOS and Windows apps, zips the platform artifacts, and attaches both zips to a GitHub Release. For example, `version = "0.1.1"` must be released with the tag `v0.1.1` and a `## 0.1.1` changelog entry.

If a tag and GitHub Release already exist, pushing the same tag again will not create a new release. Update that release's notes from the matching `CHANGELOG.md` entry in the GitHub UI, or put those notes in `release-notes.md` and run:

```sh
gh release edit v0.1.0 --notes-file release-notes.md
```
