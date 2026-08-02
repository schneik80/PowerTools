# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Wire Report command (attribute prove-out, part 4).
#
# Presents every routed wire and cable in the design in a theme-aware HTML
# palette, organized per assembly:
#
# - Single wires: both connectors and pins, gauge, diameter, and the TOTAL
#   WIRE LENGTH (bare conductor stubs + the sheathed run) - the cut length.
# - Cables: both connectors and pin sets, gauge, wire and jacket diameters,
#   every wire's full path length, the jacket run - and the CABLE LENGTH,
#   which is set by the LONGEST wire path (all wires in a manufactured
#   cable are cut to the same length, so the longest run governs).
#
# Lengths are measured from the routing sketches the builder created (sum
# of non-construction curve lengths per component - the jacket's direction
# lines are construction and excluded) and formatted in the document's
# units. Routes are found via their PowerTools.Cable "route" attributes
# (builder.collect_routes).
#
# The palette mechanics (delete-then-add lifecycle, init.js first-paint
# sidecar, theme resolution) come from ptutil.palette_utils - shared with
# the other palette commands. The page pushes an htmlReady handshake and
# applies the resolved theme as a body class.

import datetime
import json
import os
import traceback

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..cable_shared import builder, schema
from ..cable_shared import routing as route_logic
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Wire Report"
CMD_ID = "PTCB_wirereport"
CMD_Description = (
    "Report every routed wire and cable in the design: connectors, pins, "
    "gauges, diameters, and computed lengths (a cable's length is set by "
    "its longest wire path)."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

PALETTE_NAME = "Wire & Cable Report"
PALETTE_ID = config.wire_report_palette_id
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight
_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "index.html").replace("\\", "/")
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

local_handlers: list = []
_palette_handlers: list = []  # live as long as the palette exists
_last_state: dict | None = None  # last gathered report (htmlReady re-sends it)


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
        palette = ui.palettes.itemById(PALETTE_ID)
        if palette:
            palette.deleteMe()
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


def command_execute(args: adsk.core.CommandEventArgs):
    global _last_state
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            return
        state = _gather_state(design)
        _last_state = state
        if not state["assemblies"] and not state["skipped"]:
            ui.messageBox(
                "No routed wires or cables were found in this design.\n\n"
                "Route Wire stamps each assembly it builds; run it first.",
                CMD_NAME,
                0,
                2,
            )
            return
        _show_palette(state)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []


# ---------------------------------------------------------------------------
# Data gathering and measurement
# ---------------------------------------------------------------------------
def _gather_state(design) -> dict:
    """Collect, measure, summarize, and format the whole report state."""
    measured = []
    for route in builder.collect_routes(design):
        measured.append(_measure_route(design, route))
    report = logic.summarize_routes(measured)
    return _display_state(design, report)


def _measure_route(design, route) -> dict:
    """Raw route dict for logic.summarize_routes: payload + measured cm."""
    payload = route["payload"]
    comp = route["occ"].component
    kind = payload.get("kind") or route_logic.KIND_SINGLE
    entry = {
        "kind": kind,
        "name": payload.get("name"),
        "awg": payload.get("awg"),
        "od_mm": payload.get("od_mm"),
        "cable_od_mm": payload.get("cable_od_mm"),
        "ends": [_end_info(design, end, kind) for end in payload.get("ends") or []],
    }
    if kind == route_logic.KIND_SINGLE:
        entry["conductor_cm"] = _child_curve_length_cm(
            comp, schema.MEMBER_CONDUCTOR, "Conductor"
        )
        entry["sheath_cm"] = _child_curve_length_cm(
            comp, schema.MEMBER_SHEATH, "Sheath"
        )
    elif kind == route_logic.KIND_CABLE:
        entry["jacket_cm"] = _own_curve_length_cm(comp)
        entry["wires"] = _measure_cable_wires(comp, payload)
    return entry


def _measure_cable_wires(comp, payload) -> list:
    """Per-wire out-of-jacket lengths, labeled with the most reliable pin.

    Children are found by their stamped member attribute (role "wire",
    which also carries the pin - immune to renames and Fusion's uniqueness
    suffixes). For assemblies built before members were stamped, the
    fallbacks are the old ladder: name-prefix discovery, pins by creation
    order against the payload (build order = paired pin order), then
    component-name parsing when the counts disagree.
    """
    children = []  # (component, stamped pin or None)
    try:
        for index in range(comp.occurrences.count):
            child = comp.occurrences.item(index)
            member = _member_payload(child.component)
            if member is not None:
                if member.get("role") == schema.MEMBER_WIRE:
                    pin = str(member.get("pin") or "")
                    children.append((child.component, pin or None))
                continue
            if child.component.name.startswith("Wire "):
                children.append((child.component, None))
    except Exception:
        ptutil.log(f"{CMD_NAME}: cable child scan failed on {comp.name}.")
    payload_pins = []
    ends = payload.get("ends") or []
    if ends and isinstance(ends[0], dict):
        payload_pins = [str(pin) for pin in ends[0].get("pins") or []]
    use_payload = len(payload_pins) == len(children)
    wires = []
    for index, (child, stamped_pin) in enumerate(children):
        if stamped_pin:
            pin = stamped_pin
        elif use_payload:
            pin = payload_pins[index]
        elif child.name.startswith("Wire "):
            pin = child.name[len("Wire ") :]
        else:
            pin = child.name
        wires.append({"pin": pin, "extra_cm": _own_curve_length_cm(child)})
    return wires


