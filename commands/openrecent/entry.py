# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

# Open Recent.
#
# Adds an "Open Recent" flyout to the QAT File dropdown, directly after the
# native "Open" command. The flyout lists recently-touched part/hybrid/assembly
# documents from the shared PowerTools recents cache (lib/ptAddInUtils/
# recents_utils), newest-first. Each item displays the document name; hovering
# shows the document's Data Panel location and a thumbnail tool-clip. Selecting
# an item opens that document in Fusion.
#
# The recents cache is shared with New Assembly (commands/assemblyintent). This
# command ALSO records the active document on documentActivated, so the recents
# list grows even when the Assembly commands are disabled — Open Recent has no
# hard dependency on any other command.

import adsk.core

from ...lib import ptAddInUtils as ptutil
from ...lib.ptAddInUtils import recents_utils as recents

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Open Recent"
CMD_Description = (
    "Open a recently used document from the PowerTools recents list, straight "
    "from the File menu."
)

# The flyout control (a DropDownControl nested in the File dropdown) and the
# per-item command definitions it holds.
DROPDOWN_ID = "PT_openrecent_dropdown"
ITEM_ID_PREFIX = "PT_openrecent_item_"
EMPTY_ITEM_ID = "PT_openrecent_empty"

# Max entries shown in the flyout. The cache itself holds up to
# recents.RECENT_LIMIT; the menu is capped shorter to stay quick to scan.
MENU_LIMIT = 15

# No icon assets — an empty resource folder renders the default menu glyph,
# matching Scripts and Add-ins / PowerTools Preferences in the same File menu.
ICON_FOLDER = ""

# Candidate command IDs for the native File-menu "Open" control, most likely
# first. The flyout is inserted directly AFTER whichever is present.
# "OpenCommand" is the confirmed ID on the current Fusion build; the rest are
# fallbacks for other releases (Fusion has renamed this control across
# versions). A DEBUG build logs the actual File-dropdown control IDs (see
# _dump_file_menu_ids) so the exact anchor can be confirmed on a given build.
_OPEN_ANCHOR_CANDIDATES = (
    "OpenCommand",
    "OpenDocumentCommand",
    "FusionOpenDocumentCommand",
    "OpenClientCommand",
    "OpenFromMyComputerCommand",
    "open",
)
# Fallbacks when no Open control is found: sit just after New, else just before
# the PowerTools Preferences item (always present — it is infrastructure).
_NEW_ANCHOR_CANDIDATES = ("NewDocumentCommand", "new")
_PREFERENCES_CMD_ID = "PT_preferences"

local_handlers = []

# Module state: the flyout control, the IDs of its dynamic item command
# definitions, and a signature of the last-built list so we can skip a rebuild
# when the visible recents have not changed (documentActivated fires on every
# tab switch).
_dropdown = None
_item_cmd_ids: list[str] = []
_last_signature = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _qat_file_dropdown():
    qat = ui.toolbars.itemById("QAT")
    if not qat:
        return None
    return adsk.core.DropDownControl.cast(qat.controls.itemById("FileSubMenuCommand"))


def start():
    global _dropdown, _last_signature

    file_dd = _qat_file_dropdown()
    if file_dd is None:
        ptutil.log(f"{CMD_NAME}: QAT File dropdown unavailable — skipping.")
        return

    _dump_file_menu_ids(file_dd)

    existing = file_dd.controls.itemById(DROPDOWN_ID)
    if existing:
        existing.deleteMe()

    anchor_id, want_after = _resolve_open_anchor(file_dd)
    if anchor_id:
        _dropdown = _add_flyout_positioned(file_dd, anchor_id, want_after)
    else:
        _dropdown = file_dd.controls.addDropDown(CMD_NAME, ICON_FOLDER, DROPDOWN_ID)

    _last_signature = None
    _rebuild_menu()

    # Keep the flyout current. The recents cache grows as documents are opened
    # and activated, and Fusion exposes no "menu about to open" event, so the
    # flyout is rebuilt on document events (mirrors Favorites' rebuild-on-hub-
    # change). documentOpened is a belt-and-suspenders backup where available.
    ptutil.add_handler(
        app.documentActivated, _on_document_event, local_handlers=local_handlers
    )
    opened = getattr(app, "documentOpened", None)
    if opened is not None:
        try:
            ptutil.add_handler(
                opened, _on_document_event, local_handlers=local_handlers
            )
        except Exception:
            pass


