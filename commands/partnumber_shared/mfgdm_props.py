# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""MFGDM GraphQL helpers for reading and writing component custom properties.

The Fusion Desktop Python API does **not** expose user-defined custom
properties via ``Component.propertyGroups`` — that API only surfaces the
built-in "General" group (Part Name, Part Number, Description). Custom
properties like "Drawing Number" live in MFGDM and must be accessed via
the ``mfgdm://v3`` GraphQL endpoint.

Autodesk's public documentation states that ``setProperties`` is blocked
from the Fusion Desktop API (see
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/MFGDMAPI_UM.htm).
In practice, empirical testing shows the mutation succeeds against a
user's **own** Custom Properties collection when three conditions hold:

    1. ``targetId`` is the **componentId** (time-specific, obtained from
       ``model(modelId).component.id``) — NOT the ``mfgdmModelId``.
       Using the modelId returns ``"The targetId is not a valid Component
       or Drawing ID."``.
    2. The property's ``definition.isReadOnly`` is ``False``.
    3. The component's ``isWritableByUser`` is ``True``.

This module encapsulates those rules so callers don't have to rediscover
them.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import adsk.core

MFGDM_URL = "mfgdm://v3"


class MfgdmPropsError(Exception):
    """General failure in the MFGDM property helpers."""


class PropertyNotFoundError(MfgdmPropsError):
    """Raised when a named custom property isn't defined on the component.

    Callers typically treat this distinctly from other errors because it
    implies the user's hub / property-definition collection needs to be
    configured, not that the command itself has a bug.
    """


# ---------------------------------------------------------------------------
# GraphQL client
# ---------------------------------------------------------------------------


def gql(query: str, variables: Optional[dict] = None) -> dict:
    """Public alias for :func:`_gql`.

    The transport - Fusion's own ``HttpRequest`` against ``mfgdm://v3``, which
    attaches the signed-in user's credentials - is the reusable part of this
    module. Document History reads version authorship over the same endpoint
    and has no business reaching for a private name to do it.
    """
    return _gql(query, variables)


def _gql(query: str, variables: Optional[dict] = None) -> dict:
    """POST a GraphQL query/mutation and return the ``data`` object.

    Raises :class:`MfgdmPropsError` on HTTP error or GraphQL ``errors``.
    """
    req = adsk.core.HttpRequest.create(MFGDM_URL, adsk.core.HttpMethods.PostMethod)
    req.setHeader("Content-type", "application/json; charset=utf-8")
    payload: dict = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    req.data = json.dumps(payload)
    resp = req.executeSync()

    if resp.statusCode != 200:
        raise MfgdmPropsError(f"MFGDM HTTP {resp.statusCode}: {resp.data[:500]}")

    parsed = json.loads(resp.data)
    if parsed.get("errors"):
        raise MfgdmPropsError(
            "MFGDM GraphQL errors: " + json.dumps(parsed["errors"], default=str)
        )
    return parsed.get("data", {})


# ---------------------------------------------------------------------------
# Queries / mutations
# ---------------------------------------------------------------------------


_Q_FETCH_COMPONENT = """
query($modelId: ID!) {
  model(modelId: $modelId) {
    component {
      id
      isWritableByUser
      hub { id }
      allProperties {
        results {
          name
          value
          definition {
            id
            name
            isReadOnly
          }
        }
      }
    }
  }
}
"""
# NOTE: ``allProperties.results`` returns properties that currently have
# a value on the component *plus* the component's built-in base properties.
# It does **not** include user-defined custom properties whose value has
# never been set on this particular component — those show up only after
# they're assigned a value. For the first-ever write of a property to a
# component, we therefore fall back to :func:`_find_definition_in_hub`
# which walks the hub's PropertyDefinitionCollections directly.


_Q_HUB_PROPERTY_DEFINITIONS = """
query($hubId: ID!) {
  hub(hubId: $hubId) {
    propertyDefinitionCollections {
      results {
        id
        name
        definitions {
          results {
            id
            name
            isReadOnly
            isArchived
          }
        }
      }
    }
  }
}
"""


