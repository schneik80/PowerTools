# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Set Up Shared Add-ins Folder.
#
# There is nothing to browse for and nothing to save: the location is a
# convention, <active hub>/Assets/Shared Addins, the same shape
# commands/partnumber_shared uses for Assets/Pn-Cache. This command finds that
# folder or creates it, then reports what it found — which is all the setup
# Team Add-ins needs.
#
# Launched from the Team Add-ins section of the Preferences palette; it has no
# toolbar control of its own.

import os
import os.path

import adsk.core

from ... import config
from ...lib import ptAddInUtils as ptutil
from ..teamaddins import team_fs

app = adsk.core.Application.get()
ui = app.userInterface

# Command identity information.
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_configTeamAddins"
CMD_NAME = "Set Up Shared Add-ins Folder"
CMD_Description = (
    "Find or create the shared folder your team keeps add-ins in: "
    f"{team_fs.ASSETS_PROJECT_NAME} / {team_fs.SHARED_ADDINS_FOLDER_NAME} in the "
    "active hub.\n"
    "Drop an add-in .zip into that folder and everyone running PowerTools picks "
    "it up shortly after Fusion starts.\n"
    "There is nothing to configure — the location is the same in every hub."
)

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")


# Executed when add-in is run.
def start():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )

    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # No toolbar control: launched from the Preferences palette (and from the
    # Team Add-ins report) via ui.commandDefinitions.itemById(CMD_ID).execute().


# Executed when add-in is stopped.
def stop():
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Runs the entire flow inline — no command inputs are added, so Fusion
# auto-executes without showing a command dialog.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    folder_name = team_fs.SHARED_ADDINS_FOLDER_NAME

    try:
        project = team_fs.find_assets_project(app)
    except team_fs.NotConfigured as exc:
        ui.messageBox(
            f"{exc}\n\nSign in to the hub that holds your team's "
            f"'{team_fs.ASSETS_PROJECT_NAME}' project and try again.",
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
        return
    except team_fs.TeamFsError as exc:
        ui.messageBox(
            str(exc),
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
        return

    # Report an existing folder rather than touching it — the common case is a
    # team where somebody has already set this up.
    try:
        existing = team_fs.find_shared_addins_folder(project, create=False)
    except team_fs.TeamFsError as exc:
        ui.messageBox(
            str(exc),
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
        return

    if existing is not None:
        count = 0
        try:
            listing = team_fs.list_folder(existing)
            count = sum(
                1
                for name, _ in listing
                if name.lower().endswith(team_fs.PACKAGE_SUFFIXES)
            )
        except team_fs.TeamFsError:
            count = 0

        ptutil.log(f"{CMD_NAME}: found {project.name}/{folder_name} ({count} packages)")
        ui.messageBox(
            f"'{folder_name}' is ready.\n\n"
            f"Hub: {getattr(team_fs.active_hub(app), 'name', '')}\n"
            f"Project: {project.name}\n"
            f"Folder: {folder_name}\n"
            f"Add-in packages in it: {count}\n\n"
            f"Drop an add-in .zip into that folder to share it with the team. "
            f"Use Tools → Power Tools → Team Add-ins to check it now.",
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType,
        )
        return

    confirm = ui.messageBox(
        f"Create a '{folder_name}' folder in the '{project.name}' project?\n\n"
        f"Everyone on this hub running PowerTools will read add-ins from it.",
        CMD_NAME,
        adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
        adsk.core.MessageBoxIconTypes.QuestionIconType,
    )
    if confirm != adsk.core.DialogResults.DialogOK:
        return

    try:
        team_fs.find_shared_addins_folder(project, create=True)
    except team_fs.TeamFsError as exc:
        ui.messageBox(
            str(exc),
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.CriticalIconType,
        )
        return

    ui.messageBox(
        f"'{folder_name}' created in '{project.name}'.\n\n"
        f"Drop an add-in .zip into that folder to share it with the team. "
        f"Everyone running PowerTools picks it up shortly after Fusion starts.",
        CMD_NAME,
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType,
    )
