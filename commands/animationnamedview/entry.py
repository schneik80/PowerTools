# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Save the Animation viewport camera as a Named View on the design.

Named views live on the design (``NamedViews`` is in ``adsk.core``, reached via
``Product.namedViews``), and they can be created directly from the Animation
environment -- with one catch that this command exists to handle: while the
Animation workspace is active, ``app.activeProduct`` is *not* the design, so the
obvious ``Design.cast(app.activeProduct)`` returns None. The design has to be
looked up on the document's product list instead.

That, plus the storyboard-derived naming in ``logic.py``, is the whole command.
Both facts were established by probing the live API across several approaches on
Fusion 2704.1.36; see docs/Animation Named View.md for the results.
"""

import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from . import logic

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Save Named View"
CMD_ID = "PTAN_animationnamedview"
CMD_Description = (
    "Save the current Animation viewport camera as a named view on the design, "
    "named from the active storyboard."
)
IS_PROMOTED = True

PANEL_ID = config.animation_panel_id

# Resource location for command icons, here we assume a sub folder in this
# directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Holds references to event handlers
local_handlers = []

AUTO_NAME_INPUT_ID = "PTAN_autoName"
NAME_INPUT_ID = "PTAN_name"

# Fallback name when there is no design or storyboard to derive one from.
FALLBACK_VIEW_NAME = "Animation View"

# The Animation workspace and its tab are resolved at start() — Fusion publishes
# neither ID, so config pins the observed ones and falls back to a name scan.
# Both are kept so stop() tears down the same panel.
_workspace_id = None
_tab_id = None


# Executed when add-in is run.
def start():
    global _workspace_id, _tab_id
    _workspace_id = config.resolve_animation_workspace_id()
    if _workspace_id is None:
        # No Animation environment on this build — skip the UI rather than
        # raising, so the rest of the add-in still starts.
        ptutil.log(f"{CMD_NAME}: no Animation workspace found; UI skipped.")
        return

    ptutil.log(f"{CMD_NAME}: using Animation workspace {_workspace_id!r}")

    # ******************************** Create Command Definition ****************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control *******************
    # Our panel goes on Fusion's own Animation tab, after its View panel.
    panel, _tab_id = config.get_or_create_animation_panel(_workspace_id)
    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # remove_from_panel deletes the tab once it holds no panels, which is only
    # ever reached for a tab we created. The Animation tab is Fusion's own and
    # keeps its built-in panels, so it is never emptied and never deleted.
    if _workspace_id is not None and _tab_id is not None:
        ptutil.remove_from_panel(_workspace_id, PANEL_ID, _tab_id, CMD_ID)

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    cmd = args.command
    cmd.okButtonText = "Save View"
    inputs = cmd.commandInputs

    inputs.addBoolValueInput(
        AUTO_NAME_INPUT_ID, "Auto-name from storyboard", True, "", True
    )
    name_input = inputs.addStringValueInput(NAME_INPUT_ID, "Name", default_view_name())
    name_input.isEnabled = False

    ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    ptutil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    """Keep the name field in step with the auto-name checkbox.

    Mirrors the Related Data command: the field is disabled while auto-naming is
    on, and is re-seeded from the storyboard each time it is turned back on so a
    stale hand-edit is never silently reused.
    """
    if args.input.id != AUTO_NAME_INPUT_ID:
        return
    inputs = args.inputs
    auto_input = inputs.itemById(AUTO_NAME_INPUT_ID)
    name_input = inputs.itemById(NAME_INPUT_ID)
    if auto_input is None or name_input is None:
        return
    name_input.isEnabled = not auto_input.value
    if auto_input.value:
        name_input.value = default_view_name()


def command_execute(args: adsk.core.CommandEventArgs):
    try:
        ptutil.log(f"{CMD_NAME} Command Execute Event")
        inputs = args.command.commandInputs
        auto_input = inputs.itemById(AUTO_NAME_INPUT_ID)
        name_input = inputs.itemById(NAME_INPUT_ID)

        auto_name = auto_input is None or auto_input.value
        requested_name = ""
        if name_input is not None and not auto_name:
            requested_name = (name_input.value or "").strip()
        if not requested_name:
            requested_name = default_view_name()
            auto_name = True

        # A successful save is silent — the log records it. Only a stored view
        # that does not match the viewport is worth interrupting the user for.
        summary, warning = save_named_view(requested_name, allow_update=auto_name)
        ptutil.log(f"{CMD_NAME}: {summary}")
        if warning:
            ui.messageBox(warning, CMD_NAME)
    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    ptutil.log(f"{CMD_NAME} Command Destroy Event")


def design_product():
    """Return the Design product for the active document, or None.

    The design is looked up on the document's product list rather than through
    ``app.activeProduct``, because the Animation environment does not expose the
    design as the active product -- ``Design.cast(app.activeProduct)`` returns
    None there.
    """
    doc = app.activeDocument
    products = doc.products if doc is not None else None
    if products is None:
        return None
    return adsk.fusion.Design.cast(products.itemByProductType("DesignProductType"))


def default_view_name() -> str:
    """Derive the named-view name from the active storyboard and playhead.

    ``Storyboard`` exposes no readable name, so the label is recovered by probing
    the storyboards collection and falls back to a positional label -- see
    ``logic.storyboard_label``.

    Returns:
        A name such as ``"Storyboard2 @ 3.50s"``, or ``FALLBACK_VIEW_NAME`` when
        there is no design or animation to read.
    """
    try:
        design = design_product()
        if design is None:
            return FALLBACK_VIEW_NAME
        manager = design.animationManager
        if manager is None:
            return FALLBACK_VIEW_NAME
        storyboards = manager.storyboards
        index = logic.find_active_storyboard_index(storyboards)
        label = logic.storyboard_label(storyboards, index)

        playhead = 0.0
        active = manager.activeStoryboard
        if active is not None:
            playhead = active.playheadPosition
        return logic.derive_view_name(label, playhead)
    except Exception:
        ptutil.log(f"{CMD_NAME}: could not derive a name from the storyboard")
        return FALLBACK_VIEW_NAME


def save_named_view(requested_name: str, allow_update: bool):
    """Save the current viewport camera as a named view on the design.

    When *allow_update* is set and a view of that name already exists, its
    camera is overwritten in place rather than a second view being created
    alongside it. That is the right behaviour for an auto-generated name,
    because the name encodes the storyboard and playhead: a collision means the
    same point in the same storyboard, which is the same view, so re-saving it
    should move it. A name the user typed is not treated that way -- it gets a
    numbered suffix instead, so a view they named deliberately is never
    silently overwritten.

    Either way the stored camera is read back and compared against the one
    submitted. That check is cheap and guards against a reported Fusion defect
    where a perspective camera can be stored with a badly wrong eye position --
    it does not reproduce on every build, so a silent save would be a gamble.

    Args:
        requested_name: The desired view name, before collision handling.
        allow_update: Overwrite an existing view of the same name instead of
            creating a suffixed one.

    Returns:
        A ``(summary, warning)`` pair. The summary always describes what
        happened and is written to the log; the warning is empty unless the
        stored view does not match the viewport and the user needs to act.

    Raises:
        RuntimeError: If no design is available, or Fusion declines the save.
    """
    design = design_product()
    if design is None:
        raise RuntimeError(
            "No design was found for the active document. Open a design "
            "document before saving a named view."
        )

    named_views = design.namedViews
    if named_views is None:
        raise RuntimeError("This document does not support named views.")

    source_camera = app.activeViewport.camera

    existing = (
        logic.find_named_view(named_views, requested_name) if allow_update else None
    )
    if existing is not None:
        # NamedView.camera is read/write except on the four standard views, and
        # itemByName cannot return one of those, so this is always assignable.
        existing.camera = source_camera
        view, summary = existing, f'Updated named view "{requested_name}".'
    else:
        name = logic.unique_view_name(
            requested_name, logic.make_name_taken(named_views)
        )
        view = named_views.add(source_camera, name)
        if view is None:
            raise RuntimeError(f'Fusion did not create a named view called "{name}".')
        summary = f'Saved named view "{name}".'
        if name != requested_name:
            summary += f' The name "{requested_name}" was already in use.'

    warning = ""
    drift = logic.camera_drift(source_camera, view.camera)
    if drift is not None and drift > logic.DRIFT_TOLERANCE:
        warning = (
            f'The named view "{view.name}" was stored, but its camera differs '
            f"from the viewport by {drift:.3f}. Applying it will not restore "
            "the framing you saved.\n\nTry switching the viewport to an "
            "orthographic view and saving again."
        )
    return summary, warning
