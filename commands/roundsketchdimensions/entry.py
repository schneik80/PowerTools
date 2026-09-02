# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Round Sketch Dimensions — snap the active sketch's dimensions to a grid.

Lives in Sketch > Modify. Rounds the length and angular dimensions of the sketch
currently being edited to adjustable increments (a length grid plus a degree
grid that applies to every unit system), with smart defaults sized to the
sketch, a Fractions/Decimal choice for imperial documents, selection-based
include/exclude overrides, and a live preview that reverts on Cancel and
commits on OK.

Pure math (increment tables, eligibility parsing, rounding, smart default) lives
in the sibling ``rounding.py`` so it can be unit-tested outside Fusion. This
module holds only the Fusion-touching command wiring and the apply step.
"""

import math
import os
import traceback

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from .._command_abort import (
    abort_before_dialog,
    clear_abort,
    consume_abort,
)
from . import rounding

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Round Sketch Dimensions"
CMD_ID = "PTPM_roundsketchdimensions"
CMD_Description = (
    "Round the length and angular dimensions of the active sketch to clean, "
    "adjustable increments. Formula-driven and reference dimensions are left "
    "untouched."
)
IS_PROMOTED = False

WORKSPACE_ID = config.design_workspace
TAB_ID = "SketchTab"
PANEL_ID = "SketchModifyPanel"

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# ---------------------------------------------------------------------------
# Command-input IDs and dropdown item labels
# ---------------------------------------------------------------------------
INPUT_UNITS = "rsd_units"
INPUT_MODE = "rsd_mode"
INPUT_SELECTION = "rsd_selection"
INPUT_FORMAT = "rsd_format"
INPUT_SLIDER = "rsd_slider"
INPUT_INCR_LABEL = "rsd_incr_label"
INPUT_ANGLE_SLIDER = "rsd_angle_slider"
INPUT_ANGLE_LABEL = "rsd_angle_label"
INPUT_PREVIEW = "rsd_preview"

MODE_ALL = "Round all dimensions"
MODE_ONLY = "Only round selected dimensions"
MODE_IGNORE = "Ignore selected dimensions"

FMT_FRACTIONS = "Fractions"
FMT_DECIMAL = "Decimal"

# cm (Fusion's internal length unit) per one grid unit.
CM_PER_UNIT = {"mm": 0.1, "in": 2.54}

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------
local_handlers = []
_cached_sketch = None  # adsk.fusion.Sketch being edited
_is_imperial = False  # True when the document's length unit is inch/foot


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------
def start():
    try:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )
        ptutil.add_handler(cmd_def.commandCreated, command_created)

        sketch_tab = ui.allToolbarTabs.itemById(TAB_ID)
        if not sketch_tab:
            ptutil.log(f"{CMD_NAME}: '{TAB_ID}' not found — not added to UI.")
            return

        panel = sketch_tab.toolbarPanels.itemById(PANEL_ID)
        if not panel:
            ptutil.log(f"{CMD_NAME}: '{PANEL_ID}' not found in '{TAB_ID}'.")
            return

        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED

    except Exception:
        ptutil.log(f"{CMD_NAME} start() failed:\n{traceback.format_exc()}")


def stop():
    # Delete the control and command definition only — SketchModifyPanel is a
    # built-in Fusion panel and must never be deleted.
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
# Command created — build the dialog and wire handlers
# ---------------------------------------------------------------------------
def command_created(args: adsk.core.CommandCreatedEventArgs):
    global _cached_sketch, _is_imperial
    ptutil.log(f"{CMD_NAME} Command Created Event")

    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design or not isinstance(design.activeEditObject, adsk.fusion.Sketch):
            ui.messageBox(
                "A sketch must be active before running this command.\n\n"
                "Double-click a sketch in the browser to open it, then try again.",
                CMD_NAME,
            )
            abort_before_dialog(CMD_ID, CMD_NAME, "no active sketch")
            return

        _cached_sketch = adsk.fusion.Sketch.cast(design.activeEditObject)

        units_mgr = design.unitsManager
        token = units_mgr.defaultLengthUnits
        _is_imperial = token in ("in", "ft")
        grid_unit = "in" if _is_imperial else "mm"

        # Choose the default length grid and a smart starting index.
        if _is_imperial:
            increments = rounding.fraction_increments()  # Fractions default
        else:
            increments = rounding.MM_INCREMENTS
        magnitudes = _eligible_magnitudes(_cached_sketch, grid_unit)
        default_index = rounding.smart_default_index(magnitudes, increments)

        # Angular grid is degrees for every document.
        angle_magnitudes = _eligible_angle_magnitudes(_cached_sketch)
        angle_default_index = rounding.smart_default_index(
            angle_magnitudes, rounding.DEG_INCREMENTS
        )

        has_length = _count_length_eligible(_cached_sketch) > 0
        has_angle = _count_angle_eligible(_cached_sketch) > 0

        cmd = args.command
        cmd.okButtonText = "Round"
        inputs = cmd.commandInputs

        # 1. Document units (read-only).
        inputs.addTextBoxCommandInput(INPUT_UNITS, "Document units", token, 1, True)

        # 2. Mode dropdown.
        mode_dd = inputs.addDropDownCommandInput(
            INPUT_MODE, "Mode", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        mode_dd.listItems.add(MODE_ALL, True)
        mode_dd.listItems.add(MODE_ONLY, False)
        mode_dd.listItems.add(MODE_IGNORE, False)

        # 3. Dimension selection (hidden until a selection mode is chosen).
        # Fusion has no selection filter for sketch dimensions, so the input is
        # left unfiltered; non-dimension picks are ignored in code
        # (see _selected_param_names).
        sel = inputs.addSelectionInput(
            INPUT_SELECTION,
            "Dimensions",
            "Select sketch dimensions in the canvas.",
        )
        sel.setSelectionLimits(0, 0)
        sel.isVisible = False

        # 4. Value format (imperial only): Fractions vs Decimal. Only relevant
        # when there are length dimensions to round.
        fmt_dd = inputs.addDropDownCommandInput(
            INPUT_FORMAT, "Value format", adsk.core.DropDownStyles.TextListDropDownStyle
        )
        fmt_dd.listItems.add(FMT_FRACTIONS, True)
        fmt_dd.listItems.add(FMT_DECIMAL, False)
        fmt_dd.isVisible = _is_imperial and has_length

        # 5. Length increment slider (index into the active grid; length fixed).
        slider = inputs.addIntegerSliderCommandInput(
            INPUT_SLIDER, "Length increment", 0, len(increments) - 1
        )
        slider.valueOne = default_index
        slider.isVisible = has_length

        # 6. Resolved length increment label (read-only); populated below.
        length_label = inputs.addTextBoxCommandInput(
            INPUT_INCR_LABEL, "Length rounds to", "", 1, True
        )
        length_label.isVisible = has_length

        # 7. Angle increment slider (degrees; applies to every unit system).
        angle_slider = inputs.addIntegerSliderCommandInput(
            INPUT_ANGLE_SLIDER, "Angle increment", 0, len(rounding.DEG_INCREMENTS) - 1
        )
        angle_slider.valueOne = angle_default_index
        angle_slider.isVisible = has_angle

        # 8. Resolved angle increment label (read-only); populated below.
        angle_label = inputs.addTextBoxCommandInput(
            INPUT_ANGLE_LABEL, "Angle rounds to", "", 1, True
        )
        angle_label.isVisible = has_angle

        # 9. Preview toggle (default on).
        inputs.addBoolValueInput(INPUT_PREVIEW, "Preview", True, "", True)

        _update_increment_label(inputs)
        _update_angle_label(inputs)

        ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
        ptutil.add_handler(
            cmd.executePreview, command_execute_preview, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.validateInputs, command_validate, local_handlers=local_handlers
        )
        ptutil.add_handler(
            cmd.inputChanged, command_input_changed, local_handlers=local_handlers
        )
        ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    except Exception:
        ui.messageBox(f"{CMD_NAME}: Setup failed.\n{traceback.format_exc()}", CMD_NAME)


# ---------------------------------------------------------------------------
# Input changed — toggle selection visibility, swap grid, refresh label
# ---------------------------------------------------------------------------
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        inputs = args.inputs
        changed_id = args.input.id

        if changed_id == INPUT_MODE:
            mode = _current_mode(inputs)
            sel = inputs.itemById(INPUT_SELECTION)
            if mode == MODE_ALL:
                sel.clearSelection()
                sel.isVisible = False
            else:
                sel.isVisible = True
                sel.tooltip = (
                    "Select the dimensions to round."
                    if mode == MODE_ONLY
                    else "Select the dimensions to leave unchanged."
                )

        if changed_id in (INPUT_SLIDER, INPUT_FORMAT):
            _update_increment_label(inputs)

        if changed_id == INPUT_ANGLE_SLIDER:
            _update_angle_label(inputs)

    except Exception:
        ptutil.log(f"{CMD_NAME} inputChanged failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Validate — enable OK only when there is actionable work
# ---------------------------------------------------------------------------
def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        inputs = args.inputs
        mode = _current_mode(inputs)

        if mode != MODE_ALL:
            sel = inputs.itemById(INPUT_SELECTION)
            if not sel or sel.selectionCount < 1:
                args.areInputsValid = False
                return

        eligible = _count_length_eligible(_cached_sketch) + _count_angle_eligible(
            _cached_sketch
        )
        args.areInputsValid = eligible > 0
    except Exception:
        args.areInputsValid = False


# ---------------------------------------------------------------------------
# Execute preview — live-apply when Preview is on
# ---------------------------------------------------------------------------
def command_execute_preview(args: adsk.core.CommandEventArgs):
    try:
        inputs = args.command.commandInputs
        preview_on = inputs.itemById(INPUT_PREVIEW).value
        if not preview_on:
            args.isValidResult = False
            return

        _apply_rounding(inputs)
        # Keep the previewed edits when the user clicks OK (execute is then
        # skipped); Fusion rolls them back on Cancel.
        args.isValidResult = True

    except Exception:
        ptutil.log(f"{CMD_NAME} executePreview failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Execute — apply for the no-preview path (idempotent, so always safe)
# ---------------------------------------------------------------------------
def command_execute(args: adsk.core.CommandEventArgs):
    # command_created bailed out before building a dialog, so Fusion is
    # auto-executing a command with no inputs. _apply_rounding would then read
    # inputs that do not exist and raise, reporting a traceback on top of the
    # message the user already saw.
    if consume_abort(CMD_ID, CMD_NAME):
        return

    try:
        inputs = args.command.commandInputs
        count = _apply_rounding(inputs)
        ptutil.log(f"{CMD_NAME}: rounded {count} dimension(s).")
    except Exception:
        ui.messageBox(f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME)


# ---------------------------------------------------------------------------
# Destroy — release references and reset state
# ---------------------------------------------------------------------------
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _cached_sketch, _is_imperial
    # Bound the abort flag to this invocation: consume_abort only clears it
    # if command_execute ran, and destroy always runs.
    clear_abort(CMD_ID)
    local_handlers = []
    _cached_sketch = None
    _is_imperial = False
    ptutil.log(f"{CMD_NAME} Command Destroy Event")


# ===========================================================================
# Helpers
# ===========================================================================
def _current_mode(inputs) -> str:
    dd = inputs.itemById(INPUT_MODE)
    if dd and dd.selectedItem:
        return dd.selectedItem.name
    return MODE_ALL


def _current_increment(inputs):
    """Return ``(increment_in_grid_unit, grid_unit)`` for the current inputs."""
    slider = inputs.itemById(INPUT_SLIDER)
    idx = slider.valueOne if slider else 0

    if _is_imperial:
        fmt = inputs.itemById(INPUT_FORMAT)
        is_fraction = not (
            fmt and fmt.selectedItem and fmt.selectedItem.name == FMT_DECIMAL
        )
        if is_fraction:
            idx = max(0, min(idx, len(rounding.INCH_FRACTION_DENOMS) - 1))
            return (1.0 / rounding.INCH_FRACTION_DENOMS[idx], "in")
        idx = max(0, min(idx, len(rounding.INCH_DECIMAL_INCH) - 1))
        return (rounding.INCH_DECIMAL_INCH[idx], "in")

    idx = max(0, min(idx, len(rounding.MM_INCREMENTS) - 1))
    return (rounding.MM_INCREMENTS[idx], "mm")


def _current_angle_increment(inputs) -> float:
    """Return the current angular increment in degrees."""
    slider = inputs.itemById(INPUT_ANGLE_SLIDER)
    idx = slider.valueOne if slider else 0
    idx = max(0, min(idx, len(rounding.DEG_INCREMENTS) - 1))
    return rounding.DEG_INCREMENTS[idx]


def _update_increment_label(inputs):
    label = inputs.itemById(INPUT_INCR_LABEL)
    if not label:
        return
    slider = inputs.itemById(INPUT_SLIDER)
    idx = slider.valueOne if slider else 0

    if _is_imperial:
        fmt = inputs.itemById(INPUT_FORMAT)
        is_fraction = not (
            fmt and fmt.selectedItem and fmt.selectedItem.name == FMT_DECIMAL
        )
        if is_fraction:
            idx = max(0, min(idx, len(rounding.INCH_FRACTION_DENOMS) - 1))
            label.text = rounding.fraction_increment_label(
                rounding.INCH_FRACTION_DENOMS[idx]
            )
        else:
            idx = max(0, min(idx, len(rounding.INCH_DECIMAL_INCH) - 1))
            label.text = rounding.decimal_increment_label(
                rounding.INCH_DECIMAL_INCH[idx], "in"
            )
    else:
        idx = max(0, min(idx, len(rounding.MM_INCREMENTS) - 1))
        label.text = rounding.decimal_increment_label(rounding.MM_INCREMENTS[idx], "mm")


def _update_angle_label(inputs):
    label = inputs.itemById(INPUT_ANGLE_LABEL)
    if not label:
        return
    label.text = rounding.decimal_increment_label(
        _current_angle_increment(inputs), "deg"
    )


def _is_length_eligible(dim) -> bool:
    """True if *dim* is an editable, plain-constant length dimension."""
    # Driven (reference) dimensions are read-only — skip them.
    try:
        if not dim.isDriving:
            return False
    except Exception:
        pass
    param = dim.parameter
    if not param:
        return False
    try:
        unit = (param.unit or "").lower()
    except Exception:
        return False
    if "deg" in unit or "rad" in unit:  # angular dimension — handled separately
        return False
    try:
        expr = param.expression
    except Exception:
        return False
    return rounding.is_plain_numeric_expression(expr)


def _is_angle_eligible(dim) -> bool:
    """True if *dim* is an editable, plain-constant angular dimension."""
    # Driven (reference) dimensions are read-only — skip them.
    try:
        if not dim.isDriving:
            return False
    except Exception:
        pass
    param = dim.parameter
    if not param:
        return False
    try:
        unit = (param.unit or "").lower()
    except Exception:
        return False
    if "deg" not in unit and "rad" not in unit:  # not angular — skip
        return False
    try:
        expr = param.expression
    except Exception:
        return False
    return rounding.is_plain_numeric_expression(expr, rounding.ANGLE_UNIT_TOKENS)


def _iter_dimensions(sketch):
    if not sketch:
        return
    dims = sketch.sketchDimensions
    for i in range(dims.count):
        yield dims.item(i)


def _eligible_magnitudes(sketch, grid_unit):
    """Magnitudes (in *grid_unit*) of every eligible length dimension."""
    cm_per = CM_PER_UNIT.get(grid_unit, 0.1)
    out = []
    for dim in _iter_dimensions(sketch):
        if _is_length_eligible(dim):
            out.append(abs(dim.parameter.value) / cm_per)
    return out


def _eligible_angle_magnitudes(sketch):
    """Magnitudes (in degrees) of every eligible angular dimension.

    Angular parameter values are stored in radians internally, so convert to
    degrees to match :data:`rounding.DEG_INCREMENTS`.
    """
    out = []
    for dim in _iter_dimensions(sketch):
        if _is_angle_eligible(dim):
            out.append(abs(math.degrees(dim.parameter.value)))
    return out


def _count_length_eligible(sketch) -> int:
    return sum(1 for dim in _iter_dimensions(sketch) if _is_length_eligible(dim))


def _count_angle_eligible(sketch) -> int:
    return sum(1 for dim in _iter_dimensions(sketch) if _is_angle_eligible(dim))


def _selected_param_names(inputs):
    """Names of the model parameters for the currently selected dimensions.

    Parameter names (``d1``, ``d2``, …) are unique per design and stable across
    the preview cycle, so they are a reliable identity key for include/exclude
    matching.
    """
    names = set()
    sel = inputs.itemById(INPUT_SELECTION)
    if not sel or not sel.isVisible:
        return names
    for i in range(sel.selectionCount):
        dim = adsk.fusion.SketchDimension.cast(sel.selection(i).entity)
        if dim and dim.parameter:
            names.add(dim.parameter.name)
    return names


def _apply_rounding(inputs) -> int:
    """Round every targeted, eligible dimension. Returns the count changed.

    Reads each dimension's CURRENT value, so it is idempotent — re-running (as
    happens on every preview refresh) never compounds.
    """
    if not _cached_sketch:
        return 0

    increment, grid_unit = _current_increment(inputs)
    cm_per = CM_PER_UNIT.get(grid_unit, 0.1)
    angle_increment = _current_angle_increment(inputs)

    mode = _current_mode(inputs)
    selected = _selected_param_names(inputs) if mode != MODE_ALL else set()

    count = 0
    for dim in _iter_dimensions(_cached_sketch):
        is_length = _is_length_eligible(dim)
        is_angle = _is_angle_eligible(dim) if not is_length else False
        if not is_length and not is_angle:
            continue
        param = dim.parameter

        name = param.name
        if mode == MODE_ONLY and name not in selected:
            continue
        if mode == MODE_IGNORE and name in selected:
            continue

        if is_length:
            if increment <= 0:
                continue
            grid_val = param.value / cm_per
            step, unit_token = increment, grid_unit
        else:
            if angle_increment <= 0:
                continue
            grid_val = math.degrees(param.value)  # radians -> degrees
            step, unit_token = angle_increment, "deg"

        rounded = rounding.round_to_increment(grid_val, step)
        if abs(rounded - grid_val) < step * 1e-9:
            continue  # already on the grid — skip needless recompute

        try:
            param.expression = rounding.format_value_expression(rounded, unit_token)
            count += 1
        except Exception:
            # Driven / reference dimension — read-only parameter. Skip.
            continue

    return count
