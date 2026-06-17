# Changelog

## 0.3.0 - 2026-06-18

### Added

- A confirmation dialog before closing a tab (bypassed if the sheet is empty).
- Support for closing tabs by middle-clicking on them in the tab bar.
- An extensive end-user guide (`docs/USER_GUIDE.md`) detailing calculations, units, currencies, mathematical functions, dates, times, and keyboard shortcuts.
- Automated tests (`tests/test_user_guide.py`) that verify guide examples against the evaluation engine.

### Fixed

- A bug where the `xor` keyword was incorrectly normalized to the exponentiation operator (`**`) rather than evaluating as bitwise XOR.

## 0.2.0 - 2026-06-17

### Added

- Multi-sheet tabs with session persistence and reorderable calculation sheets.
- Windows platform support, including a PowerShell build script, a dedicated
  Windows icon asset, and GitHub Actions release automation for Windows builds.
- Parentheses handling in expression evaluation.
- Typed arithmetic for units, currencies, and percentages.
- Yahoo Finance-backed currency rates and expanded currency parsing using the
  `yfinance` package.
- System theme mode, an About dialog, and bundled macOS app icon support.
- Ruff linting configuration and an MIT license.
- A VS Code launch configuration for development.

### Changed

- Improved aggregate calculations, including mixed-currency totals converted to
  a target currency.
- Refined result pane layout and right-aligned result rendering.
- Made the autocomplete shortcut platform-aware.
- Updated release automation to publish notes from the matching changelog
  entry.

### Fixed

- Fixed the 'Surround with Parentheses' shortcut on Windows to support
  `Ctrl+Shift+9` and `Ctrl+Shift+0`.

## 0.1.0 - 2026-06-16

### Added

- Initial Pnumi macOS application.
- Natural language calculations with variables, previous results, units, currencies, dates, times, functions, and formatting.
- PySide6 editor with inline results, autocomplete, syntax highlighting, light and dark themes, import, export, copy, and print support.
- Local PyInstaller macOS app build script.
- GitHub Actions release workflow for tagged macOS app releases.
