# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Team Add-ins — keep a team's private add-ins in step from a hub folder.
#
# Why the check is deferred rather than backgrounded: the Fusion Data API is
# main-thread only, so a worker thread cannot read the hub itself. What a worker
# thread CAN do is fire a custom event, and Fusion dispatches that handler on
# the main thread on a later turn. So start() returns immediately, a daemon
# timer waits, and the actual check runs once Fusion has finished launching.
# The same deferral is used by commands/assemblyintent and commands/externalize.
#
# Three constraints in this file are load-bearing and were paid for elsewhere in
# this add-in (see assemblyintent/entry.py:_schedule_finish_insert):
#
#   * The worker thread must touch nothing but fireCustomEvent — not even
#     ptutil.log, which calls Application.log.
#   * fireCustomEvent returns False even when the event fires. Its return value
#     is ignored.
#   * The timer is a daemon, so a pending check never holds Fusion open.

import json
import os
import threading

import adsk.core

from ... import config, settings_store
from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from . import sync

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = "PT_teamaddins"
CMD_NAME = "Team Add-ins"
CMD_Description = (
    "Check the hub's Shared Addins folder and install any add-in that is new or "
    "updated. Runs automatically shortly after Fusion starts; click to check now."
)

IS_PROMOTED = False

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

PALETTE_ID = config.team_addins_palette_id
PALETTE_NAME = "Team Add-ins"
_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "report.html").replace("\\", "/")
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

# The setup command this one sends the user to when the folder does not exist.
CONFIG_CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_configTeamAddins"

_CHECK_EVENT_ID = "PT_teamaddins_startup_check"

# Fallback used only when the preference is missing or unreadable; the real
# default lives in settings_store.COMMAND_SETTING_DEFAULTS and the two are kept
# in step.
_DEFAULT_DELAY_SECONDS = 25

# Retry delay when the check lands before the user is signed in to a hub.
_HUB_RETRY_SECONDS = 60.0

local_handlers = []

# Registered custom event handler, held in a module global so it is not garbage
# collected. Custom events use an explicit handler class rather than
# ptutil.add_handler — the convention the other deferred commands follow.
_check_event_handler = None
_timer = None
_retry_used = False

# Report produced by apply_pending() during start(), surfaced by the deferred
# check so start() itself never opens UI.
_startup_pending_report = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _setting(name, default):
    try:
        return settings_store.command_setting("teamaddins", name, default)
    except Exception:
        return default


def _startup_delay() -> float:
    try:
        value = float(_setting("startup_delay_seconds", _DEFAULT_DELAY_SECONDS))
    except (TypeError, ValueError):
        value = float(_DEFAULT_DELAY_SECONDS)
    # A check that fires during Fusion's own start-up is the thing this whole
    # design exists to avoid, and one that never fires is useless.
    return max(5.0, min(value, 600.0))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
        )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    panel = _ui_bootstrap.get_power_tools_panel()
    if panel is not None:
        # Clear stale controls from a prior version or an unclean reload so the
        # button never accumulates.
        existing = panel.controls.itemById(CMD_ID)
        while existing is not None:
            existing.deleteMe()
            existing = panel.controls.itemById(CMD_ID)
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED

    _register_check_event()

    # The deferred turn is scheduled even when the automatic check is off, so
    # that a package staged by a previous session still gets applied. Applying
    # it here instead would put file moves and a script start straight onto
    # Fusion's launch path, which is the one thing this design exists to avoid.
    _schedule_check(_startup_delay())


def stop():
    global _timer, _check_event_handler, _startup_pending_report, _retry_used

    _retry_used = False

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
    _startup_pending_report = None

    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.deleteMe()

    panel = _ui_bootstrap.get_power_tools_panel()
    if panel is not None:
        control = panel.controls.itemById(CMD_ID)
        if control:
            control.deleteMe()

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    local_handlers.clear()


# ---------------------------------------------------------------------------
# Deferred start-up check
# ---------------------------------------------------------------------------


