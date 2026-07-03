# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Pure rounding helpers for the Round Sketch Dimensions command.

This module is deliberately free of any ``adsk`` import and of relative imports
so it can be unit-tested outside Fusion (loaded directly by file path). All
Fusion-touching logic (reading/writing sketch dimensions) lives in ``entry.py``.

Two families of increments are supported:

* Metric documents round on a millimetre grid (:data:`MM_INCREMENTS`).
* Imperial (inch/foot) documents offer two grids of the SAME length so the
  increment slider can be built once and only its interpretation changes when
  the user toggles Fractions vs Decimal:
    - Fractions: a ``1/den`` inch grid (:data:`INCH_FRACTION_DENOMS`).
    - Decimal:   a curated set of nice decimal-inch increments
      (:data:`INCH_DECIMAL_INCH`).

Values are always snapped to the grid; the written expression is a decimal in
the grid unit, which is exact for every fraction denominator here
(``1/64 == 0.015625`` exactly).
"""

from __future__ import annotations

import re
from math import gcd
from typing import List, Optional, Sequence

# Increment grids. Each list is ascending so the smart-default search can take
# the largest increment not exceeding the target.
MM_INCREMENTS: List[float] = [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0]
INCH_FRACTION_DENOMS: List[int] = [64, 32, 16, 8, 4, 2, 1]  # -> 1/64 .. 1 in
INCH_DECIMAL_INCH: List[float] = [0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]

# Length unit tokens that may trail a dimension expression. Longer tokens must
# be tried first (see ``is_plain_numeric_expression``) so "mm" is stripped
# before "m".
LENGTH_UNIT_TOKENS = (
    "millimeter",
    "centimeter",
    "meter",
    "inch",
    "foot",
    "feet",
    "mm",
    "cm",
    "in",
    "ft",
    "m",
)

# Matches a bare number or a simple ``a/b`` fraction (no parameter references,
# no functions, no arithmetic beyond a single division).
_PLAIN_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?")


def fraction_increments() -> List[float]:
    """Return the imperial fraction grid as absolute inch increments."""
    return [1.0 / d for d in INCH_FRACTION_DENOMS]


def is_plain_numeric_expression(
    expr: str, unit_tokens: Sequence[str] = LENGTH_UNIT_TOKENS
) -> bool:
    """Return True if *expr* is a plain constant value, not a formula/reference.

    A plain expression is a number (optionally a simple ``a/b`` fraction)
    followed by an optional length-unit token. Expressions that reference other
    parameters (``width/2``, ``d1``) or use functions/arithmetic
    (``sin(30 deg)``, ``2*d0``) return False so their parametric intent is
    preserved (they are skipped by the rounding command).
    """
    if not expr:
        return False
    s = expr.strip().lower()
    for tok in sorted(unit_tokens, key=len, reverse=True):
        if s.endswith(tok):
            s = s[: -len(tok)].strip()
            break
    return _PLAIN_NUMBER_RE.fullmatch(s) is not None


def round_to_increment(value: float, increment: float) -> float:
    """Snap *value* to the nearest multiple of *increment*.

    A non-positive increment is a no-op (returns *value* unchanged). The result
    is idempotent: rounding a value already on the grid returns the same value.
    """
    if increment <= 0:
        return value
    return round(value / increment) * increment


def median(values: Sequence[float]) -> Optional[float]:
    """Return the median of *values*, or None if empty."""
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def smart_default_index(
    magnitudes: Sequence[float], increments: Sequence[float]
) -> int:
    """Pick a sensible default increment index for the given dimension sizes.

    Uses the median magnitude of the eligible dimensions and targets an
    increment around 5% of that characteristic size, choosing the largest grid
    increment that does not exceed the target. Falls back to the middle of the
    list when there is nothing to size against, and to the smallest increment
    when every grid step is larger than the target.

    *increments* is assumed ascending. *magnitudes* are in the same (display)
    unit as *increments*.
    """
    if not increments:
        return 0
    mags = [abs(m) for m in magnitudes if m and abs(m) > 0]
    char = median(mags)
    if char is None:
        return len(increments) // 2
    target = char / 20.0
    candidates = [i for i, inc in enumerate(increments) if inc <= target]
    if candidates:
        return max(candidates)
    return 0


def _trim_number(x: float) -> str:
    """Format *x* as a compact decimal string without trailing-zero noise."""
    s = f"{x:.10f}".rstrip("0").rstrip(".")
    if s in ("", "-0"):
        s = "0"
    return s


def format_value_expression(value: float, unit_token: str) -> str:
    """Build a dimension expression like ``"12.5 mm"`` from a rounded value."""
    return f"{_trim_number(value)} {unit_token}"


def decimal_increment_label(increment: float, unit_token: str) -> str:
    """Human-readable label for a decimal increment, e.g. ``"0.5 mm"``."""
    return f"{_trim_number(increment)} {unit_token}"


def fraction_increment_label(denominator: int, unit_token: str = "in") -> str:
    """Human-readable label for a ``1/denominator`` increment, e.g. ``"1/16 in"``.

    A denominator of 1 renders as ``"1 in"``.
    """
    return f"{_format_fraction(1, denominator)} {unit_token}"


def _format_fraction(numerator: int, denominator: int) -> str:
    """Return a reduced fraction string; whole values drop the denominator."""
    if denominator == 0:
        return str(numerator)
    g = gcd(numerator, denominator) or 1
    num, den = numerator // g, denominator // g
    if den == 1:
        return str(num)
    return f"{num}/{den}"
