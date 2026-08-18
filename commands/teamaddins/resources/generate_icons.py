#!/usr/bin/env python3
# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Generate the command icons for both Team Add-ins commands.

The glyph is a jigsaw puzzle piece -- the universal "plugin / add-in" mark:

* ``teamaddins`` (Team Add-ins) -- the piece outlined, with a circular sync
  arrow badged into the lower-right corner, because the command checks the hub
  and installs what is new.
* ``configteamaddins`` (Set Up Shared Add-ins Folder) -- a folder outline with
  a solid piece resting inside it, because the command creates that folder.

Only the geometry lives here; the drawing and PNG machinery is shared with the
other icon generators in tools/icons/iconkit.py.  Run this from anywhere:

    .\\.venv-dev\\Scripts\\python commands\\teamaddins\\resources\\generate_icons.py
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
TEAM_ADDINS_RESOURCES = SCRIPT_DIR
CONFIG_TEAM_ADDINS_RESOURCES = os.path.join(
    COMMANDS_DIR, "configteamaddins", "resources"
)

STROKE = 3.2

# The piece shrinks and shifts up-left on the badged icon to make room.
PIECE_SCALE = 0.76
PIECE_OFFSET = -2.56

BADGE_CENTER = 49.0
BADGE_RADIUS = 9.5
# Clear ring knocked out of the piece so the badge reads as an overlay.
BADGE_CLEARANCE = BADGE_RADIUS + STROKE / 2.0 + 2.5

# The piece tucked inside the folder, and the one bitten out of it at 16px.
INSET_PIECE_SCALE = 0.565
INSET_PIECE_DX = 14.2
INSET_PIECE_DY = 19.2


def puzzle_piece() -> kit.Shape:
    """Build the puzzle piece: a square body with two tabs and two sockets.

    Four outward tabs -- one per edge, as on the reference glyph -- collapse
    into a rosette at icon sizes however the proportions are tuned.  A real
    jigsaw piece is asymmetric, so the top and left edges push a tab out while
    the right and bottom edges take the matching socket in.  That keeps the
    square silhouette dominant and still reads at 16px.

    Tabs and sockets are complementary: both are radius 6.5 with the centre
    2.5 units off the edge, giving a 12-unit mouth and 9 units of depth on a
    42-unit edge.  The body's corner stays near-square at 1.5 units -- round
    it off and the silhouette turns back into a flower.

    Returns:
        The shapes to union, and the sockets to subtract.  Together they span
        6..57 on the design grid.
    """
    body = kit.round_box(36.0, 36.0, 21.0, 21.0, 1.5)
    tabs = [
        kit.round_disc(36.0, 12.5, 6.5),
        kit.round_disc(12.5, 36.0, 6.5),
    ]
    sockets = [
        kit.round_disc(54.5, 36.0, 6.5),
        kit.round_disc(36.0, 54.5, 6.5),
    ]
    return [body, *tabs], sockets


def folder() -> kit.Shape:
    """Build the folder: a tab box overlapping a body box.

    Returns:
        The shapes to union, and an empty socket list.  They span 8..56 across
        and 10..56 down.
    """
    tab = kit.round_box(18.0, 16.0, 10.0, 6.0, 3.0)
    body = kit.round_box(32.0, 37.0, 24.0, 19.0, 3.0)
    return [tab, body], []


def team_addins_mask(size: int) -> kit.Mask:
    """Build the Team Add-ins glyph for one output size.

    Args:
        size: Output size in pixels.

    Returns:
        The mask to rasterize.  At 16px the piece drops its badge and turns
        solid, because a 3.2-unit stroke and a badge both vanish at that size.
    """
    if size <= 16:
        return kit.filled(*puzzle_piece())

    parts, holes = kit.scale_shape(
        puzzle_piece(), PIECE_SCALE, PIECE_OFFSET, PIECE_OFFSET
    )
    clearance = kit.filled(
        [kit.round_disc(BADGE_CENTER, BADGE_CENTER, BADGE_CLEARANCE)]
    )
    return kit.combined(
        kit.knocked_out(kit.outlined(parts, STROKE, holes), clearance),
        kit.sync_badge(BADGE_CENTER, BADGE_RADIUS, STROKE),
    )


def config_team_addins_mask(size: int) -> kit.Mask:
    """Build the Set Up Shared Add-ins Folder glyph for one output size.

    Args:
        size: Output size in pixels.

    Returns:
        The mask to rasterize.  At 16px the folder turns solid and the piece is
        bitten out of it, so the two Team Add-ins icons stay tellable apart by
        silhouette alone.
    """
    inset = kit.filled(
        *kit.scale_shape(
            puzzle_piece(), INSET_PIECE_SCALE, INSET_PIECE_DX, INSET_PIECE_DY
        )
    )
    folder_parts, folder_holes = folder()
    if size <= 16:
        return kit.knocked_out(kit.filled(folder_parts, folder_holes), inset)
    return kit.combined(kit.outlined(folder_parts, STROKE, folder_holes), inset)


def main() -> None:
    """Regenerate the icons for both Team Add-ins commands."""
    kit.render_set(TEAM_ADDINS_RESOURCES, team_addins_mask)
    kit.render_set(CONFIG_TEAM_ADDINS_RESOURCES, config_team_addins_mask)


if __name__ == "__main__":
    main()
