# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Flatten Surface - lay curved faces flat, show where the material has to
# stretch or gather, and commit the result as a sketch.
#
# All Fusion API contact lives here. The flattening itself is in flatten.py and
# the report writing in report.py; neither imports adsk, so both are unit tested
# outside Fusion. Background and sources: docs/dev/Flatten Surface research.md.

import math
import os
import tempfile
import time
import traceback

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from . import flatten, report

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Flatten Surface"
CMD_ID = "PTPM_flattensurface"
CMD_Description = (
    "Flatten curved faces into a flat pattern, preview how far the material "
    "has to stretch or gather, and create a sketch of the result."
)
IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []

INPUT_FACES = "fs_faces"
INPUT_PLANE = "fs_plane"
INPUT_TRIAD = "fs_triad"
INPUT_QUALITY = "fs_quality"
INPUT_RELAX = "fs_relax"
INPUT_REPORT = "fs_report"
INPUT_STATS = "fs_stats"

_GFX_TAG = f"{CMD_ID}_gfx"

# Mesh fineness per quality level, as (sag tolerance, longest triangle side),
# both fractions of the selection's bounding-box diagonal so the same setting
# behaves the same on a watch case and on a boat hull.
#
# The side-length cap matters as much as the tolerance. Sag alone leaves a
# planar face as two enormous triangles however fine the setting, which both
# conditions the solver badly and leaves far too few nodes along that face's
# edges to weld against a curved neighbour meshed much more finely.
_QUALITY = {
    "Coarse": (0.014, 0.16),
    "Medium": (0.006, 0.09),
    "Fine": (0.0025, 0.05),
}
_DEFAULT_QUALITY = "Medium"

# The solver is pure Python, so triangle count is the whole performance story:
# roughly 4000 triangles is a one-second preview and 10000 would be ten. Past
# the cap the mesh is coarsened rather than left to hang the dialog.
_MAX_TRIANGLES = 4000
_COARSEN_ATTEMPTS = 3

# Boundary points closer than this fraction of the pattern size to the line
# between their neighbours are dropped before a spline is fitted through them.
_SIMPLIFY_FRACTION = 0.0015

_COLOR_SEAM = (90, 90, 90, 255)

# Selections, captured while the dialog is open because a SelectionCommandInput
# cannot be read reliably from execute (see lib/ptAddInUtils/selection_utils.py).
_picks: dict = {}

# One solve is reused across triad drags, redraws and the final commit. The
# model cannot change while the dialog is open, so the only things that
# invalidate it are the face set and the two solver settings.
_solve_cache_key = None
_solve_cache = None
_frame = None
_cmd_inputs = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def start():
    """Register the command and add it to the Power Tools panel."""
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
        ptutil.handle_error(f"{CMD_NAME}.start")


def stop():
    """Remove the control, the definition, and any graphics left behind."""
    try:
        _clear_graphics()
        panel = _ui_bootstrap.get_power_tools_panel()
        if panel:
            existing = panel.controls.itemById(CMD_ID)
            if existing:
                existing.deleteMe()
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}.stop")


