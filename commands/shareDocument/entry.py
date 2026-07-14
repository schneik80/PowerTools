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

# Specify the command identity information.
CMD_ID = "PTSHD_sharedocument"
CMD_NAME = "Get a Share Link"
CMD_Description = "Share active Document and copy the link to the clipboard."

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
    control = dropDown.controls.addCommand(cmd_def, "", False)
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
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Execute Event")

    # ******************************** Your code here ********************************

    shareCmdDef = ui.commandDefinitions.itemById("SimpleSharingPublicLinkCommand")
    isShareAllowed = shareCmdDef.controlDefinition.isEnabled

    if not ptutil.isSaved():
        return

    if not isShareAllowed:
        permLink = app.activeDocument.designDataFile.fusionWebURL
        ptutil.clipText(permLink)
        ui.messageBox(
            "Sharing is not allowed. Please check if your Team Hub Administrator has disabled sharing.<br><br>A private perma-link was copied to clipboard instead. This link will only allow Team hub members access to the document details page.",
            "Share Document",
            0,
            2,
        )
        return

    try:
        shareState = app.activeDocument.dataFile.sharedLink

        # check share settings
        if shareState.isShared == True:
            wasShared = True
        else:
            wasShared = False

        # show a progress bar
        progressBar = ui.progressBar

        # Check if the document is shared
        if shareState.isShared == False:
            # creating a link can take a few seconds so show a busy bar
            (progressBar.showBusy("Generating Share Link"),)

            shareState.isShared = True  # Share the document

        # Get the shared link
        shareLink = shareState.linkURL

        if shareLink == "":
            ptutil.log("Failed to get a link to the document")
            ui.messageBox(
                "Failed to share the document.",
                "Share Document",
                1,
                2,
            )
            exit(0)

        # Copy the shared link to the clipboard
        ptutil.clipText(shareLink)

        if wasShared == True:
            resultString = "Document is already shared <br>"
        else:
            resultString = "<b>Document is now shared.</b> <br>"

        resultString += f"A <b>Share link</b> for {app.activeDocument.name}: <a href=''{shareLink}''>{shareLink}</a> was added to the clipboard.<br><br>Note:"

        if shareState.isDownloadAllowed == False:
            noDownload = True
        else:
            noDownload = False

        if shareState.isPasswordRequired == True:
            passwordProtected = True
        else:
            passwordProtected = False

        if noDownload == True:
            resultString += "<br>Downloading from the link is not turned on. To enable downloading, go to <b>Share Settings</b><br>"
        else:
            resultString += (
                "<br>Downloading the document from the share link is allowed.<br>"
            )

        if passwordProtected == True:
            resultString += "<br>The share is password protected.<br>"
        else:
            resultString += "<br>The share does not have a password. To set a password, go to <b>Share Settings</b><br>"

        if app.activeProduct.productType == "DesignProductType":
            rootComp = app.activeProduct.rootComponent

            if has_external_child_reference(rootComp):
                ptutil.log(f"{CMD_NAME} Document has external references")
                if noDownload == True:
                    resultString += "<br>This design has external references. Sharing this design will allow the referenced designs to be viewed but not downloaded. <br>"
                else:
                    resultString += "<br>This design has external references. Sharing this design will also share the referenced designs. To avoid sharing referenced designs, either save this design as a new document and break link or disable download.<br>"
            else:
                ptutil.log(f"{CMD_NAME} Document has no external references")

        # Hide the progress bar
        progressBar.hide()

        # Display the message to the user
        ui.messageBox(
            resultString,
            "Share Document",
            0,
            2,
        )

    except Exception:
        # Write the error message to the TEXT COMMANDS window.
        ptutil.handle_error(CMD_NAME)


def has_external_child_reference(component: adsk.fusion.Component) -> bool:
    for occurrence in component.occurrences:
        if occurrence.isReferencedComponent:
            return True
        # Recursively check child components
        if has_external_child_reference(occurrence.component):
            return True
    return False


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
