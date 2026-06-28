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
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Refresh Active Document"
CMD_ID = "PTAT-refresh"
CMD_Description = (
    "Close and reopen the active document to get new versions from Team Hub"
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
        control = file_dd.controls.addCommand(cmd_def, "ExportCommand", False)


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

    # close(False) discards unsaved edits — a destructive action, so confirm first.
    if doc_a.isModified:
        result = ui.messageBox(
            "This document has unsaved changes that will be discarded when it is "
            "refreshed to the latest Team Hub version.\n\nContinue?",
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
