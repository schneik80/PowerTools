# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Shared discovery of Fusion's Inspect panels, for commands that sit in them.

Which design tabs a build actually shows varies with the Fusion version and the
user's entitlements, so the panels are discovered by walking the tab tree at
runtime rather than listed. A hardcoded tab list silently misses a panel on one
build and logs "not found" noise on another.

Every panel this returns is **built in**. Add and remove controls; never create
or delete the panel itself (3b92f3f).

First written inside ``commands/measurepath``; lifted here when Match Units
needed the same placement, so the two cannot drift apart.
"""

import adsk.core

from .. import config
from ..lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

# Matched as a substring of the panel id, case-insensitively. Fusion names them
# all "InspectPanel" today; matching loosely survives a per-workspace suffix.
_PANEL_MATCH = "inspect"

# productType's exact value is not documented, so match it loosely and fall back
# to the known design workspace id.
_DESIGN_PRODUCT_MATCH = "design"


def _is_design_workspace(workspace) -> bool:
    """True if *workspace* hosts a Design product, so it carries an Inspect panel."""
    if workspace.id == config.design_workspace:
        return True
    try:
        product = (workspace.productType or "").lower()
    except Exception:
        return False
    return _DESIGN_PRODUCT_MATCH in product


def design_inspect_panels(cmd_name: str) -> list:
    """Every Inspect panel of every design-product workspace.

    Deduplicated by panel id: Fusion shows one panel across several tabs, so the
    same panel can be reached more than once while walking the tab tree, and
    adding a control twice would either throw or leave a duplicate button.

    Args:
        cmd_name: The calling command's name, for the error log only.

    Returns:
        The panels, in discovery order. Empty on a build with no design
        workspace, or if the walk failed -- which is logged, not raised, so a
        command can still register its definition.
    """
    seen = set()
    panels = []
    try:
        for workspace in ui.workspaces:
            if not _is_design_workspace(workspace):
                continue
            groups = [workspace.toolbarPanels]
            try:
                groups.extend(tab.toolbarPanels for tab in workspace.toolbarTabs)
            except Exception:
                pass
            for collection in groups:
                if not collection:
                    continue
                for panel in collection:
                    panel_id = panel.id or ""
                    if _PANEL_MATCH not in panel_id.lower():
                        continue
                    if panel_id in seen:
                        continue
                    seen.add(panel_id)
                    panels.append(panel)
    except Exception:
        ptutil.handle_error(f"{cmd_name}.design_inspect_panels")
    return panels


def add_to_inspect_panels(cmd_def, cmd_name: str, is_promoted: bool = False) -> list:
    """Add *cmd_def* to every design Inspect panel that does not already have it.

    Args:
        cmd_def: The command definition to place.
        cmd_name: The command's name, for the log.
        is_promoted: Whether the control shows in the collapsed panel.

    Returns:
        The ids of the panels the control was added to.
    """
    placed = []
    for panel in design_inspect_panels(cmd_name):
        try:
            if panel.controls.itemById(cmd_def.id):
                continue
            control = panel.controls.addCommand(cmd_def)
            control.isPromoted = is_promoted
            placed.append(panel.id)
        except Exception as place_err:
            ptutil.log(f"{cmd_name}: could not add to {panel.id} ({place_err})")

    if placed:
        ptutil.log(f"{cmd_name} added to {len(placed)} panel(s): {placed}")
    else:
        ptutil.log(f"{cmd_name}: no Inspect panel found to add to")
    return placed


def remove_from_inspect_panels(cmd_id: str, cmd_name: str) -> None:
    """Remove *cmd_id*'s control from every design Inspect panel.

    The panels themselves are built in and are left alone.
    """
    for panel in design_inspect_panels(cmd_name):
        try:
            control = panel.controls.itemById(cmd_id)
            if control:
                control.deleteMe()
        except Exception as drop_err:
            ptutil.log(f"{cmd_name}: could not remove from {panel.id} ({drop_err})")
