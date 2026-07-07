# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# Show In Location.
#
# When enabled (Preferences -> Commands), runs Dashboard.ShowInLocation for the
# active document so its data-panel location is revealed. Two preferences in its
# Preferences settings section control when it fires: on document open
# (`run_on_open`) and on document activate (`run_on_activate`).

import adsk.core
import os
from ...lib import ptAddInUtils as ptutil
from ... import settings_store

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Show In Location"
CMD_Description = (
    "Automatically reveal a document's location in the data panel when it is "
    "opened or activated."
)

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


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


def stop():
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME}: documentOpened and documentActivated handlers removed.")


# ---------------------------------------------------------------------------
# Document event handling
# ---------------------------------------------------------------------------


def _show_in_location(event_name: str, doc: adsk.core.Document):
    """Get the URN from the event document and run Dashboard.ShowInLocation via executeTextCommand."""
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
    if settings_store.command_setting("docopen", "run_on_open", True):
        _show_in_location("documentOpened", args.document)


# Event handler — fires when the user switches to a different document tab.
def application_documentActivated(args: adsk.core.DocumentEventArgs):
    if settings_store.command_setting("docopen", "run_on_activate", True):
        _show_in_location("documentActivated", args.document)
