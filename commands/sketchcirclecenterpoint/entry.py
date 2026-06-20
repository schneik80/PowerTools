# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import adsk.fusion
import os
import traceback
import math

from ...lib import ptAddInUtils as ptutil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Radial Hole Circle"
CMD_ID = "PTPM-sketchcirclecenterpoint"
CMD_Description = (
    "In an active sketch, interactively place a construction circle by selecting "
    "a center point and dragging to set the diameter. A sketch point is then "
    "automatically added and constrained vertically above the circle's center."
)
IS_PROMOTED = False

WORKSPACE_ID = config.design_workspace
TAB_ID = "SketchTab"
PANEL_ID = "SketchCreatePanel"

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local event handler references – must persist for the lifetime of the command.
local_handlers = []

# ---------------------------------------------------------------------------
# Preview state – shared between event handlers
# ---------------------------------------------------------------------------
_preview_center_model: adsk.core.Point3D | None = None   # world-space center
_preview_sketch: adsk.fusion.Sketch | None = None         # active sketch ref
_preview_selected_entity = None                           # original SketchPoint/Vertex
_cmd_inputs: adsk.core.CommandInputs | None = None        # live command inputs
_active_command: adsk.core.Command | None = None          # command ref for deferred execute

# args.position (MouseEventArgs) is in application-window coordinates while
# viewport.modelToViewSpace() returns viewport-local coordinates.  The two
# spaces share the same scale but differ by a constant offset equal to the
# viewport's top-left corner within the application window.  We calibrate
# this offset once at selection time and apply it on every mouseMove.
_selection_click_pos: adsk.core.Point2D | None = None   # window coords of the selection click
_vp_offset_x: float = 0.0   # window_x - viewport_local_x
_vp_offset_y: float = 0.0

# Tag used to find / delete the preview graphics group each frame.
_PREVIEW_GFX_NAME  = f"{CMD_ID}_preview"
_COMMIT_EVENT_ID   = f"{CMD_ID}_commit"   # custom event used to defer doExecute

# Set to True once geometry has been committed so neither a second click
# nor the OK-button fallback creates duplicate geometry.
_geometry_created: bool = False


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------

def start() -> None:
    try:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )
        ptutil.add_handler(cmd_def.commandCreated, command_created)

        sketch_tab = ui.allToolbarTabs.itemById(TAB_ID)
        if not sketch_tab:
            ptutil.log(f"{CMD_NAME}: Toolbar tab '{TAB_ID}' not found – command not added to UI.")
            return

        panel = sketch_tab.toolbarPanels.itemById(PANEL_ID)
        if not panel:
            ptutil.log(f"{CMD_NAME}: Panel '{PANEL_ID}' not found in '{TAB_ID}' – command not added to UI.")
            return

        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED

    except Exception:
        ptutil.log(f"{CMD_NAME} start() failed:\n{traceback.format_exc()}")


