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
# The recents cache is shared with Assembly Palette (commands/assemblypalette). This
# command ALSO records the active document on documentActivated, so the recents
# list grows even when the Assembly commands are disabled — Open Recent has no
# hard dependency on any other command.

import adsk.core

from ...lib import ptAddInUtils as ptutil
from ...lib.ptAddInUtils import recents_utils as recents
from . import menu_plan
from .menu_plan import EMPTY_ITEM_ID

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Open Recent"
CMD_Description = "Add a flyout to the File menu that lists your recently used documents, with location and thumbnail on hover, and opens one on click."

# The flyout control (a DropDownControl nested in the File dropdown) and the
# per-item command definitions it holds. The item ids are positional
# (``PT_openrecent_item_0`` is the newest entry) and live in menu_plan.py with
# the rest of the adsk-free rebuild logic.
DROPDOWN_ID = "PT_openrecent_dropdown"

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

# Module state: the flyout control; the definitions this module instance has
# wired a commandCreated handler to (so a rebuild updates them in place and
# never attaches a second handler); what each positional button opens right
# now; ids whose deleteMe() did not take and must be retried; and a signature
# of the last *completed* build so a rebuild can be skipped when the visible
# recents have not changed (documentActivated fires on every tab switch).
_dropdown = None
_owned_ids: set[str] = set()
_item_targets: dict[str, tuple[str, str]] = {}
_leftover_ids: set[str] = set()
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
    global _dropdown, local_handlers, _last_signature

    _clear_items()
    file_dd = _qat_file_dropdown()
    if file_dd:
        ctrl = file_dd.controls.itemById(DROPDOWN_ID)
        if ctrl:
            ctrl.deleteMe()

    _dropdown = None
    _owned_ids.clear()
    _item_targets.clear()
    _leftover_ids.clear()
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


def _all_item_ids() -> list[str]:
    """Every id this flyout can ever own, whatever an earlier build tracked."""
    return [menu_plan.item_cmd_id(i) for i in range(MENU_LIMIT)] + [EMPTY_ITEM_ID]


def _clear_items() -> None:
    """Delete every item control and command definition the flyout can own.

    Works from the full id range rather than a record of the last build, so it
    also sweeps up what an unclean reload or a half-finished rebuild left
    behind (rule 10: start()/stop() idempotent).
    """
    for cmd_id in _all_item_ids():
        _remove_item(cmd_id)
    _item_targets.clear()


def _remove_item(cmd_id: str) -> None:
    """Delete *cmd_id*'s control and definition; remember it if Fusion refuses.

    ``deleteMe()`` reports failure by returning False, not by raising, and
    does so when the definition's own command is in flight (the rebuild runs
    inside the item's commandCreated — see menu_plan.py). A survivor is noted
    in ``_leftover_ids`` so the next rebuild retries instead of skipping on an
    unchanged signature. Its handler stays attached, so it stays in
    ``_owned_ids`` and is updated in place if its slot is needed again.
    """
    _item_targets.pop(cmd_id, None)
    survived = False
    if _dropdown is not None:
        ctrl = _dropdown.controls.itemById(cmd_id)
        if ctrl:
            ctrl.deleteMe()
            if _dropdown.controls.itemById(cmd_id):
                survived = True
    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if cmd_def:
        cmd_def.deleteMe()
        if ui.commandDefinitions.itemById(cmd_id):
            survived = True
    if survived:
        _leftover_ids.add(cmd_id)
        ptutil.log(f"{CMD_NAME}: '{cmd_id}' refused deletion; will retry.")
    else:
        _leftover_ids.discard(cmd_id)
        _owned_ids.discard(cmd_id)


def _ensure_definition(cmd_id: str, name: str, tooltip: str):
    """Return the definition for *cmd_id* showing *name*/*tooltip*.

    Reuses the definition if this module instance already owns it (its
    commandCreated handler is attached and routes through ``_item_targets``,
    so only the text changes). A definition this instance did not create —
    left by an unclean reload, with a handler from a dead module — is deleted
    and recreated when Fusion allows, else adopted. Never calls
    ``addButtonDefinition`` for an id that is still present.
    """
    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if cmd_def and cmd_id not in _owned_ids:
        cmd_def.deleteMe()
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if cmd_def:
            ptutil.log(f"{CMD_NAME}: adopting foreign definition '{cmd_id}'.")
    if cmd_def:
        cmd_def.name = name
        cmd_def.tooltip = tooltip
    else:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            cmd_id, name, tooltip, ICON_FOLDER
        )
    if cmd_id not in _owned_ids:
        ptutil.add_handler(
            cmd_def.commandCreated,
            _make_open_handler(cmd_id),
            local_handlers=local_handlers,
        )
        _owned_ids.add(cmd_id)
    return cmd_def


