# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

import os
import re
import time
import traceback

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from .document_dag import document_bottom_up_order, resolve_document

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Bottom-up Update"
CMD_ID = "PTAT_bottomupupdate"
CMD_Description = "Save and update all references in the open assembly from the bottom up\n \nOptions to Rebuild all, log the results, hide objects and apply document intent.\nUpdating can skip standard components and already saved documents."
IS_PROMOTED = False

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Holds references to event handlers to prevent garbage collection
local_handlers = []
# Set to track document IDs that have already been saved to avoid duplicate processing
saved = set()
resume_plan = {}
# Prior autosave preference values while a run has them suspended; None when no
# suspension is active. Restored on success, on failure, and in command_destroy.
_autosave_prior_state = None

# Command input IDs
REBUILD_INPUT_ID = "rebuild_all"  # Checkbox to enable full rebuild of all components
SKIP_STANDARD_ID = "skip_standard"  # Checkbox to skip standard library components
SKIP_SAVED_ID = "skip_saved"  # Checkbox to skip components that are already saved
SKIP_CONFIGS_ID = "skip_configurations"  # Checkbox to skip configuration documents
HIDE_ORIGINS_ID = "hide_origins"  # Checkbox to hide coordinate system origins
HIDE_JOINTS_ID = "hide_joints"  # Checkbox to hide joint elements in the model
HIDE_SKETCHES_ID = "hide_sketches"  # Checkbox to hide component sketches
HIDE_JOINTORIGINS_ID = "hide_jointorigins"  # Checkbox to hide joint origin markers
HIDE_CANVASES_ID = "hide_canvases"  # Checkbox to hide canvases
APPLY_INTENT_ID = "apply_intent"  # Checkbox to apply design intent before saving
PAUSE_TIME_ID = (
    "pause_time"  # Text input for upload completion poll interval in seconds
)
LOG_ENABLE_ID = "enable_log"  # Checkbox to enable progress logging
LOG_PATH_ID = "log_path"  # Text input for custom log file path
LOG_BROWSE_ID = "browse_log"  # Button to browse for log file location
LOG_OPEN_VIEW_ID = "open_log_view"  # Checkbox to auto-open a live log viewer
RESUME_STATUS_ID = "resume_status"  # Read-only status for resume behavior


# Executed when add-in is run.
def start():
    # Remove any stale command definition for clean setup
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)
    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        existing = panel.controls.itemById(CMD_ID)
        if existing:
            existing.deleteMe()
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    # Connect to the events that are needed by this command.
    ptutil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.inputChanged, on_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )

    global product, design, title, resume_plan

    # Get the active Fusion product and cast to Design for manipulation
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    # Title for dialogs and messages
    title = CMD_NAME

    # Check a Design document is active.
    if not design:
        ui.messageBox("A Fusion 3D Design must be active", "title")
        return

    # Check if there are any references to update
    if app.activeDocument.documentReferences.count == 0:
        ui.messageBox("No document references found", title)
        return

    # Check that the active document has been saved.
    if not ptutil.isSaved():
        return

    resume_plan = {
        "should_resume": False,
        "resume_start_index": 0,
        "last_saved_index": 0,
        "status_message": "A full run will start.",
    }
    try:
        root_component = design.rootComponent
        bottom_up_records = document_bottom_up_order(root_component)
        bottom_up_order = [record["doc_id"] for record in bottom_up_records]
        resume_plan = _analyze_resume_state(
            _default_temp_log_path(), app.version, bottom_up_order
        )
    except Exception as resume_error:
        resume_plan = {
            "should_resume": False,
            "resume_start_index": 0,
            "last_saved_index": 0,
            "status_message": f"Resume check failed ({resume_error}). A full run will start.",
        }

    # Build command dialog inputs
    inputs: adsk.core.CommandInputs = args.command.commandInputs
    # Main tab
    main_tab = inputs.addTabCommandInput("mainTab", "Main")
    main_inputs = main_tab.children

    rebuild_input = main_inputs.addBoolValueInput(
        REBUILD_INPUT_ID, "Rebuild all", True, "", True
    )
    rebuild_input.tooltip = (
        "Forces a complete rebuild of all components to ensure they are up to date."
    )

    skip_standard_input = main_inputs.addBoolValueInput(
        SKIP_STANDARD_ID, "Skip standard components", True, "", True
    )
    skip_standard_input.tooltip = (
        "Skip processing of standard library component Documents."
    )

    skip_saved_input = main_inputs.addBoolValueInput(
        SKIP_SAVED_ID, "Skip already saved Documents", True, "", False
    )
    skip_saved_input.tooltip = (
        "Skip Documents that have already been saved in this Fusion client build."
    )

    skip_configs_input = main_inputs.addBoolValueInput(
        SKIP_CONFIGS_ID, "Skip configured designs", True, "", True
    )
    skip_configs_input.tooltip = (
        "Skip configuration members and configured designs. Fusion can crash "
        "natively in its configuration data-model when this command opens "
        "them in bulk; skipped documents are listed in the log."
    )

    apply_intent_input = main_inputs.addBoolValueInput(
        APPLY_INTENT_ID, "Apply Design Doc Intent", True, "", True
    )
    apply_intent_input.tooltip = "Applies design intent (Part, Assembly, or Hybrid) to the document's root component."

    resume_status_input = main_inputs.addTextBoxCommandInput(
        RESUME_STATUS_ID,
        "Run status",
        resume_plan.get("status_message", "A full run will start."),
        3,
        True,
    )
    resume_status_input.tooltip = "Startup check based on temp log, Fusion client version, and current bottom-up list."

    advanced_group = main_inputs.addGroupCommandInput("advancedGroup", "Advanced")
    advanced_group.isExpanded = False
    advanced_inputs = advanced_group.children

    # Add upload poll interval input
    pause_time_input = advanced_inputs.addStringValueInput(
        PAUSE_TIME_ID, "Upload check interval (seconds)", "0.5"
    )
    pause_time_input.tooltip = "How often to check upload status after each save. Lower values react faster, higher values reduce CPU usage."

    # Visualization tab
    vis_tab = inputs.addTabCommandInput("visTab", "Visibility")
    vis_inputs = vis_tab.children
    hide_origins_input = vis_inputs.addBoolValueInput(
        HIDE_ORIGINS_ID, "Hide origins", True, "", False
    )
    hide_origins_input.tooltip = "Hide the origin in the document's root component."

    hide_joints_input = vis_inputs.addBoolValueInput(
        HIDE_JOINTS_ID, "Hide joints", True, "", False
    )
    hide_joints_input.tooltip = "Hides all joints. \n \nSet the Joint Folder visibility off to hide any new Joints created."

    hide_sketches_input = vis_inputs.addBoolValueInput(
        HIDE_SKETCHES_ID, "Hide sketches", True, "", False
    )
    hide_sketches_input.tooltip = "Hides each sketch in the document's root component.\n \nSet the Sketch Folder visibility On to show any new Sketches created."

    hide_joint_origins_input = vis_inputs.addBoolValueInput(
        HIDE_JOINTORIGINS_ID, "Hide joint origins", True, "", False
    )
    hide_joint_origins_input.tooltip = "Hides each joint origin in the document's root component before saving.\n \nSet the Joint Origins Folder visibility On to show any new Joint Origins created."

    hide_canvases_input = vis_inputs.addBoolValueInput(
        HIDE_CANVASES_ID, "Hide canvases", True, "", False
    )
    hide_canvases_input.tooltip = "Hides each canvas in the document's root component before saving.\n \nSet the Canvases Folder visibility On to show any new Canvases created."

    # Logging tab
    log_tab = inputs.addTabCommandInput("logTab", "Logging")
    log_inputs = log_tab.children
    log_enable = log_inputs.addBoolValueInput(
        LOG_ENABLE_ID, "Log Progress", True, "", True
    )
    log_enable.tooltip = (
        "Enables detailed progress logging to a text file during the update process."
    )

    log_path = log_inputs.addStringValueInput(LOG_PATH_ID, "Log file path", "")
    log_path.isReadOnly = True

    browse_btn = log_inputs.addBoolValueInput(
        LOG_BROWSE_ID, "Browse…", False, "", False
    )
    browse_btn.tooltip = (
        "Click to browse and select a custom location for the log file."
    )

    open_view = log_inputs.addBoolValueInput(
        LOG_OPEN_VIEW_ID, "Open live log viewer", True, "", True
    )
    open_view.tooltip = "Automatically opens a system console window to live-monitor log output while the command runs."

    log_path.isEnabled = log_enable.value
    browse_btn.isEnabled = log_enable.value
    open_view.isEnabled = log_enable.value


