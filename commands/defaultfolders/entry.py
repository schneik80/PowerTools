# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import adsk.core, adsk.fusion
import os
from ...lib import ptAddInUtils as ptutil
from ... import settings_store

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "PowerTools Add Project Folders"
CMD_ID = "PT-defaultfolders"
CMD_Description = "Create default project folders if they do not exist"

# Input IDs used in the command dialog
INPUT_FOLDER_SET = "folderSet"
INPUT_PREVIEW = "folderPreview"

# The Basic / Advanced folder sets are user-configurable in the Preferences
# palette (Add Project Folders section) and read at runtime from the settings
# store; see _folder_set().

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_existing_lower() -> list[str]:
    """Return a lowercase list of folder names already in the active project root."""
    try:
        root = adsk.core.Application.get().data.activeProject.rootFolder
        return [f.name.casefold() for f in root.dataFolders]
    except Exception:
        return []


def _folder_set(option_key: str) -> list[str]:
    """Return the user-configurable folder list for 'basic' or 'advanced'.

    Edited in the Preferences palette and stored under
    command_settings.defaultfolders; falls back to the canonical defaults in
    settings_store.
    """
    fallback = settings_store.COMMAND_SETTING_DEFAULTS["defaultfolders"].get(option_key, [])
    value = settings_store.command_setting("defaultfolders", option_key, fallback)
    if not isinstance(value, list):
        return list(fallback)
    return [str(name) for name in value if str(name).strip()]


def _build_preview(folder_set_name: str, existing_lower: list[str]) -> str:
    """
    Return a plain-text preview of the folders for the chosen set.
    Folders that already exist in the project are marked so the user
    knows they will be skipped.
    """
    folders = _folder_set("basic" if folder_set_name == "Basic" else "advanced")
    lines = []
    for name in folders:
        if name.casefold() in existing_lower:
            lines.append(f"  (exists)  {name}")
        else:
            lines.append(f"  + {name}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # **************** Add a button into the UI so the user can run the command. ****************
    # Get the target workspace the button will be created in.
    qat = ui.toolbars.itemById("QAT")

    # Get the drop-down that contains the file related commands.
    fileDropDown = qat.controls.itemById("FileSubMenuCommand")

    # Add a new button to the end of the file menu.
    control = fileDropDown.controls.addCommand(cmd_def)


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    qat = ui.toolbars.itemById("QAT")
    fileDropDown = qat.controls.itemById("FileSubMenuCommand")
    command_control = fileDropDown.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# ---------------------------------------------------------------------------
# Command events
# ---------------------------------------------------------------------------


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    cmd = args.command
    inputs = cmd.commandInputs

    # --- Folder-set selector -------------------------------------------
    dropdown = inputs.addDropDownCommandInput(
        INPUT_FOLDER_SET,
        "Folder set",
        adsk.core.DropDownStyles.TextListDropDownStyle,
    )
    dropdown.listItems.add("Basic", True)  # default selection
    dropdown.listItems.add("Advanced", False)

    # --- Preview (read-only text box) -----------------------------------
    existing_lower = _get_existing_lower()
    initial_preview = _build_preview("Basic", existing_lower)
    num_preview_rows = max(len(_folder_set("basic")), len(_folder_set("advanced"))) + 1

    inputs.addTextBoxCommandInput(
        INPUT_PREVIEW,
        "Folders to create",
        initial_preview,
        num_preview_rows,
        True,  # isReadOnly
    )

    # Connect to the events that are needed by this command.
    ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    ptutil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    """Live-update the preview whenever the folder-set dropdown changes."""
    changed = args.input
    if changed.id != INPUT_FOLDER_SET:
        return

    inputs = args.inputs
    dropdown = adsk.core.DropDownCommandInput.cast(inputs.itemById(INPUT_FOLDER_SET))
    preview_box = adsk.core.TextBoxCommandInput.cast(inputs.itemById(INPUT_PREVIEW))

    selected_name = dropdown.selectedItem.name
    existing_lower = _get_existing_lower()
    preview_box.text = _build_preview(selected_name, existing_lower)


def command_execute(args: adsk.core.CommandEventArgs):
    """Create the selected folder set in the active project root."""
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Read the user's choice from the dialog
        inputs = args.command.commandInputs
        dropdown = adsk.core.DropDownCommandInput.cast(
            inputs.itemById(INPUT_FOLDER_SET)
        )
        use_advanced = dropdown.selectedItem.name == "Advanced"

        # Target folder list (user-configurable in Preferences)
        folders_to_create = _folder_set("advanced" if use_advanced else "basic")

        # Project root
        project = app.data.activeProject
        root = project.rootFolder
        root_folders = root.dataFolders

        existing_lower = [f.name.casefold() for f in root_folders]

        for name in folders_to_create:
            if name.casefold() not in existing_lower:
                root_folders.add(name)

    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