def _ensure_control(cmd_def, after_id: str = ""):
    """Return *cmd_def*'s control in the flyout, adding it after *after_id*
    (or at the end) when it is not there yet."""
    ctrl = _dropdown.controls.itemById(cmd_def.id)
    if ctrl:
        return ctrl
    if after_id and _dropdown.controls.itemById(after_id):
        return _dropdown.controls.addCommand(cmd_def, after_id, False)
    return _dropdown.controls.addCommand(cmd_def)


def _rebuild_menu() -> None:
    """Bring the flyout in line with the recents list, newest-first.

    Buttons are positional (slot 0 = newest), so an unchanged slot count means
    text updates only; the plan from ``menu_plan.plan_menu`` says which slots
    to keep and which to remove. ``_last_signature`` is cleared before the
    work and set only after it completes, so an exception midway leaves a
    state the next document event rebuilds rather than one it skips.
    """
    global _last_signature

    if _dropdown is None:
        return

    active_id = _active_data_file_id()
    # file_types=None: opening a drawing from the File menu is as reasonable as
    # opening a design, so this flyout lists every type Fusion recorded. (The New
    # Assembly gallery stays designs-only — its cards insert a component.)
    items = recents.list_recent(
        exclude_ids={active_id} if active_id else None,
        limit=MENU_LIMIT,
        file_types=None,
    )

    # Skip the rebuild when nothing visible changed — documentActivated fires
    # on every tab switch — unless a previous pass has deletions to retry.
    signature = menu_plan.menu_signature(items)
    if (
        signature == _last_signature
        and _dropdown.controls.count > 0
        and not _leftover_ids
    ):
        return
    _last_signature = None

    keep, remove = menu_plan.plan_menu(len(items), MENU_LIMIT)
    for cmd_id in remove:
        _remove_item(cmd_id)

    if not items:
        cmd_def = _ensure_definition(
            EMPTY_ITEM_ID, menu_plan.EMPTY_LABEL, menu_plan.EMPTY_TOOLTIP
        )
        ctrl = _ensure_control(cmd_def)
        try:
            ctrl.isEnabled = False  # a non-actionable placeholder
        except Exception:
            pass
        _last_signature = signature
        return

    previous_id = ""
    for cmd_id, item in zip(keep, items, strict=True):
        name = menu_plan.item_label(item)
        # The tooltip carries the document's Data Panel location; the tool-clip
        # image carries its cached thumbnail.
        cmd_def = _ensure_definition(cmd_id, name, menu_plan.item_tooltip(item))
        try:
            cmd_def.toolClipFilename = item.get("thumbPath", "") or ""
        except Exception:
            pass
        _item_targets[cmd_id] = (item["dataFileId"], name)
        _ensure_control(cmd_def, previous_id)
        previous_id = cmd_id

    _last_signature = signature


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _make_open_handler(cmd_id: str):
    """Return a commandCreated handler that opens whatever *cmd_id* shows now.

    The target is looked up in ``_item_targets`` at click time, not captured
    when the handler is made: the definition is positional and reused across
    rebuilds, so one handler per definition serves every document that slot
    ever displays.

    The open happens directly in commandCreated, deliberately not by way of the
    command's execute event. Fusion runs commands through a document-scoped
    pipeline: with no document open — the start screen, exactly where this menu
    matters most — commandCreated fires but the command terminates without ever
    raising execute, so an execute-based open silently did nothing. These items
    have no CommandInputs and no dialog, so there is nothing for execute to
    commit. Same fix as PowerTools Preferences; see the execution-model note in
    docs/arch/architecture.md.
    """

    def _created(args: adsk.core.CommandCreatedEventArgs):
        target = _item_targets.get(cmd_id)
        if target is None:
            ptutil.log(f"{CMD_NAME}: '{cmd_id}' has no target; ignoring click.")
            return
        _open_recent(*target)

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
    """Record the activated/opened document and refresh the flyout.

    An invisible open by another command fires the same events (issue #11);
    that sibling is never the user's document and must not land in recents.
    """
    if not ptutil.is_user_document(args.document):
        ptutil.log(f"{CMD_NAME}: document event is not the user's document, skipping.")
        return
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
