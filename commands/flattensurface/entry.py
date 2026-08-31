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
import time
import traceback

import adsk.core
import adsk.fusion

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
INPUT_CHAIN = "fs_chain"
INPUT_QUALITY = "fs_quality"
INPUT_RELAX = "fs_relax"
INPUT_WIREFRAME = "fs_wireframe"
INPUT_EXPORT = "fs_export"
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
_COLOR_WIRE = (45, 45, 45, 255)

# The Min and Max markers take the two ends of the strain ramp, so a marker's
# colour says which end of the scale it sits at without reading the label.
_COLOR_MIN = (59, 76, 192, 255)
_COLOR_MAX = (180, 4, 38, 255)

# Marker and label geometry in screen pixels, converted to centimetres against
# the current view so they hold their size however far the user zooms.
_MARKER_PX_RADIUS = 6.0
_LABEL_PX_SIZE = 11.7
_LABEL_PX_OFFSET = 11.0
_LABEL_FONT = "Arial"

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

# Guards the tangent-chain expansion. Adding to a selection input fires
# inputChanged again, so without this the walk would re-enter itself; the
# count lets a face be deselected without the chain immediately restoring it.
_chaining = False
_face_count = 0


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

        # The plane comes first because nothing can be previewed without it:
        # there is nowhere to draw the pattern until it is picked. Its single-
        # selection limit also hands focus straight on to the face input.
        plane = inputs.addSelectionInput(
            INPUT_PLANE,
            "Place on",
            "Select a plane or planar face to lay the pattern on.",
        )
        plane.addSelectionFilter("ConstructionPlanes")
        plane.addSelectionFilter("PlanarFaces")
        plane.setSelectionLimits(1, 1)

        # Created with every handle hidden, and moved onto the placement plane
        # and revealed only once that plane is picked. hideAll is what actually
        # keeps it out of the viewport: isVisible governs the input's row in the
        # dialog, so on its own it leaves a full triad sitting at the origin
        # until the first plane selection reshapes it.
        triad = inputs.addTriadCommandInput(INPUT_TRIAD, adsk.core.Matrix3D.create())
        triad.hideAll()
        triad.isVisible = False

        chain = inputs.addBoolValueInput(INPUT_CHAIN, "Tangent chain", True, "", False)
        chain.tooltip = (
            "Picking one face also picks every face joined to it by a smooth "
            "edge, so a filleted run comes in with a single click."
        )

        faces = inputs.addSelectionInput(
            INPUT_FACES, "Faces", "Select the faces to flatten."
        )
        faces.addSelectionFilter("Faces")
        faces.setSelectionLimits(1, 0)
        faces.tooltip = (
            "Faces that touch are flattened together as one piece. Faces that "
            "do not touch are laid out side by side."
        )

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

        wireframe = inputs.addBoolValueInput(
            INPUT_WIREFRAME, "Show mesh", True, "", False
        )
        wireframe.tooltip = (
            "Draw the triangles the strain was measured on. Useful for judging "
            "whether the mesh is fine enough to trust."
        )

        # isCheckBox=False with an empty resource folder renders as a plain
        # text button, which is what a one-shot action wants.
        export = inputs.addBoolValueInput(INPUT_EXPORT, "Export SVG", False, "", False)
        export.tooltip = (
            "Save the strain map as an SVG file. Opens straight in a browser "
            "and prints without going fuzzy."
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
    global _chaining, _face_count
    _picks.clear()
    _solve_cache_key = None
    _solve_cache = None
    _frame = None
    _cmd_inputs = None
    _chaining = False
    _face_count = 0


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


def _wants_chain() -> bool:
    if _cmd_inputs is None:
        return False
    toggle = adsk.core.BoolValueCommandInput.cast(_cmd_inputs.itemById(INPUT_CHAIN))
    return bool(toggle and toggle.value)


def _wants_wireframe() -> bool:
    if _cmd_inputs is None:
        return False
    toggle = adsk.core.BoolValueCommandInput.cast(_cmd_inputs.itemById(INPUT_WIREFRAME))
    return bool(toggle and toggle.value)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    """Track selections and settings. Never draws - see executePreview."""
    global _frame, _solve_cache_key, _solve_cache
    try:
        ptutil.capture_selections(args.inputs, _picks, INPUT_FACES, INPUT_PLANE)

        changed = args.input.id
        if changed in (INPUT_FACES, INPUT_QUALITY, INPUT_RELAX, INPUT_CHAIN):
            _solve_cache_key = None
            _solve_cache = None

        if changed in (INPUT_FACES, INPUT_CHAIN):
            _grow_tangent_chain(args.inputs)

        if changed == INPUT_PLANE:
            entity = ptutil.picked_one(_picks, INPUT_PLANE)
            _frame = _plane_frame(entity) if entity else None
            _place_triad(args.inputs)

        if changed == INPUT_EXPORT:
            button = adsk.core.BoolValueCommandInput.cast(args.input)
            if button:
                button.value = False  # momentary
            _export_svg()
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}.command_input_changed")


