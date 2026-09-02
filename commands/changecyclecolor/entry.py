# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Change Cycle Color.

Selection-driven command that writes Fusion's per-component
``Component.componentColor`` (the value read by Fusion's "Color Cycling
Toggle") on every selected component. Operates purely on
``componentColor`` — does not touch ``Appearance`` at all.

Available from the browser/canvas context menu when a Component or
Occurrence is selected (including the root component).

Swatches are sourced from Fusion's own ``ColorCycleTable`` in
``RiverRubicon.xml`` (located dynamically inside the running install) and
sorted into a rainbow. The "Custom color..." button opens the OS-native
color picker via ``tkinter.colorchooser`` and applies the chosen color
directly — there is no intermediate HTML palette.

Last-used color is held in a module-level variable for the session only;
it does not persist across Fusion restarts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from typing import List, Optional

import adsk.core
import adsk.fusion

from ... import config, settings_store
from ...lib import ptAddInUtils as ptutil
from . import swatches as swatch_png
from .colors import (
    Color,
    Swatch,
    hex_to_rgb,
    load_color_cycle,
    rgb_to_hex,
    sort_rainbow,
)
from .fusion_install import (
    find_bundled_python,
    find_environment_xml,
    find_river_rubicon_xml,
    lighting_environment_dirs,
)

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Change Cycle Color"
CMD_ID = "PTAT_changecyclecolor"
CMD_Description = (
    "Set the per-component color (used by Fusion's Color Cycling Toggle) "
    "for every selected component."
)

# When the command is invoked from the linear marking menu, this is the
# anchor we position our menu entry after.
LINEAR_MENU_AFTER_ID = "CycleComponentColorCmd"

SWATCH_CACHE_DIR = os.path.join(config.CACHE_DIR, "changecyclecolor", "swatches")
COLOR_PICKER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_color_picker_subprocess.py"
)
CUSTOM_BTN_ICON_DIR = os.path.join(config.CACHE_DIR, "changecyclecolor", "custom_btn")
# 4-quadrant rainbow used for the Custom-color button icon.
_CUSTOM_BTN_COLORS = (
    (220, 50, 50),  # top-left  red
    (50, 200, 50),  # top-right green
    (240, 200, 60),  # bot-left  yellow
    (60, 110, 220),  # bot-right blue
)

# Input IDs
INPUT_PREVIEW = "ccc_preview"
INPUT_CUSTOM_BTN = "ccc_custom"
INPUT_INFO = "ccc_info"

SWATCH_ROW_COUNT = 4
ROW_ID_PREFIX = "ccc_row"
ROW_IDS = tuple(f"{ROW_ID_PREFIX}{i}" for i in range(SWATCH_ROW_COUNT))

local_handlers: list = []

# Cached at first command_created — XML doesn't change during a session.
_swatches: List[Swatch] = []
# Environment the cached _swatches were loaded from. The palette differs per
# lighting environment, so a switch mid-session has to invalidate the cache;
# None means nothing is cached yet.
_swatches_env: Optional[str] = None

# Selection state: hex string of the chosen color (uppercase, no '#').
_selected_hex: Optional[str] = None

# Component targets captured at command_created time; iterated in execute.
_pending_targets: List[adsk.fusion.Component] = []

# Tells command_execute there is nothing for it to apply. Set by two paths:
# the Custom-color flow, which has already written the color via the native
# picker and calls cmd.doExecute(True) only to dismiss the swatch dialog; and
# _abort_before_dialog, where Fusion auto-executes a command that never built
# a dialog. Without it, the first would double-apply and the second would
# apply a stale swatch to stale targets.
_skip_normal_execute: bool = False

# Captured during command_created so the Custom-color flow can call
# doExecute() to dismiss the swatch dialog after the native picker returns.
_active_command: Optional[adsk.core.Command] = None

# Error to display once the dialog has closed (set in execute, shown in destroy).
_pending_error_message: Optional[str] = None

