# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free routing math for the Cable command family.

AWG sizing math, the allowed-gauge intersections, the guide-point fallback
used when 3D-sketch tangency constraints are unavailable, the route
attribute payload stamped on built assemblies, and the shared build-result
summary notes. The attribute schema itself (group name, payload parsing)
lives in ``commands/cable_shared/schema.py`` and is imported here as
``schema`` — that module remains the single source of truth for the
PowerTools.Cable group.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable

from . import schema

ROUTE_NAME = "route"

# Route kinds stored in the route payload's "kind" field.
KIND_SINGLE = "single"
KIND_CABLE = "cable"
KIND_RIBBON = "ribbon"

# Default insulation wall thickness used for the recommended sheathed outer
# diameter (rule of thumb for common hookup wire, e.g. UL1007-class).
WALL_MM_DEFAULT = 0.45

# How far past each connector exit the fallback spline guide points reach,
# as a fraction of the exit-to-exit distance.
GUIDE_FRACTION = 0.25

# How far an implied (multi-connector) cable end anchor is pulled from the
# connectors' cable-point centroid toward the midpoint of the cable run.
CABLE_END_PULL = 0.10

# Bundle diameter factors for n identical round wires (standard cable-design
# circle-packing table, cf. Standard Wire & Cable / Glenair bundle charts);
# bundle OD = wire OD * factor. Beyond the table the dense-packing
# approximation 1.155 * sqrt(n) is used (continuous: n=12 -> 4.0).
_BUNDLE_FACTORS = {
    1: 1.0,
    2: 2.0,
    3: 2.155,
    4: 2.414,
    5: 2.7,
    6: 3.0,
    7: 3.0,
    8: 3.31,
    9: 3.61,
    10: 3.81,
    11: 3.92,
    12: 4.03,
}
CABLE_JACKET_WALL_MM = 0.6
CABLE_LAY_FACTOR = 1.03  # twist/lay allowance over the ideal packed bundle

# Wire insulation colors offered when routing (key -> sRGB). The tuple
# order IS the assignment sequence for multi-conductor cables: wires are
# colored in paired-pin order, cycling when a cable has more than twelve.
WIRE_COLORS = (
    ("red", (192, 32, 32)),
    ("black", (25, 25, 25)),
    ("white", (235, 235, 235)),
    ("grey", (128, 128, 128)),
    ("brown", (121, 68, 32)),
    ("yellow", (235, 200, 40)),
    ("dark blue", (24, 48, 128)),
    ("light blue", (96, 168, 224)),
    ("purple", (112, 48, 160)),
    ("pink", (232, 128, 168)),
    ("light green", (112, 200, 96)),
    ("dark green", (24, 112, 48)),
)
WIRE_COLOR_KEYS = tuple(key for key, _rgb in WIRE_COLORS)
DEFAULT_WIRE_COLOR = WIRE_COLOR_KEYS[0]
_WIRE_COLOR_RGB = dict(WIRE_COLORS)

# Cable jackets are always black; conductor bodies are always copper (the
# builder prefers the library's polished copper, tinting this as fallback).
JACKET_COLOR = "black"
CONDUCTOR_RGB = (184, 115, 51)

Vec = tuple[float, float, float]


def conductor_diameter_mm(awg: int) -> float:
    """Bare conductor diameter in mm for a numeric AWG size.

    Standard AWG formula: ``d = 0.127 mm * 92 ** ((36 - AWG) / 39)``
    (e.g. AWG 24 -> 0.511 mm, AWG 10 -> 2.588 mm).
    """
    return 0.127 * (92.0 ** ((36 - awg) / 39.0))


def recommended_od_mm(awg: int, wall_mm: float = WALL_MM_DEFAULT) -> float:
    """Recommended sheathed outer diameter in mm: conductor + 2 * wall."""
    return conductor_diameter_mm(awg) + 2.0 * wall_mm


def bundle_factor(count: int) -> float:
    """Bundle-to-wire diameter ratio for *count* identical round wires."""
    if count <= 1:
        return 1.0
    if count in _BUNDLE_FACTORS:
        return _BUNDLE_FACTORS[count]
    return 1.155 * math.sqrt(count)


def cable_od_mm(
    wire_od_mm: float, count: int, jacket_wall_mm: float = CABLE_JACKET_WALL_MM
) -> float:
    """Recommended multi-conductor cable outer diameter in mm.

    Standard cable-design method: bundle OD = insulated wire OD x packing
    factor for the conductor count, a small lay (twist) allowance, plus two
    jacket walls.
    """
    bundle = wire_od_mm * bundle_factor(count) * CABLE_LAY_FACTOR
    return bundle + 2.0 * jacket_wall_mm