def stop() -> None:
    try:
        sketch_tab = ui.allToolbarTabs.itemById(TAB_ID)
        panel = sketch_tab.toolbarPanels.itemById(PANEL_ID) if sketch_tab else None
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()

        if command_definition:
            command_definition.deleteMe()

    except Exception:
        ptutil.log(f"{CMD_NAME} stop() failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Command created – builds dialog UI and wires up event handlers
# ---------------------------------------------------------------------------

def command_created(args: adsk.core.CommandCreatedEventArgs) -> None:
    global _cmd_inputs, _active_command
    ptutil.log(f"{CMD_NAME} Command Created Event")

    try:
        app_local = adsk.core.Application.get()
        product = app_local.activeProduct
        design = adsk.fusion.Design.cast(product)

        if not design or not isinstance(design.activeEditObject, adsk.fusion.Sketch):
            ui.messageBox(
                "A sketch must be active before running this command.\n\n"
                "Double-click a sketch in the browser to open it, then try again.",
                CMD_NAME,
            )
            args.command.doExecute(False)
            return

        cmd = args.command
        cmd.okButtonText = "Create"
        _active_command = cmd
        inputs = cmd.commandInputs
        _cmd_inputs = inputs

        # Center point selection
        center_sel = inputs.addSelectionInput(
            "center_point",
            "Circle Center",
            "Select a sketch point or vertex for the circle center, "
            "then move the mouse to preview the diameter.",
        )
        center_sel.addSelectionFilter("SketchPoints")
        center_sel.addSelectionFilter("Vertices")
        center_sel.setSelectionLimits(1, 1)

        # Diameter value input (Fusion internal unit = cm; default 25 mm)
        units_mgr = design.unitsManager
        diameter_input = inputs.addValueInput(
            "diameter",
            "Diameter",
            units_mgr.defaultLengthUnits,
            adsk.core.ValueInput.createByReal(2.5),
        )

        # Wire up all event handlers
        ptutil.add_handler(cmd.execute,         command_execute,         local_handlers=local_handlers)
        ptutil.add_handler(cmd.executePreview,  command_execute_preview, local_handlers=local_handlers)
        ptutil.add_handler(cmd.validateInputs,  command_validate,        local_handlers=local_handlers)
        ptutil.add_handler(cmd.inputChanged,    command_input_changed,   local_handlers=local_handlers)
        ptutil.add_handler(cmd.mouseMove,       command_mouse_move,      local_handlers=local_handlers)
        ptutil.add_handler(cmd.mouseClick,      command_mouse_click,     local_handlers=local_handlers)
        ptutil.add_handler(cmd.destroy,         command_destroy,         local_handlers=local_handlers)

        # Register the custom event used to defer doExecute outside the mouse
        # event stack (Fusion raises RuntimeError if doExecute is called from
        # within any command event handler).
        app_local = adsk.core.Application.get()
        custom_event = app_local.registerCustomEvent(_COMMIT_EVENT_ID)
        ptutil.add_handler(custom_event, custom_event_commit, local_handlers=local_handlers)

    except Exception:
        ui.messageBox(f"{CMD_NAME}: Setup failed.\n{traceback.format_exc()}", CMD_NAME)


# ---------------------------------------------------------------------------
# inputChanged – capture center point as soon as it is selected
# ---------------------------------------------------------------------------

def command_input_changed(args: adsk.core.InputChangedEventArgs) -> None:
    global _preview_center_model, _preview_sketch, _preview_selected_entity

    if args.input.id != "center_point":
        return

    sel_input = adsk.core.SelectionCommandInput.cast(args.input)

    if sel_input.selectionCount == 1:
        app_local = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app_local.activeProduct)
        _preview_sketch = adsk.fusion.Sketch.cast(design.activeEditObject)

        entity = sel_input.selection(0).entity
        _preview_selected_entity = entity

        # SketchPoint.geometry is in sketch-local space (2-D, z=0 relative to
        # the sketch plane).  We must use worldGeometry to get the actual 3-D
        # model/world-space position so the preview circle lands in the right
        # place and the radius computed from the mouse position is meaningful.
        sk_pt = adsk.fusion.SketchPoint.cast(entity)
        if sk_pt and _preview_sketch:
            # Use sketch-local geometry → sketchToModelSpace for a reliable
            # world-space position (same pipeline used everywhere else in this
            # command).  worldGeometry can silently return the origin for some
            # sketch point types.
            local_pt = sk_pt.geometry   # Point3D in sketch 2-D coords (z=0)
            _preview_center_model = _preview_sketch.sketchToModelSpace(
                adsk.core.Point3D.create(local_pt.x, local_pt.y, 0.0)
            )
        else:
            # Vertex.geometry is already in model space
            _preview_center_model = entity.geometry

        # Calibrate the offset between args.position (window coords) and
        # viewport.modelToViewSpace (viewport-local coords) using the click
        # that just selected the center point.
        global _vp_offset_x, _vp_offset_y
        if _selection_click_pos is not None:
            vp = adsk.core.Application.get().activeViewport
            cs_screen = vp.modelToViewSpace(_preview_center_model)
            if cs_screen is not None:
                _vp_offset_x = _selection_click_pos.x - cs_screen.x
                _vp_offset_y = _selection_click_pos.y - cs_screen.y

        # Hide the satisfied selection input so Fusion stops routing mouse
        # events through its selection machinery.  This allows mouseMove to
        # fire freely while the user drags to set the diameter.
        sel_input.isVisible = False
        ptutil.log(
            f"{CMD_NAME}: center picked at "
            f"({_preview_center_model.x:.3f},{_preview_center_model.y:.3f},{_preview_center_model.z:.3f}) "
            f"– entering drag-to-set-diameter mode."
        )
    else:
        _preview_center_model = None
        _preview_sketch = None
        _preview_selected_entity = None
        sel_input.isVisible = True
        _clear_preview()


