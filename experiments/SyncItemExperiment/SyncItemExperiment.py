# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# ---------------------------------------------------------------------------
# Phase A de-risking experiment for the "Sync Item to Part Number" command.
#
# READ-ONLY. This script writes nothing to the model or the cloud. It exists to
# prove the local Python API -> cloud MFGDM GraphQL API bridge before the real
# command is built, because the two APIs use different, non-interchangeable IDs.
#
# HOW TO RUN
#   1. Open Fusion with the Manufacturing Data Model / Manage Extension enabled.
#   2. Open a design that is KNOWN to be part of a shared part number group.
#   3. Utilities/Tools > Scripts and Add-Ins > Scripts > green "+" > add this
#      folder > Run.  (Or paste the body into the Text Commands console.)
#   4. Read the output in the Text Commands window (View > Show Text Commands).
#
# WHAT IT REPORTS (paste these lines back to finish the implementation)
#   * LOCAL partNumber / mfgdmModelId / timestamp / activeHub.id
#   * ATTR[...] lines  -> where the Fusion Manage "Item Number" lives locally
#                         (fills read_item_number()); if none match, the item
#                         number is cloud-only and we switch the enablement path
#                         to mfgdmDataReady.
#   * TAB id=... lines -> the exact built-in Manage tab id (fills
#                         config.manage_tab_id).
#   * GQL component.id / component.hub.id  -> the cloud-side ids.
#   * ID CHECK ...      -> confirms local activeHub.id != gql hub.id (the trap).
#   * SharedPartNumberInfo schema  -> the fields; pick the one(s) that signal a
#                                     2+-model group (fills _decide_shared()).
#   * sharedPartNumber (gql hubId) vs (LOCAL hubId)  -> proves which hub id the
#                                     query actually accepts.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
import traceback

import adsk.core
import adsk.fusion

app = adsk.core.Application.get()
ui = app.userInterface

# Bump this on every edit so a run's output proves which version executed
# (Fusion can re-run a cached copy of a script rather than reloading the file).
SCRIPT_VERSION = "v6-dynamic-finalize"

# Keep a module reference so the event handler is not garbage-collected.
_handler = None

MFGDM_URL = "mfgdm://v3"
DESIGN_WORKSPACE_ID = "FusionSolidEnvironment"


def _log(message: str) -> None:
    """Write to the Text Commands window (and stdout for an attached debugger)."""
    app.log(message)
    print(message)


def gql(query: str, variables: dict | None = None) -> dict:
    """POST a GraphQL query/mutation to the MFGDM endpoint on behalf of the user."""
    req = adsk.core.HttpRequest.create(MFGDM_URL, adsk.core.HttpMethods.PostMethod)
    req.setHeader("Content-type", "application/json; charset=utf-8")
    payload: dict = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    req.data = json.dumps(payload)
    resp = req.executeSync()
    _log(f"HTTP {resp.statusCode}")
    try:
        return json.loads(resp.data)
    except Exception:
        _log(f"non-JSON response: {resp.data[:1000]}")
        return {}


def _dump_local_facts(design: adsk.fusion.Design):
    """(1) Everything the local Python API knows. Returns (model_id, timestamp,
    part_number, local_hub_id)."""
    root = design.rootComponent
    part_number = root.partNumber
    data = design.rootDataComponent
    model_id, timestamp = data.mfgdmModelId, data.timestamp
    local_hub = app.data.activeHub
    local_hub_id = local_hub.id if local_hub else None

    _log("=" * 70)
    _log(f"LOCAL partNumber            = {part_number!r}")
    _log(f"LOCAL rootComponent.name    = {root.name!r}")
    _log(f"LOCAL mfgdmModelId          = {model_id!r}")
    _log(f"LOCAL timestamp             = {timestamp!r}")
    _log(f"LOCAL app.data.activeHub.id = {local_hub_id!r}")

    # Item-number carrier discovery: dump every attribute on the root component
    # and the design. The Fusion Manage "Item Number" is expected to surface as
    # a Manage-owned Fusion Attribute here if it is locally readable.
    _log("-- attributes (looking for the Item Number carrier) --")
    for tag, owner in (("rootComponent", root), ("design", design)):
        attrs = owner.attributes
        if attrs.count == 0:
            _log(f"ATTR[{tag}] <none>")
        for i in range(attrs.count):
            a = attrs.item(i)
            _log(f"ATTR[{tag}] group={a.groupName!r} name={a.name!r} value={a.value!r}")

    # Manage tab id discovery.
    _log("-- Design-workspace toolbar tabs (looking for the Manage tab) --")
    ws = ui.workspaces.itemById(DESIGN_WORKSPACE_ID)
    for i in range(ws.toolbarTabs.count):
        t = ws.toolbarTabs.item(i)
        _log(f"TAB id={t.id!r} name={t.name!r} visible={t.isVisible}")

    return model_id, timestamp, part_number, local_hub_id


