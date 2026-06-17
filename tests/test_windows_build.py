from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_icon_asset_is_present_and_contains_png_layers() -> None:
    icon = ROOT / "assets" / "pnumi.ico"
    data = icon.read_bytes()

    assert data[:4] == b"\x00\x00\x01\x00"
    layer_count = struct.unpack_from("<H", data, 4)[0]
    assert layer_count == 7

    sizes = []
    for index in range(layer_count):
        entry_offset = 6 + (index * 16)
        width, height, color_count, reserved = struct.unpack_from("<BBBB", data, entry_offset)
        planes, bit_count, byte_count, image_offset = struct.unpack_from("<HHII", data, entry_offset + 4)
        size = 256 if width == 0 else width
        image = data[image_offset : image_offset + byte_count]

        assert height == width
        assert color_count == 0
        assert reserved == 0
        assert planes == 1
        assert bit_count == 32
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        assert _png_dimensions(image) == (size, size)
        sizes.append(size)

    assert sizes == [16, 24, 32, 48, 64, 128, 256]


def test_windows_build_script_uses_windows_pyinstaller_options() -> None:
    script = (ROOT / "scripts" / "build_windows_app.ps1").read_text(encoding="utf-8")

    assert r".venv\Scripts\pyinstaller.exe" in script
    assert r"assets\pnumi.ico" in script
    assert r"assets\pnumi-icon.png;assets" in script
    assert "--windowed" in script
    assert "--osx-bundle-identifier" not in script


def test_release_workflow_builds_and_attaches_windows_zip() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "runs-on: windows-latest" in workflow
    assert r".\scripts\build_windows_app.ps1" in workflow
    assert "Pnumi-${{ github.ref_name }}-windows.zip" in workflow
    assert "Pnumi-${GITHUB_REF_NAME}-windows.zip#Pnumi Windows app" in workflow


def _png_dimensions(data: bytes) -> tuple[int, int]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    return width, height
