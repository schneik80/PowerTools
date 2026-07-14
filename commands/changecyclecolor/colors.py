# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Load Fusion's built-in ColorCycleTable from RiverRubicon.xml.

The XML stores RGB as three space-separated floats in 0.0..1.0. A handful of
shipped entries are missing decimal points (e.g. ``"5412 7765"``) — we repair
those by prepending a decimal point when a token parses to a value > 1.0.
"""

from __future__ import annotations

import colorsys
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from .fusion_install import find_river_rubicon_xml


Color = Tuple[int, int, int]  # 0..255 ints
Swatch = Tuple[str, Color]  # (name, rgb)


def _coerce_unit_float(token: str) -> Optional[float]:
    """Parse a single RGB token from the XML into a 0..1 float.

    Repairs the missing-decimal-point typos found in shipped XMLs (e.g.
    ``"5412"`` → ``0.5412``). Returns ``None`` if the value cannot be
    interpreted as a unit float.
    """
    try:
        v = float(token)
    except ValueError:
        return None
    if 0.0 <= v <= 1.0:
        return v
    # Heuristic repair: integer-looking token with no decimal point — assume
    # the leading "." was dropped. Works for values like "5412" → 0.5412.
    if "." not in token:
        stripped = token.lstrip("-")
        if stripped.isdigit():
            try:
                v = float("." + stripped)
            except ValueError:
                return None
            if 0.0 <= v <= 1.0:
                return v
    return None


def _parse_rgb(attr: str) -> Optional[Color]:
    parts = attr.split()
    if len(parts) != 3:
        return None
    floats: List[float] = []
    for p in parts:
        f = _coerce_unit_float(p)
        if f is None:
            return None
        floats.append(f)
    return tuple(int(round(f * 255)) for f in floats)  # type: ignore[return-value]


def load_color_cycle(xml_path: Optional[str] = None) -> List[Swatch]:
    """Return the ColorCycleTable swatches from RiverRubicon.xml.

    Falls back to an empty list if the XML cannot be located or parsed.
    Malformed entries are skipped silently.
    """
    if xml_path is None:
        xml_path = find_river_rubicon_xml()
    if not xml_path:
        return []

    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError):
        return []

    table = root.find("ColorCycleTable")
    if table is None:
        return []

    out: List[Swatch] = []
    for entry in table.findall("ColorCycle"):
        name = (entry.get("name") or "").strip()
        rgb = _parse_rgb(entry.get("RGB") or "")
        if not name or rgb is None:
            continue
        out.append((name, rgb))
    return out


def sort_rainbow(swatches: List[Swatch]) -> List[Swatch]:
    """Return *swatches* sorted into a rainbow: hue first, then darker
    variants of the same hue grouped together. Highly desaturated colors
    (pastels/neutrals like Magnolia) are pushed to the end so the rainbow
    band itself stays clean.

    Sort key tuple per swatch:
      (is_neutral, hue, -value)

    where ``is_neutral`` (bool) is True for saturation < 0.18 — empirically
    chosen so the very pale lavender entries (Magnolia, Amethyst, Thistle)
    drop out of the main rainbow while saturated darks/brights stay in.
    """
    NEUTRAL_SAT = 0.18

    def key(swatch: Swatch):
        _, (r, g, b) = swatch
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        is_neutral = s < NEUTRAL_SAT
        # Within neutrals, sort by value (lightest → darkest).
        # Within the rainbow, sort by hue, then brighter-first within hue.
        if is_neutral:
            return (1, 0.0, -v)
        return (0, h, -v)

    return sorted(swatches, key=key)


def rgb_to_hex(rgb: Color) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def hex_to_rgb(hex_str: str) -> Optional[Color]:
    s = hex_str.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None
