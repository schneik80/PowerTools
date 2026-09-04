# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Document History.
#
# A QAT button that opens an HTML palette showing the active document's version
# history as a stack of day rows, newest at the top: one row per calendar day,
# split into a track per author, with the saves drawn on a 00:00-24:00 clock
# axis and the elapsed time called out between rows.
#
# It replaces the previous behaviour of selecting the root component and running
# Fusion's built-in ShowHistoryCmd. That panel is a single undifferentiated
# strip: it cannot show who saved what, how a working day was shaped, or how
# long a design sat untouched, all of which are the questions this view exists
# to answer.
#
# The split of work:
#   * this file      - Fusion contact only: read the versions, serve the page,
#                      pump thumbnails.
#   * history_model  - the bucketing (day rows, author tracks, gaps). Pure and
#                      unit-tested; it is where a wrong number would come from.
#   * resources/html - the drawing, and the width-dependent geometry that has
#                      to be measured in the browser.

import json
import os
import threading
import time

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from ...lib.ptAddInUtils import recents_utils as recents
from . import history_model as model
from . import mfgdm_history

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "History"
CMD_ID = "PTND_history"
CMD_Description = (
    "Show the active design's version history as a stack of day rows in a "
    "palette: one row per day, a track per author, saves placed on a clock "
    "axis, and the elapsed time called out between days. Reaching Fusion's own "
    "history panel otherwise means right-clicking the root component in the "
    "browser, which is easy to miss."
)

PALETTE_ID = config.document_history_palette_id
PALETTE_NAME = "Document History"
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight

# Docked width. Leaves the day view about 310 px of plot, which is over
# hourTicks()'s 260 px threshold: three-hourly gridlines with midnight, noon
# and midnight labelled, rather than the six-hourly noon-only axis a narrower
# dock falls back to. The layout degrades further on its own if the dock is
# dragged in.
PALETTE_WIDTH = 400
PALETTE_HEIGHT = 720

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "index.html").replace("\\", "/")
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

# Custom event that drives the lazy thumbnail pump. ``DataFile.thumbnail``
# returns a DataObjectFuture and adsk.core.Future has no completion event, so a
# thumbnail can only be collected by polling. Polling inline would hold the UI
# thread while the palette is on screen, so each poll is one turn of a
# timer-fired custom event instead - the same shape the Assembly Palette
# gallery uses, and for the same reason.
# Custom event that carries the history read off the commandCreated stack.
# Two reasons it cannot happen inline. Reading
# ``rootDataComponent.mfgdmModelId`` from commandCreated destabilised Fusion
# once already (234b043, commands/partnumber_shared/intent.py). And the read is
# a cloud call: doing it before the palette exists meant the user stared at
# nothing for as long as it took - 21 seconds on a 27-version design.
_LOAD_EVENT_ID = "PTND_history_loadHistory"
_LOAD_DELAY_SECONDS = 0.1

_THUMB_EVENT_ID = "PTND_history_thumbTick"
_THUMB_TICK_SECONDS = 0.15
_THUMB_MAX_INFLIGHT = 8

# A future that never leaves ProcessingFutureState is abandoned after this so a
# single wedged download cannot keep the pump ticking for the whole session.
_THUMB_FUTURE_TIMEOUT_SECONDS = 20.0

# Re-arm a tick scheduled this long ago that never ran. fireCustomEvent returns
# False even when it works, so its return value cannot be trusted to prove the
# tick is really coming; this bounds the damage if one is lost.
_THUMB_TICK_STALE_SECONDS = 2.0

# adsk.core.FutureStates, as plain ints - named locally so the pump reads the
# same way as the one in commands/assemblypalette.
_FUTURE_PROCESSING = 0
_FUTURE_FINISHED = 1

# versionId -> the version's DataFile, captured while the history was read.
# Only the thumbnail pump uses these; a stale handle degrades to "no preview".
_version_files: dict = {}

