# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Shared UI access-point bootstrap.
#
# In the original separately-installable PowerTools add-ins, every command had
# to *detect* whether a sibling add-in had already created the shared "Power
# Tools" panel or the "PowerTools Settings" QAT flyout, and create it only if it
# was missing. Now that a single consolidated add-in owns all commands, that
# detection is unnecessary: this module creates the two genuinely-shared access
# points exactly once at start-up and removes them once at shut-down.
#
# Scope (per the consolidation plan): ONLY these two access points are managed
# here — the "Power Tools" panel (ToolsTab / FusionSolidEnvironment) and the
# PTSettings flyout in the QAT File dropdown. Every other UI location (the
# Drawing-tab panel, the QATRight Share flyout, SolidTab panels, palettes and
# sketch/modify menus) is still owned by its individual command.
#
# In-scope commands call get_power_tools_panel() / get_pt_settings_flyout() to
# obtain the already-created container — a plain itemById lookup, with no
# create-or-detect branch.

import adsk.core

from .. import config


def _ui():
    return adsk.core.Application.get().userInterface


# ── Power Tools panel (ToolsTab) ──────────────────────────────────────────────

def get_power_tools_panel():
    """Return the shared "Power Tools" toolbar panel, or None if it is absent.

    The panel is guaranteed to exist after create_shared_access_points() has run
    at add-in start-up, so in-scope commands can add their control directly.
    """
    workspace = _ui().workspaces.itemById(config.design_workspace)
    if workspace is None:
        return None
    return workspace.toolbarPanels.itemById(config.my_panel_id)


# ── PowerTools Settings flyout (QAT File dropdown) ────────────────────────────

def get_pt_settings_flyout():
    """Return the shared PTSettings flyout in the QAT File dropdown, or None.

    Guaranteed to exist after create_shared_access_points() when the QAT File
    dropdown is available; callers should still guard with ``if flyout:``.
    """
    qat = _ui().toolbars.itemById("QAT")
    if qat is None:
        return None
    file_dd = adsk.core.DropDownControl.cast(
        qat.controls.itemById("FileSubMenuCommand")
    )
    if file_dd is None:
        return None
    return adsk.core.DropDownControl.cast(
        file_dd.controls.itemById(config.PT_SETTINGS_DROPDOWN_ID)
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def create_shared_access_points():
    """Create the shared "Power Tools" panel once, before any command starts.

    (The old "PowerTools Settings" QAT flyout is gone — those settings were
    consolidated into the Preferences command, which registers its own single
    QAT File entry.)
    """
    workspace = _ui().workspaces.itemById(config.design_workspace)
    if workspace is not None:
        tab = workspace.toolbarTabs.itemById(config.tools_tab_id)
        if tab is None:
            tab = workspace.toolbarTabs.add(config.tools_tab_id, config.my_tab_name)
        if tab.toolbarPanels.itemById(config.my_panel_id) is None:
            tab.toolbarPanels.add(
                config.my_panel_id, config.my_panel_name, config.my_panel_after, False
            )


def remove_shared_access_points():
    """Remove the shared "Power Tools" panel once, after every command has stopped.

    By the time this runs each command has already removed its own control, so
    the panel should be empty; it is deleted unconditionally, and the Tools tab
    is deleted only if it has no remaining panels.
    """
    workspace = _ui().workspaces.itemById(config.design_workspace)
    if workspace is not None:
        panel = workspace.toolbarPanels.itemById(config.my_panel_id)
        if panel is not None:
            panel.deleteMe()
        tab = workspace.toolbarTabs.itemById(config.tools_tab_id)
        if tab is not None and tab.toolbarPanels.count == 0:
            tab.deleteMe()