def wire_color_rgb(key: str) -> tuple[int, int, int]:
    """sRGB for a wire color key (the default color's when unknown)."""
    return _WIRE_COLOR_RGB.get(str(key), _WIRE_COLOR_RGB[DEFAULT_WIRE_COLOR])


def normalize_wire_color(value: object) -> str:
    """A valid wire color key (:data:`DEFAULT_WIRE_COLOR` when *value* is not).

    Tolerant of case and stray whitespace so hand-edited route payloads
    still resolve to a color instead of failing a rebuild.
    """
    key = str(value or "").strip().lower()
    return key if key in _WIRE_COLOR_RGB else DEFAULT_WIRE_COLOR


def assign_wire_colors(count: int) -> list[str]:
    """Cable wire colors in paired order: the palette sequence, cycling.

    Mirrors multi-conductor cable practice - conductors follow a standard
    color sequence - so a cable's wires are told apart without per-wire
    input in the dialog.
    """
    return [WIRE_COLOR_KEYS[index % len(WIRE_COLOR_KEYS)] for index in range(count)]


def sort_pins(pins: Iterable[str]) -> list[str]:
    """Pins sorted numerically when possible, then lexically."""
    return sorted(pins, key=_pin_sort_key)


def _pin_sort_key(pin: str) -> tuple:
    """Numeric-first sort key for one pin name.

    int() is the numeric arbiter: str.isdigit() alone is not enough because
    it accepts unicode digits (superscripts, circled numbers) that int()
    rejects with ValueError, and pins are free text.
    """
    text = str(pin)
    if text.isdigit():
        try:
            return (0, int(text), "")
        except ValueError:
            pass  # unicode digit that int() rejects - sort lexically
    return (1, 0, text)


def awg_overlap_many(ranges: Iterable[tuple[int, int]]) -> list[int]:
    """AWG sizes allowed by EVERY range, thickest first ([] when none).

    Used for cables: the single gauge choice must satisfy every paired wire
    on both connectors.
    """
    sizes: set | None = None
    for low, high in ranges:
        current = set(range(low, high + 1)) if low <= high else set()
        sizes = current if sizes is None else sizes & current
        if not sizes:
            return []
    return sorted(sizes) if sizes else []


def awg_overlap(range_a: tuple[int, int], range_b: tuple[int, int]) -> list[int]:
    """AWG sizes allowed by both wires, thickest (smallest number) first.

    Args:
        range_a: One wire's ``(awg_min, awg_max)`` numeric range.
        range_b: The other wire's range.

    Returns:
        Every AWG integer inside both ranges; empty when they do not overlap.
    """
    low = max(range_a[0], range_b[0])
    high = min(range_a[1], range_b[1])
    if low > high:
        return []
    return list(range(low, high + 1))


def spline_guide_points(
    strip_a: Vec,
    exit_a: Vec,
    strip_b: Vec,
    exit_b: Vec,
    fraction: float = GUIDE_FRACTION,
) -> list[Vec]:
    """Fit points for a smooth exit-to-exit spline without tangent constraints.

    Used when 3D-sketch tangency constraints cannot be applied: two interior
    guide points continue each strip-to-exit direction past its exit by
    *fraction* of the exit-to-exit distance, so the fitted spline leaves each
    connector roughly along its wire axis. A degenerate (zero-length)
    strip-to-exit segment falls back to the direct exit-to-exit direction.

    Returns:
        ``[exit_a, guide_a, guide_b, exit_b]`` as xyz tuples.
    """
    span = _norm(_sub(exit_b, exit_a))
    direct = _unit(_sub(exit_b, exit_a)) or (0.0, 0.0, 1.0)
    reach = (span or 1.0) * fraction
    dir_a = _unit(_sub(exit_a, strip_a)) or direct
    dir_b = _unit(_sub(exit_b, strip_b)) or _scale(direct, -1.0)
    guide_a = _add(exit_a, _scale(dir_a, reach))
    guide_b = _add(exit_b, _scale(dir_b, reach))
    return [tuple(exit_a), guide_a, guide_b, tuple(exit_b)]