# The state last written into init.js. Kept so the page's load handshake can be
# answered from memory instead of reading the whole history from the cloud a
# second time - see _open_palette.
_last_state: dict = {}

# versionId -> (future, started_monotonic) for downloads in flight.
_thumb_inflight: dict = {}
_thumb_queue: list = []
_thumb_missing: set = set()
_thumb_tick_pending = False
_thumb_tick_scheduled_at = 0.0
_thumb_event_handler = None
_load_event_handler = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    global _thumb_event_handler, _load_event_handler

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    qat = ui.toolbars.itemById("QAT")
    if qat:
        qat.controls.addCommand(cmd_def, "save", True)

    # Unregister first so a re-run of the add-in without a Fusion restart does
    # not stack a second handler on the same event.
    try:
        app.unregisterCustomEvent(_THUMB_EVENT_ID)
    except Exception:
        pass
    thumb_event = app.registerCustomEvent(_THUMB_EVENT_ID)
    _thumb_event_handler = _ThumbTickHandler()
    thumb_event.add(_thumb_event_handler)

    try:
        app.unregisterCustomEvent(_LOAD_EVENT_ID)
    except Exception:
        pass
    load_event = app.registerCustomEvent(_LOAD_EVENT_ID)
    _load_event_handler = _LoadHistoryHandler()
    load_event.add(_load_event_handler)


