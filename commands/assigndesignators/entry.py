# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Assign Designators command (attribute prove-out, part 5).
#
# Lists every connector occurrence in the assembly (components carrying a
# Define Wires manifest) and lets the user assign each a unique reference
# designator (J1, J2, ...) - the connector IDs used by harness wire lists
# (Export / Import Connectivity) and shown by the Wire Report.
#
# Designators are stored on the OCCURRENCE (group PowerTools.Cable, name
# "designator"): per instance - two instances of one connector part carry
# J1 and J2 - and assembly-local (a component attribute on an XRef part
# would live in the part document and be shared by every instance).
#
# The dialog is a table of editable rows (the globalParameters pattern:
# read-only header row, one StringValueInput per row, values collected on
# execute with table.getInputAtPosition). Unassigned connectors are seeded
# with J<n> suggestions; blanking a value clears the stored designator.

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..cable_shared import builder, connectivity, schema

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Assign Designators"
CMD_ID = "PTCB_assigndesignators"
CMD_Description = (
    "Assign a unique reference designator (J1, J2, ...) to every connector "
    "occurrence in the assembly - the connector IDs used by the "
    "connectivity wire list and the Wire Report."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Command-input ids.
INPUT_STATUS = "ad_status"
INPUT_TABLE = "ad_table"
ROW_NAME_PREFIX = "ad_name_"
ROW_DES_PREFIX = "ad_des_"

HEADER_ROW = 0

local_handlers: list = []

# Dialog state for the open command. All reset in command_destroy and,
# defensively, at the top of command_created.
_rows: list = []  # [{"occ", "label", "stored"}] in table order
_ui_refs: dict = {}


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------
def start():
    try:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )
        ptutil.add_handler(cmd_def.commandCreated, command_created)

        panel = _ui_bootstrap.get_power_tools_panel()
        if panel:
            control = panel.controls.addCommand(cmd_def)
            control.isPromoted = IS_PROMOTED
    except Exception:
        ptutil.log(f"{CMD_NAME} start() failed:\n{traceback.format_exc()}")


def stop():
    try:
        panel = _ui_bootstrap.get_power_tools_panel()
        if panel:
            existing = panel.controls.itemById(CMD_ID)
            if existing:
                existing.deleteMe()
        command_definition = ui.commandDefinitions.itemById(CMD_ID)
        if command_definition:
            command_definition.deleteMe()
    except Exception:
        ptutil.log(f"{CMD_NAME} stop() failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Command created - preconditions and dialog build
# ---------------------------------------------------------------------------
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")
    try:
        _reset_state()

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            args.command.doExecute(False)
            return
        connectors = builder.connector_occurrences(design)
        if not connectors:
            ui.messageBox(
                "No connectors were found in this design.\n\nRun Define "
                "Wires on the connector parts first - a connector is any "
                "occurrence whose component carries wire-point data.",
                CMD_NAME,
                0,
                2,
            )
            args.command.doExecute(False)
            return

        global _rows
        stored_values = []
        for occ in connectors:
            stored = builder.occurrence_designator(occ)
            _rows.append({"occ": occ, "label": occ.name, "stored": stored})
            if stored:
                stored_values.append(stored)
        suggestions = connectivity.suggest_designators(
            sum(1 for row in _rows if not row["stored"]), taken=stored_values
        )
        suggestion_iter = iter(suggestions)
        for row in _rows:
            row["value"] = row["stored"] or next(suggestion_iter)

        cmd = args.command
        inputs = cmd.commandInputs

        status = inputs.addTextBoxCommandInput(INPUT_STATUS, "", "", 2, True)
        status.isFullWidth = True
        _ui_refs["status"] = status

        table = adsk.core.TableCommandInput.cast(
            inputs.addTableCommandInput(INPUT_TABLE, "Connectors", 2, "3:1")
        )
        table.minimumVisibleRows = 3
        table.maximumVisibleRows = 12
        table.columnSpacing = 1
        table.hasGrid = True
        _ui_refs["table"] = table

        for col, header in enumerate(["Connector", "Designator"]):
            cell = inputs.addStringValueInput(f"ad_hdr_{col}", "", header)
            cell.isReadOnly = True
            table.addCommandInput(cell, HEADER_ROW, col)
        for index, row in enumerate(_rows):
            name_cell = inputs.addStringValueInput(
                f"{ROW_NAME_PREFIX}{index}", "", row["label"]
            )
            name_cell.isReadOnly = True
            des_cell = inputs.addStringValueInput(
                f"{ROW_DES_PREFIX}{index}", "", row["value"]
            )
            table.addCommandInput(name_cell, index + 1, 0)
            table.addCommandInput(des_cell, index + 1, 1)

        _update_status()

        ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
        ptutil.add_handler(
            cmd.inputChanged, command_input_changed, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.validateInputs, command_validate, local_handlers=local_handlers
        )
        ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    except Exception:
        ui.messageBox(f"{CMD_NAME}: Setup failed.\n{traceback.format_exc()}", CMD_NAME)


# ---------------------------------------------------------------------------
# Input events
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        if args.input.id.startswith(ROW_DES_PREFIX):
            _update_status()
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} inputChanged")


def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        args.areInputsValid = not connectivity.validate_designators(_entries())
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} validateInputs")
        args.areInputsValid = False  # fail closed - never enable OK unchecked


def _entries() -> list:
    """(connector label, designator) pairs read from the table."""
    table = _ui_refs.get("table")
    entries = []
    if table is None:
        return entries
    for index, row in enumerate(_rows):
        cell = adsk.core.StringValueCommandInput.cast(
            table.getInputAtPosition(index + 1, 1)
        )
        entries.append((row["label"], cell.value if cell else ""))
    return entries


def _update_status():
    status = _ui_refs.get("status")
    if status is None:
        return
    problems = connectivity.validate_designators(_entries())
    status.text = (
        "\n".join(problems)
        if problems
        else (
            "Designators identify connectors in the connectivity wire list. "
            "Blank a value to leave that connector unassigned."
        )
    )


# ---------------------------------------------------------------------------
# Execute - write/clear occurrence designator attributes
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    try:
        assigned = 0
        cleared = 0
        for (label, value), row in zip(_entries(), _rows, strict=True):
            value = value.strip()
            occ = row["occ"]
            if value:
                if value != row["stored"]:
                    occ.attributes.add(
                        schema.ATTR_GROUP,
                        schema.DESIGNATOR_NAME,
                        schema.build_designator_payload(value),
                    )
                assigned += 1
            elif row["stored"]:
                try:
                    attr = occ.attributes.itemByName(
                        schema.ATTR_GROUP, schema.DESIGNATOR_NAME
                    )
                    if attr:
                        attr.deleteMe()
                    cleared += 1
                except Exception:
                    ptutil.log(f"{CMD_NAME}: could not clear '{label}'.")
        lines = [f"Connectors: {len(_rows)}", f"Designators assigned: {assigned}"]
        if cleared:
            lines.append(f"Designators cleared: {cleared}")
        ui.messageBox("\n".join(lines), CMD_NAME)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _reset_state():
    """Reset all per-dialog module state."""
    global _rows, _ui_refs
    _rows = []
    _ui_refs = {}


# ---------------------------------------------------------------------------
# Destroy - release references and reset state
# ---------------------------------------------------------------------------
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    _reset_state()
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