# NOTE: traverse_assembly / sort_dag_bottom_up build the component-name DAG that
# the command used before the move to the document-level graph in document_dag.py.
# The live path (command_created / command_execute) now consumes
# document_bottom_up_order instead; these two are retained as the reference
# implementation exercised by tests/test_bottomupupdate_dag.py and can be removed
# once the id-based path is verified in Fusion.
def traverse_assembly(component, parent_dict, _memo=None):
    """
    Recursively traverses the assembly and creates a dictionary for each component.
    :param component: The root component to traverse.
    :param parent_dict: The dictionary to store child components.
    :param _memo: Internal cache keyed by component name. The first time a
        component is seen its subtree is walked and its node cached; every later
        occurrence of that same component reuses the already-built node instead
        of re-walking its subtree. This preserves the produced structure (and so
        the bottom-up order) while avoiding O(refs) re-walks of shared
        sub-assemblies. Fusion assemblies are acyclic, so reuse cannot recurse
        infinitely.
    """
    if _memo is None:
        _memo = {}
    for occurrence in component.occurrences:
        child_component = occurrence.component
        name = child_component.name
        node = _memo.get(name)
        if node is None:
            # First time we have seen this component: build it and walk down.
            node = {"component": child_component, "children": {}}
            _memo[name] = node
            parent_dict[name] = node
            traverse_assembly(child_component, node["children"], _memo)
        else:
            # Already built elsewhere; reuse the same subtree under this parent.
            parent_dict[name] = node


def sort_dag_bottom_up(assembly_dict):
    """
    Sorts the dictionary as a DAG in bottom-up (leaves-first) order.

    Performs a depth-first, post-order traversal: a node is appended only
    after every one of its children has been appended, so each component's
    dependencies always precede it in the result.

    Two sets keep the traversal both correct and efficient:

    - ``emitted`` records components already appended. A component shared by
      several sub-assemblies (a "diamond" dependency) is therefore emitted
      exactly once, and the walk stays O(V + E) instead of re-descending a
      shared subtree once per path that reaches it (worst case exponential).
    - ``in_progress`` marks the components currently on the DFS stack (the
      "VISITING" state). Fusion assemblies are acyclic, but if a malformed
      graph ever presented a back edge this breaks and reports it instead of
      recursing until the interpreter raises RecursionError.

    :param assembly_dict: The dictionary representing the assembly structure.
    :return: A list of unique component names in bottom-up order.
    """
    sorted_components = []
    emitted = set()
    in_progress = set()

    def traverse_dag(node):
        name = node["component"].name
        if name in emitted:
            return  # Shared sub-assembly already placed; do not re-walk it.
        if name in in_progress:
            # A cycle is impossible for a real Fusion assembly; guard anyway so
            # a malformed graph degrades gracefully instead of overflowing.
            ptutil.log(f"Cycle detected at component '{name}'; skipping re-entry.")
            return
        in_progress.add(name)
        for child_data in node["children"].values():
            traverse_dag(child_data)
        in_progress.discard(name)
        emitted.add(name)
        sorted_components.append(name)

    for value in assembly_dict.values():
        traverse_dag(value)

    return sorted_components


def _configuration_label(data_file):
    """Describe a data file's configuration role, or return '' if none.

    The 2026-07-02 CER crash faulted inside Fusion's configuration event
    consumer (Ns::MFGDMEventConsumer ... hubModelIdsForConfiguration) while
    this command opened a configuration member -- a documented Fusion
    native-crash class for Configurations / Manage-extension data. This helper
    lets the loop identify such documents before opening them. Both properties
    are documented on DataFile; access is guarded for older clients.
    """
    try:
        if getattr(data_file, "isConfiguration", False):
            return "configuration member"
        if getattr(data_file, "isConfiguredDesign", False):
            return "configured design"
    except Exception:
        return ""
    return ""


def _open_document_index(documents):
    """Map dataFile.id -> name for every currently open document (best effort).

    Includes invisible documents (Documents.count covers both). Documents with
    no dataFile (never saved) cannot be identified reliably and are omitted.
    """
    index = {}
    try:
        count = documents.count
    except Exception:
        return index
    for i in range(count):
        try:
            doc = documents.item(i)
            data_file = doc.dataFile if doc else None
            if data_file and data_file.id:
                index[data_file.id] = doc.name
        except Exception:
            continue
    return index


def _collect_stray_documents(documents, initial_ids, is_top_fn):
    """Return open documents that were not open when the run started.

    Fusion implicitly opens related documents while a parent is opened or has
    its references updated -- notably configuration members and configured
    designs -- and never closes them, so they accumulate across the run. The
    processing loop only closes the document it explicitly opened; this
    identifies the rest. The top document and anything already open at run
    start (including invisible reference documents) are never returned;
    documents without a dataFile id cannot be identified and are left alone.

    :param documents: The app.documents collection (count / item(i)).
    :param initial_ids: Container of dataFile ids open at run start.
    :param is_top_fn: Predicate marking the top document (never a stray).
    """
    strays = []
    try:
        count = documents.count
    except Exception:
        return strays
    for i in range(count):
        try:
            doc = documents.item(i)
        except Exception:
            continue
        if not doc or is_top_fn(doc):
            continue
        doc_id = None
        try:
            data_file = doc.dataFile
            doc_id = data_file.id if data_file else None
        except Exception:
            doc_id = None
        if not doc_id or doc_id in initial_ids:
            continue
        strays.append(doc)
    return strays


