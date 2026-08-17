# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# PowerTools Assembly - New Assembly Intent dialog.
#
# When the user creates a new, empty Fusion Design with Assembly intent, this
# add-in pops up a docked palette offering three quick-start sections:
#
#   1. Create  — make a new external Part/Hybrid component in place, or jump
#                to the Assembly Builder or Global Parameters commands.
#   2. Insert Open    — gallery of currently-open Part/Hybrid/Assembly docs
#                       (saved only, since addByInsert needs a DataFile).
#                       Click a card to insert that doc into the active design.
#   3. Insert Recent  — gallery of recently-touched docs that are NOT currently
#                       open. Backed by a small JSON cache that grows as the
#                       user works.

import json
import os
import threading

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from ...lib.ptAddInUtils import cache_utils as cache
from ...lib.ptAddInUtils import intent_icons
from ...lib.ptAddInUtils import recents_utils as recents

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "New Assembly"
PALETTE_NAME = "New Assembly"
PALETTE_ID = config.assembly_intent_palette_id
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "index.html").replace("\\", "/")
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

# Design-intent icons, emitted as CSS variables carrying data URIs. Generated
# from the shared SVGs in lib/ptAddInUtils/assets rather than committed, so the
# palette and any future consumer stay pinned to one set of glyphs.
INTENT_ICONS_CSS_PATH = os.path.join(_HTML_DIR, "intent-icons.css")

# The recents cache and the per-document thumbnail store are shared with the
# Open Recent command; recents_utils owns their format, paths, and helpers so
# the two commands can never drift. These aliases retain the local names used
# below while the data layer lives in one place.
_RECENT_CACHE_PATH = recents.RECENT_CACHE_PATH
_THUMB_DIR = recents.THUMB_DIR
_THUMB_SIZE = recents.THUMB_SIZE
_RECENT_LIMIT = recents.RECENT_LIMIT

# Commands we hand off to from the palette.
_ASSEMBLY_BUILDER_CMD_ID = "PTAT_AssemblyBuilder"
_GLOBAL_PARAMETERS_CMD_ID = "PTAT_globalParameters"
# Fusion's own Fasteners command — the ASSEMBLY > INSERT panel button, defined by
# Fusion as FusionFastenersCommand in its ribbon and command-definition
# resources. There is no public insert API (FastenerOccurrenceDefinition only
# exposes updateSize on existing occurrences), so executing the command
# definition is the only route.
_FASTENERS_CMD_ID = "FusionFastenersCommand"

# Inserting a component from the ASSEMBLY > INSERT panel runs a sequence —
# FusionImportCommand, CommitCommand, SelectCommand, FitCommand,
# FusionMoveCommand — so the new occurrence arrives selected, framed, and ready
# to position. ``addByInsert`` only covers the import and commit;
# _finish_insert_like_fusion adds the rest, with Edit Initial Position standing in
# for Fusion's final Move/Copy step: it edits the placement the insert itself
# recorded instead of stacking a separate Move feature on top of it.
#
# Fusion ships two definitions with the same "Edit Initial Position" label and
# identical HUD and marking-menu entries (Libraries/.../CommandDefinitions.xml):
# the Dc ("double click") variant and the plain one. The Dc id is the one that
# comes up on a palette insert; the plain one is kept as a fallback in case a build
# ever differs, since both resolve to the same command for the user.
_EDIT_POSITION_CMD_IDS = (
    "FusionDcEditInitialPositionCommand",
    "FusionEditInitialPositionCommand",
)

# Custom event used to defer the post-insert chain out of the palette's
# incomingFromHTML handler — see _FinishInsertHandler for why that matters. The
# delay is what actually buys the deferral: fired inline, Fusion dispatched the
# handler within the same event turn and the command it started was torn down
# again when the HTML event finished (see _schedule_finish_insert).
_FINISH_EVENT_ID = "PTAT_newAssembly_finishInsert"
_FINISH_DELAY_SECONDS = 0.35

# How long to keep pumping events before believing ui.activeCommand. A command
# started by execute() does not become active in the same turn — reading it after a
# single doEvents() said "SelectCommand" for a command that visibly did start.
_COMMAND_START_WAIT_SECONDS = 0.4

# Fusion reports its idle state as the Select command rather than "nothing
# running", so these ids mean "no real command is active".
_IDLE_CMD_IDS = ("", "SelectCommand")

# Toolbar button that manually launches the palette. Lives in the Assembly
# Insert panel, directly below the Insert STEP command. The palette also pops
# automatically on new empty Assembly docs (see the documentActivated trigger);
# this button is the on-demand entry point.
LAUNCH_CMD_ID = "PTAT_newAssembly"
LAUNCH_CMD_NAME = "New Assembly"
LAUNCH_CMD_DESC = "Open the New Assembly quick-start palette."
LAUNCH_WORKSPACE_ID = "FusionSolidEnvironment"
LAUNCH_TAB_ID = "AssemblyTab"
LAUNCH_TAB_NAME = "ASSEMBLY"
LAUNCH_PANEL_ID = "InsertAssemblePanel"
LAUNCH_PANEL_NAME = "INSERT"
# Position the control immediately after (below) the Insert STEP command.
LAUNCH_POSITION_REF = "PTAT_insertSTEP"

local_handlers = []


