# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Update Wire command (attribute prove-out, part 3).
#
# Recovery path for routed wires: when a connector was moved in a way the
# associative links could not follow, or was swapped/edited so the links
# broke, this command rebuilds the wire from its stored route attribute.
#
# The dialog lists every routed wire found at the design root (components
# stamped with the PowerTools.Cable "route" attribute). For the chosen wire
# each end is resolved back to a connector occurrence - by the stored
# occurrence entity token first (survives renames and disambiguates multiple
# instances of the same connector), then by unique connector id (survives a
# dead token after reinsertion) - and the wire record is found by wire id
# with a pin fallback. On OK the old wire (its "Wire <name>" timeline group,
# or failing that its occurrence) is deleted and the wire is rebuilt with
# builder.build_wire using the stored name, gauge, and diameter, creating
# fresh associative links to wherever the connectors are now.

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..routewire import builder
from ..routewire import logic as route_logic
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Update Wire"
CMD_ID = "PTCB_updatewire"
CMD_Description = (
    "Rebuild a routed wire from its stored route data: re-resolve both "
    "connectors, delete the old wire assembly, and route it again with the "
    "same name, gauge, and diameter."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Command-input ids.
INPUT_WIRE = "uw_wire"
INPUT_INFO = "uw_info"

local_handlers: list = []

# Dialog state for the open command. All reset in command_destroy and,
# defensively, at the top of command_created.
_ui_refs: dict = {}
_routes: list = []  # [{"occ", "payload", "label"}] routed wires at the root
_resolution = None  # result of _resolve_route for the selected wire
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
            ui.messageBox(f"{CMD_NAME} requires a parametric design.", CMD_NAME, 0, 2)
            args.command.doExecute(False)
            return

        global _routes
        _routes = _collect_routes(design)
        if not _routes:
            ui.messageBox(
                "No routed wires were found in this design.\n\nRoute Wire "
                "stamps each wire assembly it builds; run it first.",
                CMD_NAME,
                0,
                2,
            )
            args.command.doExecute(False)
            return

        cmd = args.command
        cmd.okButtonText = "Rebuild"
        inputs = cmd.commandInputs

        wire_dd = inputs.addDropDownCommandInput(
            INPUT_WIRE, "Wire", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        for index, route in enumerate(_routes):
            wire_dd.listItems.add(route["label"], index == 0)
        _ui_refs["wire"] = wire_dd

        info = inputs.addTextBoxCommandInput(INPUT_INFO, "", "", 6, True)
        info.isFullWidth = True
        _ui_refs["info"] = info

        global _resolution
        _resolution = _resolve_route(design, _routes[0])
        _update_info()

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
# Input changed / validate
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    global _loading, _resolution
    try:
        if _loading:
            return
        if args.input.id != INPUT_WIRE:
            return
        _loading = True
        try:
            design = adsk.fusion.Design.cast(app.activeProduct)
            route = _selected_route()
            _resolution = _resolve_route(design, route) if design and route else None
            _update_info()
        finally:
            _loading = False
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} inputChanged")


def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        args.areInputsValid = bool(
            _resolution
            and not _resolution["problems"]
            and len(_resolution["ends"]) == 2
        )
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} validateInputs")
        args.areInputsValid = True  # fail-open so the user is never stuck


# ---------------------------------------------------------------------------
# Execute - delete the old wire, rebuild from the stored route
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        route = _selected_route()
        if design is None or route is None:
            ui.messageBox(f"{CMD_NAME}: nothing to rebuild.", CMD_NAME, 0, 2)
            return

        resolution = _resolve_route(design, route)  # fresh, not dialog-cached
        if resolution["problems"] or len(resolution["ends"]) != 2:
            ui.messageBox(
                f"{CMD_NAME}: the route could not be resolved:\n\n"
                + "\n".join(resolution["problems"] or ["Unknown resolution error."]),
                CMD_NAME,
                0,
                2,
            )
            return

        if not _delete_wire(route["occ"]):
            ui.messageBox(
                f"{CMD_NAME}: the existing wire assembly could not be deleted "
                "- nothing was changed. Delete its timeline group manually "
                "and use Route Wire instead.",
                CMD_NAME,
                0,
                2,
            )
            return

        params = resolution["params"]
        result = builder.build_wire(design, tuple(resolution["ends"]), params)

        summary = (
            f"Wire {params['name']} rebuilt.\n\n"
            + "\n".join(
                f"Pin {pin}: {comp_name} (matched by "
                f"{'entity token' if how == logic.HOW_TOKEN else 'connector id'})"
                for comp_name, pin, how in resolution["hows"]
            )
            + f"\nGauge: {params['awg']} AWG, "
            f"diameter {params['od_mm']:.3f} mm."
        )
        if result["spline_fallback"]:
            summary += (
                "\n\nNote: tangency constraints could not be applied - the "
                "spline was shaped with guide points instead."
            )
        if result["baked_points"]:
            summary += (
                f"\n\nNote: {result['baked_points']} point(s) could not be "
                "linked to the connector geometry and were baked at fixed "
                "positions."
            )
        ui.messageBox(summary, CMD_NAME)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _delete_wire(occ) -> bool:
    """Delete the wire assembly: its timeline group when present, else the
    occurrence (which removes the components, sketches, and features)."""
    group = None
    try:
        timeline_object = occ.timelineObject
        group = timeline_object.parentGroup if timeline_object else None
    except Exception:
        ptutil.log(f"{CMD_NAME}: wire timeline group lookup failed.")
    if group is not None:
        try:
            if group.deleteMe(True):
                return True
        except Exception:
            ptutil.log(
                f"{CMD_NAME}: timeline group delete failed:\n{traceback.format_exc()}"
            )
    try:
        return bool(occ.deleteMe())
    except Exception:
        ptutil.log(f"{CMD_NAME}: occurrence delete failed:\n{traceback.format_exc()}")
    return False


