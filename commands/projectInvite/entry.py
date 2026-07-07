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
import urllib, webbrowser
from urllib.parse import quote
from ...lib import ptAddInUtils as ptutil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

# Specify the command identity information.
CMD_ID = "PTSHD_projectInvite"
CMD_NAME = "Invite to Project..."
CMD_Description = "Invite members to the active document's project.\n\nThis will open your default WEB browser to invite to the hub and project for the active document.\n\nThis command is only available when the active document is saved and in a project.\n\nNote: This command will not work if the active document is not saved or is not in a project."

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
    # Get the target workspace the button will be created in.

    qat = ui.toolbars.itemById("QATRight")

    if qat.controls.itemById("shareDropMenu") is None:
        dropDown = qat.controls.addDropDown(
            "Share Menu", ICON_FOLDER, "shareDropMenu", "FeaturePacksCommand", True
        )
    else:
        dropDown = qat.controls.itemById("shareDropMenu")

    # Add a button to toggle the visibility to the end of the panel.
    control = dropDown.controls.addCommand(cmd_def, "PTSHD_sharesettings", True)
    # control.isPromoted = True


# Executed when add-in is stopped.
def stop():
    # Remove this command's control from the shared QATRight "Share Menu" flyout.
    # The helper deletes the flyout itself only once its last control is gone, so
    # sibling share commands are never torn down out from under each other.
    ptutil.remove_from_qat_right_flyout(CMD_ID, "shareDropMenu")

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Created Event")

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Connect to the events that are needed by this command.
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy,
        command_destroy,
        local_handlers=local_handlers,  # Connect the destroy event
    )


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Execute Event")

    if not ptutil.isSaved():
        return

    try:
        # show a progress bar
        progressBar = ui.progressBar
        progressBar.showBusy("Generating Share Link"),

        # Generate the active document link

        rootLink = quote(app.activeDocument.dataFile.fusionWebURL)

        # Trim all text after the last "/"
        rootLink = rootLink.rpartition("/")[0]
        rootLink = urllib.parse.unquote(rootLink)
        shareLink = f"{rootLink}==/fpV2?redirectSource=fremont&action=ffpInviteMembers"

        # output the link to the text commands
        ptutil.log(f"{CMD_NAME} Invite Link: {shareLink}.\n")

        # Hide the progress bar
        progressBar.hide()

        # Open the share link in the default browser
        webbrowser.open(shareLink)

    except Exception:
        # Write the error message to the TEXT COMMANDS window.
        ptutil.handle_error(CMD_NAME)


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