def is_external_component(comp: adsk.fusion.Component):
    """
    Check if the component is external by checking its occurrences
    comp: A fusion component object.
    """
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        return False

    root = design.rootComponent
    occs = root.occurrencesByComponent(comp)
    return any(occ.isReferencedComponent for occ in occs)


def hide_origins_in_document(document):
    """
    Hide all coordinate system origins in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control origin visibility
        try:
            # Check if the origin folder light bulb is on (visible) and turn it off
            if design.activeComponent.isOriginFolderLightBulbOn:
                design.activeComponent.isOriginFolderLightBulbOn = False
                return "   Origin hidden "
            else:
                return "   Origin was already hidden"

        except Exception as api_e:
            return f"Error using Fusion API to hide origins: {str(api_e)}"

    except Exception as e:
        return f"Error hiding origins: {str(e)}"


def hide_joint_origins_in_document(document):
    """
    Hide all joint origins in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control joint origin visibility
        try:
            # Set the joint origins folder light bulb to true (ensure folder is accessible)
            design.activeComponent.isJointOriginsFolderLightBulbOn = True

            # Check if there are joint origins to hide
            joint_origins = design.activeComponent.jointOrigins
            if joint_origins.count > 0:
                hidden_count = 0
                # Iterate over each joint origin and try to hide it
                for i in range(joint_origins.count):
                    joint_origin = joint_origins.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if (
                            hasattr(joint_origin, "isLightBulbOn")
                            and joint_origin.isLightBulbOn
                        ):
                            joint_origin.isLightBulbOn = False
                            hidden_count += 1
                    except Exception:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   joint origins hidden ({hidden_count})"
                else:
                    return "   Attempted to hide joint origins - individual visibility control may be limited"
            else:
                return "   No joint origins found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide joint origins: {str(api_e)}"

    except Exception as e:
        return f"Error hiding joint origins: {str(e)}"


def hide_sketches_in_document(document):
    """
    Hide all sketches in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control sketch visibility
        try:
            # Set the sketches folder light bulb to true (ensure folder is accessible)
            design.activeComponent.isSketchFolderLightBulbOn = True

            # Check if there are sketches to hide
            sketches = design.activeComponent.sketches
            if sketches.count > 0:
                hidden_count = 0
                # Iterate over each sketch and try to hide it
                for i in range(sketches.count):
                    sketch = sketches.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if hasattr(sketch, "isLightBulbOn") and sketch.isLightBulbOn:
                            sketch.isLightBulbOn = False
                            hidden_count += 1
                    except Exception:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   sketches hidden ({hidden_count})"
                else:
                    return "   Attempted to hide sketches - individual visibility control may be limited"
            else:
                return "   No sketches found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide sketches: {str(api_e)}"

    except Exception as e:
        return f"Error hiding sketches: {str(e)}"


def hide_joints_in_document(document):
    """
    Hide all joints in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control joint visibility
        try:
            # Set the joints folder light bulb to false (hide folder)
            design.activeComponent.isJointsFolderLightBulbOn = False

            # Check if there are joints to hide
            joints = design.activeComponent.joints
            if joints.count > 0:
                hidden_count = 0
                # Iterate over each joint and try to hide it
                for i in range(joints.count):
                    joint = joints.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if hasattr(joint, "isLightBulbOn") and joint.isLightBulbOn:
                            joint.isLightBulbOn = False
                            hidden_count += 1
                    except Exception:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   joints hidden ({hidden_count})"
                else:
                    return "   Attempted to hide joints - individual visibility control may be limited"
            else:
                return "   No joints found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide joints: {str(api_e)}"

    except Exception as e:
        return f"Error hiding joints: {str(e)}"


