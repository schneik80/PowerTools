# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Measure Path - cumulative arc length along a connected chain of sketch curves
# and model edges between two picked objects.
#
# All Fusion API contact lives here; every decision about what constitutes a
# deterministic chain lives in pathgraph.py, which imports no adsk module and is
# unit tested outside Fusion.

import math
import os
import traceback

import adsk.core
import adsk.fusion

from ... import config

# Import the ptAddInUtils module from the parent directory.
from ...lib import ptAddInUtils as ptutil
from . import pathgraph

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Measure Path"
CMD_ID = "PTPM_measurepath"
CMD_Description = (
    "Measure the cumulative length of a connected chain of sketch curves and "
    "model edges between two selected objects."
)
IS_PROMOTED = False

WORKSPACE_ID = config.design_workspace
# The command goes on every Inspect panel of every design-product workspace, so
# it is to hand wherever Fusion's own Measure is - Solid, Surface, Mesh, Sheet
# Metal and Plastic all carry one.
#
# Panels are discovered at runtime rather than listed: which tabs exist varies
# with the Fusion version and the user's entitlements, and a hardcoded tab list
# would silently miss panels on one build and log "not found" noise on another.
# All of these panels are BUILT-IN and must never be created or deleted by us.
_PANEL_MATCH = "inspect"
# productType's exact value is not documented, so match it loosely and fall back
# to the known design workspace id.
_DESIGN_PRODUCT_MATCH = "design"

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []

INPUT_START = "mp_start"
INPUT_END = "mp_end"
INPUT_SHORTEST = "mp_shortest"
INPUT_RESULT = "mp_result"
INPUT_STATUS = "mp_status"
INPUT_BRANCH = "mp_branch_pick"
INPUT_UNDO = "mp_undo_branch"
INPUT_TABLE = "mp_segments"
INPUT_HIGHLIGHT = "mp_highlight"

_SELECTION_FILTERS = (
    "SketchPoints",
    "Vertices",
    "ConstructionPoints",
    "SketchCurves",
    "Edges",
)

_GFX_TAG = f"{CMD_ID}_gfx"

# Pixel geometry of the branch manipulator. Each candidate direction gets a cone
# whose apex points the way the chain would continue - a sphere can mark a spot
# but cannot show a direction.
_CONE_PX_OFFSET = 34.0
_CONE_PX_LENGTH = 26.0
_CONE_PX_RADIUS = 8.0
_HOVER_PX_RADIUS = 10.5
_HIT_PX_SLOP = 15.0
# Apex radius as a fraction of the base. createCylinderOrCone does not document
# a radius of exactly 0 as legal, and a sliver this small reads as a point.
_CONE_APEX_FRAC = 0.04

# Pixel geometry of the Start / End terminal markers.
_TERMINAL_PX_RADIUS = 6.0
_LABEL_PX_SIZE = 11.7
_LABEL_PX_OFFSET = 11.0
_LABEL_FONT = "Arial"
# Cursor travel between press and release above which the gesture is a drag
# (orbit/pan) rather than a click.
_DRAG_PX_SLOP = 4.0

# Ceiling on frontier expansion steps, so a pathological model cannot spin.
_MAX_EXPANSION_STEPS = 200000

# Bounds on how far along a candidate a marker may sit, as a fraction of that
# candidate's length, so a marker never overshoots its own segment.
_MARKER_MIN_FRAC = 0.05
_MARKER_MAX_FRAC = 0.45

_COLOR_CANDIDATE = (255, 190, 60, 255)
_COLOR_HOVER = (255, 255, 255, 255)
_COLOR_START = (70, 200, 120, 255)
_COLOR_END = (235, 95, 95, 255)

# Pixel geometry of the per-segment direction markers on a resolved chain. They
# sit at each segment's midpoint, so they are smaller than the branch cones -
# which sit alone at a fork and have to be easy to click.
_PATH_CONE_PX_LENGTH = 22.0
_PATH_CONE_PX_RADIUS = 6.5
_PATH_LABEL_PX_SIZE = 10.5
_PATH_LABEL_PX_OFFSET = 9.0
# Above this many segments the per-segment markers are skipped: a cone plus a
# label each, rebuilt every preview cycle, stalls the viewport long before the
# numbers become legible. The status box says when this bites.
_MAX_PATH_MARKERS = 250

# Command state. Module globals, matching every other command in this add-in.
_graph = None
_node_coords = ()
_seg_entities = {}
_start_nodes = ()
_end_nodes = ()
_seeds = {}
_tail = None
_choices = []
_candidates = []
# (segment key, screen-space hit centre, radius) for each direction cone.
_hit_targets = []
_hover_key = None
_result_cm = 0.0
_picks = {}
_cmd_inputs = None
_press_xy = None
_last_pick_xy = None
_cell_serial = 0
# Prefix and fork node cached while a branch is pending, so hover redraws do
# not have to re-walk the graph.
_pending_node = None
_active_command = None
_preview_pending = False
# Live cone graphics, keyed by segment, so hover can recolour in place.
_marker_gfx = {}
# Nodes carrying the Start / End labels.
_marker_start = ()
_marker_end = ()
# Resolved chain the preview draws per-segment markers for. Empty while the
# chain is unresolved or above the marker cap.
_path_segs = []


def _is_design_workspace(workspace) -> bool:
    """True if *workspace* hosts a Design product, so a path is measurable."""
    if workspace.id == WORKSPACE_ID:
        return True
    try:
        product = (workspace.productType or "").lower()
    except Exception:
        return False
    return _DESIGN_PRODUCT_MATCH in product


def _inspect_panels():
    """Yield every Inspect panel of every design-product workspace.

    Deduplicated by panel id: Fusion shows one panel across several tabs, so the
    same panel can be reached more than once while walking the tab tree, and
    adding a control twice would either throw or leave a duplicate button.
    """
    seen = set()
    panels = []
    try:
        for workspace in ui.workspaces:
            if not _is_design_workspace(workspace):
                continue
            groups = [workspace.toolbarPanels]
            try:
                groups.extend(tab.toolbarPanels for tab in workspace.toolbarTabs)
            except Exception:
                pass
            for collection in groups:
                if not collection:
                    continue
                for panel in collection:
                    panel_id = panel.id or ""
                    if _PANEL_MATCH not in panel_id.lower():
                        continue
                    if panel_id in seen:
                        continue
                    seen.add(panel_id)
                    panels.append(panel)
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}._inspect_panels")
    return panels