# ---------------------------------------------------------------------------
# mouseMove – live preview circle via Custom Graphics
# ---------------------------------------------------------------------------

def command_mouse_move(args: adsk.core.MouseEventArgs) -> None:
    global _cmd_inputs

    if _preview_center_model is None or _preview_sketch is None:
        return

    hit = _mouse_to_sketch_plane(args)
    if hit is None:
        return

    # Distance from center to mouse position = radius
    dx = hit.x - _preview_center_model.x
    dy = hit.y - _preview_center_model.y
    dz = hit.z - _preview_center_model.z
    radius = math.sqrt(dx * dx + dy * dy + dz * dz)

    if radius < 1e-6:
        return

    # Push the live diameter value back into the dialog input.
    # This also triggers executePreview which redraws the graphics.
    if _cmd_inputs:
        diam_input: adsk.core.ValueCommandInput = _cmd_inputs.itemById("diameter")
        if diam_input:
            diam_input.value = radius * 2.0

    _update_preview(radius, hit)
    adsk.core.Application.get().activeViewport.refresh()


# ---------------------------------------------------------------------------
# mouseClick – lock diameter at click position and commit the command
# ---------------------------------------------------------------------------

def command_mouse_click(args: adsk.core.MouseEventArgs) -> None:
    global _selection_click_pos

    # Capture every left-click window position.  When the center has not yet
    # been selected this records the click that will trigger the selection,
    # allowing inputChanged to calibrate the window→viewport-local offset.
    if args.button == adsk.core.MouseButtons.LeftMouseButton:
        _selection_click_pos = args.position

    # Only act after a center point has been picked (selection hidden).
    if _preview_center_model is None or _preview_sketch is None:
        return

    # Only respond to left-button clicks; ignore right-click / middle-click.
    if args.button != adsk.core.MouseButtons.LeftMouseButton:
        return

    hit = _mouse_to_sketch_plane(args)
    if hit is None:
        return

    dx = hit.x - _preview_center_model.x
    dy = hit.y - _preview_center_model.y
    dz = hit.z - _preview_center_model.z
    radius = math.sqrt(dx * dx + dy * dy + dz * dz)

    if radius < 1e-6:
        return

    # Update the diameter input for display consistency.
    if _cmd_inputs:
        diam_input: adsk.core.ValueCommandInput = _cmd_inputs.itemById("diameter")
        if diam_input:
            diam_input.value = radius * 2.0

    # Guard against double-clicks committing geometry twice.
    global _geometry_created
    if _geometry_created:
        return

    # Create the sketch geometry directly here – sketch API calls are safe
    # inside event handlers; only doExecute() is restricted.
    _create_sketch_geometry(radius)
    _geometry_created = True

    # Fire the custom event so doExecute(True) closes the dialog cleanly
    # once this event handler returns (doExecute cannot be called directly
    # from within a command event handler).
    adsk.core.Application.get().fireCustomEvent(_COMMIT_EVENT_ID)


# ---------------------------------------------------------------------------
# custom_event_commit – deferred commit, fires after the mouse event unwinds
# ---------------------------------------------------------------------------

