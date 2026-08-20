# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Merged configuration for the consolidated PowerTools add-in. This single
# module replaces the per-add-in config.py files that previously shipped with
# each separate PowerTools add-in. It is organised into sections:
#   1. Global flags / identity
#   2. Shared UI access points (Design workspace "Power Tools" panel)
#   3. Drawing-workspace panel (Document Tools)
#   4. PowerTools Settings dropdown (QAT File menu)
#   5. Per-domain settings cache (Document Tools)
#   6. Hub configuration (Related Data)
#   7. Palette IDs (Assembly)

import json
import os
import os.path
import sys

import adsk.core

from .lib import ptAddInUtils as ptutil

# ---------------------------------------------------------------------------
# 1. Global flags / identity
# ---------------------------------------------------------------------------

# Master logging gate. DEBUG is enabled by the presence of a ``.debug`` marker
# file in the add-in root (next to this module). Developers toggle verbose
# logging by creating or deleting that file — no code change is required; the
# flag is evaluated when the add-in loads. The marker file is git-ignored, so it
# never ships in a distribution (where it is absent and DEBUG is therefore False).
DEBUG = os.path.isfile(os.path.join(os.path.dirname(__file__), ".debug"))

# Emit structured [PERF] timing lines from the perf_timer context manager in
# lib/ptAddInUtils. Zero runtime cost when False — useful for diagnosing slow
# Hub operations in the Global Parameters commands.
PERF_TRACE = False

# Attach-debugger gate. When the ``.debug`` marker enables DEBUG (above), the
# add-in also starts an in-process ``debugpy`` server on startup so an external
# DAP client (Zed, or a VS Code "attach" config) can connect. The server is
# non-blocking and localhost-only, and it never runs in a shipped build because
# the ``.debug`` marker is git-ignored and absent there. See docs/dev/debugging.md.
WAIT_FOR_DEBUGGER = DEBUG
DEBUGGER_PORT = 5678
# When True, run() blocks until a debugger attaches. Left False so a developer
# who keeps ``.debug`` present for logging is never forced to attach on launch.
DEBUGGER_BLOCK_UNTIL_ATTACHED = False

ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = "IMA LLC"

# Root path of the add-in and its single shared cache directory.
ADDIN_PATH = os.path.dirname(os.path.realpath(__file__))
CACHE_PATH = os.path.join(ADDIN_PATH, "cache")

# ---------------------------------------------------------------------------
# 2. Shared "Power Tools" panel — Design workspace, Tools tab
# ---------------------------------------------------------------------------

design_workspace = "FusionSolidEnvironment"
tools_tab_id = "ToolsTab"
my_tab_name = "Power Tools"

my_panel_id = f"PT_{my_tab_name}"
my_panel_name = "Power Tools"
my_panel_after = ""

# ---------------------------------------------------------------------------
# 3. Drawing workspace — target for commands that run inside a 2D drawing doc.
# FusionDocTab is a built-in Drawing-workspace tab, so we never create or
# delete it; we only add/remove our own PowerTools panel on it.
# ---------------------------------------------------------------------------

drawing_workspace = "FusionDocumentationEnvironment"
drawing_tab_id = "FusionDocTab"
drawing_panel_id = "PT_DrawingPowerTools"
drawing_panel_name = "Power Tools"
drawing_panel_after = ""

# ---------------------------------------------------------------------------
# 3b. Manage tab (Design workspace) — added by the Fusion Manage Extension.
# "ManageTab" is a built-in tab (name "MANAGE"); we never create or delete it,
# we only add/remove our own PowerTools panel on it. Absent when the Manage
# Extension is not enabled for the hub, in which case the command skips its UI.
# ---------------------------------------------------------------------------

manage_workspace = "FusionSolidEnvironment"
manage_tab_id = "ManageTab"
manage_panel_id = "PT_ManagePowerTools"
manage_panel_name = "Power Tools"
manage_panel_after = ""