def hide_canvases_in_document(document):
    """
    Hide all canvases in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control canvas visibility
        try:
            # Set the canvases folder light bulb to false (hide folder)
            design.activeComponent.isCanvasFolderLightBulbOn = False

            # Check if there are canvases to hide
            canvases = design.activeComponent.canvases
            if canvases.count > 0:
                hidden_count = 0
                # Iterate over each canvas and try to hide it
                for i in range(canvases.count):
                    canvas = canvases.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if hasattr(canvas, "isLightBulbOn") and canvas.isLightBulbOn:
                            canvas.isLightBulbOn = False
                            hidden_count += 1
                    except Exception:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   canvases hidden ({hidden_count})"
                else:
                    return "   Attempted to hide canvases - individual visibility control may be limited"
            else:
                return "   No canvases found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide canvases: {str(api_e)}"

    except Exception as e:
        return f"Error hiding canvases: {str(e)}"


def execute_command_with_timeout(
    command_definition,
    command_label,
    poll_interval_seconds=0.1,
    timeout_seconds=120,
):
    """
    Execute a Fusion command definition with polling and timeout protection.

    :return: (is_success, message)
    """
    if command_definition is None:
        return False, f"{command_label} not found"

    poll_interval = max(0.05, poll_interval_seconds)
    start_time = time.time()
    while True:
        if command_definition.execute():
            return True, f"{command_label} executed successfully"

        if timeout_seconds > 0 and (time.time() - start_time) >= timeout_seconds:
            return (
                False,
                f"{command_label} timed out after {timeout_seconds} seconds",
            )
        # Pump events across the poll interval so the UI stays responsive and the
        # command's async work keeps advancing instead of freezing on a bare sleep.
        ptutil.pump_events_for(poll_interval)


def _suspend_autosave(log_fn=None):
    """Temporarily disable Fusion's background autosave for the current run.

    The processing loop opens, saves, and closes documents in rapid succession
    while pumping ``adsk.doEvents()``. Fusion's automatic-versioning background
    thread and the save-on-close automation can dispatch a concurrent save of a
    dirty document inside one of those pumps, invalidating data-model objects
    the loop still holds -- the recurring native NsDataModel10.dll access
    violation captured by CER (LastCommand PLM360SaveCommand_Spawned /
    CloseDocumentCommand_Spawned; crashed document flagged Needs Autosave).
    Suspending both switches removes that concurrent mutator for the run.

    Callers must pair this with ``_restore_autosave()``; both are idempotent,
    and the prior values are logged so a crash between the two calls leaves a
    recoverable record in the log.
    """
    global _autosave_prior_state
    log = log_fn or ptutil.log
    if _autosave_prior_state is not None:
        return  # Already suspended by this run.
    try:
        prefs = adsk.core.Application.get().preferences.generalPreferences
        prior = {
            "isAutomaticVersioningEnabled": prefs.isAutomaticVersioningEnabled,
            "isAutomaticSaveOnCloseEnabled": prefs.isAutomaticSaveOnCloseEnabled,
        }
        prefs.isAutomaticVersioningEnabled = False
        prefs.isAutomaticSaveOnCloseEnabled = False
        _autosave_prior_state = prior
        log(f"Autosave suspended for this run (prior settings: {prior})")
    except Exception as suspend_error:
        _autosave_prior_state = None
        log(
            f"Could not suspend autosave ({suspend_error}); "
            "continuing with autosave active."
        )


def _restore_autosave(log_fn=None):
    """Restore the autosave settings captured by ``_suspend_autosave``.

    Idempotent: safe to call from every exit path (success, failure, and
    command destroy); only the first call after a suspension does work.
    """
    global _autosave_prior_state
    log = log_fn or ptutil.log
    if _autosave_prior_state is None:
        return
    prior = _autosave_prior_state
    _autosave_prior_state = None
    try:
        prefs = adsk.core.Application.get().preferences.generalPreferences
        prefs.isAutomaticVersioningEnabled = prior["isAutomaticVersioningEnabled"]
        prefs.isAutomaticSaveOnCloseEnabled = prior["isAutomaticSaveOnCloseEnabled"]
        log(f"Autosave settings restored: {prior}")
    except Exception as restore_error:
        log(
            f"Failed to restore autosave settings ({restore_error}); "
            f"prior values were: {prior}"
        )


def command_execute(args: adsk.core.CommandEventArgs):
    # ...existing code...
    global product, design, title, saved, resume_plan
    from datetime import datetime

    app = adsk.core.Application.get()
    ui = app.userInterface
    start_total_time = time.time()  # Track total execution time

    # Initialize logging variables early
    create_log = False
    file_path = None
    progress_bar = None  # Initialize progress bar variable

    def write_log_entry(entry):
        """Helper function to write entries to the log file if logging is enabled"""
        if create_log and file_path:
            try:
                with open(file_path, "a", encoding="utf-8") as fh:
                    fh.write(entry + "\n")
            except Exception as log_e:
                ptutil.log(f"Failed to write log entry: {log_e}")

    try:
        design = app.activeProduct
        appVersionBuild = app.version  # Store Fusion version for save comments
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("No active Fusion design")
            return

        # Keep the starting/top document open throughout command execution.
        top_document = app.activeDocument
        top_document_id = None
        try:
            if top_document and top_document.dataFile:
                top_document_id = top_document.dataFile.id
        except Exception:
            top_document_id = None

        def is_top_document(doc):
            if not doc:
                return False
            if doc == top_document:
                return True
            try:
                return bool(
                    top_document_id
                    and doc.dataFile
                    and doc.dataFile.id == top_document_id
                )
            except Exception:
                return False

        def close_processed_document(expected_doc_id, label):
            """Close the just-processed document via a freshly acquired handle.

            Document handles held across pumped waits are the native-crash
            vector: a background operation dispatched during adsk.doEvents()
            can invalidate them, and the next dereference faults inside the
            data model (NsDataModel10.dll access violation). Re-acquire
            activeDocument, close it only when it provably is the document just
            processed, then pump briefly so the close finishes before the next
            open (queued Close/Open/Save commands overflowing the message queue
            also appears in the CER data).
            """
            try:
                doc = app.activeDocument
            except Exception as close_error:
                write_log_entry(
                    f"   Could not re-acquire document to close {label}: {close_error}"
                )
                return
            if doc is None or is_top_document(doc):
                return
            actual_id = None
            try:
                if doc.dataFile:
                    actual_id = doc.dataFile.id
            except Exception:
                actual_id = None
            if actual_id != expected_doc_id:
                write_log_entry(
                    f"   Active document changed during the save wait for {label} "
                    f"(expected {expected_doc_id}, found {actual_id}); leaving it open."
                )
                return
            try:
                doc.close(False)
            except Exception as close_error:
                write_log_entry(f"   Failed to close {label}: {close_error}")
                return
            # Let the data model finish processing the close before the next open.
            ptutil.pump_events_for(0.25)

        def sweep_stray_documents(context_label):
            """Close documents Fusion opened implicitly since the run started.

            Opening a parent (or updating its references) pulls configuration
            members / configured designs open as a side effect; nothing closes
            them, so they pile up across the run. Sweeps anything not open at
            run start, except the top document.
            """
            strays = _collect_stray_documents(
                app.documents, initial_open_doc_ids, is_top_document
            )
            for stray in strays:
                try:
                    stray_name = stray.name
                except Exception:
                    stray_name = "<unknown>"
                try:
                    stray.close(False)
                    write_log_entry(
                        f"   Closed stray document ({context_label}): {stray_name}"
                    )
                except Exception as stray_error:
                    write_log_entry(
                        f"   Failed to close stray document {stray_name}: {stray_error}"
                    )
            if strays:
                # Let the closes drain before continuing.
                ptutil.pump_events_for(0.25)

        # Read dialog values from user inputs
        inputs: adsk.core.CommandInputs = args.command.commandInputs
        skip_standard = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(SKIP_STANDARD_ID)
        ).value
        skip_configs_input = inputs.itemById(SKIP_CONFIGS_ID)
        skip_configs = (
            adsk.core.BoolValueCommandInput.cast(skip_configs_input).value
            if skip_configs_input
            else True
        )
        rebuild_all = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(REBUILD_INPUT_ID)
        ).value
        create_log = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(LOG_ENABLE_ID)
        ).value
        open_log_view = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(LOG_OPEN_VIEW_ID)
        ).value
        log_path_val = adsk.core.StringValueCommandInput.cast(
            inputs.itemById(LOG_PATH_ID)
        ).value
        skip_saved = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(SKIP_SAVED_ID)
        ).value
        hide_origins = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_ORIGINS_ID)
        ).value
        hide_joints = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_JOINTS_ID)
        ).value
        hide_sketches = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_SKETCHES_ID)
        ).value
        hide_joint_origins = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_JOINTORIGINS_ID)
        ).value
        hide_canvases = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_CANVASES_ID)
        ).value

        # Read and validate upload poll interval
        pause_time_input = inputs.itemById(PAUSE_TIME_ID)
        if pause_time_input:
            pause_time_str = adsk.core.StringValueCommandInput.cast(
                pause_time_input
            ).value
            try:
                pause_time = float(pause_time_str)
                if pause_time < 0:
                    pause_time = 0.5
            except (ValueError, TypeError):
                pause_time = 0.5
                ptutil.log(
                    f"Invalid upload check interval '{pause_time_str}', using default 0.5 seconds"
                )
                write_log_entry(
                    f"Invalid upload check interval '{pause_time_str}', using default 0.5 seconds"
                )
        else:
            pause_time = 0.5
            ptutil.log(
                "Upload check interval input not found, using default 0.5 seconds"
            )
            write_log_entry(
                "Upload check interval input not found, using default 0.5 seconds"
            )

        # Build the document dependency graph and determine processing order.
        # Nodes are keyed by dataFile.id, so multi-component documents collapse to
        # a single save unit and the order is deduplicated by construction. Each
        # record is {"doc_id", "name"}; the id list drives resume and dedup, the
        # name is carried for human-readable logs and progress.
        root_component = design.rootComponent
        bottom_up_records = document_bottom_up_order(root_component)
        bottom_up_order = [record["doc_id"] for record in bottom_up_records]

        docCount = len(bottom_up_records)
        default_temp_log_path = _default_temp_log_path()
        resume_info = _analyze_resume_state(
            default_temp_log_path, appVersionBuild, bottom_up_order
        )
        if resume_info.get("completed_successfully") and resume_info.get("log_exists"):
            try:
                with open(default_temp_log_path, "w", encoding="utf-8"):
                    pass
            except Exception as clear_error:
                ptutil.log(f"Failed to clear previous completed log: {clear_error}")
        resume_plan = resume_info
        resume_start_index = max(
            0, min(resume_info.get("resume_start_index", 0), docCount)
        )
        saved_doc_count = (
            max(resume_info.get("last_saved_index", 0), 0)
            if resume_info.get("should_resume")
            else 0
        )

        ptutil.log(f"Bottom-up order (doc_id, name): {bottom_up_records}")
        write_log_entry(f"Bottom-up order (doc_id, name): {bottom_up_records}")
        ptutil.log(resume_info.get("status_message", "A full run will start."))
        write_log_entry(resume_info.get("status_message", "A full run will start."))
        if docCount == 0:
            ui.messageBox("No referenced documents found to update.")
            return
        ptutil.log(f"----- Starting saving {docCount} documents -----")
        write_log_entry(f"----- Starting saving {docCount} documents -----")

        # Set up logging if enabled
        if create_log:
            doc = app.activeDocument
            if log_path_val:  # Use custom path if provided
                file_path = log_path_val
            else:
                file_path = default_temp_log_path
            # Write initial log info at start
            try:
                log_mode = "a" if resume_info.get("should_resume") else "w"
                with open(file_path, log_mode, encoding="utf-8") as fh:
                    if log_mode == "a":
                        fh.write("\n----- Resume attempt -----\n")
                    parent_project_name = None
                    doc_id = None
                    try:
                        # Get project and document information for logging
                        parent_project_name = (
                            doc.dataFile.parentProject.name
                            if doc and doc.dataFile and doc.dataFile.parentProject
                            else None
                        )
                        doc_id = doc.dataFile.id if doc and doc.dataFile else None
                    except Exception:
                        parent_project_name = None
                        doc_id = None
                    fh.write(f"Fusion client version: {appVersionBuild}\n")
                    fh.write(f"Active Document Parent Project: {parent_project_name}\n")
                    fh.write(f"Active Document ID: {doc_id}\n")
                    fh.write("Command Options:\n")
                    fh.write(f"  Rebuild all: {rebuild_all}\n")
                    fh.write(f"  Create log file: {create_log}\n")
                    fh.write(f"  Open live log viewer: {open_log_view}\n")
                    fh.write(f"  Skip standard components: {skip_standard}\n")
                    fh.write(f"  Upload check interval: {pause_time} seconds\n")
                    fh.write(f"  Log file path: {file_path}\n")
                    fh.write(
                        f"  Resume requested: {resume_info.get('should_resume', False)}\n"
                    )
                    fh.write(f"  Resume start index: {resume_start_index}\n")
                    fh.write("\nBottom-up order:\n")
                    fh.write(
                        "\n".join(
                            f"{record['doc_id']}|{record['name']}"
                            for record in bottom_up_records
                        )
                    )
                    fh.write("\n\nDocument save log:\n")
            except Exception as log_e:
                ptutil.log(f"Failed to write initial log: {log_e}")

            if open_log_view and file_path:
                _, open_msg = ptutil.open_live_log_viewer(file_path)
                ptutil.log(open_msg)
                write_log_entry(open_msg)

        # Initialize progress bar for document processing
        progress_bar = ui.createProgressDialog()
        progress_bar.cancelButtonText = "Cancel"
        progress_bar.isBackgroundTranslucent = False
        progress_bar.isCancelButtonShown = True
        progress_bar.maximumValue = docCount
        progress_bar.minimumValue = 0
        progress_bar.progressValue = resume_start_index
        progress_bar.show(
            "Bottom-up Update Progress",
            "Resuming from checkpoint..."
            if resume_info.get("should_resume")
            else "Preparing to update components...",
            resume_start_index,
            docCount,
            1,
        )

        # Counter for progress tracking
        processed_count = resume_start_index

        # Suspend Fusion's background autosave for the run so it cannot save a
        # dirty document concurrently with the loop's own save/close cycle.
        # Restored on every exit path (success, failure, command destroy).
        _suspend_autosave(write_log_entry)

        # Snapshot the documents open right now (visible and invisible): the
        # stray-document sweep must never close anything the user or Fusion
        # already had open before the run -- only what processing opens later.
        initial_open_doc_ids = _open_document_index(app.documents)
        write_log_entry(
            f"Open documents at run start ({len(initial_open_doc_ids)}): "
            + ", ".join(sorted(initial_open_doc_ids.values()))
        )

        # Map document id -> a representative component once, so the per-document
        # skip checks below (which read parentDesign.parentDocument metadata) cost
        # O(1) instead of rescanning design.allComponents. Any component that
        # resolves to a given document is equivalent for those checks, so keep the
        # FIRST one seen per document id.
        components_by_docid = {}
        for comp in design.allComponents:
            resolved = resolve_document(comp)
            if resolved is None:
                continue
            comp_docid = resolved[0]
            if comp_docid not in components_by_docid:
                components_by_docid[comp_docid] = comp

        # Process each document in bottom-up dependency order. Records are unique
        # by doc_id, so the graph already excludes the root document and collapses
        # multi-component documents; the saved-set guard below stays as defense in
        # depth and for resume safety.
        for record in bottom_up_records[resume_start_index:]:
            docid = record["doc_id"]
            component_name = record["name"]  # Display/log name for this document
            # Clean up anything the previous document's open/update left behind
            # (implicitly opened configuration documents in particular).
            sweep_stray_documents(f"before {component_name}")
            if docid == top_document_id:  # Root assembly is saved separately at the end
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = (
                    f"Skipping root document ({processed_count} of {docCount})"
                )
                continue
            # Representative component for this document, used only to read the
            # parentDesign.parentDocument metadata the skip checks below need.
            component = components_by_docid.get(docid)
            if not component:  # No component resolves to this document; skip it
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Component not found: {component_name} ({processed_count} of {docCount})"
                continue
            # Walk the parentDesign.parentDocument chain once and reuse it below
            # instead of re-marshalling it 3-6x per iteration.
            parent_document = component.parentDesign.parentDocument
            parent_project = None
            try:
                # Get the project name to check if it's a standard component
                parent_project = parent_document.dataFile.parentProject.name
            except Exception:
                parent_project = None

            # Skip standard components if option is enabled
            if skip_standard and parent_project == "Standard Components":
                log_entry = f"Skipping standard component: {component_name}"
                ptutil.log(log_entry)
                write_log_entry(log_entry)
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping standard component: {component_name} ({processed_count} of {docCount})"
                continue

            # Skip already saved components if option is enabled
            target_doc_version = None
            try:
                target_doc_version = parent_document.version
            except Exception:
                target_doc_version = None

            if skip_saved and target_doc_version == appVersionBuild:
                log_entry = f"Skipping already saved component: {component_name}"
                ptutil.log(log_entry)
                write_log_entry(log_entry)
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping already saved: {component_name} ({processed_count} of {docCount})"
                continue

            # Skip if we've already processed this document ID
            if docid in saved:
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping already processed: {component_name} ({processed_count} of {docCount})"
                continue
            saved.add(docid)  # Mark this document as processed

            # Update progress bar before opening document
            processed_count += 1
            progress_bar.progressValue = processed_count
            progress_bar.message = (
                f"Updating component {processed_count} of {docCount}: {component_name}"
            )

            # Open the component's document for editing
            try:
                document = app.data.findFileById(docid)
                if not document:
                    error_msg = (
                        f"Could not find document for component: {component_name}"
                    )
                    ptutil.log(error_msg)
                    write_log_entry(error_msg)
                    progress_bar.message = f"Failed to find document: {component_name} ({processed_count} of {docCount})"
                    continue

                # Configuration documents crash Fusion's configuration/PIM
                # data-model when opened in bulk (see _configuration_label);
                # skip them unless the user opted in to processing them.
                config_label = _configuration_label(document)
                if config_label and skip_configs:
                    log_entry = f"Skipping {config_label}: {component_name}"
                    ptutil.log(log_entry)
                    write_log_entry(log_entry)
                    progress_bar.message = f"Skipping {config_label}: {component_name} ({processed_count} of {docCount})"
                    continue
                if config_label:
                    write_log_entry(f"   Note: {component_name} is a {config_label}")

                # Drain pending events (e.g. configuration/PIM cache updates
                # from prior saves) before opening the next document; the
                # 2026-07-02 crash faulted in that event consumer mid-open.
                ptutil.pump_events_for(0.25)

                app.documents.open(document, True)
                # Log the document open event
                ptutil.log(f"Opened component: {component_name}")
                write_log_entry(f"Opened component: {component_name}")
            except Exception as open_error:
                error_msg = (
                    f"Failed to open document for {component_name}: {str(open_error)}"
                )
                ptutil.log(error_msg)
                write_log_entry(error_msg)
                progress_bar.message = f"Failed to open document: {component_name} ({processed_count} of {docCount})"
                continue  # Skip this component and move to the next one
            # Update all references in the newly opened document
            opened_doc = app.activeDocument
            try:
                opened_doc.updateAllReferences()
                ptutil.log(f"Updated references for component: {component_name}")
                write_log_entry(f"Updated references for component: {component_name}")
            except RuntimeError as ref_error:
                error_msg = f"Failed to update references for {component_name}: {str(ref_error)}"
                ptutil.log(error_msg)
                write_log_entry(error_msg)
                # Continue processing despite reference update failure

            # Ensure we're in the correct workspace for operations
            workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if workspace and not workspace.isActive:
                workspace.activate()
            des = adsk.fusion.Design.cast(app.activeProduct)

            # Hide origins if option is enabled
            if hide_origins:
                hide_log = hide_origins_in_document(opened_doc)
                ptutil.log(f"   Hide origins for {component_name}: {hide_log}")
                write_log_entry(f"   Hide origins for {component_name}: {hide_log}")

            # Hide joints if option is enabled
            if hide_joints:
                hide_joint_log = hide_joints_in_document(opened_doc)
                ptutil.log(f"   Hide joints for {component_name}: {hide_joint_log}")
                write_log_entry(
                    f"   Hide joints for {component_name}: {hide_joint_log}"
                )

            # Hide joint origins if option is enabled
            if hide_joint_origins:
                hide_joint_log = hide_joint_origins_in_document(opened_doc)
                ptutil.log(
                    f"   Hide joint origins for {component_name}: {hide_joint_log}"
                )
                write_log_entry(
                    f"   Hide joint origins for {component_name}: {hide_joint_log}"
                )

            # Hide sketches if option is enabled
            if hide_sketches:
                hide_sketch_log = hide_sketches_in_document(opened_doc)
                ptutil.log(f"   Hide sketches for {component_name}: {hide_sketch_log}")
                write_log_entry(
                    f"   Hide sketches for {component_name}: {hide_sketch_log}"
                )

            # Hide canvases if option is enabled
            if hide_canvases:
                hide_canvas_log = hide_canvases_in_document(opened_doc)
                ptutil.log(f"   Hide canvases for {component_name}: {hide_canvas_log}")
                write_log_entry(
                    f"   Hide canvases for {component_name}: {hide_canvas_log}"
                )

            # Apply design intent if option is enabled
            apply_intent = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(APPLY_INTENT_ID)
            ).value

            if apply_intent and des:
                # Determine the appropriate design intent type
                # PartDesignIntentType = 0, AssemblyDesignIntentType = 1, HybridDesignIntentType = 2
                if des.rootComponent.occurrences.count == 0:
                    # No children = part
                    intent_type = adsk.fusion.DesignIntentTypes.PartDesignIntentType
                    intent_label = "part"
                    ptutil.log(
                        f"   Applying part intent to {component_name} (no children)"
                    )
                    write_log_entry(
                        f"   Applying part intent to {component_name} (no children)"
                    )
                else:
                    child_count = des.rootComponent.occurrences.count
                    sketch_count = des.rootComponent.sketches.count
                    body_count = des.rootComponent.bRepBodies.count

                    if sketch_count > 0 or body_count > 0:
                        # Has children AND has sketches or bodies = hybrid assembly
                        intent_type = (
                            adsk.fusion.DesignIntentTypes.HybridDesignIntentType
                        )
                        intent_label = "hybrid assembly"
                        ptutil.log(
                            f"   Applying hybrid assembly intent to {component_name} ({child_count} children, {sketch_count} sketches, {body_count} bodies)"
                        )
                        write_log_entry(
                            f"   Applying hybrid assembly intent to {component_name} ({child_count} children, {sketch_count} sketches, {body_count} bodies)"
                        )
                    else:
                        # Has children but no sketches or bodies = regular assembly
                        intent_type = (
                            adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType
                        )
                        intent_label = "assembly"
                        ptutil.log(
                            f"   Applying assembly intent to {component_name} ({child_count} children, no sketches/bodies)"
                        )
                        write_log_entry(
                            f"   Applying assembly intent to {component_name} ({child_count} children, no sketches/bodies)"
                        )

                try:
                    des.designIntent = intent_type
                    ptutil.log(
                        f"   {intent_label.capitalize()} intent applied to {component_name}"
                    )
                    write_log_entry(
                        f"   {intent_label.capitalize()} intent applied to {component_name}"
                    )
                except Exception as intent_error:
                    ptutil.log(
                        f"   Failed to apply {intent_label} intent to {component_name}: {intent_error}"
                    )
                    write_log_entry(
                        f"   Failed to apply {intent_label} intent to {component_name}: {intent_error}"
                    )

            # Rebuild the component if rebuild option is enabled
            if rebuild_all:
                ptutil.log(f"   Rebuilding component: {component_name}")
                write_log_entry(f"   Rebuilding component: {component_name}")
                while not des.computeAll():  # Force compute until complete
                    # Keep the UI responsive while the compute settles.
                    ptutil.pump_events_for(0.1)
                ptutil.log(f"   Rebuild complete: {component_name}")
                write_log_entry(f"   Rebuilt {component_name}")

            # Add and remove a temporary attribute to trigger change detection.
            # Re-acquire the design handle first: `des` may have been held across
            # pumped waits (design intent / rebuild), and stale handles across
            # doEvents pumps are the native-crash vector.
            des = adsk.fusion.Design.cast(app.activeProduct)
            if des:
                des.attributes.add("FusionRA", "FusionRA", component_name)
                attr = des.attributes.itemByName("FusionRA", "FusionRA")
                attr.deleteMe()
            else:
                write_log_entry(
                    f"   Skipped change-detection tickle for {component_name} "
                    "(no active design after compute)"
                )

            # Save the document with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            active_doc = app.activeDocument
            pre_save_version = None
            try:
                if active_doc.dataFile and hasattr(
                    active_doc.dataFile, "versionNumber"
                ):
                    pre_save_version = active_doc.dataFile.versionNumber
            except Exception:
                pre_save_version = None

            data_file_future = active_doc.save(
                f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
            )

            save_ok, save_msg = ptutil.wait_for_upload(
                data_file_future,
                component_name,
                poll_interval_seconds=pause_time,
                document=active_doc,
                pre_save_version=pre_save_version,
                log_fn=write_log_entry,
            )
            ptutil.log(f"   {save_msg}")
            write_log_entry(f"   {save_msg}")
            if not save_ok:
                close_processed_document(docid, component_name)
                continue

            # Already saved; close via a fresh handle to avoid another save cycle.
            close_processed_document(docid, component_name)
            log_entry = f"   {component_name} saved - [{timestamp}]"
            ptutil.log(log_entry)
            write_log_entry(log_entry)
            saved_doc_count += 1  # Increment counter for completed saves

            checkpoint_entry = (
                f"CHECKPOINT|SAVE_UPLOAD_COMPLETE|doc_id={docid}|"
                f"component={component_name}|saved_index={saved_doc_count}|"
                f"total={docCount}|timestamp={timestamp}"
            )
            ptutil.log(checkpoint_entry)
            write_log_entry(checkpoint_entry)

            # Add progress separator
            progress_msg = (
                f"----- Completed {saved_doc_count} of {docCount} components -----"
            )
            ptutil.log(progress_msg)
            write_log_entry(progress_msg)

            des = None  # Clear design reference

        ptutil.log("----- Components saved -----")
        write_log_entry("----- Components saved -----")

        # Update progress bar for final steps
        progress_bar.message = "Getting latest versions of all components..."

        # Execute Fusion commands to get latest versions and update references
        ptutil.log("Executing GetAllLatestCmd...")
        write_log_entry("Executing GetAllLatestCmd...")
        cmdDefs = ui.commandDefinitions
        cmdGet = cmdDefs.itemById("GetAllLatestCmd")  # Get all latest command
        get_all_ok, get_all_msg = execute_command_with_timeout(
            cmdGet, "GetAllLatestCmd", poll_interval_seconds=0.1, timeout_seconds=120
        )
        ptutil.log(get_all_msg)
        write_log_entry(get_all_msg)
        if not get_all_ok:
            raise RuntimeError(get_all_msg)

        ptutil.log("Executing ContextUpdateAllFromParentCmd...")
        write_log_entry("Executing ContextUpdateAllFromParentCmd...")
        progress_bar.message = "Updating all references from parent..."
        cmdUpdate = cmdDefs.itemById(
            "ContextUpdateAllFromParentCmd"
        )  # Update all from parent
        update_ok, update_msg = execute_command_with_timeout(
            cmdUpdate,
            "ContextUpdateAllFromParentCmd",
            poll_interval_seconds=0.1,
            timeout_seconds=120,
        )
        ptutil.log(update_msg)
        write_log_entry(update_msg)
        if not update_ok:
            raise RuntimeError(update_msg)

        # Save the active document after updating references
        progress_bar.message = "Saving main assembly document..."
        ptutil.log("Saving active document after updating references...")
        write_log_entry("Saving active document after updating references...")
        main_doc = app.activeDocument
        main_pre_save_version = None
        try:
            if main_doc.dataFile and hasattr(main_doc.dataFile, "versionNumber"):
                main_pre_save_version = main_doc.dataFile.versionNumber
        except Exception:
            main_pre_save_version = None

        final_save_future = main_doc.save(
            f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
        )
        final_save_ok, final_save_msg = ptutil.wait_for_upload(
            final_save_future,
            "main assembly",
            poll_interval_seconds=pause_time,
            document=main_doc,
            pre_save_version=main_pre_save_version,
            log_fn=write_log_entry,
        )
        ptutil.log(final_save_msg)
        write_log_entry(final_save_msg)
        if not final_save_ok:
            raise RuntimeError(final_save_msg)

        final_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_checkpoint_entry = (
            "CHECKPOINT|SAVE_UPLOAD_COMPLETE|component=main assembly|"
            f"saved_index={saved_doc_count}|total={docCount}|timestamp={final_timestamp}"
        )
        ptutil.log(final_checkpoint_entry)
        write_log_entry(final_checkpoint_entry)

        # The final Get All Latest / Update All From Parent on the root can
        # also open configuration documents implicitly; sweep them so the run
        # ends with only the documents that were open when it started.
        sweep_stray_documents("final cleanup")

        # Hide the progress bar
        progress_bar.hide()

        # Prepare completion message and finalize logging
        completion_msg = "Bottom-up Update complete."
        end_total_time = time.time()
        total_elapsed = (
            end_total_time - start_total_time
        )  # Calculate total execution time

        # Log final statistics to both logging systems
        ptutil.log(f"Total documents saved: {saved_doc_count}")
        ptutil.log(f"Total command run time: {total_elapsed:.2f} seconds")
        write_log_entry(f"Total documents saved: {saved_doc_count}")
        write_log_entry(f"Total command run time: {total_elapsed:.2f} seconds")

        if create_log and file_path:
            try:
                ptutil.log(f"Log written to: {file_path}")
                completion_msg += f"\nLog written to: {file_path}"
            except Exception as log_e:
                ptutil.log(f"Failed to write log: {log_e}")
                completion_msg += f"\nFailed to write log to: {file_path}\n{log_e}"

        # Clear global variables for next run
        _restore_autosave(write_log_entry)
        saved.clear()  # Clear the set of processed document IDs
        resume_plan = {}
        product = None
        design = None
        title = None
        ptutil.log("Cleared global variables for next execution")
        write_log_entry("Cleared global variables for next execution")

        ptutil.log("Bottom-up Update completed successfully")
        write_log_entry("Bottom-up Update completed successfully")
        ui.messageBox(completion_msg)  # Show completion message to user
    except Exception:
        # Hide progress bar if it exists
        try:
            if progress_bar:
                progress_bar.hide()
        except Exception:
            pass  # Ignore any errors hiding the progress bar

        # Clear global variables even on failure to ensure clean state for next run
        _restore_autosave(write_log_entry)
        saved.clear()
        resume_plan = {}
        product = None
        design = None
        title = None
        ptutil.log("Cleared global variables after error")
        write_log_entry("Cleared global variables after error")
        if ui:
            ui.messageBox(f"Failed:\n{traceback.format_exc()}")


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, saved, product, design, title, resume_plan
    local_handlers = []
    _restore_autosave()  # Belt and braces: idempotent, no-op if already restored
    saved.clear()  # Clear the set of processed document IDs
    resume_plan = {}
    product = None
    design = None
    title = None
    ptutil.log(f"{CMD_NAME} Command Destroy Event - cleared global variables")


def _propose_default_log_filename() -> str:
    """Generate a default log filename based on the active document name"""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    base_name = "assembly_log"
    if doc and doc.dataFile:
        base_name = doc.dataFile.name
    elif doc and doc.name:
        base_name = doc.name
    # Clean filename for filesystem compatibility
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
    if not base_name.lower().endswith(".txt"):
        base_name += ".txt"
    return base_name


def _default_temp_log_path() -> str:
    """Return the default log path used for auto logging in this command."""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    base_name = "assembly_log"
    if doc and doc.dataFile:
        base_name = doc.dataFile.name
    elif doc and doc.name:
        base_name = doc.name
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
    if not base_name.lower().endswith(".log"):
        base_name += ".log"
    return os.path.join(ptutil.default_log_directory(), base_name)


def _extract_latest_bottom_up_order(log_lines):
    """Extract the most recent Bottom-up order section from a log file."""
    marker_indexes = [
        i for i, line in enumerate(log_lines) if line.strip() == "Bottom-up order:"
    ]
    if not marker_indexes:
        return []

    start_idx = marker_indexes[-1] + 1
    order = []
    for line in log_lines[start_idx:]:
        value = line.strip()
        if not value or value == "Document save log:":
            break
        # Each order line is "doc_id|name"; compare on the stable doc_id so a
        # component rename does not invalidate an otherwise-resumable run.
        order.append(value.split("|", 1)[0])
    return order


def _extract_last_checkpoint(log_lines):
    """Return the last document checkpoint tuple (doc_id, saved_index).

    Only per-document checkpoints carry a ``doc_id`` field; the final
    "main assembly" checkpoint has none and is therefore skipped.
    """
    last_doc_id = None
    last_saved_index = 0

    for line in log_lines:
        line = line.strip()
        if not line.startswith("CHECKPOINT|SAVE_UPLOAD_COMPLETE|"):
            continue
        parts = line.split("|")
        fields = {}
        for part in parts[2:]:
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            fields[k] = v

        doc_id = fields.get("doc_id")
        if not doc_id:
            continue

        try:
            saved_index = int(fields.get("saved_index", "0"))
        except ValueError:
            saved_index = 0

        last_doc_id = doc_id
        last_saved_index = saved_index

    return last_doc_id, last_saved_index


def _analyze_resume_state(log_path, fusion_client_version, current_doc_ids):
    """Inspect an existing log and return whether this run should resume.

    ``current_doc_ids`` is the freshly computed bottom-up order of document ids;
    it is compared against the ids recorded in the previous log to decide whether
    the previous run's checkpoints still apply.
    """
    result = {
        "log_exists": False,
        "matches_version": False,
        "completed_successfully": False,
        "dag_matches": False,
        "should_resume": False,
        "resume_doc_id": None,
        "resume_start_index": 0,
        "last_saved_index": 0,
        "clear_log": False,
        "status_message": "No previous log found. A full run will start.",
    }

    if not log_path or not os.path.exists(log_path):
        return result

    result["log_exists"] = True
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            log_lines = fh.read().splitlines()
    except Exception as read_error:
        result["status_message"] = (
            f"Found previous log but could not read it ({read_error}). A full run will start."
        )
        return result

    version_line = next(
        (line for line in log_lines if line.startswith("Fusion client version:")), None
    )
    logged_version = ""
    if version_line:
        logged_version = version_line.split(":", 1)[1].strip()

    if logged_version == fusion_client_version:
        result["matches_version"] = True
    else:
        result["status_message"] = (
            "Previous temp log is from a different Fusion client version. "
            "A full run will start."
        )
        return result

    logged_order = _extract_latest_bottom_up_order(log_lines)
    result["dag_matches"] = logged_order == current_doc_ids
    result["completed_successfully"] = any(
        "Bottom-up Update completed successfully" in line for line in log_lines
    )

    if result["completed_successfully"]:
        result["clear_log"] = True
        result["status_message"] = (
            "Previous run completed successfully. Log will be reset for a new run."
        )
        return result

    if not result["dag_matches"]:
        result["status_message"] = (
            "Previous run did not complete, but the document save list has changed. "
            "A full run will start."
        )
        return result

    last_doc_id, last_saved_index = _extract_last_checkpoint(log_lines)
    if last_doc_id and last_doc_id in current_doc_ids:
        next_index = current_doc_ids.index(last_doc_id) + 1
        result["resume_doc_id"] = last_doc_id
        result["resume_start_index"] = min(next_index, len(current_doc_ids))
        result["last_saved_index"] = max(last_saved_index, 0)
        result["should_resume"] = True
        result["status_message"] = (
            "Resume available. Processing will continue after the last saved document."
        )
        return result

    result["status_message"] = (
        "Previous run did not complete and save list matches. "
        "No completed checkpoint was found, so processing will restart from the beginning."
    )
    return result


def on_input_changed(args: adsk.core.InputChangedEventArgs):
    """Handle changes to UI input controls in the command dialog"""
    try:
        changed = args.input
        inputs = args.inputs
        ui = adsk.core.Application.get().userInterface

        # Handle logging enable/disable toggle
        if changed.id == LOG_ENABLE_ID:
            enabled = adsk.core.BoolValueCommandInput.cast(changed).value
            path_input = adsk.core.StringValueCommandInput.cast(
                inputs.itemById(LOG_PATH_ID)
            )
            browse_btn = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(LOG_BROWSE_ID)
            )
            open_view = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(LOG_OPEN_VIEW_ID)
            )
            # Enable/disable log path controls based on logging checkbox
            path_input.isEnabled = enabled
            browse_btn.isEnabled = enabled
            open_view.isEnabled = enabled

        # Handle browse button click for log file selection
        if changed.id == LOG_BROWSE_ID:
            # Treat as a momentary button
            btn = adsk.core.BoolValueCommandInput.cast(changed)
            # Reset state so it can be clicked again later
            btn.value = False

            # Create and configure file dialog for log file selection
            dlg: adsk.core.FileDialog = ui.createFileDialog()
            dlg.title = "Save log file"
            dlg.filter = "Text files (*.txt);;All Files (*.*)"
            dlg.isMultiSelectEnabled = False
            dlg.initialDirectory = ptutil.default_log_directory()
            dlg.initialFilename = _propose_default_log_filename()

            # If user selected a file, update the path input
            if dlg.showSave() == adsk.core.DialogResults.DialogOK:
                sel_path = dlg.filename
                path_input = adsk.core.StringValueCommandInput.cast(
                    inputs.itemById(LOG_PATH_ID)
                )
                path_input.value = sel_path
    except Exception:
        ui = adsk.core.Application.get().userInterface
        if ui:
            ptutil.handle_error(CMD_NAME, show_message_box=True)
