#!/usr/bin/env python3
# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate the command icon for Measure Path.

The glyph is what the command does: a chain of three straight runs measured end
to end, with a node dot at every junction.  The two end nodes are drawn solid
and larger than the interior one, because the command's whole premise is that
you pick two objects and it works out the run between them.

The path leans up to the right rather than sitting flat so that the three runs
stay individually readable -- a flat zig-zag collapses into a single band once
the bars are thick enough to survive 16px.

At 16px one pixel is four design units, so the small variant is redrawn rather
than scaled: two runs instead of three, every vertex on a whole-pixel boundary,
and fatter bars.  Scaling the 64px art down smears every junction across a
pixel boundary and the dots disappear into the bars.

Only the geometry lives here; the drawing and PNG machinery is shared with the
other icon generators in tools/icons/iconkit.py.  Run this from anywhere:

    .\\.venv-dev\\Scripts\\python commands\\measurepath\\resources\\generate_icons.py
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

# Vertices of the measured chain on the 64-unit design grid, walking left to
# right. The rise is deliberate: a flat zig-zag merges into one band at 16px.
CHAIN = ((9.0, 17.0), (25.0, 41.0), (43.0, 21.0), (55.0, 45.0))
BAR = 3.2
END_DOT = 6.6
MID_DOT = 4.4

# 16px redraw: one fewer run, vertices on whole pixels (multiples of 4), and
# heavier bars so the strokes still read at a quarter of the resolution.
CHAIN_16 = ((8.0, 20.0), (32.0, 44.0), (56.0, 20.0))
BAR_16 = 3.6
END_DOT_16 = 7.0
MID_DOT_16 = 5.2


def _mask(chain, bar, end_dot, mid_dot):
    """Build the glyph: the runs, then a node dot at every vertex."""
    parts = []
    for start, end in zip(chain, chain[1:]):
        parts.append(kit.capsule(start[0], start[1], end[0], end[1], bar))

    last = len(chain) - 1
    for index, (x, y) in enumerate(chain):
        radius = end_dot if index in (0, last) else mid_dot
        parts.append(kit.round_disc(x, y, radius))

    return kit.filled(parts)


def build_mask(size: int):
    if size <= 16:
        return _mask(CHAIN_16, BAR_16, END_DOT_16, MID_DOT_16)
    return _mask(CHAIN, BAR, END_DOT, MID_DOT)


def main() -> None:
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    kit.render_set(SCRIPT_DIR, build_mask, kit.THEME_VARIANTS)


if __name__ == "__main__":
    main()