# Reference to the markingMenuDisplaying handler so stop() can detach it.
_marking_menu_handler = None


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------


def start():
    global _marking_menu_handler

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    # Register the browser/canvas context menu hook. We add the command to
    # the linear (right-click) menu whenever the right-clicked entity is a
    # Component or Occurrence — that includes the root component.
    _marking_menu_handler = ptutil.add_handler(
        ui.markingMenuDisplaying, _on_marking_menu_displaying
    )

    ptutil.log(f"{CMD_NAME} command started")


def stop():
    global _marking_menu_handler

    try:
        if _marking_menu_handler is not None:
            try:
                ui.markingMenuDisplaying.remove(_marking_menu_handler)
            except Exception as exc:
                ptutil.log(f"{CMD_NAME}: marking menu unsubscribe failed: {exc}")
            _marking_menu_handler = None

        command_definition = ui.commandDefinitions.itemById(CMD_ID)
        if command_definition:
            command_definition.deleteMe()

        ptutil.log(f"{CMD_NAME} command stopped")
    except Exception as exc:
        ptutil.log(f"Error stopping {CMD_NAME}: {exc}")


# ---------------------------------------------------------------------------
# Browser / canvas context menu hook
# ---------------------------------------------------------------------------


def _on_marking_menu_displaying(args: adsk.core.MarkingMenuEventArgs):
    """Add the command to the linear marking menu (right-click context menu)
    when at least one Component or Occurrence is selected. Filters by entity
    type so the command only appears in component contexts (browser nodes,
    canvas component-mode picks) — never on bodies, faces, edges, sketches.
    """
    try:
        if not settings_store.command_setting(
            "changecyclecolor", "show_in_context_menu", True
        ):
            return
        selected = list(args.selectedEntities) if args.selectedEntities else []
        if not selected:
            return
        if not any(_entity_to_component(e) is not None for e in selected):
            return

        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def is None:
            ptutil.log(f"{CMD_NAME}: command definition {CMD_ID!r} not found")
            return

        menu = args.linearMarkingMenu
        if menu is None:
            return
        # Insert AFTER the built-in Cycle Component Color command. If that
        # anchor isn't in the current menu, Fusion silently appends to the
        # end — fine fallback.
        menu.controls.addCommand(cmd_def, LINEAR_MENU_AFTER_ID, False)
    except Exception as exc:
        # Never let our handler crash the menu — Fusion would silently drop
        # the rest of the menu's controls if we raise.
        ptutil.log(f"{CMD_NAME}: marking menu handler error: {exc}")


def _entity_to_component(entity) -> Optional[adsk.fusion.Component]:
    """Return the Component for *entity* if it is a Component or Occurrence;
    None otherwise. Lets the menu filter and the selection collector share
    a single rule for what "a component target" means.
    """
    if entity is None:
        return None
    occ = adsk.fusion.Occurrence.cast(entity)
    if occ is not None:
        return occ.component
    comp = adsk.fusion.Component.cast(entity)
    if comp is not None:
        return comp
    return None


def _collect_selected_components() -> List[adsk.fusion.Component]:
    """Walk ``ui.activeSelections`` and return the unique Components reached
    via Component or Occurrence selections. Order preserved; duplicates
    (multiple instances of the same component definition) collapsed.
    """
    out: List[adsk.fusion.Component] = []
    seen_ids = set()
    sel = ui.activeSelections
    for i in range(sel.count):
        try:
            entity = sel.item(i).entity
        except Exception:
            continue
        comp = _entity_to_component(entity)
        if comp is None:
            continue
        # Component.id (entity token) is unique per component definition.
        token = getattr(comp, "id", None) or comp.name
        if token in seen_ids:
            continue
        seen_ids.add(token)
        out.append(comp)
    return out


# ---------------------------------------------------------------------------
# Palette source — the active lighting environment
# ---------------------------------------------------------------------------


