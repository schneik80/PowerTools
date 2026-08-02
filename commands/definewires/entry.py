# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Define Wires command (attribute prove-out).
#
# Runs on a single-component 3D design (the component IS the connector) and
# lets the user define one or more wires, each anchored to three points:
# conductor start, strip length, and connector exit. A point can be picked as
# a sketch point, a work point, a circular/arc sketch curve (its center sketch
# point is used), or a circular/arc BRep edge (a work point is created at the
# edge center via ConstructionPointInput.setByCenter). On OK the command
# writes the PowerTools.Cable attribute schema onto those points and the root
# component (see docs/arch/Define Wires.md); re-running the command finds the
# attributes with design.findAttributes and rebuilds the whole dialog so the
# set can be modified. A future command will route wires between connectors
# across an assembly by querying the same attribute group.
#
# UI note: Fusion does not allow SelectionCommandInputs inside table cells
# ("Selection and button row command inputs are not supported in a table"),
# so the table holds per-wire summary rows and a per-row Edit button, while a
# "Wire editor" group below the table carries the three selection inputs plus
# pin/gauge values for the wire currently being edited. Editor changes write
# straight into the active wire's record, so switching rows never loses edits.

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Define Wires"
CMD_ID = "PTCB_definewires"
CMD_Description = (
    "Define connector wires on a single-component part: pick conductor start, "
    "strip length, and connector exit points per wire, assign a pin and an AWG "
    "gauge range, and store the set as cable-routing attributes on the points."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Command-input ids.
INPUT_NOTICE = "dw_notice"
INPUT_TABLE = "dw_wire_table"
INPUT_ADD = "dw_add_wire"
INPUT_DEL = "dw_del_wire"
INPUT_EDITOR_GROUP = "dw_editor_group"
INPUT_EDITOR_LABEL = "dw_editor_label"
INPUT_SEL_START = "dw_sel_start"
INPUT_SEL_STRIP = "dw_sel_strip"
INPUT_SEL_EXIT = "dw_sel_exit"
INPUT_PIN = "dw_pin"
INPUT_AWG_MIN = "dw_awg_min"
INPUT_AWG_MAX = "dw_awg_max"
INPUT_CABLE = "dw_sel_cable"

# Per-row cell id prefixes; the suffix is the row's monotonic rid.
ROW_EDIT_PREFIX = "dw_row_edit_"
ROW_PIN_PREFIX = "dw_row_pin_"
ROW_AWG_PREFIX = "dw_row_awg_"
ROW_PTS_PREFIX = "dw_row_pts_"

HEADER_ROW = 0

SEL_INPUT_ROLE = {
    INPUT_SEL_START: logic.ROLE_START,
    INPUT_SEL_STRIP: logic.ROLE_STRIP,
    INPUT_SEL_EXIT: logic.ROLE_EXIT,
}
ROLE_LABELS = {
    logic.ROLE_START: "Conductor start",
    logic.ROLE_STRIP: "Strip length",
    logic.ROLE_EXIT: "Connector exit",
}
# "CircularEdges" covers circles AND arcs; there is no "SketchArcs" filter, so
# "SketchCurves" is used and non-circular curves are rejected in inputChanged.
SELECTION_FILTERS = (
    "CircularEdges",
    "SketchCurves",
    "SketchPoints",
    "ConstructionPoints",
)

local_handlers: list = []

# Dialog state for the open command. All reset in command_destroy and,
# defensively, at the top of command_created.
# rid -> {"wire_id", "pin", "awg_min", "awg_max", "points": {role: entity},
#         "from_attrs", "missing": set of roles needing re-selection}
_wires: dict = {}
_row_order: list = []  # rids in table order (table row = index + 1 for header)
_row_inputs: dict = {}  # rid -> {"edit", "pin", "awg", "pts"} cell input refs
_ui_refs: dict = {}  # long-lived input refs (table, notice, editor widgets)
_active_rid = None  # rid currently loaded in the editor
_deleted_wire_ids: set = set()  # attribute-backed wires the user deleted
_loading_row = False  # reentrancy guard while seeding editor inputs
_row_counter = 0
# Connector-level cable point (multi-conductor cable breakout); required by
# validateInputs when the connector has more than one wire.
_cable_point: dict = {"entity": None}


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
# Command created - preconditions, dialog build, reconstruction
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
        if design.rootComponent.occurrences.count > 0:
            ui.messageBox(
                f"{CMD_NAME} runs on single-component part files only (the "
                "component is the connector).\n\nThis design contains component "
                "occurrences - open the connector part directly and run the "
                "command there.",
                CMD_NAME,
                0,
                2,
            )
            args.command.doExecute(False)
            return

        cmd = args.command
        inputs = cmd.commandInputs

        # 1. Problem notice (hidden unless reconstruction finds missing points).
        notice = inputs.addTextBoxCommandInput(INPUT_NOTICE, "", "", 3, True)
        notice.isFullWidth = True
        notice.isVisible = False
        _ui_refs["notice"] = notice

        # 2. Wire table: Edit | Pin | Gauge | Points, plus Add/Delete toolbar.
        table = adsk.core.TableCommandInput.cast(
            inputs.addTableCommandInput(INPUT_TABLE, "Wires", 4, "2:2:3:3")
        )
        table.minimumVisibleRows = 3
        table.maximumVisibleRows = 10
        table.columnSpacing = 1
        table.hasGrid = True
        _ui_refs["table"] = table
        _add_header_row(inputs, table)

        add_btn = inputs.addBoolValueInput(INPUT_ADD, "Add", False, "", False)
        add_btn.tooltip = "Add a wire."
        del_btn = inputs.addBoolValueInput(INPUT_DEL, "Delete", False, "", False)
        del_btn.tooltip = "Delete the wire currently in the editor."
        table.addToolbarCommandInput(add_btn)
        table.addToolbarCommandInput(del_btn)

        # 3. Wire editor for the active row. Selection inputs cannot live in
        # table cells, so the editor always shows/edits the active wire.
        group = inputs.addGroupCommandInput(INPUT_EDITOR_GROUP, "Wire editor")
        group.isExpanded = True
        group.isEnabledCheckBoxDisplayed = False
        grp = group.children

        label = grp.addTextBoxCommandInput(INPUT_EDITOR_LABEL, "", "", 2, True)
        _ui_refs["label"] = label

        for input_id, role in SEL_INPUT_ROLE.items():
            sel = grp.addSelectionInput(
                input_id,
                ROLE_LABELS[role],
                "Select a circular edge, circular/arc sketch curve, sketch "
                "point, or work point.",
            )
            for filter_name in SELECTION_FILTERS:
                sel.addSelectionFilter(filter_name)
            sel.setSelectionLimits(1, 1)
            _ui_refs[input_id] = sel

        _ui_refs["pin"] = grp.addStringValueInput(INPUT_PIN, "Pin", "")
        _ui_refs["awg_min"] = grp.addIntegerSpinnerCommandInput(
            INPUT_AWG_MIN,
            "Min gauge (AWG)",
            logic.AWG_LOWER_BOUND,
            logic.AWG_UPPER_BOUND,
            1,
            logic.AWG_DEFAULT_MIN,
        )
        _ui_refs["awg_max"] = grp.addIntegerSpinnerCommandInput(
            INPUT_AWG_MAX,
            "Max gauge (AWG)",
            logic.AWG_LOWER_BOUND,
            logic.AWG_UPPER_BOUND,
            1,
            logic.AWG_DEFAULT_MAX,
        )

        # 4. Cable point (last, after the per-wire editor) - where a
        # multi-conductor cable ends at this connector and its wires fan
        # out to the pins. One per connector; required when it has more
        # than one wire (validateInputs enforces it).
        cable_sel = inputs.addSelectionInput(
            INPUT_CABLE,
            "Cable point",
            "Where the cable meets this connector and its wires fan out. "
            "Select a circular edge, circular/arc sketch curve, sketch "
            "point, or work point.",
        )
        for filter_name in SELECTION_FILTERS:
            cable_sel.addSelectionFilter(filter_name)
        cable_sel.setSelectionLimits(0, 1)
        _ui_refs["cable"] = cable_sel

        # 5. Rebuild rows from a previous run's attributes, if any.
        _load_existing_wires(design, inputs, table)
        if not _row_order:
            _add_wire_row(inputs, table)
        _activate_row(_row_order[0])

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
# Input changed - row activation, add/delete, live editor -> row sync
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        if _loading_row:
            return
        inputs = args.inputs
        changed = args.input
        changed_id = changed.id

        if changed_id == INPUT_ADD:
            adsk.core.BoolValueCommandInput.cast(changed).value = False
            rid = _add_wire_row(inputs, _ui_refs.get("table"))
            _activate_row(rid)
            return
        if changed_id == INPUT_DEL:
            adsk.core.BoolValueCommandInput.cast(changed).value = False
            _delete_active_row(inputs)
            return
        if changed_id.startswith(ROW_EDIT_PREFIX):
            adsk.core.BoolValueCommandInput.cast(changed).value = False
            rid = _rid_from_input_id(changed_id, ROW_EDIT_PREFIX)
            if rid in _wires:
                _activate_row(rid)
            return
        if changed_id == INPUT_TABLE:
            # Bonus path only: Fusion does not reliably fire inputChanged on
            # bare table row-selection (the per-row Edit button is the real
            # activation mechanism), but follow it when it does fire.
            table = adsk.core.TableCommandInput.cast(changed)
            row = table.selectedRow
            if HEADER_ROW < row <= len(_row_order):
                _activate_row(_row_order[row - 1])
            return

        if changed_id == INPUT_CABLE:
            _handle_cable_selection_changed(changed)
            return

        wire = _wires.get(_active_rid)
        if wire is None:
            return
        if changed_id in SEL_INPUT_ROLE:
            _handle_selection_changed(changed, SEL_INPUT_ROLE[changed_id], wire)
            return
        if changed_id == INPUT_PIN:
            wire["pin"] = adsk.core.StringValueCommandInput.cast(changed).value
        elif changed_id == INPUT_AWG_MIN:
            wire["awg_min"] = adsk.core.IntegerSpinnerCommandInput.cast(changed).value
        elif changed_id == INPUT_AWG_MAX:
            wire["awg_max"] = adsk.core.IntegerSpinnerCommandInput.cast(changed).value
        else:
            return
        _refresh_row_cells(_active_rid)
        _update_editor_label()
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} inputChanged")