def _diag(msg: str) -> None:
    """Diagnostic log for the document-trigger logic, gated by config.DEBUG so
    release builds stay quiet. When DEBUG is on it writes to the Fusion Text
    Commands window with a clear prefix so it's easy to grep."""
    if not config.DEBUG:
        return
    try:
        app.log(
            f"[New Assembly] {msg}",
            adsk.core.LogLevels.InfoLogLevel,
            adsk.core.LogTypes.ConsoleLogType,
        )
    except Exception:
        pass


# Data-file ids inserted from the palette during this palette-open session.
# Cleared on every _show_palette() so a fresh palette open starts clean.
# Without this filter, an inserted-from-Recent doc shows back up in the next
# refresh (it's not "open" in a tab, so Recent re-includes it) and clicking
# again would silently insert a second occurrence into the assembly.
_inserted_in_session: set[str] = set()

# Upper bound on Recent entries handed to the page. The page renders only the
# newest slice of these and filters across the whole set, so the cap has to be
# generous — capping here instead would leave the filter unable to find anything
# it was not sent.
RECENT_PAYLOAD_LIMIT = 300

# Open-tab filter, toggled from the palette checkbox. Default False → show only
# top-level (directly-opened) docs. True → also include reference-loaded
# children of open assemblies. Both paths are cheap: the top-level test is an
# instant in-memory API check (see _is_top_level_doc), no cloud lookup.
# Persists across palette opens this session.
_show_children = False

# Custom event handler for the post-insert chain, kept alive for the life of the
# add-in, plus the occurrence handed to it by the last insert (cleared as soon as
# the handler picks it up).
_finish_event_handler = None
_pending_finish = None

# The Document we last popped the palette for (or had open when palette closed).
# Compared via Python identity (`is`) — NOT id(), which can collide across
# short-lived Fusion Document wrappers and previously caused the popup to be
# suppressed after closing + creating a new doc. None means "next eligible
# document activation will pop the palette".
_palette_was_open_for = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    global _finish_event_handler

    # documentActivated is the reliable trigger across Fusion builds —
    # documentOpened isn't always emitted for File > New on macOS.
    # documentActivated fires on every tab switch too, so we gate manually
    # via _palette_was_open_for (set on show and on close).
    ptutil.add_handler(app.documentActivated, _on_document_activated)

    # Attach documentOpened as a belt-and-suspenders backup IF this build
    # exposes it. Harmless if it never fires; the gate handles dedup.
    opened_event = getattr(app, "documentOpened", None)
    if opened_event is not None:
        try:
            ptutil.add_handler(opened_event, _on_document_opened)
            _diag("documentOpened handler attached (backup trigger).")
        except Exception as e:
            _diag(f"documentOpened attach failed: {e}")

    # Manual launch button in the Assembly Insert panel, below Insert STEP.
    cmd_def = ui.commandDefinitions.itemById(LAUNCH_CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            LAUNCH_CMD_ID, LAUNCH_CMD_NAME, LAUNCH_CMD_DESC, ICON_FOLDER
        )
    ptutil.add_handler(cmd_def.commandCreated, _launch_command_created)

    workspace = ui.workspaces.itemById(LAUNCH_WORKSPACE_ID)
    if workspace is not None:
        toolbar_tab = workspace.toolbarTabs.itemById(LAUNCH_TAB_ID)
        if toolbar_tab is None:
            toolbar_tab = workspace.toolbarTabs.add(LAUNCH_TAB_ID, LAUNCH_TAB_NAME)
        panel = toolbar_tab.toolbarPanels.itemById(LAUNCH_PANEL_ID)
        if panel is None:
            panel = toolbar_tab.toolbarPanels.add(LAUNCH_PANEL_ID, LAUNCH_PANEL_NAME)
        control = panel.controls.addCommand(cmd_def, LAUNCH_POSITION_REF, False)
        control.isPromoted = False

    # Runner for the post-insert chain. unregister-then-register gives a clean
    # slate if the add-in was reloaded without restarting Fusion.
    try:
        app.unregisterCustomEvent(_FINISH_EVENT_ID)
    except Exception:
        pass
    finish_event = app.registerCustomEvent(_FINISH_EVENT_ID)
    _finish_event_handler = _FinishInsertHandler()
    finish_event.add(_finish_event_handler)

    _diag(f"start(): primary trigger=documentActivated. thumb dir = {_THUMB_DIR}")


def _launch_command_created(args: adsk.core.CommandCreatedEventArgs):
    """Toolbar button clicked — open the palette regardless of the active doc.
    _show_palette() rebuilds a fresh palette each time, so this is safe to
    invoke even when the palette was previously auto-popped and closed."""
    try:
        _show_palette()
    except Exception:
        ptutil.handle_error(CMD_NAME)


