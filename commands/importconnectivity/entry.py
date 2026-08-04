# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Cable - Import Connectivity command (attribute prove-out, part 7).
#
# Reads an edited connectivity wire list (the CSV written by Export
# Connectivity) and builds every wire and cable it defines, batch-driving
# cable_shared.builder - the same construction Route Wire uses, including
# associative includes, colors, member stamps, and route attributes.
#
# The import is ADDITIVE and tolerant: a row whose endpoints match an
# already-routed connection is skipped and counted, invalid rows or cable
# groups are reported and skipped (never blocking the rest of the file),
# and nothing is ever deleted. Connectors are identified by their
# reference designators (Assign Designators); existing routes resolve
# through the Update Wire ladder (findEntityByToken, never token-string
# comparison). Cable rows pair pins ROW BY ROW - richer than Route Wire's
# sorted pairing. Progress uses the non-modal status-bar progress bar (the
# modal ProgressDialog intercepts events during API churn).

import os
import traceback

import adsk.core
import adsk.fusion

from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..cable_shared import builder, connectivity
from ..cable_shared import routing as route_logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Import Connectivity"
CMD_ID = "PTCB_importconnectivity"
CMD_Description = (
    "Read a connectivity wire list (CSV) and build every wire and "
    "multi-conductor cable it defines between the assembly's designated "
    "connectors. Additive: existing routes are skipped, never changed."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

MAX_REPORTED_PROBLEMS = 12

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
# Execute - parse, resolve, preflight, build
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            ui.messageBox(
                f"{CMD_NAME} requires an active Fusion 3D design.", CMD_NAME, 0, 2
            )
            return
        if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            ui.messageBox(f"{CMD_NAME} requires a parametric design.", CMD_NAME, 0, 2)
            return

        path = _ask_open_path()
        if not path:
            return
        # utf-8-sig eats the BOM Excel prepends when saving CSV.
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()

        parsed = connectivity.parse_wire_list(text)
        problems: list = list(parsed["problems"])
        groups = parsed["groups"]
        if not groups:
            _show_summary(0, 0, 0, problems, None)
            return

        connectors = builder.connector_occurrences(design)
        designators = _designator_map(connectors, problems)
        existing_keys = _existing_route_keys(design, connectors)
        side_cache: dict = {}

        built_wires = 0
        built_cables = 0
        skipped_existing = 0
        aggregate = {"spline_fallback": False, "baked_points": 0, "dropped_tangents": 0}

        progress = ui.progressBar
        try:
            progress.show(
                f"{CMD_NAME}: building %v of %m route(s)...", 0, max(len(groups), 1)
            )
        except Exception:
            pass  # best-effort; never fail the run over progress UI
        try:
            for index, group in enumerate(groups):
                try:
                    progress.progressValue = index
                except Exception:
                    pass
                outcome = _build_group(
                    design, group, designators, existing_keys, side_cache, problems
                )
                if outcome == "existing":
                    skipped_existing += 1
                elif isinstance(outcome, dict):
                    _merge_result(aggregate, outcome)
                    if group["kind"] == "cable":
                        built_cables += 1
                    else:
                        built_wires += 1
                adsk.doEvents()
        finally:
            try:
                progress.hide()
            except Exception:
                pass

        _show_summary(built_wires, built_cables, skipped_existing, problems, aggregate)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


def _build_group(design, group, designators, existing_keys, side_cache, problems):
    """Build one parsed group.

    Returns the builder result dict on success, ``"existing"`` when the
    group is already routed, or None (with a problem appended) when it
    cannot be built.
    """
    label = f"{'Cable' if group['kind'] == 'cable' else 'Wire'} '{group['name']}'"
    if group["kind"] == "cable":
        refs = list(group["from_refs"]) + list(group["to_refs"])
    else:
        refs = [group["from_ref"], group["to_ref"]]
    sides_by_ref: dict = {}
    for ref in refs:
        occ = designators.get(ref.strip().lower())
        if occ is None:
            problems.append(f"{label}: no connector has the designator '{ref}'.")
            return None
        side = _side_data(occ, side_cache)
        if side["error"]:
            problems.append(f"{label}: connector '{ref}': {side['error']}")
            return None
        sides_by_ref[ref.strip().lower()] = side

    if group["kind"] == "cable":
        return _build_cable_group(
            design, group, sides_by_ref, existing_keys, problems, label
        )
    sides = [sides_by_ref[ref.strip().lower()] for ref in refs]
    return _build_single_group(design, group, sides, existing_keys, problems, label)


def _build_single_group(design, group, sides, existing_keys, problems, label):
    """Preflight and build one single-wire group."""
    if group["key"] in existing_keys:
        return "existing"
    side_a, side_b = sides
    wire_a = _pin_wire(side_a, group["from_ref"], group["from_pin"], problems, label)
    wire_b = _pin_wire(side_b, group["to_ref"], group["to_pin"], problems, label)
    if wire_a is None or wire_b is None:
        return None
    if not _gauge_ok((wire_a, wire_b), group["awg"], problems, label):
        return None
    result = builder.build_wire(
        design,
        ((side_a, wire_a), (side_b, wire_b)),
        {
            "name": group["name"],
            "awg": group["awg"],
            "od_mm": group["od_mm"],
            "color": group["color"],
        },
    )
    existing_keys.add(group["key"])
    return result


def _build_cable_group(design, group, sides_by_ref, existing_keys, problems, label):
    """Preflight and build one cable group (its ends may span connectors)."""
    matched = [key in existing_keys for key in group["keys"]]
    if all(matched):
        return "existing"
    if any(matched):
        problems.append(
            f"{label}: some of its wires are already routed - resolve the "
            "overlap manually (nothing was built)."
        )
        return None
    for ref in list(group["from_refs"]) + list(group["to_refs"]):
        if sides_by_ref[ref.strip().lower()]["cable"] is None:
            problems.append(
                f"{label}: connector '{ref}' has no cable point - re-run "
                "Define Wires on the part."
            )
            return None
    end_a = []
    end_b = []
    for wire in group["wires"]:
        side_a = sides_by_ref[wire["from_ref"].strip().lower()]
        side_b = sides_by_ref[wire["to_ref"].strip().lower()]
        wire_a = _pin_wire(side_a, wire["from_ref"], wire["from_pin"], problems, label)
        wire_b = _pin_wire(side_b, wire["to_ref"], wire["to_pin"], problems, label)
        if wire_a is None or wire_b is None:
            return None
        end_a.append((side_a, wire_a))
        end_b.append((side_b, wire_b))
    records = [wire for _, wire in end_a] + [wire for _, wire in end_b]
    if not _gauge_ok(records, group["awg"], problems, label):
        return None
    anchors = route_logic.cable_end_anchors(
        [_cable_xyz(sides_by_ref[ref.strip().lower()]) for ref in group["from_refs"]],
        [_cable_xyz(sides_by_ref[ref.strip().lower()]) for ref in group["to_refs"]],
    )
    if anchors["degenerate"]:
        problems.append(f"{label}: the two cable end anchor points coincide.")
        return None
    result = builder.build_cable(
        design,
        (end_a, end_b),
        {
            "name": group["name"],
            "awg": group["awg"],
            "od_mm": group["od_mm"],
            "cable_od_mm": group["cable_od_mm"],
            "colors": [wire["color"] for wire in group["wires"]],
            "labels": [wire["label"] for wire in group["wires"]],
        },
    )
    existing_keys.update(group["keys"])
    return result


def _cable_xyz(side) -> tuple:
    """A connector's cable-point world position as an xyz tuple."""
    point = side["cable"]["world"]
    return (point.x, point.y, point.z)


def _pin_wire(side, ref, pin, problems, label):
    """The connector's wire record for *pin* (None + problem when missing)."""
    wire = side["wires"].get(pin)
    if wire is None:
        problems.append(f"{label}: pin '{pin}' is not defined on '{ref}'.")
    return wire


def _gauge_ok(wires, awg, problems, label) -> bool:
    """True when *awg* is inside every wire's allowed range."""
    for wire in wires:
        if not (wire["awg_min"] <= awg <= wire["awg_max"]):
            problems.append(
                f"{label}: {awg} AWG is outside pin {wire['pin']}'s allowed "
                f"range ({wire['awg_min']}-{wire['awg_max']} AWG)."
            )
            return False
    return True


def _side_data(occ, side_cache) -> dict:
    """read_connector data for *occ*, cached per import run."""
    key = builder.occ_path(occ)
    if key not in side_cache:
        side_cache[key] = builder.read_connector(occ)
    return side_cache[key]


def _designator_map(connectors, problems) -> dict:
    """lowercased designator -> occurrence (ambiguous ones dropped)."""
    designators: dict = {}
    ambiguous: set = set()
    for occ in connectors:
        designator = builder.occurrence_designator(occ)
        if not designator:
            continue
        key = designator.lower()
        if key in designators:
            ambiguous.add(designator)
            continue
        designators[key] = occ
    for designator in sorted(ambiguous):
        problems.append(
            f"Designator '{designator}' is assigned to several connectors - "
            "run Assign Designators and make it unique."
        )
        designators.pop(designator.lower(), None)
    return designators


def _existing_route_keys(design, connectors) -> set:
    """Endpoint keys of every resolvable routed connection in the design."""
    keys: set = set()
    for route in builder.collect_routes(design):
        payload = route["payload"]
        ends = payload.get("ends") or []
        if len(ends) != 2:
            continue
        end_refs = []
        for end in ends:
            refs = []
            for entry in route_logic.end_connectors(end):
                occ = builder.resolve_end_occurrence(design, entry, connectors)
                refs.append(builder.occurrence_designator(occ) if occ else "")
            end_refs.append(refs)
        if not all(all(refs) for refs in end_refs):
            continue  # unresolved or unassigned - cannot be matched
        if payload.get("kind") == route_logic.KIND_CABLE:
            pins_a = [str(pin) for pin in ends[0].get("pins") or []]
            pins_b = [str(pin) for pin in ends[1].get("pins") or []]
            wc_a = route_logic.end_wire_connectors(ends[0], len(pins_a))
            wc_b = route_logic.end_wire_connectors(ends[1], len(pins_b))
            for index, (pin_a, pin_b) in enumerate(zip(pins_a, pins_b, strict=False)):
                keys.add(
                    connectivity.route_key(
                        end_refs[0][wc_a[index]],
                        pin_a,
                        end_refs[1][wc_b[index]],
                        pin_b,
                    )
                )
        else:
            keys.add(
                connectivity.route_key(
                    end_refs[0][0],
                    str(ends[0].get("pin") or ""),
                    end_refs[1][0],
                    str(ends[1].get("pin") or ""),
                )
            )
    return keys


def _show_summary(built_wires, built_cables, skipped_existing, problems, aggregate):
    """The end-of-import report."""
    lines = [
        f"Wires built: {built_wires}",
        f"Cables built: {built_cables}",
        f"Already routed (skipped): {skipped_existing}",
    ]
    if problems:
        lines.append(f"Problems ({len(problems)}):")
        lines.extend(problems[:MAX_REPORTED_PROBLEMS])
        if len(problems) > MAX_REPORTED_PROBLEMS:
            lines.append(f"... and {len(problems) - MAX_REPORTED_PROBLEMS} more.")
    summary = "\n".join(lines)
    if aggregate is not None:
        summary += route_logic.result_notes(aggregate)
    ui.messageBox(summary, CMD_NAME)


def _merge_result(aggregate: dict, result: dict):
    """Fold one build's result flags into the whole-import aggregate."""
    aggregate["spline_fallback"] = aggregate["spline_fallback"] or bool(
        result.get("spline_fallback")
    )
    aggregate["baked_points"] += int(result.get("baked_points") or 0)
    aggregate["dropped_tangents"] += int(result.get("dropped_tangents") or 0)


def _ask_open_path() -> str:
    """The chosen wire-list path ("" when the user cancels)."""
    dialog = ui.createFileDialog()
    dialog.title = "Open connectivity wire list"
    dialog.filter = "CSV files (*.csv);;All Files (*.*)"
    dialog.isMultiSelectEnabled = False
    if dialog.showOpen() != adsk.core.DialogResults.DialogOK:
        return ""
    return dialog.filename