def _handle_selection_changed(changed, role: str, wire: dict):
    """Store or reject the pick for *role* on the active wire."""
    global _loading_row
    sel = adsk.core.SelectionCommandInput.cast(changed)
    if sel.selectionCount == 0:
        wire["points"][role] = None
        _refresh_row_cells(_active_rid)
        _update_editor_label()
        return
    entity = sel.selection(0).entity
    if not _is_supported_point_source(entity):
        # The SketchCurves filter admits lines/splines; clear those picks.
        # Guard the programmatic clearSelection - it re-fires inputChanged.
        _loading_row = True
        try:
            sel.clearSelection()
        finally:
            _loading_row = False
        wire["points"][role] = None
        _refresh_row_cells(_active_rid)
        _update_editor_label(
            "Pick a circular edge, circular/arc sketch curve, sketch point, "
            "or work point."
        )
        return
    wire["points"][role] = entity
    wire["missing"].discard(role)
    _refresh_row_cells(_active_rid)
    _update_editor_label()


def _handle_cable_selection_changed(changed):
    """Store or reject the connector-level cable point pick.

    An EMPTY selection event never erases the stored point: Fusion clears
    selection inputs during focus/visibility churn and re-fires
    inputChanged, and honoring those events wiped the cable point - the
    next OK then silently DELETED the stored attribute. The module state is
    the truth; the input is re-seeded from it. Changing the point is done
    by picking a different one (a max-1 input replaces its selection).
    """
    global _loading_row
    sel = adsk.core.SelectionCommandInput.cast(changed)
    if sel.selectionCount == 0:
        entity = _cable_point.get("entity")
        if entity is None:
            return
        _loading_row = True
        try:
            sel.addSelection(entity)
        except Exception:
            ptutil.log(f"{CMD_NAME}: stored cable point no longer selectable.")
            _cable_point["entity"] = None
        finally:
            _loading_row = False
        return
    entity = sel.selection(0).entity
    if not _is_supported_point_source(entity):
        # Reject the pick but KEEP the stored point (re-seed it like the
        # empty-selection branch above): clearing state here armed silent
        # deletion of the stored cablepoint attribute on the next OK after
        # a stray click. Guard the programmatic clearSelection/addSelection
        # - they re-fire inputChanged.
        stored = _cable_point.get("entity")
        _loading_row = True
        try:
            sel.clearSelection()
            if stored is not None:
                try:
                    sel.addSelection(stored)
                except Exception:
                    ptutil.log(f"{CMD_NAME}: stored cable point not re-seedable.")
                    _cable_point["entity"] = None
        finally:
            _loading_row = False
        _update_editor_label(
            "Pick a circular edge, circular/arc sketch curve, sketch point, "
            "or work point for the cable."
        )
        return
    _cable_point["entity"] = entity
    _update_editor_label()