_M_SET_PROPERTIES = """
mutation($input: SetPropertiesInput!) {
  setProperties(input: $input) {
    targetId
    properties {
      name
      value
      definition { id name }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _find_definition_in_hub(hub_id: str, property_name: str) -> Optional[dict]:
    """Walk the hub's property-definition collections looking for a
    definition named ``property_name``.

    Returns a dict ``{"id": ..., "isReadOnly": bool, "collection_name": str}``
    for the first matching non-archived definition, or ``None`` if no
    match exists anywhere in the hub.

    This is the slow-path lookup used when ``Component.allProperties``
    doesn't surface the definition (the common case when the property
    has never been set on this particular component).
    """
    if not hub_id:
        return None

    try:
        data = _gql(_Q_HUB_PROPERTY_DEFINITIONS, {"hubId": hub_id})
    except MfgdmPropsError:
        # Any failure here just falls through to "not found" — the caller
        # will raise PropertyNotFoundError with the usual setup-guide
        # message, which is the correct UX.
        return None

    hub = data.get("hub") or {}
    collections = (
        (hub.get("propertyDefinitionCollections") or {}).get("results")
    ) or []
    for coll in collections:
        defs = ((coll.get("definitions") or {}).get("results")) or []
        for defn in defs:
            if defn.get("name") != property_name:
                continue
            if defn.get("isArchived"):
                continue
            return {
                "id": defn.get("id"),
                "isReadOnly": bool(defn.get("isReadOnly")),
                "collection_name": coll.get("name") or "",
            }
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def set_component_custom_property(model_id: str, property_name: str, value: Any) -> str:
    """Set ``property_name`` on the component identified by ``model_id``.

    Lookup is two-tier:

    1. **Fast path** — ``Component.allProperties`` is scanned first. When
       the property has an existing value (or is a base property) this
       surfaces its definition id immediately.
    2. **Hub fallback** — if step 1 misses, the hub's
       ``propertyDefinitionCollections`` are walked to find a non-archived
       definition of the given ``property_name``. This handles the
       first-ever write case for a component that has never had the
       property set.

    Returns the new value as echoed back by the server.

    Raises:
        :class:`PropertyNotFoundError` — the property is not defined
            anywhere in the hub's property-definition collections.
        :class:`MfgdmPropsError` — any other failure (HTTP, auth,
            read-only property, component not writable, etc.).
    """
    if not model_id:
        raise MfgdmPropsError("No MFGDM model id provided.")

    # 1. Fetch componentId + the component's current property snapshot.
    data = _gql(_Q_FETCH_COMPONENT, {"modelId": model_id})
    model = data.get("model") or {}
    comp = model.get("component") or {}
    comp_id = comp.get("id")
    if not comp_id:
        raise MfgdmPropsError(f"No component returned for modelId={model_id!r}.")
    if not comp.get("isWritableByUser", False):
        raise MfgdmPropsError(
            "Component is not writable by the current user (isWritableByUser=False)."
        )

    defn_id: Optional[str] = None
    defn_read_only = False

    # Fast path: component's own property list.
    results = ((comp.get("allProperties") or {}).get("results")) or []
    target = next((p for p in results if p.get("name") == property_name), None)
    if target is not None:
        defn = target.get("definition") or {}
        defn_id = defn.get("id")
        defn_read_only = bool(defn.get("isReadOnly"))

    # Fallback: walk the hub's PropertyDefinitionCollections. This covers
    # the first-ever write case where the property has a definition in the
    # hub but has never been assigned a value on this component, so it is
    # absent from allProperties.
    if not defn_id:
        hub_id = ((comp.get("hub") or {}).get("id")) or ""
        match = _find_definition_in_hub(hub_id, property_name)
        if match is None:
            raise PropertyNotFoundError(
                f"Custom property {property_name!r} is not defined in "
                f"this hub's property-definition collections."
            )
        defn_id = match["id"]
        defn_read_only = match["isReadOnly"]

    if not defn_id:
        raise MfgdmPropsError(
            f"Custom property {property_name!r} has no definition id."
        )
    if defn_read_only:
        raise MfgdmPropsError(f"Custom property {property_name!r} is read-only.")

    # 2. setProperties mutation — targetId is the componentId (time-specific).
    mut = _gql(
        _M_SET_PROPERTIES,
        {
            "input": {
                "targetId": comp_id,
                "propertyInputs": [
                    {"propertyDefinitionId": defn_id, "value": value},
                ],
            },
        },
    )
    echoed = ((mut.get("setProperties") or {}).get("properties")) or []
    if not echoed:
        raise MfgdmPropsError("setProperties returned no property echo.")
    return str(echoed[0].get("value", ""))


# ---------------------------------------------------------------------------
# Item Number / Part Number (cloud values) + shared-part-number status
#
# The Fusion Manage "Item Number" is a cloud property with no local Desktop API
# accessor, so it is read via GraphQL. The local ``mfgdmModelId`` anchors the
# query; the time-specific componentId and the MDM ``hub.id`` come from the
# server. IMPORTANT: cloud queries need ``Component.hub.id`` (``urn:adsk...``),
# NOT the local ``app.data.activeHub.id`` (``a.<base64>``), which the service
# rejects with "Invalid hub or project id. It must start with 'urn:adsk'."
# ---------------------------------------------------------------------------


_Q_ITEM_PART_HUB = """
query ($modelId: ID!, $time: DateTime) {
  model(modelId: $modelId, time: $time) {
    component {
      hub { id }
      itemNumber { id }
      partNumber { value }
    }
  }
}
"""


def fetch_item_part_hub(model_id: str, timestamp: str = "") -> tuple:
    """Return ``(item_number, part_number, hub_id)`` for a model's component.

    - ``item_number`` — the Fusion Manage Item Number (``Component.itemNumber.id``,
      e.g. ``"PN-000038"``), or "" when none is assigned.
    - ``part_number`` — ``Component.partNumber.value`` (cloud-authoritative), or "".
    - ``hub_id`` — the MDM ``Component.hub.id`` needed by :func:`is_part_number_shared`.

    Raises :class:`MfgdmPropsError` on transport / GraphQL failure.
    """
    if not model_id:
        raise MfgdmPropsError("No MFGDM model id provided.")
    variables: dict = {"modelId": model_id}
    if timestamp:
        variables["time"] = timestamp
    data = _gql(_Q_ITEM_PART_HUB, variables)
    comp = ((data.get("model") or {}).get("component")) or {}
    item_number = ((comp.get("itemNumber") or {}).get("id")) or ""
    part_number = ((comp.get("partNumber") or {}).get("value")) or ""
    hub_id = ((comp.get("hub") or {}).get("id")) or ""
    return item_number, part_number, hub_id


_Q_SHARED_PART_NUMBER = """
query ($hubId: ID!, $partNumber: String!) {
  sharedPartNumber(hubId: $hubId, partNumber: $partNumber) {
    isPresent
    isModeled
    component {
      models {
        isAllReadableByUser
        pagination { cursor }
        results { id }
      }
    }
  }
}
"""


def is_part_number_shared(hub_id: str, part_number: str) -> bool:
    """Return True if ``part_number`` is in a shared part number group (2+ models).

    ``hub_id`` must be the MDM hub id (``urn:adsk...``) from
    :func:`fetch_item_part_hub`, not the local ``activeHub.id``.

    "Shared" means the part number is present and modeled AND its component's
    ``models`` collection resolves to more than one member. That collection is
    permission-filtered and paginated, so membership is inferred from any of:
    more than one returned result, ``isAllReadableByUser == False`` (the group
    holds models this user can't read), or a non-empty pagination cursor (more
    members beyond the first page).

    Raises :class:`MfgdmPropsError` on transport / GraphQL failure.
    """
    if not hub_id or not part_number:
        return False
    data = _gql(_Q_SHARED_PART_NUMBER, {"hubId": hub_id, "partNumber": part_number})
    info = data.get("sharedPartNumber") or {}
    if not info.get("isPresent") or not info.get("isModeled"):
        return False
    models = ((info.get("component") or {}).get("models")) or {}
    results = models.get("results") or []
    all_readable = models.get("isAllReadableByUser", True)
    cursor = ((models.get("pagination") or {}).get("cursor")) or ""
    return len(results) > 1 or (not all_readable) or bool(cursor)