def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    """Build the dialog and wire the per-invocation handlers."""
    global _cmd_inputs
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox(f"{CMD_NAME} needs an open design.", CMD_NAME)
            return

        _reset_state()

        cmd = args.command
        inputs = cmd.commandInputs
        # Cached so the preview and the commit can read the settings without
        # being handed the inputs collection.
        _cmd_inputs = inputs

        faces = inputs.addSelectionInput(
            INPUT_FACES, "Faces", "Select the faces to flatten."
        )
        faces.addSelectionFilter("Faces")
        faces.setSelectionLimits(1, 0)
        faces.tooltip = (
            "Faces that touch are flattened together as one piece. Faces that "
            "do not touch are laid out side by side."
        )

        plane = inputs.addSelectionInput(
            INPUT_PLANE,
            "Place on",
            "Select a plane or planar face to lay the pattern on.",
        )
        plane.addSelectionFilter("ConstructionPlanes")
        plane.addSelectionFilter("PlanarFaces")
        plane.setSelectionLimits(1, 1)

        # Created hidden with an identity transform; it is moved onto the
        # placement plane and shown once that plane is picked.
        triad = inputs.addTriadCommandInput(INPUT_TRIAD, adsk.core.Matrix3D.create())
        triad.isVisible = False

        quality = inputs.addDropDownCommandInput(
            INPUT_QUALITY,
            "Mesh quality",
            adsk.core.DropDownStyles.TextListDropDownStyle,
        )
        for name in _QUALITY:
            quality.listItems.add(name, name == _DEFAULT_QUALITY)
        quality.tooltip = (
            "How finely the faces are meshed before flattening. Finer measures "
            "the distortion more precisely but takes longer."
        )

        relax = inputs.addBoolValueInput(INPUT_RELAX, "Relax pattern", True, "", True)
        relax.tooltip = (
            "Spread the error between shape and size instead of leaving it all "
            "in size. Turn off for a faster, angle-true preview."
        )

        write_report = inputs.addBoolValueInput(
            INPUT_REPORT, "Write report", True, "", False
        )
        write_report.tooltip = (
            "Save a strain map and summary beside the document when the "
            "command finishes."
        )

        stats = inputs.addTextBoxCommandInput(
            INPUT_STATS, "", "Select faces and a plane.", 3, True
        )
        stats.isFullWidth = True

        ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
        ptutil.add_handler(
            cmd.executePreview,
            command_execute_preview,
            local_handlers=local_handlers,
        )
        ptutil.add_handler(
            cmd.inputChanged, command_input_changed, local_handlers=local_handlers
        )
        ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    except Exception:
        ui.messageBox(f"{CMD_NAME}: setup failed.\n{traceback.format_exc()}", CMD_NAME)


def _reset_state() -> None:
    global _solve_cache_key, _solve_cache, _frame, _cmd_inputs
    _picks.clear()
    _solve_cache_key = None
    _solve_cache = None
    _frame = None
    _cmd_inputs = None


def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    """Drop handlers, state and graphics when the dialog closes."""
    global local_handlers
    try:
        _clear_graphics()
    finally:
        local_handlers = []
        _reset_state()


# ---------------------------------------------------------------------------
# Placement plane
# ---------------------------------------------------------------------------
def _plane_frame(entity):
    """Build a coordinate frame for the placement plane.

    The frame is computed here rather than taken from the eventual sketch,
    because the manipulator has to be positioned before any sketch exists. The
    two are reconciled at commit time by running the points through
    ``Sketch.modelToSketchSpace``, so the axes chosen here need only be stable.

    Args:
        entity: A ConstructionPlane or a planar BRepFace.

    Returns:
        ``(origin, x_axis, y_axis, normal)`` as Vector3D/Point3D, or None if
        *entity* carries no plane geometry.
    """
    geometry = None
    construction = adsk.fusion.ConstructionPlane.cast(entity)
    if construction:
        geometry = construction.geometry
    else:
        face = adsk.fusion.BRepFace.cast(entity)
        if face:
            geometry = adsk.core.Plane.cast(face.geometry)
    if not geometry:
        return None

    origin = geometry.origin
    normal = geometry.normal.copy()
    normal.normalize()

    # Take whichever world axis leans least on the normal and project it into
    # the plane. For the standard planes this hands back the expected axes.
    axes = (
        adsk.core.Vector3D.create(1.0, 0.0, 0.0),
        adsk.core.Vector3D.create(0.0, 1.0, 0.0),
        adsk.core.Vector3D.create(0.0, 0.0, 1.0),
    )
    seed = min(axes, key=lambda axis: abs(axis.dotProduct(normal)))
    projection = normal.copy()
    projection.scaleBy(seed.dotProduct(normal))
    x_axis = seed.copy()
    x_axis.subtract(projection)
    if x_axis.length < 1e-9:
        return None
    x_axis.normalize()
    y_axis = normal.crossProduct(x_axis)
    y_axis.normalize()
    return origin, x_axis, y_axis, normal


def _triad_offset():
    """How far the manipulator has been dragged, in placement-plane axes.

    Returns:
        ``(du, dv)`` in centimetres, or (0.0, 0.0) when there is nothing to
        read. Read from the matrix rather than xTranslation/yTranslation so the
        answer does not depend on which frame those are expressed in.
    """
    if _frame is None or _cmd_inputs is None:
        return 0.0, 0.0
    triad = adsk.core.TriadCommandInput.cast(_cmd_inputs.itemById(INPUT_TRIAD))
    if triad is None:
        return 0.0, 0.0
    origin, x_axis, y_axis, _normal = _frame
    try:
        moved = triad.transform.translation
    except Exception:
        return 0.0, 0.0
    delta = adsk.core.Vector3D.create(
        moved.x - origin.x, moved.y - origin.y, moved.z - origin.z
    )
    return delta.dotProduct(x_axis), delta.dotProduct(y_axis)


