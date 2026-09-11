# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Match Units - reconcile a document's units with the application default.

Two faces, one comparison:

* a **button** on every design Inspect panel that changes the active document's
  units to the application default in one click, and
* a **watcher** on ``documentOpened`` that, when the preference
  ``prompt_on_open`` is set, asks yes/no whether to do the same.

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

import adsk.core
import adsk.fusion

from ... import settings_store
from ...lib import ptAddInUtils as ptutil
from .. import _inspect_panels
from . import logic

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

    # During start-up there is no active product to read yet; documentActivated
    # brings the indicator up to date as soon as there is one.
    if app.isStartupComplete:
        _refresh_indicator()


def stop():
    """Remove every control and handler this command installed."""
    global _timer, _check_event_handler, _tables, _indicator_folder

    if _timer is not None:
        try:
            _timer.cancel()
        except Exception:
            pass
        _timer = None

    try:
        app.unregisterCustomEvent(_CHECK_EVENT_ID)
    except Exception:
        pass
    _check_event_handler = None

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
    design = adsk.fusion.Design.cast(app.activeProduct)
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

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        # A drawing, a CAM setup or a non-design document. Nothing to compare.
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
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ptutil.log(f"{CMD_NAME}: design went away while the prompt was up.")
        return

    if _apply(design, comparison):
        ptutil.log(f"{CMD_NAME}: {logic.applied_text(_tables, comparison)}")


# ---------------------------------------------------------------------------
# Reading and writing units
# ---------------------------------------------------------------------------


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
        design = adsk.fusion.Design.cast(app.activeProduct)
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
