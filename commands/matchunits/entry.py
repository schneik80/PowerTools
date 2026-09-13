# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Match Units - keep a document's units consistent, in three places.

Three faces, two independent comparisons:

* a **button** on every design Inspect panel that changes the active document's
  units to the application default in one click,
* a **watcher** on ``documentOpened`` that, when the preference
  ``prompt_on_open`` is set, asks yes/no whether to do the same, and
* a **watcher** on ``workspaceActivated`` that, when ``prompt_on_manufacture``
  is set, catches the case where the **Manufacture** workspace's active unit
  system disagrees with the document's design units, and offers to bring
  Manufacture into line. That one is length-only and family-granular; all of
  its logic lives in ``mfg.py``, which explains why.

The two comparisons deliberately do NOT share ``logic.Comparison``. Its
``UnitsState.is_known`` requires both a length and a mass, which is the
invariant that stops the design write path acting on a half-read, and a
length-only comparison run through it would have to fabricate a mass.

The button's icon carries the state: ``resources/`` while the document agrees
with the default, ``resources/mismatch/`` (the same glyph with an alert badge)
while it does not. Its tooltip is rewritten with the actual units either way,
because a badge alone cannot say *which* units disagree.

Three Fusion constraints shape the code:

1. **All the work runs in ``command_created``.** The command builds no inputs,
   so ``execute`` is not guaranteed to fire at all - with no document open it
   never does (f18b911, 11cfc51). ``Command.isAutoExecute`` ends the command by
   itself once this handler returns. Never ``args.command.doExecute()`` here; it
   re-enters the command manager on a half-built command and segfaults Fusion
   (14871d7). Same launcher shape as ``commands/closealldocuments``, and for the
   same reason there is no ``execute``/``destroy`` handler and so no
   ``_command_abort`` flag to consume.
2. **The open-time check is deferred, not run inline.** A modal prompt raised
   from ``documentOpened`` would block Fusion's own open pipeline, and writing
   to the design from an application event races Fusion's background saver. The
   event only arms a ``threading.Timer``, which fires a custom event so the
   check lands on a later main-loop turn (c440ad3, 266e2c2). The worker thread
   touches nothing but ``app.fireCustomEvent`` - not even ``ptutil.log``.
3. **The document handle is not held across the wait.** The deferred turn
   re-reads ``app.activeDocument`` and checks ``isValid`` rather than trusting
   the handle the event carried, because a stale one faults natively instead of
   raising (a1d22e1).