# ---------------------------------------------------------------------------
# 3c. Animation workspace — target for commands that run inside the Animation
# environment. Unlike every other workspace above, none of these IDs are
# published: not the workspace, not its built-in tab, not its panels. They are
# absent from the API docs and from the shipped binaries, so they were read out
# of the debug log on a live build (Fusion 2704.1.36) and pinned below. The
# catch is that the Animation environment is internally the *Publisher*
# environment, so its IDs say "Publisher", not "Animation" — guessing
# "FusionAnimationEnvironment" never hits.
#
# Every lookup keeps a name-based fallback behind the pinned IDs, and logs what
# it saw, so a build that renumbers or renames these can be fixed by reading the
# debug log rather than by guesswork.
#
# Our panel goes on Fusion's own Animation tab, immediately after its View
# panel (and so before Publish). We never create or delete that tab — the same
# rule as FusionDocTab and ManageTab above; we only add and remove our own
# panel on it. resolve_animation_workspace_id() returns None on a build with no
# Animation environment, in which case the command skips its UI.
# ---------------------------------------------------------------------------

animation_workspace_candidates = (
    "Publisher3DEnvironment",
    "FusionAnimationEnvironment",
    "AnimationEnvironment",
    "NaAnimationEnvironment",
)
animation_panel_id = "PT_AnimationPowerTools"
animation_panel_name = "Power Tools"

# IDs of the built-in tab we put our panel on, and of the built-in panel we
# insert directly after. The Publish panel follows View, so inserting after View
# also places us before Publish.
animation_tab_candidates = ("Animation",)
animation_after_panel_candidates = ("PublisherViewPanel",)

# Display names matched, case-insensitively, when none of the IDs above hit.
animation_workspace_names = ("Animation",)
animation_tab_names = ("Animation",)
animation_after_panel_names = ("View",)


def resolve_animation_workspace_id():
    """Find the ID of Fusion's Animation workspace on this build.

    Tries ``animation_workspace_candidates`` first, then falls back to scanning
    every workspace for one whose display name matches
    ``animation_workspace_names``. The full workspace list is logged on the
    fallback path so the real ID can be read out of the debug log and pinned into
    the candidate tuple.

    Returns:
        The workspace ID string, or None when no Animation workspace exists.
    """
    workspaces = adsk.core.Application.get().userInterface.workspaces
    for candidate in animation_workspace_candidates:
        try:
            if workspaces.itemById(candidate) is not None:
                return candidate
        except Exception:
            continue

    ptutil.log("Animation workspace not found by ID; scanning workspaces.")
    wanted = {name.strip().lower() for name in animation_workspace_names}
    fallback = None
    for workspace in workspaces:
        try:
            workspace_id, name = workspace.id, workspace.name
        except Exception:
            continue
        ptutil.log(f"  workspace id={workspace_id!r} name={name!r}")
        lowered = (name or "").lower()
        if fallback is None and any(want in lowered for want in wanted):
            fallback = workspace_id
    return fallback


def _panel_id_by_name(tab, names):
    """Return the ID of the first panel on *tab* whose display name matches.

    Every panel is logged, so a build that names them differently can be fixed
    by reading the debug log rather than by guesswork.

    Args:
        tab: A Fusion ``ToolbarTab``.
        names: Display names to accept, compared case-insensitively.

    Returns:
        The matching panel ID, or "" when none matches.
    """
    wanted = {name.lower() for name in names}
    match = ""
    for panel in tab.toolbarPanels:
        try:
            panel_id, panel_name = panel.id, panel.name
        except Exception:
            continue
        ptutil.log(f"    animation panel id={panel_id!r} name={panel_name!r}")
        if not match and (panel_name or "").strip().lower() in wanted:
            match = panel_id
    return match


def _anchor_panel_id(tab):
    """Return the ID of the built-in panel our panel is inserted directly after.

    Tries ``animation_after_panel_candidates`` first and only walks the tab's
    panels — logging each one — when none of those IDs is present.

    Returns:
        The matching panel ID, or "" when none matches.
    """
    panels = tab.toolbarPanels
    for candidate in animation_after_panel_candidates:
        try:
            if panels.itemById(candidate) is not None:
                return candidate
        except Exception:
            continue
    return _panel_id_by_name(tab, animation_after_panel_names)