def start():
    """Register the command and add it to every design Inspect panel."""
    try:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )
        ptutil.add_handler(cmd_def.commandCreated, command_created)

        placed = []
        for panel in _inspect_panels():
            try:
                if panel.controls.itemById(CMD_ID):
                    continue
                control = panel.controls.addCommand(cmd_def)
                control.isPromoted = IS_PROMOTED
                placed.append(panel.id)
            except Exception as place_err:
                ptutil.log(f"{CMD_NAME}: could not add to {panel.id} ({place_err})")

        if placed:
            ptutil.log(f"{CMD_NAME} added to {len(placed)} panel(s): {placed}")
        else:
            ptutil.log(f"{CMD_NAME}: no Inspect panel found to add to")

    except Exception:
        ptutil.handle_error(f"{CMD_NAME}.start")


def stop():
    """Remove every control this command added, and its definition."""
    try:
        for panel in _inspect_panels():
            try:
                control = panel.controls.itemById(CMD_ID)
                if control:
                    control.deleteMe()
                # These are built-in Fusion panels; never delete the panel.
            except Exception as drop_err:
                ptutil.log(f"{CMD_NAME}: could not remove from {panel.id} ({drop_err})")

        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()

    except Exception:
        ptutil.handle_error(f"{CMD_NAME}.stop")


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Build the dialog and wire the per-invocation handlers."""
    global _cmd_inputs, _active_command
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("Measure Path needs an open design.", CMD_NAME)
            args.command.doExecute(False)
            return

        _reset_state()

        cmd = args.command
        cmd.okButtonText = "Close"
        cmd.isExecutedWhenPreEmpted = False
        _active_command = cmd
        inputs = cmd.commandInputs
        # Cached so the branch manipulator can refresh the dialog from a mouse
        # event, which carries no reference back to the inputs.
        _cmd_inputs = inputs

        start_sel = inputs.addSelectionInput(
            INPUT_START,
            "Start",
            "Select the point, vertex, sketch curve or edge to measure from.",
        )
        end_sel = inputs.addSelectionInput(
            INPUT_END,
            "End",
            "Select the point, vertex, sketch curve or edge to measure to.",
        )
        for sel in (start_sel, end_sel):
            for filter_name in _SELECTION_FILTERS:
                sel.addSelectionFilter(filter_name)
            sel.setSelectionLimits(0, 1)

        inputs.addBoolValueInput(INPUT_SHORTEST, "Shortest path", True, "", True)

        branch_sel = inputs.addSelectionInput(
            INPUT_BRANCH,
            "Direction",
            "Click a highlighted marker or its curve to choose a direction.",
        )
        for filter_name in ("SketchCurves", "Edges"):
            branch_sel.addSelectionFilter(filter_name)
        branch_sel.setSelectionLimits(0, 1)
        branch_sel.isVisible = False

        # isCheckBox=False with an empty resource folder renders as a plain
        # text button, which is what we want for a one-shot action.
        undo = inputs.addBoolValueInput(
            INPUT_UNDO, "Undo last direction", False, "", False
        )
        undo.isVisible = False

        result = inputs.addTextBoxCommandInput(INPUT_RESULT, "Length", "-", 1, True)
        result.isFullWidth = False

        status = inputs.addTextBoxCommandInput(
            INPUT_STATUS, "", "Select a start and an end object.", 2, True
        )
        status.isFullWidth = True

        table = inputs.addTableCommandInput(INPUT_TABLE, "Segments", 3, "3:2:3")
        table.minimumVisibleRows = 1
        table.maximumVisibleRows = 10
        table.isVisible = False

        # Highlights the resolved chain natively. Limits 0,0 so it never takes
        # focus, blocks OK, or competes for the user's picks.
        highlight = inputs.addSelectionInput(INPUT_HIGHLIGHT, "Path", "")
        for filter_name in ("SketchCurves", "Edges"):
            highlight.addSelectionFilter(filter_name)
        highlight.setSelectionLimits(0, 0)
        highlight.tooltip = "The chain currently being measured."

        ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
        ptutil.add_handler(
            cmd.executePreview,
            command_execute_preview,
            local_handlers=local_handlers,
        )
        ptutil.add_handler(
            cmd.inputChanged, command_input_changed, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.preSelect, command_pre_select, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.mouseMove, command_mouse_move, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.mouseDown, command_mouse_down, local_handlers=local_handlers
        )
        ptutil.add_handler(cmd.mouseUp, command_mouse_up, local_handlers=local_handlers)
        ptutil.add_handler(
            cmd.mouseClick, command_mouse_click, local_handlers=local_handlers
        )
        ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    except Exception:
        ui.messageBox(f"{CMD_NAME}: setup failed.\n{traceback.format_exc()}", CMD_NAME)


def _reset_state() -> None:
    global _graph, _node_coords, _seg_entities, _start_nodes, _end_nodes
    global _seeds, _tail, _choices, _candidates, _hit_targets, _hover_key, _result_cm
    global _picks
    global _press_xy, _last_pick_xy, _pending_node
    global _preview_pending, _marker_gfx, _marker_start, _marker_end
    global _path_segs
    _path_segs = []
    _press_xy = None
    _last_pick_xy = None
    _pending_node = None
    _preview_pending = False
    _marker_gfx = {}
    _marker_start = ()
    _marker_end = ()
    _graph = None
    _node_coords = ()
    _seg_entities = {}
    _start_nodes = ()
    _end_nodes = ()
    _seeds = {}
    _tail = None
    _choices = []
    _candidates = []
    _hit_targets = []
    _hover_key = None
    _result_cm = 0.0
    _picks = {}


# ---------------------------------------------------------------------------
# Geometry extraction
# ---------------------------------------------------------------------------


def _tuple(point) -> tuple:
    return (point.x, point.y, point.z)


def _geom_key(prefix: str, ends, length: float) -> str:
    """Geometric fallback key: rounded endpoints plus rounded length.

    Deliberately not id(): Fusion returns a fresh Python wrapper on each access
    to the same topological entity, so identity-based keys would let one edge
    enter the graph twice under different names. Coordinates are stable where
    wrapper identity is not. Two exactly coincident duplicate curves would
    collide, which is degenerate geometry we would rather merge than double.
    """
    first, second = sorted((ends[0], ends[1]))
    return (
        f"{prefix}:"
        f"{first[0]:.6f},{first[1]:.6f},{first[2]:.6f}/"
        f"{second[0]:.6f},{second[1]:.6f},{second[2]:.6f}/"
        f"{length:.6f}"
    )


def _token(entity, prefix: str, ends, length: float) -> str:
    """A graph key for *entity*, stable for the life of one invocation.

    entityToken is the documented durable identifier and distinguishes
    occurrence proxies from each other, which is what we want. It can raise on
    some entities, so a geometric key backs it up.
    """
    try:
        token = entity.entityToken
        if token:
            return f"{prefix}:{token}"
    except Exception:
        pass
    return _geom_key(prefix, ends, length)


def _sketch_point_world(sketch_point) -> tuple | None:
    """World-space position of a SketchPoint.

    SketchPoint.worldGeometry can silently return the origin for some point
    types, so this goes through the sketch transform instead - the same
    pipeline commands/sketchcirclecenterpoint/entry.py settled on.
    """
    try:
        sketch = sketch_point.parentSketch
        if not sketch:
            return None
        local = sketch_point.geometry
        model = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(local.x, local.y, 0.0)
        )
        context = sketch_point.assemblyContext
        if context:
            model.transformBy(context.transform2)
        return _tuple(model)
    except Exception:
        return None


def _curve_ends(curve) -> tuple | None:
    """(start_world, end_world) for an open sketch curve, else None.

    Closed curves - SketchCircle and SketchEllipse - expose only a centre point
    and can never form part of a chain, so they are rejected here.
    """
    start_pt = getattr(curve, "startSketchPoint", None)
    end_pt = getattr(curve, "endSketchPoint", None)
    if start_pt is None or end_pt is None:
        return None
    first = _sketch_point_world(start_pt)
    second = _sketch_point_world(end_pt)
    if first is None or second is None:
        return None
    return first, second


def _iter_collection(collection):
    """Iterate a Fusion collection that may be None, or may raise on access.

    SketchPoint.connectedEntities returns None rather than an empty collection
    for some points. Iterating it directly raised
    "TypeError: 'NoneType' object is not iterable" out of _collect and aborted
    the entire graph build for one unremarkable sketch point, which surfaced as
    Measure Path simply not finding a path. One flaky property should cost us
    that point's neighbours, not the whole measurement.
    """
    if not collection:
        return ()
    try:
        return list(collection)
    except Exception:
        return ()


def _vertex_world(vertex) -> tuple | None:
    try:
        return _tuple(vertex.geometry)
    except Exception:
        return None


def _edge_ends(edge) -> tuple | None:
    try:
        if edge.isDegenerate:
            return None
        first = _vertex_world(edge.startVertex)
        second = _vertex_world(edge.endVertex)
        if first is None or second is None:
            return None
        return first, second
    except Exception:
        return None


def _coord_key(prefix: str, point) -> str:
    """Dedup key for a traversal waypoint, based on position not identity."""
    return f"{prefix}:{point[0]:.6f},{point[1]:.6f},{point[2]:.6f}"


def _collect(entity, records, seen) -> None:
    """Walk outward from *entity*, appending (key, pa, pb, length, kind, obj).

    Expansion is frontier driven and stays local: BRepVertex.edges and
    SketchPoint.connectedEntities hand us adjacency directly, so nothing scans
    a whole assembly.
    """
    frontier = [entity]
    guard = 0
    while frontier and guard < _MAX_EXPANSION_STEPS:
        guard += 1
        current = frontier.pop()

        edge = adsk.fusion.BRepEdge.cast(current)
        if edge:
            ends = _edge_ends(edge)
            if ends is None:
                continue
            key = _token(edge, "edge", ends, edge.length)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                (key, ends[0], ends[1], edge.length, pathgraph.KIND_EDGE, edge)
            )
            frontier.append(edge.startVertex)
            frontier.append(edge.endVertex)
            continue

        vertex = adsk.fusion.BRepVertex.cast(current)
        if vertex:
            world = _vertex_world(vertex)
            if world is None:
                continue
            vkey = _coord_key("v", world)
            if vkey in seen:
                continue
            seen.add(vkey)
            for incident in _iter_collection(vertex.edges):
                frontier.append(incident)
            continue

        curve = adsk.fusion.SketchCurve.cast(current)
        if curve:
            ends = _curve_ends(curve)
            if ends is None:
                continue
            key = _token(curve, "sketch", ends, curve.length)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                (key, ends[0], ends[1], curve.length, pathgraph.KIND_SKETCH, curve)
            )
            frontier.append(curve.startSketchPoint)
            frontier.append(curve.endSketchPoint)
            continue

        point = adsk.fusion.SketchPoint.cast(current)
        if point:
            world = _sketch_point_world(point)
            if world is None:
                continue
            pkey = _coord_key("p", world)
            if pkey in seen:
                continue
            seen.add(pkey)
            for connected in _iter_collection(point.connectedEntities):
                connected_curve = adsk.fusion.SketchCurve.cast(connected)
                if not connected_curve:
                    continue
                # connectedEntities also reports circles, arcs and ellipses
                # that merely use this point as their CENTRE. Those are not
                # continuations, and counting them would turn every circle
                # centre into a phantom branch.
                ends = _curve_ends(connected_curve)
                if ends is None:
                    continue
                if not _touches(ends, world):
                    continue
                frontier.append(connected_curve)
            continue


def _touches(ends, point, tol=pathgraph.DEFAULT_WELD_TOL) -> bool:
    if point is None:
        return False
    for candidate in ends:
        dx = candidate[0] - point[0]
        dy = candidate[1] - point[1]
        dz = candidate[2] - point[2]
        if dx * dx + dy * dy + dz * dz <= tol * tol:
            return True
    return False


def _anchor_points(entity) -> list:
    """World points at which a chain may start from *entity*."""
    point = adsk.fusion.SketchPoint.cast(entity)
    if point:
        world = _sketch_point_world(point)
        return [world] if world else []

    vertex = adsk.fusion.BRepVertex.cast(entity)
    if vertex:
        world = _vertex_world(vertex)
        return [world] if world else []

    construction = adsk.fusion.ConstructionPoint.cast(entity)
    if construction:
        try:
            return [_tuple(construction.geometry)]
        except Exception:
            return []

    edge = adsk.fusion.BRepEdge.cast(entity)
    if edge:
        ends = _edge_ends(edge)
        return list(ends) if ends else []

    curve = adsk.fusion.SketchCurve.cast(entity)
    if curve:
        ends = _curve_ends(curve)
        return list(ends) if ends else []

    return []


def _seg_key(entity) -> str | None:
    """The graph key for a selection that is itself a traversable segment.

    Must build the key exactly as _collect does, or the branch-pick lookup and
    the curve seed both silently miss.
    """
    edge = adsk.fusion.BRepEdge.cast(entity)
    if edge:
        ends = _edge_ends(edge)
        if ends is None:
            return None
        return _token(edge, "edge", ends, edge.length)
    curve = adsk.fusion.SketchCurve.cast(entity)
    if curve:
        ends = _curve_ends(curve)
        if ends is None:
            return None
        return _token(curve, "sketch", ends, curve.length)
    return None


def _closed_pick(entity) -> bool:
    """True if *entity* is a closed sketch curve, which cannot join a chain."""
    curve = adsk.fusion.SketchCurve.cast(entity)
    if not curve:
        return False
    return _curve_ends(curve) is None


def _rebuild(start_entity, end_entity) -> bool:
    """Extract the graph around both selections and locate their nodes."""
    global _graph, _node_coords, _seg_entities, _start_nodes, _end_nodes, _seeds
    global _tail

    records = []
    seen = set()
    _collect(start_entity, records, seen)
    _collect(end_entity, records, seen)

    if not records:
        _graph = None
        return False

    points = []
    for _, first, second, _, _, _ in records:
        points.append(first)
        points.append(second)

    start_anchors = _anchor_points(start_entity)
    end_anchors = _anchor_points(end_entity)
    points.extend(start_anchors)
    points.extend(end_anchors)

    indices, coords = pathgraph.weld(points, pathgraph.DEFAULT_WELD_TOL)

    segs = []
    entities = {}
    for position, record in enumerate(records):
        key, _, _, length, kind, obj = record
        segs.append(
            pathgraph.Seg(
                key, indices[2 * position], indices[2 * position + 1], length, kind
            )
        )
        entities[key] = obj

    _graph = pathgraph.build(segs)
    _node_coords = coords
    _seg_entities = entities

    offset = 2 * len(records)
    _start_nodes = tuple(dict.fromkeys(indices[offset : offset + len(start_anchors)]))
    _end_nodes = tuple(dict.fromkeys(indices[offset + len(start_anchors) :]))

    # A curve picked as the start counts its own length, so force it as the
    # first step out of whichever of its endpoints the walk leaves from.
    _seeds = {}
    seed_key = _seg_key(start_entity)
    if seed_key and seed_key in _graph.segs:
        seed = _graph.segs[seed_key]
        for node in _start_nodes:
            if node in (seed.a, seed.b):
                _seeds[node] = seed

    # A curve picked as the end counts its own length too. The walk targets its
    # endpoints, so without this it would stop on touching one and drop the
    # segment from both the total and the breakdown.
    _tail = None
    tail_key = _seg_key(end_entity)
    if tail_key and tail_key in _graph.segs:
        _tail = _graph.segs[tail_key]

    return bool(_start_nodes and _end_nodes)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _resolve_and_draw(inputs) -> None:
    """Run the disambiguation ladder and reflect the outcome in the dialog."""
    global _candidates, _result_cm, _pending_node

    result_box = inputs.itemById(INPUT_RESULT)
    status_box = inputs.itemById(INPUT_STATUS)
    branch_sel = adsk.core.SelectionCommandInput.cast(inputs.itemById(INPUT_BRANCH))
    undo = inputs.itemById(INPUT_UNDO)
    table = adsk.core.TableCommandInput.cast(inputs.itemById(INPUT_TABLE))

    _candidates = []
    _pending_node = None

    if _graph is None or not _start_nodes or not _end_nodes:
        _result_cm = 0.0
        result_box.text = "-"
        status_box.text = "Select a start and an end object."
        branch_sel.isVisible = False
        undo.isVisible = False
        table.isVisible = False
        _highlight(inputs, ())
        _set_markers((), False)
        _request_preview()
        return

    shortest_input = adsk.core.BoolValueCommandInput.cast(
        inputs.itemById(INPUT_SHORTEST)
    )

    if shortest_input.value:
        seed = next(iter(_seeds.values()), None)
        segs, length = pathgraph.shortest(
            _graph, _start_nodes, set(_end_nodes), seed=seed, tail=_tail
        )
        if segs is None:
            _report_unreachable(result_box, status_box, branch_sel, undo, table)
            return
        _result_cm = length
        result_box.text = _format(length)
        status_box.text = f"Shortest path, {len(segs)} segment(s).{_marker_note(segs)}"
        branch_sel.isVisible = False
        undo.isVisible = False
        _fill_table(table, segs)
        _highlight(inputs, segs)
        _set_markers(segs, True)
        _request_preview()
        return

    result, how = pathgraph.resolve(
        _graph,
        _start_nodes,
        set(_end_nodes),
        pathgraph.HOMOGENEOUS_ORDER,
        _choices,
        _seeds,
        _tail,
    )

    if result is None:
        _report_unreachable(result_box, status_box, branch_sel, undo, table)
        return

    _result_cm = result.length
    result_box.text = _format(result.length)
    undo.isVisible = bool(_choices)
    _highlight(inputs, result.segs)
    _set_markers(result.segs, result.reached)

    if result.reached:
        note = {
            "direct": "Single connected chain.",
            "chosen": "Chain resolved from your chosen directions.",
            "edges": "Ambiguous overall; resolved as the only all-edge chain.",
            "sketch": "Ambiguous overall; resolved as the only all-sketch chain.",
        }.get(how, "Chain resolved.")
        status_box.text = (
            f"{note} {len(result.segs)} segment(s).{_marker_note(result.segs)}"
        )
        branch_sel.isVisible = False
        _fill_table(table, result.segs)
        _request_preview()
        return

    if not result.candidates:
        _report_unreachable(result_box, status_box, branch_sel, undo, table)
        return

    _candidates = list(result.candidates)
    _pending_node = result.node
    branch_sel.isVisible = True
    branch_sel.clearSelection()
    status_box.text = (
        f"{len(_candidates)} directions available. Click a marker or its curve "
        "to continue. Partial length shown above."
    )
    _fill_table(table, result.segs)
    _request_preview()


def _report_unreachable(result_box, status_box, branch_sel, undo, table) -> None:
    global _result_cm
    _result_cm = 0.0
    result_box.text = "-"
    gap = _nearest_gap()
    detail = f" Nearest unconnected gap is {_format(gap)}." if gap is not None else ""
    status_box.text = (
        "No connected chain of sketch curves or model edges joins these two "
        f"selections.{detail}"
    )
    branch_sel.isVisible = False
    undo.isVisible = bool(_choices)
    table.isVisible = False
    if _cmd_inputs is not None:
        _highlight(_cmd_inputs, ())
    _set_markers((), False)
    _request_preview()


def _marker_note(segs) -> str:
    """Say so when a chain is too long to mark up, rather than silently not."""
    if len(segs) <= _MAX_PATH_MARKERS:
        return ""
    return f" Segment markers hidden above {_MAX_PATH_MARKERS} segments."


def _set_markers(segs, resolved) -> None:
    """Decide where the Start and End labels go, and what the preview marks up.

    A resolved chain gets exactly one of each, at its real terminals, which is
    what tells the user the path's sense. While a chain is still partial the
    target end anchors are labelled instead, so the markers show where the
    measurement is heading rather than where it has got to.
    """
    global _marker_start, _marker_end, _path_segs
    origin, terminus = pathgraph.endpoints(segs, _start_nodes)
    # Per-segment markers describe a finished answer, so a partial chain gets
    # none - numbering a chain that is about to change would mislead.
    _path_segs = list(segs) if resolved and len(segs) <= _MAX_PATH_MARKERS else []
    if resolved and origin is not None and terminus is not None:
        _marker_start = (origin,)
        _marker_end = (terminus,)
        return
    _marker_start = (origin,) if origin is not None else tuple(_start_nodes)
    _marker_end = tuple(_end_nodes)


def _highlight(inputs, segs) -> None:
    """Highlight *segs* natively, via a selection input rather than graphics.

    ui.activeSelections does not highlight while a command dialog is open, but
    SelectionCommandInput.addSelection does - the mechanism
    commands/inferconstraints/entry.py:193-201 already relies on. Unlike custom
    graphics this is not part of the preview transaction, so it cannot be undone
    out from under us on the next preview cycle.
    """
    try:
        sel = adsk.core.SelectionCommandInput.cast(inputs.itemById(INPUT_HIGHLIGHT))
        if not sel:
            return
        sel.clearSelection()
        for seg in segs:
            entity = _seg_entities.get(seg.key)
            if entity is None:
                continue
            try:
                sel.addSelection(entity)
            except Exception as sel_err:
                ptutil.log(f"{CMD_NAME}: could not highlight ({sel_err})")
    except Exception:
        ptutil.log(f"{CMD_NAME}: highlight failed\n{traceback.format_exc()}")


def _request_preview() -> None:
    """Ask Fusion for a preview cycle, which is where graphics get drawn.

    Custom graphics created anywhere else are built inside the command's
    transaction, and Fusion aborts that transaction ("the equivalent of an
    undo") when the next preview fires - which is why drawing from inputChanged
    or a mouse handler makes the graphics flash and vanish. Drawing only inside
    executePreview keeps them alive until the next cycle, when we redraw.

    Fusion fires executePreview by itself after an input changes, so this is
    only needed after a state change driven by a mouse click.
    """
    global _preview_pending
    _preview_pending = True
    command = _active_command
    if command is None:
        return
    try:
        command.doExecutePreview()
    except Exception:
        # Not fatal: an input-driven change gets its own preview anyway.
        ptutil.log(f"{CMD_NAME}: doExecutePreview unavailable here")


def _nearest_gap() -> float | None:
    """Smallest distance between a start-side and end-side node.

    Reported on failure so "not connected" is diagnosable rather than mute -
    usually the answer is that two endpoints are close but outside tolerance.
    """
    if not _node_coords or not _start_nodes or not _end_nodes:
        return None
    best = None
    for start in _start_nodes:
        first = _node_coords[start]
        for end in _end_nodes:
            second = _node_coords[end]
            gap = math.dist(first, second)
            if best is None or gap < best:
                best = gap
    return best


def _format(length_cm: float) -> str:
    """Format a centimetre length using the document's unit preferences."""
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design:
            # formatValue honours the precision preferences; the older
            # formatInternalValue is retired and does not.
            return design.unitsManager.formatValue(length_cm)
    except Exception:
        pass
    return f"{length_cm:.4f} cm"


def _fill_table(table, segs) -> None:
    """Rebuild the per-segment breakdown.

    Cell ids come from a monotonic counter, never from the row index. Clearing a
    table removes its rows but leaves the cell CommandInputs alive on the table's
    own input collection, so reusing an id throws on the second rebuild.
    """
    global _cell_serial
    try:
        table.clear()
        table.isVisible = bool(segs)
        if not segs:
            return
        children = table.commandInputs
        for row, seg in enumerate(segs):
            _cell_serial += 1
            base = f"mp_c{_cell_serial}"
            index = children.addTextBoxCommandInput(
                f"{base}_n", "", str(row + 1), 1, True
            )
            kind = children.addTextBoxCommandInput(
                f"{base}_k",
                "",
                "Model edge" if seg.kind == pathgraph.KIND_EDGE else "Sketch curve",
                1,
                True,
            )
            length = children.addTextBoxCommandInput(
                f"{base}_l", "", _format(seg.length), 1, True
            )
            table.addCommandInput(index, row, 0)
            table.addCommandInput(kind, row, 1)
            table.addCommandInput(length, row, 2)
    except Exception:
        ptutil.log(f"{CMD_NAME}: table refresh failed\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Custom graphics
# ---------------------------------------------------------------------------


def _clear_graphics() -> None:
    """Delete every graphics group this command created.

    Groups are found by their id tag rather than a cached reference, which goes
    stale across document and edit-state changes.
    """
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return
        groups = design.rootComponent.customGraphicsGroups
        # Reverse so the index stays valid while items are removed.
        for index in range(groups.count - 1, -1, -1):
            group = groups.item(index)
            if group.id == _GFX_TAG:
                group.deleteMe()
    except Exception:
        pass


def _group():
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return None
    group = design.rootComponent.customGraphicsGroups.add()
    group.id = _GFX_TAG
    # Our overlay must not intercept picks aimed at the candidate curves it
    # sits on; that native pick is the reliable half of branch selection.
    group.isSelectable = False
    return group


def _color(rgba):
    return adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(*rgba)
    )


def _entity_curve(seg):
    """A Curve3D in world space for a graph segment, or None."""
    entity = _seg_entities.get(seg.key)
    if entity is None:
        return None
    edge = adsk.fusion.BRepEdge.cast(entity)
    if edge:
        return edge.geometry
    curve = adsk.fusion.SketchCurve.cast(entity)
    if curve:
        return getattr(curve, "worldGeometry", None)
    return None


def command_execute_preview(args: adsk.core.CommandEventArgs) -> None:
    """Draw the branch manipulator.

    This is the ONLY place custom graphics are created. Everything Fusion builds
    during a preview lives in one transaction that it aborts when the next
    preview fires, so graphics created from inputChanged or a mouse handler are
    undone almost immediately - they flash and vanish. Created here they survive
    until the next cycle, which redraws them from state.

    isValidResult is deliberately left False: we build no document geometry, and
    setting it True would make Fusion skip the execute event, which is where the
    result gets copied to the clipboard.
    """
    global _preview_pending
    _preview_pending = False
    try:
        _clear_graphics()
        _hit_targets.clear()
        _marker_gfx.clear()
        _draw_terminals()
        # Mutually exclusive with the candidate cones below: _path_segs is only
        # populated for a resolved chain, _candidates only for an unresolved one.
        if _path_segs:
            _draw_path_markers(_path_segs)
        if _candidates and _pending_node is not None:
            _draw_candidates(_pending_node, _candidates)
        adsk.core.Application.get().activeViewport.refresh()
    except Exception:
        ptutil.log(f"{CMD_NAME}: preview draw failed\n{traceback.format_exc()}")


def _px_per_cm(point) -> float | None:
    """Screen pixels per centimetre near *point*.

    Sampling the projected basis keeps the manipulator a constant size on
    screen without relying on CustomGraphicsViewScale, which is unproven in
    this add-in.
    """
    try:
        viewport = app.activeViewport
        origin = viewport.modelToViewSpace(adsk.core.Point3D.create(*point))
        if origin is None:
            return None
        best = None
        for offset in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
            probe = viewport.modelToViewSpace(
                adsk.core.Point3D.create(
                    point[0] + offset[0], point[1] + offset[1], point[2] + offset[2]
                )
            )
            if probe is None:
                continue
            scale = math.hypot(probe.x - origin.x, probe.y - origin.y)
            if scale > 1e-9 and (best is None or scale > best):
                best = scale
        return best
    except Exception:
        return None


def _point_along(seg, node, distance_cm):
    """Point *distance_cm* along *seg* measured from *node*, by true arc length."""
    curve = _entity_curve(seg)
    if curve is None:
        return None
    try:
        evaluator = curve.evaluator
        ok, min_param, max_param = evaluator.getParameterExtents()
        if not ok:
            return None
        node_point = adsk.core.Point3D.create(*_node_coords[node])
        ok, node_param = evaluator.getParameterAtPoint(node_point)
        if not ok:
            return None
        # Step toward whichever extent we are not already sitting on.
        forward = abs(node_param - min_param) <= abs(max_param - node_param)
        signed = distance_cm if forward else -distance_cm
        ok, target_param = evaluator.getParameterAtLength(node_param, signed)
        if not ok:
            return None
        ok, point = evaluator.getPointAtParameter(target_param)
        if not ok:
            return None
        return point
    except Exception:
        return None


def _draw_candidates(node, candidates) -> None:
    """Raise a cone on each candidate direction leaving *node*.

    The cone's base sits on its own candidate curve and its apex points further
    along that curve, so the marker shows which way the chain would continue
    rather than just where a choice exists.

    Sitting on the curve also means a click on the cone is geometrically a click
    on the curve beneath it, so Fusion's native picking resolves the choice even
    where raw mouse events never reach us.
    """
    global _hit_targets
    _hit_targets = []
    try:
        group = _group()
        if group is None:
            return

        scale = _px_per_cm(_node_coords[node])
        temp = adsk.fusion.TemporaryBRepManager.get()
        candidate_color = _color(_COLOR_CANDIDATE)
        hover_color = _color(_COLOR_HOVER)

        for seg in candidates:
            hovered = seg.key == _hover_key
            if scale:
                offset_cm = _CONE_PX_OFFSET / scale
                length_cm = _CONE_PX_LENGTH / scale
                radius_cm = (_HOVER_PX_RADIUS if hovered else _CONE_PX_RADIUS) / scale
            else:
                # No usable projection (direction near-parallel to the view
                # axis): fall back to sizing off the segment itself.
                offset_cm = min(0.2 * seg.length, 1.0)
                length_cm = min(0.15 * seg.length, 0.8)
                radius_cm = max(length_cm * 0.3, 0.04)

            # Keep the whole cone on its own segment, base to apex.
            span = max(offset_cm + length_cm, 1e-6)
            limit = _MARKER_MAX_FRAC * seg.length
            if span > limit:
                shrink = limit / span
                offset_cm *= shrink
                length_cm *= shrink
                radius_cm *= shrink
            offset_cm = max(offset_cm, _MARKER_MIN_FRAC * seg.length)

            base = _point_along(seg, node, offset_cm)
            apex = _point_along(seg, node, offset_cm + length_cm)
            if base is None or apex is None:
                continue

            curve = _entity_curve(seg)
            if curve is not None:
                lead = group.addCurve(curve)
                lead.weight = 3.0
                lead.color = candidate_color
                lead.depthPriority = 1

            body = temp.createCylinderOrCone(
                base, radius_cm, apex, radius_cm * _CONE_APEX_FRAC
            )
            if body is None:
                continue
            marker = group.addBRepBody(body)
            marker.color = hover_color if hovered else candidate_color
            marker.depthPriority = 2
            marker.id = seg.key

            # Hit-test against the cone's midpoint, which is what the eye reads
            # as its position.
            centre = adsk.core.Point3D.create(
                (base.x + apex.x) * 0.5,
                (base.y + apex.y) * 0.5,
                (base.z + apex.z) * 0.5,
            )
            _hit_targets.append((seg.key, centre, radius_cm))
            # Kept so hover can recolour in place. Creating and deleting graphics
            # per mouse move would churn the preview transaction and flicker.
            _marker_gfx[seg.key] = marker

    except Exception:
        ptutil.log(f"{CMD_NAME}: manipulator draw failed\n{traceback.format_exc()}")


def _ramp(index: int, count: int) -> tuple:
    """RGBA at position *index* of *count* on the Start-green to End-red ramp.

    Reusing the terminal colours as the ends of the ramp is what ties the
    per-segment markers to the Start and End dots: the chain visibly runs from
    one colour to the other rather than carrying an unrelated palette.
    """
    fraction = 0.0 if count < 2 else index / (count - 1)
    return tuple(
        int(round(first + (second - first) * fraction))
        for first, second in zip(_COLOR_START, _COLOR_END, strict=True)
    )


def _draw_path_markers(segs) -> None:
    """Raise a numbered direction cone at the midpoint of each resolved segment.

    Each cone runs base to apex along its own segment in the direction the chain
    travels, so the markers show the path's sense and not just its route, and
    the number ties each one to its row in the Segments table. The colour ramps
    green to red across the chain, which is what makes a long path readable in
    order rather than as an undifferentiated highlight.

    These cones are deliberately kept out of _hit_targets and _marker_gfx: those
    drive the branch manipulator, and a resolved chain has nothing to pick.
    """
    try:
        pairs = pathgraph.traversal(segs, _start_nodes)
        if not pairs:
            return
        group = _group()
        if group is None:
            return

        temp = adsk.fusion.TemporaryBRepManager.get()
        total = len(pairs)

        for index, (seg, node) in enumerate(pairs):
            if node >= len(_node_coords):
                continue
            scale = _px_per_cm(_node_coords[node])
            if scale:
                length_cm = _PATH_CONE_PX_LENGTH / scale
                radius_cm = _PATH_CONE_PX_RADIUS / scale
                text_cm = _PATH_LABEL_PX_SIZE / scale
                offset_cm = _PATH_LABEL_PX_OFFSET / scale
            else:
                # No usable projection (segment near-parallel to the view axis):
                # fall back to sizing off the segment itself.
                length_cm = min(0.15 * seg.length, 0.8)
                radius_cm = max(length_cm * 0.3, 0.04)
                text_cm = 0.2
                offset_cm = 0.14

            # Keep the whole cone on its own segment, straddling the midpoint.
            limit = _MARKER_MAX_FRAC * seg.length
            if length_cm > limit:
                radius_cm *= limit / max(length_cm, 1e-6)
                length_cm = limit
            middle = seg.length * 0.5
            half = length_cm * 0.5

            base = _point_along(seg, node, middle - half)
            apex = _point_along(seg, node, middle + half)
            if base is None or apex is None:
                continue

            colour = _color(_ramp(index, total))
            body = temp.createCylinderOrCone(
                base, radius_cm, apex, radius_cm * _CONE_APEX_FRAC
            )
            if body is not None:
                marker = group.addBRepBody(body)
                marker.color = colour
                marker.depthPriority = 2
                marker.isSelectable = False

            _billboard_text(
                group,
                (apex.x, apex.y, apex.z),
                str(index + 1),
                colour,
                text_cm,
                offset_cm,
            )

    except Exception:
        ptutil.log(f"{CMD_NAME}: segment marker draw failed\n{traceback.format_exc()}")


def _draw_terminals() -> None:
    """Mark and label where the measured path starts and ends.

    Without this the highlighted chain shows the route but not its sense, which
    matters as soon as the chain doubles back on itself or the two selections
    look alike.
    """
    try:
        if not _marker_start and not _marker_end:
            return
        group = _group()
        if group is None:
            return
        for nodes, rgba, label in (
            (_marker_start, _COLOR_START, "Start"),
            (_marker_end, _COLOR_END, "End"),
        ):
            for node in nodes:
                _draw_terminal(group, node, rgba, label)
    except Exception:
        ptutil.log(f"{CMD_NAME}: terminal draw failed\n{traceback.format_exc()}")


def _draw_terminal(group, node, rgba, label) -> None:
    """Draw one terminal: a dot at *node* and a billboarded text label."""
    if node is None or node >= len(_node_coords):
        return
    point = _node_coords[node]
    scale = _px_per_cm(point)
    colour = _color(rgba)

    if scale:
        radius_cm = _TERMINAL_PX_RADIUS / scale
        text_cm = _LABEL_PX_SIZE / scale
        offset_cm = _LABEL_PX_OFFSET / scale
    else:
        radius_cm = 0.08
        text_cm = 0.2
        offset_cm = 0.14

    centre = adsk.core.Point3D.create(*point)
    body = adsk.fusion.TemporaryBRepManager.get().createSphere(centre, radius_cm)
    if body is not None:
        dot = group.addBRepBody(body)
        dot.color = colour
        dot.depthPriority = 3
        dot.isSelectable = False

    _billboard_text(group, point, label, colour, text_cm, offset_cm)


def _billboard_text(group, point, label, colour, text_cm, offset_cm) -> None:
    """Place *label* near *point*, turned to face the camera.

    addText places the string parallel to X-Y with its origin at the upper-left
    corner, so on its own it would be edge-on from most viewpoints. Billboarding
    turns it to face the camera; the transform only carries position.
    """
    label_point = adsk.core.Point3D.create(
        point[0] + offset_cm, point[1] + offset_cm, point[2]
    )
    transform = adsk.core.Matrix3D.create()
    transform.translation = label_point.asVector()
    text = group.addText(label, _LABEL_FONT, text_cm, transform)
    if text is None:
        return
    text.color = colour
    text.depthPriority = 4
    text.isSelectable = False
    try:
        # Anchor on the label's own point, not the node: anchoring at the node
        # rotates the offset with the camera and the label orbits the dot.
        billboard = adsk.fusion.CustomGraphicsBillBoard.create(label_point)
        billboard.billBoardStyle = (
            adsk.fusion.CustomGraphicsBillBoardStyles.ScreenBillBoardStyle
        )
        text.billBoarding = billboard
    except Exception:
        # Readable but view-dependent is better than no label at all.
        ptutil.log(f"{CMD_NAME}: billboarding unavailable for the {label} label")


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------


def _viewport_xy(args) -> tuple | None:
    """Cursor position in viewport space, matching modelToViewSpace."""
    position = args.viewportPosition
    if position is None:
        return None
    return (position.x, position.y)


def _hit(args) -> str | None:
    """Segment key of the marker under the cursor, or None."""
    if not _hit_targets:
        return None
    cursor = _viewport_xy(args)
    if cursor is None:
        return None
    viewport = args.viewport or app.activeViewport
    best_key = None
    best_distance = None
    for key, centre, _ in _hit_targets:
        projected = viewport.modelToViewSpace(centre)
        if projected is None:
            continue
        distance = math.hypot(projected.x - cursor[0], projected.y - cursor[1])
        if distance <= _HIT_PX_SLOP and (
            best_distance is None or distance < best_distance
        ):
            best_key = key
            best_distance = distance
    return best_key


def command_pre_select(args: adsk.core.SelectionEventArgs) -> None:
    """While a branch is pending, only the candidate curves may be picked."""
    try:
        if not _candidates:
            return
        # activeInput is not guaranteed to be populated on every build. When it
        # is, respect it so the user can still re-pick start/end mid-session;
        # when it is not, fail closed and filter, so a stray pick cannot be
        # mistaken for a branch choice.
        active = args.activeInput
        if active is not None and active.id != INPUT_BRANCH:
            return
        key = _seg_key(args.selection.entity)
        if key is None or all(seg.key != key for seg in _candidates):
            args.isSelectable = False
    except Exception:
        ptutil.log(f"{CMD_NAME}: preSelect failed\n{traceback.format_exc()}")


def command_mouse_move(args: adsk.core.MouseEventArgs) -> None:
    """Highlight the marker under the cursor."""
    global _hover_key
    try:
        if not _candidates:
            return
        hit = _hit(args)
        if hit == _hover_key:
            return
        _hover_key = hit
        _apply_hover()
    except Exception:
        ptutil.log(f"{CMD_NAME}: mouseMove failed\n{traceback.format_exc()}")


def _apply_hover() -> None:
    """Recolour the markers in place to reflect the hovered one.

    Deliberately mutates the existing graphics rather than rebuilding them.
    Rebuilding would mean deleting and re-adding graphics outside a preview
    cycle, which is exactly what makes them flicker; setting a colour on a live
    entity touches no transaction.
    """
    if not _marker_gfx:
        return
    try:
        candidate_color = _color(_COLOR_CANDIDATE)
        hover_color = _color(_COLOR_HOVER)
        for key, marker in _marker_gfx.items():
            try:
                marker.color = hover_color if key == _hover_key else candidate_color
            except Exception:
                # Entity went stale (a preview rebuilt it); the next preview
                # cycle will redraw with the right colour anyway.
                return
        adsk.core.Application.get().activeViewport.refresh()
    except Exception:
        ptutil.log(f"{CMD_NAME}: hover update failed\n{traceback.format_exc()}")


def command_mouse_down(args: adsk.core.MouseEventArgs) -> None:
    """Record where a press began, so a drag can be told from a click."""
    global _press_xy
    try:
        _press_xy = _viewport_xy(args)
    except Exception:
        _press_xy = None


def command_mouse_up(args: adsk.core.MouseEventArgs) -> None:
    _handle_click(args)


def command_mouse_click(args: adsk.core.MouseEventArgs) -> None:
    # mouseClick is documented as unreliable on some builds, so both it and
    # mouseUp are bound. _handle_click de-duplicates so one physical click can
    # never consume two branch choices.
    _handle_click(args)


def _handle_click(args: adsk.core.MouseEventArgs) -> None:
    global _last_pick_xy, _press_xy
    try:
        if not _candidates:
            return
        if args.button != adsk.core.MouseButtons.LeftMouseButton:
            return

        cursor = _viewport_xy(args)
        if cursor is None:
            return

        # An orbit or pan that happens to end over a marker is not a choice.
        if _press_xy is not None:
            travel = math.hypot(cursor[0] - _press_xy[0], cursor[1] - _press_xy[1])
            if travel > _DRAG_PX_SLOP:
                _press_xy = None
                return

        # Both mouseUp and mouseClick fire for the same press on builds where
        # mouseClick works; consume only the first.
        rounded = (round(cursor[0]), round(cursor[1]))
        if _last_pick_xy == rounded:
            return

        hit = _hit(args)
        if hit is None:
            return

        _last_pick_xy = rounded
        _press_xy = None
        _choose_branch(hit)
    except Exception:
        ptutil.log(f"{CMD_NAME}: click failed\n{traceback.format_exc()}")


def _choose_branch(key: str) -> None:
    """Commit a branch choice and re-resolve."""
    global _hover_key
    if all(seg.key != key for seg in _candidates):
        return
    _choices.append(key)
    _hover_key = None
    if _cmd_inputs is not None:
        _resolve_and_draw(_cmd_inputs)
    else:
        ptutil.log(f"{CMD_NAME}: branch {key} picked before inputs were cached")


def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    """Re-extract and re-resolve whenever a relevant input changes."""
    global _cmd_inputs, _choices
    try:
        inputs = args.inputs
        _cmd_inputs = inputs
        changed = args.input

        if changed.id == INPUT_BRANCH:
            branch_sel = adsk.core.SelectionCommandInput.cast(changed)
            if branch_sel.selectionCount == 1:
                key = _seg_key(branch_sel.selection(0).entity)
                branch_sel.clearSelection()
                if key:
                    _choose_branch(key)
            return

        if changed.id == INPUT_UNDO:
            if _choices:
                _choices.pop()
            _resolve_and_draw(inputs)
            return

        if changed.id == INPUT_SHORTEST:
            _resolve_and_draw(inputs)
            return

        if changed.id in (INPUT_START, INPUT_END):
            ptutil.capture_selections(inputs, _picks, INPUT_START, INPUT_END)
            _choices = []
            start_entity = ptutil.picked_one(_picks, INPUT_START)
            end_entity = ptutil.picked_one(_picks, INPUT_END)
            if start_entity is None or end_entity is None:
                _reset_graph_only()
                _resolve_and_draw(inputs)
                return
            closed = _closed_pick(start_entity) or _closed_pick(end_entity)
            if closed:
                _reset_graph_only()
                _resolve_and_draw(inputs)
                inputs.itemById(INPUT_STATUS).text = (
                    "A full circle or ellipse has no endpoints, so it cannot be "
                    "part of a measured chain. Select an arc, line, edge, or point."
                )
                return
            try:
                with ptutil.perf_timer("measurepath.rebuild", CMD_NAME):
                    _rebuild(start_entity, end_entity)
            except Exception:
                # Refresh regardless. Returning here left the previous
                # selection's length on screen next to the new picks, which
                # reads as the answer for them.
                ptutil.log(f"{CMD_NAME}: graph build failed\n{traceback.format_exc()}")
                _reset_graph_only()
                _resolve_and_draw(inputs)
                inputs.itemById(INPUT_STATUS).text = (
                    "Could not read the geometry around one of these selections. "
                    "Try picking a different point, curve, or edge."
                )
                return
            _resolve_and_draw(inputs)

    except Exception:
        ptutil.log(f"{CMD_NAME}: inputChanged failed\n{traceback.format_exc()}")


def _reset_graph_only() -> None:
    global _graph, _start_nodes, _end_nodes, _seeds, _tail, _candidates
    global _pending_node, _marker_start, _marker_end, _path_segs
    _path_segs = []
    _graph = None
    _start_nodes = ()
    _end_nodes = ()
    _seeds = {}
    _tail = None
    _candidates = []
    _pending_node = None
    _marker_start = ()
    _marker_end = ()


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Copy the measured length to the clipboard."""
    try:
        if _result_cm <= 0.0:
            return
        ptutil.clipText(_format(_result_cm))
    except Exception:
        ptutil.log(f"{CMD_NAME}: execute failed\n{traceback.format_exc()}")


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    global local_handlers, _cmd_inputs, _active_command
    try:
        _clear_graphics()
        adsk.core.Application.get().activeViewport.refresh()
    except Exception:
        pass
    _reset_state()
    _cmd_inputs = None
    _active_command = None
    local_handlers = []
