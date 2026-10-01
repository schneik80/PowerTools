# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""The Drawing workspace's "Power Tools" panel, shared by the commands in it.

The panel (``config.drawing_panel_id``) lives on ``FusionDocTab``, a built-in
Drawing-workspace tab that is never created or deleted here (3b92f3f). The
panel itself is ours: the first command to start creates it, and the last one
to stop deletes it once it is empty, so start and stop order between the
commands does not matter.

First written inside ``commands/assigndrawingnumber``; lifted here when
Document Information joined the panel, so the two cannot drift apart.
"""

import adsk.core

from .. import config
from ..lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface


def _drawing_tab(cmd_name: str):
    """``FusionDocTab`` on the Drawing workspace, or None (logged) if absent."""
    workspace = ui.workspaces.itemById(config.drawing_workspace)
    if workspace is None:
        ptutil.log(f"[{cmd_name}] Workspace {config.drawing_workspace} not found")
        return None
    tab = workspace.toolbarTabs.itemById(config.drawing_tab_id)
    if tab is None:
        ptutil.log(
            f"[{cmd_name}] Tab '{config.drawing_tab_id}' not found on "
            f"'{config.drawing_workspace}' -- skipping UI registration."
        )
    return tab


def add_to_drawing_panel(cmd_def, cmd_name: str, is_promoted: bool = False):
    """Add *cmd_def* to the drawing Power Tools panel, creating the panel if needed.

    Idempotent: a control that is already there is returned, not duplicated.

    Returns:
        The control, or None when the Drawing workspace or its tab is missing
        on this build.
    """
    tab = _drawing_tab(cmd_name)
    if tab is None:
        return None
    panel = tab.toolbarPanels.itemById(config.drawing_panel_id)
    if panel is None:
        panel = tab.toolbarPanels.add(
            config.drawing_panel_id,
            config.drawing_panel_name,
            config.drawing_panel_after,
            False,
        )
    control = panel.controls.itemById(cmd_def.id)
    if control is None:
        control = panel.controls.addCommand(cmd_def)
    control.isPromoted = is_promoted
    return control


def remove_from_drawing_panel(cmd_id: str, cmd_name: str) -> None:
    """Remove *cmd_id*'s control; delete the panel once nothing is left in it.

    Never raises -- this runs from ``stop()``.
    """
    try:
        tab = _drawing_tab(cmd_name)
        panel = tab.toolbarPanels.itemById(config.drawing_panel_id) if tab else None
        if panel is None:
            return
        control = panel.controls.itemById(cmd_id)
        if control:
            control.deleteMe()
        if panel.controls.count == 0:
            panel.deleteMe()
    except Exception as exc:
        ptutil.log(f"{cmd_name}: could not remove from the drawing panel ({exc})")