def _find_animation_tab(workspace):
    """Return Fusion's built-in Animation tab, or None.

    Tries ``animation_tab_candidates`` first, then matches on display name, then
    settles for whichever tab actually carries the panel we want to sit next to
    rather than assuming a position, and finally falls back to the first tab so a
    build that renames everything still gets the command somewhere usable.
    """
    tabs = workspace.toolbarTabs
    for candidate in animation_tab_candidates:
        try:
            tab = tabs.itemById(candidate)
        except Exception:
            continue
        if tab is not None:
            return tab

    ptutil.log("Animation tab not found by ID; scanning tabs.")
    wanted = {name.strip().lower() for name in animation_tab_names}
    fallback = None
    for tab in tabs:
        try:
            tab_id, tab_name = tab.id, tab.name
        except Exception:
            continue
        ptutil.log(f"  animation tab id={tab_id!r} name={tab_name!r}")
        if fallback is None:
            fallback = tab
        if any(want in (tab_name or "").lower() for want in wanted):
            return tab
        if _panel_id_by_name(tab, animation_after_panel_names):
            return tab
    return fallback


def get_or_create_animation_panel(workspace_id):
    """Find or create the PowerTools panel on Fusion's Animation tab.

    The panel is placed immediately after the built-in View panel, which puts it
    before Publish. ``ToolbarPanels.add`` takes the anchor panel's ID and an
    ``isBefore`` flag, so this passes ``False`` to insert after it. With no
    anchor found, the panel is appended rather than skipped.

    Args:
        workspace_id: The Animation workspace ID from
            ``resolve_animation_workspace_id``.

    Returns:
        A ``(panel, tab_id)`` pair, or ``(None, None)`` when the workspace or
        its tab cannot be found. The tab ID is returned so teardown can find the
        panel again without repeating the search.
    """
    workspace = adsk.core.Application.get().userInterface.workspaces.itemById(
        workspace_id
    )
    if workspace is None:
        return None, None

    tab = _find_animation_tab(workspace)
    if tab is None:
        return None, None

    existing = tab.toolbarPanels.itemById(animation_panel_id)
    if existing is not None:
        return existing, tab.id

    after_id = _anchor_panel_id(tab)
    panel = tab.toolbarPanels.add(
        animation_panel_id, animation_panel_name, after_id, False
    )
    return panel, tab.id


# ---------------------------------------------------------------------------
# 4. Shared PowerTools Settings dropdown in the QAT File menu
# ---------------------------------------------------------------------------

PT_SETTINGS_DROPDOWN_ID = "PTSettings"
PT_SETTINGS_DROPDOWN_NAME = "PowerTools Settings"


def get_or_create_pt_settings_dropdown():
    """Return the shared PowerTools Settings dropdown in the QAT file menu, creating it if absent.

    Retained for compatibility; the consolidated add-in creates this dropdown
    once at startup via commands/_ui_bootstrap.py. Uses DropDownControl.cast() —
    required for itemById to work correctly on controls nested inside built-in
    menus like FileSubMenuCommand.
    """
    app = adsk.core.Application.get()
    ui = app.userInterface
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return None
    file_dropdown = adsk.core.DropDownControl.cast(
        qat.controls.itemById("FileSubMenuCommand")
    )
    if not file_dropdown:
        return None

    existing = file_dropdown.controls.itemById(PT_SETTINGS_DROPDOWN_ID)
    if existing:
        return adsk.core.DropDownControl.cast(existing)

    return file_dropdown.controls.addDropDown(
        PT_SETTINGS_DROPDOWN_NAME, "", PT_SETTINGS_DROPDOWN_ID
    )


def remove_from_pt_settings_dropdown(control_id: str) -> None:
    """Remove *control_id* from the PowerTools Settings dropdown.

    Deletes the dropdown itself when no children remain.
    """
    app = adsk.core.Application.get()
    ui = app.userInterface
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return
    file_dropdown = adsk.core.DropDownControl.cast(
        qat.controls.itemById("FileSubMenuCommand")
    )
    if not file_dropdown:
        return

    pt_settings = adsk.core.DropDownControl.cast(
        file_dropdown.controls.itemById(PT_SETTINGS_DROPDOWN_ID)
    )
    if not pt_settings:
        return

    ctrl = pt_settings.controls.itemById(control_id)
    if ctrl:
        ctrl.deleteMe()

    if pt_settings.controls.count == 0:
        pt_settings.deleteMe()