def _active_environment_name() -> Optional[str]:
    """Folder name of the lighting environment Fusion is rendering with, or
    ``None`` if it cannot be determined.

    ``Application.lightingEnvironment`` returns an
    ``adsk.core.LightingEnvironments`` value, and each of its members names an
    environment folder that ships its own ColorCycleTable.
    """
    try:
        value = app.lightingEnvironment
        name = lighting_environment_dirs(adsk.core.LightingEnvironments).get(value)
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: could not read lightingEnvironment: {exc!r}")
        return None
    if name is None:
        ptutil.log(f"{CMD_NAME}: unmapped lightingEnvironment value {value!r}")
    return name


def _load_palette(env_name: Optional[str]) -> List[Swatch]:
    """Load the ColorCycleTable for *env_name*, falling back to RiverRubicon.

    The fallback keeps the dialog populated when the environment cannot be
    identified or ships no table of its own. It is a guess at that point — the
    palette shown may not be the one Fusion cycles through — so it is logged
    rather than silently substituted.
    """
    if env_name:
        xml_path = find_environment_xml(env_name)
        if xml_path:
            loaded = load_color_cycle(xml_path)
            if loaded:
                ptutil.log(
                    f"{CMD_NAME}: palette from {env_name} ({len(loaded)} colors)"
                )
                return loaded
            ptutil.log(f"{CMD_NAME}: {env_name} has no usable ColorCycleTable")
        else:
            ptutil.log(f"{CMD_NAME}: no environment XML for {env_name}")

    fallback = find_river_rubicon_xml()
    loaded = load_color_cycle(fallback) if fallback else []
    ptutil.log(
        f"{CMD_NAME}: falling back to RiverRubicon palette ({len(loaded)} colors)"
    )
    return loaded


# ---------------------------------------------------------------------------
# Command created — validate selection, build the dialog
# ---------------------------------------------------------------------------


def _abort_before_dialog(message: str) -> None:
    """Bail out of ``command_created`` without building a dialog.

    Never call ``Command.doExecute`` from ``command_created``. That callback
    runs inside Fusion's ``CommandDefinition::createCommand``, so doExecute
    re-enters the command manager on a half-constructed command and segfaults
    Fusion — observed 2026-09-02 running the command with nothing selected,
    with the faulting frame inside
    ``Xl::APICommandDefinitionImpl::doOnCreateCommand``.

    Creating no inputs is enough to end the command: ``Command.isAutoExecute``
    defaults to true, so Fusion executes and terminates it on its own. The
    message is deferred to ``command_destroy`` instead of shown here, keeping
    modal UI out of the create callback as well.
    """
    global _pending_targets, _skip_normal_execute, _pending_error_message
    # Both of these outlive a single invocation. Without clearing the targets,
    # the auto-execute below would re-apply the previous run's color to the
    # previous run's components.
    _pending_targets = []
    _skip_normal_execute = True
    _pending_error_message = message
    ptutil.log(f"{CMD_NAME}: aborted before building the dialog — {message}")


