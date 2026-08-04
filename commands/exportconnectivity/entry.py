# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Export Connectivity command (attribute prove-out, part 6).
#
# Writes the assembly's connectivity as an industry-practice CSV wire list
# (From, From Pin, To, To Pin, Color, Gauge, ... - the tabular format used
# on harness drawings): a commented connector/pin reference block, then one
# row per routed wire (cable wires grouped by their Cable value). The file
# is meant to be EDITED - add rows to define new connectivity, then run
# Import Connectivity to build it.
#
# Connectors are identified by their reference designators (Assign
# Designators); the export refuses while any connector is unassigned.
# Existing route ends resolve through the Update Wire ladder
# (findEntityByToken, never token-string comparison; unique connector-id
# fallback). Lengths are measured from the routing sketches (the Wire
# Report helpers, shared via cable_shared.builder) and are export-only
# documentation. The CSV format itself lives in
# commands/cable_shared/connectivity.py.

import os
import re
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..cable_shared import builder, connectivity, schema
from ..cable_shared import routing as route_logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Export Connectivity"
CMD_ID = "PTCB_exportconnectivity"
CMD_Description = (
    "Write the assembly's connectors and routed wires/cables as an editable "
    "CSV wire list (From, From Pin, To, To Pin, Color, Gauge). Edit the "
    "file to define new connectivity, then run Import Connectivity."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers: list = []


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


def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []


# ---------------------------------------------------------------------------
# Execute - gather, serialize, save
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            return
        connectors = builder.connector_occurrences(design)
        if not connectors:
            ui.messageBox(
                "No connectors were found in this design.\n\nRun Define "
                "Wires on the connector parts first.",
                CMD_NAME,
                0,
                2,
            )
            return

        unassigned = [
            occ.name for occ in connectors if not builder.occurrence_designator(occ)
        ]
        if unassigned:
            shown = "\n".join(unassigned[:10])
            if len(unassigned) > 10:
                shown += f"\n... and {len(unassigned) - 10} more"
            ui.messageBox(
                "Every connector needs a reference designator before the "
                "wire list can be written. Run Assign Designators.\n\n"
                f"Unassigned:\n{shown}",
                CMD_NAME,
                0,
                2,
            )
            return

        reference = connectivity.connector_reference_lines(
            sorted(
                (_connector_info(occ) for occ in connectors),
                key=lambda info: connectivity.designator_sort_key(info["designator"]),
            )
        )
        rows, notes = _route_rows(design, connectors)

        text = connectivity.serialize_rows(rows, reference)
        path = _ask_save_path()
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

        singles = sum(1 for row in rows if not row["cable"])
        cables = len({row["cable"] for row in rows if row["cable"]})
        lines = [
            f"Wire list saved:\n{path}",
            "",
            f"Connectors: {len(connectors)}",
            f"Wires: {singles} single, {cables} cable(s)",
        ]
        lines.extend(notes)
        ui.messageBox("\n".join(lines), CMD_NAME)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _connector_info(occ) -> dict:
    """Reference-block data for one connector occurrence."""
    data = builder.read_connector(occ)
    pins = [
        {
            "pin": pin,
            "awg_min": data["wires"][pin]["awg_min"],
            "awg_max": data["wires"][pin]["awg_max"],
        }
        for pin in route_logic.sort_pins(data["wires"].keys())
    ]
    return {
        "designator": builder.occurrence_designator(occ),
        "name": data["comp_name"] or occ.name,
        "pins": pins,
        "has_cable_point": data["cable"] is not None,
    }


def _route_rows(design, connectors) -> tuple:
    """Wire-list rows for every routed assembly, plus skip notes."""
    rows: list = []
    notes: list = []
    for route in builder.collect_routes(design):
        payload = route["payload"]
        name = str(payload.get("name") or "unnamed")
        ends = payload.get("ends") or []
        if len(ends) != 2:
            notes.append(f"Skipped '{name}': stored route data is damaged.")
            continue
        end_refs = []
        for end in ends:
            refs = []
            for entry in route_logic.end_connectors(end):
                occ = builder.resolve_end_occurrence(design, entry, connectors)
                refs.append(builder.occurrence_designator(occ) if occ else "")
            end_refs.append(refs)
        if not all(all(refs) for refs in end_refs):
            notes.append(
                f"Skipped '{name}': a connector could not be resolved to a "
                "designator (swapped or removed - run Update Wire)."
            )
            continue
        kind = payload.get("kind", route_logic.KIND_SINGLE)
        if kind == route_logic.KIND_CABLE:
            rows.extend(_cable_rows(route, end_refs))
        else:
            rows.append(_single_row(route, end_refs))
    return rows, notes


def _single_row(route, end_refs: list) -> dict:
    """One wire-list row for a single-wire route."""
    payload = route["payload"]
    ends = payload["ends"]
    comp = route["occ"].component
    length_cm = builder.member_child_length_cm(
        comp, schema.MEMBER_CONDUCTOR, "Conductor"
    ) + builder.member_child_length_cm(comp, schema.MEMBER_SHEATH, "Sheath")
    return {
        "cable": "",
        "wire": str(payload.get("name") or ""),
        "from_ref": end_refs[0][0],
        "from_pin": str(ends[0].get("pin") or ""),
        "to_ref": end_refs[1][0],
        "to_pin": str(ends[1].get("pin") or ""),
        "color": str(payload.get("color") or ""),
        "awg": payload.get("awg"),
        "wire_od_mm": payload.get("od_mm"),
        "cable_od_mm": None,
        "length_mm": length_cm * 10.0,
    }


def _cable_rows(route, end_refs: list) -> list:
    """One wire-list row per wire of a cable route (each row's own refs)."""
    payload = route["payload"]
    ends = payload["ends"]
    comp = route["occ"].component
    pins_a = [str(pin) for pin in ends[0].get("pins") or []]
    pins_b = [str(pin) for pin in ends[1].get("pins") or []]
    wc_a = route_logic.end_wire_connectors(ends[0], len(pins_a))
    wc_b = route_logic.end_wire_connectors(ends[1], len(pins_b))
    labels = [str(label) for label in payload.get("wire_labels") or []]
    colors = [str(color) for color in payload.get("colors") or []]
    jacket_cm = builder.own_curve_length_cm(comp)
    extra_by_label = {
        wire["label"]: wire["extra_cm"]
        for wire in builder.measure_cable_wires(comp, payload)
    }
    rows = []
    for index, (pin_a, pin_b) in enumerate(zip(pins_a, pins_b, strict=False)):
        label = labels[index] if index < len(labels) else pin_a
        length_cm = jacket_cm + extra_by_label.get(label, 0.0)
        rows.append(
            {
                "cable": str(payload.get("name") or ""),
                "wire": label,
                "from_ref": end_refs[0][wc_a[index]],
                "from_pin": pin_a,
                "to_ref": end_refs[1][wc_b[index]],
                "to_pin": pin_b,
                "color": colors[index] if index < len(colors) else "",
                "awg": payload.get("awg"),
                "wire_od_mm": payload.get("od_mm") if index == 0 else None,
                "cable_od_mm": payload.get("cable_od_mm") if index == 0 else None,
                "length_mm": length_cm * 10.0,
            }
        )
    return rows


def _ask_save_path() -> str:
    """The chosen .csv save path ("" when the user cancels)."""
    dialog = ui.createFileDialog()
    dialog.title = "Save connectivity wire list"
    dialog.filter = "CSV files (*.csv);;All Files (*.*)"
    dialog.isMultiSelectEnabled = False
    doc_name = app.activeDocument.name if app.activeDocument else "connectivity"
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", doc_name)
    dialog.initialFilename = f"{safe_name} connectivity.csv"
    if dialog.showSave() != adsk.core.DialogResults.DialogOK:
        return ""
    return dialog.filename
