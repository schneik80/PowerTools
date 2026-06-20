# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core, adsk.fusion
import os, json, traceback
from ...lib import ptAddInUtils as ptutil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Favorites"
CMD_ID = "PTAT-favorites-dropdown"  # The QAT dropdown control ID
CMD_ADD_ID = "PTAT-favorites-add"  # The "Favorite This Location" button definition ID
CMD_ADD_NAME = "Favorite This Location"
CMD_ADD_Description = "Save the current document location to your Favorites menu"
CMD_EDIT_ID = "PTAT-favorites-edit"
CMD_EDIT_NAME = "Edit Favorites"
CMD_EDIT_DESCRIPTION = "Edit and remove saved favorites"

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Path to the addin root (3 levels up from this file: entry.py → favorites/ → commands/ → root)
ADDIN_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CACHE_DIR = os.path.join(ADDIN_ROOT, "cache")

# Legacy single-file path — deleted on start if it still exists.
_LEGACY_CACHE_FILE = os.path.join(CACHE_DIR, "favorites.json")

# Holds references to event handlers to prevent garbage collection
local_handlers = []

# Module-level reference to the dropdown control so _rebuild_menu can update it
_favorites_dropdown = None

# Tracks the IDs of dynamically created favorite command definitions for cleanup
_fav_cmd_ids = []

# Currently active hub ID — drives which per-hub cache file is read/written
_active_hub_id: str = ""

# Edit dialog state (staged only; committed on OK)
_edit_staged_favorites = []
_edit_checkbox_map = {}
_edit_build_version = 0

EDIT_TABLE_ID = "PTAT-favorites-edit-table"
EDIT_DELETE_BTN_ID = "PTAT-favorites-edit-delete"
EDIT_COUNT_ID = "PTAT-favorites-edit-count"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    global _favorites_dropdown, _active_hub_id

    # Remove the legacy single-file cache so old entries are not used.
    _remove_legacy_cache()

    # Resolve the hub that is active right now (may be empty string if no
    # document is open yet; hub will be detected when the first doc activates).
    _active_hub_id = _get_active_hub_id()

    # -- "Favorite This Location" command definition --
    add_cmd_def = ui.commandDefinitions.itemById(CMD_ADD_ID)
    if not add_cmd_def:
        add_cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ADD_ID, CMD_ADD_NAME, CMD_ADD_Description
        )
    ptutil.add_handler(
        add_cmd_def.commandCreated,
        _add_favorite_created,
        local_handlers=local_handlers,
    )

    # -- "Edit Favorites" command definition --
    edit_cmd_def = ui.commandDefinitions.itemById(CMD_EDIT_ID)
    if not edit_cmd_def:
        edit_cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_EDIT_ID, CMD_EDIT_NAME, CMD_EDIT_DESCRIPTION
        )
    ptutil.add_handler(
        edit_cmd_def.commandCreated,
        _edit_favorites_created,
        local_handlers=local_handlers,
    )

    # -- Dropdown in QAT --
    qat = ui.toolbars.itemById("QAT")
    existing = qat.controls.itemById(CMD_ID)
    if existing:
        existing.deleteMe()

    # Preferred placement: after Data Panel and before File/New.
    file_anchor_ids = ["FileSubMenuCommand", "NewDocumentCommand", "new"]
    data_anchor_ids = ["ShowDataPanelCommand", "DataPanelCommand"]

    anchor_id = ""
    is_before = True

    # Best placement is directly before File menu/New control.
    for candidate_id in file_anchor_ids:
        anchor_ctrl = qat.controls.itemById(candidate_id)
        if anchor_ctrl:
            anchor_id = candidate_id
            is_before = True
            break

    # Fallback: place directly after Data Panel control.
    if not anchor_id:
        for candidate_id in data_anchor_ids:
            anchor_ctrl = qat.controls.itemById(candidate_id)
            if anchor_ctrl:
                anchor_id = candidate_id
                is_before = False
                break

    if anchor_id:
        _favorites_dropdown = qat.controls.addDropDown(
            CMD_NAME, ICON_FOLDER, CMD_ID, anchor_id, is_before
        )
    else:
        _favorites_dropdown = qat.controls.addDropDown(CMD_NAME, ICON_FOLDER, CMD_ID)

    # Fixed "Add" button at the top of the dropdown
    _favorites_dropdown.controls.addCommand(add_cmd_def)
    _favorites_dropdown.controls.addCommand(edit_cmd_def)
    _favorites_dropdown.controls.addSeparator()

    # Populate with favorites for the initial hub
    _rebuild_menu()

    # Monitor document events to detect hub changes
    ptutil.add_handler(
        app.documentActivated,
        _favorites_document_event,
        local_handlers=local_handlers,
    )
    ptutil.add_handler(
        app.documentOpened,
        _favorites_document_event,
        local_handlers=local_handlers,
    )