# ---------------------------------------------------------------------------
# Tangent chaining
# ---------------------------------------------------------------------------
def _face_key(face) -> str:
    """A stable identity for a face.

    Fusion hands back a fresh wrapper on every access, so identity has to come
    from the entity token rather than the Python object.
    """
    try:
        return face.entityToken
    except Exception:
        # Tokenless in some contexts; position is enough to deduplicate within
        # a single walk.
        box = face.boundingBox
        return (
            f"{box.minPoint.x:.6f},{box.minPoint.y:.6f},{box.minPoint.z:.6f},"
            f"{box.maxPoint.x:.6f},{box.maxPoint.y:.6f},{box.maxPoint.z:.6f}"
        )


def tangent_closure(seeds: list) -> dict:
    """Every face reachable from *seeds* across smooth edges.

    ``tangentiallyConnectedFaces`` only reports a face's immediate smooth
    neighbours, so reaching the whole of a filleted run means walking outward
    from each of them in turn.

    Args:
        seeds: Faces the user picked.

    Returns:
        Face key -> face, including the seeds.
    """
    found: dict = {}
    queue = list(seeds)
    while queue:
        face = queue.pop()
        key = _face_key(face)
        if key in found:
            continue
        found[key] = face
        try:
            neighbours = list(face.tangentiallyConnectedFaces)
        except Exception:
            continue
        for neighbour in neighbours:
            if _face_key(neighbour) not in found:
                queue.append(neighbour)
    return found


def _in_context(face, occurrence):
    """Re-proxy a face into the occurrence its seed came from.

    A proxied face's smooth neighbours may come back native rather than
    proxied, and a native face would be measured in the wrong space.
    """
    if occurrence is None:
        return face
    try:
        return face.createForAssemblyContext(occurrence)
    except Exception:
        return face


def _grow_tangent_chain(inputs) -> None:
    """Add every face smoothly joined to the ones already picked."""
    global _chaining, _face_count
    if _chaining or not _wants_chain():
        _face_count = _selected_face_count(inputs)
        return

    picker = adsk.core.SelectionCommandInput.cast(inputs.itemById(INPUT_FACES))
    if picker is None:
        return

    count = picker.selectionCount
    if count <= _face_count:
        # Deselecting must be allowed to stick, so only a growing selection
        # triggers the walk.
        _face_count = count
        return

    seeds = []
    for index in range(count):
        try:
            seeds.append(picker.selection(index).entity)
        except Exception:
            continue
    if not seeds:
        _face_count = count
        return

    occurrence = getattr(seeds[0], "assemblyContext", None)
    have = {_face_key(face) for face in seeds}
    extra = [
        _in_context(face, occurrence)
        for key, face in tangent_closure(seeds).items()
        if key not in have
    ]
    if not extra:
        _face_count = count
        return

    _chaining = True
    try:
        for face in extra:
            try:
                picker.addSelection(face)
            except Exception:
                ptutil.log(f"{CMD_NAME}: could not chain onto a tangent face")
    finally:
        _chaining = False
    _face_count = picker.selectionCount
    ptutil.capture_selections(inputs, _picks, INPUT_FACES, INPUT_PLANE)


