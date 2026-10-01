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
import adsk.drawing
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from .._drawing_panel import add_to_drawing_panel, remove_from_drawing_panel
from ..partnumber_shared import mfgdm_props
from . import mfgdm_status

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Document Information"
CMD_ID = "PTND_docinfo"
CMD_Description = "Show the hub, project, folder, version and MFGDM identifiers of the active design or drawing, and warn when saving it would migrate it to the running Fusion build."
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

    # And to the Drawing workspace's Power Tools panel, shared with Assign
    # Drawing Number.
    add_to_drawing_panel(cmd_def, CMD_NAME, IS_PROMOTED)


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    panel = _ui_bootstrap.get_power_tools_panel()
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    remove_from_drawing_panel(CMD_ID, CMD_NAME)

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


def _design_of(doc):
    """The Design product of *doc*, or None.

    Never ask a drawing for its products' ``productType``: on a DrawingDocument
    it raises ``InternalValidationError : adapter`` (ADSKMVG91G2F5W,
    pre-production, 2026-10-01). Callers branch on DrawingDocument first.
    """
    try:
        return adsk.fusion.Design.cast(
            doc.products.itemByProductType("DesignProductType")
        )
    except Exception:
        return None


def _drawing_mfgdm(doc, hub) -> tuple[str, bool]:
    """MFGDM block for a drawing: the DrawingItem, then its source design."""
    item = mfgdm_status.item_summary(
        mfgdm_props.gql, hub.mfgdmId or "", doc.dataFile.id or ""
    )

    source_name = source_lineage = ""
    source_model = None
    refs = doc.documentReferences
    if refs and refs.count > 0:
        # A drawing references at most one 3D design (see Assign Drawing Number).
        ref = refs.item(0)
        source_name = ref.dataFile.name or ""
        source_lineage = ref.dataFile.id or ""
        # Never open the source design here; report what is already loaded.
        source_doc = ref.referencedDocument
        design = _design_of(source_doc) if source_doc else None
        if design is None:
            source_model = {"status": mfgdm_status.NOT_LOADED}
        else:
            source_model = mfgdm_status.model_summary(
                mfgdm_props.gql, mfgdm_props.design_model_id(design)
            )

    return mfgdm_status.render_drawing(item, source_name, source_lineage, source_model)


def command_execute(args: adsk.core.CommandCreatedEventArgs):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = ptutil.require_document(CMD_NAME, "document", saved=True)
        if doc is None:
            return

        is_drawing = isinstance(doc, adsk.drawing.DrawingDocument)
        design = None if is_drawing else _design_of(doc)
        if not is_drawing and design is None:
            ui.messageBox(
                ptutil.document_required_message(CMD_NAME, "design"), CMD_NAME
            )
            return

        data_file = doc.dataFile
        title_name = doc.name if is_drawing else design.rootComponent.name
        mTitle = f"{title_name} Document Info"

        # The document's own hub, not the Data Panel's active one: MFGDM needs
        # this hub's mfgdmId, and the two can differ.
        hub = data_file.parentProject.parentHub
        docHub = hub.id
        docHubName = hub.name

        docProject = data_file.parentProject.id
        docProjectName = data_file.parentProject.name

        docFolder = data_file.parentFolder.id
        if data_file.parentFolder.isRoot:
            docFolderName = "Project Root"
        else:
            docFolderName = data_file.parentFolder.name

        rootTest = data_file.parentFolder
        docPath = f"{data_file.parentFolder.name}"
        while not rootTest.isRoot:
            nextFolder = rootTest.parentFolder.name
            docPath = f"{nextFolder} / {docPath}"
            rootTest = rootTest.parentFolder

        docPath = f"{docPath} / {data_file.name}"
        docID = data_file.id
        docName = data_file.name
        docVersion = data_file.versionNumber
        docVersions = data_file.latestVersionNumber
        # docVersionUser = data_file.lastUpdatedBy.displayName
        docVersionComment = data_file.description
        docVersionBuild = doc.version
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

        # MFGDM queries are cloud round trips; one repaint so the busy
        # indicator shows (rule 2 allows no more).
        progress = ui.progressBar
        progress.showBusy(f"{CMD_NAME} - checking MFGDM...")
        adsk.doEvents()
        try:
            if is_drawing:
                mfgdmHtml, mfgdmWarn = _drawing_mfgdm(doc, hub)
            else:
                mfgdmHtml, mfgdmWarn = mfgdm_status.render_design(
                    mfgdm_status.model_summary(
                        mfgdm_props.gql, mfgdm_props.design_model_id(design)
                    )
                )
        finally:
            progress.hide()
        resultString += mfgdmHtml

        VersionMigration = doc.version != app.version
        messageIcon = 3 if (VersionMigration or mfgdmWarn) else 2

        if VersionMigration:
            mTitle = f"{title_name} Document Info - Document will migrate on save"
            resultString += (
                f"<br>"
                f"<br>"
                f"<b>Document will migrate to new schema {appVersionBuild} if saved.</b><br>"
                f"Team members must be on the same client version to work with this document after save."
            )

        ui.messageBox(resultString, mTitle, 0, messageIcon)

    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