def stop():
    global _favorites_dropdown, _fav_cmd_ids, local_handlers
    global _edit_staged_favorites, _edit_checkbox_map, _edit_build_version
    global _active_hub_id

    # Remove the dropdown from the QAT
    qat = ui.toolbars.itemById("QAT")
    dropdown = qat.controls.itemById(CMD_ID)
    if dropdown:
        dropdown.deleteMe()
    _favorites_dropdown = None

    # Delete the "Add" command definition
    add_cmd_def = ui.commandDefinitions.itemById(CMD_ADD_ID)
    if add_cmd_def:
        add_cmd_def.deleteMe()

    # Delete the "Edit" command definition
    edit_cmd_def = ui.commandDefinitions.itemById(CMD_EDIT_ID)
    if edit_cmd_def:
        edit_cmd_def.deleteMe()

    # Delete all dynamically created favorite command definitions
    for cmd_id in _fav_cmd_ids:
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if cmd_def:
            cmd_def.deleteMe()
    _fav_cmd_ids = []

    # Release handler references
    local_handlers = []
    _edit_staged_favorites = []
    _edit_checkbox_map = {}
    _edit_build_version = 0
    _active_hub_id = ""


# ---------------------------------------------------------------------------
# Hub detection and event handler
# ---------------------------------------------------------------------------


def _get_active_hub_id() -> str:
    """Return the ID of the currently active Fusion hub, or '' if unavailable."""
    try:
        hub = app.data.activeHub
        if hub is None:
            return ""
        hub_id = getattr(hub, "id", None) or getattr(hub, "hubId", None)
        return str(hub_id) if hub_id else ""
    except Exception:
        return ""


def _hub_cache_file(hub_id: str) -> str:
    """Return the per-hub cache file path for the given hub ID.

    The hub ID (e.g. 'b.abc123def456') is sanitised by replacing every
    character that is not alphanumeric or a hyphen/underscore with '_'.
    Example: 'b.abc123' → cache/favorites_b_abc123.json
    """
    if not hub_id:
        safe = "unknown"
    else:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in hub_id)
    return os.path.join(CACHE_DIR, f"favorites_{safe}.json")


def _favorites_document_event(args: adsk.core.DocumentEventArgs):
    """Fire on documentActivated / documentOpened; switch hub cache if needed."""
    try:
        new_hub_id = _get_active_hub_id()
        if new_hub_id and new_hub_id != _active_hub_id:
            _on_hub_changed(new_hub_id)
    except Exception:
        ptutil.log(
            f"Favorites: hub-check error\n{traceback.format_exc()}",
            adsk.core.LogLevels.ErrorLogLevel,
        )


def _on_hub_changed(new_hub_id: str) -> None:
    """Update the active hub and rebuild the menu with that hub's favorites."""
    global _active_hub_id
    old_hub_id = _active_hub_id
    _active_hub_id = new_hub_id
    ptutil.log(
        f"Favorites: hub changed from '{old_hub_id}' to '{new_hub_id}', rebuilding menu"
    )
    _rebuild_menu()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _remove_legacy_cache() -> None:
    """Delete the old single-file favorites.json if it still exists."""
    if os.path.exists(_LEGACY_CACHE_FILE):
        try:
            os.remove(_LEGACY_CACHE_FILE)
            ptutil.log("Favorites: removed legacy cache/favorites.json")
        except Exception:
            ptutil.log(
                f"Favorites: could not remove legacy cache\n{traceback.format_exc()}",
                adsk.core.LogLevels.ErrorLogLevel,
            )