def _own_curve_length_cm(comp) -> float:
    """Summed length of the component's non-construction sketch curves."""
    total = 0.0
    try:
        for sketch_index in range(comp.sketches.count):
            sketch = comp.sketches.item(sketch_index)
            curves = sketch.sketchCurves
            for curve_index in range(curves.count):
                curve = curves.item(curve_index)
                try:
                    if curve.isConstruction:
                        continue
                    total += curve.length
                except Exception:
                    ptutil.log(f"{CMD_NAME}: a curve in {sketch.name} was skipped.")
    except Exception:
        ptutil.log(f"{CMD_NAME}: sketch scan failed on {comp.name}.")
    return total


def _child_curve_length_cm(comp, role: str, name_prefix: str) -> float:
    """Curve length of the child component with member role *role*.

    Members match by their stamped member attribute first (immune to
    renames); the display-name prefix is only the fallback for assemblies
    built before members were stamped (prefix, because Fusion suffixes
    duplicate component names - "Conductor (1)"). A total miss is logged
    instead of silently reporting a zero length as fact.
    """
    fallback = None
    try:
        for index in range(comp.occurrences.count):
            child = comp.occurrences.item(index)
            member = _member_payload(child.component)
            if member is not None:
                if member.get("role") == role:
                    return _own_curve_length_cm(child.component)
                continue
            if fallback is None and child.component.name.startswith(name_prefix):
                fallback = child.component
    except Exception:
        ptutil.log(f"{CMD_NAME}: child lookup failed on {comp.name}.")
    if fallback is not None:
        return _own_curve_length_cm(fallback)
    ptutil.log(f"{CMD_NAME}: no {role} member found on {comp.name} - length 0.")
    return 0.0


def _member_payload(comp) -> dict | None:
    """The component's parsed member attribute payload, or None."""
    try:
        attr = comp.attributes.itemByName(schema.ATTR_GROUP, schema.MEMBER_NAME)
        return schema.parse_payload(attr.value if attr else "")
    except Exception:
        return None  # tolerant read - not a stamped member


def _end_info(design, end: dict, kind: str) -> dict:
    """Display info for one route end: connector name and pin list."""
    connector = str(end.get("connector_id") or "unknown")
    token = end.get("occ_token") or ""
    if token:
        try:
            for entity in design.findEntityByToken(token) or []:
                occ = adsk.fusion.Occurrence.cast(entity)
                if occ:
                    connector = occ.name
                    break
        except Exception:
            ptutil.log(f"{CMD_NAME}: connector token lookup failed.")
    if kind == route_logic.KIND_CABLE:
        pins = ", ".join(str(pin) for pin in end.get("pins") or [])
    else:
        pins = str(end.get("pin") or "?")
    return {"connector": connector, "pins": pins}


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------
def _display_state(design, report: dict) -> dict:
    """Format the summarized report into the palette's render state."""
    assemblies = []
    for entry in report["assemblies"]:
        if entry["kind"] == route_logic.KIND_CABLE:
            assemblies.append(_display_cable(design, entry))
        else:
            assemblies.append(_display_single(design, entry))
    totals = report["totals"]
    return {
        "theme": ptutil.fusion_theme(),
        "docName": app.activeDocument.name if app.activeDocument else "",
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "wires": totals["wire_count"],
            "cables": totals["cable_count"],
            "conductor": _len_value(design, totals["conductor_cm"]),
        },
        "skipped": report["skipped"],
        "assemblies": assemblies,
    }


def _display_single(design, entry: dict) -> dict:
    return {
        "kind": "wire",
        "title": f"Wire {entry['name']}",
        "ends": _ends_line(entry["ends"]),
        "spec": f"{_awg_text(entry['awg'])} AWG, {_mm_text(entry['od_mm'])} mm sheath",
        "rows": [
            {
                "label": "Bare conductor stubs",
                "value": _len_value(design, entry["conductor_cm"]),
            },
            {
                "label": "Sheathed run",
                "value": _len_value(design, entry["sheath_cm"]),
            },
        ],
        "total": {
            "label": "Total wire length",
            "value": _len_value(design, entry["total_cm"]),
        },
    }