# ---------------------------------------------------------------------------
# Validate - gate OK until every wire is complete and consistent
# ---------------------------------------------------------------------------
def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        summaries = []
        for rid in _row_order:
            wire = _wires[rid]
            summaries.append(
                {
                    "pin": wire["pin"],
                    "awg_min": wire["awg_min"],
                    "awg_max": wire["awg_max"],
                    "points_set": sum(
                        1 for r in logic.ROLES if wire["points"][r] is not None
                    ),
                }
            )
        problems = logic.validate_wires(summaries)
        if not problems:
            for rid in _row_order:
                wire = _wires[rid]
                tokens = [
                    _point_identity(wire["points"][r])
                    for r in logic.ROLES
                    if wire["points"][r] is not None
                ]
                # Unreadable tokens ("") carry no verdict - they must not
                # collide with each other and falsely block OK.
                tokens = [token for token in tokens if token]
                if len(set(tokens)) != len(tokens):
                    problems.append("Same point used twice in one wire.")
                    break
        if not problems and len(_row_order) > 1:
            # Multi-pin connectors need the cable breakout point.
            if _cable_point.get("entity") is None:
                problems.append("Cable point required for multi-pin connectors.")
        args.areInputsValid = not problems
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} validateInputs")
        args.areInputsValid = False  # fail closed - never enable OK unchecked


