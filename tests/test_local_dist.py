from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("build_package", ["missing", "namespace", "cli"])
def test_local_build_checks_for_runnable_build_package(tmp_path, build_package):
    bash = shutil.which("bash")
    if bash is None or sys.platform == "win32":
        pytest.skip("The local distribution script requires a Unix shell")
    script = tmp_path / "scripts" / "build_local_dist.sh"
    script.parent.mkdir()
    shutil.copyfile(ROOT / "scripts" / "build_local_dist.sh", script)
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    # Disable site packages so this checks dependency discovery regardless of
    # whether the test runner happens to have the real build package installed.
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -S "$@"\n', encoding="utf-8")
    python.chmod(0o755)
    if build_package != "missing":
        package = tmp_path / "build"
        package.mkdir()
        if build_package == "cli":
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "__main__.py").write_text(
                'if __name__ == "__main__":\n    print("Build CLI invoked")\n', encoding="utf-8"
            )
    result = subprocess.run([bash, str(script)], capture_output=True, text=True, timeout=10)
    if build_package == "cli":
        assert result.returncode == 0
        assert result.stdout.strip() == "Build CLI invoked"
    else:
        assert result.returncode == 1
        assert "Python package 'build' is required" in result.stderr
        assert "pip install -e '.[dev]'" in result.stderr
        assert "No module named" not in result.stderr