def stop():
    global _thumb_event_handler, _load_event_handler

    qat = ui.toolbars.itemById("QAT")
    if qat:
        command_control = qat.controls.itemById(CMD_ID)
        if command_control:
            command_control.deleteMe()

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()

    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        try:
            palette.deleteMe()
        except Exception:
            pass

    for event_id in (_THUMB_EVENT_ID, _LOAD_EVENT_ID):
        try:
            app.unregisterCustomEvent(event_id)
        except Exception:
            pass
    _thumb_event_handler = None
    _load_event_handler = None
    _reset_thumb_pump()
    _version_files.clear()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Open the palette straight from the click.

    Deliberately not by way of the command's execute event: this command has no
    CommandInputs, and execute only fires when Fusion runs a command through its
    document-scoped pipeline. The palette is opened here for the same reason
    Preferences and Close All Documents do their work here (f18b911, 11cfc51).
    """
    ptutil.log(f"{CMD_NAME} Command Created Event")

    try:
        doc = app.activeDocument
    except Exception:
        doc = None
    if doc is None:
        ui.messageBox("Open a document to see its version history.", CMD_NAME, 0, 2)
        return

    # The version history lives in the cloud, so an unsaved document has none.
    if not ptutil.isSaved():
        return

    # The palette is opened by the deferred load, not here: it can only be
    # populated through init.js, which has to be written before the page loads,
    # and the read that fills it must not happen on this stack. See
    # _LoadHistoryHandler.
    _schedule_load()


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def _open_palette(state: dict):
    """Write *state* into init.js and show a palette built from it.

    init.js is the only channel to this page that is known to work. The page
    sends `htmlReady` on load and Python answers with `setHistory`, but that
    handshake has never once been observed arriving - the log has counted zero
    of them across every session - so anything the first paint needs has to be
    on disk before the page loads. A build that opened the palette first and
    pushed the history afterwards left it blank.

    An open palette is therefore torn down and rebuilt rather than refreshed in
    place: a live page cannot be made to re-read init.js. That costs the thread
    toggle and the scroll position on a re-click, which is the price of showing
    the right history.
    """
    global _last_state
    _last_state = state

    palettes = ui.palettes
    existing = palettes.itemById(PALETTE_ID)
    if existing is not None:
        try:
            existing.deleteMe()
        except Exception:
            pass

    _reset_thumb_pump()
    _write_init_js(state)
    palette = palettes.add(
        id=PALETTE_ID,
        name=PALETTE_NAME,
        htmlFileURL=PALETTE_URL,
        isVisible=True,
        showCloseButton=True,
        isResizable=True,
        width=PALETTE_WIDTH,
        height=PALETTE_HEIGHT,
        useNewWebBrowser=True,
    )
    ptutil.add_handler(palette.closed, _palette_closed)
    ptutil.add_handler(palette.incomingFromHTML, _palette_incoming)
    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING
    palette.isVisible = True


def _palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    """Delete the palette on close and drop everything it was holding.

    Fusion can leave a torn-down palette object in ui.palettes after a close;
    toggling isVisible on that husk silently no-ops, so the next open would show
    nothing. Deleting it here keeps itemById honest.
    """
    global _last_state
    _reset_thumb_pump()
    _version_files.clear()
    _last_state = {}
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception:
            pass


def _schedule_load() -> None:
    """Hand the history read to a later main-loop turn.

    Not merely cosmetic. ``rootDataComponent.mfgdmModelId`` is documented as
    safe only away from a synchronous command callback (234b043), and the read
    is a cloud round trip that would otherwise freeze Fusion before the palette
    is even on screen.
    """
    timer = threading.Timer(_LOAD_DELAY_SECONDS, _fire_load_event)
    timer.daemon = True
    timer.start()


def _fire_load_event() -> None:
    """Runs on the timer thread, so it may touch nothing but fireCustomEvent."""
    try:
        app.fireCustomEvent(_LOAD_EVENT_ID)
    except Exception:
        pass


class _LoadHistoryHandler(adsk.core.CustomEventHandler):
    """Read the history, then open the palette on it. Main thread.

    This is a later main-loop turn than commandCreated, which is what makes it
    safe to touch ``rootDataComponent.mfgdmModelId`` (234b043) and what keeps a
    multi-second cloud read off the click.
    """

    def notify(self, args):
        try:
            _open_palette(_gather_history())
        except Exception:
            ptutil.handle_error(CMD_NAME, show_message_box=True)


def _write_init_js(state: dict) -> None:
    """Write the state the page reads synchronously on its first paint.

    Generated, never committed (git-ignored by glob). It carries only the theme
    and the document name so the first frame is themed and titled correctly; the
    history itself arrives by sendInfoToHTML once the page says it is ready.
    """
    try:
        with open(INIT_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"window.__ptInit = {json.dumps(state)};\n")
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: could not write init.js - {exc}")


def _theme_str() -> str:
    """Fusion's UI theme as "dark" or "light", resolving "match device"."""
    themes = adsk.core.UserInterfaceThemes
    theme = app.preferences.generalPreferences.userInterfaceTheme
    if theme == themes.DeviceUserInterfaceTheme:
        return "dark" if _os_is_dark() else "light"
    if theme in (
        themes.DarkBlueUserInterfaceTheme,
        themes.DarkGrayUserInterfaceTheme,
    ):
        return "dark"
    return "light"


def _os_is_dark() -> bool:
    """Best-effort OS dark-mode detection (for the "match device" theme)."""
    import sys

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
        except Exception:
            return True
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return out.stdout.strip() == "Dark"
        except Exception:
            return True
    return True


def _doc_name() -> str:
    try:
        return getattr(app.activeDocument, "name", "") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Reading the history out of Fusion
# ---------------------------------------------------------------------------


# Author properties, in the order _user_fields tries them. Order is the whole
# point of this constant - see that function.
_AUTHOR_ATTRS = ("createdBy", "lastUpdatedBy")


def _read_user(version, attr: str) -> tuple[str, str]:
    """Read one User-valued property as ``(display name, stable id)``.

    Returns ("", "") for a property that is absent, null, or raises - a version
    whose author will not resolve is drawn as an unknown author, not dropped.
    """
    try:
        user = getattr(version, attr, None)
    except Exception:
        return "", ""
    if user is None:
        return "", ""
    try:
        return (user.displayName or user.userName or ""), (user.userId or "")
    except Exception:
        return "", ""


