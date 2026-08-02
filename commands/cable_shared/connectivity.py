# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""The connectivity wire-list (CSV) format - single source of truth.

Industry-practice tabular wire list (From, From Pin, To, To Pin, Color,
Gauge - the CSV wire-list convention used on harness drawings, cf.
IPC/WHMA-A-620 assemblies) plus the cable grouping and reference-designator
rules shared by the Assign Designators, Export Connectivity, and Import
Connectivity commands. Pure and Fusion-free; unit-tested in
``tests/test_cable_connectivity.py``.

Format rules (documented in ``docs/arch/Export Connectivity.md``):

- Lines starting with ``#`` are comments (the export leads with a
  connector/pin reference block); the ``Length (mm)`` column is
  export-only documentation. Both are ignored on import.
- An empty ``Cable`` cell makes the row a SINGLE wire (``Wire`` is the
  route name). Rows sharing a ``Cable`` value become one multi-conductor
  cable: one row per wire, pins paired row by row, one gauge per cable.
- Blank ``Wire OD (mm)`` falls back to the gauge recommendation; a
  cable's ``Cable OD (mm)`` is read from the group's first non-empty cell,
  else recommended from wire OD and count.
- Cells that would read as spreadsheet formulas are written with a leading
  apostrophe and stripped again on parse.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from . import routing, schema

HEADER = (
    "Cable",
    "Wire",
    "From",
    "From Pin",
    "To",
    "To Pin",
    "Color",
    "Gauge (AWG)",
    "Wire OD (mm)",
    "Cable OD (mm)",
    "Length (mm)",
)
COMMENT_PREFIX = "#"
_FORMULA_LEADS = ("=", "+", "-", "@")


# ---------------------------------------------------------------------------
# Reference designators
# ---------------------------------------------------------------------------
def suggest_designators(count: int, taken: Iterable[str] = ()) -> list[str]:
    """``J1..Jn`` suggestions, skipping *taken* (case-insensitive)."""
    used = {str(value).strip().lower() for value in taken if str(value).strip()}
    suggestions: list[str] = []
    number = 1
    while len(suggestions) < count:
        candidate = f"J{number}"
        if candidate.lower() not in used:
            suggestions.append(candidate)
            used.add(candidate.lower())
        number += 1
    return suggestions


def validate_designators(entries: Iterable[tuple[str, str]]) -> list[str]:
    """Problems for ``(connector label, designator)`` pairs (empty = valid).

    Blank designators are allowed (the connector stays unassigned);
    non-blank ones must be unique case-insensitively.
    """
    problems: list[str] = []
    seen: dict[str, str] = {}
    for label, designator in entries:
        key = str(designator or "").strip().lower()
        if not key:
            continue
        if key in seen:
            problems.append(
                f"Designator '{str(designator).strip()}' used by both "
                f"'{seen[key]}' and '{label}'."
            )
        else:
            seen[key] = label
    return problems


def designator_sort_key(designator: str) -> tuple:
    """Natural sort key: alpha prefix, then number ("J2" before "J10")."""
    text = str(designator).strip()
    head = text.rstrip("0123456789")
    tail = text[len(head) :]
    return (head.lower(), int(tail) if tail else -1, text.lower())


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _guard(cell: object) -> str:
    """Prefix cells that a spreadsheet would evaluate as a formula."""
    text = "" if cell is None else str(cell)
    if text[:1] in _FORMULA_LEADS or text[:1] in ("\t", "\r"):
        return "'" + text
    return text


def _unguard(cell: str) -> str:
    """Strip the formula guard written by :func:`_guard`."""
    if cell[:1] == "'" and cell[1:2] in _FORMULA_LEADS:
        return cell[1:]
    return cell


def _number_cell(value: object) -> str:
    """A blank-tolerant numeric cell with trailing zeros trimmed."""
    if value is None or value == "":
        return ""
    return f"{float(value):.3f}".rstrip("0").rstrip(".")  # type: ignore[arg-type]