def _load_favorites() -> list:
    """Load the favorites list for the active hub from its per-hub cache file."""
    cache_file = _hub_cache_file(_active_hub_id)
    if not os.path.exists(cache_file):
        return []
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("favorites", [])
    except Exception:
        ptutil.log(
            f"Favorites: failed to load cache '{cache_file}'\n{traceback.format_exc()}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        return []


def _save_favorites(favorites: list) -> None:
    """Persist the favorites list for the active hub to its per-hub cache file."""
    cache_file = _hub_cache_file(_active_hub_id)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"hub_id": _active_hub_id, "favorites": favorites}, f, indent=2)


# ---------------------------------------------------------------------------
# Dynamic menu builder
# ---------------------------------------------------------------------------


def _rebuild_menu() -> None:
    """Clear and recreate the dynamic favorite items in the dropdown."""
    global _fav_cmd_ids

    if _favorites_dropdown is None:
        return

    # Remove existing favorite controls and their command definitions
    for cmd_id in _fav_cmd_ids:
        ctrl = _favorites_dropdown.controls.itemById(cmd_id)
        if ctrl:
            ctrl.deleteMe()
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if cmd_def:
            cmd_def.deleteMe()
    _fav_cmd_ids = []

    favorites = _load_favorites()

    for i, fav in enumerate(favorites):
        cmd_id = f"PTAT-fav-{i}"
        display = fav.get("display", "Unknown Location")
        urn = fav.get("urn", "")

        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if not cmd_def:
            cmd_def = ui.commandDefinitions.addButtonDefinition(
                cmd_id,
                display,
                f"Navigate to {display} in Fusion Hub",
            )

        # Build a handler that captures this entry's URN via closure
        ptutil.add_handler(
            cmd_def.commandCreated,
            _make_navigate_handler(urn, display),
            local_handlers=local_handlers,
        )

        _favorites_dropdown.controls.addCommand(cmd_def)
        _fav_cmd_ids.append(cmd_id)

    ptutil.log(
        f"Favorites: menu rebuilt with {len(favorites)} item(s) for hub '{_active_hub_id}'"
    )


def _make_navigate_handler(urn: str, display: str):
    """Return a commandCreated handler that navigates to *urn* when executed."""

    def _created(args: adsk.core.CommandCreatedEventArgs):
        def _execute(exec_args: adsk.core.CommandEventArgs):
            try:
                app.executeTextCommand(f"Dashboard.ShowInLocation {urn}")
                ptutil.log(f"Favorites: navigated to '{display}' ({urn})")
            except Exception:
                ptutil.log(
                    f"Favorites: navigation failed\n{traceback.format_exc()}",
                    adsk.core.LogLevels.ErrorLogLevel,
                )
                ui.messageBox(
                    f"Unable to navigate to '{display}'.\n\nThe location may no longer exist.",
                    "Favorites",
                )

        ptutil.add_handler(args.command.execute, _execute, local_handlers=local_handlers)

    return _created


# ---------------------------------------------------------------------------
# "Add Favorite" command handlers
# ---------------------------------------------------------------------------


def _add_favorite_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME}: Add Favorite command created")
    ptutil.add_handler(
        args.command.execute, _add_favorite_execute, local_handlers=local_handlers
    )