def stop():
    global _palette_was_open_for, _finish_event_handler, _pending_finish
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        try:
            palette.deleteMe()
        except Exception:
            pass

    # Remove the launch button. Leave the shared Insert panel/tab in place —
    # insertSTEP owns the conditional panel/tab cleanup.
    workspace = ui.workspaces.itemById(LAUNCH_WORKSPACE_ID)
    if workspace is not None:
        toolbar_tab = workspace.toolbarTabs.itemById(LAUNCH_TAB_ID)
        if toolbar_tab is not None:
            panel = toolbar_tab.toolbarPanels.itemById(LAUNCH_PANEL_ID)
            if panel is not None:
                control = panel.controls.itemById(LAUNCH_CMD_ID)
                if control:
                    control.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(LAUNCH_CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    try:
        app.unregisterCustomEvent(_FINISH_EVENT_ID)
    except Exception:
        pass
    _finish_event_handler = None
    _pending_finish = None

    _inserted_in_session.clear()
    _palette_was_open_for = None


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


def _design_is_empty(design: adsk.fusion.Design) -> bool:
    root = design.rootComponent
    if root.occurrences.count > 0:
        return False
    if root.bRepBodies.count > 0:
        return False
    if root.sketches.count > 0:
        return False
    try:
        if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            if design.timeline.count > 0:
                return False
    except Exception:
        pass
    return True


def _design_intent(doc: adsk.core.Document) -> int | None:
    return recents.design_intent(doc)


def _intent_name(intent: int | None) -> str:
    return recents.intent_name(intent)


def _maybe_show_palette_for(doc, source: str) -> None:
    """Shared trigger logic for both document events.

    Eligibility: doc is unsaved + empty Design + Assembly intent.
    Dedup: skip when *doc* is the same Python object we last popped/closed
    against. The dedup uses `is` (object identity), not id(), since id() of
    Fusion's Document wrappers can collide once a wrapper is GC'd.
    """
    global _palette_was_open_for

    if doc is None:
        _diag(f"{source}: doc is None — skip.")
        return

    if doc.isSaved:
        _remember_recent_if_eligible(doc)
        return

    try:
        product = doc.products.itemByProductType("DesignProductType")
    except Exception as e:
        _diag(f"{source}: products access raised: {e}")
        return
    design = adsk.fusion.Design.cast(product)
    if design is None:
        _diag(f"{source}: '{doc.name}' has no Design product — skip.")
        return

    if design.designIntent != adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType:
        _diag(f"{source}: '{doc.name}' intent != Assembly — skip.")
        return
    if not _design_is_empty(design):
        _diag(f"{source}: '{doc.name}' not empty — skip.")
        return

    if _palette_was_open_for is doc:
        _diag(f"{source}: already showed palette for '{doc.name}' — skip.")
        return

    _diag(f"{source}: opening palette for new empty Assembly '{doc.name}'.")
    _palette_was_open_for = doc
    _show_palette()


def _on_document_activated(args: adsk.core.DocumentEventArgs):
    """Primary trigger. Fires on every tab switch, but the dedup gate in
    _maybe_show_palette_for keeps the popup from re-firing for the same doc."""
    try:
        _maybe_show_palette_for(args.document, "documentActivated")
    except Exception:
        ptutil.handle_error(CMD_NAME)


def _on_document_opened(args: adsk.core.DocumentEventArgs):
    """Backup trigger. Some Fusion builds emit this for File > New; others
    don't. The same dedup gate handles overlap with documentActivated."""
    try:
        _maybe_show_palette_for(args.document, "documentOpened")
    except Exception:
        ptutil.handle_error(CMD_NAME)


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def _show_palette():
    # Fresh palette open → forget which docs were inserted during a prior open
    # so the user can deliberately insert them again in this new session.
    _inserted_in_session.clear()

    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)

    # Fusion's palette.closed sometimes leaves a palette object in
    # `ui.palettes` that has been internally torn down — toggling isVisible
    # on it silently no-ops. The reliable cure is to delete any pre-existing
    # palette and create a fresh one. That also means we re-register
    # navigation / incoming / closed handlers cleanly each time, avoiding
    # accumulating stale handlers across sessions.
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception as e:
            _diag(f"could not deleteMe() existing palette: {e}")
        palette = None

    _write_init_js(_gather_palette_state())
    _write_intent_icons_css()
    palette = palettes.add(
        id=PALETTE_ID,
        name=PALETTE_NAME,
        htmlFileURL=PALETTE_URL,
        isVisible=True,
        showCloseButton=True,
        isResizable=True,
        width=420,
        height=720,
        useNewWebBrowser=True,
    )
    ptutil.add_handler(palette.closed, _palette_closed)
    ptutil.add_handler(palette.navigatingURL, _palette_navigating)
    ptutil.add_handler(palette.incomingFromHTML, _palette_incoming)

    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING

    palette.isVisible = True


def _gather_palette_state() -> dict:
    doc = app.activeDocument
    folder = cache.resolve_target_folder(CMD_NAME)
    return {
        "docName": getattr(doc, "name", ""),
        "theme": _theme_str(),
        "showChildren": _show_children,
        "openDocs": _list_open_docs(),
        "recentDocs": _list_recent_docs(),
        # Drives the "no target project" banner + New Component enablement.
        "hasTargetProject": folder is not None,
        "targetProject": cache.target_project_label(folder),
    }


def _theme_str() -> str:
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


def _write_init_js(state: dict) -> None:
    try:
        payload = json.dumps(state)
        with open(INIT_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"window.__ptInit = {payload};\n")
    except Exception as e:
        ptutil.log(f"{CMD_NAME}: could not write init.js — {e}")


def _write_intent_icons_css() -> None:
    """Refresh the generated intent-icon stylesheet the page links.

    Unlike init.js this content never varies, so rewriting it on every open is
    only about keeping it in step with the SVGs in lib/ptAddInUtils/assets.
    """
    if not intent_icons.write_stylesheet(INTENT_ICONS_CSS_PATH):
        ptutil.log(f"{CMD_NAME}: could not write intent-icons.css")


