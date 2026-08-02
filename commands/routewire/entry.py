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
# crosses XRef boundaries). The user then picks one pin per connector, an AWG
# size from the intersection of both wires' allowed ranges (a recommended
# sheathed outer diameter is offered, editable), and a wire name. A custom
# graphics line previews the exit-to-exit connection.
#
# On OK the command builds, under the design root:
#
#   Wire <name>            (local assembly component)
#     Conductor            (component: bodies 1 and 2, bare-conductor stubs)
#     Sheath               (component: body 3, the sheathed run)
#
# The geometry construction lives in builder.py (shared with Update Wire):
# solid circular Pipe features along 3D-sketch paths whose points are
# INCLUDED from the connector geometry, so the wire is associative and
# follows connector moves; the exit-to-exit spline is merged onto the exit
# lines and tangency-constrained (guide-point fallback if constraints
# refuse). All timeline items are grouped as "Wire <name>", features/bodies
# carry "Wire <name> ..." names, and the wire assembly component is stamped
# with a "route" attribute recording both ends (including occurrence tokens
# so Update Wire can rebuild after connector edits break the links).

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
    "Route a wire between two connectors that carry Define Wires data: pick "
    "the connectors and pins, choose an allowed AWG size and sheath diameter, "
    "and build the conductor and sheath bodies as a local wire assembly."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Command-input ids.
INPUT_STATUS = "rw_status"
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

        _ui_refs["name"] = inputs.addStringValueInput(INPUT_NAME, "Wire name", "")

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
        elif changed_id == INPUT_AWG:
            _loading = True
            try:
                _update_dia()
            finally:
                _loading = False
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} inputChanged")


def _refresh_route_options():
    """Recompute the AWG options, recommended diameter, preview, and status."""
    _rebuild_awg_dropdown()
    _update_preview()
    _update_status()


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
        wire_a, wire_b = _selected_wire(0), _selected_wire(1)
        if not wire_a or not wire_b:
            args.areInputsValid = False
            return
        if _sides[0]["path"] == _sides[1]["path"]:
            args.areInputsValid = False  # same occurrence picked twice
            return
        awg = _selected_awg()
        if awg is None:
            args.areInputsValid = False
            return
        dia_cm = _ui_refs["dia"].value
        if dia_cm <= logic.conductor_diameter_mm(awg) / 10.0:
            args.areInputsValid = False  # sheath must cover the conductor
            return
        if not _ui_refs["name"].value.strip():
            args.areInputsValid = False
            return
        exit_a = wire_a["world"][schema.ROLE_EXIT]
        exit_b = wire_b["world"][schema.ROLE_EXIT]
        args.areInputsValid = exit_a.distanceTo(exit_b) > 1e-6
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} validateInputs")
        args.areInputsValid = True  # fail-open so the user is never stuck


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
        wire_a, wire_b = _selected_wire(0), _selected_wire(1)
        awg = _selected_awg()
        if not wire_a or not wire_b or awg is None:
            ui.messageBox(f"{CMD_NAME}: route is incomplete.", CMD_NAME, 0, 2)
            return
        name = _ui_refs["name"].value.strip()
        sheath_dia_cm = _ui_refs["dia"].value

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
        if result["spline_fallback"]:
            summary += (
                "\n\nNote: tangency constraints could not be applied - the "
                "spline was shaped with guide points instead (see the debug "
                "log for the reason)."
            )
        if result["baked_points"]:
            summary += (
                f"\n\nNote: {result['baked_points']} point(s) could not be "
                "linked to the connector geometry and were baked at fixed "
                "positions (that part of the wire will not follow connector "
                "moves)."
            )
        ui.messageBox(summary, CMD_NAME)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


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
    return sorted(
        wires.keys(),
        key=lambda pin: (0, int(pin), "") if pin.isdigit() else (1, 0, pin),
    )


def _rebuild_pin_dropdown(side: int):
    """Refresh a side's pin list from its connector data (idempotent)."""
    dropdown = _ui_refs.get(SIDE_PIN_KEYS[side])
    if dropdown is None:
        return
    data = _sides[side]
    names = _sorted_pins(data["wires"]) if data and data["wires"] else []
    _set_list_items(dropdown, names)


def _rebuild_awg_dropdown():
    """Refresh the AWG options from the two selected wires (idempotent)."""
    dropdown = _ui_refs.get("awg")
    if dropdown is None:
        return
    wire_a, wire_b = _selected_wire(0), _selected_wire(1)
    names = []
    if wire_a and wire_b:
        names = [
            str(size)
            for size in logic.awg_overlap(
                (wire_a["awg_min"], wire_a["awg_max"]),
                (wire_b["awg_min"], wire_b["awg_max"]),
            )
        ]
    _set_list_items(dropdown, names)
    _update_dia()


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
    problems = []
    if _sides[0] is None or _sides[1] is None:
        problems.append("Select two connector components that carry wire points.")
    for side in (0, 1):
        if _sides[side] and _sides[side]["error"]:
            problems.append(f"Connector {side + 1}: {_sides[side]['error']}")
    if _sides[0] and _sides[1] and _sides[0]["path"] == _sides[1]["path"]:
        problems.append("Pick two different occurrences.")
    wire_a, wire_b = _selected_wire(0), _selected_wire(1)
    if wire_a and wire_b and _selected_awg() is None:
        problems.append("The selected wires share no allowed AWG size.")
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
    """Redraw the exit-to-exit preview line for the selected pins."""
    _clear_preview()
    wire_a, wire_b = _selected_wire(0), _selected_wire(1)
    if not wire_a or not wire_b:
        return
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return
        exit_a = wire_a["world"][schema.ROLE_EXIT]
        exit_b = wire_b["world"][schema.ROLE_EXIT]
        if exit_a.distanceTo(exit_b) < 1e-6:
            return
        graphics = design.rootComponent.customGraphicsGroups.add()
        graphics.id = PREVIEW_GFX_ID
        curve = graphics.addCurve(adsk.core.Line3D.create(exit_a, exit_b))
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