def _add_favorite_execute(args: adsk.core.CommandEventArgs):
    ptutil.log(f"{CMD_NAME}: Add Favorite execute")
    try:
        doc = app.activeDocument
        if not doc:
            ui.messageBox("No active document found.", "Favorites")
            return

        if not doc.isSaved:
            ui.messageBox(
                "The active document must be saved to Fusion Hub before it can be added to Favorites.",
                "Favorites",
            )
            return

        data_file = doc.dataFile
        if not data_file:
            ui.messageBox(
                "Unable to access the document's cloud data.\n"
                "Ensure the document is saved to Fusion Team Hub.",
                "Favorites",
            )
            return

        # Use data_file.id — the same URN format that Dashboard.ShowInLocation
        # expects (consistent with the docopen Show In Location command).
        lineage_urn = getattr(data_file, "id", None)
        if not lineage_urn:
            ui.messageBox(
                "Unable to determine the active document URN.",
                "Favorites",
            )
            return
        lineage_urn = str(lineage_urn)

        folder = data_file.parentFolder
        if not folder:
            ui.messageBox(
                "Unable to determine the document's folder location.", "Favorites"
            )
            return

        display = _get_folder_lineage(folder)
        document_name = _get_document_name(data_file, doc)

        favorites = _load_favorites()

        # Prevent duplicates
        if any(f.get("urn") == lineage_urn for f in favorites):
            ui.messageBox(f'"{display}" is already in your Favorites.', "Favorites")
            return

        favorites.append(
            {"name": document_name, "display": display, "urn": lineage_urn}
        )
        _save_favorites(favorites)
        _rebuild_menu()

        ptutil.log(f"Favorites: saved '{display}' ({lineage_urn})")

    except Exception:
        ptutil.log(
            f"Favorites: error adding favorite\n{traceback.format_exc()}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        ui.messageBox(
            f"An error occurred while adding to Favorites:\n{traceback.format_exc()}",
            "Favorites",
        )


# ---------------------------------------------------------------------------
# "Edit Favorites" command handlers
# ---------------------------------------------------------------------------


def _edit_favorites_created(args: adsk.core.CommandCreatedEventArgs):
    global _edit_staged_favorites, _edit_checkbox_map, _edit_build_version

    ptutil.log(f"{CMD_NAME}: Edit Favorites command created")

    _edit_staged_favorites = [dict(f) for f in _load_favorites()]
    _edit_checkbox_map = {}
    _edit_build_version = 0

    cmd = args.command
    _build_edit_dialog_inputs(cmd.commandInputs)

    ptutil.add_handler(
        cmd.inputChanged, _edit_favorites_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(
        cmd.execute, _edit_favorites_execute, local_handlers=local_handlers
    )
    ptutil.add_handler(
        cmd.destroy, _edit_favorites_destroy, local_handlers=local_handlers
    )


def _edit_favorites_input_changed(args: adsk.core.InputChangedEventArgs):
    changed = args.input
    if not changed:
        return

    if changed.id.startswith("fav_edit_sel_"):
        _update_delete_button_enabled(args.inputs)
        return

    if changed.id != EDIT_DELETE_BTN_ID:
        return

    btn = adsk.core.BoolValueCommandInput.cast(changed)
    if not btn or not btn.value:
        return

    try:
        inputs = args.inputs
        selected_indices = []

        for checkbox_id, fav_index in _edit_checkbox_map.items():
            checkbox = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(checkbox_id)
            )
            if checkbox and checkbox.value:
                selected_indices.append(fav_index)

        if not selected_indices:
            ui.messageBox("Select one or more rows to delete.", "Edit Favorites")
            btn.value = False
            return

        selected_set = set(selected_indices)

        global _edit_staged_favorites
        _edit_staged_favorites = [
            fav for i, fav in enumerate(_edit_staged_favorites) if i not in selected_set
        ]

        # Reset the button value BEFORE rebuilding inputs; after the rebuild
        # the old btn reference points to a deleted object and can no longer
        # be written to.
        btn.value = False
        _build_edit_dialog_inputs(inputs)

    except Exception:
        ptutil.log(
            f"Favorites: edit delete failed\n{traceback.format_exc()}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        ui.messageBox(
            f"Failed to delete selected rows:\n{traceback.format_exc()}",
            "Edit Favorites",
        )


def _edit_favorites_execute(args: adsk.core.CommandEventArgs):
    """Commit staged changes only when user confirms with OK."""
    try:
        _save_favorites(_edit_staged_favorites)
        _rebuild_menu()
        ptutil.log(f"Favorites: committed {_safe_len(_edit_staged_favorites)} item(s)")
    except Exception:
        ptutil.log(
            f"Favorites: edit commit failed\n{traceback.format_exc()}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        ui.messageBox(
            f"Failed to save favorites:\n{traceback.format_exc()}",
            "Edit Favorites",
        )