class _CheckHandler(adsk.core.CustomEventHandler):
    """Runs the hub check on the main thread, well after Fusion has launched."""

    def notify(self, args):
        try:
            _run_startup_check()
        except Exception:
            ptutil.handle_error(CMD_NAME)


def _register_check_event():
    global _check_event_handler
    # Unregister first so an add-in reload starts from a clean slate.
    try:
        app.unregisterCustomEvent(_CHECK_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(_CHECK_EVENT_ID)
    _check_event_handler = _CheckHandler()
    event.add(_check_event_handler)


def _schedule_check(delay_seconds: float):
    global _timer
    _timer = threading.Timer(delay_seconds, _fire_check)
    _timer.daemon = True  # never hold Fusion open on a pending check
    _timer.start()
    ptutil.log(f"{CMD_NAME}: check queued (+{delay_seconds:.0f}s, {_CHECK_EVENT_ID}).")


def _fire_check():
    """Hand the check to the main thread. Runs on the timer's worker thread.

    Nothing here may touch the Fusion API beyond fireCustomEvent — including
    ptutil.log, which calls Application.log. The return value is ignored because
    Fusion returns False even when the event fires.
    """
    try:
        app.fireCustomEvent(_CHECK_EVENT_ID)
    except Exception:
        pass


def _run_startup_check():
    """Main-thread body of the deferred turn: apply pending, then check."""
    global _retry_used, _startup_pending_report

    # Finish anything a previous session could not swap in while it was
    # running. Held across a retry so it is reported exactly once.
    pending_report = _startup_pending_report
    if pending_report is None:
        pending_report = sync.apply_pending()
    _startup_pending_report = None

    if not _setting("auto_check_on_launch", True):
        ptutil.log(f"{CMD_NAME}: automatic launch check is off.")
        if pending_report is not None and pending_report.is_news:
            _update_tooltip(pending_report)
            _show_report(pending_report)
        return

    # Not signed in yet is a timing problem, not a user problem. Give it one
    # more go, quietly, then leave it to the manual button.
    if team_hub_missing() and not _retry_used:
        _retry_used = True
        ptutil.log(f"{CMD_NAME}: no active hub yet; retrying in {_HUB_RETRY_SECONDS:.0f}s.")
        _startup_pending_report = pending_report
        _schedule_check(_HUB_RETRY_SECONDS)
        return

    report = sync.check_and_apply(
        trigger="startup",
        force=False,
        allow_reload=bool(_setting("auto_reload", True)),
    )

    if pending_report is not None:
        _merge(report, pending_report)

    _update_tooltip(report)

    # The rule that makes this feature liveable: nothing changed means the user
    # sees nothing at all. A repeat of a failure already reported for the same
    # manifest version is also suppressed, so a package that is broken at the
    # source cannot nag on every launch — the manual check still shows it.
    if not report.is_news:
        return
    if _is_repeat_failure(report):
        ptutil.log(f"{CMD_NAME}: suppressing repeat failure report.")
        return

    _show_report(report)


def team_hub_missing() -> bool:
    try:
        return app.data.activeHub is None
    except Exception:
        return True


def _merge(report, pending):
    """Fold a pending-updates report into the main one."""
    report.rows = list(pending.rows) + list(report.rows)
    report.errors = list(pending.errors) + list(report.errors)
    if pending.restart_required:
        report.restart_required = True
    if pending.rows and report.status in (sync.STATUS_UP_TO_DATE,):
        report.status = sync.STATUS_APPLIED
        report.headline = pending.headline


def _is_repeat_failure(report) -> bool:
    """True when the automatic check should stay quiet about this failure.

    Only a pure-failure report is ever suppressed, and only after it has been
    shown once: if anything also installed successfully the user sees it.
    """
    if not report.repeat_failure:
        return False
    return not any(r.state != "failed" for r in report.rows)


def _update_tooltip(report):
    """Keep the button's tooltip as the always-available status line."""
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def is None:
        return
    if report.status == sync.STATUS_NOT_CONFIGURED:
        suffix = "No Shared Addins folder in this hub yet."
    elif report.restart_required:
        suffix = f"Last checked {report.checked_at} — restart Fusion to finish."
    elif report.rows:
        suffix = f"Last checked {report.checked_at} — {report.headline}."
    elif report.errors:
        suffix = f"Last checked {report.checked_at} — problems found."
    else:
        suffix = f"Last checked {report.checked_at} — up to date."
    try:
        cmd_def.tooltip = f"{CMD_Description}\n\n{suffix}"
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Manual check — the toolbar button
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Run the check inline.

    No command inputs are added, so Fusion auto-executes without showing a
    dialog — the same shape commands/confighub uses.
    """
    ptutil.log(f"{CMD_NAME} Command Created Event")

    progress = None
    try:
        progress = ui.progressBar
        progress.showBusy("Checking the Shared Addins folder for updates…")
    except Exception:
        progress = None

    try:
        report = sync.check_and_apply(
            trigger="manual",
            force=True,
            allow_reload=bool(_setting("auto_reload", True)),
        )
    finally:
        if progress is not None:
            try:
                progress.hide()
            except Exception:
                pass

    _update_tooltip(report)
    # A click always gets an answer, even "you are up to date".
    _show_report(report)


# ---------------------------------------------------------------------------
# Report palette
# ---------------------------------------------------------------------------


def _theme() -> str:
    """Return "dark" or "light" for the palette.

    activeUserInterfaceTheme (Fusion, January 2026) already resolves the
    "follow device" setting to the theme actually applied, which is exactly
    what a palette needs. userInterfaceTheme is the fallback on older builds,
    where DeviceUserInterfaceTheme cannot be resolved from here and is treated
    as dark — the same default the CSS uses.
    """
    themes = adsk.core.UserInterfaceThemes
    dark = (themes.DarkBlueUserInterfaceTheme, themes.DarkGrayUserInterfaceTheme)
    general = None
    try:
        general = app.preferences.generalPreferences
        return "dark" if general.activeUserInterfaceTheme in dark else "light"
    except Exception:
        pass
    try:
        theme = general.userInterfaceTheme
        return (
            "dark"
            if theme in dark or theme == themes.DeviceUserInterfaceTheme
            else "light"
        )
    except Exception:
        return "dark"


def _write_init_js(state: dict):
    try:
        with open(INIT_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"window.__ptTeamAddins = {json.dumps(state)};\n")
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: could not write init.js — {exc}")


def _show_report(report):
    state = report.to_dict()
    state["theme"] = _theme()

    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception:
            pass

    _write_init_js(state)
    palette = palettes.add(
        id=PALETTE_ID,
        name=PALETTE_NAME,
        htmlFileURL=PALETTE_URL,
        isVisible=True,
        showCloseButton=True,
        isResizable=True,
        width=560,
        height=460,
        useNewWebBrowser=True,
    )
    ptutil.add_handler(palette.closed, _palette_closed)
    ptutil.add_handler(palette.incomingFromHTML, _palette_incoming)
    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    palette.isVisible = True


def _palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception:
            pass


def _palette_incoming(html_args: adsk.core.HTMLEventArgs):
    action = html_args.action
    try:
        if action == "close":
            palette = ui.palettes.itemById(PALETTE_ID)
            if palette is not None:
                palette.deleteMe()

        elif action == "configure":
            cmd_def = ui.commandDefinitions.itemById(CONFIG_CMD_ID)
            if cmd_def:
                cmd_def.execute()
            else:
                ui.messageBox(
                    "The Team Add-ins commands are disabled. Enable them in "
                    "PowerTools Preferences and restart Fusion.",
                    CMD_NAME,
                )
    except Exception:
        ptutil.handle_error(CMD_NAME)

    html_args.returnData = "OK"
