# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""The PowerTools.Cable attribute schema - single source of truth.

Pure and Fusion-free: authored by Define Wires, consumed by Route Wire,
Update Wire, and Wire Report, and unit-tested without a live Fusion
runtime (see ``tests/test_cable_schema.py`` and the schema contract in
``docs/arch/Define Wires.md``).

Every attribute lives in the :data:`ATTR_GROUP` group. The root component holds
one manifest attribute (:data:`MANIFEST_NAME`) indexing the connector's wire
set; each wire point (work point or sketch point) holds one attribute per
``(wire, role)`` named by :func:`point_attr_name`, whose JSON value carries the
full wire record so a future routing command that only holds a point can
recover everything about the wire.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable

ATTR_GROUP = "PowerTools.Cable"
MANIFEST_NAME = "connector"
CABLE_POINT_NAME = "cablepoint"
MEMBER_NAME = "member"
DESIGNATOR_NAME = "designator"
POINT_NAME_PREFIX = "point"
SCHEMA_VERSION = 1
ROLE_CABLE = "cable"

ROLE_START = "start"
ROLE_STRIP = "strip"
ROLE_EXIT = "exit"
ROLES = (ROLE_START, ROLE_STRIP, ROLE_EXIT)

# Member roles stamped on the components a route build creates, so the
# Wire Report can identify children by data instead of display names.
MEMBER_CONDUCTOR = "conductor"
MEMBER_SHEATH = "sheath"
MEMBER_WIRE = "wire"

AWG_LOWER_BOUND = 0
AWG_UPPER_BOUND = 40
AWG_DEFAULT_MIN = 16
AWG_DEFAULT_MAX = 24


def new_id() -> str:
    """Return a short random hex id for wire ids and connector-id suffixes."""
    return uuid.uuid4().hex[:8]


