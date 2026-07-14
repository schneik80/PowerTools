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

CMD_NAME = "Hide Objects"
CMD_ID = "PTPM-hideobjects"
CMD_DESCRIPTION = (
    "Hide selected types of objects across all components in the active design."
)
IS_PROMOTED = False

WORKSPACE_ID = config.design_workspace
TAB_ID = "ToolsTab"
TAB_NAME = "Tools"
PANEL_ID = "UtilityPanel"
PANEL_NAME = "Utility"
PANEL_AFTER = ""

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []


def start() -> None:
    try:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER
        )
        ptutil.add_handler(cmd_def.commandCreated, command_created)

        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            ptutil.log(f"Warning: Workspace {WORKSPACE_ID} not found")
            return

        toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
        if toolbar_tab is None:
            toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

        panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
        if panel is None:
            panel = toolbar_tab.toolbarPanels.add(
                PANEL_ID, PANEL_NAME, PANEL_AFTER, False
            )

        control = panel.controls.addCommand(cmd_def, "", True)
        control.isPromoted = IS_PROMOTED

        ptutil.log(f"{CMD_NAME} command started successfully")

    except Exception as e:
        ptutil.log(f"Error starting {CMD_NAME}: {e}")


def stop() -> None:
    try:
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            return

        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()

        if command_definition:
            command_definition.deleteMe()

        if panel and panel.controls.count == 0:
            panel.deleteMe()

        if toolbar_tab and toolbar_tab.toolbarPanels.count == 0:
            toolbar_tab.deleteMe()

        ptutil.log(f"{CMD_NAME} command stopped successfully")

    except Exception as e:
        ptutil.log(f"Error stopping {CMD_NAME}: {e}")


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    ptutil.log(f"{CMD_NAME} Command Created Event")

    try:
        cmd = args.command
        inputs = cmd.commandInputs

        inputs.addBoolValueInput("hide_origin", "Origin", True, "", True)
        inputs.addBoolValueInput(
            "hide_construction_points", "Construction Points", True, "", True
        )
        inputs.addBoolValueInput(
            "hide_construction_axes", "Construction Axes", True, "", True
        )
        inputs.addBoolValueInput(
            "hide_construction_planes", "Construction Planes", True, "", True
        )
        inputs.addBoolValueInput("hide_joint_origins", "Joint Origins", True, "", True)
        inputs.addBoolValueInput("hide_joints", "Joints", True, "", True)
        inputs.addBoolValueInput("hide_sketches", "Sketches", True, "", True)
        inputs.addBoolValueInput("hide_canvas", "Canvas", True, "", True)

        ptutil.add_handler(
            args.command.execute, command_execute, local_handlers=local_handlers
        )
        ptutil.add_handler(
            args.command.destroy, command_destroy, local_handlers=local_handlers
        )

    except Exception as e:
        ptutil.log(f"Error in command_created: {e}")


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    try:
        app = adsk.core.Application.get()
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)

        if not design:
            ui.messageBox("No active Fusion design.", CMD_NAME)
            return

        inputs = args.command.commandInputs
        hide_origin = inputs.itemById("hide_origin").value
        hide_construction_points = inputs.itemById("hide_construction_points").value
        hide_construction_axes = inputs.itemById("hide_construction_axes").value
        hide_construction_planes = inputs.itemById("hide_construction_planes").value
        hide_joint_origins = inputs.itemById("hide_joint_origins").value
        hide_joints = inputs.itemById("hide_joints").value
        hide_sketches = inputs.itemById("hide_sketches").value
        hide_canvas = inputs.itemById("hide_canvas").value

        all_components = design.allComponents

        for component in all_components:
            if hide_origin:
                component.isOriginFolderLightBulbOn = False

            if hide_construction_points:
                for cp in component.constructionPoints:
                    cp.isLightBulbOn = False

            if hide_construction_axes:
                for ca in component.constructionAxes:
                    ca.isLightBulbOn = False

            if hide_construction_planes:
                for cl in component.constructionPlanes:
                    cl.isLightBulbOn = False

            if hide_joint_origins:
                for jo in component.jointOrigins:
                    jo.isLightBulbOn = False

            if hide_joints:
                component.isJointsFolderLightBulbOn = False

            if hide_sketches:
                component.isSketchFolderLightBulbOn = True
                for sketch in component.sketches:
                    sketch.isLightBulbOn = False

            if hide_canvas:
                component.isCanvasFolderLightBulbOn = False

        ptutil.log(f"{CMD_NAME} executed successfully.")

    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