Units are compared on the ``DistanceUnits`` / ``MassUnits`` enums, never on
``UnitsManager.defaultLengthUnits``: the API reference notes that the string
form is reshaped by the user's abbreviation and symbol preferences (inches come
back as ``inch``, ``in`` or ``"``) and points at ``distanceDisplayUnits`` as the
consistent answer. Everything downstream of the two reads lives in
``logic.py``, which imports no ``adsk`` module and is unit tested.
"""

import os
import threading

import adsk.cam
import adsk.core
import adsk.fusion

from ... import config, settings_store
from ...lib import ptAddInUtils as ptutil
from .. import _inspect_panels
from . import logic, mfg

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Match Units"
CMD_ID = "PTND_matchunits"
CMD_Description = (
    "Compare the active document's units with your Fusion default units, and "
    "change the document to match in one click."
)
IS_PROMOTED = False

_RESOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
# Icon set shown while the document agrees with the default units.
MATCH_ICON_FOLDER = _RESOURCES
# Icon set shown while it does not: the same ruler, badged with an alert dot.
MISMATCH_ICON_FOLDER = os.path.join(_RESOURCES, "mismatch", "")

# Custom event that carries the open-time check onto the main thread.
_CHECK_EVENT_ID = "PTND_matchunits_check"

# How long after documentOpened the check runs. Long enough for Fusion to finish
# opening the document and settle its product, short enough that the prompt
# still reads as part of opening the file.
_CHECK_DELAY_SECONDS = 1.5

# Application event handlers, kept referenced so they are not collected.
local_handlers = []

# Resolved unit tables (logic.build_tables). Built once in start().
_tables = None

# The custom-event plumbing for the deferred open-time check.
_check_event_handler = None
_timer = None

# Icon folder currently assigned to the command definition, so the indicator is
# only rewritten when the state actually changes.
_indicator_folder = None

# -- The Manufacture check ---------------------------------------------------
#
# A second, independent check with its OWN timer, event id and handler. Sharing
# the open-time check's plumbing would mean one silently cancelling the other:
# _schedule_check cancels any pending timer, so opening a document and switching
# to Manufacture within the delay would lose whichever armed first.

_MFG_CHECK_EVENT_ID = "PTND_matchunits_mfg_check"

# Longer than the open-time delay on purpose. The first entry into Manufacture
# CREATES the CAM product and loads tool libraries, so the product may not exist
# yet at the moment the workspace event fires.
_MFG_CHECK_DELAY_SECONDS = 3.0

# Resolved at start(); None on a build with no Manufacture workspace, which
# disables the check rather than failing to start.
_mfg_workspace_id = None

_mfg_check_event_handler = None
_mfg_timer = None

# Design length unit value -> metric/imperial (mfg.build_families).
_families = None

# Documents where the user said No, as (document key, the system Manufacture was
# on when they declined). In-memory only, per session. Keyed on the observed
# system so that a genuine change of state can still prompt, and NOT on the
# Document object, which the API does not guarantee is identifiable across two
# calls.
_mfg_declined = set()

# Guards against UnitSystems.Activate provoking an event that re-enters the
# check while the write is still in flight.
_applying = False

# Kept so stop() can actually detach it. Clearing a local_handlers list drops
# the Python reference WITHOUT calling event.remove(), which leaves Fusion
# holding a freed handler on a long-lived UI event.
_workspace_handler = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    """Register the command, place it on the Inspect panels, arm the watcher."""
    global _tables

    _tables = logic.build_tables(
        adsk.fusion.DistanceUnits,
        adsk.fusion.MassUnits,
        adsk.fusion.UnitSystems,
    )
    if _tables.unknown_names:
        # Not fatal: the affected units fall back to an "unrecognized" label
        # rather than a guess. Worth a log line, because it means this build's
        # enums have moved away from logic.py's tables.
        ptutil.log(
            f"{CMD_NAME}: enum names not present on this build: "
            f"{list(_tables.unknown_names)}"
        )

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, MATCH_ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)
    _inspect_panels.add_to_inspect_panels(cmd_def, CMD_NAME, IS_PROMOTED)

    _register_check_event()
    ptutil.add_handler(
        app.documentOpened, document_opened, local_handlers=local_handlers
    )
    ptutil.add_handler(
        app.documentActivated, document_activated, local_handlers=local_handlers
    )

    _start_manufacture_watch()

    # During start-up there is no active product to read yet; documentActivated
    # brings the indicator up to date as soon as there is one.
    if app.isStartupComplete:
        _refresh_indicator()


def stop():
    """Remove every control and handler this command installed."""
    global _timer, _check_event_handler, _tables, _indicator_folder
    global _mfg_timer, _mfg_check_event_handler, _workspace_handler
    global _mfg_workspace_id, _families, _applying

    for timer in (_timer, _mfg_timer):
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
    _timer = None
    _mfg_timer = None

    for event_id in (_CHECK_EVENT_ID, _MFG_CHECK_EVENT_ID):
        try:
            app.unregisterCustomEvent(event_id)
        except Exception:
            pass
    _check_event_handler = None
    _mfg_check_event_handler = None

    # Detach properly: local_handlers.clear() below would only drop the Python
    # reference, leaving Fusion holding a freed handler on workspaceActivated.
    if _workspace_handler is not None:
        try:
            ui.workspaceActivated.remove(_workspace_handler)
        except Exception:
            # Fusion may already have torn the event down during shutdown.
            pass
        _workspace_handler = None

    _mfg_declined.clear()
    _mfg_workspace_id = None
    _families = None
    _applying = False

    _inspect_panels.remove_from_inspect_panels(CMD_ID, CMD_NAME)

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    local_handlers.clear()
    _tables = None
    _indicator_folder = None


# ---------------------------------------------------------------------------
# The button
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Run the whole command. No inputs are built; see the module docstring."""
    ptutil.log(f"{CMD_NAME} Command Event")
    try:
        _match_active_document()
    except Exception:
        ptutil.handle_error(CMD_NAME, show_message_box=True)


