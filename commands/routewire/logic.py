# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Route Wire command.

AWG sizing math, the allowed-gauge intersection of two wires, the guide-point
fallback used when 3D-sketch tangency constraints are unavailable, and the
route attribute payload stamped on the created wire assembly component. The
attribute schema itself (group name, payload parsing) lives in
``commands/definewires/logic.py`` and is imported here as ``schema`` — that
module remains the single source of truth for the PowerTools.Cable group.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable

from ..definewires import logic as schema

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
    return notes


def build_route_payload(fields: dict) -> str:
    """Serialize the route attribute stamped on the built assembly component.

    Args:
        fields: Route fields — ``name``, ``awg`` (chosen size), ``od_mm``
            (per-wire sheathed outer diameter), ``ends`` (a list of two
            per-connector dicts, stored verbatim: single-wire routes carry
            ``connector_id``/``wire_id``/``pin``/``occ_token``; cable routes
            carry ``connector_id``/``occ_token``/``pins``/``wire_ids``),
            optional ``kind`` (:data:`KIND_SINGLE` when omitted), and
            optional ``cable_od_mm`` (cable jacket OD, cable routes only).

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
    if "cable_od_mm" in fields:
        payload["cable_od_mm"] = fields["cable_od_mm"]
    return json.dumps(payload)


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