def _probe_indexes(count: int, limit: int = 6) -> frozenset:
    """Pick up to *limit* version indexes spread across a history of *count*.

    Used only by the DEBUG author probe, whose whole question is whether a
    property varies from version to version. The ends matter most - a
    file-level property shows up as the first and last version agreeing - so
    the sample is evenly spaced and always includes both.
    """
    if count <= limit:
        return frozenset(range(max(0, count)))
    step = (count - 1) / (limit - 1)
    return frozenset(round(i * step) for i in range(limit))


def _user_fields(version) -> tuple[str, str]:
    """Return ``(display name, stable id)`` for whoever saved *version*.

    ``createdBy`` first, deliberately. Each version is its own DataFile, created
    at the moment of that save, so its creator is the person who saved it.
    ``lastUpdatedBy`` answers a different question - who last touched this - and
    reading it first made every version of a 27-version design report the same
    person, collapsing a multi-author history into one track. It stays only as
    the fallback for a version whose ``createdBy`` does not resolve.

    Under DEBUG the gather logs the distinct names each property yields, so the
    next history that looks wrong says which property lied.
    """
    for attr in _AUTHOR_ATTRS:
        name, user_id = _read_user(version, attr)
        if name or user_id:
            return name, user_id
    return "", ""


def _milestone_labels(data_file) -> dict:
    """Map version number to milestone name for every milestone on the file.

    One collection read covers the whole history, which is why this is not done
    with a per-version ``DataFile.milestone`` lookup. Milestones are few, so
    resolving each one's version is cheap.
    """
    labels: dict = {}
    try:
        milestones = data_file.milestones
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: milestones unavailable - {exc}")
        return labels
    try:
        count = milestones.count
    except Exception:
        return labels
    for i in range(count):
        try:
            milestone = milestones.item(i)
            version = milestone.version
            if version is None:
                continue
            labels[int(version.versionNumber)] = milestone.name or ""
        except Exception:
            continue
    return labels


def _shared_version(data_file) -> int:
    """Return the version number carrying a public link, or 0 for none.

    Fusion exposes the public link on the file rather than per version, so this
    marks the current version - the one the link resolves to. Reading the link
    is a cloud call, so it happens once per open, not once per version.
    """
    try:
        link = data_file.sharedLink
        if link is not None and link.isShared:
            return int(data_file.latestVersionNumber)
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: shared link unavailable - {exc}")
    return 0


def _version_record(version, labels: dict, shared_version: int) -> dict | None:
    """Flatten one version DataFile into the record the model buckets.

    Returns None when the version cannot be read at all - one unreadable
    version must cost its own dot, not the whole history.
    """
    try:
        number = int(version.versionNumber)
    except Exception:
        return None

    # dateCreated is when this version was written; dateModified only moves for
    # the few edits (a rename) that do not create a version, so it is the
    # fallback rather than the source.
    stamp = 0
    for attr in ("dateCreated", "dateModified"):
        try:
            stamp = int(getattr(version, attr, 0) or 0)
        except Exception:
            stamp = 0
        if stamp:
            break

    name, user_id = _user_fields(version)
    milestone_name = labels.get(number, "")
    try:
        is_milestone = bool(version.isMilestone)
    except Exception:
        is_milestone = False

    try:
        version_id = version.versionId or ""
    except Exception:
        version_id = ""

    try:
        comment = version.description or ""
    except Exception:
        comment = ""

    return {
        "number": number,
        "createdOnMs": stamp * 1000 if stamp else None,
        "createdBy": name,
        "createdById": user_id,
        "comment": comment,
        # A milestone the collection knows about counts even if the per-version
        # flag did not resolve, and vice versa.
        "isMilestone": is_milestone or number in labels,
        # The auto-generated milestone names are noise ("Milestone V7"), so only
        # a name the user typed travels, and it travels as the release label.
        "revision": milestone_name if model.is_release_name(milestone_name) else "",
        "publicShare": bool(shared_version) and number == shared_version,
        "versionId": version_id,
    }


