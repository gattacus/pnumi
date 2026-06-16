from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_macos_icon_asset_is_present_and_used_by_build_script() -> None:
    icon = ROOT / "assets" / "pnumi.icns"
    source_png = ROOT / "assets" / "pnumi-icon.png"
    build_script = ROOT / "scripts" / "build_macos_app.sh"

    assert source_png.is_file()
    assert icon.read_bytes().startswith(b"icns")
    assert "assets/pnumi.icns" in build_script.read_text(encoding="utf-8")
    assert "--osx-bundle-identifier uk.gattacus.Pnumi" in build_script.read_text(encoding="utf-8")


def test_macos_icon_small_layer_is_not_scrambled(tmp_path) -> None:
    if not shutil.which("iconutil"):
        pytest.skip("iconutil is only available on macOS")
    icon = ROOT / "assets" / "pnumi.icns"
    iconset = tmp_path / "pnumi.iconset"

    subprocess.run(["iconutil", "-c", "iconset", str(icon), "-o", str(iconset)], check=True)
    pixels = _read_png_rgba(iconset / "icon_16x16@2x.png")

    assert pixels[(0, 0)][3] == 0
    assert pixels[(30, 30)][3] == 0
    assert _is_yellow_icon_pixel(pixels[(24, 24)])


def _is_yellow_icon_pixel(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return alpha == 255 and red > 220 and 140 < green < 230 and blue < 80


def _read_png_rgba(path: Path) -> dict[tuple[int, int], tuple[int, int, int, int]]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    width = height = 0
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, *_ = struct.unpack(">IIBBBBB", chunk)
            assert bit_depth == 8
            assert color_type == 6
        elif kind == b"IDAT":
            compressed.extend(chunk)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(compressed)
    stride = width * 4
    rows: list[bytearray] = []
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        prior = rows[-1] if rows else bytearray(stride)
        _unfilter_png_row(row, prior, filter_type)
        rows.append(row)
    return {
        (x, y): tuple(rows[y][x * 4 : x * 4 + 4])  # type: ignore[misc]
        for y in range(height)
        for x in range(width)
    }


def _unfilter_png_row(row: bytearray, prior: bytearray, filter_type: int) -> None:
    bytes_per_pixel = 4
    for index, value in enumerate(row):
        left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        up = prior[index]
        upper_left = prior[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        if filter_type == 1:
            row[index] = (value + left) & 0xFF
        elif filter_type == 2:
            row[index] = (value + up) & 0xFF
        elif filter_type == 3:
            row[index] = (value + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            row[index] = (value + _paeth(left, up, upper_left)) & 0xFF
        else:
            assert filter_type == 0


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left
