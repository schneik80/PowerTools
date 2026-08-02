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
# Each body is a solid circular Pipe feature along a path: the conductor
# stubs run conductor-start -> strip-length per connector at the bare AWG
# diameter; the sheath runs strip -> exit, a smooth exit-to-exit spline
# (tangency-constrained to the exit lines, with a guide-point fallback when
# 3D-sketch constraints refuse), then exit -> strip on the far side, swept at
# the sheath diameter. All timeline items are grouped as "Wire <name>" and
# the features/bodies carry "Wire <name> ..." names. The wire assembly
# component is stamped with a "route" attribute recording both ends.

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..definewires import logic as schema
from . import logic

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
_sides: list = [None, None]  # per-side connector data dict (see _read_connector)
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
    try:
        if _loading:
            return
        changed_id = args.input.id

        if changed_id in SIDE_SEL_IDS:
            side = SIDE_SEL_IDS.index(changed_id)
            _on_connector_changed(
                side, adsk.core.SelectionCommandInput.cast(args.input)
            )
            _rebuild_awg_dropdown()
            _update_preview()
            _update_status()
        elif changed_id in (INPUT_PIN1, INPUT_PIN2):
            _rebuild_awg_dropdown()
            _update_preview()
            _update_status()
        elif changed_id == INPUT_AWG:
            _update_dia()
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} inputChanged")


def _on_connector_changed(side: int, sel):
    """Re-read the picked occurrence's wire data and rebuild its pin list."""
    if sel is None or sel.selectionCount == 0:
        _sides[side] = None
    else:
        occ = adsk.fusion.Occurrence.cast(sel.selection(0).entity)
        _sides[side] = _read_connector(occ) if occ else None
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
        conductor_dia_cm = logic.conductor_diameter_mm(awg) / 10.0

        timeline_start = design.timeline.markerPosition

        identity = adsk.core.Matrix3D.create()
        root = design.rootComponent
        asm_comp = root.occurrences.addNewComponent(identity).component
        asm_comp.name = f"Wire {name}"
        conductor_comp = asm_comp.occurrences.addNewComponent(identity).component
        conductor_comp.name = "Conductor"
        sheath_comp = asm_comp.occurrences.addNewComponent(identity).component
        sheath_comp.name = "Sheath"

        _build_conductor_bodies(
            conductor_comp, (wire_a, wire_b), conductor_dia_cm, name
        )
        _build_sheath_body(sheath_comp, (wire_a, wire_b), sheath_dia_cm, name)

        asm_comp.attributes.add(
            schema.ATTR_GROUP,
            logic.ROUTE_NAME,
            logic.build_route_payload(
                {
                    "name": name,
                    "awg": awg,
                    "od_mm": sheath_dia_cm * 10.0,
                    "ends": [
                        _route_end(_sides[0], wire_a),
                        _route_end(_sides[1], wire_b),
                    ],
                }
            ),
        )

        _group_timeline(design, timeline_start, name)

        ui.messageBox(
            f"Wire {name} routed.\n\n"
            f"Pins: {wire_a['pin']} <-> {wire_b['pin']}\n"
            f"Gauge: {awg} AWG "
            f"(conductor {logic.conductor_diameter_mm(awg):.3f} mm)\n"
            f"Sheath diameter: {sheath_dia_cm * 10.0:.3f} mm\n"
            "Bodies: 2 conductor stubs + 1 sheath run.",
            CMD_NAME,
        )
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _route_end(side_data: dict, wire: dict) -> dict:
    """One end's identity for the route attribute payload."""
    return {
        "connector_id": side_data["connector_id"],
        "wire_id": wire["wire_id"],
        "pin": wire["pin"],
    }


def _build_conductor_bodies(comp, wires, dia_cm: float, name: str):
    """Bodies 1 and 2: bare-conductor stubs, start -> strip, per connector."""
    sketch = comp.sketches.add(comp.xYConstructionPlane)
    sketch.name = f"Wire {name} conductor paths"
    for index, wire in enumerate(wires, start=1):
        line = sketch.sketchCurves.sketchLines.addByTwoPoints(
            sketch.modelToSketchSpace(wire["world"][schema.ROLE_START]),
            sketch.modelToSketchSpace(wire["world"][schema.ROLE_STRIP]),
        )
        path = comp.features.createPath(line, False)
        _add_pipe(comp, path, dia_cm, f"Wire {name} conductor {index}")


def _build_sheath_body(comp, wires, dia_cm: float, name: str):
    """Body 3: strip -> exit, smooth exit-to-exit spline, exit -> strip."""
    wire_a, wire_b = wires
    sketch = comp.sketches.add(comp.xYConstructionPlane)
    sketch.name = f"Wire {name} sheath path"
    lines = sketch.sketchCurves.sketchLines
    line_a = lines.addByTwoPoints(
        sketch.modelToSketchSpace(wire_a["world"][schema.ROLE_STRIP]),
        sketch.modelToSketchSpace(wire_a["world"][schema.ROLE_EXIT]),
    )
    line_b = lines.addByTwoPoints(
        sketch.modelToSketchSpace(wire_b["world"][schema.ROLE_STRIP]),
        sketch.modelToSketchSpace(wire_b["world"][schema.ROLE_EXIT]),
    )
    spline = _add_exit_spline(sketch, (line_a, line_b), wire_a, wire_b)

    curves = adsk.core.ObjectCollection.create()
    curves.add(line_a)
    curves.add(spline)
    curves.add(line_b)
    path = comp.features.createPath(curves, False)
    _add_pipe(comp, path, dia_cm, f"Wire {name} sheath")