# ---------------------------------------------------------------------------
# 5. Shared settings cache (Document Tools)
# ---------------------------------------------------------------------------

CACHE_DIR = CACHE_PATH
SETTINGS_FILE = os.path.join(CACHE_DIR, "settings.json")


def load_settings() -> dict:
    data = ptutil.read_json(SETTINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    ptutil.write_json_atomic(SETTINGS_FILE, settings)


# ---------------------------------------------------------------------------
# 6. Hub configuration (Related Data)
# ---------------------------------------------------------------------------

# List of allowed hub IDs, populated by loadHub().
COMPANY_HUB = []

# Per-hub config: hub_id -> {"name": str, "project_id": str, "folder_id": str}
COMPANY_HUB_CONFIGS = {}


def loadHub(__file__):
    """Load hub configuration from hub.json and populate COMPANY_HUB / COMPANY_HUB_CONFIGS."""
    global COMPANY_HUB, COMPANY_HUB_CONFIGS

    my_addin_path = os.path.dirname(os.path.realpath(__file__))
    my_hub_path = os.path.join(my_addin_path, "cache", "hub.json")

    if not os.path.isfile(my_hub_path):
        # No hub configured yet — commands will surface their own error message.
        COMPANY_HUB = []
        COMPANY_HUB_CONFIGS = {}
        return

    with open(my_hub_path) as json_file:
        hub_data = json.load(json_file)

    hubs = hub_data.get("hubs", [])
    COMPANY_HUB = [entry["id"] for entry in hubs]
    COMPANY_HUB_CONFIGS = {
        entry["id"]: {
            "name": entry.get("name", ""),
            "project_id": entry.get("project_id", ""),
            "project_name": entry.get("project_name", ""),
            "folder_id": entry.get("folder_id", ""),
            "folder_name": entry.get("folder_name", ""),
        }
        for entry in hubs
    }


def reload_hub_config():
    """Reload hub configuration from disk. Call after hub.json is written."""
    loadHub(__file__)


loadHub(__file__)

# ---------------------------------------------------------------------------
# 6b. Team Add-ins
# ---------------------------------------------------------------------------
#
# Team Add-ins has no hub configuration to store: the location is a convention
# (<active hub>/Assets/Shared Addins), resolved live by
# commands/teamaddins/team_fs.py. All this section contributes is where add-ins
# get installed to.


def fusion_addins_dir() -> str:
    """Return the platform-appropriate Fusion AddIns directory.

    This is where Fusion scans for add-ins at start-up, and where Team Add-ins
    installs each package as ``<addin id>/``.
    """
    if sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"
        )
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Autodesk",
        "Autodesk Fusion 360",
        "API",
        "AddIns",
    )


# ---------------------------------------------------------------------------
# 7. Palette IDs (Assembly)
# ---------------------------------------------------------------------------

assembly_builder_palette_id = (
    f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_assembly_builder_palette"
)
assembly_palette_id = f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_assembly_palette"
preferences_palette_id = (
    f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_preferences_palette"
)
team_addins_palette_id = (
    f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_team_addins_palette"
)

# ---------------------------------------------------------------------------
# 8. Preferences / user settings store
# ---------------------------------------------------------------------------

# Per-user preferences live in their own root ``settings/`` folder (git-ignored,
# created on first run). This is distinct from the runtime ``cache/`` folder.
SETTINGS_DIR = os.path.join(ADDIN_PATH, "settings")
SETTINGS_PREFS_FILE = os.path.join(SETTINGS_DIR, "preferences.json")

# Base URL for per-command documentation opened from the Preferences palette.
# Each command's registry ``doc`` entry is appended (URL-encoded). The repo is
# private, so these links assume the authorized user has GitHub access.
DOCS_BASE_URL = "https://github.com/schneik80/PowerTools/blob/release/docs/"
