#!/usr/bin/env python3
# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate both icon sets for Match Units.

The command reports one of two states, so it ships two full sets and swaps the
command definition's resourceFolder between them (see entry.py):

* ``resources/`` -- a ruler, the plainest available mark for "units", shown
  while the document's units agree with the application default.
* ``resources/mismatch/`` -- the same ruler, retreated up and to the left to
  make room for an exclamation mark in the lower-right corner, shown while they
  disagree.

Two constraints drove the drawing:

**The badge is drawn in ink, not knocked out.** The first attempt put the
exclamation inside a solid disc as a hole, following the sync badge in
``commands/teamaddins``. A hole that thin closes up: at 32px the mark width is
barely one pixel and the badge reads as a plain dot. Drawing the mark itself and
biting a clearance out of the ruler behind it keeps the stroke at full weight
at every size.

**The 16px variants are redrawn, not scaled.** At 16px one design unit is a
quarter of a pixel, so every edge is placed to fill whole pixels: with a stroke
of 4 units, a frame edge at ``4k + 2`` lands exactly on pixel ``k``. The ruler
loses its two short graduations, and the shapes are plain rectangles
(``round_box`` with a zero corner radius) rather than capsules, whose round caps
otherwise push a bar half a pixel past each end.

Colour cannot carry the state: ``render_set`` paints one flat colour per
variant, so the difference between the two sets is entirely geometric.

Only the geometry lives here; the drawing and PNG machinery is shared with the
other icon generators in tools/icons/iconkit.py. Run this from anywhere:

    python commands/matchunits/resources/generate_icons.py
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
MATCH_RESOURCES = SCRIPT_DIR
MISMATCH_RESOURCES = os.path.join(SCRIPT_DIR, "mismatch")

# --- 32px and 64px -----------------------------------------------------------

# The ruler: a rounded box with graduations off its top edge, three long and two
# short, the way a real rule alternates. The badged set keeps the same box and
# the same stroke weight, shrunk and pushed left to clear the mark, and drops
# the two short graduations -- at that scale five of them merge into a band.
STROKE = 3.4
TICK = 1.7
BOX = (32.0, 32.0, 27.0, 11.5, 3.5)
TICK_TOP = 20.5
LONG_TICKS = (15.5, 32.0, 48.5)
LONG_END = 34.0
SHORT_TICKS = (23.75, 40.25)
SHORT_END = 28.5

# The ruler's retreat on the badged set. Sized so the mark clears the ruler's
# right edge outright: no clearance has to be knocked out of the frame, which
# is what the first draft did and what made the badge read as a hole.
RULER_SCALE = 0.74
RULER_NUDGE = (-7.26, 0.0)

# The exclamation, centred on the ruler's own mid-height so the pair reads as
# one row rather than as a glyph with something hanging off it.
MARK_X = 55.0
MARK_WIDTH = 5.6
MARK_TOP = 25.0
MARK_BOTTOM = 33.5
MARK_DOT_Y = 40.5
MARK_DOT_RADIUS = 2.5

# --- 16px redraw -------------------------------------------------------------

# A stroke of 4 units is one pixel, and a frame edge at 4k + 2 fills pixel k,
# so every number below is one of those.
STROKE_16 = 4.0
TICK_HALF_16 = 2.0

# Plain set: frame on pixels 2..13 across, 5..10 down; three graduations.
BOX_16 = (32.0, 32.0, 22.0, 10.0, 3.0)
TICKS_16 = (22.0, 34.0, 46.0)
TICK_MID_16 = 28.0
TICK_HALF_HEIGHT_16 = 8.0

# Badged set: the ruler gives up pixels 10..13 and two graduations; the mark
# takes pixel 12 and spans exactly the ruler's own rows.
BOX_16_BADGED = (24.0, 28.0, 14.0, 10.0, 3.0)
TICKS_16_BADGED = (22.0, 30.0)
TICK_MID_16_BADGED = 26.0
TICK_HALF_HEIGHT_16_BADGED = 6.0
MARK_X_16 = 50.0
MARK_HALF_16 = 2.0
MARK_MID_16 = 24.0
MARK_HALF_HEIGHT_16 = 8.0
MARK_DOT_MID_16 = 38.0
MARK_DOT_HALF_16 = 2.0


