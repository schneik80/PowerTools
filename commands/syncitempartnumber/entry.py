# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Sync Item to Part Number.

Copies the active design's Fusion Manage **Item Number** into its **Part
Number** (``component.partNumber``). Lives on the built-in **Manage** tab (only
present when the Manage Extension is enabled) in a PowerTools panel.

The button is enabled whenever a Fusion design is the active product; all
item/part validation happens in ``command_execute`` (no Item Number found, the
values already match, local child components present, shared part number, etc.).

The Item Number and the shared-part-number status are cloud values reached
through the Manufacturing Data Model GraphQL API (``mfgdm://v3``); see
``commands/partnumber_shared/mfgdm_props.py``. The Part Number write persists to
the backend immediately — no document save is required.
"""

from __future__ import annotations

import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from ..partnumber_shared import intent, mfgdm_props
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Sync Item to Part Number"
CMD_ID = "PTND_syncitempartnumber"
CMD_Description = (
    "Copy the active design's Fusion Manage Item Number into its Part Number."
)
IS_PROMOTED = True

# The Manage tab is built into the Design workspace by the Fusion Manage
# Extension. We only add/remove our own panel on it; we never create or delete
# the tab itself.
WORKSPACE_ID = config.design_workspace
TAB_ID = config.manage_tab_id
PANEL_ID = config.manage_panel_id
PANEL_NAME = config.manage_panel_name
PANEL_AFTER = config.manage_panel_after

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Per-invocation handlers (execute/destroy) — cleared in command_destroy.
local_handlers: list = []
# Session-long application handlers (documentActivated/Opened) — kept in a
# SEPARATE list so command_destroy can't garbage-collect them.
_app_handlers: list = []


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if workspace is None:
        ptutil.log(f"[{CMD_NAME}] workspace {WORKSPACE_ID} not found at start()")
        return

    manage_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if manage_tab is None:
        # Manage Extension not enabled — no Manage tab. Skip placement entirely;
        # never create the tab.
        ptutil.log(
            f"[{CMD_NAME}] Manage tab '{TAB_ID}' absent (Manage Extension off) — "
            f"skipping UI registration."
        )
        return

    panel = manage_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        # PANEL_AFTER == "" -> the panel is appended at the END of the tab.
        panel = manage_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED

    # Keep the button enabled whenever a design is active; execute does all
    # item/part validation. documentActivated covers tab switches and open;
    # documentOpened is registered defensively.
    ptutil.add_handler(
        app.documentActivated, _on_document_event, local_handlers=_app_handlers
    )
    ptutil.add_handler(
        app.documentOpened, _on_document_event, local_handlers=_app_handlers
    )
    _refresh_enabled()
    ptutil.log(f"{CMD_NAME} command started")


def stop():
    global _app_handlers
    _app_handlers = []
    try:
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        manage_tab = workspace.toolbarTabs.itemById(TAB_ID) if workspace else None
        panel = manage_tab.toolbarPanels.itemById(PANEL_ID) if manage_tab else None
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()
        if command_definition:
            command_definition.deleteMe()
        # Delete our panel only when empty; never touch the built-in Manage tab.
        if panel and panel.controls.count == 0:
            panel.deleteMe()
        ptutil.log(f"{CMD_NAME} command stopped")
    except Exception as exc:
        ptutil.log(f"Error stopping {CMD_NAME}: {exc}")


# ---------------------------------------------------------------------------
# Enablement — enabled whenever a design is the active product
# ---------------------------------------------------------------------------


def _on_document_event(args: adsk.core.DocumentEventArgs):
    _refresh_enabled()


def _refresh_enabled():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        return
    try:
        is_design = adsk.fusion.Design.cast(app.activeProduct) is not None
    except Exception:
        is_design = False
    cmd_def.controlDefinition.isEnabled = is_design


# ---------------------------------------------------------------------------
# Command created / execute / destroy
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandEventArgs):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            return

        # Precheck: reject designs that contain local child components. Only a
        # single model (external/referenced children are fine) can be synced.
        if intent.has_local_components(design):
            ui.messageBox(
                f"{CMD_NAME} operates on a single model.\n\n"
                "This design contains local child components. Only designs with "
                "no local children can be synced (external/referenced children "
                "are fine).",
                CMD_NAME,
                0,
                2,
            )
            return

        data = design.rootDataComponent
        model_id = data.mfgdmModelId if data else ""
        if not model_id:
            ui.messageBox(
                "Cloud data for this design isn't ready yet. Wait a moment and "
                "try again.",
                CMD_NAME,
                0,
                2,
            )
            return
        timestamp = (data.timestamp or "") if data else ""

        progress = ui.progressBar
        progress.showBusy(f"{CMD_NAME} — reading Item Number...")
        adsk.doEvents()
        try:
            item_number, part_number, hub_id = mfgdm_props.fetch_item_part_hub(
                model_id, timestamp
            )
        finally:
            progress.hide()

        item_number = (item_number or "").strip()
        old_part = (part_number or "").strip()
        component_name = design.rootComponent.name

        if not item_number:
            ui.messageBox(
                "This design has no Fusion Manage Item Number to copy.",
                CMD_NAME,
                0,
                2,
            )
            return

        if not logic.needs_sync(item_number, old_part):
            ui.messageBox(
                "Item Number and Part Number already match. Nothing to copy.",
                CMD_NAME,
                0,
                2,
            )
            return

        # Shared part number guard: warn before changing a Part Number that is
        # shared across multiple models.
        progress.showBusy(f"{CMD_NAME} — checking shared part number...")
        adsk.doEvents()
        try:
            shared = _is_shared_guarded(hub_id, old_part)
        finally:
            progress.hide()

        if shared:
            result = ui.messageBox(
                f"The Part Number '{old_part}' is part of a shared part number "
                f"group (shared across multiple models).\n\n"
                f"Copying the Item Number '{item_number}' changes this model's "
                f"Part Number and removes it from that shared group.\n\n"
                f"Continue?",
                CMD_NAME,
                adsk.core.MessageBoxButtonTypes.OKCancelButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType,
            )
            if result != adsk.core.DialogResults.DialogOK:
                return

        # Copy. The Part Number write persists to the backend immediately; no
        # document save is required.
        root = design.rootComponent
        root.partNumber = item_number

        ui.messageBox(
            f"<b>Component:</b> {_escape_html(component_name)}<br>"
            f"<b>Old Part Number:</b> {_escape_html(old_part) or '(none)'}<br>"
            f"<b>New Part Number:</b> {_escape_html(item_number)}  "
            f"(copied from Item Number)",
            f"{CMD_NAME} — Complete",
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.InformationIconType,
        )
    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_shared_guarded(hub_id: str, part_number: str) -> bool:
    """Fail-safe shared-part-number check.

    Returns False for an empty / auto-generated placeholder part number. On any
    network/GraphQL error, defaults to True (treated as shared) so a possibly
    shared part number is never overwritten without the user confirming.
    """
    if not part_number or intent.is_fusion_auto_pn(part_number):
        return False
    try:
        return bool(mfgdm_props.is_part_number_shared(hub_id, part_number))
    except Exception:
        ptutil.log(
            f"{CMD_NAME}: shared part-number check failed; defaulting to shared "
            f"(will prompt to confirm)."
        )
        return True


def _escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