def _bridge_to_cloud(model_id: str, timestamp: str):
    """(2) local mfgdmModelId -> GraphQL componentId + hub.id. Returns the
    GraphQL hub id."""
    _log("=" * 70)
    variables: dict = {"modelId": model_id}
    if timestamp:
        variables["time"] = timestamp
    data = gql(
        """
        query ($modelId: ID!, $time: DateTime) {
          model(modelId: $modelId, time: $time) {
            component { id hub { id } }
          }
        }
        """,
        variables,
    )
    comp = ((data.get("data") or {}).get("model") or {}).get("component") or {}
    gql_component_id = comp.get("id")
    gql_hub_id = (comp.get("hub") or {}).get("id")
    _log(f"GQL component.id (componentId) = {gql_component_id!r}")
    _log(f"GQL component.hub.id (hubId)   = {gql_hub_id!r}")
    return gql_hub_id


# Substrings used to surface the interesting fields on large types.
_FIELD_FILTER = [
    "item", "number", "manage", "lifecycle", "revision", "state", "shar",
    "model", "sibling", "group", "member", "variant", "primary", "part",
    "propert", "descr",
]


def _introspect_type(type_name: str, name_filter=None):
    """Introspect a GraphQL type's fields. Uses the proven literal-name,
    no-description shape (adding `description` or a `$var` name returned a null
    __type). Dumps the raw response if __type is null so we can see why."""
    intro = gql(
        '{ __type(name: "' + type_name + '") { name kind '
        "fields { name type { name kind ofType { name kind } } } } }"
    )
    t = (intro.get("data") or {}).get("__type")
    if not t:
        _log(f"-- {type_name}: __type is NULL — raw: " + json.dumps(intro)[:1200])
        return
    fields = t.get("fields") or []
    _log(f"-- {type_name}: kind={t.get('kind')!r} ({len(fields)} fields) --")
    _log("  ALL FIELD NAMES: " + ", ".join(f.get("name") or "?" for f in fields))
    if not name_filter:
        return
    shown = 0
    for f in fields:
        nm = f.get("name") or ""
        if any(s in nm.lower() for s in name_filter):
            shown += 1
            _log("  " + json.dumps(f))
    if shown == 0:
        _log(f"  (no {type_name} fields matched the filter)")


def _introspect_shared_part_number_info():
    """(3a) SharedPartNumberInfo + locate the Item Number and any group-membership
    fields on Component / Model / Query (item number is cloud, not an attribute)."""
    _log("=" * 70)
    _introspect_type("SharedPartNumberInfo", _FIELD_FILTER)
    _introspect_type("Component", _FIELD_FILTER)
    _introspect_type("Model", _FIELD_FILTER)
    _introspect_type("Query", _FIELD_FILTER)


def _query_shared_part_number(gql_hub_id, local_hub_id, part_number):
    """(3b/3c) Run sharedPartNumber with the REAL fields using the GraphQL hub id
    (expected correct) and, as a control, the local hub id (expected to fail)."""
    _log("=" * 70)
    shared_q = """
        query ($hubId: ID!, $partNumber: String!) {
          sharedPartNumber(hubId: $hubId, partNumber: $partNumber) {
            isPresent
            isModeled
            partNumber { value displayValue }
            component { id }
          }
        }
    """
    _log(f"sharedPartNumber (GraphQL hub id) for partNumber={part_number!r}:")
    _log(json.dumps(gql(shared_q, {"hubId": gql_hub_id, "partNumber": part_number}), indent=2))

    if local_hub_id and local_hub_id != gql_hub_id:
        _log("sharedPartNumber (LOCAL activeHub.id — control, expected to fail/differ):")
        _log(json.dumps(gql(shared_q, {"hubId": local_hub_id, "partNumber": part_number}), indent=2))
    else:
        _log("ID CHECK: local activeHub.id == gql hub.id (or local id missing) — "
             "no separate control run.")


def _scalar_field_names(type_name: str):
    """Return the SCALAR (or NON_NULL SCALAR) field names of a GraphQL type."""
    intro = gql(
        '{ __type(name: "' + type_name + '") { fields { name '
        "type { name kind ofType { name kind } } } } }"
    )
    t = (intro.get("data") or {}).get("__type") or {}
    names = []
    for f in t.get("fields") or []:
        ty = f.get("type") or {}
        inner = ty.get("ofType") or {}
        if ty.get("kind") == "SCALAR" or inner.get("kind") == "SCALAR":
            if f.get("name"):
                names.append(f["name"])
    return names


def _field_type_name(type_name: str, field_name: str):
    """Return the (unwrapped) type name of one field on a GraphQL type."""
    intro = gql(
        '{ __type(name: "' + type_name + '") { fields { name '
        "type { name kind ofType { name kind } } } } }"
    )
    t = (intro.get("data") or {}).get("__type") or {}
    for f in t.get("fields") or []:
        if f.get("name") == field_name:
            ty = f.get("type") or {}
            return ty.get("name") or (ty.get("ofType") or {}).get("name")
    return None