def _selected_face_count(inputs) -> int:
    picker = adsk.core.SelectionCommandInput.cast(inputs.itemById(INPUT_FACES))
    return picker.selectionCount if picker else 0


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

    if _wants_wireframe():
        _draw_wireframe(group, coordinates, result)
    _draw_seams(group, result, du, dv)
    _draw_extremes(group, result, du, dv)


def _draw_wireframe(group, coordinates: list, result) -> None:
    """Outline every triangle the strain was measured on.

    Drawn as one lines entity rather than a curve each: a few thousand separate
    additions is slow enough to be felt on every redraw.

    A fresh coordinates object is built because the mesh's own carries per-vertex
    colours, which would paint the wireframe in the strain colours and leave it
    invisible against the surface it is drawn over.
    """
    edges = flatten.mesh_edges(result.tris)
    if not edges:
        return
    index_list = []
    for a, b in edges:
        index_list.extend((a, b))
    plain = adsk.fusion.CustomGraphicsCoordinates.create(coordinates)
    lines = group.addLines(plain, index_list, False)
    if lines is None:
        return
    lines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(*_COLOR_WIRE)
    )
    lines.weight = 1.0
    # Above the shaded mesh, below the seam and marker overlays.
    lines.depthPriority = 1


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
            segment.weight = 2.0
            # Above the wireframe, so turning the mesh on does not bury the
            # seams in a field of identical-looking lines.
            segment.depthPriority = 2


def _draw_extremes(group, result, du: float, dv: float) -> None:
    """Mark and label the worst gather and the worst stretch.

    The colour map shows the whole field but not where its extremes are; on a
    large pattern with a gentle gradient the worst spot is genuinely hard to
    find by eye, and it is the spot that decides whether the pattern is usable.
    """
    stats = result.stats
    if not flatten.is_measurable(stats):
        # With no distortion to find, the worst spot is wherever the arithmetic
        # happened to land. Marking it would invent a defect.
        return
    marks = (
        (stats.min_vertex, _COLOR_MIN, f"Min {stats.min_strain * 100.0:+.2f}%"),
        (stats.max_vertex, _COLOR_MAX, f"Max {stats.max_strain * 100.0:+.2f}%"),
    )
    for vertex, rgba, label in marks:
        if vertex is None or vertex < 0 or vertex >= len(result.uvs):
            continue
        u, v = result.uvs[vertex]
        point = _to_model(u, v, du, dv)
        _draw_marker(group, point, rgba, label)


def _draw_marker(group, point, rgba, label: str) -> None:
    """Draw one labelled sphere at *point*, held at a constant screen size."""
    scale = _px_per_cm(point)
    if scale:
        radius_cm = _MARKER_PX_RADIUS / scale
        text_cm = _LABEL_PX_SIZE / scale
        offset_cm = _LABEL_PX_OFFSET / scale
    else:
        radius_cm = 0.08
        text_cm = 0.2
        offset_cm = 0.14

    colour = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(*rgba)
    )
    body = adsk.fusion.TemporaryBRepManager.get().createSphere(point, radius_cm)
    if body is not None:
        dot = group.addBRepBody(body)
        dot.color = colour
        dot.depthPriority = 3
        dot.isSelectable = False

    _billboard_text(group, point, label, colour, text_cm, offset_cm)


