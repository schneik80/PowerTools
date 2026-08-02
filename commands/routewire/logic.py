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

from ..definewires import logic as schema

ROUTE_NAME = "route"

# Default insulation wall thickness used for the recommended sheathed outer
# diameter (rule of thumb for common hookup wire, e.g. UL1007-class).
WALL_MM_DEFAULT = 0.45

# How far past each connector exit the fallback spline guide points reach,
# as a fraction of the exit-to-exit distance.
GUIDE_FRACTION = 0.25

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


def build_route_payload(fields: dict) -> str:
    """Serialize the route attribute stamped on the wire assembly component.

    Args:
        fields: Route fields — ``name`` (wire name), ``awg`` (chosen size),
            ``od_mm`` (sheathed outer diameter), and ``ends`` (a list of two
            dicts with ``connector_id``, ``wire_id``, ``pin``).

    Returns:
        A JSON string in the PowerTools.Cable schema (parse with
        :func:`schema.parse_payload`).
    """
    return json.dumps(
        {
            "schema": schema.SCHEMA_VERSION,
            "name": fields["name"],
            "awg": fields["awg"],
            "od_mm": fields["od_mm"],
            "ends": fields["ends"],
        }
    )


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
