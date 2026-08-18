# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# Scripts and Add-ins launcher.
#
# Adds a single "Scripts and Add-ins" entry to the QAT File dropdown, positioned
# directly before the "PowerTools Preferences" item, that opens Fusion's built-in
# Scripts and Add-Ins manager (command ID "ScriptsManagerCommand"). The item is a
# pure launcher — it presents no dialog of its own and fires the target command
# from its commandCreated handler, mirroring the datatoggle pattern.

import adsk.core

from ...lib import ptAddInUtils as ptutil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = "PT_scriptsmanager"
CMD_NAME = "Scripts and Add-ins"
CMD_Description = (
    "Open Fusion's built-in Scripts and Add-Ins manager: the same dialog as "
    "Shift+S or Utilities > Add-Ins, from the File menu, directly above "
    "PowerTools Preferences. Purely a shortcut: it puts a frequently used "
    "tool one click from where you already are."
)

# The built-in Fusion command this menu item launches.
TARGET_CMD_ID = "ScriptsManagerCommand"

# QAT File-dropdown control this item is inserted directly before. The
# Preferences command is infrastructure and always starts first (see
# commands/__init__.py), so this anchor exists by the time start() runs.
PREFERENCES_CMD_ID = "PT_preferences"

# No icon assets — an empty resource folder renders the default menu glyph.
ICON_FOLDER = ""

local_handlers = []


def _qat_file_dropdown():
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return None
    return adsk.core.DropDownControl.cast(qat.controls.itemById("FileSubMenuCommand"))


def start():
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    file_dd = _qat_file_dropdown()
    if file_dd and not file_dd.controls.itemById(CMD_ID):
        # Insert directly before the PowerTools Preferences item when present;
        # otherwise fall back to appending to the dropdown.
        if file_dd.controls.itemById(PREFERENCES_CMD_ID):
            file_dd.controls.addCommand(cmd_def, PREFERENCES_CMD_ID, True)
        else:
            file_dd.controls.addCommand(cmd_def)


def stop():
    file_dd = _qat_file_dropdown()
    if file_dd:
        ctrl = file_dd.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    # This item is a launcher with no dialog of its own. Fire the built-in
    # Scripts and Add-Ins manager and let this command terminate immediately.
    try:
        target = ui.commandDefinitions.itemById(TARGET_CMD_ID)
        if target:
            target.execute()
        else:
            ui.messageBox(
                "The Scripts and Add-Ins manager is not available in this "
                "version of Fusion.",
                CMD_NAME,
            )
    except Exception:
        ptutil.handle_error(CMD_NAME)