def _add_exit_spline(sketch, exit_lines, wire_a, wire_b):
    """Create the exit-to-exit spline, smooth against both exit lines.

    Preferred: a two-point fitted spline made coincident and tangent to the
    exit lines (the lines are fixed first so the solver bends the spline, not
    the connector geometry). 3D-sketch constraint support is not guaranteed by
    the API docs, so any constraint failure falls back to an unconstrained
    spline shaped by directional guide points (logic.spline_guide_points).
    """
    line_a, line_b = exit_lines
    exit_a = sketch.modelToSketchSpace(wire_a["world"][schema.ROLE_EXIT])
    exit_b = sketch.modelToSketchSpace(wire_b["world"][schema.ROLE_EXIT])
    fit = adsk.core.ObjectCollection.create()
    fit.add(exit_a)
    fit.add(exit_b)
    spline = sketch.sketchCurves.sketchFittedSplines.add(fit)
    try:
        line_a.isFixed = True
        line_b.isFixed = True
        constraints = sketch.geometricConstraints
        constraints.addCoincident(spline.startSketchPoint, line_a.endSketchPoint)
        constraints.addCoincident(spline.endSketchPoint, line_b.endSketchPoint)
        if constraints.addTangent(line_a, spline) is None:
            raise ValueError("addTangent(line_a, spline) returned null")
        if constraints.addTangent(spline, line_b) is None:
            raise ValueError("addTangent(spline, line_b) returned null")
        return spline
    except Exception:
        ptutil.log(
            f"{CMD_NAME}: tangency constraints unavailable, using guide-point "
            f"spline.\n{traceback.format_exc()}"
        )
    try:
        spline.deleteMe()
    except Exception:
        ptutil.log(f"{CMD_NAME}: could not delete the constrained spline attempt.")
    guides = logic.spline_guide_points(
        _as_tuple(wire_a["world"][schema.ROLE_STRIP]),
        _as_tuple(wire_a["world"][schema.ROLE_EXIT]),
        _as_tuple(wire_b["world"][schema.ROLE_STRIP]),
        _as_tuple(wire_b["world"][schema.ROLE_EXIT]),
    )
    fallback_fit = adsk.core.ObjectCollection.create()
    for xyz in guides:
        fallback_fit.add(sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz)))
    return sketch.sketchCurves.sketchFittedSplines.add(fallback_fit)