def _to_model(u: float, v: float, du: float, dv: float):
    """Map a flattened point onto the placement plane in model space."""
    origin, x_axis, y_axis, _normal = _frame
    return adsk.core.Point3D.create(
        origin.x + (u + du) * x_axis.x + (v + dv) * y_axis.x,
        origin.y + (u + du) * x_axis.y + (v + dv) * y_axis.y,
        origin.z + (u + du) * x_axis.z + (v + dv) * y_axis.z,
    )


# ---------------------------------------------------------------------------
# Tessellation and solve
# ---------------------------------------------------------------------------
def _tessellate(faces, quality_name):
    """Mesh the selected faces, coarsening if the result is too big to solve.

    Args:
        faces: The selected BRepFace objects.
        quality_name: A key of :data:`_QUALITY`.

    Returns:
        ``(meshes, coarsened)`` where meshes is the list of (coords, triangles)
        pairs flatten.py expects, and coarsened says whether the requested
        quality had to be reduced to stay inside the triangle budget.
    """
    diagonal = _selection_diagonal(faces)
    sag_fraction, side_fraction = _QUALITY[quality_name]
    tolerance = max(diagonal * sag_fraction, 1e-4)
    side = max(diagonal * side_fraction, 1e-3)

    for attempt in range(_COARSEN_ATTEMPTS):
        meshes = []
        total = 0
        for face in faces:
            calculator = face.meshManager.createMeshCalculator()
            calculator.surfaceTolerance = tolerance
            calculator.maxSideLength = side
            mesh = calculator.calculate()
            if mesh is None:
                continue
            flat = mesh.nodeCoordinatesAsDouble
            coords = [
                (flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat), 3)
            ]
            indices = mesh.nodeIndices
            triangles = [
                (indices[i], indices[i + 1], indices[i + 2])
                for i in range(0, len(indices), 3)
            ]
            meshes.append((coords, triangles))
            total += len(triangles)

        if total <= _MAX_TRIANGLES or attempt == _COARSEN_ATTEMPTS - 1:
            return meshes, attempt > 0
        # Triangle count grows with the square of the linear density, so both
        # controls move by the square root of the overshoot.
        factor = math.sqrt(total / _MAX_TRIANGLES)
        tolerance *= factor
        side *= factor

    return [], False


def _selection_diagonal(faces) -> float:
    """Bounding-box diagonal of the selected faces, in centimetres."""
    box = None
    for face in faces:
        try:
            face_box = face.boundingBox
        except Exception:
            continue
        if box is None:
            box = face_box
        else:
            box.combine(face_box)
    if box is None:
        return 1.0
    return max(
        math.sqrt(
            (box.maxPoint.x - box.minPoint.x) ** 2
            + (box.maxPoint.y - box.minPoint.y) ** 2
            + (box.maxPoint.z - box.minPoint.z) ** 2
        ),
        1e-6,
    )


def _selection_key(faces, quality_name, relax):
    """A cache key that changes when the solve would change."""
    tokens = []
    for face in faces:
        try:
            tokens.append(face.entityToken)
        except Exception:
            tokens.append(str(id(face)))
    return (tuple(tokens), quality_name, relax)


def _solve():
    """Flatten the current selection, reusing the previous result when valid.

    Returns:
        A ``(FlattenResult, coarsened)`` pair, or (None, False) when there is
        nothing to flatten.
    """
    global _solve_cache_key, _solve_cache

    faces = [
        face
        for face in (
            adsk.fusion.BRepFace.cast(e) for e in ptutil.picked(_picks, INPUT_FACES)
        )
        if face
    ]
    if not faces:
        return None, False

    quality_name = _current_quality()
    relax = _current_relax()
    key = _selection_key(faces, quality_name, relax)
    if key == _solve_cache_key and _solve_cache is not None:
        return _solve_cache

    started = time.perf_counter()
    meshes, coarsened = _tessellate(faces, quality_name)
    if not meshes:
        return None, False
    result = flatten.flatten_meshes(meshes, relax=relax)
    ptutil.log(
        f"{CMD_NAME}: flattened {result.stats.triangles} triangles in "
        f"{time.perf_counter() - started:.2f}s "
        f"(quality={quality_name}, relax={relax})"
    )

    _solve_cache_key = key
    _solve_cache = (result, coarsened)
    return _solve_cache