def _send_palette_init(palette: adsk.core.Palette):
    state = _gather_palette_state()
    palette.sendInfoToHTML("setDocumentName", state["docName"])
    palette.sendInfoToHTML("setTheme", state["theme"])
    palette.sendInfoToHTML("setOpenDocs", json.dumps(state["openDocs"]))
    palette.sendInfoToHTML("setRecentDocs", json.dumps(state["recentDocs"]))
    palette.sendInfoToHTML(
        "setTargetProject",
        json.dumps(
            {"hasProject": state["hasTargetProject"], "name": state["targetProject"]}
        ),
    )


def _send_target_project(palette: adsk.core.Palette) -> None:
    """Re-resolve the target project and push just that state to the page.

    Fusion exposes no active-project-changed event, so we can't observe the
    user picking a project in the Data Panel. This lightweight recheck (used by
    the banner's Re-check button and the page's focus handler) re-runs only the
    folder resolution — not the full gallery rebuild of _send_palette_init."""
    folder = cache.resolve_target_folder(CMD_NAME)
    palette.sendInfoToHTML(
        "setTargetProject",
        json.dumps(
            {
                "hasProject": folder is not None,
                "name": cache.target_project_label(folder),
            }
        ),
    )


def _palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    """Tear the palette down completely on close so the next show() builds a
    fresh one with fresh handlers. Without deleteMe() here, a stale palette
    object lingered in ui.palettes after close and the next show() silently
    no-op'd on isVisible — leaving the user with no palette.

    We also pin *_palette_was_open_for* to the currently-active document so
    that any spurious documentActivated event Fusion fires immediately after
    close (e.g. when CEF releases focus) doesn't immediately re-pop the
    palette for the same doc. Creating a NEW doc will produce a different
    Document instance which trips the `is` check and pops normally."""
    global _palette_was_open_for
    _diag("palette closed — tearing down.")
    _inserted_in_session.clear()
    try:
        _palette_was_open_for = app.activeDocument
    except Exception:
        _palette_was_open_for = None
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception as e:
            _diag(f"deleteMe() in close handler raised: {e}")


def _palette_navigating(args: adsk.core.NavigationEventArgs):
    url = args.navigationURL
    if url.startswith("http"):
        args.launchExternally = True


# ---------------------------------------------------------------------------
# Open / recent document enumeration
# ---------------------------------------------------------------------------


def _is_top_level_doc(doc) -> bool:
    """True for a document the user opened directly (a tab), False for one
    loaded only as a reference (a sub-assembly/part of an open assembly).

    Fusion exposes this directly and instantly: Document.documentReferences
    raises "Cannot get documentReferences of a non-top-level document" for a
    reference-loaded child, and returns the reference collection for a
    top-level doc. No cloud round-trip, unlike DataFile.childReferences."""
    try:
        # Touch .count so the accessor actually evaluates and raises for
        # non-top-level docs rather than handing back a lazy wrapper. Assigned
        # to _ purely to evaluate it (and raise) without tripping B018.
        _ = doc.documentReferences.count
        return True
    except Exception:
        return False


def _list_open_docs() -> list[dict]:
    """Open Fusion design docs (part/hybrid/assembly) for the Open tab.

    By default only top-level (directly-opened) docs appear; when
    _show_children is set, reference-loaded children of open assemblies are
    included too. Always excludes the active doc, unsaved docs (addByInsert
    needs a DataFile), and docs inserted earlier in this palette session."""
    out: list[dict] = []
    active = app.activeDocument
    active_key = id(active) if active else None

    # Dedup by DataFile id so a doc that's open in more than one document
    # wrapper (or otherwise enumerated twice) only yields a single card —
    # mirrors the `seen` guard in _list_recent_docs.
    seen: set[str] = set()

    documents = app.documents
    for i in range(documents.count):
        try:
            doc = documents.item(i)
        except Exception:
            continue
        if doc is None:
            continue
        if id(doc) == active_key:
            continue
        if not doc.isSaved:
            continue
        if not _show_children and not _is_top_level_doc(doc):
            continue
        intent = _design_intent(doc)
        intent_name = _intent_name(intent)
        if intent_name not in ("part", "hybrid", "assembly"):
            continue
        try:
            df = doc.dataFile
        except Exception:
            df = None
        if df is None:
            continue
        df_id = getattr(df, "id", "")
        if df_id in _inserted_in_session:
            continue
        if df_id in seen:
            continue
        seen.add(df_id)
        out.append(
            {
                "dataFileId": df_id,
                "name": getattr(df, "name", "") or doc.name,
                "intent": intent_name,
                # Cache-only here so building the gallery never blocks on a
                # synchronous Component.createThumbnail render. The cache is
                # pre-warmed by _remember_recent_if_eligible on documentActivated
                # (see its docstring), so activated docs already have a thumb;
                # any not-yet-rendered doc simply shows blank until then.
                "thumbUrl": _cached_thumbnail(df_id),
            }
        )
    return out


# Thumbnail rendering and the per-document thumbnail cache now live in
# lib/ptAddInUtils/recents_utils (shared with the Open Recent command). The
# open-doc render is invoked via recents.remember_recent_if_eligible below.


