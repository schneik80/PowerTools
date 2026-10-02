# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Does MFGDM know this document? -- pure logic, no ``adsk`` import.

Document Information asks the cloud manufacturing data model (``mfgdm://v3``)
whether it holds a record for the active design or drawing, and shows what it
answered. ``entry.py`` reads the local ids and owns the transport; everything
that turns a GraphQL answer into dialog text lives here, under test.

The two document kinds reach MFGDM differently, because the desktop API gives
them different local handles:

* **Design** -- ``rootDataComponent.mfgdmModelId`` (falling back to
  ``rootComponent.mfgdmModelId``) is the timeless model id, queried with
  ``model(modelId)``.
* **Drawing** -- there is no local MFGDM id at all. ``DataHub.mfgdmId`` is the
  ``urn:adsk.ace`` hub id and ``DataFile.id`` the lineage urn, and
  ``item(hubId, itemId)`` resolves the pair to a ``DrawingItem``. Its
  ``tipDrawing.model`` names the design MFGDM thinks the drawing documents,
  which is compared with the drawing's local document reference. The two
  should agree; a disagreement seen on 2026-10-01 was a Fusion bug, and the
  warning exists to surface it.
* **Electronics project, schematic, 2D board** -- the same ``item()`` lookup;
  MFGDM answers with a ``BasicItem``: a file record (extension, tip version)
  with no model, component or part number behind it. The 3D PCB is an
  ordinary design. Seen on ADSKMVG91G2F5W, pre-production 2706.0.116,
  2026-10-02.

Query shapes verified against the live schema on ADSKMVG91G2F5W, pre-production
channel, 2026-10-01, with a drawing and its source design open.
"""

from __future__ import annotations

from html import escape

ITEM_QUERY = """
query($hubId: ID!, $itemId: ID!) {
  item(hubId: $hubId, itemId: $itemId) {
    __typename
    id
    extensionType
    ... on BasicItem { tipVersion { versionNumber } }
    ... on DrawingItem {
      tipVersion { versionNumber }
      tipDrawing {
        id
        itemNumber { id }
        lifecycle { state { value } revision { value } }
        model { id designItem { id name } }
      }
    }
  }
}
"""

MODEL_QUERY = """
query($modelId: ID!) {
  model(modelId: $modelId) {
    id
    component {
      id
      hub { id }
      partNumber { value }
      itemNumber { id }
    }
    designItem { id name }
  }
}
"""

# Statuses a summary can carry.
OK = "ok"
MISSING = "missing"  # the query ran and MFGDM has no record
NO_LOCAL_ID = "no_local_id"  # Fusion holds no id to ask with
NOT_LOADED = "not_loaded"  # a drawing's source design is not open
ERROR = "error"  # transport or GraphQL failure


def _dig(obj, *keys) -> str:
    """Walk nested dicts, treating a missing or null level as "" at the end."""
    for key in keys:
        if not isinstance(obj, dict):
            return ""
        obj = obj.get(key)
    if obj is None:
        return ""
    return str(obj)


def summarize_model(data: dict) -> dict:
    """Flatten a :data:`MODEL_QUERY` answer (the ``data`` object)."""
    model = (data or {}).get("model")
    if not model:
        return {"status": MISSING}
    return {
        "status": OK,
        "model_id": _dig(model, "id"),
        "component_id": _dig(model, "component", "id"),
        "hub_id": _dig(model, "component", "hub", "id"),
        "part_number": _dig(model, "component", "partNumber", "value"),
        "item_number": _dig(model, "component", "itemNumber", "id"),
        "design_item_id": _dig(model, "designItem", "id"),
        "design_item_name": _dig(model, "designItem", "name"),
    }


def summarize_item(data: dict) -> dict:
    """Flatten an :data:`ITEM_QUERY` answer (the ``data`` object)."""
    item = (data or {}).get("item")
    if not item:
        return {"status": MISSING}
    drawing = item.get("tipDrawing") or {}
    return {
        "status": OK,
        "kind": _dig(item, "__typename"),
        "item_id": _dig(item, "id"),
        "extension": _dig(item, "extensionType"),
        "version_number": _dig(item, "tipVersion", "versionNumber"),
        "drawing_id": _dig(drawing, "id"),
        "item_number": _dig(drawing, "itemNumber", "id"),
        "lifecycle_state": _dig(drawing, "lifecycle", "state", "value"),
        "revision": _dig(drawing, "lifecycle", "revision", "value"),
        "source_model_id": _dig(drawing, "model", "id"),
        "source_design_item_id": _dig(drawing, "model", "designItem", "id"),
        "source_design_item_name": _dig(drawing, "model", "designItem", "name"),
    }


def fetch(gql, query: str, variables: dict, summarize) -> dict:
    """Run *query* through the *gql* transport and summarize the answer.

    Never raises: any failure becomes an :data:`ERROR` summary carrying the
    message, so the rest of the dialog still shows.
    """
    try:
        return summarize(gql(query, variables))
    except Exception as exc:
        return {"status": ERROR, "error": str(exc)}


def model_summary(gql, model_id: str) -> dict:
    """:func:`summarize_model` for *model_id*, or :data:`NO_LOCAL_ID` without one."""
    if not model_id:
        return {"status": NO_LOCAL_ID}
    return fetch(gql, MODEL_QUERY, {"modelId": model_id}, summarize_model)


def item_summary(gql, hub_id: str, item_id: str) -> dict:
    """:func:`summarize_item` for the pair, or :data:`NO_LOCAL_ID` if either is empty."""
    if not hub_id or not item_id:
        return {"status": NO_LOCAL_ID}
    return fetch(gql, ITEM_QUERY, {"hubId": hub_id, "itemId": item_id}, summarize_item)


def source_mismatch(local_lineage_id: str, cloud_design_item_id: str) -> bool:
    """True when the drawing's local reference and MFGDM name different designs.

    Only a provable disagreement counts: an id missing on either side is
    "unknown", not a mismatch.
    """
    if not local_lineage_id or not cloud_design_item_id:
        return False
    return local_lineage_id != cloud_design_item_id


# --- Rendering ---------------------------------------------------------------

_STATUS_TEXT = {
    MISSING: "Not found. MFGDM returned no record for this document.",
    NO_LOCAL_ID: (
        "Not available yet. Fusion has not received the MFGDM ids for this "
        "document; wait a moment after a save, then retry."
    ),
    NOT_LOADED: "Not checked. The source design is not open in Fusion.",
}


def _row(label: str, value: str) -> str:
    return f"<b>{escape(label)}:</b> {escape(value) if value else '(none)'}<br>"


def _status_row(label: str, summary: dict) -> str:
    """The one-line verdict for *summary*; "" when it is OK (rows follow)."""
    status = summary.get("status")
    if status == OK:
        return f"<b>{escape(label)}:</b> Available<br>"
    if status == ERROR:
        return (
            f"<b>{escape(label)}:</b> Query failed: "
            f"{escape(summary.get('error') or 'unknown error')}<br>"
        )
    return f"<b>{escape(label)}:</b> {escape(_STATUS_TEXT.get(status, status))}<br>"


def _model_rows(summary: dict) -> str:
    if summary.get("status") != OK:
        return ""
    return (
        _row("Model ID", summary.get("model_id", ""))
        + _row("Component ID", summary.get("component_id", ""))
        + _row("MFGDM Hub ID", summary.get("hub_id", ""))
        + _row("Part Number", summary.get("part_number", ""))
        + _row("Item Number", summary.get("item_number", ""))
    )


def render_design(model: dict) -> tuple[str, bool]:
    """The MFGDM block for a design. Returns ``(html, warn)``."""
    html = "<p><b>MFGDM</b><br>" + _status_row("MFGDM Data", model) + _model_rows(model)
    return html, model.get("status") != OK


def render_file(item: dict) -> tuple[str, bool]:
    """The MFGDM block for an electronics file (a ``BasicItem``). Returns ``(html, warn)``.

    MFGDM keeps a file record for these and nothing more, which the block says
    so that a missing part number does not read as missing data.
    """
    html = "<p><b>MFGDM</b><br>" + _status_row("MFGDM Data", item)
    if item.get("status") == OK:
        html += (
            _row("Item ID", item.get("item_id", ""))
            + _row("Item Type", item.get("kind", ""))
            + _row("File Type", item.get("extension", ""))
            + _row("Tip Version", item.get("version_number", ""))
            + "MFGDM keeps only a file record for this document type: no "
            "model, component or part number.<br>"
        )
    return html, item.get("status") != OK


def render_drawing(
    item: dict,
    source_name: str,
    source_lineage_id: str,
    source_model: dict | None,
) -> tuple[str, bool]:
    """The MFGDM block for a drawing and its source design. Returns ``(html, warn)``.

    Args:
        item: :func:`item_summary` of the drawing.
        source_name: The local reference's file name, "" with no reference.
        source_lineage_id: The local reference's ``DataFile.id``.
        source_model: :func:`model_summary` of the source design, or a
            :data:`NOT_LOADED` summary; None when the drawing references
            nothing.
    """
    warn = item.get("status") != OK
    html = "<p><b>MFGDM</b><br>" + _status_row("Drawing MFGDM Data", item)
    if item.get("status") == OK:
        html += (
            _row("Drawing ID", item.get("drawing_id", ""))
            + _row("Item Number", item.get("item_number", ""))
            + _row("Lifecycle State", item.get("lifecycle_state", ""))
            + _row("Revision", item.get("revision", ""))
            + _row("MFGDM Source Design", item.get("source_design_item_name", ""))
        )

    if source_model is None:
        html += _row("Source Design", "")
    else:
        html += "<br>" + _row("Source Design", source_name)
        html += _status_row("Source Design MFGDM Data", source_model)
        html += _model_rows(source_model)
        if source_model.get("status") not in (OK, NOT_LOADED):
            warn = True

    if source_mismatch(source_lineage_id, item.get("source_design_item_id", "")):
        warn = True
        html += (
            "<br><b>MFGDM links this drawing to a different design.</b> The "
            f"drawing references {escape(source_name or 'a design')} locally, "
            "but MFGDM records it as documenting "
            f"{escape(item.get('source_design_item_name') or 'another design')}."
            "<br>"
        )
    return html, warn