def serialize_rows(rows: Iterable[dict], reference_lines: Iterable[str] = ()) -> str:
    """CSV text: optional ``#`` lines, the header, one line per wire row.

    Row keys: ``cable``, ``wire``, ``from_ref``, ``from_pin``, ``to_ref``,
    ``to_pin``, ``color``, ``awg``, ``wire_od_mm``, ``cable_od_mm``,
    ``length_mm`` (numbers may be None/"" for a blank cell).
    """
    buffer = io.StringIO()
    for line in reference_lines:
        if not line.startswith(COMMENT_PREFIX):
            line = f"{COMMENT_PREFIX} {line}"
        buffer.write(line + "\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow(
            [
                _guard(row.get("cable", "")),
                _guard(row.get("wire", "")),
                _guard(row.get("from_ref", "")),
                _guard(row.get("from_pin", "")),
                _guard(row.get("to_ref", "")),
                _guard(row.get("to_pin", "")),
                _guard(row.get("color", "")),
                "" if row.get("awg") in (None, "") else str(row["awg"]),
                _number_cell(row.get("wire_od_mm")),
                _number_cell(row.get("cable_od_mm")),
                _number_cell(row.get("length_mm")),
            ]
        )
    return buffer.getvalue()


def connector_reference_lines(connectors: Iterable[dict]) -> list[str]:
    """The commented connector/pin reference block for an export.

    Args:
        connectors: One dict per connector with ``designator``, ``name``,
            ``pins`` (``[{"pin", "awg_min", "awg_max"}]``), and
            ``has_cable_point``.
    """
    lines = [
        "# PowerTools connectivity wire list (v1).",
        "# Edit or add data rows below the header, then run Import",
        "# Connectivity. '#' lines and the Length column are ignored on",
        "# import. Rows sharing a Cable value become one multi-conductor",
        "# cable (one row per wire, pins paired per row, one gauge).",
        "# Connectors:",
    ]
    for connector in connectors:
        pins = ", ".join(
            f"{pin['pin']} ({pin['awg_min']}-{pin['awg_max']} AWG)"
            for pin in connector.get("pins", [])
        )
        cable_note = "yes" if connector.get("has_cable_point") else "no"
        lines.append(
            f"#   {connector['designator']} = {connector['name']}: "
            f"pins {pins}; cable point: {cable_note}"
        )
    return lines


# ---------------------------------------------------------------------------
# Route matching
# ---------------------------------------------------------------------------
def route_key(from_ref: str, from_pin: str, to_ref: str, to_pin: str) -> tuple:
    """Direction-insensitive endpoint key for matching rows to routes."""
    ends = sorted(
        (
            (str(from_ref).strip().lower(), str(from_pin).strip()),
            (str(to_ref).strip().lower(), str(to_pin).strip()),
        )
    )
    return tuple(ends)