def stop():
    global _dropdown, _item_cmd_ids, local_handlers, _last_signature

    _clear_items()
    file_dd = _qat_file_dropdown()
    if file_dd:
        ctrl = file_dd.controls.itemById(DROPDOWN_ID)
        if ctrl:
            ctrl.deleteMe()

    _dropdown = None
    _item_cmd_ids = []
    _last_signature = None
    local_handlers = []


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def _resolve_open_anchor(file_dd):
    """Return (anchor_control_id, want_after) for placing the flyout.

    ``want_after`` is the *intent* — True to sit directly after the anchor, False
    to sit directly before it. The actual `isBefore` flag needed to achieve that
    is worked out empirically in `_add_flyout_positioned` (see its docstring),
    because the flag's effective direction has proven unreliable when adding into
    the File dropdown across Fusion builds.

    Preference order: directly after the native Open command; else after New;
    else before PowerTools Preferences; else ("", …) meaning "append"."""
    for cid in _OPEN_ANCHOR_CANDIDATES:
        if file_dd.controls.itemById(cid):
            return cid, True  # AFTER Open
    for cid in _NEW_ANCHOR_CANDIDATES:
        if file_dd.controls.itemById(cid):
            return cid, True  # AFTER New (best available slot)
    if file_dd.controls.itemById(_PREFERENCES_CMD_ID):
        return _PREFERENCES_CMD_ID, False  # BEFORE Preferences
    return "", True  # append to the dropdown


def _control_index(controls, control_id) -> int:
    """Return the index of *control_id* in *controls*, or -1 if not present."""
    for i in range(controls.count):
        try:
            if controls.item(i).id == control_id:
                return i
        except Exception:
            continue
    return -1


def _add_flyout_positioned(file_dd, anchor_id, want_after):
    """Add the flyout so it lands on the requested side of *anchor_id*.

    `ToolbarControls.addDropDown(text, resourceFolder, id, positionID, isBefore)`
    is documented as isBefore=True → before / False → after, but that flag's
    effective direction has proven unreliable for controls added into the
    built-in File dropdown (the flyout came out on the wrong side of the Open
    command in testing). Rather than hard-code an assumption, this adds the
    control, checks its actual index relative to the anchor, and recreates it
    with the opposite flag if it landed on the wrong side — so the result is
    correct regardless of how this Fusion build interprets the flag.
    """
    # Documented mapping first (want_after → isBefore=False), then the opposite.
    for is_before in (not want_after, want_after):
        dd = file_dd.controls.addDropDown(
            CMD_NAME, ICON_FOLDER, DROPDOWN_ID, anchor_id, is_before
        )
        a = _control_index(file_dd.controls, anchor_id)
        d = _control_index(file_dd.controls, DROPDOWN_ID)
        landed_after = d == a + 1
        landed_before = a == d + 1
        if a != -1 and (
            (want_after and landed_after) or (not want_after and landed_before)
        ):
            ptutil.log(
                f"{CMD_NAME}: placed flyout at index {d} "
                f"({'after' if want_after else 'before'} '{anchor_id}' @ {a}), "
                f"isBefore={is_before}."
            )
            return dd
        # Wrong side (or position not honoured) — remove and try the other flag.
        try:
            dd.deleteMe()
        except Exception:
            pass

    # Neither flag produced the requested side; fall back to the documented
    # placement so the flyout is at least present.
    ptutil.log(
        f"{CMD_NAME}: could not verify placement relative to '{anchor_id}'; "
        "using documented isBefore fallback."
    )
    return file_dd.controls.addDropDown(
        CMD_NAME, ICON_FOLDER, DROPDOWN_ID, anchor_id, not want_after
    )