# ---------------------------------------------------------------------------
# Execute - resolve points, write/refresh/remove attributes, write manifest
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            return
        root = design.rootComponent

        existing = _read_existing(design)
        state = existing["state"]
        manifest = state["manifest"] or {}
        connector_id = logic.connector_id_for(root.name, manifest.get("connector_id"))

        desired: list = []
        manifest_wires: list = []
        kept_ids: list = []
        created_points = 0
        failures: list = []
        for rid in _row_order:
            fields, created = _write_wire(root, _wires[rid], connector_id, existing)
            created_points += created
            if fields is None:
                failures.append(
                    f"Wire pin '{_wires[rid]['pin']}': could not resolve all "
                    "three points - wire skipped (stored data kept)."
                )
                # A write failure is NOT a deletion: keep the wire's stored
                # attributes and manifest entry so a transient resolution
                # failure never destroys the definition.
                wire_id = _wires[rid].get("wire_id")
                if wire_id and wire_id in state["wires"]:
                    kept_ids.append(wire_id)
                    kept = logic.wire_fields(
                        state["wires"][wire_id],
                        logic.manifest_entry(manifest, wire_id),
                    )
                    manifest_wires.append({"wire_id": wire_id, **kept})
            else:
                desired.append(fields)
                manifest_wires.append(fields)

        diff = logic.diff_wires(
            state["wires"].keys(),
            [fields["wire_id"] for fields in desired] + kept_ids,
            _deleted_wire_ids,
        )
        removed = _delete_removed_attributes(existing, diff["remove"])

        root.attributes.add(
            logic.ATTR_GROUP,
            logic.MANIFEST_NAME,
            logic.build_manifest_payload(connector_id, root.name, manifest_wires),
        )

        cable_note = _write_cable_point(root, connector_id, existing)

        lines = [
            f"Connector: {connector_id}",
            f"Wires written: {len(desired)}",
        ]
        if cable_note:
            lines.append(cable_note)
        if created_points:
            lines.append(f"Work points created: {created_points}")
        if diff["remove"]:
            lines.append(f"Wires removed: {len(diff['remove'])} ({removed} attrs)")
        if existing["unknown_attrs"]:
            lines.append(
                f"Unrecognized cable attributes left untouched: "
                f"{len(existing['unknown_attrs'])}"
            )
        lines.extend(failures)
        ui.messageBox("\n".join(lines), CMD_NAME)

    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _write_wire(root, wire: dict, connector_id: str, existing: dict):
    """Write the three point attributes for one wire.

    Returns:
        ``(fields, created_count)`` where *fields* is the wire's manifest entry
        dict, or None when any point could not be resolved (wire skipped);
        *created_count* is how many work points were created for edge picks.
    """
    wire_id = wire["wire_id"] or logic.new_id()
    wire["wire_id"] = wire_id
    fields = {
        "wire_id": wire_id,
        "pin": wire["pin"].strip(),
        "awg_min": wire["awg_min"],
        "awg_max": wire["awg_max"],
    }
    created = 0
    for role in logic.ROLES:
        entity = wire["points"][role]
        if entity is None:
            return None, created
        point, was_created = _resolve_point(root, entity, fields["pin"], role)
        if point is None:
            return None, created
        if was_created:
            created += 1
        _replace_stale_attr(existing, (wire_id, role), point)
        point.attributes.add(
            logic.ATTR_GROUP,
            logic.point_attr_name(wire_id, role),
            logic.build_point_payload(connector_id, fields, role),
        )
    return fields, created