# ---------------------------------------------------------------------------
# Parsing an edited wire list
# ---------------------------------------------------------------------------
def parse_wire_list(text: str) -> dict:
    """Parse an edited wire list into buildable groups.

    Tolerant reader: comment/blank lines are skipped, short rows are padded,
    extra trailing columns are ignored (room for future columns such as
    signal names). Validation is per GROUP - a bad row or cable never
    blocks the rest of the file.

    Returns:
        ``{"groups": [...], "problems": [...]}``. Single group:
        ``{"kind": "single", "name", "from_ref", "from_pin", "to_ref",
        "to_pin", "color", "awg", "od_mm", "key"}``. Cable group:
        ``{"kind": "cable", "name", "from_ref", "to_ref", "awg", "od_mm",
        "cable_od_mm", "wires": [{"label", "from_pin", "to_pin", "color"}],
        "keys": [...]}``. Problems are human-readable reasons for every
        row/group that did not survive.
    """
    problems: list[str] = []
    data_lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(COMMENT_PREFIX)
    ]
    if not data_lines:
        return {"groups": [], "problems": ["The file contains no data rows."]}
    parsed = list(csv.reader(data_lines))
    header = [cell.strip().lower() for cell in parsed[0]]
    expected = [cell.lower() for cell in HEADER]
    if header[: len(expected)] != expected:
        return {
            "groups": [],
            "problems": [
                "The header row does not match the expected columns: "
                + ", ".join(HEADER)
            ],
        }

    rows: list[dict] = []
    for number, cells in enumerate(parsed[1:], start=1):
        if not any(cell.strip() for cell in cells):
            continue
        row = _coerce_row(number, cells, problems)
        if row is not None:
            rows.append(row)

    groups: list[dict] = []
    cable_rows: dict[str, list[dict]] = {}
    cable_order: dict[str, int] = {}
    for row in rows:
        if row["cable"]:
            cable_rows.setdefault(row["cable"], []).append(row)
            cable_order.setdefault(row["cable"], row["n"])
        else:
            group = _single_group(row, problems)
            if group is not None:
                groups.append((row["n"], group))
    for cable_name, group_rows in cable_rows.items():
        group = _cable_group(cable_name, group_rows, problems)
        if group is not None:
            groups.append((cable_order[cable_name], group))
    groups.sort(key=lambda item: item[0])  # keep the file's order
    return {"groups": [group for _n, group in groups], "problems": problems}


def _coerce_row(number: int, cells: list, problems: list) -> dict | None:
    """Normalize one data row; None (with a problem) when unusable."""
    cells = [_unguard(str(cell).strip()) for cell in cells]
    cells += [""] * (len(HEADER) - len(cells))
    row = {
        "n": number,
        "cable": cells[0],
        "wire": cells[1],
        "from_ref": cells[2],
        "from_pin": cells[3],
        "to_ref": cells[4],
        "to_pin": cells[5],
        "color": routing.normalize_wire_color(cells[6]) if cells[6] else "",
        "awg": None,
        "wire_od": None,
        "cable_od": None,
    }
    missing = [
        label
        for label, value in (
            ("From", row["from_ref"]),
            ("From Pin", row["from_pin"]),
            ("To", row["to_ref"]),
            ("To Pin", row["to_pin"]),
        )
        if not value
    ]
    if missing:
        problems.append(f"Row {number}: missing {', '.join(missing)}.")
        return None
    if row["from_ref"].lower() == row["to_ref"].lower():
        problems.append(
            f"Row {number}: connects '{row['from_ref']}' to itself - a route "
            "needs two different connectors."
        )
        return None
    try:
        row["awg"] = int(cells[7])
    except (TypeError, ValueError):
        problems.append(f"Row {number}: gauge '{cells[7]}' is not a whole AWG size.")
        return None
    if not (schema.AWG_LOWER_BOUND <= row["awg"] <= schema.AWG_UPPER_BOUND):
        problems.append(
            f"Row {number}: gauge {row['awg']} is outside "
            f"{schema.AWG_LOWER_BOUND}-{schema.AWG_UPPER_BOUND} AWG."
        )
        return None
    for key, label in (("wire_od", "Wire OD"), ("cable_od", "Cable OD")):
        cell = cells[8 if key == "wire_od" else 9]
        if not cell:
            continue
        try:
            value = float(cell)
        except ValueError:
            problems.append(f"Row {number}: {label} '{cell}' is not a number.")
            return None
        if value <= 0:
            problems.append(f"Row {number}: {label} must be positive.")
            return None
        row[key] = value
    return row