def _match_active_document():
    """Compare the active design against the default and change it to match."""
    design = _active_design()
    if not design:
        ui.messageBox(f"{CMD_NAME} needs an open design.", CMD_NAME)
        return

    comparison = _read_comparison(design)
    if comparison is None:
        ui.messageBox(
            "Could not read the document units or your Fusion default units, so "
            "there is nothing to compare. Check the PowerTools log for details.",
            CMD_NAME,
        )
        return

    ptutil.log(f"{CMD_NAME}: {logic.log_line(_tables, comparison)}")

    if comparison.matches:
        # Repaint even so: the click may be the first look at this document.
        _apply_indicator(comparison)
        ui.messageBox(logic.already_matching_text(_tables, comparison), CMD_NAME)
        return

    if not _apply(design, comparison):
        ui.messageBox(
            "Could not change this document's units. Check the PowerTools log "
            "for details.",
            CMD_NAME,
        )
        return

    ui.messageBox(logic.applied_text(_tables, comparison), CMD_NAME)


# ---------------------------------------------------------------------------
# The watcher
# ---------------------------------------------------------------------------


def document_opened(args: adsk.core.DocumentEventArgs):
    """Arm the deferred check for a document that has just opened.

    Nothing is read or prompted here: a modal dialog raised from this event
    blocks Fusion's open pipeline, and touching the design model from an
    application event races the background saver.
    """
    if not settings_store.command_setting("matchunits", "prompt_on_open", False):
        return
    _schedule_check()


def document_activated(args: adsk.core.DocumentEventArgs):
    """Bring the button's icon and tooltip in line with the new active document."""
    _refresh_indicator()


class _CheckHandler(adsk.core.CustomEventHandler):
    """Runs the open-time check on the main thread, after the open has settled."""

    def notify(self, args):
        try:
            _run_open_check()
        except Exception:
            ptutil.handle_error(CMD_NAME)