def _write_cable_point(root, connector_id: str, existing: dict) -> str:
    """Write, move, or remove the connector's cable point attribute.

    Returns a one-line summary note ("" when nothing notable happened).
    """
    old_attr = existing["cable_attr"]
    old_entity = existing["cable_entity"]
    entity = _cable_point.get("entity")
    if entity is None:
        if old_attr is not None:
            try:
                old_attr.deleteMe()
                return "Cable point removed."
            except Exception:
                ptutil.log(f"{CMD_NAME}: could not delete the old cable point.")
        return ""
    point, created = _resolve_point(root, entity, "", logic.ROLE_CABLE)
    if point is None:
        return "Cable point could not be resolved - not written."
    if old_attr is not None and (
        old_entity is None or _entity_token(old_entity) != _entity_token(point)
    ):
        try:
            old_attr.deleteMe()
        except Exception:
            ptutil.log(f"{CMD_NAME}: could not delete the stale cable point.")
    point.attributes.add(
        logic.ATTR_GROUP,
        logic.CABLE_POINT_NAME,
        logic.build_cable_point_payload(connector_id),
    )
    if created:
        return "Cable point written (work point created)."
    return "Cable point written."


def _resolve_point(root, entity, pin: str, role: str):
    """Resolve a user selection to a durable, attributable point entity.

    Sketch and work points pass through unchanged; a circular/arc sketch curve
    contributes its center sketch point; a circular/arc BRep edge gets a new
    work point created at its center.

    Returns:
        ``(point_entity, created)`` - *created* is True only when a work point
        was created here. ``(None, False)`` when resolution failed.
    """
    if adsk.fusion.SketchPoint.cast(entity) or adsk.fusion.ConstructionPoint.cast(
        entity
    ):
        return entity, False

    sketch_curve = adsk.fusion.SketchCircle.cast(entity) or adsk.fusion.SketchArc.cast(
        entity
    )
    if sketch_curve:
        # Sketch circles/arcs already own a durable center sketch point - use
        # it directly instead of creating a redundant work point.
        return sketch_curve.centerSketchPoint, False

    try:
        point_input = root.constructionPoints.createInput()
        if not point_input.setByCenter(entity):
            raise ValueError("setByCenter rejected the selected edge")
        point = root.constructionPoints.add(point_input)
    except Exception:
        ptutil.log(
            f"{CMD_NAME}: work point creation failed for role '{role}':\n"
            f"{traceback.format_exc()}"
        )
        return None, False
    try:
        if role == logic.ROLE_CABLE:
            point.name = "Cable point"
        else:
            point.name = f"Wire {pin or 'unpinned'} {role}"
    except Exception:
        ptutil.log(f"{CMD_NAME}: could not rename work point for role '{role}'.")
    return point, True


def _replace_stale_attr(existing: dict, key: tuple, point):
    """Delete a wire-point attribute now living on a different (or no) entity.

    When the stored attribute already sits on *point* itself nothing is done -
    the subsequent ``attributes.add`` overwrites the same-name attribute in
    place.
    """
    old_attr = existing["attr_objs"].get(key)
    if old_attr is None:
        return
    old_entity = existing["entity_map"].get(key)
    if old_entity is not None and _entity_token(old_entity) == _entity_token(point):
        return
    try:
        old_attr.deleteMe()
    except Exception:
        ptutil.log(f"{CMD_NAME}: could not delete stale attribute for {key}.")


