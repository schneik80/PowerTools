# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate solid-color PNG icons for swatch buttons.

Fusion's ``ButtonRowCommandInput.listItems`` expects an icon folder with PNGs
at standard sizes. PIL is not bundled with Fusion's Python, so we emit
minimal 8-bit RGB PNGs using only the standard library.
"""

from __future__ import annotations

import os
import struct
import zlib
from typing import Iterable, Tuple

from .colors import Color, rgb_to_hex


_SIZES = (16, 32, 64)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _solid_png(rgb: Color, size: int) -> bytes:
    r, g, b = rgb
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(
        ">IIBBBBB", size, size, 8, 2, 0, 0, 0
    )  # 8-bit, color type 2 (RGB)
    row = bytes((0,)) + bytes((r, g, b)) * size  # filter=None, then pixel triples
    idat = zlib.compress(row * size, 9)
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _quadrant_png(colors_4, size: int) -> bytes:
    """4-quadrant solid PNG. ``colors_4`` is ``[top-left, top-right,
    bottom-left, bottom-right]``. Used to draw the multi-color icon for
    the "Custom color..." button so it reads as a color-picker affordance.
    """
    half = size // 2
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter byte
        top = y < half
        for x in range(size):
            left = x < half
            idx = (0 if top else 2) + (0 if left else 1)
            r, g, b = colors_4[idx]
            raw.extend((r, g, b))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def ensure_quadrant_icon(folder: str, colors_4) -> str:
    """Write 16/32/64 px 4-quadrant icons into *folder*. Idempotent."""
    os.makedirs(folder, exist_ok=True)
    for size in _SIZES:
        path = os.path.join(folder, f"{size}x{size}.png")
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            continue
        with open(path, "wb") as f:
            f.write(_quadrant_png(colors_4, size))
    return folder


def ensure_swatch_folder(base_dir: str, rgb: Color) -> str:
    """Write 16/32/64 px PNGs for *rgb* into a per-color folder. Returns the
    absolute folder path that can be passed straight to ``listItems.add``.

    Idempotent: skips files that already exist with non-zero size, so repeated
    calls during a session are cheap.
    """
    folder = os.path.join(base_dir, rgb_to_hex(rgb).lstrip("#"))
    os.makedirs(folder, exist_ok=True)
    for size in _SIZES:
        path = os.path.join(folder, f"{size}x{size}.png")
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            continue
        with open(path, "wb") as f:
            f.write(_solid_png(rgb, size))
    return folder


def ensure_all(base_dir: str, swatches: Iterable[Tuple[str, Color]]) -> None:
    os.makedirs(base_dir, exist_ok=True)
    for _, rgb in swatches:
        ensure_swatch_folder(base_dir, rgb)
