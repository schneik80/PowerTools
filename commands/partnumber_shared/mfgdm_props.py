# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
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
        raise MfgdmPropsError(
            f"MFGDM HTTP {resp.statusCode}: {resp.data[:500]}"
        )

    parsed = json.loads(resp.data)
    if parsed.get("errors"):
        raise MfgdmPropsError(
            "MFGDM GraphQL errors: "
            + json.dumps(parsed["errors"], default=str)
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
    collections = ((hub.get("propertyDefinitionCollections") or {}).get("results")) or []
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


def set_component_custom_property(model_id: str,
                                  property_name: str,
                                  value: Any) -> str:
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
        raise MfgdmPropsError(
            f"No component returned for modelId={model_id!r}."
        )
    if not comp.get("isWritableByUser", False):
        raise MfgdmPropsError(
            "Component is not writable by the current user "
            "(isWritableByUser=False)."
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
        raise MfgdmPropsError(
            f"Custom property {property_name!r} is read-only."
        )

    # 2. setProperties mutation — targetId is the componentId (time-specific).
    mut = _gql(_M_SET_PROPERTIES, {
        "input": {
            "targetId": comp_id,
            "propertyInputs": [
                {"propertyDefinitionId": defn_id, "value": value},
            ],
        },
    })
    echoed = ((mut.get("setProperties") or {}).get("properties")) or []
    if not echoed:
        raise MfgdmPropsError("setProperties returned no property echo.")
    return str(echoed[0].get("value", ""))
