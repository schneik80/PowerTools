# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Picks black or white ink for the Min and Max markers so they read against
# the viewport backdrop of the active lighting environment. Like flatten.py
# this imports no `adsk` module, so it is tested outside Fusion.
#
# Each shipped environment XML names its own grid colour, and Fusion chooses
# that colour to contrast with the environment's backdrop: white on Dark Sky,
# River Rubicon and Infinity Pool, black on Photo Booth, Grey Room and the
# Studios. Following the grid is following Fusion's own judgement. The
# backdrop colour itself is only the fallback, because it is not always what
# is on screen: Infinity Pool declares a white background yet renders dark,
# and its grid is white accordingly.

import xml.etree.ElementTree as ET

BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)

# Relative luminance above which a backdrop counts as light.
_LIGHT_THRESHOLD = 0.5


def _parse_floats(text: str, count: int) -> list | None:
    """The first *count* numbers in a space-separated attribute, or None."""
    try:
        values = [float(part) for part in text.split()]
    except ValueError:
        return None
    return values[:count] if len(values) >= count else None


def _luminance(rgb) -> float:
    """Rec. 709 luma of an RGB triple in the 0..1 range."""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ink_for_environment(root) -> tuple | None:
    """Black or white RGBA for marks drawn over *root*'s backdrop, or None.

    *root* is the parsed root element of an environment XML. ``GridBackground``
    is ``ARGB`` and decides when present; ``Background`` is ``RGB`` and is
    used only when the grid is missing or unreadable.
    """
    grid = root.find("GridBackground")
    if grid is not None:
        argb = _parse_floats(grid.get("ARGB") or "", 4)
        if argb is not None:
            # Fusion inks the grid to contrast with the backdrop, so the
            # markers take the same side of the scale.
            return WHITE if _luminance(argb[1:]) >= _LIGHT_THRESHOLD else BLACK
    background = root.find("Background")
    if background is not None:
        rgb = _parse_floats(background.get("RGB") or "", 3)
        if rgb is not None:
            return BLACK if _luminance(rgb) >= _LIGHT_THRESHOLD else WHITE
    return None


def ink_for_environment_xml(xml_path: str | None) -> tuple | None:
    """:func:`ink_for_environment` for the XML at *xml_path*, or None."""
    if not xml_path:
        return None
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError):
        return None
    return ink_for_environment(root)