def slugify(name: str, max_len: int = 24) -> str:
    """Reduce *name* to an alnum/dash slug suitable for a connector id.

    Args:
        name: Component name (may contain spaces and punctuation).
        max_len: Maximum slug length before the unique suffix is appended.

    Returns:
        A non-empty slug; ``"connector"`` when *name* has no usable characters.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name or "").strip("-")
    slug = slug[:max_len].rstrip("-")
    return slug or "connector"


def connector_id_for(component_name: str, existing: str | None = None) -> str:
    """Return the connector id, preserving *existing* once assigned.

    The id is generated exactly once per connector (component renames must not
    change it — recorded ids on points would go stale), so any truthy
    *existing* value wins.
    """
    if existing:
        return existing
    return f"{slugify(component_name)}-{new_id()}"


def point_attr_name(wire_id: str, role: str) -> str:
    """Return the attribute name for one wire point, e.g. ``point.7c1d2e3f.start``."""
    return f"{POINT_NAME_PREFIX}.{wire_id}.{role}"


def parse_point_attr_name(name: str) -> tuple[str, str] | None:
    """Parse a point attribute name into ``(wire_id, role)``.

    Returns:
        The ``(wire_id, role)`` pair, or None when *name* is not a
        well-formed point attribute name (wrong prefix, missing parts, or an
        unknown role).
    """
    if not name:
        return None
    parts = name.split(".")
    if len(parts) != 3 or parts[0] != POINT_NAME_PREFIX:
        return None
    wire_id, role = parts[1], parts[2]
    if not wire_id or role not in ROLES:
        return None
    return wire_id, role


def build_point_payload(connector_id: str, wire: dict, role: str) -> str:
    """Serialize the JSON attribute value for one wire point.

    Args:
        connector_id: The owning connector's id.
        wire: Wire fields with keys ``wire_id``, ``pin``, ``awg_min``,
            ``awg_max``.
        role: One of :data:`ROLES`.

    Returns:
        A JSON string carrying the full wire record for this point.
    """
    return json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "connector_id": connector_id,
            "wire_id": wire["wire_id"],
            "role": role,
            "pin": wire["pin"],
            "awg_min": wire["awg_min"],
            "awg_max": wire["awg_max"],
        }
    )


def build_manifest_payload(
    connector_id: str, component_name: str, wires: list[dict]
) -> str:
    """Serialize the root-component manifest attribute value.

    Args:
        connector_id: The connector's stable id.
        component_name: Current component name (display only; may change).
        wires: Ordered wire field dicts (``wire_id``, ``pin``, ``awg_min``,
            ``awg_max``) — order defines the wire display order on recall.

    Returns:
        A JSON string indexing the connector's whole wire set.
    """
    return json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "connector_id": connector_id,
            "name": component_name,
            "wires": [
                {
                    "wire_id": wire["wire_id"],
                    "pin": wire["pin"],
                    "awg_min": wire["awg_min"],
                    "awg_max": wire["awg_max"],
                }
                for wire in wires
            ],
        }
    )


def build_cable_point_payload(connector_id: str) -> str:
    """Serialize the JSON attribute value for a connector's cable point.

    The cable point is where a multi-conductor cable ends at this connector
    and its wires fan out to the pins. One per connector, stored under the
    attribute name :data:`CABLE_POINT_NAME`.
    """
    return json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "connector_id": connector_id,
            "role": ROLE_CABLE,
        }
    )


def build_designator_payload(designator: str) -> str:
    """Serialize a connector's reference-designator attribute value.

    Stored on the connector OCCURRENCE (never the component): designators
    are per instance - two instances of one connector part carry J1 and J2
    - and belong to the assembly document, not the referenced part.
    """
    return json.dumps({"schema": SCHEMA_VERSION, "designator": designator})


def build_member_payload(role: str, pin: str | None = None) -> str:
    """Serialize the member attribute stamped on a built child component.

    The builder stamps every component it creates inside a wire or cable
    assembly (:data:`MEMBER_CONDUCTOR`, :data:`MEMBER_SHEATH`,
    :data:`MEMBER_WIRE`) under the name :data:`MEMBER_NAME`, so the Wire
    Report can find and label children by data instead of display names -
    which users can rename and Fusion suffixes for uniqueness.

    Args:
        role: One of the member role constants.
        pin: The wire's pin, for :data:`MEMBER_WIRE` members.
    """
    payload: dict = {"schema": SCHEMA_VERSION, "role": role}
    if pin is not None:
        payload["pin"] = pin
    return json.dumps(payload)


def next_pin(pins: Iterable[str]) -> str:
    """Default pin name for a new wire: highest numeric pin + 1.

    Non-numeric pin names are ignored; with no numeric pins the first
    default is ``"1"``. The user can always edit the result. int() is the
    numeric arbiter: str.isdigit() alone is not enough because it accepts
    unicode digits (superscripts, circled numbers) that int() rejects with
    ValueError, and pins are free text.
    """
    numbers = []
    for pin in pins:
        text = str(pin).strip()
        if not text.isdigit():
            continue
        try:
            numbers.append(int(text))
        except ValueError:
            continue  # unicode digit that int() rejects
    return str(max(numbers) + 1) if numbers else "1"


def parse_payload(value: str | None) -> dict | None:
    """Parse a JSON attribute value written by this command.

    Tolerant by design (attribute values may be hand-edited or written by a
    future schema): returns None for invalid JSON, non-dict JSON, or an
    unknown schema version. Extra keys are preserved.
    """
    try:
        data = json.loads(value) if value else None
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema") != SCHEMA_VERSION:
        return None
    return data


def group_attributes_into_wires(records: Iterable[tuple[str, str, bool]]) -> dict:
    """Bucket raw attribute records into manifest / wires / orphans / bad.

    Args:
        records: ``(name, value, has_parent)`` tuples for every attribute in
            :data:`ATTR_GROUP`. ``has_parent`` is False when the owning entity
            was deleted outside the command (``attribute.parent is None``).

    Returns:
        A dict with keys:
        ``manifest`` — parsed manifest payload or None;
        ``cable`` — ``{"payload": dict, "has_parent": bool}`` for the
        connector's cable point attribute, or None;
        ``wires`` — ``{wire_id: {role: {"payload": dict, "has_parent": bool}}}``;
        ``orphans`` — ``(name, payload)`` for parentless point attributes
        (also present in ``wires`` with ``has_parent`` False);
        ``bad`` — names that failed to parse (cleanup candidates).
    """
    manifest: dict | None = None
    cable: dict | None = None
    wires: dict = {}
    orphans: list = []
    bad: list = []
    for name, value, has_parent in records:
        payload = parse_payload(value)
        if name == MANIFEST_NAME:
            if payload is None:
                bad.append(name)
            else:
                manifest = payload
            continue
        if name == CABLE_POINT_NAME:
            if payload is None:
                bad.append(name)
            else:
                cable = {"payload": payload, "has_parent": has_parent}
            continue
        parsed = parse_point_attr_name(name)
        if parsed is None or payload is None:
            bad.append(name)
            continue
        wire_id, role = parsed
        if not has_parent:
            orphans.append((name, payload))
        wires.setdefault(wire_id, {})[role] = {
            "payload": payload,
            "has_parent": has_parent,
        }
    return {
        "manifest": manifest,
        "cable": cable,
        "wires": wires,
        "orphans": orphans,
        "bad": bad,
    }


def ordered_wire_ids(manifest: dict | None, wires: dict) -> list[str]:
    """Return wire ids in display order.

    Manifest order first (it records the order the user built), then any
    point-only wires the manifest does not know about (stale/missing
    manifest), sorted by pin for a stable result.
    """
    ordered: list[str] = []
    if manifest:
        for entry in manifest.get("wires", []):
            wire_id = entry.get("wire_id") if isinstance(entry, dict) else None
            if wire_id and wire_id in wires and wire_id not in ordered:
                ordered.append(wire_id)

    def pin_of(wire_id: str) -> str:
        return wire_fields(wires[wire_id])["pin"]

    leftovers = sorted((w for w in wires if w not in ordered), key=pin_of)
    ordered.extend(leftovers)
    return ordered


def manifest_entry(manifest: dict | None, wire_id: str) -> dict | None:
    """Return the manifest's wire entry for *wire_id*, or None."""
    if not manifest:
        return None
    for entry in manifest.get("wires", []):
        if isinstance(entry, dict) and entry.get("wire_id") == wire_id:
            return entry
    return None


