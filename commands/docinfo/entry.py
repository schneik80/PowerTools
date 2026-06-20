# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core, adsk.fusion
import os
from ...lib import ptAddInUtils as ptutil
from ... import config
from .. import _ui_bootstrap

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Document Information"
CMD_ID = "PTND-docinfo"
CMD_Description = (
    "Document data management Id`s for document in Autodesk`s Fusion Industry Cloud"
)
IS_PROMOTED = True

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Holds references to event handlers
local_handlers = []


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Add command created handler. The function passed here will be executed when the command is executed.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control ********************************
    # Add the control to the shared Power Tools panel.
    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        # Create the command control, i.e. a button in the UI.
        control = panel.controls.addCommand(cmd_def)

        # Now you can set various options on the control such as promoting it to always be shown.
        control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    panel = _ui_bootstrap.get_power_tools_panel()
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    # Connect to the events that are needed by this command.
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandCreatedEventArgs):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)

        # Check that the active document has been saved.
        if ptutil.isSaved() == False:
            return

        root_name = design.rootComponent.name  # Get root component name.
        mTitle = f"{root_name} Document Info"

        docHub = app.data.activeHub.id
        docHubName = app.data.activeHub.name

        docProject = app.activeDocument.dataFile.parentProject.id
        docProjectName = app.activeDocument.dataFile.parentProject.name

        docFolder = app.activeDocument.dataFile.parentFolder.id
        if app.activeDocument.dataFile.parentFolder.isRoot == True:
            docFolderName = "Project Root"
        else:
            docFolderName = app.activeDocument.dataFile.parentFolder.name

        rootTest = app.activeDocument.dataFile.parentFolder
        docPath = f"{app.activeDocument.dataFile.parentFolder.name}"
        while rootTest.isRoot == False:
            nextFolder = rootTest.parentFolder.name
            docPath = f"{nextFolder} / {docPath}"
            rootTest = rootTest.parentFolder

        docPath = f"{docPath} / {app.activeDocument.dataFile.name}"
        docID = app.activeDocument.dataFile.id
        docName = app.activeDocument.dataFile.name
        docVersion = app.activeDocument.dataFile.versionNumber
        docVersions = app.activeDocument.dataFile.latestVersionNumber
        # docVersionUser = app.activeDocument.dataFile.lastUpdatedBy.displayName
        docVersionComment = app.activeDocument.dataFile.description
        docVersionBuild = app.activeDocument.version
        appVersionBuild = app.version

        resultString = (
            f"<b>Team HUB Name:</b> {docHubName} <br>"
            f"<b>Team HUB ID:</b> {docHub} <p>"
            f"<b>Project Name:</b> {docProjectName} <br>"
            f"<b>Project ID:</b> {docProject} <p>"
            f"<b>Parent Folder Name:</b> {docFolderName} <br>"
            f"<b>Parent Folder ID:</b> {docFolder} <p>"
            f"<b>Path:</b> {docPath} <p>"
            f"<b>Document Name:</b> {docName} <br>"
            f"<b>Document ID:</b> {docID}<br>"
            f"<b>Document Version:</b> Version {docVersion} of {docVersions}<br>"
            f"<b>Version Comment:</b> ''{docVersionComment}''<br>"
            f"<b>Version Build:</b> Saved by Fusion build {docVersionBuild} (current build is {appVersionBuild})"
        )

        if app.activeDocument.version == app.version:
            VersionMigration = False
            messageIcon = 2
        else:
            VersionMigration = True
            messageIcon = 3

        if VersionMigration == True:
            mTitle = f"{root_name} Document Info - Document will migrate on save"
            resultString += (
                f"<br>"
                f"<br>"
                f"<b>Document will migrate to new schema {appVersionBuild} if saved.</b><br>"
                f"Team members must be on the same client version to work with this document after save."
            )

        ui.messageBox(resultString, mTitle, 0, messageIcon)

    except:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
