# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Update Wire command.

Resolution logic for rebuilding a routed wire from its stored route
attribute: matching each route end back to a connector occurrence, finding
the wire record on that connector, and validating the stored build
parameters. The route payload format is defined by
``commands/cable_shared/routing.py``; the attribute schema constants live
in ``commands/cable_shared/schema.py`` (imported as ``schema``).
"""

from __future__ import annotations

from ..cable_shared import schema

HOW_TOKEN = "token"
HOW_CONNECTOR_ID = "connector_id"
REASON_AMBIGUOUS = "ambiguous"
REASON_NOT_FOUND = "not_found"


def choose_end_occurrence(candidates: list[dict], end: dict) -> tuple[int | None, str]:
    """Pick the candidate occurrence for one route end.

    Args:
        candidates: One dict per occurrence, in order, with ``token_match``
            (True when the stored occurrence token RESOLVED to this
            occurrence) and ``connector_id`` (its component's connector id,
            "" when it has none). The caller resolves tokens with Fusion's
            ``Design.findEntityByToken`` - never by comparing token strings,
            which the API documents as unstable (the same entity can return
            different token strings over time).
        end: A route-payload end with ``connector_id``.

    Resolution ladder: a UNIQUE token resolution wins (it survives renames
    and disambiguates multiple instances of the same connector); otherwise
    a UNIQUE connector-id match (the token died - document copied or
    connector reinserted); otherwise unresolvable.

    Returns:
        ``(index, how)`` on success with how :data:`HOW_TOKEN` or
        :data:`HOW_CONNECTOR_ID`; ``(None, reason)`` with reason
        :data:`REASON_AMBIGUOUS` or :data:`REASON_NOT_FOUND`.
    """
    token_matches = [
        index
        for index, candidate in enumerate(candidates)
        if candidate.get("token_match")
    ]
    if len(token_matches) == 1:
        return token_matches[0], HOW_TOKEN
    connector_id = end.get("connector_id") or ""
    if connector_id:
        matches = [
            index
            for index, candidate in enumerate(candidates)
            if connector_id == (candidate.get("connector_id") or "")
        ]
        if len(matches) == 1:
            return matches[0], HOW_CONNECTOR_ID
        if len(matches) > 1:
            return None, REASON_AMBIGUOUS
    return None, REASON_NOT_FOUND


def find_wire(wires: dict, wire_id: str, pin: str) -> dict | None:
    """Find a connector's wire record by wire id (preferred) or pin.

    Args:
        wires: ``{pin: record}`` as returned by ``builder.read_connector``;
            records carry a ``wire_id``.
        wire_id: The stable id stored in the route payload.
        pin: Fallback lookup key when the wire id is gone (wire redefined).
    """
    for record in wires.values():
        if wire_id and record.get("wire_id") == wire_id:
            return record
    return wires.get(pin)


def coerce_cable_od_mm(payload: dict) -> float | None:
    """The stored cable jacket OD in mm, or None when absent or damaged."""
    try:
        od_mm = float(payload.get("cable_od_mm"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return od_mm if od_mm > 0 else None


def match_cable_wires(wires: dict, wire_ids: list, pins: list) -> tuple[list, list]:
    """Resolve a cable end's stored wire list against live connector data.

    Args:
        wires: ``{pin: record}`` from ``builder.read_connector``.
        wire_ids: The route payload's ordered wire-id list for this end.
        pins: The payload's ordered pin list (index-paired with wire_ids).

    Each stored ``(wire_id, pin)`` resolves via :func:`find_wire` (wire id
    preferred, pin fallback - so renamed pins keep their original pairing).

    Returns:
        ``(records, missing)`` - resolved wire records in stored order, and
        display labels for entries that no longer exist on the connector.
    """
    records: list = []
    missing: list = []
    ids = [str(wire_id) for wire_id in (wire_ids or [])]
    pin_list = [str(pin) for pin in (pins or [])]
    for index in range(max(len(ids), len(pin_list))):
        wire_id = ids[index] if index < len(ids) else ""
        pin = pin_list[index] if index < len(pin_list) else ""
        record = find_wire(wires, wire_id, pin)
        if record is None:
            missing.append(pin or wire_id or f"#{index + 1}")
        else:
            records.append(record)
    return records, missing


def match_multi_cable_wires(
    sides_wires: list, wire_ids: list, pins: list, wire_connectors: list
) -> tuple[list, list]:
    """Resolve a cable end's stored wires when the end spans connectors.

    Args:
        sides_wires: One ``{pin: record}`` dict (from
            ``builder.read_connector``) per resolved connector of the end,
            in stored connector order.
        wire_ids: The route payload's ordered wire-id list for this end.
        pins: The payload's ordered pin list (index-paired with wire_ids).
        wire_connectors: Per-wire connector indices (index-paired); a
            missing entry defaults to connector 0 (the legacy
            single-connector shape), junk or out-of-range entries make
            that wire missing.

    Each stored wire resolves via :func:`find_wire` on ITS OWN connector's
    wires (wire id preferred, pin fallback).

    Returns:
        ``(pairs, missing)`` - ``(connector_index, record)`` tuples in
        stored order, and display labels for wires that no longer resolve.
    """
    pairs: list = []
    missing: list = []
    ids = [str(wire_id) for wire_id in (wire_ids or [])]
    pin_list = [str(pin) for pin in (pins or [])]
    indices = list(wire_connectors or [])
    for index in range(max(len(ids), len(pin_list))):
        wire_id = ids[index] if index < len(ids) else ""
        pin = pin_list[index] if index < len(pin_list) else ""
        try:
            connector = int(indices[index]) if index < len(indices) else 0
        except (TypeError, ValueError):
            connector = -1
        record = None
        if 0 <= connector < len(sides_wires):
            record = find_wire(sides_wires[connector], wire_id, pin)
        if record is None:
            missing.append(pin or wire_id or f"#{index + 1}")
        else:
            pairs.append((connector, record))
    return pairs, missing


def coerce_route_params(payload: dict) -> dict | None:
    """Extract validated build parameters from a route payload.

    Returns:
        ``{"name": str, "awg": int, "od_mm": float}`` ready for
        ``builder.build_wire``, or None when the stored data is damaged
        (missing name, non-numeric or out-of-range gauge, non-positive
        diameter).
    """
    name = str(payload.get("name") or "").strip()
    try:
        awg = int(payload.get("awg"))  # type: ignore[call-overload]
        od_mm = float(payload.get("od_mm"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not name or od_mm <= 0:
        return None
    if not (schema.AWG_LOWER_BOUND <= awg <= schema.AWG_UPPER_BOUND):
        return None
    return {"name": name, "awg": awg, "od_mm": od_mm}