def _display_cable(design, entry: dict) -> dict:
    rows = [
        {
            "label": f"Wire {wire['pin']} path",
            "value": _len_value(design, wire["path_cm"]),
            "highlight": wire["pin"] == entry["longest_pin"],
        }
        for wire in entry["wires"]
    ]
    rows.append(
        {"label": "Jacket run", "value": _len_value(design, entry["jacket_cm"])}
    )
    cable_od = entry.get("cable_od_mm")
    spec = f"{_awg_text(entry['awg'])} AWG, {_mm_text(entry['od_mm'])} mm wires"
    if cable_od:
        spec += f", {_mm_text(cable_od)} mm jacket"
    return {
        "kind": "cable",
        "title": f"Cable {entry['name']}",
        "ends": _ends_line(entry["ends"]),
        "spec": spec,
        "rows": rows,
        "total": {
            "label": (
                f"Cable length (longest wire path, pin {entry['longest_pin']})"
                if entry["longest_pin"]
                else "Cable length"
            ),
            "value": _len_value(design, entry["cable_cm"]),
        },
    }


def _ends_line(ends: list) -> str:
    parts = [
        f"{end.get('connector', '?')} (pins {end.get('pins', '?')})"
        if "," in str(end.get("pins", ""))
        else f"{end.get('connector', '?')} (pin {end.get('pins', '?')})"
        for end in ends
    ]
    return "  <->  ".join(parts) if parts else ""


def _mm_text(value) -> str:
    """A stored millimeter value formatted to 2 decimals ("?" when damaged).

    Route payloads are parsed tolerantly (only the schema version is
    checked), so a missing or non-numeric diameter must degrade to "?" in
    that one route's spec line instead of aborting the whole report with a
    format TypeError.
    """
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "?"


def _awg_text(value) -> str:
    """A stored gauge for display ("?" when absent)."""
    return "?" if value is None else str(value)


def _len_value(design, cm: float) -> dict:
    """A length as raw cm plus a document-units formatted string.

    The page formats from the raw value using the rounding control
    (default .00 mm) and only uses the pre-formatted string for its
    "Document units" option - so changing the rounding never needs a
    round-trip to Fusion.
    """
    try:
        units_mgr = design.unitsManager
        doc = units_mgr.formatInternalValue(cm, units_mgr.defaultLengthUnits, True)
    except Exception:
        doc = f"{cm * 10.0:.2f} mm"
    return {"cm": cm, "doc": doc}


# ---------------------------------------------------------------------------
# Palette lifecycle (repo pattern: delete-then-add, init.js, htmlReady)
# ---------------------------------------------------------------------------
def _show_palette(state: dict):
    global _palette_handlers
    if ui.palettes.itemById(PALETTE_ID) is not None:
        _palette_handlers = []  # the stale palette (and its handlers) go away
    ptutil.write_init_js(INIT_JS_PATH, state, CMD_NAME)
    ptutil.recreate_palette(
        PALETTE_ID,
        PALETTE_NAME,
        PALETTE_URL,
        width=440,
        height=680,
        handlers={
            "incoming": _palette_incoming,
            "closed": _palette_closed,
            "navigating": _palette_navigating,
        },
        local_handlers=_palette_handlers,
        docking=PALETTE_DOCKING,
    )


def _palette_incoming(html_args: adsk.core.HTMLEventArgs):
    global _last_state
    try:
        action = html_args.action
        palette = ui.palettes.itemById(PALETTE_ID)
        if action in ("htmlReady", "refresh") and palette is not None:
            # htmlReady re-sends the state already gathered for this
            # invocation (the init.js sidecar may be stale - Windows CEF
            # caches it by URL) WITHOUT re-measuring the whole design;
            # refresh re-gathers when a design is active and otherwise
            # re-sends the last report (unchanged timestamp) rather than
            # silently leaving stale data that looks refreshed.
            if action == "refresh" or _last_state is None:
                design = adsk.fusion.Design.cast(app.activeProduct)
                if design is not None:
                    _last_state = _gather_state(design)
            if _last_state is not None:
                palette.sendInfoToHTML("setState", json.dumps(_last_state))
        html_args.returnData = "OK"
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} palette event")


def _palette_closed(args):
    global _palette_handlers
    try:
        palette = ui.palettes.itemById(PALETTE_ID)
        if palette:
            palette.deleteMe()  # rebuild fresh handlers on next show
    except Exception:
        ptutil.log(f"{CMD_NAME}: palette close cleanup failed.")
    _palette_handlers = []


def _palette_navigating(args: adsk.core.NavigationEventArgs):
    try:
        if args.navigationURL.startswith("http"):
            args.launchExternally = True
    except Exception:
        ptutil.log(f"{CMD_NAME}: navigation handling failed.")
