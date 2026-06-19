#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! .venv/bin/python -c "import build" >/dev/null 2>&1; then
  echo "Python package 'build' is required. Install it with: .venv/bin/python -m pip install -e '.[dev]'" >&2
  exit 1
fi

.venv/bin/python -m build