def _delete_removed_attributes(existing: dict, remove_ids: set) -> int:
    """Delete every attribute of wires the user removed.

    Attributes with unrecognized names (``existing["unknown_attrs"]``) are
    deliberately NOT deleted: they may belong to a future schema version or
    a sibling feature, and destroying them here would silently eat that
    data every time this dialog is OK'd.
    """
    removed = 0
    for (wire_id, _role), attribute in existing["attr_objs"].items():
        if wire_id not in remove_ids:
            continue
        try:
            attribute.deleteMe()
            removed += 1
        except Exception:
            ptutil.log(f"{CMD_NAME}: could not delete attribute of wire {wire_id}.")
    return removed


# ---------------------------------------------------------------------------
# Reading and reconstructing prior state
# ---------------------------------------------------------------------------
def _read_existing(design) -> dict:
    """Read every PowerTools.Cable attribute in the design.

    Returns:
        A dict with ``attr_objs`` (``{(wire_id, role): Attribute}``),
        ``entity_map`` (``{(wire_id, role): entity or None}``),
        ``unknown_attrs`` (live Attribute objects whose NAME this build does
        not recognize - reported but never deleted, since they may belong
        to a future schema version), and ``state`` (the
        :func:`logic.group_attributes_into_wires` result).
    """
    attr_objs: dict = {}
    entity_map: dict = {}
    unknown_attrs: list = []
    records: list = []
    cable_attr = None
    cable_entity = None
    try:
        found = design.findAttributes(logic.ATTR_GROUP, "") or []
    except Exception:
        ptutil.log(f"{CMD_NAME}: findAttributes failed:\n{traceback.format_exc()}")
        found = []
    for attribute in found:
        try:
            name = attribute.name
            value = attribute.value
        except Exception:
            ptutil.log(f"{CMD_NAME}: unreadable attribute skipped.")
            continue
        try:
            parent = attribute.parent
        except Exception:
            parent = None  # deleted-entity access can raise instead of None
        records.append((name, value, parent is not None))
        key = logic.parse_point_attr_name(name)
        if key is not None:
            attr_objs[key] = attribute
            entity_map[key] = parent
        elif name == logic.CABLE_POINT_NAME:
            cable_attr = attribute
            cable_entity = parent
        elif name != logic.MANIFEST_NAME:
            unknown_attrs.append(attribute)
    return {
        "attr_objs": attr_objs,
        "entity_map": entity_map,
        "unknown_attrs": unknown_attrs,
        "cable_attr": cable_attr,
        "cable_entity": cable_entity,
        "state": logic.group_attributes_into_wires(records),
    }


def _load_existing_wires(design, inputs, table):
    """Rebuild table rows, cable point, and wire records from attributes."""
    global _loading_row
    existing = _read_existing(design)
    state = existing["state"]

    missing_any = False
    if existing["cable_attr"] is not None:
        if existing["cable_entity"] is not None:
            _cable_point["entity"] = existing["cable_entity"]
            cable_sel = _ui_refs.get("cable")
            if cable_sel is not None:
                _loading_row = True
                try:
                    cable_sel.addSelection(existing["cable_entity"])
                except Exception:
                    ptutil.log(f"{CMD_NAME}: stored cable point not selectable.")
                    _cable_point["entity"] = None
                    missing_any = True
                finally:
                    _loading_row = False
        else:
            # Cable point deleted outside the command - must be re-picked.
            missing_any = True

    if not state["wires"]:
        if missing_any:
            _show_missing_notice()
        return
    for wire_id in logic.ordered_wire_ids(state["manifest"], state["wires"]):
        roles = state["wires"][wire_id]
        fields = logic.wire_fields(
            roles, logic.manifest_entry(state["manifest"], wire_id)
        )
        wire = _new_wire()
        wire["wire_id"] = wire_id
        wire["from_attrs"] = True
        wire["pin"] = fields["pin"]
        wire["awg_min"] = fields["awg_min"]
        wire["awg_max"] = fields["awg_max"]
        for role in logic.ROLES:
            entity = existing["entity_map"].get((wire_id, role))
            if entity is not None:
                wire["points"][role] = entity
            else:
                # Attribute orphaned (point deleted outside the command) or
                # never written - either way the user must re-select.
                wire["missing"].add(role)
                missing_any = True
        _add_wire_row(inputs, table, wire)
    if missing_any:
        _show_missing_notice()


def _show_missing_notice():
    """Unhide the notice about stored points that no longer exist."""
    notice = _ui_refs.get("notice")
    if notice:
        notice.text = (
            "Some stored points no longer exist (deleted outside this "
            "command). Re-select the missing wire points in the rows marked "
            "'missing' (or delete those rows) and re-pick the cable point "
            "if it is empty."
        )
        notice.isVisible = True