def _model_id(doc) -> str:
    """The design's timeless MFGDM model id, or "" if there is not one.

    Safe here and only here: this runs from the deferred load event, never from
    ``commandCreated``, where reading it destabilised Fusion (234b043).
    """
    try:
        design = adsk.fusion.Design.cast(
            doc.products.itemByProductType("DesignProductType")
        )
        if design is None:
            return ""
        return design.rootDataComponent.mfgdmModelId or ""
    except Exception:
        return ""


def _decorate_cloud_records(records: list, data_file) -> None:
    """Add what MFGDM's version list does not carry, in place.

    Milestones, releases and the public share are each one collection or
    property read for the whole file, so they stay on the desktop API rather
    than costing another GraphQL round trip.

    The thumbnail key is rewritten here too. MFGDM gives no ``versionId``, so
    the merge leaves a bare version number behind; scoping it to the file id
    keeps two documents' version 3 from sharing a cached thumbnail.
    """
    labels = _milestone_labels(data_file)
    shared_version = _shared_version(data_file)
    file_id = getattr(data_file, "id", "") or ""
    for record in records:
        number = record["number"]
        name = labels.get(number, "")
        record["isMilestone"] = number in labels
        record["revision"] = name if model.is_release_name(name) else ""
        record["publicShare"] = bool(shared_version) and number == shared_version
        record["versionId"] = f"{file_id}:v{number}"


