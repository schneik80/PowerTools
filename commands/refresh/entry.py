# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Refresh Active Document"
CMD_ID = "PTAT_refresh"
CMD_Description = (
    "Check Team Hub for a newer version of the active document and load it"
)

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    file_dd = ptutil.get_qat_file_dropdown()
    if file_dd:
        file_dd.controls.addCommand(cmd_def, "ExportCommand", False)


# Executed when add-in is stopped.
def stop():
    ptutil.remove_from_qat_file_dropdown(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Event")

    # Refresh pulls the latest Team Hub version by closing and reopening the
    # active document. Closing first is required so Fusion reloads the file from
    # the Hub instead of re-activating the already-open (stale) copy.
    doc_a = app.activeDocument
    if doc_a.dataFile is None:
        ui.messageBox(
            "The active document must be saved to Team Hub before it can be refreshed.",
            CMD_NAME,
        )
        return

    source_file = app.data.findFileById(doc_a.dataFile.id)
    if source_file is None:
        ui.messageBox("Could not locate this document in Team Hub.", CMD_NAME)
        return

    # Compare the open version against the Hub before touching the document: the
    # close-and-reopen costs a full document load and discards unsaved edits, so
    # it is only worth doing when there is actually something newer to load.
    # source_file is the freshly looked-up DataFile, so it carries the current
    # Hub state; the document's own dataFile is passed too as a stale-cache
    # guard (see logic.latest_version).
    name = logic.display_name(source_file)
    current_version = logic.open_version(doc_a.dataFile)
    latest_version = logic.latest_version(source_file, doc_a.dataFile)
    ptutil.log(
        f"{CMD_NAME}: "
        f"{logic.refresh_log_message(name, current_version, latest_version)}"
    )

    # close(False) discards unsaved edits — a destructive action, so confirm
    # first. Which question to ask depends on what the reload would accomplish:
    # loading a newer version, or only reverting the local changes.
    if logic.newer_version_available(current_version, latest_version):
        prompt = (
            logic.discard_for_newer_prompt(name, current_version, latest_version)
            if doc_a.isModified
            else None
        )
    elif doc_a.isModified:
        prompt = logic.discard_to_reload_prompt(name, latest_version)
    else:
        # Already at the latest version with nothing to discard: reopening would
        # reload the same bytes, so report it and leave the document alone.
        ui.messageBox(logic.up_to_date_message(name, latest_version), CMD_NAME)
        return

    if prompt is not None:
        result = ui.messageBox(
            prompt,
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
        if result != adsk.core.DialogResults.DialogYes:
            return

    # Open the looked-up file only after the stale copy is closed; if the open
    # fails the original is already gone, so surface it rather than failing silently.
    doc_a.close(False)
    try:
        app.documents.open(source_file)
    except Exception:
        ptutil.handle_error(CMD_NAME)
        ui.messageBox(
            "Could not reopen the document after refresh. Reopen it from "
            "Team Hub via the Data Panel or the File menu.",
            CMD_NAME,
        )


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