def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        _abort_before_dialog("Open a Fusion design before running Change Cycle Color.")
        return

    targets = _collect_selected_components()
    if not targets:
        _abort_before_dialog(
            "Select one or more components in the browser (or right-click a "
            "component node and pick Change Cycle Color) before running "
            "this command."
        )
        return

    global _swatches, _swatches_env, _active_command, _pending_targets
    _pending_targets = targets

    env = _active_environment_name()
    if not _swatches or _swatches_env != env:
        _swatches = sort_rainbow(_load_palette(env))
        _swatches_env = env
        if _swatches:
            try:
                swatch_png.ensure_all(SWATCH_CACHE_DIR, _swatches)
            except Exception as exc:
                ptutil.log(f"{CMD_NAME}: swatch icon generation failed: {exc}")

    cmd = args.command
    cmd.okButtonText = "Apply"
    _active_command = cmd
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        INPUT_INFO,
        "Targets",
        _describe_targets_html(targets),
        max(1, min(3, len(targets))),
        True,
    )

    if not _swatches:
        warn = inputs.addTextBoxCommandInput(
            "ccc_warn",
            "",
            "<span style='color:#b06000'><b>⚠ Built-in palette unavailable.</b></span> "
            "RiverRubicon.xml could not be located in the running Fusion install. "
            "Use <b>Custom color…</b> to pick a hex color.",
            3,
            True,
        )
        warn.isFullWidth = True
    else:
        for idx, slice_ in enumerate(_split_evenly(_swatches, SWATCH_ROW_COUNT)):
            label = "Palette" if idx == 0 else ""
            _build_swatch_row(inputs, ROW_IDS[idx], label, slice_)

    # Button-styled (isCheckBox=False) BoolValueInput — requires an icon
    # folder, so we generate a 4-quadrant rainbow on first use. Click acts
    # as a momentary trigger: we reset value to False after handling.
    icon_folder = swatch_png.ensure_quadrant_icon(
        CUSTOM_BTN_ICON_DIR, _CUSTOM_BTN_COLORS
    )
    custom_btn = inputs.addBoolValueInput(
        INPUT_CUSTOM_BTN, "Custom color…", False, icon_folder, False
    )
    custom_btn.tooltip = "Open the OS-native color picker."

    preview = inputs.addTextBoxCommandInput(
        INPUT_PREVIEW,
        "Selected",
        _preview_html(_selected_hex),
        2,
        True,
    )
    preview.isFullWidth = True

    ptutil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def _build_swatch_row(
    inputs: adsk.core.CommandInputs,
    input_id: str,
    label: str,
    swatches: List[Swatch],
) -> None:
    row = inputs.addButtonRowCommandInput(input_id, label, False)
    for name, rgb in swatches:
        folder = os.path.join(SWATCH_CACHE_DIR, rgb_to_hex(rgb).lstrip("#"))
        is_sel = (
            _selected_hex is not None and rgb_to_hex(rgb).lstrip("#") == _selected_hex
        )
        row.listItems.add(name, is_sel, folder)


def _split_evenly(items: List[Swatch], n_rows: int) -> List[List[Swatch]]:
    n_rows = max(1, n_rows)
    base, extra = divmod(len(items), n_rows)
    out: List[List[Swatch]] = []
    pos = 0
    for i in range(n_rows):
        size = base + (1 if i < extra else 0)
        out.append(items[pos : pos + size])
        pos += size
    return [chunk for chunk in out if chunk]


def _describe_targets_html(targets: List[adsk.fusion.Component]) -> str:
    if not targets:
        return "<i>No components selected.</i>"
    if len(targets) == 1:
        return f"<b>{_escape_html(targets[0].name)}</b>"
    names = ", ".join(_escape_html(t.name) for t in targets[:6])
    if len(targets) > 6:
        names += f", … (+{len(targets) - 6} more)"
    return f"<b>{len(targets)} components</b> — {names}"


def _preview_html(hex_no_hash: Optional[str]) -> str:
    if not hex_no_hash:
        return "<i>No color selected — pick a swatch or click Custom color…</i>"
    name = _name_for_hex(hex_no_hash) or "Custom"
    chip = (
        f"<span style='display:inline-block;width:14px;height:14px;"
        f"background:#{hex_no_hash};border:1px solid #888;'></span>"
    )
    return f"{chip} &nbsp;<b>{_escape_html(name)}</b> &nbsp;#{hex_no_hash}"


