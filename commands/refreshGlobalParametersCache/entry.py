# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import adsk.core
import os
from ...lib import ptAddInUtils as ptutil
from ...lib.ptAddInUtils import cache_utils as cache
from ... import config
from .. import _ui_bootstrap

app = adsk.core.Application.get()
ui = app.userInterface

# Command identity
CMD_ID = "PTAT-refreshGlobalParametersCache"
CMD_NAME = "Refresh Global Parameters Cache"
CMD_Description = (
    "Scan the active project for global parameter sets and update the cache."
)

# UI placement (reuse config from other commands)
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
PANEL_ID = config.my_panel_id
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
IS_PROMOTED = False


def start():
    existing_def = ui.commandDefinitions.itemById(CMD_ID)
    if existing_def:
        existing_def.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED


def stop():
    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        existing = panel.controls.itemById(CMD_ID)
        if existing:
            existing.deleteMe()
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


def command_created(args):
    ptutil.log(f"{CMD_NAME} Command Created Event")
    refresh_cache_for_active_project()


def refresh_cache_for_active_project():
    """Scan the active project and write the canonical gp_folder and gp_docs caches.

    Always does a fresh Hub scan (ignores any existing cache) so the result
    reflects the current state of the project.  Writes the same files that
    Global Parameters and Link Global Parameters read at startup.
    """
    project = cache.get_active_project(CMD_NAME)
    if not project:
        ui.messageBox("No active Fusion project found.")
        return

    # Bypass the cache-first lookup — this command exists to fix a stale cache.
    root = project.rootFolder
    folder = None
    try:
        for i in range(root.dataFolders.count):
            f = root.dataFolders.item(i)
            if f.name == cache.GLOBAL_PARAMS_FOLDER_NAME:
                folder = f
                break
    except Exception:
        ptutil.handle_error(CMD_NAME)
        return

    if not folder:
        ui.messageBox(
            f"No '{cache.GLOBAL_PARAMS_FOLDER_NAME}' folder found in this project."
        )
        return

    # Write both cache files via cache_utils so the format stays consistent.
    cache.write_global_params_folder_cache(project, folder, CMD_NAME)

    doc_map = {}
    for i in range(folder.dataFiles.count):
        df = folder.dataFiles.item(i)
        doc_map[df.name] = df
    cache.write_param_docs_cache(project, doc_map, CMD_NAME)

    n = len(doc_map)
    ptutil.log(f"{CMD_NAME}: cache refreshed — {n} parameter set(s) found")
    ui.messageBox(
        f"Global Parameters cache refreshed for project '{project.name}'.\n"
        f"{n} parameter set(s) found."
    )
