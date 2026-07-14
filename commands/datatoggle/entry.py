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

CMD_NAME = "Toggle Data"
CMD_ID = "PTND-toggledata"
CMD_Description = "Hide or show the data pane"
IS_PROMOTED = False

# Global variables by referencing values from /config.py
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after


# Declare constants
_navBarBtnID = "NavBarBtn"
_navBarBtnName = "NavBarBtn"
_toolbar = "NavToolbar"

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Holds references to event handlers
local_handlers = []


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.itemById(_navBarBtnID)
    if not cmd_def:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            _navBarBtnID, CMD_NAME, CMD_Description, ICON_FOLDER
        )

    # Add command created handler. The function passed here will be executed when the command is executed.
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control ********************************

    navToolbar = ui.toolbars.itemById(_toolbar)
    navToolbarControls = navToolbar.controls
    control = navToolbarControls.addCommand(cmd_def, "", False)

    # ****************
    # Get target workspace for the command.


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    global app, ui, _handlers, _navBarBtnID, _navBarBtnName, _toolbar
    _app = adsk.core.Application.get()
    _ui = _app.userInterface

    # Clean up the UI.
    navToolbar = _ui.toolbars.itemById(_toolbar)
    navToolbarControls = navToolbar.controls

    cntrl = navToolbarControls.itemById(_navBarBtnID)
    if cntrl:
        cntrl.deleteMe()

    navBarBtnCmdDef = _ui.commandDefinitions.itemById(_navBarBtnID)
    if not navBarBtnCmdDef:
        navBarBtnCmdDef.deleteMe()


# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Started Event")
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        cmdDefs = ui.commandDefinitions

        if app.data.isDataPanelVisible == True:
            datatoggleclose = cmdDefs.itemById("DashboardModeCloseCommand")
            datatoggleclose.execute()
        else:
            datatoggleopen = cmdDefs.itemById("DashboardModeOpenCommand")
            datatoggleopen.execute()

    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)

    ptutil.log(f"{CMD_NAME} Command Completed Event")