def _thumbnail_for_open_doc(doc, df_id: str) -> str:
    """Render *doc*'s live root component to a cached PNG and return a data: URL.

    Delegates to the shared thumbnail store; kept as a thin wrapper for the
    Open gallery path's readability."""
    return recents.render_thumbnail_for_doc(doc, df_id)


def _cached_thumbnail(df_id: str) -> str:
    """Cached thumbnail as a data: URL, or "" — delegated to the shared store.

    Recent (closed) documents cannot be rendered live, so both galleries reuse
    the PNG cached while the document was last open."""
    return recents.cached_thumbnail_data_url(df_id)


def _find_data_file_by_id(df_id: str):
    """Best-effort DataFile resolution from an id. Returns None on failure."""
    if not df_id:
        return None
    # get_active_project guards app.data.activeProject, which raises
    # InternalValidationError('id.size()') when no project is in context — the
    # old eager tuple (app.data.activeProject, app.data) let that abort inserts.
    owners = []
    project = cache.get_active_project(CMD_NAME)
    if project is not None:
        owners.append(project)
    owners.append(app.data)
    for owner in owners:
        finder = getattr(owner, "findFileById", None)
        if callable(finder):
            try:
                df = finder(df_id)
                if df is not None:
                    return df
            except Exception:
                pass
    return None


def _read_recent_cache() -> list[dict]:
    return recents.read_recent_cache()


def _write_recent_cache(entries: list[dict]) -> None:
    recents.write_recent_cache(entries)


def _touch_recent(df_id: str, name: str, intent_name: str) -> None:
    """Append (or move to end) a recent entry — delegated to the shared store.

    Thumbnails are cached on disk separately and derived from df_id at list
    time, so the JSON cache stays small."""
    recents.touch_recent(df_id, name, intent_name)


def _remember_recent_if_eligible(doc: adsk.core.Document | None) -> None:
    """Record *doc* in the recent cache when it's a saved part/hybrid/assembly,
    and pre-warm its thumbnail cache while the doc is open — delegated to the
    shared store. Called from documentActivated so both grow as the user works."""
    recents.remember_recent_if_eligible(doc)