def _register_check_event():
    """(Re-)register the custom event the timer fires."""
    global _check_event_handler
    # Unregister first so an add-in reload starts from a clean slate.
    try:
        app.unregisterCustomEvent(_CHECK_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(_CHECK_EVENT_ID)
    _check_event_handler = _CheckHandler()
    event.add(_check_event_handler)


def _schedule_check():
    """Hand the check to a worker thread that will bounce it back on an event."""
    global _timer
    if _timer is not None:
        try:
            _timer.cancel()
        except Exception:
            pass
    _timer = threading.Timer(_CHECK_DELAY_SECONDS, _fire_check)
    _timer.daemon = True  # never hold Fusion open on a pending check
    _timer.start()


def _fire_check():
    """Runs on the timer's worker thread.

    Nothing here may touch the Fusion API beyond ``fireCustomEvent`` - not even
    ``ptutil.log``, which calls ``Application.log``. The return value is ignored
    because Fusion returns False even when the event fires (c440ad3).
    """
    try:
        app.fireCustomEvent(_CHECK_EVENT_ID)
    except Exception:
        pass


def _run_open_check():
    """Main-thread body of the deferred turn: compare, then ask.

    The document handle from ``documentOpened`` is deliberately not used - it
    was captured before the wait and could have been invalidated since. The
    active document is re-read and validated here instead.
    """
    # Re-read the preference: the user may have switched it off while the timer
    # was pending, and the settings store is cheap (memoized).
    if not settings_store.command_setting("matchunits", "prompt_on_open", False):
        return

    doc = app.activeDocument
    if not doc or not doc.isValid:
        ptutil.log(f"{CMD_NAME}: no valid active document at check time, skipping.")
        return

    design = _active_design()
    if not design:
        # A document with no design at all, e.g. a standalone drawing. Asked for
        # by product type, so this no longer depends on which workspace happens
        # to be active when the document opens.
        return

    comparison = _read_comparison(design)
    if comparison is None:
        return

    ptutil.log(f"{CMD_NAME} [documentOpened]: {logic.log_line(_tables, comparison)}")
    _apply_indicator(comparison)
    if comparison.matches:
        return

    answer = ui.messageBox(
        logic.prompt_text(_tables, comparison, doc.name),
        CMD_NAME,
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        adsk.core.MessageBoxIconTypes.QuestionIconType,
    )
    if answer != adsk.core.DialogResults.DialogYes:
        ptutil.log(f"{CMD_NAME}: user declined the change.")
        return

    # Re-acquire the design: the prompt pumped the UI while it was up.
    design = _active_design()
    if not design:
        ptutil.log(f"{CMD_NAME}: design went away while the prompt was up.")
        return

    if _apply(design, comparison):
        ptutil.log(f"{CMD_NAME}: {logic.applied_text(_tables, comparison)}")


# ---------------------------------------------------------------------------
# The Manufacture check
# ---------------------------------------------------------------------------


def _start_manufacture_watch():
    """Resolve the Manufacture workspace and start listening for the switch.

    Degrades to "feature off" rather than failing start(): a build with no
    Manufacture workspace, or one that renamed it beyond recognition, just
    never arms the check.
    """
    global _mfg_workspace_id, _families, _workspace_handler

    _families = mfg.build_families(adsk.fusion.DistanceUnits)
    _mfg_workspace_id = config.resolve_manufacture_workspace_id()
    if not _mfg_workspace_id:
        ptutil.log(f"{CMD_NAME}: no Manufacture workspace; that check is off.")
        return

    ptutil.log(f"{CMD_NAME}: Manufacture workspace is {_mfg_workspace_id!r}.")
    _register_mfg_check_event()
    # Held rather than pushed into local_handlers, so stop() can detach it.
    _workspace_handler = ptutil.add_handler(ui.workspaceActivated, workspace_activated)


def workspace_activated(args: adsk.core.WorkspaceEventArgs):
    """Repaint the indicator, and arm the Manufacture check on the way in.

    Fires for EVERY workspace, so the check is filtered on the resolved
    Manufacture id rather than on "not Design".
    """
    # The indicator is a function of the design, which is readable from any
    # workspace, so this is also how returning to Design gets a fresh verdict.
    _refresh_indicator()

    if not _mfg_workspace_id:
        return
    try:
        if args.workspace.id != _mfg_workspace_id:
            return
    except Exception:
        return
    if not settings_store.command_setting("matchunits", "prompt_on_manufacture", False):
        return
    _schedule_mfg_check()


class _MfgCheckHandler(adsk.core.CustomEventHandler):
    """Runs the Manufacture check on the main thread, after the switch settles."""

    def notify(self, args):
        try:
            _run_mfg_check()
        except Exception:
            ptutil.handle_error(f"{CMD_NAME} (manufacture)")


def _register_mfg_check_event():
    """(Re-)register the custom event the Manufacture timer fires."""
    global _mfg_check_event_handler
    try:
        app.unregisterCustomEvent(_MFG_CHECK_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(_MFG_CHECK_EVENT_ID)
    _mfg_check_event_handler = _MfgCheckHandler()
    event.add(_mfg_check_event_handler)


def _schedule_mfg_check():
    """Arm the deferred check, replacing any pending one.

    Cancel-and-replace means a burst of workspace switching produces one check
    rather than a queue of prompts.
    """
    global _mfg_timer
    if _mfg_timer is not None:
        try:
            _mfg_timer.cancel()
        except Exception:
            pass
    _mfg_timer = threading.Timer(_MFG_CHECK_DELAY_SECONDS, _fire_mfg_check)
    _mfg_timer.daemon = True
    _mfg_timer.start()


def _fire_mfg_check():
    """Runs on the timer's worker thread. fireCustomEvent and nothing else."""
    try:
        app.fireCustomEvent(_MFG_CHECK_EVENT_ID)
    except Exception:
        pass


def _document_key(doc):
    """A stable-enough identity for the declined memo.

    ``dataFile.id`` where there is one; the name otherwise, because an unsaved
    document has no dataFile. Never the Document object itself — the API does
    not guarantee two calls hand back an identifiable same object.
    """
    data_file = _read(lambda: doc.dataFile)
    if data_file is not None:
        urn = _read(lambda: data_file.id)
        if urn:
            return urn
    return _read(lambda: doc.name) or ""


def _run_mfg_check():
    """Main-thread body of the deferred Manufacture check."""
    if _applying:
        return
    if _tables is None or _families is None:
        # start() did not get far enough to build them.
        return
    if not settings_store.command_setting("matchunits", "prompt_on_manufacture", False):
        return

    # The user had the delay to switch away again, and UnitSystems.List reports
    # whichever product is active.
    if not _in_manufacture():
        return

    doc = app.activeDocument
    if not doc or not doc.isValid:
        return

    design = _active_design()
    if not design:
        return

    cam = adsk.cam.CAM.cast(app.activeProduct)
    if cam is None:
        # First entry into Manufacture creates the CAM product; it is simply not
        # there yet. Do not re-arm — the next switch in will catch it.
        ptutil.log(f"{CMD_NAME}: no CAM product yet, skipping the check.")
        return

    design_distance = _read(lambda: design.fusionUnitsManager.distanceDisplayUnits)
    active_id = _read_manufacture_system()
    comparison = mfg.compare(_families, design_distance, active_id)
    if comparison is None:
        ptutil.log(
            f"{CMD_NAME}: cannot compare manufacture units "
            f"(design {design_distance!r}, manufacture {active_id!r})."
        )
        return

    # Independent corroboration before anything is offered: the parsed id
    # against a measured scale. evaluateExpression returns -1 on error rather
    # than raising, which mfg.system_for_scale rejects.
    measured = mfg.system_for_scale(
        _read(lambda: cam.unitsManager.evaluateExpression("1"))
    )
    if measured is not None and mfg.family_of_system(measured) != mfg.family_of_system(
        active_id
    ):
        ptutil.log(
            f"{CMD_NAME}: manufacture reads disagree - UnitSystems.List says "
            f"{active_id!r}, measured scale says {measured!r}. Saying nothing."
        )
        return

    ptutil.log(f"{CMD_NAME}: {mfg.log_line(_tables.distance, comparison)}")
    if comparison.matches:
        return

    key = (_document_key(doc), comparison.active_id)
    if key in _mfg_declined:
        return

    answer = ui.messageBox(
        mfg.prompt_text(_tables.distance, comparison, doc.name),
        CMD_NAME,
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        adsk.core.MessageBoxIconTypes.QuestionIconType,
    )
    if answer != adsk.core.DialogResults.DialogYes:
        # Remembered for the session so switching in and out does not nag.
        _mfg_declined.add(key)
        ptutil.log(f"{CMD_NAME}: user declined the manufacture change.")
        return

    if _apply_manufacture(comparison):
        # No confirmation dialog: the user clicked Yes a moment ago and the
        # viewport now reads in the new unit, so an OK box is a second click
        # for something already visible. Matches the open-time check, which
        # has only ever logged. Failure still speaks up, because that is the
        # outcome the user cannot see.
        ptutil.log(f"{CMD_NAME}: {mfg.applied_text(comparison)}")
    else:
        ui.messageBox(
            "Could not change the Manufacture workspace units. Check the "
            "PowerTools log for details.",
            CMD_NAME,
        )


def _in_manufacture() -> bool:
    """True when the Manufacture workspace is the active one, right now."""
    if not _mfg_workspace_id:
        return False
    try:
        return ui.activeWorkspace.id == _mfg_workspace_id
    except Exception:
        return False


def _read_manufacture_system():
    """The active unit system id of whichever product is active.

    There is no API for this: the CAM product has no settable units manager and
    its inherited one exposes only a preference-shaped string. ``UnitSystems``
    text commands are the whole interface.

    Returns:
        The system id, or None when the output could not be parsed — which is
        logged, because that output is the only diagnostic there is.
    """
    text = _read(lambda: app.executeTextCommand("UnitSystems.List"))
    report = mfg.parse_unit_systems(text)
    if report.active_id is None:
        ptutil.log(
            f"{CMD_NAME}: could not read the active unit system. "
            f"UnitSystems.List said:\n{text}"
        )
    return report.active_id


def _apply_manufacture(comparison) -> bool:
    """Activate the target unit system, and verify it landed where intended.

    ``UnitSystems.Activate`` takes no target argument: it acts on whatever
    product is active. Both the timer delay and the modal prompt gave the user
    time to switch back to Design, and firing it there would rewrite the
    DESIGN units instead — the exact thing this command offers to do
    deliberately, happening by accident. Hence the workspace re-check
    immediately before the write, and the verification of both sides after it.

    Args:
        comparison: The comparison whose ``target_id`` is to be activated.

    Returns:
        True only when Manufacture moved to the target family and the design
        side did not move at all.
    """
    global _applying

    if not _in_manufacture():
        ptutil.log(
            f"{CMD_NAME}: no longer in Manufacture, abandoning the change "
            "rather than risk rewriting the design."
        )
        return False

    design = _active_design()
    before = _read(lambda: design.fusionUnitsManager.distanceDisplayUnits)
    if before is None:
        # Without a readable design unit there is no way to prove afterwards
        # that the write landed on Manufacture and not on the design, and that
        # proof is the whole point of the verification below.
        ptutil.log(
            f"{CMD_NAME}: cannot read the design units, so the change cannot "
            "be verified. Not writing."
        )
        return False

    _applying = True
    try:
        result = _read(
            lambda: app.executeTextCommand(
                f"UnitSystems.Activate {comparison.target_id}"
            )
        )
        ptutil.log(
            f"{CMD_NAME}: UnitSystems.Activate {comparison.target_id} -> {result!r}"
        )

        # Verify rather than trust. The text command reports nothing useful.
        settled = _read_manufacture_system()
        if mfg.family_of_system(settled) != mfg.family_of_system(comparison.target_id):
            ptutil.log(
                f"{CMD_NAME}: manufacture did not move - still {settled!r}, "
                f"wanted {comparison.target_id!r}."
            )
            return False

        after = _read(lambda: _active_design().fusionUnitsManager.distanceDisplayUnits)
        if after != before:
            ptutil.log(
                f"{CMD_NAME}: the DESIGN units moved ({before!r} -> {after!r}). "
                "That is not what was asked for."
            )
            return False
    finally:
        _applying = False

    return True


# ---------------------------------------------------------------------------
# Reading and writing units
# ---------------------------------------------------------------------------


def _active_design():
    """The active document's Design product, whatever workspace is active.

    ``Design.cast(app.activeProduct)`` returns None in Manufacture, Animation,
    Drawing and Render, because activeProduct is that workspace's product. The
    design is still there — it just has to be asked for by product type, the
    way commands/animationnamedview does it.

    Returns:
        The ``Design``, or None for a document that genuinely has none.
    """
    doc = _read(lambda: app.activeDocument)
    if doc is None:
        return None
    product = _read(lambda: doc.products.itemByProductType("DesignProductType"))
    return adsk.fusion.Design.cast(product) if product else None


def _read_comparison(design: adsk.fusion.Design):
    """Read both sides of the comparison.

    Args:
        design: The open design.

    Returns:
        A ``logic.Comparison``, or None if either side could not be read (which
        is logged). Every read is guarded individually so a build that drops one
        property degrades to "cannot compare" rather than to a wrong answer.
    """
    if _tables is None:
        return None

    units_manager = _read(lambda: design.fusionUnitsManager)
    document = logic.UnitsState(
        distance=_read(lambda: units_manager.distanceDisplayUnits),
        mass=_read(lambda: units_manager.massDisplayUnits),
    )
    application = _application_units()

    comparison = logic.compare(document, application)
    if comparison is None:
        ptutil.log(
            f"{CMD_NAME}: incomplete units read - document "
            f"{document.distance}/{document.mass}, default "
            f"{application.distance}/{application.mass}"
        )
    return comparison


def _application_units() -> logic.UnitsState:
    """The Default Units preference for a new Fusion design.

    ``defaultUnitsPreferences`` is a collection keyed by product name; the
    Fusion design entry is the one that backs Preferences > Design > Default
    Units, and is documented as reachable by that exact name.
    """
    prefs = _read(lambda: app.preferences.defaultUnitsPreferences.itemByName("Design"))
    if prefs is None:
        ptutil.log(f"{CMD_NAME}: no 'Design' entry in defaultUnitsPreferences.")
        return logic.UnitsState()
    return logic.UnitsState(
        distance=_read(lambda: prefs.distanceDisplayUnits),
        mass=_read(lambda: prefs.massDisplayUnits),
    )


def _apply(design: adsk.fusion.Design, comparison) -> bool:
    """Write the application default onto *design*.

    Args:
        design: The design to change. Freshly acquired by the caller.
        comparison: The comparison the plan is derived from.

    Returns:
        True if every write in the plan succeeded. A partial write is reported
        as a failure and logged property by property, because half-applied units
        are worse than none.
    """
    plan = logic.change_plan(_tables, comparison)
    if plan.is_empty:
        return True

    units_manager = _read(lambda: design.fusionUnitsManager)
    if units_manager is None:
        ptutil.log(f"{CMD_NAME}: design has no fusionUnitsManager.")
        return False

    ok = True
    if plan.system is not None:
        ok = _set(units_manager, "unitSystem", plan.system)
    else:
        # No predefined system covers the target pair, so the halves that differ
        # are set individually. Each assignment flips unitSystem to Custom,
        # which is correct here: the default itself is a custom combination.
        if plan.distance is not None:
            ok = _set(units_manager, "distanceDisplayUnits", plan.distance) and ok
        if plan.mass is not None:
            ok = _set(units_manager, "massDisplayUnits", plan.mass) and ok

    # Re-read rather than assume the document now matches: if Fusion refused
    # half of a field-by-field write, the button should say so.
    _refresh_indicator()
    return ok


# ---------------------------------------------------------------------------
# The state indicator
# ---------------------------------------------------------------------------


def _refresh_indicator():
    """Re-read the active design and repaint the button's state, quietly.

    Called from ``documentActivated``, so it must not prompt, must not write,
    and must not raise.
    """
    try:
        design = _active_design()
        if not design:
            _reset_indicator()
            return
        comparison = _read_comparison(design)
        if comparison is None:
            _reset_indicator()
            return
        _apply_indicator(comparison)
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}._refresh_indicator")


def _apply_indicator(comparison):
    """Point the command definition at the icon set for *comparison*.

    ``CommandDefinition.resourceFolder`` and ``.tooltip`` are both documented as
    settable. The folder is only written when it changes, so a document switch
    that does not change the verdict costs one comparison and no UI work.
    """
    global _indicator_folder
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        return
    folder = MATCH_ICON_FOLDER if comparison.matches else MISMATCH_ICON_FOLDER
    try:
        if folder != _indicator_folder:
            cmd_def.resourceFolder = folder
            _indicator_folder = folder
            ptutil.log(
                f"{CMD_NAME}: icon set to {os.path.basename(folder.rstrip(os.sep)) or 'resources'}"
            )
        cmd_def.tooltip = logic.tooltip_text(_tables, comparison)
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}._apply_indicator")


def _reset_indicator():
    """Fall back to the neutral icon and the static description.

    Used when there is nothing to compare - no design open, or a read that
    failed. Showing the alert badge then would claim a mismatch nobody
    established.
    """
    global _indicator_folder
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        return
    try:
        if _indicator_folder != MATCH_ICON_FOLDER:
            cmd_def.resourceFolder = MATCH_ICON_FOLDER
            _indicator_folder = MATCH_ICON_FOLDER
        cmd_def.tooltip = CMD_Description
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}._reset_indicator")


# ---------------------------------------------------------------------------
# Guarded property access
# ---------------------------------------------------------------------------


def _read(getter):
    """Return ``getter()``, or None if it raised. Logs nothing; callers do."""
    try:
        return getter()
    except Exception:
        return None


def _set(target, name: str, value) -> bool:
    """Assign ``target.name = value``, reporting failure as False.

    Args:
        target: The object to write to.
        name: The property name, also used in the error log.
        value: The value to assign.

    Returns:
        True if the assignment went through.
    """
    try:
        setattr(target, name, value)
        return True
    except Exception:
        ptutil.handle_error(f"{CMD_NAME}: setting {name}")
        return False
