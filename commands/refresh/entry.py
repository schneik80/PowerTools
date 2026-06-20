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

    # this handles the document close and reopen
    id = app.activeDocument.dataFile.id
    sF = app.data.findFileById(id)
    doc_a = app.activeDocument
    doc_a.close(False)
    app.documents.open(sF)


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