def _finalize_item_and_group(model_id, timestamp, gql_hub_id, part_number):
    """(4) Nail the two seams: read the item number (via ItemNumber.sequenceProperty)
    and the TRUE shared-group size (via Models.pagination + isAllReadableByUser),
    building sub-selections dynamically so the queries are always valid."""
    _log("=" * 70)
    _log(f"FINALIZE [{SCRIPT_VERSION}]: resolve nested shapes dynamically, then real reads")

    seq_type = _field_type_name("ItemNumber", "sequenceProperty")
    seq_scalars = _scalar_field_names(seq_type) if seq_type else []
    pag_type = _field_type_name("Models", "pagination")
    pag_scalars = _scalar_field_names(pag_type) if pag_type else []
    _log(f"ItemNumber.sequenceProperty type={seq_type!r} scalars={seq_scalars}")
    _log(f"Models.pagination type={pag_type!r} scalars={pag_scalars}")

    time_vars = {"m": model_id}
    if timestamp:
        time_vars["t"] = timestamp

    # (a) Read this model's item number.
    seq_sel = " ".join(seq_scalars) or "id"
    q_item = (
        "query ($m: ID!, $t: DateTime) { model(modelId: $m, time: $t) { component { "
        "itemNumber { id sequenceProperty { " + seq_sel + " } } partNumber { value } } } }"
    )
    _log("READ model.component.itemNumber:")
    _log(json.dumps(gql(q_item, time_vars), indent=2)[:2500])

    # (b) TRUE shared-group size for the current part number.
    pag_sel = " ".join(pag_scalars) or "cursor"
    q_group = (
        "query ($h: ID!, $p: String!) { sharedPartNumber(hubId: $h, partNumber: $p) { "
        "isPresent isModeled component { primaryModel { id } "
        "models { isAllReadableByUser pagination { " + pag_sel + " } results { id } } } } }"
    )
    _log("READ sharedPartNumber.component.models (full — pagination + readability):")
    _log(json.dumps(gql(q_group, {"h": gql_hub_id, "p": part_number}), indent=2)[:3000])


def _process_design(design: adsk.fusion.Design, source: str) -> bool:
    """Full read-only flow for one design. Returns True if the cloud calls ran,
    False if cloud metadata (mfgdmModelId) was not yet available."""
    model_id, timestamp, part_number, local_hub_id = _dump_local_facts(design)
    if not model_id:
        _log(f"[{source}] No mfgdmModelId yet — the model isn't cloud-registered. "
             f"Save the design (or wait for the mfgdmDataReady event) and re-run.")
        return False

    gql_hub_id = _bridge_to_cloud(model_id, timestamp)
    _log("=" * 70)
    _log(f"ID CHECK  local activeHub.id == gql hub.id ?  -> {local_hub_id == gql_hub_id}")

    _introspect_shared_part_number_info()
    _query_shared_part_number(gql_hub_id, local_hub_id, part_number)
    _finalize_item_and_group(model_id, timestamp, gql_hub_id, part_number)
    _log("=" * 70)
    _log(f"[{source}] EXPERIMENT COMPLETE — copy the lines above into the implementation.")
    return True


class MFGDMReadyHandler(adsk.core.MFGDMDataEventHandler):
    """Fires once cloud metadata (mfgdmModelId) is guaranteed available — the
    documented, reliable point to read model ids and call the MFGDM API. Note:
    this does NOT re-fire for a document that was already open before the handler
    was added, which is why run() also does an immediate best-effort pass."""

    def notify(self, args: adsk.core.MFGDMDataEventArgs):
        try:
            product = args.document.products.itemByProductType("DesignProductType")
            design = adsk.fusion.Design.cast(product)
            if design is None:
                _log("mfgdmDataReady: document is not a design — skipping.")
                return
            _process_design(design, "mfgdmDataReady")
        except Exception:
            _log("EXPERIMENT ERROR (event):\n" + traceback.format_exc())


def run(_context):
    """Fusion script entry point."""
    global _handler
    try:
        _handler = MFGDMReadyHandler()
        app.mfgdmDataReady.add(_handler)
        _log(f"SyncItemExperiment {SCRIPT_VERSION}: registered mfgdmDataReady handler.")

        # Immediate best-effort pass for the already-open, already-registered
        # document — mfgdmDataReady does NOT re-fire for a doc that was open
        # before this script started, so don't just wait on the event.
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            _log("No active design — open your shared-group design; the "
                 "mfgdmDataReady event will run it, or re-run this script.")
        elif not _process_design(design, "immediate"):
            _log("Waiting for mfgdmDataReady... (save or re-open the design to trigger it).")

        # Keep the script alive so the event can still fire; Stop it from the
        # Scripts and Add-Ins dialog when done.
        adsk.autoTerminate(False)
    except Exception:
        _log("SyncItemExperiment failed to start:\n" + traceback.format_exc())


def stop(_context):
    """Called when the script is stopped from Scripts and Add-Ins."""
    global _handler
    try:
        if _handler is not None:
            app.mfgdmDataReady.remove(_handler)
    except Exception:
        _log("SyncItemExperiment: error removing handler:\n" + traceback.format_exc())
    finally:
        _handler = None
