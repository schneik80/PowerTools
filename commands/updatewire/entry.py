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
# The dialog lists every routed assembly found at the design root
# (components stamped with the PowerTools.Cable "route" attribute) - single
# wires AND multi-conductor cables. For the chosen route each end is
# resolved back to a connector occurrence - by the stored occurrence entity
# token first (survives renames and disambiguates multiple instances of the
# same connector), then by unique connector id (survives a dead token after
# reinsertion). Wires are found by wire id with a pin fallback; for cables
# the stored ordered pin/wire-id lists reconstruct the original pairing
# (surviving pin renames), and both connectors must still carry their cable
# points. On OK the old assembly (its timeline group, or failing that its
# occurrence) is deleted and rebuilt with builder.build_wire / build_cable
# using the stored name, gauge, and diameters, creating fresh associative
# links to wherever the connectors are now.

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..cable_shared import builder
from ..cable_shared import routing as route_logic
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Update Wire"
CMD_ID = "PTCB_updatewire"
CMD_Description = (
    "Rebuild a routed wire or cable from its stored route data: re-resolve "
    "both connectors, delete the old assembly, and route it again with the "
    "same name, gauge, and diameters."
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
        args.areInputsValid = False  # fail closed - never enable OK unchecked


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

        params = resolution["params"]
        is_cable = resolution["kind"] == route_logic.KIND_CABLE
        group_label = f"{'Cable' if is_cable else 'Wire'} {params['name']}"
        if not _delete_wire(route["occ"], group_label):
            ui.messageBox(
                f"{CMD_NAME}: the existing assembly could not be deleted "
                "- nothing was changed. Delete its timeline group manually "
                "and use Route Wire instead.",
                CMD_NAME,
                0,
                2,
            )
            return

        if is_cable:
            result = builder.build_cable(design, tuple(resolution["ends"]), params)
            wire_count = len(resolution["ends"][0][1])
            headline = f"Cable {params['name']} rebuilt ({wire_count} wires).\n\n"
            sizes = (
                f"\nGauge: {params['awg']} AWG, wire {params['od_mm']:.3f} mm, "
                f"cable {params['cable_od_mm']:.3f} mm."
            )
        else:
            result = builder.build_wire(design, tuple(resolution["ends"]), params)
            headline = f"Wire {params['name']} rebuilt.\n\n"
            sizes = f"\nGauge: {params['awg']} AWG, diameter {params['od_mm']:.3f} mm."

        summary = (
            headline
            + "\n".join(
                f"{label}: {comp_name} (matched by "
                f"{'entity token' if how == logic.HOW_TOKEN else 'connector id'})"
                for comp_name, label, how in resolution["hows"]
            )
            + sizes
        )
        ui.messageBox(summary + route_logic.result_notes(result), CMD_NAME)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _delete_wire(occ, expected_group: str) -> bool:
    """Delete the wire assembly: its OWN timeline group when present, else
    the occurrence (which removes the components, sketches, and features).

    The parent group is deleted with contents only when its name still
    matches the builder's label for this route. Build-time grouping can
    fail silently, and a user may later have grouped the occurrence with
    unrelated features - a name mismatch means the group is not ours, and
    deleting it wholesale would destroy those features.
    """
    group = None
    try:
        timeline_object = occ.timelineObject
        group = timeline_object.parentGroup if timeline_object else None
    except Exception:
        ptutil.log(f"{CMD_NAME}: wire timeline group lookup failed.")
    if group is not None:
        group_name = ""
        try:
            group_name = group.name or ""
        except Exception:
            ptutil.log(f"{CMD_NAME}: timeline group name read failed.")
        if group_name == expected_group:
            try:
                if group.deleteMe(True):
                    return True
            except Exception:
                ptutil.log(
                    f"{CMD_NAME}: timeline group delete failed:\n"
                    f"{traceback.format_exc()}"
                )
        else:
            ptutil.log(
                f"{CMD_NAME}: timeline group '{group_name}' does not match "
                f"'{expected_group}' - deleting only the occurrence."
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
    """Routed assemblies at the design root, labeled for the dropdown."""
    routes = builder.collect_routes(design)
    used = set()
    for route in routes:
        payload = route["payload"]
        base = str(payload.get("name") or "unnamed")
        kind = payload.get("kind", route_logic.KIND_SINGLE)
        prefix = "Cable" if kind == route_logic.KIND_CABLE else "Wire"
        label = f"{prefix} {base}"
        suffix = 2
        while label in used:
            label = f"{prefix} {base} ({suffix})"
            suffix += 1
        used.add(label)
        route["label"] = label
    return routes


def _resolve_route(design, route) -> dict:
    """Resolve a stored route back to live connector data.

    Returns ``{"kind": str, "ends": [...], "params": dict | None,
    "hows": [(comp_name, label, how)], "problems": [str]}`` - empty
    problems and two ends means the route is rebuildable. For single
    routes each end is ``(side_data, wire)``; for cable routes each end is
    ``(side_data, [wire, ...])`` in the stored (paired) order.
    """
    payload = route["payload"]
    kind = payload.get("kind", route_logic.KIND_SINGLE)
    problems: list = []
    if kind not in (route_logic.KIND_SINGLE, route_logic.KIND_CABLE):
        return {
            "kind": kind,
            "ends": [],
            "params": None,
            "hows": [],
            "problems": [
                f"Routes of type '{kind}' cannot be rebuilt - delete the "
                "timeline group and re-route with Route Wire."
            ],
        }
    params = logic.coerce_route_params(payload)
    if params is None:
        problems.append("Stored route data is damaged (name/gauge/diameter).")
    elif kind == route_logic.KIND_CABLE:
        cable_od_mm = logic.coerce_cable_od_mm(payload)
        if cable_od_mm is None:
            problems.append("Stored route data is damaged (cable diameter).")
        else:
            params["cable_od_mm"] = cable_od_mm
        # Rebuild with the original wire colors when stored (normalized;
        # the builder re-assigns from the palette on a count mismatch).
        stored_colors = payload.get("colors")
        if isinstance(stored_colors, list) and stored_colors:
            params["colors"] = [
                route_logic.normalize_wire_color(color) for color in stored_colors
            ]
    else:
        params["color"] = route_logic.normalize_wire_color(payload.get("color"))

    ends_payload = payload.get("ends") or []
    if len(ends_payload) != 2:
        problems.append("Stored route data does not describe two ends.")
        ends_payload = []

    # Candidate occurrences: everything except the route assembly's own tree.
    route_path = builder.occ_path(route["occ"])
    candidate_occs: list = []
    candidate_paths: list = []
    candidates: list = []
    all_occs = design.rootComponent.allOccurrences
    for index in range(all_occs.count):
        occ = all_occs.item(index)
        path = builder.occ_path(occ)
        if path == route_path or path.startswith(route_path + "+"):
            continue
        candidate_occs.append(occ)
        candidate_paths.append(path)
        candidates.append(
            {
                "token_match": False,
                "connector_id": builder.component_connector_id(occ.component),
            }
        )

    ends: list = []
    hows: list = []
    used_paths: set = set()
    for end in ends_payload:
        label = _end_label(end, kind)
        _mark_token_matches(design, candidates, candidate_paths, end)
        index, how = logic.choose_end_occurrence(candidates, end)
        if index is None:
            if how == logic.REASON_AMBIGUOUS:
                problems.append(
                    f"{label}: several instances of that connector exist - "
                    "cannot tell which one this route used."
                )
            else:
                problems.append(f"{label}: connector occurrence not found.")
            continue
        occ = candidate_occs[index]
        path = builder.occ_path(occ)
        if path in used_paths:
            problems.append("Both ends resolve to the same occurrence.")
            continue
        used_paths.add(path)
        side = builder.read_connector(occ)
        if side["error"]:
            problems.append(f"{label}: {side['error']}")
            continue
        if kind == route_logic.KIND_CABLE:
            if side["cable"] is None:
                problems.append(
                    f"{label}: '{side['comp_name']}' has no cable point - "
                    "re-run Define Wires on the connector part."
                )
                continue
            records, missing = logic.match_cable_wires(
                side["wires"], end.get("wire_ids"), end.get("pins")
            )
            if missing:
                problems.append(
                    f"{label}: wire(s) {', '.join(missing)} no longer "
                    f"defined on '{side['comp_name']}'."
                )
                continue
            ends.append((side, records))
        else:
            wire = logic.find_wire(
                side["wires"],
                str(end.get("wire_id") or ""),
                str(end.get("pin") or ""),
            )
            if wire is None:
                problems.append(
                    f"{label}: wire no longer defined on '{side['comp_name']}'."
                )
                continue
            ends.append((side, wire))
        hows.append((side["comp_name"], label, how))

    if kind == route_logic.KIND_CABLE and len(ends) == 2:
        count_a, count_b = len(ends[0][1]), len(ends[1][1])
        if count_a != count_b or count_a == 0:
            problems.append(
                f"Resolved wire counts differ ({count_a} vs {count_b}) - "
                "cable pairing cannot be reconstructed."
            )
    if len(ends) != 2 and not problems:
        problems.append("Could not resolve both ends of the route.")
    return {
        "kind": kind,
        "ends": ends,
        "params": params,
        "hows": hows,
        "problems": problems,
    }


def _mark_token_matches(design, candidates: list, paths: list, end: dict):
    """Flag the candidates that one end's stored occurrence token resolves to.

    Tokens are resolved through ``Design.findEntityByToken`` - NEVER by
    comparing token strings, which the Fusion API documents as invalid (the
    same entity can return different token strings over time). Resolved
    occurrences are matched to candidates by their occurrence path, both
    read at this same instant.
    """
    for candidate in candidates:
        candidate["token_match"] = False
    token = str(end.get("occ_token") or "")
    if not token:
        return
    try:
        entities = design.findEntityByToken(token) or []
    except Exception:
        ptutil.log(f"{CMD_NAME}: findEntityByToken failed for a stored token.")
        return
    for entity in entities:
        occ = adsk.fusion.Occurrence.cast(entity)
        if occ is None:
            continue
        path = builder.occ_path(occ)
        for index, candidate_path in enumerate(paths):
            if candidate_path == path:
                candidates[index]["token_match"] = True


def _end_label(end: dict, kind: str) -> str:
    """Display label for one stored route end ("Pin 4" / "Pins 1, 2, 3")."""
    if kind == route_logic.KIND_CABLE:
        pins = ", ".join(str(pin) for pin in end.get("pins") or [])
        return f"Pins {pins}" if pins else "Pins ?"
    return f"Pin {end.get('pin') or '?'}"


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
        info.text = "Select a route to rebuild."
        return
    lines = []
    params = _resolution["params"]
    if params:
        spec = f"{route['label']}: {params['awg']} AWG, {params['od_mm']:.2f} mm"
        if params.get("cable_od_mm"):
            spec += f" wires, {params['cable_od_mm']:.2f} mm cable"
        if params.get("color"):
            spec += f", {params['color']}"
        lines.append(spec + ".")
    for comp_name, label, how in _resolution["hows"]:
        matched = "entity token" if how == logic.HOW_TOKEN else "connector id"
        lines.append(f"{label}: {comp_name} (matched by {matched})")
    if _resolution["problems"]:
        lines.extend(_resolution["problems"])
        lines.append("This route cannot be rebuilt until the above is resolved.")
    else:
        lines.append("Ready to rebuild (the old assembly is replaced).")
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
