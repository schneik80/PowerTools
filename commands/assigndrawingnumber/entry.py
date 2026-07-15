# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Assign Drawing Number — reserves the next DWG-NNNNNN number from the
hub-wide Pn-Cache and stamps it on the active Drawing document.

Storage happens in two places, both automatic:

1. **Drawing document attribute** (canonical local record) — stored as an
   ``adsk.core.Attribute`` on the DrawingDocument with group
   ``PowerTools.PartNumber`` and name ``assigned``. Because
   ``adsk.drawing`` does not expose a first-class ``partNumber`` property
   and ``DataFile.description`` is read-only in the Python API, this
   attribute is the durable source of truth for the drawing itself.

2. **Source design's ``Drawing Number`` custom property** (titleblock hook)
   — written through the MFGDM GraphQL ``setProperties`` mutation against
   the drawing's referenced 3D design (opened silently if not already in
   memory). A hub-configured titleblock with a binding to the source
   component's ``Drawing Number`` custom property will auto-populate on
   the drawing once synced. If the custom property is missing from the
   user's hub, an actionable error (with a setup-guide link) is shown.
"""

from __future__ import annotations

import os
import traceback

import adsk.core
import adsk.drawing
import adsk.fusion

from ... import config
from ...lib import ptAddInUtils as ptutil
from ..partnumber_shared import hub_fs, mfgdm_props, pn_cache, schemes

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Assign Drawing Number"
CMD_ID = "PTND_assignDrawingNumber"
CMD_Description = (
    "Reserve the next DWG-NNNNNN number from the hub Pn-Cache and stamp it "
    "on the active drawing document."
)
IS_PROMOTED = True

# Drawing command lives in the Drawing workspace on the built-in
# FusionDocTab, in our own PowerTools panel.
WORKSPACE_ID = config.drawing_workspace
TAB_ID = config.drawing_tab_id
PANEL_ID = config.drawing_panel_id
PANEL_NAME = config.drawing_panel_name
PANEL_AFTER = config.drawing_panel_after

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

INPUT_PREVIEW = "ad_preview"
INPUT_CURRENT = "ad_current"
INPUT_INFO = "ad_info"

ATTR_GROUP = "PowerTools.PartNumber"
ATTR_NAME = "assigned"
DRAWING_PREFIX = schemes.DRAWING_PREFIX  # "DWG"

# Name of the MFGDM custom property on the source design's root component
# that the titleblock is configured to read. Must match the property's name
# in the hub's Custom Properties collection exactly.
DRAWING_NUMBER_PROPERTY_NAME = "Drawing Number"

# URL of the setup guide for the 'Drawing Number' custom property. Shown
# as a clickable link in the error dialog when the property is missing
# from the user's hub. Replace with the real documentation URL when it is
# published.
DRAWING_NUMBER_SETUP_URL = "https://example.com/drawing-number-setup"

local_handlers: list = []

# Error to display once the dialog has closed (set in execute, shown in destroy).
_pending_error_message = None


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    ptutil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    if workspace is None:
        ptutil.log(f"[{CMD_NAME}] Workspace {WORKSPACE_ID} not found at start()")
        return

    # FusionDocTab is built-in to the Drawing workspace; we never create it.
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        ptutil.log(
            f"[{CMD_NAME}] Tab '{TAB_ID}' not found on '{WORKSPACE_ID}' — "
            f"skipping UI registration."
        )
        return

    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED

    ptutil.log(f"{CMD_NAME} command started")


def stop():
    try:
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        if not workspace:
            return

        toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
        panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID) if toolbar_tab else None
        command_control = panel.controls.itemById(CMD_ID) if panel else None
        command_definition = ui.commandDefinitions.itemById(CMD_ID)

        if command_control:
            command_control.deleteMe()
        if command_definition:
            command_definition.deleteMe()
        # Delete our panel when it's empty, but never touch FusionDocTab — it
        # is a native Fusion tab and belongs to the Drawing workspace.
        if panel and panel.controls.count == 0:
            panel.deleteMe()

        ptutil.log(f"{CMD_NAME} command stopped")
    except Exception as exc:
        ptutil.log(f"Error stopping {CMD_NAME}: {exc}")


# ---------------------------------------------------------------------------
# Command created
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs):
    ptutil.log(f"{CMD_NAME} Command Created Event")

    if not ptutil.isSaved():
        args.command.doExecute(True)
        return

    doc = app.activeDocument
    if not isinstance(doc, adsk.drawing.DrawingDocument):
        ui.messageBox(
            "Assign Drawing Number requires an active Fusion 2D drawing document.",
            CMD_NAME,
            0,
            2,
        )
        args.command.doExecute(True)
        return

    current = _read_existing_drawing_number(doc) or ""

    # Preview the real next DWG number by reading the hub Pn-Cache counter.
    # Falls back to DWG-000001 if the cache is unreachable; the actual
    # reserved number on Assign comes from a fresh download (optimistic retry).
    next_n, baseline_loaded = _peek_next_drawing_number()
    preview_text = schemes.format_number(DRAWING_PREFIX, next_n)
    if not baseline_loaded:
        preview_text += "  (baseline unavailable — actual number may differ)"

    cmd = args.command
    cmd.okButtonText = "Assign"
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        INPUT_INFO,
        "Scheme",
        f"<b>{DRAWING_PREFIX}</b> — Drawing (controlled document)",
        1,
        True,
    )

    # Show the current number and an inline warning only when one exists —
    # this replaces the modal overwrite confirmation so the user has all the
    # information in one place and clicking Assign does exactly what it says.
    if current:
        current_input = inputs.addStringValueInput(
            INPUT_CURRENT, "Current number", current
        )
        current_input.isReadOnly = True

        note = inputs.addTextBoxCommandInput(
            "ad_overwrite_note",
            "",
            (
                "<span style='color:#b06000'><b>⚠ This drawing already has a "
                "number assigned.</b></span> Clicking <b>Assign</b> will "
                f"replace <b>{_escape_html(current)}</b> with the new number "
                f"shown below."
            ),
            4,
            True,
        )
        note.isFullWidth = True

    preview_input = inputs.addStringValueInput(
        INPUT_PREVIEW,
        "Will assign",
        preview_text,
    )
    preview_input.isReadOnly = True

    ptutil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    ptutil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _peek_next_drawing_number() -> tuple:
    """Return (next_n, baseline_loaded). Best-effort — never raises."""
    progress = ui.progressBar
    progress.showBusy(f"{CMD_NAME} — loading Pn-Cache counter...")
    adsk.doEvents()
    try:
        project = hub_fs.find_assets_project(app)
        folder = hub_fs.find_or_create_pn_cache_folder(project)
        snapshot = pn_cache.download_snapshot(folder, pn_cache.default_tmp_dir())
        return snapshot.last_used(DRAWING_PREFIX) + 1, True
    except Exception as exc:
        ptutil.log(f"{CMD_NAME}: could not peek DWG counter: {exc}")
        return 1, False
    finally:
        progress.hide()


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


def command_execute(args: adsk.core.CommandEventArgs):
    ptutil.log(f"{CMD_NAME} execute: start")
    deferred_error = None
    try:
        doc = app.activeDocument
        if not isinstance(doc, adsk.drawing.DrawingDocument):
            deferred_error = "Active document is no longer a drawing."
            return

        # The dialog already showed the user an inline warning and the
        # existing number when one was present, so no modal confirmation is
        # needed here — Assign means Assign. We still log the overwrite for
        # audit/diagnostic purposes.
        existing = _read_existing_drawing_number(doc)
        if existing:
            ptutil.log(f"{CMD_NAME} execute: overwriting existing number {existing!r}")

        progress = ui.progressBar
        progress.showBusy(f"{CMD_NAME} — updating hub Pn-Cache...")
        adsk.doEvents()
        try:
            result = pn_cache.commit_assignments(
                app=app,
                increments={DRAWING_PREFIX: 1},
                updated_by=_current_user_id(),
                tmp_dir=pn_cache.default_tmp_dir(),
            )
        finally:
            progress.hide()

        n = result.snapshot_before.last_used(DRAWING_PREFIX) + 1
        number_str = schemes.format_number(DRAWING_PREFIX, n)

        # Stamp the drawing document. Document save is left to the user so
        # the dialog can close promptly on Assign.
        stamp_errors = []
        try:
            _write_drawing_attribute(doc, number_str)
        except Exception as exc:
            stamp_errors.append(f"attribute write: {exc}")

        # Best-effort: sync the drawing number into the source design's
        # 'Drawing Number' custom property so the titleblock can pull it
        # automatically. Failures here do NOT invalidate the drawing stamp
        # — the drawing-attribute record above is the canonical local
        # record. Missing-custom-property returns an HTML-formatted error
        # with a setup-guide link.
        sync_deferred_html = _sync_drawing_number_to_source_design(doc, number_str)

        if stamp_errors:
            deferred_error = (
                f"Drawing number {number_str} reserved in Pn-Cache, "
                f"but some stamps failed:\n\n" + "\n".join(stamp_errors)
            )
            ptutil.log(f"{CMD_NAME} execute: stamp errors: {stamp_errors}")
        else:
            ptutil.log(
                f"{CMD_NAME}: assigned {number_str} "
                f"(cache v{result.new_version_number}, retries={result.retries_used})"
            )

        # Merge the titleblock-sync error, if any, into the deferred error.
        if sync_deferred_html:
            deferred_error = (
                (deferred_error + "<br/><br/>") if deferred_error else ""
            ) + sync_deferred_html

    except pn_cache.PnCacheError as exc:
        deferred_error = f"Pn-Cache error:\n\n{exc}"
        ptutil.log(f"{CMD_NAME} execute: PnCacheError: {exc}")
    except hub_fs.HubFsError as exc:
        deferred_error = f"Hub layout error:\n\n{exc}"
        ptutil.log(f"{CMD_NAME} execute: HubFsError: {exc}")
    except Exception:
        ptutil.log(f"{CMD_NAME} execute failure:\n{traceback.format_exc()}")
        deferred_error = f"Failed:\n{traceback.format_exc()}"

    if deferred_error:
        global _pending_error_message
        _pending_error_message = deferred_error

    ptutil.log(f"{CMD_NAME} execute: return (dialog will close)")


# ---------------------------------------------------------------------------
# Attribute / DataFile helpers
# ---------------------------------------------------------------------------


def _read_existing_drawing_number(doc: adsk.drawing.DrawingDocument) -> str:
    """Return the existing drawing number stamp, or "" if none."""
    try:
        attrs = doc.attributes
        if attrs is None:
            return ""
        attr = attrs.itemByName(ATTR_GROUP, ATTR_NAME)
        if attr is None:
            return ""
        return attr.value or ""
    except Exception:
        return ""


def _write_drawing_attribute(
    doc: adsk.drawing.DrawingDocument, number_str: str
) -> None:
    attrs = doc.attributes
    if attrs is None:
        raise RuntimeError("DrawingDocument does not expose attributes.")
    attrs.add(ATTR_GROUP, ATTR_NAME, number_str)


def _current_user_id() -> str:
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


# ---------------------------------------------------------------------------
# Titleblock sync — writes the drawing number into the source design's
# 'Drawing Number' custom property via MFGDM GraphQL.
# ---------------------------------------------------------------------------


def _sync_drawing_number_to_source_design(
    drawing_doc: adsk.drawing.DrawingDocument,
    number_str: str,
) -> str:
    """Best-effort write-through to the source design's 'Drawing Number'
    custom property. Returns an HTML error string on failure (to be shown
    after the dialog closes), or an empty string on success / no-op.

    Rules:
      * Fusion drawings reference at most one 3D design — we use the first
        DocumentReference only.
      * If the source design isn't already open, open it with
        ``visible=False`` and close it after we're done.
      * Missing ``Drawing Number`` custom property returns a user-actionable
        HTML error with a link to the setup guide; every other failure is
        surfaced as a short plain-text warning.
      * The drawing stamp on this document has already succeeded by the
        time this runs — sync failure never invalidates it.
    """
    refs = drawing_doc.documentReferences
    if refs is None or refs.count == 0:
        ptutil.log(
            f"{CMD_NAME}: drawing has no source-design reference; "
            f"skipping titleblock sync."
        )
        return ""

    # Fusion guarantees a drawing references at most one 3D design.
    ref = refs.item(0)
    source_data_file = ref.dataFile
    source_doc = ref.referencedDocument
    opened_by_us = False

    try:
        if source_doc is None:
            ptutil.log(
                f"{CMD_NAME}: source design "
                f"{getattr(source_data_file, 'name', '?')!r} not open — "
                f"opening silently for titleblock sync."
            )
            try:
                source_doc = app.documents.open(source_data_file, False)
                opened_by_us = True
            except Exception as exc:
                ptutil.log(f"{CMD_NAME}: silent open failed: {exc}")
                return (
                    f"Titleblock sync skipped: could not open the source "
                    f"design ({exc})."
                )

        if source_doc is None:
            return "Titleblock sync skipped: source design unavailable."

        source_design = adsk.fusion.Design.cast(
            source_doc.products.itemByProductType("DesignProductType")
        )
        if source_design is None:
            return "Titleblock sync skipped: source document has no Design product."

        try:
            model_id = source_design.rootDataComponent.mfgdmModelId or ""
        except Exception:
            model_id = ""
        if not model_id:
            return (
                "Titleblock sync skipped: source design has no MFGDM model "
                "id yet (cloud metadata not ready). Save the source design "
                "and retry."
            )

        try:
            new_value = mfgdm_props.set_component_custom_property(
                model_id=model_id,
                property_name=DRAWING_NUMBER_PROPERTY_NAME,
                value=number_str,
            )
        except mfgdm_props.PropertyNotFoundError:
            ptutil.log(
                f"{CMD_NAME}: source design is missing "
                f"{DRAWING_NUMBER_PROPERTY_NAME!r} custom property."
            )
            return _missing_custom_property_html()
        except mfgdm_props.MfgdmPropsError as exc:
            ptutil.log(f"{CMD_NAME}: MFGDM setProperties failed: {exc}")
            return f"Titleblock sync failed: {exc}"
        except Exception:
            ptutil.handle_error(f"{CMD_NAME} titleblock sync")
            return "Titleblock sync failed unexpectedly — see the Text Commands log."

        ptutil.log(
            f"{CMD_NAME}: wrote {DRAWING_NUMBER_PROPERTY_NAME!r} = "
            f"{new_value!r} on source design "
            f"{getattr(source_data_file, 'name', '?')!r}."
        )
        return ""
    finally:
        # Close the source design if we opened it — regardless of outcome.
        if opened_by_us and source_doc is not None:
            try:
                source_doc.close(False)
                ptutil.log(f"{CMD_NAME}: closed silently-opened source design.")
            except Exception as exc:
                ptutil.log(
                    f"{CMD_NAME}: failed to close silently-opened source design: {exc}"
                )


def _missing_custom_property_html() -> str:
    """HTML error body shown when the source design lacks the 'Drawing
    Number' custom property. Includes a clickable setup-guide link.
    """
    prop = DRAWING_NUMBER_PROPERTY_NAME
    url = DRAWING_NUMBER_SETUP_URL
    return (
        f"<b>⚠ Titleblock sync skipped.</b><br/><br/>"
        f"The drawing number was assigned successfully on this drawing, "
        f"but the source 3D design is missing the "
        f"<b>{prop!r}</b> custom property — so the titleblock cannot "
        f"auto-populate from the source component.<br/><br/>"
        f"To enable titleblock auto-population, add a <b>{prop}</b> "
        f"custom property to your hub's Custom Properties collection, "
        f"then re-run this command.<br/><br/>"
        f'Setup guide: <a href="{url}">{url}</a>'
    )


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _pending_error_message
    local_handlers = []
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
