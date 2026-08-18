#!/usr/bin/env python3
# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate the command icons for the three number-stamping commands.

The glyph is the number sign, badged to say which number and where it lands:

* ``assignpartnumbers`` (Assign Part Numbers) -- the bare mark.  This is the
  family's canonical icon, so it carries no badge.
* ``syncitempartnumber`` (Sync Item to Part Number) -- the mark with the same
  circular sync arrow the Team Add-ins icon uses, because the command copies
  an Item Number that already exists rather than issuing a new one.
* ``assigndrawingnumber`` (Assign Drawing Number) -- the mark inside a
  landscape drawing sheet, because it stamps a drawing rather than a part.

The mark is built from four capsules and painted solid, so unlike an outlined
glyph it survives 16px.  What does not survive is shrinking the 64px art: at
16px one pixel is four design units, and a lean of three units smears every
upright across a pixel boundary.  Each 16px variant is therefore redrawn --
heavier bars, no lean, every edge on a whole pixel -- rather than scaled down.

Only the geometry lives here; the drawing and PNG machinery is shared with the
other icon generators in tools/icons/iconkit.py.  Run this from anywhere:

    .\\.venv-dev\\Scripts\\python commands\\assignpartnumbers\\resources\\generate_icons.py
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
COMMANDS_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
PART_NUMBERS_RESOURCES = SCRIPT_DIR
SYNC_ITEM_RESOURCES = os.path.join(COMMANDS_DIR, "syncitempartnumber", "resources")
DRAWING_NUMBER_RESOURCES = os.path.join(
    COMMANDS_DIR, "assigndrawingnumber", "resources"
)

# Number-sign geometry: bar radius, the span it fills, where the two inner
# bars sit within that span, and how far the uprights lean right.
MARK = (2.8, 7.0, 57.0, (24.0, 40.0), 3.0)
# 16px redraws of the same mark.  Bars land on whole pixels: at 16x16 one
# pixel is four design units, so 20..28 is pixels 5 and 6, exactly two wide.
MARK_16 = (4.0, 8.0, 56.0, (24.0, 40.0), 0.0)
SYNC_MARK_16 = (4.0, 4.0, 44.0, (16.0, 32.0), 0.0)
SHEET_MARK_16 = (2.0, 20.0, 44.0, (30.0, 38.0), 0.0)

STROKE = 4.0

# Sync: the mark shrinks up-left to clear the badge in the lower-right corner.
SYNC_SCALE = 0.78
SYNC_OFFSET = -3.46
BADGE_CENTER = 49.0
BADGE_RADIUS = 9.5
BADGE_STROKE = 4.4
BADGE_CLEARANCE = BADGE_RADIUS + BADGE_STROKE / 2.0 + 2.5
# At 16px the arc collapses into mush, so the badge becomes a bare arrowhead
# in the corner pocket the smaller mark leaves open.  It points down rather
# than following the arc's own head: a diagonal arrow at this size is all
# partial coverage and reads as a smudge, whereas a flat top edge on a pixel
# boundary stays crisp -- and "copy into" is what the command does anyway.
SYNC_ARROWHEAD_16 = (44.0, 48.0, 60.0, 48.0, 52.0, 62.0)

# Drawing sheet: landscape, and at 16px squatter so its 4-unit border lands on
# whole pixels top and bottom as well as left and right.
SHEET = (32.0, 32.0, 26.0, 22.0, 2.0)
SHEET_16 = (32.0, 32.0, 26.0, 18.0, 2.0)
# The mark inside the sheet, drawn heavier than its size suggests because the
# sheet's border already spends the icon's contrast budget.
SHEET_MARK_SCALE = 0.60
SHEET_MARK_OFFSET = 12.8
SHEET_MARK_RADIUS = 3.4


def number_sign(
    radius: float,
    low: float,
    high: float,
    inner: tuple[float, float],
    slant: float,
) -> kit.Shape:
    """Build the number sign from two crossbars and two leaning uprights.

    The mark always spans low..high: the capsule ends are pulled in by the
    radius so a heavier bar grows inward, not out of the icon.

    Args:
        radius: Half the bar thickness, in design units.
        low: Where the mark starts on both axes.
        high: Where the mark ends on both axes.
        inner: Where the two inner bars sit, measured at mid-span.
        slant: How far the uprights lean right, top versus bottom.

    Returns:
        The shapes to union, and an empty socket list.
    """
    start = low + radius
    end = high - radius

    bars = [kit.capsule(start, y, end, y, radius) for y in inner]
    bars += [kit.capsule(x + slant, start, x - slant, end, radius) for x in inner]
    return bars, []


def part_numbers_mask(size: int) -> kit.Mask:
    """Build the Assign Part Numbers glyph for one output size.

    Args:
        size: Output size in pixels.

    Returns:
        The mask to rasterize: the bare mark, filling the grid.
    """
    return kit.filled(*number_sign(*(MARK_16 if size <= 16 else MARK)))


def sync_item_mask(size: int) -> kit.Mask:
    """Build the Sync Item to Part Number glyph for one output size.

    Args:
        size: Output size in pixels.

    Returns:
        The mask to rasterize.  At 16px the circular arrow gives way to a solid
        arrowhead, and the mark is redrawn smaller rather than scaled so its
        bars stay on whole pixels.
    """
    if size <= 16:
        mark = kit.filled(*number_sign(*SYNC_MARK_16))
        return kit.combined(mark, kit.triangle(*SYNC_ARROWHEAD_16))

    parts, holes = kit.scale_shape(
        number_sign(*MARK), SYNC_SCALE, SYNC_OFFSET, SYNC_OFFSET
    )
    clearance = kit.filled(
        [kit.round_disc(BADGE_CENTER, BADGE_CENTER, BADGE_CLEARANCE)]
    )
    return kit.combined(
        kit.knocked_out(kit.filled(parts, holes), clearance),
        kit.sync_badge(BADGE_CENTER, BADGE_RADIUS, BADGE_STROKE),
    )


def drawing_number_mask(size: int) -> kit.Mask:
    """Build the Assign Drawing Number glyph for one output size.

    Landscape is the whole point of the sheet -- it is what separates this
    glyph from the portrait document icons already in the panel.

    Args:
        size: Output size in pixels.

    Returns:
        The mask to rasterize: the sheet outlined, with the mark solid inside.
    """
    if size <= 16:
        sheet = [kit.round_box(*SHEET_16)]
        mark = kit.filled(*number_sign(*SHEET_MARK_16))
    else:
        sheet = [kit.round_box(*SHEET)]
        mark = kit.filled(
            *kit.scale_shape(
                number_sign(SHEET_MARK_RADIUS, *MARK[1:]),
                SHEET_MARK_SCALE,
                SHEET_MARK_OFFSET,
                SHEET_MARK_OFFSET,
            )
        )
    return kit.combined(kit.outlined(sheet, STROKE), mark)


def main() -> None:
    """Regenerate the icons for all three number-stamping commands.

    These sets ship light and dark only -- no "-disabled" variant -- matching
    what the commands already carried.
    """
    kit.render_set(PART_NUMBERS_RESOURCES, part_numbers_mask, kit.THEME_VARIANTS)
    kit.render_set(SYNC_ITEM_RESOURCES, sync_item_mask, kit.THEME_VARIANTS)
    kit.render_set(DRAWING_NUMBER_RESOURCES, drawing_number_mask, kit.THEME_VARIANTS)


if __name__ == "__main__":
    main()
