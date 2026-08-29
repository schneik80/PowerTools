#!/usr/bin/env python3
# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate the command icon for Flatten Surface.

The glyph is the command's whole premise seen edge-on: a curved sheet above, the
same sheet laid flat below.  The contrast between the two strokes carries the
meaning, so both are drawn at the same weight -- if the flat one were lighter it
would read as a shadow or a baseline rather than as the result.

No arrow between them.  There is room for one at 64px but not at 16px, and a
glyph that loses an element at the small size stops being the same mark.

At 16px one pixel is four design units, so the small variant is redrawn rather
than scaled: a shallower arc, heavier strokes, and both elements on whole-pixel
boundaries.  Scaling the 64px art down thins the arc until its ends fade out.

Only the geometry lives here; the drawing and PNG machinery is shared with the
other icon generators in tools/icons/iconkit.py.  Run this from anywhere:

    .\\.venv-dev\\Scripts\\python commands\\flattensurface\\resources\\generate_icons.py
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_KIT_PATH = Path(__file__).resolve().parents[3] / "tools" / "icons" / "iconkit.py"
_spec = importlib.util.spec_from_file_location("pt_iconkit", _KIT_PATH)
kit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kit)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# The curved sheet, struck as an arc on the 64-unit design grid. Angles run
# clockwise from east, so a sweep centred on 270 bulges upward.
ARC_CX = 32.0
ARC_CY = 40.0
ARC_RADIUS = 25.0
ARC_WIDTH = 4.8
ARC_START = 203.0
ARC_SWEEP = 134.0

# The same sheet flattened: a straight bar of the same weight below it.
BAR_Y = 47.5
BAR_X0 = 9.0
BAR_X1 = 55.0
BAR_HALF = 2.4

# 16px redraw: a shallower, heavier arc so its ends still carry, and a thicker
# bar sitting on a whole-pixel row.
ARC_CY_16 = 44.0
ARC_RADIUS_16 = 26.0
ARC_WIDTH_16 = 6.0
ARC_START_16 = 210.0
ARC_SWEEP_16 = 120.0
BAR_Y_16 = 48.0
BAR_HALF_16 = 3.0
BAR_X0_16 = 8.0
BAR_X1_16 = 56.0


def _mask(cy, radius, width, start, sweep, bar_y, bar_x0, bar_x1, bar_half):
    """Build the glyph: the curved sheet, then the flat one under it."""
    curved = kit.arc(ARC_CX, cy, radius, width, start, sweep)
    flat = kit.filled([kit.capsule(bar_x0, bar_y, bar_x1, bar_y, bar_half)])
    return kit.combined(curved, flat)


def build_mask(size: int):
    """Build the glyph's mask for one output size."""
    if size <= 16:
        return _mask(
            ARC_CY_16,
            ARC_RADIUS_16,
            ARC_WIDTH_16,
            ARC_START_16,
            ARC_SWEEP_16,
            BAR_Y_16,
            BAR_X0_16,
            BAR_X1_16,
            BAR_HALF_16,
        )
    return _mask(
        ARC_CY,
        ARC_RADIUS,
        ARC_WIDTH,
        ARC_START,
        ARC_SWEEP,
        BAR_Y,
        BAR_X0,
        BAR_X1,
        BAR_HALF,
    )


def main() -> None:
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    kit.render_set(SCRIPT_DIR, build_mask, kit.THEME_VARIANTS)


if __name__ == "__main__":
    main()