def _current_quality() -> str:
    if _cmd_inputs is None:
        return _DEFAULT_QUALITY
    dropdown = adsk.core.DropDownCommandInput.cast(_cmd_inputs.itemById(INPUT_QUALITY))
    if dropdown and dropdown.selectedItem:
        return dropdown.selectedItem.name
    return _DEFAULT_QUALITY


def _current_relax() -> bool:
    if _cmd_inputs is None:
        return True
    toggle = adsk.core.BoolValueCommandInput.cast(_cmd_inputs.itemById(INPUT_RELAX))
    return True if toggle is None else toggle.value


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    """Track selections and settings. Never draws - see executePreview."""
    global _frame, _solve_cache_key, _solve_cache
    try:
        ptutil.capture_selections(args.inputs, _picks, INPUT_FACES, INPUT_PLANE)

        changed = args.input.id
        if changed in (INPUT_FACES, INPUT_QUALITY, INPUT_RELAX):
            _solve_cache_key = None
            _solve_cache = None

        if changed == INPUT_PLANE:
            entity = ptutil.picked_one(_picks, INPUT_PLANE)
            _frame = _plane_frame(entity) if entity else None
            _place_triad(args.inputs)
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}.command_input_changed")


def _place_triad(inputs) -> None:
    """Move the manipulator onto the placement plane, or hide it again."""
    triad = adsk.core.TriadCommandInput.cast(inputs.itemById(INPUT_TRIAD))
    if triad is None:
        return
    if _frame is None:
        triad.isVisible = False
        return

    origin, x_axis, y_axis, normal = _frame
    matrix = adsk.core.Matrix3D.create()
    matrix.setWithCoordinateSystem(origin, x_axis, y_axis, normal)
    triad.transform = matrix
    # Only in-plane movement is meaningful: the pattern is flat and lives on
    # the chosen plane, so lifting or spinning it would only misplace it.
    triad.hideAll()
    triad.isXTranslationVisible = True
    triad.isYTranslationVisible = True
    triad.isXYPlaneTranslationVisible = True
    triad.isVisible = True


def command_execute_preview(args: adsk.core.CommandEventArgs) -> None:
    """Draw the flattened pattern shaded by strain.

    This is the ONLY place custom graphics are created: everything built during
    a preview lives in one transaction that Fusion aborts when the next preview
    fires, so graphics made anywhere else are undone almost immediately. See
    docs/dev/Custom graphics that stay painted.md.

    isValidResult is deliberately left False. Nothing here is document geometry
    worth keeping, and setting it True would skip execute, which is where the
    sketch is actually created.
    """
    try:
        _clear_graphics()
        result, coarsened = _solve()
        _update_stats(result, coarsened)
        if result is None or not result.tris or _frame is None:
            return
        _draw(result)
        app.activeViewport.refresh()
    except Exception:
        ptutil.log(f"{CMD_NAME}: preview failed\n{traceback.format_exc()}")