def _name_for_hex(hex_no_hash: str) -> Optional[str]:
    target = hex_no_hash.upper()
    for name, rgb in _swatches:
        if rgb_to_hex(rgb).lstrip("#") == target:
            return name
    return None


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Input changed — coordinate single-selection across the swatch rows, drive
# the preview, and react to the Custom Color button.
# ---------------------------------------------------------------------------


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    global _selected_hex

    cmd_inputs = args.inputs
    changed = args.input

    if changed.id == INPUT_CUSTOM_BTN:
        custom = adsk.core.BoolValueCommandInput.cast(changed)
        if custom and custom.value:
            _enter_custom_color_flow()
            custom.value = False
        return

    if changed.id in ROW_IDS:
        row = adsk.core.ButtonRowCommandInput.cast(changed)
        if not row:
            return
        picked_name = _selected_listitem_name(row)
        if not picked_name:
            return
        picked = next(((n, rgb) for n, rgb in _swatches if n == picked_name), None)
        if not picked:
            return
        _selected_hex = rgb_to_hex(picked[1]).lstrip("#")
        for other_id in ROW_IDS:
            if other_id == changed.id:
                continue
            other = adsk.core.ButtonRowCommandInput.cast(cmd_inputs.itemById(other_id))
            if not other:
                continue
            for i in range(other.listItems.count):
                item = other.listItems.item(i)
                if item.isSelected:
                    item.isSelected = False
        _refresh_preview(cmd_inputs)


def _selected_listitem_name(row: adsk.core.ButtonRowCommandInput) -> Optional[str]:
    for i in range(row.listItems.count):
        item = row.listItems.item(i)
        if item.isSelected:
            return item.name
    return None


def _refresh_preview(cmd_inputs: adsk.core.CommandInputs) -> None:
    preview = adsk.core.TextBoxCommandInput.cast(cmd_inputs.itemById(INPUT_PREVIEW))
    if preview:
        preview.formattedText = _preview_html(_selected_hex)


# ---------------------------------------------------------------------------
# Custom-color flow — native OS picker via tkinter.colorchooser
# ---------------------------------------------------------------------------


def _enter_custom_color_flow() -> None:
    """Open the OS-native color picker. On confirm: apply the chosen color
    to the captured targets and dismiss the swatch dialog. On cancel: do
    nothing (the swatch dialog stays open so the user can pick a swatch
    instead).
    """
    global _skip_normal_execute, _selected_hex

    ptutil.log(
        f"{CMD_NAME}: custom-color flow entered, "
        f"targets={[t.name for t in _pending_targets]}"
    )

    if not _pending_targets:
        ptutil.log(f"{CMD_NAME}: no targets — aborting custom-color flow")
        return

    initial = _selected_hex or "808080"
    rgb = _pick_color_native(initial)
    if rgb is None:
        ptutil.log(f"{CMD_NAME}: native picker returned None (cancel/error)")
        return

    succeeded = []
    failed = []
    for comp in _pending_targets:
        if _set_component_color(comp, rgb):
            succeeded.append(comp.name)
        else:
            failed.append(comp.name)
    ptutil.log(
        f"{CMD_NAME}: custom-color apply {rgb_to_hex(rgb)} — "
        f"succeeded={len(succeeded)} {succeeded}, "
        f"failed={len(failed)} {failed}"
    )

    if not succeeded:
        ui.messageBox(
            "componentColor could not be set on any target. The components "
            "may be from a referenced/locked design.",
            CMD_NAME,
            0,
            2,
        )
        return

    # Remember the picked color so the swatch preview seeds correctly on the
    # next invocation.
    _selected_hex = rgb_to_hex(rgb).lstrip("#")

    # Dismiss the swatch dialog. doExecute fires command_execute which we
    # skip via _skip_normal_execute so we don't double-apply.
    _skip_normal_execute = True
    cmd = _active_command
    if cmd is not None:
        try:
            cmd.doExecute(True)
        except Exception as exc:
            ptutil.log(f"{CMD_NAME}: failed to dismiss swatch dialog: {exc}")
            _skip_normal_execute = False