def _gather_history() -> dict:
    """Read the active document's versions and bucket them into day rows.

    Returns:
        The page's whole state: ``status`` is "ok", "unsaved" or "error", and
        the remaining keys are only meaningful when it is "ok".
    """
    state = {
        "theme": _theme_str(),
        "docName": _doc_name(),
        "status": "error",
        "message": "",
        "versionCount": 0,
        # Non-save history entries, and the day rows that include them. The
        # DataFile fallback cannot see them at all, so it leaves both at their
        # defaults and the page hides the toggle.
        "changeCount": 0,
        "rows": [],
        "rowsWithChanges": [],
    }

    try:
        doc = app.activeDocument
    except Exception:
        doc = None
    if doc is None:
        state["message"] = "Open a document to see its version history."
        return state
    if not doc.isSaved:
        state["status"] = "unsaved"
        state["message"] = (
            "This document has not been saved yet, so it has no version history."
        )
        return state

    try:
        data_file = doc.dataFile
    except Exception as exc:
        state["message"] = f"Fusion could not read this document's cloud data: {exc}"
        return state
    if data_file is None:
        state["message"] = "This document is not stored in Fusion's cloud data."
        return state

    progress = ui.progressBar
    progress.showBusy(f"{PALETTE_NAME} - reading version history...")
    started = time.monotonic()

    # The cloud read first: it is the only source that attributes versions to
    # the people who made them, and it is fifteen times faster than the walk
    # below. Any failure falls through rather than surfacing - a design outside
    # a hub, an offline session or an MFGDM outage should still get a history,
    # just one that cannot say who saved what.
    try:
        records, changes = mfgdm_history.fetch_records(_model_id(doc))
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: MFGDM history unavailable ({exc}); using DataFile.")
        records = None

    if records is not None:
        try:
            _decorate_cloud_records(records, data_file)
            state["status"] = "ok"
            state["versionCount"] = len(records)
            state["changeCount"] = len(changes)
            state["rows"] = model.bucket_by_day(records)
            # Two stacks, because bucketing is done here and the toggle is on
            # the page: which day a change lands on, and whose track it joins,
            # is the same tested arithmetic as a save's. Shipping both costs a
            # little JSON and keeps the page free of it.
            state["rowsWithChanges"] = (
                model.bucket_by_day(records + changes) if changes else state["rows"]
            )
            ptutil.log(
                f"{CMD_NAME}: read {len(records)} versions and {len(changes)} "
                f"other changes from MFGDM in {time.monotonic() - started:.2f}s "
                f"({len(state['rows'])} day rows)."
            )
            return state
        except Exception:
            ptutil.handle_error(CMD_NAME)
        finally:
            progress.hide()

    # Fallback: walk the version DataFiles. Correct for dates and comments, but
    # it reports one file-level name for every version (see _user_fields) and
    # costs a cloud round trip per property - 21s for 27 versions.
    progress.showBusy(f"{PALETTE_NAME} - reading version history...")
    adsk.doEvents()
    try:
        labels = _milestone_labels(data_file)
        shared_version = _shared_version(data_file)
        versions = data_file.versions
        count = versions.count

        _version_files.clear()
        records = []
        # Which names each author property yields, sampled only under DEBUG.
        # One line in the log then settles "is this design really one person's,
        # or is the property lying to us" without another code change.
        #
        # Sampled, not exhaustive: every property read here is a cloud round
        # trip - 27 versions cost 21s, and probing both properties on all of
        # them cost 41s. A handful spread across the history answers "does this
        # vary at all" for a fixed price.
        author_sources = {attr: set() for attr in _AUTHOR_ATTRS} if config.DEBUG else {}
        probe_at = _probe_indexes(count) if author_sources else ()
        for i in range(count):
            try:
                version = versions.item(i)
            except Exception:
                continue
            if version is None:
                continue
            record = _version_record(version, labels, shared_version)
            if record is None:
                continue
            records.append(record)
            if record["versionId"]:
                _version_files[record["versionId"]] = version
            if i in probe_at:
                for attr, names in author_sources.items():
                    names.add(_read_user(version, attr)[0])
    except Exception as exc:
        state["message"] = f"Fusion could not read the version history: {exc}"
        ptutil.handle_error(CMD_NAME)
        return state
    finally:
        progress.hide()

    state["status"] = "ok"
    state["versionCount"] = len(records)
    state["rows"] = model.bucket_by_day(records)
    state["rowsWithChanges"] = state["rows"]
    ptutil.log(
        f"{CMD_NAME}: read {len(records)} versions from DataFile in "
        f"{time.monotonic() - started:.2f}s ({len(state['rows'])} day rows)."
    )
    if author_sources:
        ptutil.log(
            f"{CMD_NAME}: distinct authors per property - "
            + "; ".join(
                f"{attr}={sorted(n for n in names if n)}"
                for attr, names in author_sources.items()
            )
        )
    return state


def _push_state(palette) -> None:
    """Push the state gathered for this open to the page.

    Deliberately does not re-read: the caller has just filled ``_last_state``,
    and a second walk of the versions is a second round of cloud calls.
    """
    if palette is None or not _last_state:
        return
    try:
        palette.sendInfoToHTML("setHistory", json.dumps(_last_state))
    except Exception:
        ptutil.handle_error(CMD_NAME)


# ---------------------------------------------------------------------------
# Incoming messages from the palette
# ---------------------------------------------------------------------------


def _palette_incoming(html_args: adsk.core.HTMLEventArgs):
    """Serve the page.

    A raise in here is swallowed by DEBUG-gated handle_error and reads to the
    user as "nothing happened", so every branch guards its own Fusion calls and
    answers the page either way (7535954).
    """
    action = html_args.action
    # Logged unconditionally: when this palette first shipped it waited on a
    # page message that never arrived, and the log could not say whether the
    # page had gone quiet or Python had. Now it can.
    ptutil.log(f"{CMD_NAME}: page sent '{action}'.")

    try:
        data = json.loads(html_args.data) if html_args.data else {}
    except Exception:
        data = {}

    palette = ui.palettes.itemById(PALETTE_ID)

    try:
        if action == "htmlReady":
            # Repaint from the state this open already gathered. init.js has
            # normally done the job by now, but Fusion's embedded browser
            # caches it by URL across palette recreations on Windows and can
            # serve a stale copy - the same trap the Assembly Palette hit. This
            # costs nothing, because it re-sends rather than re-reads.
            _push_state(palette)
        elif action == "requestThumbs":
            _action_request_thumbs(palette, data)
    except Exception:
        ptutil.handle_error(CMD_NAME)

    html_args.returnData = "OK"