# ---------------------------------------------------------------------------
# Table and editor plumbing
# ---------------------------------------------------------------------------
def _new_wire() -> dict:
    """Return a fresh wire record with defaults and no points."""
    return {
        "wire_id": None,
        "pin": "",
        "awg_min": logic.AWG_DEFAULT_MIN,
        "awg_max": logic.AWG_DEFAULT_MAX,
        "points": {role: None for role in logic.ROLES},
        "from_attrs": False,
        "missing": set(),
    }


def _add_header_row(inputs, table):
    """Add the read-only header row as table row 0."""
    for col, header in enumerate(["", "Pin", "Gauge", "Points"]):
        cell = inputs.addStringValueInput(f"dw_hdr_{col}", "", header)
        cell.isReadOnly = True
        table.addCommandInput(cell, HEADER_ROW, col)


def _add_wire_row(inputs, table, wire: dict | None = None) -> int:
    """Append a table row for *wire* (a fresh default wire when None)."""
    global _row_counter
    _row_counter += 1
    rid = _row_counter
    if wire is None:
        wire = _new_wire()
        # Default pin: highest numeric pin so far + 1 ("1" for the first).
        wire["pin"] = logic.next_pin(w["pin"] for w in _wires.values())
    _wires[rid] = wire
    _row_order.append(rid)

    row = table.rowCount
    edit_btn = inputs.addBoolValueInput(
        f"{ROW_EDIT_PREFIX}{rid}", "Edit", False, "", False
    )
    edit_btn.tooltip = "Load this wire into the editor below."
    pin_cell = inputs.addTextBoxCommandInput(f"{ROW_PIN_PREFIX}{rid}", "", "", 1, True)
    awg_cell = inputs.addTextBoxCommandInput(f"{ROW_AWG_PREFIX}{rid}", "", "", 1, True)
    pts_cell = inputs.addTextBoxCommandInput(f"{ROW_PTS_PREFIX}{rid}", "", "", 1, True)
    table.addCommandInput(edit_btn, row, 0)
    table.addCommandInput(pin_cell, row, 1)
    table.addCommandInput(awg_cell, row, 2)
    table.addCommandInput(pts_cell, row, 3)
    _row_inputs[rid] = {
        "edit": edit_btn,
        "pin": pin_cell,
        "awg": awg_cell,
        "pts": pts_cell,
    }
    _refresh_row_cells(rid)
    _update_cable_visibility()
    return rid


def _delete_active_row(inputs):
    """Delete the active wire's row, then activate a neighbor (or a blank)."""
    rid = _active_rid
    if rid is None or rid not in _wires:
        return
    wire = _wires.pop(rid)
    if wire["from_attrs"] and wire["wire_id"]:
        _deleted_wire_ids.add(wire["wire_id"])
    index = _row_order.index(rid)
    _row_order.remove(rid)
    _row_inputs.pop(rid, None)
    table = _ui_refs.get("table")
    if table:
        table.deleteRow(index + 1)  # +1 for the header row
    if _row_order:
        _activate_row(_row_order[max(0, index - 1)])
    else:
        _activate_row(_add_wire_row(inputs, table))
    _update_cable_visibility()


def _update_cable_visibility():
    """Show the single, connector-level cable point only when relevant.

    Hidden for a one-wire connector (no cable to break out) unless a cable
    point is already set, so it can still be reviewed or cleared.
    """
    cable_sel = _ui_refs.get("cable")
    if cable_sel is None:
        return
    cable_sel.isVisible = len(_row_order) > 1 or _cable_point.get("entity") is not None