def _add_pipe(comp, path, dia_cm: float, label: str):
    """Solid circular pipe of *dia_cm* along *path*, named *label*."""
    pipes = comp.features.pipeFeatures
    pipe_input = pipes.createInput(
        path, adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    # VERIFY AT RUNTIME: sectionSize is assumed to be the section DIAMETER
    # (matching the UI's "Section Size" field); the API docs do not say
    # radius or diameter. Section type defaults to circular, solid.
    pipe_input.sectionSize = adsk.core.ValueInput.createByReal(dia_cm)
    pipe = pipes.add(pipe_input)
    pipe.name = label
    try:
        if pipe.bodies.count > 0:
            pipe.bodies.item(0).name = label
    except Exception:
        ptutil.log(f"{CMD_NAME}: could not rename body for '{label}'.")
    return pipe


def _group_timeline(design, start_index: int, name: str):
    """Group everything created since *start_index* as 'Wire <name>'."""
    try:
        timeline = design.timeline
        end_index = timeline.markerPosition - 1
        if end_index > start_index:
            group = timeline.timelineGroups.add(start_index, end_index)
            group.name = f"Wire {name}"
    except Exception:
        ptutil.log(f"{CMD_NAME}: timeline grouping failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Reading connector data
# ---------------------------------------------------------------------------
def _read_connector(occ) -> dict:
    """Scan the occurrence's component for Define Wires attribute data.

    Returns a dict with ``occ``, ``path`` (unique occurrence path),
    ``comp_name``, ``connector_id``, ``wires`` (``{pin: {wire_id, pin,
    awg_min, awg_max, world: {role: Point3D}}}`` — complete wires only, world
    positions in root space via occurrence proxies), and ``error`` ("" when
    usable).
    """
    comp = occ.component
    data = {
        "occ": occ,
        "path": _occ_path(occ),
        "comp_name": comp.name,
        "connector_id": "",
        "wires": {},
        "error": "",
    }
    manifest = schema.parse_payload(_component_manifest_value(comp))
    if manifest:
        data["connector_id"] = str(manifest.get("connector_id") or "")

    partial: dict = {}
    for entity in _iter_component_points(comp):
        for attr_name, payload in _cable_attrs_on(entity):
            parsed = schema.parse_point_attr_name(attr_name)
            if parsed is None or payload is None:
                continue
            wire_id, role = parsed
            record = partial.setdefault(
                wire_id,
                {
                    "wire_id": wire_id,
                    "pin": str(payload.get("pin") or ""),
                    "awg_min": schema.coerce_awg(
                        payload.get("awg_min"), schema.AWG_DEFAULT_MIN
                    ),
                    "awg_max": schema.coerce_awg(
                        payload.get("awg_max"), schema.AWG_DEFAULT_MAX
                    ),
                    "points": {},
                },
            )
            record["points"][role] = entity

    for record in partial.values():
        if not record["pin"] or set(record["points"]) != set(schema.ROLES):
            continue  # incomplete wire - not routable
        world = {}
        for role, entity in record["points"].items():
            point = _world_point(entity, occ)
            if point is None:
                break
            world[role] = point
        if len(world) != len(schema.ROLES):
            continue
        record["world"] = world
        del record["points"]
        data["wires"][record["pin"]] = record

    if not data["wires"]:
        data["error"] = (
            f"No complete Define Wires data found on '{comp.name}'. Run "
            "Define Wires on the connector part first."
        )
    return data


def _component_manifest_value(comp) -> str:
    """The component's connector-manifest attribute value ("" when absent)."""
    try:
        attr = comp.attributes.itemByName(schema.ATTR_GROUP, schema.MANIFEST_NAME)
        return attr.value if attr else ""
    except Exception:
        return ""  # tolerant read - a missing manifest is not an error


def _iter_component_points(comp):
    """Yield every construction point and sketch point of *comp* (native)."""
    try:
        for index in range(comp.constructionPoints.count):
            yield comp.constructionPoints.item(index)
    except Exception:
        ptutil.log(f"{CMD_NAME}: construction point scan failed on {comp.name}.")
    try:
        for sketch_index in range(comp.sketches.count):
            sketch = comp.sketches.item(sketch_index)
            for point_index in range(sketch.sketchPoints.count):
                yield sketch.sketchPoints.item(point_index)
    except Exception:
        ptutil.log(f"{CMD_NAME}: sketch point scan failed on {comp.name}.")


def _cable_attrs_on(entity) -> list:
    """``(name, parsed_payload)`` for the entity's PowerTools.Cable attributes."""
    results = []
    try:
        attrs = entity.attributes
        for index in range(attrs.count):
            attribute = attrs.item(index)
            if attribute.groupName != schema.ATTR_GROUP:
                continue
            results.append((attribute.name, schema.parse_payload(attribute.value)))
    except Exception:
        ptutil.log(f"{CMD_NAME}: attribute read failed on an entity - skipped.")
    return results


def _world_point(entity, occ):
    """The entity's position in root (world) space via its occurrence proxy."""
    try:
        proxy = entity.createForAssemblyContext(occ)
        construction_point = adsk.fusion.ConstructionPoint.cast(proxy)
        if construction_point:
            return construction_point.geometry
        sketch_point = adsk.fusion.SketchPoint.cast(proxy)
        if sketch_point:
            return sketch_point.worldGeometry
    except Exception:
        ptutil.log(f"{CMD_NAME}: world position unavailable for a wire point.")
    return None


def _occ_path(occ) -> str:
    """Unique identity for an occurrence (used to reject picking it twice)."""
    try:
        return occ.fullPathName or occ.name
    except Exception:
        return occ.name


# ---------------------------------------------------------------------------
# Dropdowns, info, status, preview
# ---------------------------------------------------------------------------
def _clear_list_items(dropdown):
    """Empty a dropdown (ListItems has no documented clear; delete items)."""
    while dropdown.listItems.count > 0:
        dropdown.listItems.item(0).deleteMe()


def _sorted_pins(wires: dict) -> list:
    """Pins sorted numerically when possible, then lexically."""
    return sorted(
        wires.keys(),
        key=lambda pin: (0, int(pin), "") if pin.isdigit() else (1, 0, pin),
    )


def _rebuild_pin_dropdown(side: int):
    global _loading
    dropdown = _ui_refs.get(SIDE_PIN_KEYS[side])
    if dropdown is None:
        return
    _loading = True
    try:
        _clear_list_items(dropdown)
        data = _sides[side]
        if data and data["wires"]:
            for index, pin in enumerate(_sorted_pins(data["wires"])):
                dropdown.listItems.add(pin, index == 0)
    finally:
        _loading = False


def _rebuild_awg_dropdown():
    global _loading
    dropdown = _ui_refs.get("awg")
    if dropdown is None:
        return
    wire_a, wire_b = _selected_wire(0), _selected_wire(1)
    _loading = True
    try:
        _clear_list_items(dropdown)
        if wire_a and wire_b:
            sizes = logic.awg_overlap(
                (wire_a["awg_min"], wire_a["awg_max"]),
                (wire_b["awg_min"], wire_b["awg_max"]),
            )
            for index, size in enumerate(sizes):
                dropdown.listItems.add(str(size), index == 0)
    finally:
        _loading = False
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


def _as_tuple(point) -> tuple:
    """Point3D -> (x, y, z) for the pure-logic helpers."""
    return (point.x, point.y, point.z)


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