# ---------------------------------------------------------------------------
# Lazy thumbnail retrieval
# ---------------------------------------------------------------------------


def _reset_thumb_pump() -> None:
    """Drop all pump state.

    ``_thumb_missing`` goes too: a version whose cloud thumbnail had not been
    generated when the palette was last open may well have one now, and a
    negative cache that outlived the session would hide it forever.
    """
    _thumb_queue.clear()
    _thumb_inflight.clear()
    _thumb_missing.clear()


def _action_request_thumbs(palette, data: dict) -> None:
    """Serve the page's hover-card thumbnail request.

    The page asks only for the version the pointer actually rested on, so this
    is a trickle rather than a gallery load. Anything already on disk goes back
    in the same turn; the rest is queued for the pump. Ids already queued, in
    flight, or known to have no thumbnail are dropped, so the page can re-ask
    freely as the pointer moves.
    """
    ids = [str(i) for i in (data.get("ids") or []) if i]
    wanted = [i for i in ids if i not in _thumb_missing and i not in _thumb_inflight]
    if not wanted:
        return

    ready: dict = {}
    for version_id in wanted:
        url = recents.cached_thumbnail_data_url(version_id)
        if url:
            ready[version_id] = url
        elif version_id not in _thumb_queue:
            _thumb_queue.append(version_id)
    if ready:
        _send_thumbs(palette, ready)
    _schedule_thumb_tick()


def _send_thumbs(palette, mapping: dict) -> None:
    """Push a batch of ``versionId -> data: URL`` to the page."""
    if not palette or not mapping:
        return
    try:
        palette.sendInfoToHTML("setThumbs", json.dumps(mapping))
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: sendInfoToHTML(setThumbs) failed - {exc}")


def _future_state(future) -> int:
    """*future*'s state as a plain int, or the failed state if unreadable."""
    try:
        return int(future.state)
    except Exception:
        return _FUTURE_FINISHED + 1  # anything not Processing/Finished = failed


def _resolve_version_file(key: str):
    """Find the version DataFile behind a ``<fileId>:v<number>`` thumbnail key.

    The MFGDM path never walks the version DataFiles - that walk is the 21
    seconds it exists to avoid - so the one the pointer is resting on is looked
    up here instead, and only then.

    ``DataFile.versions`` runs newest first, so the index is normally
    ``latest - number``. That is checked rather than trusted, with a scan
    behind it: a guess that silently landed on the neighbouring version would
    put the wrong picture on the card.
    """
    if ":v" not in key:
        return None
    try:
        number = int(key.rsplit(":v", 1)[1])
        data_file = app.activeDocument.dataFile
        versions = data_file.versions
        count = versions.count
        guess = int(data_file.latestVersionNumber) - number
        for index in (guess, *range(count)):
            if not 0 <= index < count:
                continue
            version = versions.item(index)
            if version is not None and int(version.versionNumber) == number:
                _version_files[key] = version
                return version
    except Exception:
        return None
    return None


def _start_thumb_download(version_id: str):
    """Start *version_id*'s thumbnail download, returning its future or None.

    On the DataFile path the version was captured while the history was read.
    On the MFGDM path nothing was captured, so it is resolved now - once, and
    cached for the rest of the session. Reading ``.thumbnail`` only starts the
    download either way.
    """
    version = _version_files.get(version_id) or _resolve_version_file(version_id)
    if version is None:
        return None
    try:
        return getattr(version, "thumbnail", None)
    except Exception:
        return None


