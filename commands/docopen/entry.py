# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import os
from ...lib import ptAddInUtils as ptutil
from ... import config
from .. import _ui_bootstrap

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Show In Location"

TOGGLE_CMD_ID = "PT-showinlocation-toggle"
TOGGLE_CMD_TOOLTIP = (
    "Toggle the automatic 'Show In Location' behavior that runs when a "
    "document is opened or activated."
)

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

SETTING_KEY = "show_in_location_enabled"
SETTING_DEFAULT = True

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# ---------------------------------------------------------------------------
# Setting helpers
# ---------------------------------------------------------------------------


def _is_enabled() -> bool:
    return bool(config.load_settings().get(SETTING_KEY, SETTING_DEFAULT))


def _set_enabled(enabled: bool) -> None:
    settings = config.load_settings()
    settings[SETTING_KEY] = bool(enabled)
    config.save_settings(settings)


def _toggle_label() -> str:
    return f"Disable {CMD_NAME}" if _is_enabled() else f"Enable {CMD_NAME}"


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------


def start():
    ptutil.add_handler(
        app.documentOpened,
        application_documentOpened,
        local_handlers=local_handlers,
    )
    ptutil.add_handler(
        app.documentActivated,
        application_documentActivated,
        local_handlers=local_handlers,
    )
    ptutil.log(f"{CMD_NAME}: documentOpened and documentActivated handlers registered.")

    _install_menu()


def stop():
    global local_handlers
    local_handlers = []

    _uninstall_menu()

    ptutil.log(f"{CMD_NAME}: documentOpened and documentActivated handlers removed.")


# ---------------------------------------------------------------------------
# Menu install / uninstall
# ---------------------------------------------------------------------------


def _install_menu():
    settings_dropdown = _ui_bootstrap.get_pt_settings_flyout()
    if not settings_dropdown:
        ptutil.log(f"{CMD_NAME}: could not locate QAT file menu; settings menu skipped.")
        return

    toggle_cmd_def = ui.commandDefinitions.itemById(TOGGLE_CMD_ID)
    if not toggle_cmd_def:
        toggle_cmd_def = ui.commandDefinitions.addButtonDefinition(
            TOGGLE_CMD_ID, _toggle_label(), TOGGLE_CMD_TOOLTIP, ICON_FOLDER
        )
    else:
        # Sync label with persisted state in case the setting changed while unloaded.
        toggle_cmd_def.name = _toggle_label()

    ptutil.add_handler(
        toggle_cmd_def.commandCreated,
        _toggle_cmd_created,
        local_handlers=local_handlers,
    )

    if not settings_dropdown.controls.itemById(TOGGLE_CMD_ID):
        settings_dropdown.controls.addCommand(toggle_cmd_def)


def _uninstall_menu():
    settings_dropdown = _ui_bootstrap.get_pt_settings_flyout()
    if settings_dropdown:
        control = settings_dropdown.controls.itemById(TOGGLE_CMD_ID)
        if control:
            control.deleteMe()

    toggle_cmd_def = ui.commandDefinitions.itemById(TOGGLE_CMD_ID)
    if toggle_cmd_def:
        toggle_cmd_def.deleteMe()


# ---------------------------------------------------------------------------
# Toggle command handlers
# ---------------------------------------------------------------------------


def _toggle_cmd_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.add_handler(
        args.command.execute,
        _toggle_cmd_execute,
        local_handlers=local_handlers,
    )


def _toggle_cmd_execute(args: adsk.core.CommandEventArgs):
    new_state = not _is_enabled()
    _set_enabled(new_state)

    toggle_cmd_def = ui.commandDefinitions.itemById(TOGGLE_CMD_ID)
    if toggle_cmd_def:
        toggle_cmd_def.name = _toggle_label()

    ptutil.log(f"{CMD_NAME}: behavior {'enabled' if new_state else 'disabled'} by user.")


# ---------------------------------------------------------------------------
# Document event handling
# ---------------------------------------------------------------------------


def _show_in_location(event_name: str, doc: adsk.core.Document):
    """Get the URN from the event document and run Dashboard.ShowInLocation via executeTextCommand."""
    if not _is_enabled():
        return

    urn = None
    try:
        if not doc:
            ptutil.log(f"{CMD_NAME} [{event_name}]: no active document, skipping.")
            return

        data_file = doc.dataFile
        if not data_file:
            ptutil.log(
                f"{CMD_NAME} [{event_name}]: document has no dataFile (unsaved?), skipping."
            )
            return

        urn = data_file.id
        app.executeTextCommand(f"Dashboard.ShowInLocation {urn}")
        ptutil.log(
            f"{CMD_NAME} [{event_name}]: executed 'Dashboard.ShowInLocation {urn}'."
        )
    except Exception:
        ptutil.log(
            f"{CMD_NAME} [{event_name}]: error executing 'Dashboard.ShowInLocation'.",
            force_console=True,
        )
    finally:
        urn = None


# Event handler — fires at the end of every document open.
def application_documentOpened(args: adsk.core.DocumentEventArgs):
    _show_in_location("documentOpened", args.document)


# Event handler — fires when the user switches to a different document tab.
def application_documentActivated(args: adsk.core.DocumentEventArgs):
    _show_in_location("documentActivated", args.document)