def coerce_awg(value: object, fallback: int) -> int:
    """Coerce *value* to an in-range AWG int, else return *fallback*."""
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return fallback
    if AWG_LOWER_BOUND <= number <= AWG_UPPER_BOUND:
        return number
    return fallback


def wire_fields(roles: dict, fallback: dict | None = None) -> dict:
    """Extract display fields (pin, awg_min, awg_max) for one recalled wire.

    Prefers the first available point payload (in :data:`ROLES` order), then
    the manifest entry (*fallback*), then defaults — so a wire remains
    editable even when some of its attributes are damaged or orphaned.
    """
    for role in ROLES:
        entry = roles.get(role)
        payload = entry.get("payload") if entry else None
        if payload:
            return _fields_from(payload)
    if fallback:
        return _fields_from(fallback)
    return {"pin": "", "awg_min": AWG_DEFAULT_MIN, "awg_max": AWG_DEFAULT_MAX}


def _fields_from(data: dict) -> dict:
    return {
        "pin": str(data.get("pin") or ""),
        "awg_min": coerce_awg(data.get("awg_min"), AWG_DEFAULT_MIN),
        "awg_max": coerce_awg(data.get("awg_max"), AWG_DEFAULT_MAX),
    }


def validate_awg_range(awg_min: object, awg_max: object) -> str:
    """Validate an AWG range; return "" when valid, else the reason.

    The range is numeric AWG: ``awg_min`` is the smallest AWG number
    (thickest wire) and must not exceed ``awg_max``.
    """
    if not isinstance(awg_min, int) or not isinstance(awg_max, int):
        return "Gauge values must be whole AWG numbers."
    in_bounds = (
        AWG_LOWER_BOUND <= awg_min <= AWG_UPPER_BOUND
        and AWG_LOWER_BOUND <= awg_max <= AWG_UPPER_BOUND
    )
    if not in_bounds:
        return (
            f"Gauge values must be between {AWG_LOWER_BOUND} and {AWG_UPPER_BOUND} AWG."
        )
    if awg_min > awg_max:
        return "Min gauge must not exceed max gauge."
    return ""


def validate_wires(wires: list[dict]) -> list[str]:
    """Validate the whole wire set; return a list of problems (empty = valid).

    Args:
        wires: One summary dict per wire with keys ``pin``, ``awg_min``,
            ``awg_max``, and ``points_set`` (how many of the three points are
            selected, 0-3).
    """
    problems: list[str] = []
    if not wires:
        return ["Add at least one wire."]
    for index, wire in enumerate(wires, start=1):
        label = f"Wire {index}"
        if not (wire.get("pin") or "").strip():
            problems.append(f"{label}: pin is empty.")
        if wire.get("points_set", 0) != len(ROLES):
            problems.append(f"{label}: needs all three points selected.")
        reason = validate_awg_range(wire.get("awg_min"), wire.get("awg_max"))
        if reason:
            problems.append(f"{label}: {reason}")
    pins = [(wire.get("pin") or "").strip() for wire in wires]
    duplicates = sorted({pin for pin in pins if pin and pins.count(pin) > 1})
    if duplicates:
        problems.append("Duplicate pin(s): " + ", ".join(duplicates))
    return problems


def diff_wires(
    existing_ids: Iterable[str],
    desired_ids: Iterable[str],
    deleted_ids: Iterable[str],
) -> dict:
    """Split wire ids into add / update / remove sets.

    A wire id in *deleted_ids* is always removed, even if it also appears
    desired (deletion wins — the user explicitly removed that row). ``remove``
    only contains ids that actually exist, so callers can delete blindly.
    """
    existing = set(existing_ids)
    deleted = set(deleted_ids)
    desired = set(desired_ids) - deleted
    return {
        "add": desired - existing,
        "update": desired & existing,
        "remove": (existing - desired) | (deleted & existing),
    }