def _pick_color_native(initial_hex_no_hash: str) -> Optional[Color]:
    """Dispatch to the platform-appropriate native color picker. Returns an
    RGB tuple or None on cancel / error.

    On macOS 15+ (Sequoia) Gatekeeper blocks Fusion from re-spawning its
    bundled ``Python.app`` GUI helper (posix_spawn: Undefined error: 0), so
    the subprocess-Python path doesn't work. ``osascript`` is a system-
    signed binary at a fixed path so Gatekeeper always allows it — and
    AppleScript's ``choose color`` uses NSColorPanel under the hood.
    """
    if sys.platform == "darwin":
        return _pick_color_macos(initial_hex_no_hash)
    return _pick_color_subprocess_python(initial_hex_no_hash)


def _pick_color_macos(initial_hex_no_hash: str) -> Optional[Color]:
    """macOS: invoke AppleScript's ``choose color`` via /usr/bin/osascript."""
    ptutil.log(f"{CMD_NAME}: macOS osascript picker, initial=#{initial_hex_no_hash}")

    rgb = hex_to_rgb(initial_hex_no_hash) or (128, 128, 128)
    # AppleScript's color components are 0..65535, not 0..255.
    r16, g16, b16 = (int(round(c * 65535 / 255)) for c in rgb)
    script = (
        f"set chosenColor to choose color default color "
        f"{{{r16}, {g16}, {b16}}}\n"
        f'return ((item 1 of chosenColor) as text) & "," & '
        f'((item 2 of chosenColor) as text) & "," & '
        f"((item 3 of chosenColor) as text)"
    )

    try:
        proc = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        ptutil.log(f"{CMD_NAME}: osascript timed out")
        return None
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: osascript launch failed: {exc!r}")
        ptutil.log(traceback.format_exc())
        return None

    ptutil.log(
        f"{CMD_NAME}: osascript rc={proc.returncode}, "
        f"stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    )
    # rc=1 with no stdout means the user clicked Cancel — that's not an error.
    if proc.returncode != 0 or not proc.stdout.strip():
        return None

    parts = [p.strip() for p in proc.stdout.strip().split(",")]
    if len(parts) != 3:
        return None
    try:
        r16, g16, b16 = (int(p) for p in parts)
    except ValueError:
        return None

    return (
        int(round(r16 * 255 / 65535)),
        int(round(g16 * 255 / 65535)),
        int(round(b16 * 255 / 65535)),
    )


def _pick_color_subprocess_python(initial_hex_no_hash: str) -> Optional[Color]:
    """Non-macOS: spawn Fusion's bundled Python in a fresh process and let
    it run tkinter.colorchooser. ``tk.Tk()`` cannot run inside Fusion's
    own process (Cocoa/Qt run-loop conflict on macOS, similar issues
    elsewhere) — the subprocess gives Tk its own clean run loop.
    """
    ptutil.log(f"{CMD_NAME}: subprocess-Python picker, initial=#{initial_hex_no_hash}")

    py = find_bundled_python()
    if not py:
        ptutil.log(f"{CMD_NAME}: could not locate Python interpreter")
        ui.messageBox(
            "Could not locate the Python interpreter for the color picker.",
            CMD_NAME,
            0,
            2,
        )
        return None
    if not os.path.isfile(COLOR_PICKER_SCRIPT):
        ui.messageBox(
            "Color picker helper script is missing — reinstall the add-in.",
            CMD_NAME,
            0,
            2,
        )
        return None

    # Windows: keep the console window hidden. pythonw.exe is preferred and
    # has none, but python.exe is the fallback and would flash one up behind
    # the picker dialog. The flag does not exist on POSIX.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            [py, COLOR_PICKER_SCRIPT, "#" + initial_hex_no_hash],
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=creationflags,
        )
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: picker subprocess failed: {exc!r}")
        ui.messageBox(
            f"The color picker could not be started.\n\n{exc}",
            CMD_NAME,
            0,
            2,
        )
        return None

    ptutil.log(
        f"{CMD_NAME}: picker rc={proc.returncode}, "
        f"stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    )
    # A non-zero exit means the helper could not show a dialog at all — most
    # likely tkinter is missing from this Fusion build's Python. Report it:
    # returning None here is indistinguishable from a cancel, so staying
    # silent would leave the Custom color... button looking simply dead.
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        ui.messageBox(
            f"The color picker could not be opened.\n\n{detail}",
            CMD_NAME,
            0,
            2,
        )
        return None
    # Exit code 0 with no output is the user cancelling — stay silent.
    hex_str = (proc.stdout or "").strip()
    if not hex_str:
        return None
    return hex_to_rgb(hex_str)


# ---------------------------------------------------------------------------
# Execute — write componentColor on every selected component
# ---------------------------------------------------------------------------


def command_execute(args: adsk.core.CommandEventArgs):
    ptutil.log(f"{CMD_NAME} execute: start")
    global _pending_error_message, _skip_normal_execute

    # Either the Custom-color flow already wrote componentColor and called
    # doExecute(True) purely to dismiss the dialog, or command_created aborted
    # before building one and Fusion auto-executed. Both mean there is nothing
    # to apply; going on would double-apply or apply a stale swatch.
    if _skip_normal_execute:
        _skip_normal_execute = False
        ptutil.log(f"{CMD_NAME} execute: skipped (nothing to apply)")
        return

    deferred_error = None

    try:
        if _selected_hex is None:
            deferred_error = "No color was selected."
            return

        rgb = hex_to_rgb(_selected_hex)
        if rgb is None:
            deferred_error = f"Selected color #{_selected_hex} is not a valid hex."
            return

        if not _pending_targets:
            deferred_error = (
                "No components were captured at command-open time. Select a "
                "component first and re-run."
            )
            return

        succeeded = []
        failed = []
        for comp in _pending_targets:
            if _set_component_color(comp, rgb):
                succeeded.append(comp.name)
            else:
                failed.append(comp.name)

        ptutil.log(
            f"{CMD_NAME}: applied {rgb_to_hex(rgb)} — "
            f"succeeded={len(succeeded)} {succeeded}, "
            f"failed={len(failed)} {failed}"
        )

        if not succeeded:
            deferred_error = (
                "componentColor could not be set on any selected component. "
                "Component(s) may be from a referenced/locked design, or this "
                "Fusion build does not expose Component.componentColor."
            )
        elif failed:
            deferred_error = (
                f"componentColor was set on {len(succeeded)} component(s), "
                f"but failed on: {', '.join(failed)}."
            )

    except Exception:
        ptutil.log(f"{CMD_NAME} execute failure:\n{traceback.format_exc()}")
        deferred_error = f"Failed:\n{traceback.format_exc()}"

    if deferred_error:
        _pending_error_message = deferred_error

    ptutil.log(f"{CMD_NAME} execute: return (dialog will close)")


def _set_component_color(target: adsk.fusion.Component, rgb: Color) -> bool:
    """Stamp ``Component.componentColor`` to *rgb*. Returns True on success.

    This is the value Fusion's Color Cycling Toggle reads to color
    components. Older Fusion API releases may not expose the property —
    we treat absence as a non-fatal False.
    """
    if not hasattr(target, "componentColor"):
        return False
    r, g, b = rgb
    try:
        target.componentColor = adsk.core.Color.create(r, g, b, 255)
        return True
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: componentColor set failed on {target.name!r}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Destroy — surface deferred errors, clear handlers
# ---------------------------------------------------------------------------


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _pending_error_message, _active_command, _pending_targets
    global _skip_normal_execute
    local_handlers = []
    _active_command = None
    _pending_targets = []
    # Bound the skip flag to this invocation. command_execute normally consumes
    # it, but only if it runs; destroy always does. A flag left set would make
    # the next invocation accept a swatch and then apply nothing.
    _skip_normal_execute = False
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    if _pending_error_message:
        msg = _pending_error_message
        _pending_error_message = None
        ui.messageBox(
            msg,
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