def _collect_finished_thumbs() -> dict:
    """Harvest every in-flight future that has settled since the last tick.

    Returns:
        ``versionId -> data: URL``, with "" for a version that has no
        thumbnail. The empty answer is sent too: without it the hover card
        cannot tell "still downloading" from "there is no preview", and would
        sit on a blank forever.
    """
    ready: dict = {}
    now = time.monotonic()
    for version_id, (future, started) in list(_thumb_inflight.items()):
        state = _future_state(future)
        if state == _FUTURE_PROCESSING:
            if now - started > _THUMB_FUTURE_TIMEOUT_SECONDS:
                del _thumb_inflight[version_id]
                _thumb_missing.add(version_id)
                ready[version_id] = ""
            continue
        del _thumb_inflight[version_id]
        url = ""
        if state == _FUTURE_FINISHED:
            # FailedFutureState is the documented answer for "this DataFile has
            # no thumbnail", so a miss here is expected, not an error.
            data_object = getattr(future, "dataObject", None)
            path = recents.store_thumbnail_object(data_object, version_id)
            url = recents.png_to_data_url(path) if path else ""
        if not url:
            _thumb_missing.add(version_id)
        ready[version_id] = url
    return ready


def _start_queued_thumbs() -> dict:
    """Begin queued downloads up to the in-flight ceiling.

    Returns:
        ``versionId -> ""`` for versions that could not even be started - the
        version's DataFile went away - so the page hears about those too.
    """
    failed: dict = {}
    while _thumb_queue and len(_thumb_inflight) < _THUMB_MAX_INFLIGHT:
        version_id = _thumb_queue.pop(0)
        if version_id in _thumb_inflight or version_id in _thumb_missing:
            continue
        future = _start_thumb_download(version_id)
        if future is None:
            _thumb_missing.add(version_id)
            failed[version_id] = ""
        else:
            _thumb_inflight[version_id] = (future, time.monotonic())
    return failed


def _pump_thumbs() -> None:
    """One turn of the thumbnail pump. Runs on the main thread.

    Harvest what finished, start a little more, push whatever landed, and
    re-arm only while there is still work. Nothing here blocks: an unfinished
    future is simply looked at again next tick.
    """
    global _thumb_tick_pending
    _thumb_tick_pending = False

    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is None or not palette.isVisible:
        _reset_thumb_pump()
        return

    ready = _collect_finished_thumbs()
    ready.update(_start_queued_thumbs())
    if ready:
        _send_thumbs(palette, ready)
    _schedule_thumb_tick()


def _schedule_thumb_tick() -> None:
    """Arm the next pump turn, unless one is already coming or there is no work."""
    global _thumb_tick_pending, _thumb_tick_scheduled_at
    if not _thumb_queue and not _thumb_inflight:
        return
    now = time.monotonic()
    if (
        _thumb_tick_pending
        and now - _thumb_tick_scheduled_at < _THUMB_TICK_STALE_SECONDS
    ):
        return
    _thumb_tick_pending = True
    _thumb_tick_scheduled_at = now
    timer = threading.Timer(_THUMB_TICK_SECONDS, _fire_thumb_event)
    timer.daemon = True  # never hold Fusion open on a pending download
    timer.start()


def _fire_thumb_event() -> None:
    """Hand the next pump turn to the main thread. Runs on the timer thread.

    Nothing here may touch the Fusion API beyond fireCustomEvent - not even
    ptutil.log, which calls Application.log and is not thread-safe (266e2c2).
    """
    try:
        app.fireCustomEvent(_THUMB_EVENT_ID)
    except Exception:
        pass


class _ThumbTickHandler(adsk.core.CustomEventHandler):
    """Runs _pump_thumbs on the main thread, one timer tick at a time."""

    def notify(self, args):
        try:
            _pump_thumbs()
        except Exception:
            # A pump failure must never surface as a dialog over the palette;
            # the worst case is a hover card keeping its placeholder.
            ptutil.handle_error(CMD_NAME)