def custom_event_commit(args: adsk.core.CustomEventArgs) -> None:
    """Fired asynchronously after mouseClick unwinds. Calls doExecute(True) to
    run the execute handler and close the command. command_execute is guarded
    by _geometry_created so it skips geometry that was already created."""
    try:
        if _active_command is not None:
            _active_command.doExecute(True)    # True = run execute then close
    except Exception:
        ptutil.log(f"{CMD_NAME} custom_event_commit failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# executePreview – redraws graphics whenever a dialog input changes
# ---------------------------------------------------------------------------

def command_execute_preview(args: adsk.core.CommandEventArgs) -> None:
    # Do not actually commit geometry here; just update the graphics preview.
    args.isValidResult = False

    if _preview_center_model is None or _preview_sketch is None:
        return

    inputs = args.command.commandInputs
    diameter_input: adsk.core.ValueCommandInput = inputs.itemById("diameter")
    if diameter_input is None or diameter_input.value <= 0:
        return

    _update_preview(diameter_input.value / 2.0)
    adsk.core.Application.get().activeViewport.refresh()


# ---------------------------------------------------------------------------
# Validate inputs – keeps OK button disabled until required data is present
# ---------------------------------------------------------------------------

def command_validate(args: adsk.core.ValidateInputsEventArgs) -> None:
    # The center selection input is hidden after picking, so we check the
    # module-level state variable rather than the (now-hidden) selection count.
    diameter_input: adsk.core.ValueCommandInput = args.inputs.itemById("diameter")

    args.areInputsValid = (
        _preview_center_model is not None
        and _preview_sketch is not None
        and diameter_input is not None
        and diameter_input.value > 0
    )


# ---------------------------------------------------------------------------
# Execute – fallback for OK-button press (geometry normally created on click)
# ---------------------------------------------------------------------------

def command_execute(args: adsk.core.CommandEventArgs) -> None:
    _clear_preview()

    # If geometry was already created on mouse-click, nothing left to do.
    if _geometry_created:
        return

    # Fallback: user pressed the OK button without clicking in the viewport.
    # Use the current diameter input value to create the geometry.
    try:
        if _preview_center_model is None or _preview_sketch is None:
            return

        inputs = args.command.commandInputs
        diameter_input: adsk.core.ValueCommandInput = inputs.itemById("diameter")
        radius = diameter_input.value / 2.0 if diameter_input else 0.0

        if radius > 0:
            _create_sketch_geometry(radius)

    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


# ---------------------------------------------------------------------------
# Destroy – release event handler references
# ---------------------------------------------------------------------------

def command_destroy(args: adsk.core.CommandEventArgs) -> None:
    global local_handlers, _cmd_inputs, _preview_center_model, _preview_sketch, _preview_selected_entity, _active_command, _geometry_created, _selection_click_pos, _vp_offset_x, _vp_offset_y
    _clear_preview()
    # Unregister the custom event so it doesn't accumulate across re-runs.
    try:
        adsk.core.Application.get().unregisterCustomEvent(_COMMIT_EVENT_ID)
    except Exception:
        pass
    local_handlers = []
    _cmd_inputs = None
    _active_command = None
    _preview_center_model = None
    _preview_sketch = None
    _preview_selected_entity = None
    _geometry_created = False
    _selection_click_pos = None
    _vp_offset_x = 0.0
    _vp_offset_y = 0.0
    ptutil.log(f"{CMD_NAME} Command Destroy Event")


# ===========================================================================
# Helpers
# ===========================================================================

def _create_sketch_geometry(radius: float) -> None:
    """
    Create the construction circle, diameter dimension, constrained sketch
    point, and guide line in the cached sketch at the given radius (cm).
    Safe to call from any event handler context.
    """
    try:
        sketch = _preview_sketch
        center_model = _preview_center_model
        selected_entity = _preview_selected_entity

        if sketch is None or center_model is None:
            ptutil.log(f"{CMD_NAME}: _create_sketch_geometry called with no sketch/center.")
            return

        # Map world-space center → sketch-local 2D
        center_local = sketch.modelToSketchSpace(center_model)

        top_model = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(center_local.x, center_local.y + radius, 0.0)
        )
        left_model = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(center_local.x - radius, center_local.y, 0.0)
        )
        right_model = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(center_local.x + radius, center_local.y, 0.0)
        )

        # 1. Construction circle (diameter / 2-point method)
        circle = sketch.sketchCurves.sketchCircles.addByTwoPoints(left_model, right_model)
        circle.isConstruction = True

        # 2. Coincident: circle center → selected sketch point
        if selected_entity is not None:
            sketch.geometricConstraints.addCoincident(circle.centerSketchPoint, selected_entity)

        # 3. Diameter dimension
        dim_text_model = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(
                center_local.x + radius * 0.75,
                center_local.y + radius * 0.75,
                0.0,
            )
        )
        sketch.sketchDimensions.addDiameterDimension(circle, dim_text_model)

        # 4. Sketch point at top of circle
        sketch_point = sketch.sketchPoints.add(top_model)

        # 5. Coincident: sketch point ON the circle
        sketch.geometricConstraints.addCoincident(sketch_point, circle)

        # 6. Construction guide line: center → sketch point
        guide_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
            circle.centerSketchPoint, sketch_point
        )
        guide_line.isConstruction = True

        # 7. Vertical constraint on guide line
        sketch.geometricConstraints.addVertical(guide_line)

        ptutil.log(
            f"{CMD_NAME}: Created construction circle r={radius:.4f} cm "
            f"with vertically constrained sketch point at top."
        )

    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)

