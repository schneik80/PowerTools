# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

# Specify the command identity information. ***
CMD_ID = "PTSHD_sharesettings"
CMD_NAME = "Change Share Settings"
CMD_Description = "Manage the active document's share link settings. Settings control if the document can be downloaded and is password protected."

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # **************** Add a button into the UI so the user can run the command. ****************

    qat = ui.toolbars.itemById("QATRight")

    if qat.controls.itemById("shareDropMenu") is None:
        dropDown = qat.controls.addDropDown(
            "Share Menu", ICON_FOLDER, "shareDropMenu", "FeaturePacksCommand", True
        )
    else:
        dropDown = qat.controls.itemById("shareDropMenu")

    dropDown.controls.addCommand(cmd_def, "", False)


# Executed when add-in is stopped.
def stop():
    # Remove this command's control from the shared QATRight "Share Menu" flyout.
    # The helper deletes the flyout itself only once its last control is gone, so
    # sibling share commands are never torn down out from under each other.
    ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Called when the user clicks the control. There is no dialog: the work runs
# here so it still happens with no document open (rule 1, #16).
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Created Event")

    # The whole command runs here and no execute handler is registered. The
    # Share Menu is live with no document open, and Fusion never raises
    # execute for an input-less command in that state (rule 1, issue #16).
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )

    # ******************************* Your code here ********************************

    # Guard first: with no document open (the start screen) or an unsaved one,
    # require_document shows the standard message and nothing below runs.
    if ptutil.require_document(CMD_NAME, saved=True) is None:
        return

    # Fusion's own definition; never dereference it unchecked (issue #28).
    shareCmdDef = ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand")
    if shareCmdDef is None:
        ptutil.log(f"{CMD_NAME}: SimpleSharingPublicLinkCommand not found")
        ui.messageBox(
            "Fusion's sharing command is not available in this build",
            "Share Settings",
            0,
            2,
        )
        return
    isShareAllowed = shareCmdDef.controlDefinition.isEnabled

    if isShareAllowed is False:
        ui.messageBox(
            "Sharing is not allowed.\nPlease check if your Team Hub Administrator has disabled sharing",
            "Share Settings",
            0,
            2,
        )
        return

    try:
        # Native command launched from commandCreated (not doExecute, rule 20):
        # needs a Fusion check on both channels before it is trusted (issue #16).
        # Reached only after require_document() and the None check above: a native
        # CommandDefinition.execute() checks no precondition itself (#25 lesson).
        shareCmdDef.execute()

    except Exception:
        # Write the error message to the TEXT COMMANDS window.
        ptutil.handle_error(CMD_NAME)


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