def fanout_guide_points(
    strip: Vec, exit_pt: Vec, cable_pt: Vec, fraction: float = GUIDE_FRACTION
) -> list[Vec]:
    """Fit points for a wire's exit-to-cable spline without a tangent.

    One-sided fallback for a SPLINE cable fan-out: a single interior guide
    point continues the strip-to-exit direction past the exit by *fraction*
    of the exit-to-cable distance, then the spline runs on to the cable
    point. A degenerate strip-to-exit segment falls back to the direct
    direction.

    Currently unused: the cable fan-out is built from straight lines while
    a Fusion recompute defect leaves constrained fan-out splines behind on
    connector moves (see docs/arch/Route Wire.md). Kept, with its tests,
    for the spline recipe's return.

    Returns:
        ``[exit_pt, guide, cable_pt]`` as xyz tuples.
    """
    span = _norm(_sub(cable_pt, exit_pt))
    direct = _unit(_sub(cable_pt, exit_pt)) or (0.0, 0.0, 1.0)
    direction = _unit(_sub(exit_pt, strip)) or direct
    guide = _add(exit_pt, _scale(direction, (span or 1.0) * fraction))
    return [tuple(exit_pt), guide, tuple(cable_pt)]


def centroid_xyz(points: Iterable[Vec]) -> Vec:
    """Component-wise average of one or more xyz tuples.

    Raises:
        ValueError: If *points* is empty.
    """
    items = [tuple(point) for point in points]
    if not items:
        raise ValueError("centroid_xyz needs at least one point")
    count = float(len(items))
    return (
        sum(point[0] for point in items) / count,
        sum(point[1] for point in items) / count,
        sum(point[2] for point in items) / count,
    )


def pull_toward(point: Vec, target: Vec, fraction: float) -> Vec:
    """*point* moved *fraction* of the way toward *target* (``P + f*(T-P)``)."""
    return _add(point, _scale(_sub(target, point), fraction))


def cable_end_anchors(
    worlds_a: list[Vec], worlds_b: list[Vec], fraction: float = CABLE_END_PULL
) -> dict:
    """Final cable trunk anchor points for the two ends of a cable.

    Each end is the list of its connectors' cable-point positions. A
    single-connector end keeps its published point untouched; a
    multi-connector end gets an IMPLIED anchor: the centroid of its cable
    points, pulled *fraction* of the way toward the midpoint of the segment
    joining the two ends' base points (published points are never moved).

    Returns:
        ``{"a": {"xyz": Vec, "implied": bool}, "b": {...},
        "degenerate": bool}`` — degenerate when the two final anchors
        coincide (within 1e-6 cm), which cannot be built.
    """
    base_a = tuple(worlds_a[0]) if len(worlds_a) == 1 else centroid_xyz(worlds_a)
    base_b = tuple(worlds_b[0]) if len(worlds_b) == 1 else centroid_xyz(worlds_b)
    midpoint = pull_toward(base_a, base_b, 0.5)
    implied_a = len(worlds_a) > 1
    implied_b = len(worlds_b) > 1
    anchor_a = pull_toward(base_a, midpoint, fraction) if implied_a else base_a
    anchor_b = pull_toward(base_b, midpoint, fraction) if implied_b else base_b
    return {
        "a": {"xyz": anchor_a, "implied": implied_a},
        "b": {"xyz": anchor_b, "implied": implied_b},
        "degenerate": _norm(_sub(anchor_b, anchor_a)) < 1e-6,
    }


def result_notes(result: dict) -> str:
    """Builder-result notes for a summary message box ("" when clean).

    Renders the ``spline_fallback`` / ``baked_points`` / ``dropped_tangents``
    keys of a ``builder.build_wire`` / ``build_cable`` result dict. Lives
    here (beside the builder that produces the dict) so Route Wire and
    Update Wire report identical wording.
    """
    notes = ""
    if result.get("spline_fallback"):
        notes += (
            "\n\nNote: tangency constraints could not be applied everywhere "
            "- some splines were shaped with guide points instead (see the "
            "debug log for the reason)."
        )
    if result.get("baked_points"):
        notes += (
            f"\n\nNote: {result['baked_points']} point(s) could not be "
            "linked to the connector geometry and were baked at fixed "
            "positions (those parts will not follow connector moves)."
        )
    if result.get("dropped_tangents"):
        notes += (
            f"\n\nNote: {result['dropped_tangents']} fan-out tangency "
            "constraint(s) made their sketch unsolvable and were dropped - "
            "those wires stay associative but are not exactly tangent at "
            "the exit."
        )
    if result.get("implied_ends"):
        notes += (
            f"\n\nNote: {result['implied_ends']} cable end(s) span several "
            "connectors; their anchor points are computed, not linked - run "
            "Update Wire after moving those connectors."
        )
    return notes