def _rect(cx: float, cy: float, hx: float, hy: float):
    """A sharp-cornered rectangle: round_box with no corner radius.

    Used for every 16px shape. A capsule's round caps push a bar half its width
    past each stated end, which at 16px is half a pixel of grey on both sides.
    """
    return kit.round_box(cx, cy, hx, hy, 0.0)


def _ruler_16(box, ticks, tick_mid, tick_half_height):
    """The 16px ruler: whole-pixel frame, rectangular graduations."""
    frame = kit.outlined([kit.round_box(*box)], STROKE_16)
    bars = kit.filled(
        [_rect(x, tick_mid, TICK_HALF_16, tick_half_height) for x in ticks]
    )
    return kit.combined(frame, bars)


def _ruler(scale: float = 1.0, nudge=(0.0, 0.0), short_ticks: bool = True):
    """The 32/64px ruler, optionally shrunk about its own centre and nudged.

    Args:
        scale: Uniform scale. ``scaled`` scales about the grid origin, so the
            centre-preserving offset is added back here before the nudge.
            Distances are rescaled with the shape, so the stroke and the
            graduations keep their weight whatever the ruler is scaled to.
        nudge: Extra translation, applied after that scale.
        short_ticks: Whether to draw the two half-length graduations.

    Returns:
        The ruler mask.
    """
    box = kit.round_box(*BOX)
    ticks = [kit.capsule(x, TICK_TOP, x, LONG_END, TICK) for x in LONG_TICKS]
    if short_ticks:
        ticks += [kit.capsule(x, TICK_TOP, x, SHORT_END, TICK) for x in SHORT_TICKS]

    keep_centre = (kit.GRID / 2.0) * (1.0 - scale)
    dx = keep_centre + nudge[0]
    dy = keep_centre + nudge[1]

    box = kit.scaled(box, scale, dx, dy)
    ticks = [kit.scaled(tick, scale, dx, dy) for tick in ticks]
    return kit.combined(kit.outlined([box], STROKE), kit.filled(ticks))


def build_match_mask(size: int):
    """The plain ruler: the document agrees with the default units."""
    if size <= 16:
        return _ruler_16(BOX_16, TICKS_16, TICK_MID_16, TICK_HALF_HEIGHT_16)
    return _ruler()


def build_mismatch_mask(size: int):
    """The ruler with an exclamation beside it: the document disagrees."""
    if size <= 16:
        ruler = _ruler_16(
            BOX_16_BADGED,
            TICKS_16_BADGED,
            TICK_MID_16_BADGED,
            TICK_HALF_HEIGHT_16_BADGED,
        )
        mark = kit.filled(
            [
                _rect(MARK_X_16, MARK_MID_16, MARK_HALF_16, MARK_HALF_HEIGHT_16),
                _rect(MARK_X_16, MARK_DOT_MID_16, MARK_HALF_16, MARK_DOT_HALF_16),
            ]
        )
        return kit.combined(ruler, mark)

    mark = kit.filled(
        [
            kit.capsule(MARK_X, MARK_TOP, MARK_X, MARK_BOTTOM, MARK_WIDTH / 2.0),
            kit.round_disc(MARK_X, MARK_DOT_Y, MARK_DOT_RADIUS),
        ]
    )
    return kit.combined(_ruler(RULER_SCALE, RULER_NUDGE, short_ticks=False), mark)


def main() -> None:
    os.makedirs(MISMATCH_RESOURCES, exist_ok=True)
    kit.render_set(MATCH_RESOURCES, build_match_mask)
    kit.render_set(MISMATCH_RESOURCES, build_mismatch_mask)


if __name__ == "__main__":
    main()