def _list_recent_docs() -> list[dict]:
    """The Recent gallery: the shared recents list, as insertable cards.

    Uses ``recents.list_recent`` so this gallery and the Open Recent flyout are
    the same list, drawn from Fusion's own recents file. It previously walked our
    cache directly and excluded every open document, which on a small cache left
    only a handful of cards; the exclusions now match the flyout's — just the
    active document, which cannot be inserted into itself.

    Only the session-insert guard is extra, and it is functional rather than
    cosmetic: re-clicking a card already inserted this session would silently add
    a duplicate occurrence.

    Designs only (``f3d``) — these cards insert a component, so drawings and
    electronics files have no meaning here.

    The whole list goes to the page, which renders the newest slice and filters
    across all of it. Any cached thumbnails ride along as data URIs, which is the
    payload the lazy per-card fetch is meant to replace.
    """
    exclude = set(_inserted_in_session)
    try:
        active_df = getattr(app.activeDocument, "dataFile", None)
        if active_df is not None:
            exclude.add(getattr(active_df, "id", ""))
    except Exception:
        pass

    out: list[dict] = []
    for item in recents.list_recent(
        exclude_ids=exclude, limit=RECENT_PAYLOAD_LIMIT, file_types=("f3d",)
    ):
        # Cached PNGs only: a closed document cannot be rendered with
        # Component.createThumbnail, so cards without one fall back to the
        # design-intent placeholder.
        out.append(
            {
                "dataFileId": item["dataFileId"],
                "name": item["name"],
                "intent": item["intent"],
                "thumbUrl": _cached_thumbnail(item["dataFileId"]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Palette → backend actions
# ---------------------------------------------------------------------------


_INTENT_MAP = {
    "part": adsk.fusion.DesignIntentTypes.PartDesignIntentType,
    "hybrid": adsk.fusion.DesignIntentTypes.HybridDesignIntentType,
    "assembly": adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType,
}


def _palette_incoming(html_args: adsk.core.HTMLEventArgs):
    action = html_args.action
    try:
        data = json.loads(html_args.data) if html_args.data else {}
    except Exception:
        data = {}

    palette = ui.palettes.itemById(PALETTE_ID)

    if action == "htmlReady":
        # The page finished loading and is asking for current state. Push it
        # now via sendInfoToHTML rather than trusting the browser to have
        # re-read init.js — on Windows the embedded browser caches init.js
        # across palette recreations and can serve a stale/empty copy, which
        # left the galleries blank. This guarantees a fresh repaint.
        if palette:
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    if action == "createComponent":
        msg = _action_create_component(data)
        if msg:
            ui.messageBox(msg, CMD_NAME)
        # Refresh open-docs list — the new external doc just opened.
        if palette:
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    if action == "launchAssemblyBuilder":
        _hide_palette(palette)
        _execute_command(_ASSEMBLY_BUILDER_CMD_ID)
        html_args.returnData = "OK"
        return

    if action == "launchGlobalParameters":
        _hide_palette(palette)
        _execute_command(_GLOBAL_PARAMETERS_CMD_ID)
        html_args.returnData = "OK"
        return

    if action == "launchFasteners":
        # Hides the palette itself only when the command can actually start, so
        # the message below is not delivered to a dismissed palette.
        msg = _action_launch_fasteners(palette)
        if msg:
            ui.messageBox(msg, CMD_NAME)
        html_args.returnData = "OK"
        return

    if action == "insertDoc":
        msg = _action_insert_doc(data)
        if msg:
            ui.messageBox(msg, CMD_NAME)
        if palette:
            # This refresh has to complete before the post-insert chain starts its
            # command — repainting the palette in the same turn kills it. The delayed
            # fire in _schedule_finish_insert is what keeps the two apart.
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    if action == "setShowChildren":
        global _show_children
        _show_children = bool(data.get("showChildren", False))
        # Only the Open list depends on this — re-send just that.
        if palette:
            palette.sendInfoToHTML("setOpenDocs", json.dumps(_list_open_docs()))
        html_args.returnData = "OK"
        return

    if action == "recheckProject":
        # Lightweight re-resolve of the target project only — fired by the
        # banner's Re-check button and when the palette page regains focus.
        if palette:
            _send_target_project(palette)
        html_args.returnData = "OK"
        return

    if action == "refresh":
        if palette:
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    html_args.returnData = "OK"


def _hide_palette(palette) -> None:
    if palette:
        palette.isVisible = False


def _execute_command(cmd_id: str) -> None:
    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if cmd_def is None:
        ui.messageBox(f"Command '{cmd_id}' is not available.", CMD_NAME)
        return
    cmd_def.execute()


def _active_design_or_none() -> adsk.fusion.Design | None:
    product = app.activeProduct
    return adsk.fusion.Design.cast(product) if product else None


def _action_launch_fasteners(palette) -> str:
    """Hand off to Fusion's Fasteners dialog.

    Unlike the two PowerTools handoffs, this one can be legitimately unavailable:
    Fusion disables Fasteners for part-intent and direct-modeling designs, in the
    Form environment, for library and AnyCAD-derived components, and when the
    document is not on a Fusion hub. A disabled command definition executes as a
    silent no-op, which from the palette looks like a dead link, so the state is
    checked first and reported instead.

    :return: An empty string once the command has started, else a message to show
    """
    cmd_def = ui.commandDefinitions.itemById(_FASTENERS_CMD_ID)
    if cmd_def is None:
        return "Fasteners is not available in this version of Fusion."

    try:
        is_enabled = cmd_def.controlDefinition.isEnabled
    except Exception:
        # Older builds may not expose the control definition; let Fusion decide.
        is_enabled = True
    if not is_enabled:
        return (
            "Fusion has Fasteners disabled for this document.\n\n"
            "It needs an assembly or hybrid design saved to a Fusion hub, with "
            "design history captured, in the Solid or Sheet Metal environment."
        )

    _hide_palette(palette)
    cmd_def.execute()
    ptutil.log(f"{CMD_NAME}: handed off to {_FASTENERS_CMD_ID}.")
    return ""


# Target-folder + project-label resolution now live in ptAddInUtils
# (cache.resolve_target_folder / cache.target_project_label) so the Assembly
# Builder shares the exact same InternalValidationError-safe logic.


def _action_create_component(data: dict) -> str:
    name = (data.get("name") or "").strip()
    intent = data.get("intent", "part")
    if not name:
        return "Component name is required."
    fusion_intent = _INTENT_MAP.get(intent)
    if fusion_intent is None:
        return f"Unknown intent: {intent}"

    design = _active_design_or_none()
    if design is None:
        return "No active Fusion design."

    # A new external component needs a target DataFolder for its eventual save.
    # The old code read app.data.activeProject.rootFolder directly and outside a
    # try, so an InternalValidationError('id.size()') there propagated to the
    # handler wrapper and was swallowed silently (handle_error defaults to
    # show_message_box=False) — the classic "nothing happens".
    folder = cache.resolve_target_folder(CMD_NAME)
    if folder is None:
        return (
            "Couldn't determine a project to hold the new component. Open the "
            "Data Panel and click into the project you want to work in (or save "
            "this document once), then try New Component again."
        )

    transform = adsk.core.Matrix3D.create()
    try:
        occ = design.rootComponent.occurrences.addNewExternalComponent(
            name, folder, transform
        )
        if not occ:
            return f"Failed to create component '{name}'."
        try:
            occ.component.parentDesign.designIntent = fusion_intent
        except Exception as e:
            ptutil.log(f"{CMD_NAME}: could not set intent on '{name}': {e}")
        ptutil.log(f"{CMD_NAME}: created external '{name}' ({intent}).")
        return ""
    except Exception as e:
        return f"Create failed: {e}"


def _end_active_command() -> None:
    """End any running command so an insert does not start inside one.

    Clicking a ribbon button ends whatever command is active, but the palette is
    not part of the ribbon and stays clickable throughout. Since an insert now
    leaves Edit Initial Position open, clicking a second card would otherwise call
    ``addByInsert`` from inside that command. Terminating discards an uncommitted
    position edit, exactly as pressing Escape would — the click was a deliberate
    move away from the dialog.
    """
    try:
        active = ui.activeCommand
    except Exception:
        return  # older builds may not expose it; let Fusion arbitrate
    if not active or active in _IDLE_CMD_IDS:
        return
    try:
        ui.terminateActiveCommand()
        ptutil.log(f"{CMD_NAME}: ended '{active}' before inserting.")
    except Exception as e:
        ptutil.log(f"{CMD_NAME}: could not end '{active}' — {e}")


def _action_insert_doc(data: dict) -> str:
    df_id = data.get("dataFileId", "")
    if not df_id:
        return "Missing dataFileId."

    design = _active_design_or_none()
    if design is None:
        return "No active Fusion design."

    data_file = _find_data_file_by_id(df_id)
    if data_file is None:
        return "Could not resolve the selected document."

    # An insert leaves Edit Initial Position open, so a second card click has to
    # end it before calling addByInsert from inside a running command.
    _end_active_command()
    transform = adsk.core.Matrix3D.create()
    try:
        occurrence = design.rootComponent.occurrences.addByInsert(
            data_file, transform, True
        )
    except Exception as e:
        return f"Insert failed: {e}"
    # Documented to return null rather than raise when the insert fails (most
    # often the DataFile living in a different project than this document).
    if occurrence is None:
        return (
            f"Fusion could not insert '{getattr(data_file, 'name', df_id)}'.\n\n"
            "A referenced insert requires the document to be in the same project "
            "as this assembly."
        )

    intent_name = data.get("intent", "")
    _touch_recent(df_id, getattr(data_file, "name", ""), intent_name)
    # Remember this doc was inserted in this session so the next refresh
    # hides it from both galleries — a second click would silently create a
    # duplicate occurrence in the assembly.
    _inserted_in_session.add(df_id)
    ptutil.log(f"{CMD_NAME}: inserted '{getattr(data_file, 'name', df_id)}'.")
    _schedule_finish_insert(occurrence)
    return ""


class _FinishInsertHandler(adsk.core.CustomEventHandler):
    """Runs the post-insert chain outside the palette's HTML event.

    The first attempt called _finish_insert_like_fusion directly from
    ``incomingFromHTML`` and nothing visible happened. The API calls it makes are
    individually correct and ``CommandDefinition.execute`` is used the same way by
    the Fasteners handoff, which works — so the suspects were contextual: the
    palette's message handler is a poor place to start a command from, and the
    caller runs a full palette refresh the moment the handler returns, which can
    disturb the selection the command reads. A ``customEvent`` handler runs on the
    main thread after both are done, which is the same deferral
    ``commands/externalize/entry.py`` needs for its saveCopyAs pipeline.
    """

    def notify(self, args):
        global _pending_finish
        occurrence = _pending_finish
        _pending_finish = None
        if occurrence is None:
            ptutil.log(f"{CMD_NAME}: finish handler fired with nothing pending.")
            return
        # The state on arrival tells us whether the deferral landed on a clean turn.
        # Read defensively: activeCommand is not exposed on every build, and a raise
        # here would take the whole chain down before it started.
        ptutil.log(
            f"{CMD_NAME}: finish handler entered, "
            f"activeCommand={_read_property(ui, 'activeCommand')!r}."
        )
        try:
            _finish_insert_like_fusion(occurrence)
        except Exception:
            ptutil.handle_error(CMD_NAME)


def _schedule_finish_insert(occurrence) -> None:
    """Queue the select → fit → position chain for a later main-loop turn.

    Firing the customEvent straight from this HTML event was not enough of a
    deferral. A position command *did* start — it appeared on screen for a moment
    and then died with the selection — so Fusion dispatched the handler inside the
    same event turn, and finishing the HTML event (plus the full palette refresh the
    caller runs right after) tore the command back down.

    So the fire is delayed on a worker thread instead. ``fireCustomEvent`` is the
    one Application call documented as safe to make off the main thread, and it is
    all the worker does; the handler itself still runs on the main thread, now on a
    turn where the HTML event and the refresh are both long finished.

    ``fireCustomEvent`` is also documented to return True on success but returns
    **False even when the event fires** — the debug log shows "returned False"
    followed immediately by the handler running. Clearing ``_pending_finish`` on
    that return is what made an earlier attempt look dead, so the return value is
    ignored; a pending occurrence left over from an event that genuinely never fired
    is harmless, since the next insert overwrites it before firing again.
    """
    global _pending_finish
    _pending_finish = occurrence
    timer = threading.Timer(_FINISH_DELAY_SECONDS, _fire_finish_event)
    timer.daemon = True  # never hold Fusion open on a pending insert
    timer.start()
    ptutil.log(
        f"{CMD_NAME}: post-insert chain queued (+{_FINISH_DELAY_SECONDS}s, "
        f"{_FINISH_EVENT_ID})."
    )


def _fire_finish_event() -> None:
    """Hand the chain to the main thread. Runs on the timer's worker thread.

    Nothing here may touch the Fusion API beyond ``fireCustomEvent`` — including
    ptutil.log, which calls ``Application.log``. Anything worth reporting is logged
    by the handler, on the main thread.
    """
    try:
        app.fireCustomEvent(_FINISH_EVENT_ID)
    except Exception:
        pass


def _finish_insert_like_fusion(occurrence) -> None:
    """Leave the new occurrence selected, framed, and in a position command.

    Always reached through _FinishInsertHandler, never straight from the palette
    message — see that class for why.

    Fusion's own Insert Component chains five commands — FusionImportCommand,
    CommitCommand, SelectCommand, FitCommand, FusionMoveCommand. ``addByInsert``
    is the import and commit; this adds the last three so a palette insert ends
    ready to position instead of sitting unselected at the origin, with Edit
    Initial Position in place of Move/Copy so the user adjusts the placement the
    insert already recorded rather than adding a Move feature over the top of it.

    Each step degrades independently: a failure to select or fit must not stop the
    position dialog from opening, and none of them should turn a successful insert
    into a reported failure — the component is already in the assembly by this
    point.
    """
    ptutil.log(f"{CMD_NAME}: running the post-insert chain.")
    _select_only(occurrence, "the inserted occurrence")

    try:
        # Before the position dialog, so it opens over a framed view rather than
        # re-framing underneath it.
        app.activeViewport.fit()
    except Exception as e:
        ptutil.log(f"{CMD_NAME}: could not fit the view after insert — {e}")

    # Fusion refuses the edit outright for some occurrences, patterned ones for
    # example. Note the spelling: isVaild is the typo the API itself ships with, so
    # a build that ever corrects it leaves the check unanswered (None) rather than
    # blocking. Being ungrounded is NOT a blocker despite Fusion's tips text
    # scoping the command to a ground-to-parent component — a fresh insert reports
    # groundToParent=False and the dialog opens on it anyway.
    valid = _read_property(occurrence, "isVaildForEditInitialPosition")
    if valid is False:
        ptutil.log(
            f"{CMD_NAME}: occurrence is not valid for Edit Initial Position — "
            "insert only."
        )
        return

    if _start_edit_initial_position():
        return

    # Nothing came up. Log the occurrence state that would explain it, rather than
    # leaving the next person to re-derive it from an empty "did not start".
    ptutil.log(
        f"{CMD_NAME}: no position command started — "
        f"validForEditInitialPosition={valid}, "
        f"groundToParent={_read_property(occurrence, 'isGroundToParent')}."
    )


def _select_only(entity, label: str) -> bool:
    """Make *entity* the entire selection, logging rather than raising on failure.

    ``Selections.add`` returns a bool as well as being able to raise, so a
    selection can fail silently — worth logging, since every command downstream
    reads the selection.
    """
    try:
        ui.activeSelections.clear()
        added = ui.activeSelections.add(entity)
    except Exception as e:
        ptutil.log(f"{CMD_NAME}: could not select {label} — {e}")
        return False
    ptutil.log(f"{CMD_NAME}: selected {label} (add → {added}).")
    return bool(added)


def _read_property(obj, name: str):
    """Read a property off a Fusion object, or None when it is unavailable.

    Plain ``getattr`` with a default is not enough: it only swallows
    AttributeError, and a Fusion property is free to raise something else.
    """
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _start_edit_initial_position() -> bool:
    """Try the Edit Initial Position ids against the current selection.

    :return: True as soon as one of them actually starts
    """
    return any(_try_start_command(cmd_id) for cmd_id in _EDIT_POSITION_CMD_IDS)


def _try_start_command(cmd_id: str) -> bool:
    """Execute *cmd_id* and report whether a command actually came up.

    ``controlDefinition.isEnabled`` is deliberately NOT a gate here, unlike the
    Fasteners handoff. Both Edit Initial Position definitions report isEnabled
    **False** even when the command starts perfectly well: they exist only in the
    marking menus, and Fusion resolves that kind of command's availability while it
    builds the menu instead of keeping the standing ControlDefinition current.
    Fasteners is a real ribbon button, so its isEnabled means something — this one's
    does not, and gating on it skipped both ids and left the insert with no
    follow-up at all.

    ``execute()``'s own return value is not enough either: it answers True whether
    or not the command appears. So the outcome is *observed* through
    ``ui.activeCommand``, which is the only direct evidence a command started. When
    activeCommand cannot be read, execute()'s answer is all there is — and trusting
    it beats firing another command on top of one that already started.
    """
    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if cmd_def is None:
        ptutil.log(f"{CMD_NAME}: {cmd_id} is not in this build.")
        return False
    try:
        started = cmd_def.execute()
    except Exception as e:
        ptutil.log(f"{CMD_NAME}: {cmd_id} execute raised — {e}")
        return False
    active = _active_command_id()
    ptutil.log(
        f"{CMD_NAME}: {cmd_id} execute → {started}, activeCommand={active!r}, "
        f"isEnabled={_command_is_enabled(cmd_def)}."
    )
    if active is None:
        return bool(started)
    return active not in _IDLE_CMD_IDS


def _active_command_id() -> str | None:
    """The running command's id once it has had time to come up, or None.

    A command started by ``execute()`` does not become active in the same turn:
    reading activeCommand after a single ``doEvents()`` reported "SelectCommand"
    for a command that visibly did start, which had the caller fall through and fire
    a second command over the top of the running one. pump_events_for keeps the UI
    turning for long enough that an idle answer means idle.
    """
    try:
        ptutil.pump_events_for(_COMMAND_START_WAIT_SECONDS)
    except Exception:
        pass
    try:
        return ui.activeCommand
    except Exception:
        return None


def _command_is_enabled(cmd_def):
    """cmd_def.controlDefinition.isEnabled, or None when the build hides it.

    Logged as evidence only — see _start_edit_initial_position for why it is not
    trusted as a gate.
    """
    try:
        return cmd_def.controlDefinition.isEnabled
    except Exception:
        return None