def _clear_preview() -> None:
    """
    Delete every custom graphics group that was created by this command.
    Groups are identified by their name tag rather than a cached reference
    that can become stale across sketch-edit state changes.
    """
    try:
        app_local = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app_local.activeProduct)
        if not design:
            return
        root = design.rootComponent
        groups = root.customGraphicsGroups
        # Iterate in reverse so index stays valid as items are removed.
        for i in range(groups.count - 1, -1, -1):
            grp = groups.item(i)
            if grp.id == _PREVIEW_GFX_NAME:
                grp.deleteMe()
    except Exception:
        pass


def _update_preview(radius: float, hit: adsk.core.Point3D | None = None) -> None:
    """Clear then redraw the custom graphics preview circle at *radius* (cm),
    with an optional white crosshair at the cursor hit position."""
    _clear_preview()

    if _preview_center_model is None or _preview_sketch is None:
        return

    try:
        app_local = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app_local.activeProduct)
        if not design:
            return

        graphics = design.rootComponent.customGraphicsGroups.add()
        graphics.id = _PREVIEW_GFX_NAME

        sk_plane = _preview_sketch.referencePlane.geometry
        normal = sk_plane.normal
        white = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(255, 255, 255, 255)
        )

        # Preview circle – white, thin, dashed
        circle3d = adsk.core.Circle3D.createByCenter(
            _preview_center_model, normal, radius
        )
        curve_gfx = graphics.addCurve(circle3d)
        curve_gfx.weight = 1.0
        curve_gfx.color = white

        # Crosshair at cursor hit – fixed pixel size regardless of zoom.
        # We compute the model-space arm length that projects to PX_ARM pixels
        # on screen by sampling the local screen-space basis at the hit point.
        if hit is not None:
            PX_ARM = 8   # half-length of each crosshair arm, in pixels
            sketch = _preview_sketch
            hit_local = sketch.modelToSketchSpace(hit)
            hx, hy = hit_local.x, hit_local.y

            viewport = app_local.activeViewport
            hit_screen = viewport.modelToViewSpace(hit)
            ref_x_mdl = sketch.sketchToModelSpace(
                adsk.core.Point3D.create(hx + 1.0, hy, 0.0)
            )
            ref_y_mdl = sketch.sketchToModelSpace(
                adsk.core.Point3D.create(hx, hy + 1.0, 0.0)
            )
            ref_x_scr = viewport.modelToViewSpace(ref_x_mdl)
            ref_y_scr = viewport.modelToViewSpace(ref_y_mdl)

            if hit_screen and ref_x_scr and ref_y_scr:
                px_per_cm_x = math.hypot(
                    ref_x_scr.x - hit_screen.x, ref_x_scr.y - hit_screen.y
                )
                px_per_cm_y = math.hypot(
                    ref_y_scr.x - hit_screen.x, ref_y_scr.y - hit_screen.y
                )
                arm_x = PX_ARM / px_per_cm_x if px_per_cm_x > 1e-9 else 0.4
                arm_y = PX_ARM / px_per_cm_y if px_per_cm_y > 1e-9 else 0.4
            else:
                arm_x = arm_y = 0.4   # fallback: ~4 mm

            h0 = sketch.sketchToModelSpace(adsk.core.Point3D.create(hx - arm_x, hy, 0.0))
            h1 = sketch.sketchToModelSpace(adsk.core.Point3D.create(hx + arm_x, hy, 0.0))
            v0 = sketch.sketchToModelSpace(adsk.core.Point3D.create(hx, hy - arm_y, 0.0))
            v1 = sketch.sketchToModelSpace(adsk.core.Point3D.create(hx, hy + arm_y, 0.0))

            for p0, p1 in ((h0, h1), (v0, v1)):
                lg = graphics.addCurve(adsk.core.Line3D.create(p0, p1))
                lg.weight = 1.0
                lg.color = white

    except Exception:
        ptutil.log(f"{CMD_NAME} _update_preview failed:\n{traceback.format_exc()}")