def _dump_file_menu_ids(file_dd) -> None:
    """DEBUG-only: log the File dropdown's control IDs so the real Open anchor
    can be confirmed on a given Fusion build. ptutil.log no-ops unless DEBUG."""
    try:
        ids = [file_dd.controls.item(i).id for i in range(file_dd.controls.count)]
        ptutil.log(f"{CMD_NAME}: File dropdown control IDs = {ids}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Menu building
# ---------------------------------------------------------------------------


def _clear_items() -> None:
    """Delete the dynamic item controls and their command definitions."""
    global _item_cmd_ids
    ids = _item_cmd_ids + [EMPTY_ITEM_ID]
    if _dropdown is not None:
        for cmd_id in ids:
            ctrl = _dropdown.controls.itemById(cmd_id)
            if ctrl:
                ctrl.deleteMe()
    for cmd_id in ids:
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if cmd_def:
            cmd_def.deleteMe()
    _item_cmd_ids = []


def _rebuild_menu() -> None:
    """Repopulate the flyout from the recents cache, newest-first."""
    global _item_cmd_ids, _last_signature

    if _dropdown is None:
        return

    active_id = _active_data_file_id()
    items = recents.list_recent(
        exclude_ids={active_id} if active_id else None, limit=MENU_LIMIT
    )

    # Skip the rebuild (and its command-definition churn) when nothing visible
    # changed — documentActivated fires on every tab switch.
    signature = tuple(
        (
            it["dataFileId"],
            it["name"],
            it.get("location", ""),
            bool(it.get("thumbPath")),
        )
        for it in items
    )
    if signature == _last_signature and _dropdown.controls.count > 0:
        return
    _last_signature = signature

    _clear_items()

    if not items:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            EMPTY_ITEM_ID,
            "No recent documents",
            "Recently used documents appear here as you open and work on them.",
            ICON_FOLDER,
        )
        ctrl = _dropdown.controls.addCommand(cmd_def)
        try:
            ctrl.isEnabled = False  # a non-actionable placeholder
        except Exception:
            pass
        return

    for i, item in enumerate(items):
        cmd_id = f"{ITEM_ID_PREFIX}{i}"
        name = item["name"] or "Untitled"
        location = item.get("location", "")
        # The tooltip carries the document's Data Panel location; the tool-clip
        # image carries its cached thumbnail.
        tooltip = location or "Recently used document"

        existing = ui.commandDefinitions.itemById(cmd_id)
        if existing:
            existing.deleteMe()
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            cmd_id, name, tooltip, ICON_FOLDER
        )
        thumb_path = item.get("thumbPath", "")
        if thumb_path:
            try:
                cmd_def.toolClipFilename = thumb_path
            except Exception:
                pass

        ptutil.add_handler(
            cmd_def.commandCreated,
            _make_open_handler(item["dataFileId"], name),
            local_handlers=local_handlers,
        )
        _dropdown.controls.addCommand(cmd_def)
        _item_cmd_ids.append(cmd_id)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _make_open_handler(df_id: str, name: str):
    """Return a commandCreated handler that opens *df_id* when executed."""

    def _created(args: adsk.core.CommandCreatedEventArgs):
        def _execute(exec_args: adsk.core.CommandEventArgs):
            _open_recent(df_id, name)

        ptutil.add_handler(
            args.command.execute, _execute, local_handlers=local_handlers
        )

    return _created


def _open_recent(df_id: str, name: str) -> None:
    try:
        data_file = _find_data_file_by_id(df_id)
        if data_file is None:
            ui.messageBox(
                f"Could not find “{name}”.\n\n"
                "It may have been moved or deleted, or you may need to switch to "
                "the hub it belongs to.",
                CMD_NAME,
            )
            return
        app.documents.open(data_file)
        ptutil.log(f"{CMD_NAME}: opened '{name}' ({df_id}).")
    except Exception:
        ptutil.handle_error(CMD_NAME)
        ui.messageBox(f"Unable to open “{name}”.", CMD_NAME)


def _find_data_file_by_id(df_id: str):
    """Resolve a DataFile from its lineage URN, or None on failure."""
    if not df_id:
        return None
    try:
        finder = getattr(app.data, "findFileById", None)
        if callable(finder):
            return finder(df_id)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------


def _on_document_event(args: adsk.core.DocumentEventArgs) -> None:
    """Record the activated/opened document and refresh the flyout."""
    try:
        recents.remember_recent_if_eligible(args.document)
        _rebuild_menu()
    except Exception:
        ptutil.handle_error(CMD_NAME)


def _active_data_file_id() -> str:
    try:
        df = getattr(app.activeDocument, "dataFile", None)
        return getattr(df, "id", "") if df else ""
    except Exception:
        return ""