def _draw(result) -> None:
    """Build the coloured preview mesh and the seam overlay."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return
    group = design.rootComponent.customGraphicsGroups.add()
    group.id = _GFX_TAG
    # The preview lies on top of the plane the user may still want to pick.
    group.isSelectable = False

    du, dv = _triad_offset()
    limit = flatten.strain_limit(result.strain)

    coordinates = []
    colors = []
    for index, (u, v) in enumerate(result.uvs):
        point = _to_model(u, v, du, dv)
        coordinates.extend((point.x, point.y, point.z))
        colors.extend(flatten.strain_to_rgba(result.strain[index], limit))

    indices = []
    for a, b, c in result.tris:
        indices.extend((a, b, c))

    coords = adsk.fusion.CustomGraphicsCoordinates.create(coordinates)
    # Four shorts per vertex, RGBA, matching the coordinate count.
    coords.colors = colors
    mesh = group.addMesh(coords, indices, [], [])
    mesh.color = adsk.fusion.CustomGraphicsVertexColorEffect.create()

    _draw_seams(group, result, du, dv)


def _draw_seams(group, result, du: float, dv: float) -> None:
    """Trace the joins between selected faces over the preview."""
    if not result.seams:
        return
    effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(*_COLOR_SEAM)
    )
    for chain in result.seams:
        points = [_to_model(*result.uvs[index], du, dv) for index in chain]
        for start, end in zip(points, points[1:], strict=False):
            segment = group.addCurve(adsk.core.Line3D.create(start, end))
            segment.color = effect
            segment.weight = 1.0


def _update_stats(result, coarsened: bool) -> None:
    """Write the headline numbers into the dialog."""
    if _cmd_inputs is None:
        return
    box = adsk.core.TextBoxCommandInput.cast(_cmd_inputs.itemById(INPUT_STATS))
    if box is None:
        return

    if result is None or not result.tris:
        box.formattedText = "Select faces and a plane."
        return

    stats = result.stats
    lines = [
        f"Stretch up to {stats.max_strain * 100.0:+.2f}%, "
        f"gather down to {stats.min_strain * 100.0:+.2f}%.",
        f"Average {stats.mean_abs_strain * 100.0:.2f}% over "
        f"{stats.triangles} triangles.",
    ]
    if stats.islands > 1:
        lines.append(f"{stats.islands} separate pieces.")
    if coarsened:
        lines.append("Mesh coarsened to keep the preview responsive.")
    if stats.flipped:
        lines.append(
            f"Warning: {stats.flipped} triangles folded over. Try a finer mesh "
            "or fewer faces."
        )
    box.formattedText = "<br/>".join(lines)


def command_execute(args: adsk.core.CommandEventArgs) -> None:
    """Create the sketch, and the report when it was asked for."""
    try:
        result, _coarsened = _solve()
        if result is None or not result.tris:
            ui.messageBox("Nothing to flatten.", CMD_NAME)
            return
        if _frame is None:
            ui.messageBox("Select a plane to place the pattern on.", CMD_NAME)
            return

        sketch = _create_sketch(result)
        if sketch is None:
            return
        if _wants_report():
            _write_report(result)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed.\n{traceback.format_exc()}", CMD_NAME)


def _wants_report() -> bool:
    if _cmd_inputs is None:
        return False
    toggle = adsk.core.BoolValueCommandInput.cast(_cmd_inputs.itemById(INPUT_REPORT))
    return bool(toggle and toggle.value)


def _create_sketch(result):
    """Draw the flat pattern into a new sketch on the placement plane.

    Points are built in model space from the frame taken off the placement
    plane, then handed to ``modelToSketchSpace`` rather than being written as
    sketch coordinates directly. That way the sketch's own axes - which Fusion
    chooses, and which need not match the frame here - cannot mirror or rotate
    the pattern.

    Note that a placement plane belonging to an occurrence is proxied, and
    proxy geometry reads in root coordinates while the sketch resolves against
    its parent component. Flattening onto a plane inside an occurrence is
    therefore the case to check first if a pattern lands somewhere unexpected.
    """
    design = adsk.fusion.Design.cast(app.activeProduct)
    plane_entity = ptutil.picked_one(_picks, INPUT_PLANE)
    if not design or plane_entity is None:
        return None

    component = design.activeComponent or design.rootComponent
    sketch = component.sketches.add(plane_entity)
    sketch.name = f"{CMD_NAME} pattern"
    du, dv = _triad_offset()
    tolerance = _pattern_tolerance(result)

    # Thousands of curve additions each trigger a solve otherwise.
    sketch.isComputeDeferred = True
    try:
        for loop in result.boundary:
            points = flatten.simplify_loop(
                [result.uvs[i] for i in loop], tolerance, closed=True
            )
            _add_spline(sketch, points, du, dv, closed=True)

        for chain in result.seams:
            points = flatten.simplify_loop(
                [result.uvs[i] for i in chain], tolerance, closed=False
            )
            _add_seam(sketch, points, du, dv)

        _mark_extremes(sketch, result, du, dv)
    finally:
        sketch.isComputeDeferred = False
    return sketch


def _pattern_tolerance(result) -> float:
    """How far a boundary point may be moved when simplifying it."""
    if not result.uvs:
        return 0.0
    xs = [uv[0] for uv in result.uvs]
    ys = [uv[1] for uv in result.uvs]
    size = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    return size * _SIMPLIFY_FRACTION


def _add_spline(sketch, points, du: float, dv: float, closed: bool) -> None:
    """Fit a spline through *points*, in sketch space."""
    if len(points) < 3:
        return
    collection = adsk.core.ObjectCollection.create()
    for u, v in points:
        collection.add(sketch.modelToSketchSpace(_to_model(u, v, du, dv)))
    if closed:
        # Repeating the first point closes the curve; the sketch has no notion
        # of a closed fitted spline built from a bare point list.
        collection.add(collection.item(0))
    if collection.count < 3:
        return
    sketch.sketchCurves.sketchFittedSplines.add(collection)


def _add_seam(sketch, points, du: float, dv: float) -> None:
    """Draw a seam as construction lines, which stay exact where a fit would not."""
    if len(points) < 2:
        return
    mapped = [sketch.modelToSketchSpace(_to_model(u, v, du, dv)) for u, v in points]
    for start, end in zip(mapped, mapped[1:], strict=False):
        line = sketch.sketchCurves.sketchLines.addByTwoPoints(start, end)
        line.isConstruction = True


def _mark_extremes(sketch, result, du: float, dv: float) -> None:
    """Drop a sketch point on the worst stretch and the worst gather."""
    stats = result.stats
    for vertex in (stats.min_vertex, stats.max_vertex):
        if vertex is None or vertex < 0 or vertex >= len(result.uvs):
            continue
        u, v = result.uvs[vertex]
        sketch.sketchPoints.add(sketch.modelToSketchSpace(_to_model(u, v, du, dv)))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _write_report(result) -> None:
    """Write the strain map and summary, uploading them beside the document."""
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        document = app.activeDocument
        name = (document.name if document else "Untitled") or "Untitled"
        safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        safe = safe or "pattern"

        limit = flatten.strain_limit(result.strain)
        colors = [flatten.strain_to_rgba(value, limit) for value in result.strain]
        svg_name = f"{safe} flat pattern.svg"
        markdown_name = f"{safe} flat pattern.md"

        svg = report.svg_strain_map(
            result.uvs,
            result.tris,
            colors,
            result.boundary,
            limit,
            flatten.strain_to_rgba,
            title=f"{name} - flat pattern",
        )
        units = "cm"
        if design:
            units = design.unitsManager.defaultLengthUnits
        markdown = report.markdown_report(
            result.stats,
            document_name=name,
            face_count=len(ptutil.picked(_picks, INPUT_FACES)),
            quality=_current_quality(),
            relaxed=_current_relax(),
            svg_name=svg_name,
            units=units,
            timestamp=time.strftime("%Y-%m-%d %H:%M"),
        )

        folder = os.path.join(tempfile.gettempdir(), config.ADDIN_NAME, "flatten")
        os.makedirs(folder, exist_ok=True)
        svg_path = os.path.join(folder, svg_name)
        markdown_path = os.path.join(folder, markdown_name)
        with open(svg_path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        with open(markdown_path, "w", encoding="utf-8") as handle:
            handle.write(markdown)

        uploaded = _upload_beside_document(document, [markdown_path, svg_path])
        if uploaded:
            ui.messageBox(
                f"Report saved beside {name} in Fusion Team.",
                CMD_NAME,
            )
        else:
            ui.messageBox(
                "The document is not saved to Fusion Team, so the report was "
                f"written locally instead:\n\n{folder}",
                CMD_NAME,
            )
    except Exception:
        ptutil.log(f"{CMD_NAME}: report failed\n{traceback.format_exc()}")
        ui.messageBox(
            "The pattern sketch was created, but the report could not be "
            "written. See the log for details.",
            CMD_NAME,
        )


def _upload_beside_document(document, paths) -> bool:
    """Upload files into the document's own Fusion Team folder.

    Args:
        document: The active document.
        paths: Local file paths to upload.

    Returns:
        True when every file landed, False when the document has no cloud
        folder to upload into or an upload did not complete.
    """
    try:
        data_file = document.dataFile if document else None
        folder = data_file.parentFolder if data_file else None
    except Exception:
        folder = None
    if folder is None:
        return False

    for path in paths:
        try:
            future = folder.uploadFile(path)
        except Exception:
            ptutil.log(f"{CMD_NAME}: uploadFile raised for {os.path.basename(path)}")
            return False
        ok, message = ptutil.wait_for_upload(
            future, os.path.basename(path), log_fn=ptutil.log
        )
        if not ok:
            ptutil.log(f"{CMD_NAME}: {message}")
            return False
    return True


# ---------------------------------------------------------------------------
# Graphics housekeeping
# ---------------------------------------------------------------------------
def _clear_graphics() -> None:
    """Delete every graphics group this command created.

    Groups are found by their id tag rather than a cached reference, which goes
    stale across preview cycles and edit-state changes.
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