def build_route_payload(fields: dict) -> str:
    """Serialize the route attribute stamped on the built assembly component.

    Args:
        fields: Route fields — ``name``, ``awg`` (chosen size), ``od_mm``
            (per-wire sheathed outer diameter), ``ends`` (a list of two
            per-end dicts, stored verbatim: single-wire routes carry
            ``connector_id``/``wire_id``/``pin``/``occ_token``; cable ends
            use :func:`cable_route_end` — one connector keeps the legacy
            flat ``connector_id``/``occ_token``/``pins``/``wire_ids`` shape,
            several connectors carry ``connectors``/``pins``/``wire_ids``/
            ``wire_connectors`` instead), optional ``kind``
            (:data:`KIND_SINGLE` when omitted), optional ``cable_od_mm``
            (cable jacket OD, cable routes only), optional ``color``
            (single-wire insulation color key), optional ``colors`` (cable
            wire color keys in paired order), and optional ``wire_labels``
            (cable wire display labels, index-paired with ``colors``).

    Returns:
        A JSON string in the PowerTools.Cable schema (parse with
        :func:`schema.parse_payload`).
    """
    payload = {
        "schema": schema.SCHEMA_VERSION,
        "kind": fields.get("kind", KIND_SINGLE),
        "name": fields["name"],
        "awg": fields["awg"],
        "od_mm": fields["od_mm"],
        "ends": fields["ends"],
    }
    for optional in ("cable_od_mm", "color", "colors", "wire_labels"):
        if optional in fields:
            payload[optional] = fields[optional]
    return json.dumps(payload)


def cable_route_end(
    connectors: list[dict],
    pins: list[str],
    wire_ids: list[str],
    wire_connectors: list[int],
) -> dict:
    """One cable end for the route payload's ``ends`` list.

    *connectors* holds one ``{"connector_id", "occ_token"}`` dict per
    distinct connector on this end; ``wire_connectors[i]`` indexes the
    connector wire *i* attaches to. A single-connector end is emitted in
    the legacy flat shape (no ``connectors``/``wire_connectors`` keys) so
    existing payload readers keep working; a multi-connector end omits the
    legacy top-level identity keys on purpose - old add-in builds then skip
    the route with a note instead of misreading it as two-connector.
    """
    if len(connectors) == 1:
        return {
            "connector_id": connectors[0].get("connector_id") or "",
            "occ_token": connectors[0].get("occ_token") or "",
            "pins": list(pins),
            "wire_ids": list(wire_ids),
        }
    return {
        "connectors": [
            {
                "connector_id": entry.get("connector_id") or "",
                "occ_token": entry.get("occ_token") or "",
            }
            for entry in connectors
        ],
        "pins": list(pins),
        "wire_ids": list(wire_ids),
        "wire_connectors": [int(index) for index in wire_connectors],
    }


def end_connectors(end: dict) -> list[dict]:
    """Normalize a route-payload end to its list of connector identities.

    Multi-connector ends return their ``connectors`` entries (dicts only);
    legacy single-connector ends (and damaged ``connectors`` values) return
    a one-entry list built from the flat ``connector_id``/``occ_token``
    keys. Every entry carries both keys as strings.
    """
    raw = end.get("connectors")
    entries = [entry for entry in raw if isinstance(entry, dict)] if raw else []
    if not entries:
        entries = [end]
    return [
        {
            "connector_id": str(entry.get("connector_id") or ""),
            "occ_token": str(entry.get("occ_token") or ""),
        }
        for entry in entries
    ]


def end_wire_connectors(end: dict, wire_count: int) -> list[int]:
    """Per-wire connector indices for a route-payload end, always valid.

    Missing/short lists pad with 0, junk and out-of-range entries coerce to
    0, extras are truncated - a legacy single-connector end yields all
    zeros, which indexes its only connector.
    """
    limit = len(end_connectors(end))
    raw = end.get("wire_connectors")
    values = list(raw) if isinstance(raw, list) else []
    indices = []
    for slot in range(wire_count):
        try:
            index = int(values[slot]) if slot < len(values) else 0
        except (TypeError, ValueError):
            index = 0
        indices.append(index if 0 <= index < limit else 0)
    return indices


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(v: Vec, s: float) -> Vec:
    return (v[0] * s, v[1] * s, v[2] * s)


def _norm(v: Vec) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v: Vec) -> Vec | None:
    """Normalize *v*; None for a (near) zero vector so callers can fall back."""
    length = _norm(v)
    if length < 1e-9:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)