def _edit_favorites_destroy(args: adsk.core.CommandEventArgs):
    """Discard staged state on close/cancel."""
    global _edit_staged_favorites, _edit_checkbox_map, _edit_build_version
    _edit_staged_favorites = []
    _edit_checkbox_map = {}
    _edit_build_version = 0


def _build_edit_dialog_inputs(inputs: adsk.core.CommandInputs):
    """Build or rebuild the edit dialog UI from staged favorites."""
    global _edit_checkbox_map, _edit_build_version

    existing_table = inputs.itemById(EDIT_TABLE_ID)
    if existing_table:
        existing_table.deleteMe()

    existing_count = inputs.itemById(EDIT_COUNT_ID)
    if existing_count:
        existing_count.deleteMe()

    existing_delete = inputs.itemById(EDIT_DELETE_BTN_ID)
    if existing_delete:
        existing_delete.deleteMe()

    _edit_checkbox_map = {}
    _edit_build_version += 1

    count_label = inputs.addTextBoxCommandInput(
        EDIT_COUNT_ID,
        "",
        f"{_safe_len(_edit_staged_favorites)} favorite(s)",
        1,
        True,
    )
    count_label.isFullWidth = True

    table = inputs.addTableCommandInput(
        EDIT_TABLE_ID,
        "Favorites",
        3,
        "1:3:6",
    )
    table.minimumVisibleRows = 3
    table.maximumVisibleRows = 12
    table.columnSpacing = 2

    build_tag = str(_edit_build_version)
    for i, fav in enumerate(_edit_staged_favorites):
        checkbox_id = f"fav_edit_sel_{build_tag}_{i}"
        name_id = f"fav_edit_name_{build_tag}_{i}"
        location_id = f"fav_edit_loc_{build_tag}_{i}"

        name_text = _get_favorite_name(fav)
        location_text = fav.get("display", "Unknown Location")

        sel_input = inputs.addBoolValueInput(checkbox_id, "", True, "", False)
        name_input = inputs.addTextBoxCommandInput(name_id, "", name_text, 1, True)
        location_input = inputs.addTextBoxCommandInput(
            location_id, "", location_text, 1, True
        )

        table.addCommandInput(sel_input, i, 0)
        table.addCommandInput(name_input, i, 1)
        table.addCommandInput(location_input, i, 2)

        _edit_checkbox_map[checkbox_id] = i

    delete_btn = inputs.addBoolValueInput(
        EDIT_DELETE_BTN_ID,
        "Delete Selected",
        False,
        "",
        False,
    )
    delete_btn.isFullWidth = True
    delete_btn.isEnabled = False


def _update_delete_button_enabled(inputs: adsk.core.CommandInputs):
    delete_btn = adsk.core.BoolValueCommandInput.cast(
        inputs.itemById(EDIT_DELETE_BTN_ID)
    )
    if not delete_btn:
        return

    has_selected = False
    for checkbox_id in _edit_checkbox_map:
        checkbox = adsk.core.BoolValueCommandInput.cast(inputs.itemById(checkbox_id))
        if checkbox and checkbox.value:
            has_selected = True
            break

    delete_btn.isEnabled = has_selected


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _get_folder_lineage(folder) -> str:
    """Walk the folder tree upward and return a display path like 'Project > Folder > Sub'."""
    parts = []
    current = folder
    depth = 0
    while current is not None and depth < 10:
        try:
            parts.insert(0, current.name)
            current = current.parentFolder
        except Exception:
            break
        depth += 1
    return " > ".join(parts) if parts else "Unknown Location"


def _get_document_name(data_file, doc) -> str:
    name = getattr(data_file, "name", "") if data_file else ""
    if name:
        return str(name)
    if doc and getattr(doc, "name", ""):
        return str(doc.name)
    return "Unknown Document"


def _get_favorite_name(fav: dict) -> str:
    name = fav.get("name", "")
    if name:
        return name
    display = fav.get("display", "")
    if not display:
        return "Unknown Document"
    if " > " in display:
        return display.split(" > ")[-1]
    return display


def _safe_len(items) -> int:
    try:
        return len(items)
    except Exception:
        return 0