def _mouse_to_sketch_plane(
    args: adsk.core.MouseEventArgs,
) -> adsk.core.Point3D | None:
    """
    Map the mouse cursor to a point on the sketch plane using a pure affine
    screen-space inversion.

    args.position is NOT guaranteed to be in the same pixel space as
    viewport.width/height (Fusion may report window-absolute coordinates).
    This approach avoids that problem entirely: we project the sketch center
    and two 1-cm reference points through modelToViewSpace to build a 2×2
    affine basis that maps screen-pixel offsets to sketch-local cm offsets,
    then solve for the mouse position in that basis.  args.position is used
    only as a raw 2-D value – no NDC conversion, no camera math needed.
    """
    try:
        viewport   = args.viewport
        mouse_pos  = args.position   # Point2D – raw coords, any space
        sketch     = _preview_sketch
        center_mdl = _preview_center_model

        # Project world-space center and two 1-cm reference points to screen.
        center_local = sketch.modelToSketchSpace(center_mdl)
        ref_x_mdl = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(center_local.x + 1.0, center_local.y, 0.0)
        )
        ref_y_mdl = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(center_local.x, center_local.y + 1.0, 0.0)
        )

        cs  = viewport.modelToViewSpace(center_mdl)
        rxs = viewport.modelToViewSpace(ref_x_mdl)
        rys = viewport.modelToViewSpace(ref_y_mdl)
        if cs is None or rxs is None or rys is None:
            return None

        # 2-D screen-space basis vectors (screen units per 1 cm in each sketch axis).
        sxx = rxs.x - cs.x;  sxy = rxs.y - cs.y   # sketch-X direction on screen
        syx = rys.x - cs.x;  syy = rys.y - cs.y   # sketch-Y direction on screen

        det = sxx * syy - sxy * syx
        if abs(det) < 1e-9:
            return None   # sketch is edge-on to the camera

        # Convert args.position (window coords) to viewport-local coords by
        # subtracting the calibrated viewport origin offset, then compute the
        # pixel offset from the projected center.
        mx = mouse_pos.x - _vp_offset_x
        my = mouse_pos.y - _vp_offset_y
        dx = mx - cs.x
        dy = my - cs.y

        # Solve the 2×2 system to get sketch-local coords (a, b) in cm.
        # [ sxx  syx ] [ a ]   [ dx ]
        # [ sxy  syy ] [ b ] = [ dy ]
        a = ( dx * syy - dy * syx) / det   # cm along sketch-X
        b = (-dx * sxy + dy * sxx) / det   # cm along sketch-Y

        radius = math.sqrt(a * a + b * b)
        if radius < 1e-6:
            return None

        # Return the world-space point on the sketch plane at (a, b) from center.
        hit = sketch.sketchToModelSpace(
            adsk.core.Point3D.create(center_local.x + a, center_local.y + b, 0.0)
        )
        return hit

    except Exception:
        ptutil.log(f"{CMD_NAME} _mouse_to_sketch_plane failed:\n{traceback.format_exc()}")
        return None