def _single_group(row: dict, problems: list) -> dict | None:
    """One single-wire build group from one row."""
    od_mm = row["wire_od"] or routing.recommended_od_mm(row["awg"])
    if od_mm <= routing.conductor_diameter_mm(row["awg"]):
        problems.append(
            f"Row {row['n']}: Wire OD must exceed the bare {row['awg']} AWG conductor."
        )
        return None
    name = row["wire"] or (
        f"{row['from_ref']}{row['from_pin']}-{row['to_ref']}{row['to_pin']}"
    )
    return {
        "kind": "single",
        "name": name,
        "from_ref": row["from_ref"],
        "from_pin": row["from_pin"],
        "to_ref": row["to_ref"],
        "to_pin": row["to_pin"],
        "color": row["color"] or routing.DEFAULT_WIRE_COLOR,
        "awg": row["awg"],
        "od_mm": od_mm,
        "key": route_key(
            row["from_ref"], row["from_pin"], row["to_ref"], row["to_pin"]
        ),
    }


def _cable_group(cable_name: str, rows: list[dict], problems: list) -> dict | None:
    """One cable build group from its rows; None (with problems) if invalid."""
    group_problems: list[str] = []
    if len(rows) < 2:
        group_problems.append(f"Cable '{cable_name}': needs at least two wire rows.")
    gauges = sorted({row["awg"] for row in rows})
    if len(gauges) > 1:
        group_problems.append(
            f"Cable '{cable_name}': all rows must share one gauge "
            f"(found {', '.join(str(g) for g in gauges)} AWG)."
        )
    first = rows[0]
    pair = {first["from_ref"].lower(), first["to_ref"].lower()}
    wires: list[dict] = []
    keys: list[tuple] = []
    labels: set = set()
    default_colors = routing.assign_wire_colors(len(rows))
    for index, row in enumerate(rows):
        refs = {row["from_ref"].lower(), row["to_ref"].lower()}
        if refs != pair:
            group_problems.append(
                f"Cable '{cable_name}': row {row['n']} connects "
                f"{row['from_ref']}-{row['to_ref']} but the cable runs "
                f"{first['from_ref']}-{first['to_ref']}."
            )
            continue
        if row["from_ref"].lower() == first["from_ref"].lower():
            from_pin, to_pin = row["from_pin"], row["to_pin"]
        else:
            from_pin, to_pin = row["to_pin"], row["from_pin"]  # flipped row
        label = row["wire"] or from_pin
        if label.lower() in labels:
            group_problems.append(
                f"Cable '{cable_name}': duplicate wire label '{label}'."
            )
        labels.add(label.lower())
        wires.append(
            {
                "label": label,
                "from_pin": from_pin,
                "to_pin": to_pin,
                "color": row["color"] or default_colors[index],
            }
        )
        keys.append(route_key(first["from_ref"], from_pin, first["to_ref"], to_pin))
    for side, key in (("From", "from_pin"), ("To", "to_pin")):
        pins = [wire[key] for wire in wires]
        if len(set(pins)) != len(pins):
            group_problems.append(
                f"Cable '{cable_name}': a {side} pin is used by two rows."
            )
    awg = first["awg"]
    od_mm = next((row["wire_od"] for row in rows if row["wire_od"]), None)
    od_mm = od_mm or routing.recommended_od_mm(awg)
    cable_od = next((row["cable_od"] for row in rows if row["cable_od"]), None)
    cable_od = cable_od or routing.cable_od_mm(od_mm, len(wires))
    if od_mm <= routing.conductor_diameter_mm(awg):
        group_problems.append(
            f"Cable '{cable_name}': Wire OD must exceed the bare {awg} AWG conductor."
        )
    if cable_od < od_mm:
        group_problems.append(
            f"Cable '{cable_name}': Cable OD must not be smaller than the wire OD."
        )
    if group_problems:
        problems.extend(group_problems)
        return None
    return {
        "kind": "cable",
        "name": cable_name,
        "from_ref": first["from_ref"],
        "to_ref": first["to_ref"],
        "awg": awg,
        "od_mm": od_mm,
        "cable_od_mm": cable_od,
        "wires": wires,
        "keys": keys,
    }
