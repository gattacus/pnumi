#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller"

if [[ ! -x ".venv/bin/pyinstaller" ]]; then
  echo "PyInstaller not found. Run: .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

mkdir -p "$PYINSTALLER_CONFIG_DIR" "$ROOT_DIR/build/pyinstaller" "$ROOT_DIR/dist"

.venv/bin/pyinstaller \
  --name Pnumi \
  --windowed \
  --clean \
  --noconfirm \
  --icon "$ROOT_DIR/assets/pnumi.icns" \
  --osx-bundle-identifier uk.gattacus.Pnumi \
  --paths src \
  --distpath "$ROOT_DIR/dist" \
  --workpath "$ROOT_DIR/build/pyinstaller" \
  --specpath "$ROOT_DIR/build/pyinstaller" \
  src/pnumi/__main__.py

echo "Built dist/Pnumi.app"
