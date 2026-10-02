# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Power Tools panels in Fusion's four electronics environments.

An electronics design is four documents, each with its own workspace:

* the project (``.fprj``) -- a workspace with no toolbar tabs at all, only
  loose workspace-level panels; a panel of our own added there is shown, a
  control added to its built-in OUTPUTS panel is not;
* the schematic (``.fsch``) and the 2D board (``.fbrd``) -- the Schematic and
  PCB Editors, each with a UTILITIES tab (``ToolsTab``);
* the 3D PCB (``.f3d``) -- a Design workspace that hides the UTILITIES tab, so
  the shared Design Power Tools panel is unreachable there.

None of these workspace ids are published, and Fusion spells three of them
``...Environement``. Workspaces are therefore found by ``productType`` where it
is distinctive, then by candidate id, then by display name, and what resolved
is logged (rule 11). Observed with the Fusion MCP on ADSKMVG91G2F5W,
pre-production 2706.0.116, 2026-10-02.

The panels are ours: the first command to start creates each one and the last
to stop deletes it once it is empty. Built-in tabs and panels are never
touched (rule 10).
"""

from dataclasses import dataclass

import adsk.core

from .. import config
from ..lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

PANEL_NAME = "Power Tools"


@dataclass(frozen=True)
class Place:
    """Where one Power Tools panel goes."""

    key: str
    product_type: str  # "" when the productType is not distinctive
    workspace_ids: tuple
    workspace_names: tuple
    tab_ids: tuple  # () -> a workspace-level panel (the project has no tabs)
    panel_id: str


PLACES = (
    Place(
        "project",
        "ElectronProjectDocProductType",
        ("PCBDesignEnvironement",),
        ("Electronics Design",),
        (),
        config.ecad_project_panel_id,
    ),
    Place(
        "schematic",
        "ElectronSchDocProductType",
        ("SchEditorEnvironement",),
        ("Schematic Editor",),
        ("ToolsTab",),
        config.ecad_schematic_panel_id,
    ),
    Place(
        "board",
        "ElectronPcbDocProductType",
        ("BoardLayoutEnvironement",),
        ("PCB Editor",),
        ("ToolsTab",),
        config.ecad_board_panel_id,
    ),
    # A Design workspace: productType says nothing, so id and name decide.
    Place(
        "pcb3d",
        "",
        ("PCB3DEnvironment",),
        ("3D PCB",),
        ("PCB3DTab",),
        config.ecad_pcb3d_panel_id,
    ),
)


def pick_workspace(workspaces, place: Place):
    """The workspace for *place* out of *workspaces*, or None.

    ``productType`` first (when the place has a distinctive one), then the
    candidate ids, then the display names, case-insensitively. Duck-typed:
    each workspace needs ``id``, ``name`` and ``productType``; a property that
    raises is treated as empty.
    """

    def read(ws, attr) -> str:
        try:
            return str(getattr(ws, attr) or "")
        except Exception:
            return ""

    workspaces = list(workspaces or [])
    if place.product_type:
        for ws in workspaces:
            if read(ws, "productType") == place.product_type:
                return ws
    for wanted in place.workspace_ids:
        for ws in workspaces:
            if read(ws, "id") == wanted:
                return ws
    names = {n.casefold() for n in place.workspace_names}
    for ws in workspaces:
        if read(ws, "name").casefold() in names:
            return ws
    return None


def _panels_of(place: Place, cmd_name: str, create: bool):
    """``(collection, panel)`` for *place*; either may be None (logged)."""
    workspace = pick_workspace(ui.workspaces, place)
    if workspace is None:
        ptutil.log(f"[{cmd_name}] electronics {place.key}: no workspace found")
        return None, None
    collection = None
    if not place.tab_ids:
        collection = workspace.toolbarPanels
    else:
        for tab_id in place.tab_ids:
            tab = workspace.toolbarTabs.itemById(tab_id)
            if tab is not None:
                collection = tab.toolbarPanels
                break
    if collection is None:
        ptutil.log(
            f"[{cmd_name}] electronics {place.key}: none of tabs {place.tab_ids} "
            f"on '{workspace.id}'"
        )
        return None, None
    panel = collection.itemById(place.panel_id)
    if panel is None and create:
        panel = collection.add(place.panel_id, PANEL_NAME, "", False)
        ptutil.log(
            f"[{cmd_name}] electronics {place.key}: panel {place.panel_id} on "
            f"'{workspace.id}'"
            + (f" / {place.tab_ids}" if place.tab_ids else " (workspace level)")
        )
    return collection, panel


def add_to_electronics_panels(cmd_def, cmd_name: str, is_promoted: bool = False):
    """Add *cmd_def* to every electronics Power Tools panel that can be placed.

    Idempotent; a missing workspace or tab is logged and skipped, never
    raised, so the command still registers its definition.

    Returns:
        The keys of the places the control is now on.
    """
    placed = []
    for place in PLACES:
        try:
            _, panel = _panels_of(place, cmd_name, create=True)
            if panel is None:
                continue
            control = panel.controls.itemById(cmd_def.id)
            if control is None:
                control = panel.controls.addCommand(cmd_def)
            control.isPromoted = is_promoted
            placed.append(place.key)
        except Exception as exc:
            ptutil.log(f"[{cmd_name}] electronics {place.key}: could not place ({exc})")
    return placed


def remove_from_electronics_panels(cmd_id: str, cmd_name: str) -> None:
    """Remove *cmd_id*'s control everywhere; delete each panel once empty.

    Never raises -- this runs from ``stop()``.
    """
    for place in PLACES:
        try:
            _, panel = _panels_of(place, cmd_name, create=False)
            if panel is None:
                continue
            control = panel.controls.itemById(cmd_id)
            if control:
                control.deleteMe()
            if panel.controls.count == 0:
                panel.deleteMe()
        except Exception as exc:
            ptutil.log(
                f"[{cmd_name}] electronics {place.key}: could not remove ({exc})"
            )
