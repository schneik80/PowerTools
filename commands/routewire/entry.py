# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Route Wire command (attribute prove-out, part 2).
#
# Consumes the PowerTools.Cable attributes written by Define Wires. The user
# picks two connector occurrences in an assembly; each component is scanned
# for wire-point attributes (construction points and sketch points - the scan
# is per-component, sidestepping the open question of whether findAttributes
# crosses XRef boundaries). A Route type dropdown selects what gets built:
#
# Single wire - pick one pin per connector, an AWG size from the two wires'
# range intersection, and a diameter. Builds under the root:
#
#   Wire <name>            (local assembly component)
#     Conductor            (component: bodies 1 and 2, bare-conductor stubs)
#     Sheath               (component: body 3, the sheathed run)
#
# Cable - every pin is connected, paired in sorted order (counts must
# match); both connectors need the cable breakout point authored by Define
# Wires. One AWG (intersection across every paired wire) and wire diameter
# govern all wires; the cable jacket OD defaults to the standard packed-
# bundle recommendation (logic.cable_od_mm). Builds under the root:
#
#   Cable <name>           (component owning the jacket body)
#     Wire <pin>           (per pair: 2 conductor stubs + 2 sheathed
#                           strip->exit->cable-point end segments)
#
# Ribbon cable is listed but not implemented yet (OK stays disabled).
#
# The geometry construction lives in builder.py (shared with Update Wire):
# solid circular Pipe features along 3D-sketch paths whose points are
# INCLUDED from the connector geometry, so the result is associative and
# follows connector moves; splines are merged onto their neighbor curves
# and tangency-constrained (guide-point fallback if constraints refuse).
# Timeline items are grouped as "Wire <name>" / "Cable <name>" and the
# assembly component is stamped with a "route" attribute recording both
# ends (including occurrence tokens so Update Wire can rebuild).

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..definewires import logic as schema
from . import builder, logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Route Wire"
CMD_ID = "PTCB_routewire"
CMD_Description = (
    "Route a single wire or a multi-conductor cable between two connectors "
    "that carry Define Wires data: pick the connectors, choose an allowed "
    "AWG size and diameters, and build the conductor, sheath, and cable "
    "jacket bodies as a local assembly."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Command-input ids.
INPUT_STATUS = "rw_status"
INPUT_KIND = "rw_kind"
INPUT_CABLE_DIA = "rw_cable_dia"
INPUT_SEL_C1 = "rw_conn1"
INPUT_INFO_C1 = "rw_conn1_info"
INPUT_PIN1 = "rw_pin1"
INPUT_SEL_C2 = "rw_conn2"
INPUT_INFO_C2 = "rw_conn2_info"
INPUT_PIN2 = "rw_pin2"
INPUT_AWG = "rw_awg"
INPUT_DIA = "rw_dia"
INPUT_NAME = "rw_name"

# Per-side input ids, indexed by side (0, 1).
SIDE_SEL_IDS = (INPUT_SEL_C1, INPUT_SEL_C2)
SIDE_INFO_KEYS = ("info0", "info1")
SIDE_PIN_KEYS = ("pin0", "pin1")

PREVIEW_GFX_ID = "PTCB_routewire_preview"

# Route type dropdown labels -> logic kind constants (dropdown order).
KIND_LABELS = (
    ("Single wire", logic.KIND_SINGLE),
    ("Cable", logic.KIND_CABLE),
    ("Ribbon cable", logic.KIND_RIBBON),
)

local_handlers: list = []

# Dialog state for the open command. All reset in command_destroy and,
# defensively, at the top of command_created.
_ui_refs: dict = {}  # long-lived input refs (selections, dropdowns, textboxes)
_sides: list = [None, None]  # per-side data dict (see builder.read_connector)
_loading = False  # reentrancy guard while mutating inputs programmatically


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
        if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            ui.messageBox(
                f"{CMD_NAME} requires a parametric design (the wire features "
                "are grouped in the timeline).",
                CMD_NAME,
                0,
                2,
            )
            args.command.doExecute(False)
            return
        if design.rootComponent.allOccurrences.count < 2:
            ui.messageBox(
                f"{CMD_NAME} runs in an assembly containing at least two "
                "component occurrences with Define Wires data.",
                CMD_NAME,
                0,
                2,
            )
            args.command.doExecute(False)
            return

        cmd = args.command
        inputs = cmd.commandInputs

        status = inputs.addTextBoxCommandInput(INPUT_STATUS, "", "", 3, True)
        status.isFullWidth = True
        _ui_refs["status"] = status

        kind_dd = inputs.addDropDownCommandInput(
            INPUT_KIND, "Route type", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        for index, (label, _kind) in enumerate(KIND_LABELS):
            kind_dd.listItems.add(label, index == 0)
        _ui_refs["kind"] = kind_dd

        for side in (0, 1):
            sel = inputs.addSelectionInput(
                SIDE_SEL_IDS[side],
                f"Connector {side + 1}",
                "Select a component occurrence that has Define Wires data.",
            )
            sel.addSelectionFilter("Occurrences")
            sel.setSelectionLimits(1, 1)
            _ui_refs[f"sel{side}"] = sel

            info = inputs.addTextBoxCommandInput(
                INPUT_INFO_C1 if side == 0 else INPUT_INFO_C2, "", "", 2, True
            )
            _ui_refs[SIDE_INFO_KEYS[side]] = info

            pin_dd = inputs.addDropDownCommandInput(
                INPUT_PIN1 if side == 0 else INPUT_PIN2,
                f"Pin ({side + 1})",
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            _ui_refs[SIDE_PIN_KEYS[side]] = pin_dd

        awg_dd = inputs.addDropDownCommandInput(
            INPUT_AWG, "Gauge (AWG)", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        _ui_refs["awg"] = awg_dd

        dia = inputs.addValueInput(
            INPUT_DIA,
            "Wire diameter",
            "mm",
            adsk.core.ValueInput.createByReal(
                logic.recommended_od_mm(schema.AWG_DEFAULT_MAX) / 10.0
            ),
        )
        dia.tooltip = (
            "Sheathed outer diameter. A recommended value (conductor plus "
            "insulation walls) is filled in when the gauge changes; edit freely."
        )
        _ui_refs["dia"] = dia

        cable_dia = inputs.addValueInput(
            INPUT_CABLE_DIA,
            "Cable diameter",
            "mm",
            adsk.core.ValueInput.createByReal(0.0),
        )
        cable_dia.tooltip = (
            "Cable jacket outer diameter. The recommendation is the packed "
            "wire bundle (standard cable-design factors) plus a lay "
            "allowance and jacket walls; edit freely."
        )
        cable_dia.isVisible = False  # cable route type only
        _ui_refs["cable_dia"] = cable_dia

        _ui_refs["name"] = inputs.addStringValueInput(INPUT_NAME, "Wire name", "")

        _update_status()

        ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
        ptutil.add_handler(
            cmd.executePreview, command_execute_preview, local_handlers=local_handlers
        )
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
# Execute preview - keep the exit-to-exit line alive once OK is enabled
# ---------------------------------------------------------------------------
def command_execute_preview(args: adsk.core.CommandEventArgs):
    # Custom graphics drawn during a command live inside its transaction.
    # While inputs are invalid this event never fires and the line drawn
    # from inputChanged persists; once validateInputs turns true, Fusion
    # runs a preview cycle after every input change, and each cycle FIRST
    # rolls the document back - wiping graphics drawn earlier (the line
    # vanished the moment the wire name enabled OK). Redrawing here keeps
    # it alive through every cycle.
    try:
        _update_preview()
        # Graphics-only preview: never claim a valid result, so the real
        # command_execute still runs on OK (a True here would skip it).
        args.isValidResult = False
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} executePreview")


# ---------------------------------------------------------------------------
# Input changed
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    # The mute flag is held across each WHOLE mutation block: every
    # programmatic change below (dropdown items, textbox text, the diameter
    # value) re-fires inputChanged, and reacting to our own events while
    # still mutating is how a dialog hangs Fusion's UI thread. Events Fusion
    # re-delivers after this handler returns hit rebuilds that are
    # idempotent (_set_list_items compares first), so they no-op.
    global _loading
    try:
        if _loading:
            return
        changed_id = args.input.id

        if changed_id in SIDE_SEL_IDS:
            side = SIDE_SEL_IDS.index(changed_id)
            _loading = True
            try:
                _on_connector_changed(
                    side, adsk.core.SelectionCommandInput.cast(args.input)
                )
                _refresh_route_options()
            finally:
                _loading = False
        elif changed_id in (INPUT_PIN1, INPUT_PIN2):
            _loading = True
            try:
                _refresh_route_options()
            finally:
                _loading = False
        elif changed_id == INPUT_KIND:
            _loading = True
            try:
                _apply_kind_visibility()
                _refresh_route_options()
            finally:
                _loading = False
        elif changed_id == INPUT_AWG:
            _loading = True
            try:
                _update_dia()
                _update_cable_dia()
            finally:
                _loading = False
        elif changed_id == INPUT_DIA:
            # A hand-edited wire diameter changes the recommended cable OD.
            _loading = True
            try:
                _update_cable_dia()
            finally:
                _loading = False
        elif changed_id == INPUT_NAME:
            _loading = True
            try:
                _update_status()  # clears a stale "Enter a name." hint
            finally:
                _loading = False
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} inputChanged")


def _refresh_route_options():
    """Recompute the AWG options, diameters, preview, and status."""
    _rebuild_awg_dropdown()
    _update_cable_dia()
    _update_preview()
    _update_status()


def _current_kind() -> str:
    """The selected route type as a logic kind constant."""
    dropdown = _ui_refs.get("kind")
    selected = dropdown.selectedItem if dropdown else None
    if selected is not None:
        for label, kind in KIND_LABELS:
            if label == selected.name:
                return kind
    return logic.KIND_SINGLE


def _apply_kind_visibility():
    """Show/hide the kind-dependent inputs (pins for single, cable OD)."""
    kind = _current_kind()
    is_cable = kind == logic.KIND_CABLE
    for key in SIDE_PIN_KEYS:
        dropdown = _ui_refs.get(key)
        if dropdown is not None:
            # A cable connects every pin (paired in order) - no pin choice.
            dropdown.isVisible = not is_cable
    cable_dia = _ui_refs.get("cable_dia")
    if cable_dia is not None:
        cable_dia.isVisible = is_cable


def _on_connector_changed(side: int, sel):
    """Re-read the picked occurrence's wire data and rebuild its pin list."""
    if sel is None or sel.selectionCount == 0:
        _sides[side] = None
    else:
        occ = adsk.fusion.Occurrence.cast(sel.selection(0).entity)
        _sides[side] = builder.read_connector(occ) if occ else None
    _update_info(side)
    _rebuild_pin_dropdown(side)


# ---------------------------------------------------------------------------
# Validate - gate OK until a buildable route is defined
# ---------------------------------------------------------------------------
def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        args.areInputsValid = not _route_problems()
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} validateInputs")
        args.areInputsValid = True  # fail-open so the user is never stuck


def _route_problems() -> list:
    """Everything preventing OK for the current route type (empty = ready).

    Shared by validateInputs (gates OK) and the status box (explains why).
    """
    problems: list = []
    kind = _current_kind()
    if kind == logic.KIND_RIBBON:
        return ["Ribbon cable routing is not implemented yet."]
    if _sides[0] is None or _sides[1] is None:
        return ["Select two connector components that carry wire points."]
    for side in (0, 1):
        if _sides[side]["error"]:
            problems.append(f"Connector {side + 1}: {_sides[side]['error']}")
    if problems:
        return problems
    if _sides[0]["path"] == _sides[1]["path"]:
        return ["Pick two different occurrences."]

    if kind == logic.KIND_CABLE:
        problems.extend(_cable_problems())
    else:
        problems.extend(_single_problems())
    if problems:
        return problems

    awg = _selected_awg()
    dia = _ui_refs.get("dia")
    if (
        awg is not None
        and dia is not None
        and dia.value <= logic.conductor_diameter_mm(awg) / 10.0
    ):
        problems.append("Wire diameter must exceed the bare conductor.")
    name_input = _ui_refs.get("name")
    if name_input is None or not name_input.value.strip():
        problems.append("Enter a name.")
    return problems


def _single_problems() -> list:
    """Single-wire route checks (both connectors already validated)."""
    wire_a, wire_b = _selected_wire(0), _selected_wire(1)
    if not wire_a or not wire_b:
        return ["Select a pin on each connector."]
    if _selected_awg() is None:
        return ["The selected wires share no allowed AWG size."]
    exit_a = wire_a["world"][schema.ROLE_EXIT]
    exit_b = wire_b["world"][schema.ROLE_EXIT]
    if exit_a.distanceTo(exit_b) < 1e-6:
        return ["The two exit points coincide."]
    return []


def _cable_problems() -> list:
    """Cable route checks (both connectors already validated)."""
    problems: list = []
    for side in (0, 1):
        if _sides[side]["cable"] is None:
            problems.append(
                f"Connector {side + 1} ('{_sides[side]['comp_name']}') has "
                "no cable point. Re-run Define Wires on the connector part "
                "and confirm its summary says 'Cable point written'; if the "
                "part is referenced, save it and update the out-of-date "
                "reference in this assembly."
            )
    wires_a, wires_b = _cable_wires(0), _cable_wires(1)
    if len(wires_a) != len(wires_b):
        problems.append(
            f"Pin counts differ ({len(wires_a)} vs {len(wires_b)}) - cable "
            "routing pairs pins in sorted order."
        )
    elif len(wires_a) < 2:
        problems.append("A cable needs at least two wires per connector.")
    if problems:
        return problems
    if _selected_awg() is None:
        return ["The paired wires share no allowed AWG size."]
    cable_a = _sides[0]["cable"]["world"]
    cable_b = _sides[1]["cable"]["world"]
    if cable_a.distanceTo(cable_b) < 1e-6:
        return ["The two cable points coincide."]
    cable_dia = _ui_refs.get("cable_dia")
    dia = _ui_refs.get("dia")
    if cable_dia is not None and dia is not None and cable_dia.value < dia.value:
        return ["Cable diameter must not be smaller than the wire diameter."]
    return []


# ---------------------------------------------------------------------------
# Execute - build the wire assembly
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    try:
        _clear_preview()
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            return
        awg = _selected_awg()
        if awg is None:
            ui.messageBox(f"{CMD_NAME}: route is incomplete.", CMD_NAME, 0, 2)
            return
        name = _ui_refs["name"].value.strip()
        sheath_dia_cm = _ui_refs["dia"].value
        if _current_kind() == logic.KIND_CABLE:
            _execute_cable(design, name, awg, sheath_dia_cm)
        else:
            _execute_single(design, name, awg, sheath_dia_cm)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _execute_single(design, name: str, awg: int, sheath_dia_cm: float):
    """Build a single wire and report the result."""
    wire_a, wire_b = _selected_wire(0), _selected_wire(1)
    if not wire_a or not wire_b:
        ui.messageBox(f"{CMD_NAME}: route is incomplete.", CMD_NAME, 0, 2)
        return
    result = builder.build_wire(
        design,
        ((_sides[0], wire_a), (_sides[1], wire_b)),
        {"name": name, "awg": awg, "od_mm": sheath_dia_cm * 10.0},
    )
    summary = (
        f"Wire {name} routed.\n\n"
        f"Pins: {wire_a['pin']} <-> {wire_b['pin']}\n"
        f"Gauge: {awg} AWG "
        f"(conductor {logic.conductor_diameter_mm(awg):.3f} mm)\n"
        f"Sheath diameter: {sheath_dia_cm * 10.0:.3f} mm\n"
        "Bodies: 2 conductor stubs + 1 sheath run."
    )
    ui.messageBox(summary + _result_notes(result), CMD_NAME)


def _execute_cable(design, name: str, awg: int, sheath_dia_cm: float):
    """Build a multi-conductor cable and report the result."""
    wires_a, wires_b = _cable_wires(0), _cable_wires(1)
    if not wires_a or len(wires_a) != len(wires_b):
        ui.messageBox(f"{CMD_NAME}: cable route is incomplete.", CMD_NAME, 0, 2)
        return
    cable_dia_cm = _ui_refs["cable_dia"].value
    result = builder.build_cable(
        design,
        ((_sides[0], wires_a), (_sides[1], wires_b)),
        {
            "name": name,
            "awg": awg,
            "od_mm": sheath_dia_cm * 10.0,
            "cable_od_mm": cable_dia_cm * 10.0,
        },
    )
    summary = (
        f"Cable {name} routed.\n\n"
        f"Wires: {len(wires_a)} "
        f"(pins {', '.join(wire['pin'] for wire in wires_a)})\n"
        f"Gauge: {awg} AWG "
        f"(conductor {logic.conductor_diameter_mm(awg):.3f} mm)\n"
        f"Wire diameter: {sheath_dia_cm * 10.0:.3f} mm\n"
        f"Cable diameter: {cable_dia_cm * 10.0:.3f} mm\n"
        f"Bodies: 1 jacket + {len(wires_a) * 4} wire bodies."
    )
    ui.messageBox(summary + _result_notes(result), CMD_NAME)


def _result_notes(result: dict) -> str:
    """The build result's fallback/baked-point notes for the summary box."""
    notes = ""
    if result["spline_fallback"]:
        notes += (
            "\n\nNote: tangency constraints could not be applied everywhere "
            "- some splines were shaped with guide points instead (see the "
            "debug log for the reason)."
        )
    if result["baked_points"]:
        notes += (
            f"\n\nNote: {result['baked_points']} point(s) could not be "
            "linked to the connector geometry and were baked at fixed "
            "positions (those parts will not follow connector moves)."
        )
    return notes


# ---------------------------------------------------------------------------
# Dropdowns, info, status, preview
# ---------------------------------------------------------------------------
def _set_list_items(dropdown, names: list):
    """Replace a dropdown's items with *names* (first item selected).

    Idempotent: when the list already matches, nothing is touched (so an
    event Fusion re-delivers after a rebuild converges instead of churning,
    and a user's selection within an unchanged list survives). Clearing uses
    the documented ListItems.clear() - a prior delete-first-item loop here
    could spin forever when Fusion refused to delete the selected item,
    hard-hanging the UI thread.
    """
    items = dropdown.listItems
    current = [items.item(index).name for index in range(items.count)]
    if current == names:
        return
    items.clear()
    for index, name in enumerate(names):
        items.add(name, index == 0)


def _sorted_pins(wires: dict) -> list:
    """Pins sorted numerically when possible, then lexically."""
    return logic.sort_pins(wires.keys())


def _cable_wires(side: int) -> list:
    """ALL of a side's wire records in paired (sorted pin) order."""
    data = _sides[side]
    if not data or not data["wires"]:
        return []
    return [data["wires"][pin] for pin in _sorted_pins(data["wires"])]


def _rebuild_pin_dropdown(side: int):
    """Refresh a side's pin list from its connector data (idempotent)."""
    dropdown = _ui_refs.get(SIDE_PIN_KEYS[side])
    if dropdown is None:
        return
    data = _sides[side]
    names = _sorted_pins(data["wires"]) if data and data["wires"] else []
    _set_list_items(dropdown, names)


def _rebuild_awg_dropdown():
    """Refresh the AWG options for the current route type (idempotent).

    Single wire: the intersection of the two selected wires' ranges.
    Cable: the intersection across EVERY wire on both connectors (one gauge
    governs the whole cable).
    """
    dropdown = _ui_refs.get("awg")
    if dropdown is None:
        return
    if _current_kind() == logic.KIND_CABLE:
        wires = _cable_wires(0) + _cable_wires(1)
        sizes = (
            logic.awg_overlap_many([(w["awg_min"], w["awg_max"]) for w in wires])
            if _cable_wires(0) and _cable_wires(1)
            else []
        )
    else:
        wire_a, wire_b = _selected_wire(0), _selected_wire(1)
        sizes = (
            logic.awg_overlap(
                (wire_a["awg_min"], wire_a["awg_max"]),
                (wire_b["awg_min"], wire_b["awg_max"]),
            )
            if wire_a and wire_b
            else []
        )
    _set_list_items(dropdown, [str(size) for size in sizes])
    _update_dia()


def _update_cable_dia():
    """Refresh the recommended cable jacket OD from wire dia and count."""
    if _current_kind() != logic.KIND_CABLE:
        return
    cable_dia = _ui_refs.get("cable_dia")
    dia = _ui_refs.get("dia")
    count = len(_cable_wires(0))
    if cable_dia is None or dia is None or count == 0:
        return
    cable_dia.value = logic.cable_od_mm(dia.value * 10.0, count) / 10.0


def _selected_wire(side: int):
    """The wire record for the side's selected pin, or None."""
    data = _sides[side]
    if not data or not data["wires"]:
        return None
    dropdown = _ui_refs.get(SIDE_PIN_KEYS[side])
    selected = dropdown.selectedItem if dropdown else None
    if selected is None:
        return None
    return data["wires"].get(selected.name)


def _selected_awg():
    """The selected AWG size as an int, or None."""
    dropdown = _ui_refs.get("awg")
    selected = dropdown.selectedItem if dropdown else None
    if selected is None:
        return None
    try:
        return int(selected.name)
    except ValueError:
        return None


def _update_dia():
    """Refresh the recommended sheathed diameter for the selected gauge."""
    awg = _selected_awg()
    dia = _ui_refs.get("dia")
    if awg is None or dia is None:
        return
    dia.value = logic.recommended_od_mm(awg) / 10.0  # mm -> cm internal


def _update_info(side: int):
    info = _ui_refs.get(SIDE_INFO_KEYS[side])
    if info is None:
        return
    data = _sides[side]
    if data is None:
        info.text = ""
    elif data["error"]:
        info.text = data["error"]
    else:
        pins = ", ".join(_sorted_pins(data["wires"]))
        info.text = f"{data['comp_name']}: {len(data['wires'])} wire(s), pins {pins}"


def _update_status():
    status = _ui_refs.get("status")
    if status is None:
        return
    problems = _route_problems()
    status.text = "\n".join(problems) if problems else "Ready to route."


def _clear_preview():
    """Delete this command's custom graphics preview group(s), by id tag."""
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return
        groups = design.rootComponent.customGraphicsGroups
        for index in range(groups.count - 1, -1, -1):
            if groups.item(index).id == PREVIEW_GFX_ID:
                groups.item(index).deleteMe()
    except Exception:
        ptutil.log(f"{CMD_NAME}: preview cleanup failed.")


def _update_preview():
    """Redraw the preview line: exit-to-exit (single) or the cable run."""
    _clear_preview()
    kind = _current_kind()
    if kind == logic.KIND_CABLE:
        cable_a = _sides[0]["cable"] if _sides[0] else None
        cable_b = _sides[1]["cable"] if _sides[1] else None
        if not cable_a or not cable_b:
            return
        point_a, point_b = cable_a["world"], cable_b["world"]
    elif kind == logic.KIND_SINGLE:
        wire_a, wire_b = _selected_wire(0), _selected_wire(1)
        if not wire_a or not wire_b:
            return
        point_a = wire_a["world"][schema.ROLE_EXIT]
        point_b = wire_b["world"][schema.ROLE_EXIT]
    else:
        return  # ribbon: nothing to preview yet
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return
        if point_a.distanceTo(point_b) < 1e-6:
            return
        graphics = design.rootComponent.customGraphicsGroups.add()
        graphics.id = PREVIEW_GFX_ID
        curve = graphics.addCurve(adsk.core.Line3D.create(point_a, point_b))
        curve.weight = 2.0
        curve.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(255, 140, 0, 255)
        )
    except Exception:
        ptutil.log(f"{CMD_NAME}: preview draw failed:\n{traceback.format_exc()}")


def _reset_state():
    """Reset all per-dialog module state."""
    global _ui_refs, _sides, _loading
    _ui_refs = {}
    _sides = [None, None]
    _loading = False


# ---------------------------------------------------------------------------
# Destroy - release references, remove preview graphics, reset state
# ---------------------------------------------------------------------------
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    _clear_preview()
    _reset_state()
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