# ---------------------------------------------------------------------------
# Route collection and resolution
# ---------------------------------------------------------------------------
def _collect_routes(design) -> list:
    """Routed wires at the design root, labeled for the dropdown."""
    routes = builder.collect_routes(design)
    used = set()
    for route in routes:
        base = str(route["payload"].get("name") or "unnamed")
        label = f"Wire {base}"
        suffix = 2
        while label in used:
            label = f"Wire {base} ({suffix})"
            suffix += 1
        used.add(label)
        route["label"] = label
    return routes


def _resolve_route(design, route) -> dict:
    """Resolve a stored route back to live connector data.

    Returns ``{"ends": [(side_data, wire), ...], "params": dict | None,
    "hows": [(comp_name, pin, how)], "problems": [str]}`` - empty problems
    and two ends means the wire is rebuildable.
    """
    payload = route["payload"]
    problems: list = []
    if payload.get("kind", route_logic.KIND_SINGLE) != route_logic.KIND_SINGLE:
        return {
            "ends": [],
            "params": None,
            "hows": [],
            "problems": [
                "Cable routes cannot be updated yet - delete the cable's "
                "timeline group and re-route it with Route Wire."
            ],
        }
    params = logic.coerce_route_params(payload)
    if params is None:
        problems.append("Stored route data is damaged (name/gauge/diameter).")

    ends_payload = payload.get("ends") or []
    if len(ends_payload) != 2:
        problems.append("Stored route data does not describe two ends.")
        ends_payload = []

    # Candidate occurrences: everything except the wire assembly's own tree.
    wire_path = builder.occ_path(route["occ"])
    candidate_occs: list = []
    candidates: list = []
    all_occs = design.rootComponent.allOccurrences
    for index in range(all_occs.count):
        occ = all_occs.item(index)
        path = builder.occ_path(occ)
        if path == wire_path or path.startswith(wire_path + "+"):
            continue
        candidate_occs.append(occ)
        candidates.append(
            {
                "token": builder.entity_token(occ),
                "connector_id": builder.component_connector_id(occ.component),
            }
        )

    ends: list = []
    hows: list = []
    used_paths: set = set()
    for end in ends_payload:
        pin = str(end.get("pin") or "?")
        index, how = logic.choose_end_occurrence(candidates, end)
        if index is None:
            if how == logic.REASON_AMBIGUOUS:
                problems.append(
                    f"Pin {pin}: several instances of that connector exist - "
                    "cannot tell which one this wire used."
                )
            else:
                problems.append(f"Pin {pin}: connector occurrence not found.")
            continue
        occ = candidate_occs[index]
        path = builder.occ_path(occ)
        if path in used_paths:
            problems.append("Both ends resolve to the same occurrence.")
            continue
        used_paths.add(path)
        side = builder.read_connector(occ)
        if side["error"]:
            problems.append(f"Pin {pin}: {side['error']}")
            continue
        wire = logic.find_wire(side["wires"], str(end.get("wire_id") or ""), pin)
        if wire is None:
            problems.append(
                f"Pin {pin}: wire no longer defined on '{side['comp_name']}'."
            )
            continue
        ends.append((side, wire))
        hows.append((side["comp_name"], pin, how))

    if len(ends) != 2 and not problems:
        problems.append("Could not resolve both ends of the route.")
    return {"ends": ends, "params": params, "hows": hows, "problems": problems}


# ---------------------------------------------------------------------------
# Dialog helpers
# ---------------------------------------------------------------------------
def _selected_route():
    """The route record for the dropdown's selected wire, or None."""
    dropdown = _ui_refs.get("wire")
    selected = dropdown.selectedItem if dropdown else None
    if selected is None:
        return None
    for route in _routes:
        if route["label"] == selected.name:
            return route
    return None


def _update_info():
    info = _ui_refs.get("info")
    if info is None:
        return
    route = _selected_route()
    if route is None or _resolution is None:
        info.text = "Select a wire to rebuild."
        return
    lines = []
    params = _resolution["params"]
    if params:
        lines.append(
            f"{route['label']}: {params['awg']} AWG, {params['od_mm']:.2f} mm diameter."
        )
    for comp_name, pin, how in _resolution["hows"]:
        matched = "entity token" if how == logic.HOW_TOKEN else "connector id"
        lines.append(f"Pin {pin}: {comp_name} (matched by {matched})")
    if _resolution["problems"]:
        lines.extend(_resolution["problems"])
        lines.append("This wire cannot be rebuilt until the above is resolved.")
    else:
        lines.append("Ready to rebuild (the old wire assembly is replaced).")
    info.text = "\n".join(lines)


def _reset_state():
    """Reset all per-dialog module state."""
    global _ui_refs, _routes, _resolution, _loading
    _ui_refs = {}
    _routes = []
    _resolution = None
    _loading = False


# ---------------------------------------------------------------------------
# Destroy - release references and reset state
# ---------------------------------------------------------------------------
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    _reset_state()
    ptutil.log(f"{CMD_NAME} Command Destroy Event")
