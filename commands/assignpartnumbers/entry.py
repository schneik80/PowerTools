# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Assign Part Numbers — picks a scheme, reserves sequential numbers from
the hub-wide Pn-Cache, and stamps ``component.partNumber`` on the root
component and (if present) each local occurrence.

The dialog adapts:

    * No local components -> a single scheme dropdown + one preview line.
    * Local components    -> a per-row TableCommandInput so each component
                             (root + each local) gets its own scheme + preview.
"""

from __future__ import annotations

import os
import traceback
from typing import Dict, List, Optional

import adsk.core
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from .. import _ui_bootstrap
from ..partnumber_shared import hub_fs, pn_cache, schemes
from ..partnumber_shared import intent as intent_mod

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Assign Part Numbers"
CMD_ID = "PTND_assignPartNumbers"
CMD_Description = (
    "Assign a controlled part number to the active design and its local components "
    "using hub-shared sequential schemes (PRT / ASY / WLD / COT / TOL)."
)
IS_PROMOTED = True

WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Input IDs
INPUT_SCHEME_SIMPLE = "ap_scheme_simple"
INPUT_PREVIEW_SIMPLE = "ap_preview_simple"
INPUT_TABLE = "ap_table"
INPUT_INFO = "ap_info"

# Sentinel label used in every scheme dropdown for "don't assign this row".
SKIP_LABEL = "(skip)"

# Dialog state — rebuilt each time command_created fires.
_targets: List[intent_mod.Target] = []
_mode_is_table: bool = False
# Per-row input refs captured at build-time. Keys: row index (0-based).
_row_scheme_inputs: Dict[int, "adsk.core.DropDownCommandInput"] = {}
_row_preview_inputs: Dict[int, "adsk.core.TextBoxCommandInput"] = {}
# Snapshot of hub Pn-Cache counters, loaded at command_created and used to
# show accurate "next number" previews before Assign is clicked. Kept
# read-only in the dialog; the actual reserved numbers come from a fresh
# download at commit time (optimistic retry handles any drift).
_baseline_counters: Dict[str, int] = {}
_baseline_loaded: bool = False
# Error to display once the dialog has closed (set in execute, shown in destroy).
_pending_error_message: Optional[str] = None

# Holds references to event handlers so they aren't garbage-collected.
local_handlers: list = []


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    panel = _ui_bootstrap.get_power_tools_panel()
    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED

    ptutil.log(f"{CMD_NAME} command started")


def stop():
    try:
        panel = _ui_bootstrap.get_power_tools_panel()
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()
        if command_definition:
            command_definition.deleteMe()

        ptutil.log(f"{CMD_NAME} command stopped")
    except Exception as exc:
        ptutil.log(f"Error stopping {CMD_NAME}: {exc}")


# ---------------------------------------------------------------------------
# Command created — validate + build dialog
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs):
    global _targets, _mode_is_table

    ptutil.log(f"{CMD_NAME} Command Created Event")

    # Reset per-dialog state.
    _row_scheme_inputs.clear()
    _row_preview_inputs.clear()
    _baseline_counters.clear()
    global _baseline_loaded
    _baseline_loaded = False

    # --- Pre-validation ------------------------------------------------------
    if not ptutil.isSaved():
        args.command.doExecute(True)
        return

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        ui.messageBox(
            "Assign Part Numbers requires an active Fusion 3D design.",
            CMD_NAME,
            0,
            2,
        )
        args.command.doExecute(True)
        return

    _targets = intent_mod.iter_targets(design)
    _mode_is_table = len(_targets) > 1

    # NOTE: An earlier version of this command called
    # intent_mod.targets_missing_model_id() here as a synchronous pre-flight
    # to detect components lacking MFGDM metadata. That access (which reads
    # component.dataComponent.mfgdmModelId) is only safe inside an
    # MFGDMDataReady event callback per Autodesk's sample code. Calling it
    # from command_created, followed by ui.messageBox() and
    # args.command.doExecute(True), was observed to crash Fusion on dismiss.
    # The readback verification in command_execute (below) is our real
    # safety net — it catches the silent-set failure mode at the moment it
    # matters, from a regular try/except scope where a crash can't take
    # down the app.

    # Load current hub Pn-Cache counters so previews show the real
    # next-in-scheme number rather than always starting at 000001.
    _load_baseline_counters()

    # --- Build dialog --------------------------------------------------------
    cmd = args.command
    cmd.isOKButtonVisible = True
    cmd.okButtonText = "Assign"
    inputs = cmd.commandInputs

    intent_value = intent_mod.intent_of_design(design)
    intent_label = _intent_label(intent_value)
    inputs.addTextBoxCommandInput(
        INPUT_INFO,
        "Design intent",
        f"<b>{intent_label}</b>",
        1,
        True,
    )

    if not _mode_is_table:
        _build_simple_inputs(inputs, _targets[0])
    else:
        _build_table_inputs(inputs, _targets)

    # Compute initial previews.
    _recompute_previews(inputs)

    ptutil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    ptutil.add_handler(
        cmd.validateInputs, command_validate_inputs, local_handlers=local_handlers
    )
    ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def _load_baseline_counters() -> None:
    """Populate ``_baseline_counters`` from the hub Pn-Cache snapshot.

    Runs once per dialog open; errors are logged and the counters are left
    empty (so previews fall back to starting at 1). Concurrency is still
    handled correctly at Assign time via the fresh download + optimistic
    retry inside ``pn_cache.commit_assignments``.
    """
    global _baseline_loaded
    progress = ui.progressBar
    progress.showBusy(f"{CMD_NAME} — loading Pn-Cache counters...")
    adsk.doEvents()
    try:
        project = hub_fs.find_assets_project(app)
        folder = hub_fs.find_or_create_pn_cache_folder(project)
        snapshot = pn_cache.download_snapshot(folder, pn_cache.default_tmp_dir())
        _baseline_counters.update(snapshot.counters)
        _baseline_loaded = True
        ptutil.log(
            f"{CMD_NAME}: loaded baseline counters "
            f"{dict(_baseline_counters)} from cache v{snapshot.source_version_number}"
        )
    except Exception as exc:
        _baseline_loaded = False
        ptutil.log(
            f"{CMD_NAME}: could not load Pn-Cache counters ({exc}); "
            f"previews will start at 1."
        )
    finally:
        progress.hide()


def _intent_label(intent_value: int) -> str:
    return {
        schemes.INTENT_PART: "Part Intent",
        schemes.INTENT_ASSEMBLY: "Assembly Palette",
        schemes.INTENT_HYBRID: "Hybrid Intent",
    }.get(intent_value, "Unknown Intent")


# ---------------------------------------------------------------------------
# Dialog builders
# ---------------------------------------------------------------------------


def _build_simple_inputs(
    inputs: adsk.core.CommandInputs, target: intent_mod.Target
) -> None:
    """One scheme dropdown + one preview field (root only, no local comps).

    When the target already has a user-assigned part number, an inline
    warning note is shown so the user has full context before clicking
    Assign. No modal confirmation is needed on execute.
    """
    inputs.addTextBoxCommandInput(
        "ap_root_label",
        "Component",
        f"<b>{_escape_html(target.label)}</b>",
        1,
        True,
    )
    if target.current_pn:
        inputs.addTextBoxCommandInput(
            "ap_root_current",
            "Current P/N",
            _escape_html(target.current_pn),
            1,
            True,
        )
        note = inputs.addTextBoxCommandInput(
            "ap_overwrite_note",
            "",
            (
                "<span style='color:#b06000'><b>⚠ This component already has a "
                "part number.</b></span> Selecting a scheme below and clicking "
                f"<b>Assign</b> will replace <b>{_escape_html(target.current_pn)}</b>."
            ),
            4,
            True,
        )
        note.isFullWidth = True

    dropdown = inputs.addDropDownCommandInput(
        INPUT_SCHEME_SIMPLE,
        "Scheme",
        adsk.core.DropDownStyles.TextListDropDownStyle,
    )
    allowed = schemes.prefixes_for_intent(target.intent_value)
    dropdown.listItems.add(SKIP_LABEL, True)
    for prefix in allowed:
        dropdown.listItems.add(schemes.SCHEME_LABEL[prefix], False)

    preview = inputs.addStringValueInput(INPUT_PREVIEW_SIMPLE, "Preview", "")
    preview.isReadOnly = True


def _build_table_inputs(
    inputs: adsk.core.CommandInputs, targets: List[intent_mod.Target]
) -> None:
    """Per-component table: Component | Scheme | Preview.

    Mirrors the pattern used in PowerTools-Assembly's `refrences` command:
    the table lives inside a GroupCommandInput and all row cells are
    created on the group's ``children`` collection (not the outer inputs).
    The same TextBox-for-display, DropDown-for-choice recipe that
    `refrences` and `globalParameters` both use successfully.

    When any target already has a user-assigned part number, an inline
    warning note is shown above the group listing the affected components.
    No modal confirmation is needed on execute.
    """
    ptutil.log(
        f"{CMD_NAME}: building table with {len(targets)} target(s): "
        + ", ".join(t.label for t in targets)
    )

    with_existing = [t for t in targets if t.current_pn]
    if with_existing:
        count = len(with_existing)
        plural = count != 1
        affected = ", ".join(
            f"<b>{_escape_html(t.label)}</b> ({_escape_html(t.current_pn)})"
            for t in with_existing
        )
        note = inputs.addTextBoxCommandInput(
            "ap_overwrite_note",
            "",
            (
                f"<span style='color:#b06000'><b>⚠ {count} component"
                f"{'s' if plural else ''} already "
                f"{'have' if plural else 'has'} a part number.</b></span> "
                f"Assigning a scheme to {'any of them' if plural else 'it'} "
                "below will replace the existing value. Leave a row at "
                "<b>(skip)</b> to preserve its current number. "
                f"Affected: {affected}."
            ),
            5,
            True,
        )
        note.isFullWidth = True

    group = inputs.addGroupCommandInput("ap_group", "Components")
    group.isExpanded = True
    group.isEnabledCheckBoxDisplayed = False
    grp = group.children

    table = grp.addTableCommandInput(INPUT_TABLE, "Components", 3, "4:3:3")
    table.minimumVisibleRows = min(max(len(targets), 2), 10)
    table.maximumVisibleRows = 12
    table.hasGrid = True
    table.columnSpacing = 2

    for row_idx, t in enumerate(targets):
        name_text = _escape_html(t.label) + (" <i>(root)</i>" if t.is_root else "")
        try:
            name_input = grp.addTextBoxCommandInput(
                f"ap_row_name_{row_idx}", "", name_text, 1, True
            )

            scheme_input = grp.addDropDownCommandInput(
                f"ap_row_scheme_{row_idx}",
                "Scheme",
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            scheme_input.listItems.add(SKIP_LABEL, True)
            for prefix in schemes.prefixes_for_intent(t.intent_value):
                scheme_input.listItems.add(schemes.SCHEME_LABEL[prefix], False)

            preview_input = grp.addTextBoxCommandInput(
                f"ap_row_preview_{row_idx}", "", "—", 1, True
            )

            table.addCommandInput(name_input, row_idx, 0)
            table.addCommandInput(scheme_input, row_idx, 1)
            table.addCommandInput(preview_input, row_idx, 2)

            _row_scheme_inputs[row_idx] = scheme_input
            _row_preview_inputs[row_idx] = preview_input
        except Exception as exc:
            ptutil.log(
                f"{CMD_NAME}: row {row_idx} ({t.label}) build failed: {exc}\n"
                f"{traceback.format_exc()}"
            )
            raise

    ptutil.log(
        f"{CMD_NAME}: table built (rowCount={table.rowCount}, targets={len(targets)})"
    )


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Preview recomputation (live on dropdown change)
# ---------------------------------------------------------------------------


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        _recompute_previews(args.inputs)
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} recompute previews")


def command_validate_inputs(args: adsk.core.ValidateInputsEventArgs):
    """Keep the Assign button disabled until at least one row has a real scheme.

    Without this, clicking Assign with every row at "(skip)" would still fire
    execute (which just logs and returns) and the user would perceive that
    nothing happened.
    """
    try:
        choices = _collect_choices(args.inputs)
        args.areInputsValid = any(prefix is not None for _t, prefix in choices)
    except Exception:
        ptutil.handle_error(f"{CMD_NAME} validateInputs")
        args.areInputsValid = True  # fail-open so we don't block forever


def _recompute_previews(inputs: adsk.core.CommandInputs) -> None:
    """Re-run the dry-run counter bump from an in-memory baseline of zero.

    We don't know the actual hub counters until Assign is clicked (reading the
    cache every keystroke would be wasteful). So the preview shows the
    *relative* position within this command: the first PRT row is "+1", the
    next PRT is "+2", etc. We display those as zero-padded numbers so the user
    can see the scheme applies and rows advance together.
    """
    if _mode_is_table:
        _recompute_table_previews(inputs)
    else:
        _recompute_simple_preview(inputs)


def _recompute_simple_preview(inputs: adsk.core.CommandInputs) -> None:
    scheme_input = adsk.core.DropDownCommandInput.cast(
        inputs.itemById(INPUT_SCHEME_SIMPLE)
    )
    preview_input = adsk.core.StringValueCommandInput.cast(
        inputs.itemById(INPUT_PREVIEW_SIMPLE)
    )
    if scheme_input is None or preview_input is None:
        return

    prefix = _prefix_from_label(scheme_input.selectedItem.name)
    if prefix is None:
        preview_input.value = "(will skip)"
    else:
        n = _baseline_counters.get(prefix, 0) + 1
        suffix = (
            ""
            if _baseline_loaded
            else "  (baseline unavailable — actual number may differ)"
        )
        preview_input.value = schemes.format_number(prefix, n) + suffix


def _recompute_table_previews(inputs: adsk.core.CommandInputs) -> None:
    """Walk rows in target order, per-prefix running offset drives the preview.

    Displayed number = baseline counter from the hub + running offset for
    the chosen prefix. If the baseline couldn't be loaded, previews start
    at 1 and are suffixed so the user knows the actual assigned number may
    differ.
    """
    _ = inputs  # not needed — we kept direct refs in _row_scheme_inputs/_row_preview_inputs
    offsets: Dict[str, int] = {}
    for row_idx in range(len(_targets)):
        scheme_input = _row_scheme_inputs.get(row_idx)
        preview_input = _row_preview_inputs.get(row_idx)
        if scheme_input is None or preview_input is None:
            continue
        prefix = _prefix_from_label(scheme_input.selectedItem.name)
        if prefix is None:
            preview_input.formattedText = "—"
        else:
            offsets[prefix] = offsets.get(prefix, 0) + 1
            n = _baseline_counters.get(prefix, 0) + offsets[prefix]
            suffix = "" if _baseline_loaded else " *"
            preview_input.formattedText = schemes.format_number(prefix, n) + suffix


def _prefix_from_label(label: str) -> Optional[str]:
    if not label or label == SKIP_LABEL:
        return None
    # Labels look like "PRT — Custom part"; grab the first 3 chars.
    prefix = label.split(" ", 1)[0].strip()
    return prefix if prefix in schemes.SCHEME_PREFIXES else None


# ---------------------------------------------------------------------------
# Execute — commit cache, then stamp components
# ---------------------------------------------------------------------------


def command_execute(args: adsk.core.CommandEventArgs):
    ptutil.log(f"{CMD_NAME} execute: start")
    deferred_error: Optional[str] = None
    try:
        inputs = args.command.commandInputs

        # Collect the user's per-target scheme choices. validateInputs keeps
        # the Assign button disabled unless at least one real scheme is set,
        # so to_assign should be non-empty here in practice.
        choices: List[tuple] = _collect_choices(inputs)
        to_assign = [(t, p) for t, p in choices if p is not None]
        if not to_assign:
            ptutil.log(f"{CMD_NAME} execute: nothing to assign — closing")
            return

        # The dialog already surfaced an inline warning when any target had
        # an existing part number, so no modal confirmation is needed here.
        # We log each overwrite for audit/diagnostic purposes.
        overwrites = [t for t, _ in to_assign if t.current_pn]
        if overwrites:
            ptutil.log(
                f"{CMD_NAME} execute: overwriting "
                + ", ".join(f"{t.label}={t.current_pn!r}" for t in overwrites)
            )

        # Tally increments by prefix.
        increments: Dict[str, int] = {}
        for _, prefix in to_assign:
            increments[prefix] = increments.get(prefix, 0) + 1

        # Commit to pn-cache.json with optimistic retry.
        updated_by = _current_user_id()
        progress = ui.progressBar
        progress.showBusy(f"{CMD_NAME} — updating hub Pn-Cache...")
        adsk.doEvents()
        try:
            result = pn_cache.commit_assignments(
                app=app,
                increments=increments,
                updated_by=updated_by,
                tmp_dir=pn_cache.default_tmp_dir(),
            )
        finally:
            progress.hide()

        # Resolve per-target numbers from snapshot_before + per-prefix running
        # offset (matches the preview ordering).
        offsets: Dict[str, int] = {}
        assignments: List[tuple] = []  # (Target, prefix, number_str)
        for target, prefix in to_assign:
            offsets[prefix] = offsets.get(prefix, 0) + 1
            n = result.snapshot_before.last_used(prefix) + offsets[prefix]
            number_str = schemes.format_number(prefix, n)
            assignments.append((target, prefix, number_str))

        # Stamp components. Document save is intentionally left to the user:
        # Fusion's save step can be slow, and the dialog should close
        # immediately on Assign.
        #
        # The legacy Component.partNumber setter routes through MFGDM GraphQL
        # on saved docs and has been observed to silently fail for components
        # whose cloud metadata isn't ready (e.g., local components added after
        # the last save). We defend against that by reading the value back
        # after every set; a mismatch is treated as a stamp failure even
        # though no exception was raised.
        stamp_errors: List[str] = []
        for target, _prefix, number_str in assignments:
            try:
                target.component.partNumber = number_str
                actual = ""
                try:
                    actual = target.component.partNumber or ""
                except Exception:
                    actual = ""
                if actual != number_str:
                    stamp_errors.append(
                        f"{target.label}: set to {number_str!r} but readback "
                        f"returned {actual!r} (component likely lacks MFGDM "
                        f"metadata — save the document and retry)"
                    )
            except Exception as exc:
                stamp_errors.append(f"{target.label}: {exc}")

        if stamp_errors:
            deferred_error = (
                "Part numbers reserved in Pn-Cache but some stamps failed:\n\n"
                + "\n".join(stamp_errors)
                + "\n\nRe-run the command to retry."
            )
            ptutil.log(f"{CMD_NAME} execute: stamp errors: {stamp_errors}")
        else:
            ptutil.log(
                f"{CMD_NAME}: assigned "
                f"{', '.join(f'{t.label}={n}' for t, _p, n in assignments)} "
                f"(cache v{result.new_version_number}, retries={result.retries_used})"
            )

    except pn_cache.PnCacheError as exc:
        deferred_error = f"Pn-Cache error:\n\n{exc}"
        ptutil.log(f"{CMD_NAME} execute: PnCacheError: {exc}")
    except hub_fs.HubFsError as exc:
        deferred_error = f"Hub layout error:\n\n{exc}"
        ptutil.log(f"{CMD_NAME} execute: HubFsError: {exc}")
    except Exception:
        ptutil.log(f"{CMD_NAME} execute failure:\n{traceback.format_exc()}")
        deferred_error = f"Failed:\n{traceback.format_exc()}"

    # Stash the error — the destroy handler will surface it AFTER the dialog
    # has closed. Showing a messageBox here can race with dialog teardown and
    # appear to leave the command open.
    if deferred_error:
        global _pending_error_message
        _pending_error_message = deferred_error

    ptutil.log(f"{CMD_NAME} execute: return (dialog will close)")


def _collect_choices(inputs: adsk.core.CommandInputs) -> List[tuple]:
    """Return [(Target, prefix_or_None), ...] matching ``_targets`` row order."""
    choices: List[tuple] = []

    if not _mode_is_table:
        scheme_input = adsk.core.DropDownCommandInput.cast(
            inputs.itemById(INPUT_SCHEME_SIMPLE)
        )
        if scheme_input is None or not _targets:
            return choices
        prefix = _prefix_from_label(scheme_input.selectedItem.name)
        choices.append((_targets[0], prefix))
        return choices

    for row_idx, target in enumerate(_targets):
        scheme_input = _row_scheme_inputs.get(row_idx)
        if scheme_input is None:
            continue
        prefix = _prefix_from_label(scheme_input.selectedItem.name)
        choices.append((target, prefix))
    return choices


def _current_user_id() -> str:
    """Best-effort identifier for the logged-in Fusion user, or ""."""
    try:
        uid = app.userId
        if uid:
            return str(uid)
    except Exception:
        pass
    try:
        name = app.currentUser.userName
        if name:
            return str(name)
    except Exception:
        pass
    return ""


def command_destroy(args: adsk.core.CommandEventArgs):
    global \
        local_handlers, \
        _targets, \
        _mode_is_table, \
        _pending_error_message, \
        _baseline_loaded
    local_handlers = []
    _targets = []
    _mode_is_table = False
    _row_scheme_inputs.clear()
    _row_preview_inputs.clear()
    _baseline_counters.clear()
    _baseline_loaded = False
    ptutil.log(f"{CMD_NAME} Command Destroy Event")

    # Surface any errors accumulated during execute now that the dialog is
    # actually gone — message boxes shown during execute can otherwise race
    # with dialog teardown and make the command look stuck.
    if _pending_error_message:
        msg = _pending_error_message
        _pending_error_message = None
        ui.messageBox(
            msg,
            CMD_NAME,
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType,
        )
