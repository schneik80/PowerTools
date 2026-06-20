# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import adsk.core
import os, os.path
import json
from ...lib import ptAddInUtils as ptutil
from ... import config
from .. import _ui_bootstrap

app = adsk.core.Application.get()
ui = app.userInterface

# Command identity information.
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_configHub"
CMD_NAME = "Select Related Data Folder"
CMD_Description = (
    "Select the cloud folder where your start parts and templates must be located. "
    "The Create Related Data command copies templates from this folder to create a "
    "related document that lets multiple people work on different downstream domains "
    "from a shared source part.\n"
    "This folder must be configured once for each Team Hub.\n"
    "The Create Related Data command is in the Design workspace -> Create panel."
)

# QAT flyout (shared across PowerTools add-ins — create only if absent).
PT_SETTINGS_ID = "PTSettings"
PT_SETTINGS_NAME = "PowerTools Settings"

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Path to hub.json at the add-in root (two levels up from this file's directory).
ADDIN_PATH = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
HUB_JSON_PATH = os.path.join(ADDIN_PATH, "hub.json")


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the shared PowerTools Settings flyout (created once by the central bootstrap).
    flyout = _ui_bootstrap.get_pt_settings_flyout()
    if flyout:
        # Add the command into the flyout.
        flyout.controls.addCommand(cmd_def)


# Executed when add-in is stopped.
def stop():
    # Remove only confighub's own control from the shared PowerTools Settings flyout.
    flyout = _ui_bootstrap.get_pt_settings_flyout()
    if flyout:
        command_control = flyout.controls.itemById(CMD_ID)
        if command_control:
            command_control.deleteMe()

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


def _load_hubs():
    """Return the hubs list from hub.json, or an empty list if the file does not exist."""
    if not os.path.isfile(HUB_JSON_PATH):
        return []
    with open(HUB_JSON_PATH) as f:
        data = json.load(f)
    return data.get("hubs", [])


def _resolve_hub_for_folder(folder):
    """Return the DataHub that owns *folder*, or None if not found."""
    project = folder.parentProject
    if project is None:
        return None
    for i in range(app.data.dataHubs.count):
        hub = app.data.dataHubs.item(i)
        if hub.dataProjects.itemById(project.id) is not None:
            return hub
    return None


def _find_hub_entry(hub_id, hubs):
    """Return the entry dict for *hub_id*, or None if not present."""
    for entry in hubs:
        if entry.get("id") == hub_id:
            return entry
    return None


# Function that is called when a user clicks the corresponding button in the UI.
# Runs the entire flow inline — no command inputs are added, so Fusion auto-executes
# without showing a command dialog.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    active_hub = app.data.activeHub
    hubs = _load_hubs()

    # If the active hub already has an entry, surface the current location and
    # let the user cancel out or continue to repoint it.
    existing = _find_hub_entry(active_hub.id, hubs) if active_hub else None
    if existing is not None:
        result = ui.messageBox(
            f'"{existing.get("name", active_hub.name)}" is already configured.'
            f'\n\nProject: {existing.get("project_name", "")}'
            f'\nFolder: {existing.get("folder_name", "")}'
            f"\n\nClick OK to choose a new location, or Cancel to leave it unchanged.",
            "Hub Already Configured",
            adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType,
        )
        if result != adsk.core.DialogResults.DialogOK:
            return

    # Tell the user what to do, then open the cloud folder picker.
    ui.messageBox(
        "Browse to the cloud folder that contains your start parts or templates.",
        "Select Related Data Folder",
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType,
    )

    dialog = ui.createCloudFolderDialog()
    dialog.title = "Select Templates Folder"
    if app.activeDocument is not None and app.activeDocument.isSaved:
        dialog.initialFolder = app.activeDocument.dataFile.parentFolder
    if dialog.showDialog() != adsk.core.DialogResults.DialogOK:
        return

    selected_folder = dialog.dataFolder
    project = selected_folder.parentProject
    hub = _resolve_hub_for_folder(selected_folder)
    if hub is None or project is None:
        ui.messageBox(
            "Could not determine which hub owns the selected folder.\nNo changes were made.",
            "Hub Not Found",
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
        return

    ptutil.log(
        f"{CMD_NAME} Hub: {hub.name} ({hub.id}) | Project: {project.name} ({project.id}) "
        f"| Folder: {selected_folder.name} ({selected_folder.id})"
    )

    # Upsert by hub id: replace the existing entry if present, otherwise append.
    new_entry = {
        "id": hub.id,
        "name": hub.name,
        "project_id": project.id,
        "project_name": project.name,
        "folder_id": selected_folder.id,
        "folder_name": selected_folder.name,
    }
    replaced = False
    for i, entry in enumerate(hubs):
        if entry.get("id") == hub.id:
            hubs[i] = new_entry
            replaced = True
            break
    if not replaced:
        hubs.append(new_entry)

    with open(HUB_JSON_PATH, "w") as f:
        json.dump({"hubs": hubs}, f, indent=2)

    ptutil.log(f"{CMD_NAME} hub.json updated: {hubs}")

    # Reload in-memory config so all commands immediately see the new hub.
    config.reload_hub_config()

    action = "updated" if replaced else "added"
    ui.messageBox(
        f"Hub {action} successfully."
        f"\nHub: {hub.name}"
        f"\nProject: {project.name}"
        f"\nFolder: {selected_folder.name}",
        "Hub Configured",
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType,
    )
