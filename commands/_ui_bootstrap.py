# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
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
    """Create the two shared access points once, before any command starts."""
    workspace = _ui().workspaces.itemById(config.design_workspace)
    if workspace is not None:
        tab = workspace.toolbarTabs.itemById(config.tools_tab_id)
        if tab is None:
            tab = workspace.toolbarTabs.add(config.tools_tab_id, config.my_tab_name)
        if tab.toolbarPanels.itemById(config.my_panel_id) is None:
            tab.toolbarPanels.add(
                config.my_panel_id, config.my_panel_name, config.my_panel_after, False
            )

    qat = _ui().toolbars.itemById("QAT")
    if qat is not None:
        file_dd = adsk.core.DropDownControl.cast(
            qat.controls.itemById("FileSubMenuCommand")
        )
        if file_dd is not None and file_dd.controls.itemById(
            config.PT_SETTINGS_DROPDOWN_ID
        ) is None:
            file_dd.controls.addDropDown(
                config.PT_SETTINGS_DROPDOWN_NAME, "", config.PT_SETTINGS_DROPDOWN_ID
            )


def remove_shared_access_points():
    """Remove the two shared access points once, after every command has stopped.

    By the time this runs each command has already removed its own control, so
    the panel / flyout should be empty; they are deleted unconditionally, and the
    Tools tab is deleted only if it has no remaining panels.
    """
    workspace = _ui().workspaces.itemById(config.design_workspace)
    if workspace is not None:
        panel = workspace.toolbarPanels.itemById(config.my_panel_id)
        if panel is not None:
            panel.deleteMe()
        tab = workspace.toolbarTabs.itemById(config.tools_tab_id)
        if tab is not None and tab.toolbarPanels.count == 0:
            tab.deleteMe()

    flyout = get_pt_settings_flyout()
    if flyout is not None:
        flyout.deleteMe()
