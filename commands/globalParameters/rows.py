# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Row rules for the Global Parameters table. Imports no ``adsk`` module.

The dialog's table is read once into plain :class:`ParameterRow` values by
``entry.py``; everything that decides what those rows *mean* lives here so the
validator and the collector cannot drift apart again:

* :func:`is_blank_row` -- the ONE skip rule. The table always carries at
  least one empty row (the dialog opens with one, and deleting every row adds
  one back), so a blank or whitespace-only Name is "no parameter", not an
  error. Before this module existed the validator skipped such rows while the
  collector did not, and ``userParameters.add("", ...)`` raised inside Fusion.
* :func:`is_valid_param_name` -- Fusion parameter-name grammar plus the
  reserved unit designations.
* :func:`validate_parameter_rows` -- the dialog's reason string ("" when OK).
* :func:`collect_parameter_rows` -- the list of parameter dicts consumed by
  the document writers and the pending-change cache.

The module has no relative imports so tests load it straight from its path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# First char must be a letter; subsequent chars may be letter/digit or allowed symbols.
PARAM_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_"$°µ]*$')

# Fusion unit designations that are reserved and cannot be parameter names.
# Case-sensitive -- Fusion expressions are case-sensitive.
RESERVED_UNITS: frozenset[str] = frozenset(
    {
        # Length
        "mm",
        "cm",
        "m",
        "km",
        "in",
        "ft",
        "yd",
        "mil",
        "thou",
        "um",
        "nm",
        "pm",
        # Angle
        "deg",
        "rad",
        "arcmin",
        "arcsec",
        "mas",
        "sr",
        # Volume / capacity
        "ml",
        "l",
        "dl",
        "cl",
        "gal",
        "qt",
        "pt",
        # Temperature
        "C",
        "F",
        "K",
        # Mass
        "g",
        "kg",
        "lb",
        "oz",
        "slug",
        "mg",
        "t",
        # Force
        "N",
        "kN",
        "lbf",
        "kip",
        "ozf",
        "dyn",
        # Pressure
        "Pa",
        "kPa",
        "MPa",
        "GPa",
        "psi",
        "ksi",
        "bar",
        "atm",
        # Power
        "W",
        "kW",
        "MW",
        "hp",
        # Energy
        "J",
        "kJ",
        "MJ",
        "cal",
        "kcal",
        "BTU",
        "Wh",
        "kWh",
        # Electrical
        "A",
        "mA",
        "V",
        "mV",
        "kV",
        "ohm",
        "Hz",
        "kHz",
        "MHz",
        # Time
        "s",
        "ms",
        "us",
        "min",
        "hr",
        # Built-in constant
        "pi",
    }
)

DEFAULT_UNIT = "mm"


@dataclass(frozen=True)
class ParameterRow:
    """One data row of the table, as plain values.

    ``row`` is the table row index (the header occupies row 0) and is only
    used to point at the offending row in a validation message. ``value`` is
    the raw text of the Value cell; parsing happens here, not in the reader.
    """

    row: int
    enabled: bool
    name: str
    value: str
    unit: str
    comment: str


def is_blank_row(row: ParameterRow) -> bool:
    """The shared skip rule: a row with no Name is not a parameter."""
    return not row.name.strip()


def is_valid_param_name(name: str) -> tuple[bool, str]:
    """Return ``(is_valid, reason)`` for a Fusion parameter name."""
    if not name:
        return False, "Name is required"
    if not name[0].isalpha():
        return False, "Must start with a letter"
    if not PARAM_NAME_RE.match(name):
        return False, 'Only letters, digits, _, ", $, °, µ are allowed'
    if name in RESERVED_UNITS:
        return False, f'"{name}" is a reserved Fusion unit name'
    return True, ""


def parse_value(text: str) -> float:
    """Parse a Value cell. Empty text is ``0.0``; garbage raises ``ValueError``.

    The validator reports the error before ``execute`` can run, so the
    collector may rely on this succeeding for every row it is handed.
    """
    stripped = text.strip()
    return float(stripped) if stripped else 0.0


def validate_parameter_rows(rows: Iterable[ParameterRow]) -> str:
    """Return "" when every non-blank row is acceptable, else a short reason.

    Rules, in order per row: blank rows are skipped; the name must satisfy
    :func:`is_valid_param_name`; names must be unique across the table; the
    value must parse as a number.
    """
    seen_names: set[str] = set()
    for row in rows:
        if is_blank_row(row):
            continue
        name = row.name.strip()

        ok, reason = is_valid_param_name(name)
        if not ok:
            return f'Row {row.row}: "{name}" — {reason}'

        if name in seen_names:
            return f'Duplicate parameter name: "{name}"'
        seen_names.add(name)

        try:
            parse_value(row.value)
        except ValueError:
            return f'Row {row.row}: value "{row.value.strip()}" is not a valid number'

    return ""


def collect_parameter_rows(rows: Iterable[ParameterRow]) -> list[dict]:
    """Turn table rows into the parameter dicts the writers consume.

    Blank rows are dropped by the same rule the validator uses; every other
    row yields ``{"enabled", "name", "value", "unit", "comment"}`` in table
    order, with ``name`` stripped and ``value`` a float.
    """
    return [
        {
            "enabled": row.enabled,
            "name": row.name.strip(),
            "value": parse_value(row.value),
            "unit": row.unit,
            "comment": row.comment,
        }
        for row in rows
        if not is_blank_row(row)
    ]