def _activate_row(rid):
    """Load wire *rid* into the editor (selections, pin, gauges, label)."""
    global _active_rid, _loading_row
    wire = _wires.get(rid)
    if wire is None:
        return
    _active_rid = rid
    _loading_row = True
    try:
        # Focus the first editor input so the user's next canvas pick goes
        # to THIS wire's conductor start. Without this, Fusion's focus
        # auto-advance can wrap into the (single, connector-level) cable
        # point input after a wire's third pick, making every wire appear
        # to demand a cable point. Set before seeding in case focusing
        # resets the input's selection.
        start_input = _ui_refs.get(INPUT_SEL_START)
        if start_input is not None:
            try:
                start_input.hasFocus = True
            except Exception:
                ptutil.log(f"{CMD_NAME}: could not focus the start input.")
        for input_id, role in SEL_INPUT_ROLE.items():
            sel = _ui_refs.get(input_id)
            if sel is None:
                continue
            sel.clearSelection()
            entity = wire["points"][role]
            if entity is None:
                continue
            try:
                sel.addSelection(entity)
            except Exception:
                # Entity died since it was stored - demote to missing.
                ptutil.log(f"{CMD_NAME}: stored {role} point no longer selectable.")
                wire["points"][role] = None
                wire["missing"].add(role)
        pin_input = _ui_refs.get("pin")
        if pin_input:
            pin_input.value = wire["pin"]
        for key, field in (("awg_min", "awg_min"), ("awg_max", "awg_max")):
            spinner = _ui_refs.get(key)
            if spinner:
                spinner.value = wire[field]
        _refresh_row_cells(rid)
        _update_editor_label()
    finally:
        _loading_row = False


def _refresh_row_cells(rid):
    """Sync one table row's summary cells from its wire record."""
    wire = _wires.get(rid)
    cells = _row_inputs.get(rid)
    if not wire or not cells:
        return
    cells["pin"].text = wire["pin"].strip() or "-"
    cells["awg"].text = f"{wire['awg_min']}-{wire['awg_max']} AWG"
    points_set = sum(1 for r in logic.ROLES if wire["points"][r] is not None)
    status = f"{points_set}/{len(logic.ROLES)} points"
    if wire["missing"]:
        status += " - missing"
    cells["pts"].text = status


def _update_editor_label(hint: str = ""):
    """Refresh the editor caption for the active wire (optionally with *hint*)."""
    label = _ui_refs.get("label")
    if label is None:
        return
    wire = _wires.get(_active_rid)
    if wire is None:
        label.text = "No wire selected."
        return
    pin = wire["pin"].strip()
    text = f"Editing wire: pin {pin}" if pin else "Editing new wire"
    if wire["missing"]:
        text += " (re-select its missing points)"
    label.text = f"{text}\n{hint}" if hint else text


def _is_supported_point_source(entity) -> bool:
    """True when *entity* can yield a durable wire point (see _resolve_point)."""
    if adsk.fusion.SketchPoint.cast(entity) or adsk.fusion.ConstructionPoint.cast(
        entity
    ):
        return True
    if adsk.fusion.SketchCircle.cast(entity) or adsk.fusion.SketchArc.cast(entity):
        return True
    edge = adsk.fusion.BRepEdge.cast(entity)
    if edge:
        try:
            geometry = edge.geometry
        except Exception:
            return False
        return bool(adsk.core.Circle3D.cast(geometry) or adsk.core.Arc3D.cast(geometry))
    return False


def _entity_token(entity) -> str:
    """Return the entity's token, or "" when unavailable."""
    if entity is None:
        return ""
    try:
        return entity.entityToken or ""
    except Exception:
        return ""


def _point_identity(entity) -> str:
    """Validation identity token for a picked point source.

    Sketch circles/arcs resolve to their CENTER sketch point at execute
    time (see :func:`_resolve_point`), so validation compares that center -
    picking a circle and its own center point IS the same point twice.
    """
    curve = adsk.fusion.SketchCircle.cast(entity) or adsk.fusion.SketchArc.cast(entity)
    if curve is not None:
        try:
            return _entity_token(curve.centerSketchPoint)
        except Exception:
            return _entity_token(entity)
    return _entity_token(entity)


def _rid_from_input_id(input_id: str, prefix: str):
    """Parse the rid suffix from a per-row input id; None when malformed."""
    try:
        return int(input_id[len(prefix) :])
    except ValueError:
        return None


def _reset_state():
    """Reset all per-dialog module state."""
    global _wires, _row_order, _row_inputs, _ui_refs, _active_rid
    global _deleted_wire_ids, _loading_row, _row_counter, _cable_point
    _wires = {}
    _row_order = []
    _row_inputs = {}
    _ui_refs = {}
    _active_rid = None
    _deleted_wire_ids = set()
    _loading_row = False
    _row_counter = 0
    _cable_point = {"entity": None}


# ---------------------------------------------------------------------------
# Destroy - release references and reset state
# ---------------------------------------------------------------------------
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    _reset_state()
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
