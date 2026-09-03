#!/usr/bin/env python3
# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate the command icon for Document History.

The glyph is the palette turned on its side: a spine with a node for each day
and a bar of that day's work beside it, newest at the top. Bar lengths differ
because how much happened on a day is the thing the view is for.

Two shapes were drawn and rejected first, both for collisions rather than for
looks. The palette's own arrangement -- horizontal rails with beads -- is the
universal equaliser/settings mark once it loses its context. A clock is the
universal history mark, but Timeline Compute Report already wears a stopwatch,
and the two would sit in the same product a panel apart.

It replaces a hand-drawn document-stack that shipped incomplete: only 16px art
existed, the 32px files held that same 16px glyph adrift in a 32px canvas, and
the one that mattered was named ``32x32-normal.png``, which is not a name
Fusion ever looks for. There was effectively no 32px icon and no 64px set.

At 16px one pixel is four design units, so the small variant is redrawn rather
than scaled: every centre on a pixel centre (4k+2), spine and bars exactly one
pixel thick, fatter nodes, and the bars run to a common end because six pixels
cannot show three different lengths. Scaling the 64px art down lands the spine
on a pixel boundary and the nodes smear into it.

Only the geometry lives here; the drawing and PNG machinery is shared with the
other icon generators in tools/icons/iconkit.py. Run this from anywhere:

    python3 commands/dochistory/resources/generate_icons.py
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

# The spine, on the 64-unit design grid.
SPINE_X = 19.0
SPINE_Y = (9.0, 55.0)
SPINE = 2.4

# One entry per day, newest first: (node y, where its bar ends).
# Every bar starts at BAR_X0; the differing ends are the point.
DAYS = ((15.0, 54.0), (32.0, 42.0), (49.0, 58.0))
BAR_X0 = 33.0
BAR = 3.4
NODE = 7.0

# 16px redraw. One pixel is four design units, so every centre sits on 4k+2 and
# the spine and bars are exactly one pixel thick; the bars also run to a common
# end, because six pixels of bar cannot show three different lengths.
SPINE_X_16 = 18.0
SPINE_Y_16 = (10.0, 50.0)
SPINE_16 = 4.0
DAYS_16 = ((10.0, 54.0), (30.0, 54.0), (50.0, 54.0))
BAR_X0_16 = 30.0
BAR_16 = 4.0
NODE_16 = 6.0


def _mask(spine_x, spine_y, spine, days, bar_x0, bar, node):
    """Build the glyph: the spine, then each day's node and its bar."""
    parts = [
        kit.capsule(spine_x, spine_y[0], spine_x, spine_y[1], spine / 2.0),
    ]
    for y, bar_x1 in days:
        parts.append(kit.capsule(bar_x0, y, bar_x1, y, bar / 2.0))
        parts.append(kit.round_disc(spine_x, y, node))
    return kit.filled(parts)


def build_mask(size: int):
    if size <= 16:
        return _mask(
            SPINE_X_16, SPINE_Y_16, SPINE_16, DAYS_16, BAR_X0_16, BAR_16, NODE_16
        )
    return _mask(SPINE_X, SPINE_Y, SPINE, DAYS, BAR_X0, BAR, NODE)


def main() -> None:
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    kit.render_set(SCRIPT_DIR, build_mask, kit.ALL_VARIANTS)


if __name__ == "__main__":
    main()
