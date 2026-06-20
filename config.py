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

import adsk.core
import os
import os.path
import json

from .lib import ptAddInUtils as ptutil

# ---------------------------------------------------------------------------
# 1. Global flags / identity
# ---------------------------------------------------------------------------

# Master logging gate. When True, more information is written to the Fusion
# Text Command window. Set False for distribution.
DEBUG = True

# Emit structured [PERF] timing lines from the perf_timer context manager in
# lib/ptAddInUtils. Zero runtime cost when False — useful for diagnosing slow
# Hub operations in the Global Parameters commands.
PERF_TRACE = False

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
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


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
    my_hub_path = os.path.join(my_addin_path, "hub.json")

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
# 7. Palette IDs (Assembly)
# ---------------------------------------------------------------------------

assembly_builder_palette_id = (
    f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_assembly_builder_palette"
)
assembly_intent_palette_id = (
    f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_assembly_intent_palette"
)