def _px_per_cm(point) -> float | None:
    """Screen pixels per centimetre near *point*.

    Sampling the projected basis keeps a marker the same size on screen without
    relying on CustomGraphicsViewScale, which is unproven in this add-in.
    """
    try:
        viewport = app.activeViewport
        origin = viewport.modelToViewSpace(point)
        if origin is None:
            return None
        best = None
        for offset in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
            probe = viewport.modelToViewSpace(
                adsk.core.Point3D.create(
                    point.x + offset[0], point.y + offset[1], point.z + offset[2]
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


def _billboard_text(group, point, label, colour, text_cm, offset_cm) -> None:
    """Place *label* near *point*, turned to face the camera.

    addText places the string parallel to X-Y with its origin at the upper-left
    corner, so on its own it would be edge-on from most viewpoints. Billboarding
    turns it to face the camera; the transform only carries position.
    """
    label_point = adsk.core.Point3D.create(
        point.x + offset_cm, point.y + offset_cm, point.z
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
        # Anchor on the label's own point, not the marker: anchoring at the
        # marker rotates the offset with the camera and the label orbits it.
        billboard = adsk.fusion.CustomGraphicsBillBoard.create(label_point)
        billboard.billBoardStyle = (
            adsk.fusion.CustomGraphicsBillBoardStyles.ScreenBillBoardStyle
        )
        text.billBoarding = billboard
    except Exception:
        # Readable but view-dependent beats no label at all.
        ptutil.log(f"{CMD_NAME}: billboarding unavailable for the {label} label")


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
    if flatten.is_measurable(stats):
        lines = [
            f"Stretch up to {stats.max_strain * 100.0:+.2f}%, "
            f"gather down to {stats.min_strain * 100.0:+.2f}%.",
            f"Average {stats.mean_abs_strain * 100.0:.2f}% over "
            f"{stats.triangles} triangles.",
        ]
    else:
        # Saying "up to +0.00%" over a vividly coloured map reads as a fault.
        # This shape genuinely has a flat form, so say that instead.
        lines = [
            "<b>Flattens exactly.</b> No measurable distortion over "
            f"{stats.triangles} triangles."
        ]
    if stats.islands > 1:
        lines.append(f"{stats.islands} separate pieces.")
    if stats.seams_cut:
        lines.append(
            f"Slit open along {stats.seams_cut} seam"
            f"{'s' if stats.seams_cut > 1 else ''} to lay flat."
        )
    if stats.cracks_stitched:
        lines.append(
            f"Closed {stats.cracks_stitched} gap"
            f"{'s' if stats.cracks_stitched > 1 else ''} where faces met unevenly."
        )
    if stats.bent_points:
        # Without this the strain reads as a defect. A plane or a cylinder
        # flattens exactly, and so do any number of them joined edge to edge -
        # but where three faces meet at a point there is real curvature, and no
        # flat pattern can hold it.
        lines.append(
            f"{stats.bent_points} corner"
            f"{'s' if stats.bent_points > 1 else ''} hold up to "
            f"{math.degrees(stats.worst_defect):.0f}&deg; of curvature, so some "
            "distortion here cannot be avoided."
        )
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

        _create_sketch(result)
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed.\n{traceback.format_exc()}", CMD_NAME)


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
            _add_chain(
                sketch,
                [result.uvs[i] for i in loop],
                du,
                dv,
                tolerance,
                closed=True,
                construction=False,
            )

        for chain in result.seams:
            _add_chain(
                sketch,
                [result.uvs[i] for i in chain],
                du,
                dv,
                tolerance,
                closed=False,
                construction=True,
            )

        _mark_extremes(sketch, result, du, dv)
    finally:
        sketch.isComputeDeferred = False
    return sketch


def _add_chain(
    sketch,
    points: list,
    du: float,
    dv: float,
    tolerance: float,
    closed: bool,
    construction: bool,
) -> None:
    """Draw one boundary loop or seam as the geometry it actually is.

    The chain is cut at its corners first, because a single curve fitted around
    a corner averages it away and the pattern loses its shape. Each corner-to-
    corner run is then matched against lines, arcs and circles, so a bolt hole
    comes out as a circle and a fillet as an arc rather than everything arriving
    as a spline.
    """
    runs = flatten.split_at_corners(points, closed=closed)
    # A closed chain with no corners in it is still the whole loop, and only a
    # whole loop can come back as a circle.
    whole_loop = closed and len(runs) == 1
    for run in runs:
        for kind, piece in flatten.segment_curve(run, tolerance, closed=whole_loop):
            _add_segment(sketch, kind, piece, du, dv, tolerance, construction)


def _add_segment(
    sketch,
    kind: str,
    points: list,
    du: float,
    dv: float,
    tolerance: float,
    construction: bool,
) -> None:
    """Draw one recognised piece of the outline."""
    curves = sketch.sketchCurves
    curve = None

    if kind == "circle":
        fit = flatten.fit_circle(points)
        if fit is not None:
            centre = sketch.modelToSketchSpace(_to_model(fit[0], fit[1], du, dv))
            curve = curves.sketchCircles.addByCenterRadius(centre, fit[2])
    elif kind == "arc" and len(points) >= 3:
        mapped = _to_sketch(sketch, points, du, dv)
        curve = curves.sketchArcs.addByThreePoints(
            mapped[0], mapped[len(mapped) // 2], mapped[-1]
        )
    elif kind == "line" and len(points) >= 2:
        mapped = _to_sketch(sketch, [points[0], points[-1]], du, dv)
        curve = curves.sketchLines.addByTwoPoints(mapped[0], mapped[1])
    else:
        thinned = flatten.simplify_loop(points, tolerance)
        if len(thinned) < 3:
            if len(thinned) == 2:
                mapped = _to_sketch(sketch, thinned, du, dv)
                curve = curves.sketchLines.addByTwoPoints(mapped[0], mapped[1])
        else:
            collection = adsk.core.ObjectCollection.create()
            for point in _to_sketch(sketch, thinned, du, dv):
                collection.add(point)
            curve = curves.sketchFittedSplines.add(collection)

    if curve and construction:
        curve.isConstruction = True


def _to_sketch(sketch, points: list, du: float, dv: float) -> list:
    """Map pattern coordinates into the sketch's own space."""
    return [sketch.modelToSketchSpace(_to_model(u, v, du, dv)) for u, v in points]


def _pattern_tolerance(result) -> float:
    """How far a boundary point may be moved when simplifying it."""
    if not result.uvs:
        return 0.0
    xs = [uv[0] for uv in result.uvs]
    ys = [uv[1] for uv in result.uvs]
    size = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    return size * _SIMPLIFY_FRACTION


def _mark_extremes(sketch, result, du: float, dv: float) -> None:
    """Drop a sketch point on the worst stretch and the worst gather."""
    stats = result.stats
    for vertex in (stats.min_vertex, stats.max_vertex):
        if vertex is None or vertex < 0 or vertex >= len(result.uvs):
            continue
        u, v = result.uvs[vertex]
        sketch.sketchPoints.add(sketch.modelToSketchSpace(_to_model(u, v, du, dv)))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _export_svg() -> None:
    """Write the strain map to an SVG file the user picks.

    Writing straight to a chosen path, rather than uploading anywhere, is
    deliberate: the cloud upload this replaced had to be polled to completion,
    and polling from inside a command handler locks Fusion up.
    """
    try:
        result, _coarsened = _solve()
        if result is None or not result.tris:
            ui.messageBox("Select faces to flatten before exporting.", CMD_NAME)
            return

        document = app.activeDocument
        name = (document.name if document else "Untitled") or "Untitled"
        safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()

        dlg = ui.createFileDialog()
        dlg.title = "Export strain map"
        dlg.filter = "SVG files (*.svg);;All Files (*.*)"
        dlg.isMultiSelectEnabled = False
        dlg.initialFilename = f"{safe or 'pattern'} flat pattern.svg"
        if dlg.showSave() != adsk.core.DialogResults.DialogOK:
            return

        limit = flatten.strain_limit(result.strain)
        colors = [flatten.strain_to_rgba(value, limit) for value in result.strain]
        stats = result.stats
        svg = report.svg_strain_map(
            result.uvs,
            result.tris,
            colors,
            result.boundary,
            limit,
            flatten.strain_to_rgba,
            title=(
                f"{name} - flat pattern - "
                f"stretch {stats.max_strain * 100.0:+.2f}%, "
                f"gather {stats.min_strain * 100.0:+.2f}%"
                if flatten.is_measurable(stats)
                else f"{name} - flat pattern - flattens exactly"
            ),
        )
        with open(dlg.filename, "w", encoding="utf-8") as handle:
            handle.write(svg)
        ptutil.log(f"{CMD_NAME}: exported {dlg.filename}")
    except Exception:
        ptutil.log(f"{CMD_NAME}: export failed\n{traceback.format_exc()}")
        ui.messageBox("The strain map could not be exported.", CMD_NAME)


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
