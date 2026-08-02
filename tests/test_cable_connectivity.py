"""Unit tests for the connectivity wire-list format.

Exercises ``commands/cable_shared/connectivity.py``: designator
suggestion/validation/sorting, CSV serialization with the
formula-injection guard, the commented connector reference block, the
tolerant wire-list parser (comments, short/extra columns, per-row and
per-group validation, single vs cable grouping, row flipping), and the
direction-insensitive route key. These helpers have no Fusion dependency;
the module uses package-relative imports, so it is loaded via its full
package path with the conftest scaffolding in place (which also fabricates
the ``adsk`` package).
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
connectivity = importlib.import_module(f"{PT_PKG}.commands.cable_shared.connectivity")
routing = importlib.import_module(f"{PT_PKG}.commands.cable_shared.routing")


# ---------------------------------------------------------------------------
# Designators
# ---------------------------------------------------------------------------
def test_suggest_designators_skips_taken_case_insensitively() -> None:
    assert connectivity.suggest_designators(3) == ["J1", "J2", "J3"]
    assert connectivity.suggest_designators(2, taken=["j1", "J3"]) == ["J2", "J4"]
    assert connectivity.suggest_designators(0) == []


def test_validate_designators_flags_duplicates_and_allows_blanks() -> None:
    entries = [("Conn A", "J1"), ("Conn B", ""), ("Conn C", " j1 ")]
    problems = connectivity.validate_designators(entries)
    assert len(problems) == 1
    assert "J1" in problems[0] or "j1" in problems[0]
    assert connectivity.validate_designators([("A", "J1"), ("B", "P1")]) == []


def test_designator_sort_key_is_natural() -> None:
    refs = ["J10", "J2", "P1", "J1"]
    ordered = sorted(refs, key=connectivity.designator_sort_key)
    assert ordered == ["J1", "J2", "J10", "P1"]


# ---------------------------------------------------------------------------
# Serialization round trip
# ---------------------------------------------------------------------------
def _single_row(**overrides) -> dict:
    row = {
        "cable": "",
        "wire": "PWR1",
        "from_ref": "J1",
        "from_pin": "1",
        "to_ref": "J2",
        "to_pin": "4",
        "color": "red",
        "awg": 22,
        "wire_od_mm": 1.54,
        "cable_od_mm": None,
        "length_mm": 120.5,
    }
    row.update(overrides)
    return row


def test_serialize_and_parse_round_trip_single() -> None:
    text = connectivity.serialize_rows([_single_row()])
    assert text.splitlines()[0].startswith("Cable,Wire,From,From Pin")
    result = connectivity.parse_wire_list(text)
    assert result["problems"] == []
    (group,) = result["groups"]
    assert group["kind"] == "single"
    assert group["name"] == "PWR1"
    assert group["awg"] == 22
    assert group["od_mm"] == pytest.approx(1.54)
    assert group["key"] == connectivity.route_key("J1", "1", "J2", "4")


def test_serialize_guards_formula_cells_and_parse_strips_them() -> None:
    text = connectivity.serialize_rows([_single_row(wire="=SUM(A1)", from_pin="-V")])
    assert "'=SUM(A1)" in text
    assert "'-V" in text
    result = connectivity.parse_wire_list(text)
    assert result["problems"] == []
    (group,) = result["groups"]
    assert group["name"] == "=SUM(A1)"
    assert group["from_pin"] == "-V"


def test_reference_lines_are_comments_and_parse_skips_them() -> None:
    connectors = [
        {
            "designator": "J1",
            "name": "Ring Terminal",
            "pins": [{"pin": "1", "awg_min": 16, "awg_max": 24}],
            "has_cable_point": False,
        }
    ]
    lines = connectivity.connector_reference_lines(connectors)
    assert all(line.startswith("#") for line in lines)
    assert any("J1 = Ring Terminal" in line for line in lines)
    text = connectivity.serialize_rows([_single_row()], reference_lines=lines)
    result = connectivity.parse_wire_list(text)
    assert result["problems"] == []
    assert len(result["groups"]) == 1


# ---------------------------------------------------------------------------
# Route key
# ---------------------------------------------------------------------------
def test_route_key_is_direction_insensitive() -> None:
    forward = connectivity.route_key("J1", "1", "J2", "4")
    reverse = connectivity.route_key("j2", "4", "J1 ", "1")
    assert forward == reverse
    assert forward != connectivity.route_key("J1", "2", "J2", "4")


# ---------------------------------------------------------------------------
# Parsing: rows and validation
# ---------------------------------------------------------------------------
def _csv(*rows: str) -> str:
    return ",".join(connectivity.HEADER) + "\n" + "\n".join(rows) + "\n"


def test_parse_defaults_wire_od_color_and_name() -> None:
    result = connectivity.parse_wire_list(_csv(",,J1,1,J2,4,,22,,,"))
    assert result["problems"] == []
    (group,) = result["groups"]
    assert group["name"] == "J11-J24"
    assert group["color"] == routing.DEFAULT_WIRE_COLOR
    assert group["od_mm"] == pytest.approx(routing.recommended_od_mm(22))


def test_parse_reports_row_problems() -> None:
    result = connectivity.parse_wire_list(
        _csv(
            ",W1,J1,,J2,4,,22,,,",  # missing From Pin
            ",W2,J1,1,J1,2,,junk,,,",  # self-connection reported before gauge
            ",W3,J1,1,J2,4,,99,,,",  # gauge out of range
            ",W4,J1,1,J2,4,,22,-1,,",  # bad wire OD
        )
    )
    assert result["groups"] == []
    assert len(result["problems"]) == 4
    assert "missing From Pin" in result["problems"][0]
    assert "itself" in result["problems"][1]
    assert "outside" in result["problems"][2]
    assert "positive" in result["problems"][3]


def test_parse_rejects_wrong_header() -> None:
    result = connectivity.parse_wire_list("A,B,C\n1,2,3\n")
    assert result["groups"] == []
    assert "header row" in result["problems"][0]


def test_parse_tolerates_short_and_extra_columns() -> None:
    short = ",W1,J1,1,J2,4,red,22"  # no OD/length cells at all
    extra = ",W2,J1,2,J2,5,red,22,,,,GND,future"  # unknown trailing columns
    result = connectivity.parse_wire_list(_csv(short, extra))
    assert result["problems"] == []
    assert [group["name"] for group in result["groups"]] == ["W1", "W2"]


# ---------------------------------------------------------------------------
# Parsing: cable grouping
# ---------------------------------------------------------------------------
def test_cable_group_pairs_row_by_row_and_flips_reversed_rows() -> None:
    result = connectivity.parse_wire_list(
        _csv(
            "HARN1,1,J1,1,J3,5,red,24,,6.2,",
            "HARN1,2,J3,6,J1,2,black,24,,,",  # reversed row - must flip
        )
    )
    assert result["problems"] == []
    (group,) = result["groups"]
    assert group["kind"] == "cable"
    assert group["name"] == "HARN1"
    assert group["from_ref"] == "J1"
    assert group["to_ref"] == "J3"
    assert [(w["from_pin"], w["to_pin"]) for w in group["wires"]] == [
        ("1", "5"),
        ("2", "6"),
    ]
    assert group["cable_od_mm"] == pytest.approx(6.2)
    assert group["keys"][1] == connectivity.route_key("J1", "2", "J3", "6")


def test_cable_group_defaults_colors_from_palette_sequence() -> None:
    result = connectivity.parse_wire_list(
        _csv(
            "HARN1,1,J1,1,J3,1,,24,,,",
            "HARN1,2,J1,2,J3,2,,24,,,",
        )
    )
    (group,) = result["groups"]
    assert [w["color"] for w in group["wires"]] == ["red", "black"]


@pytest.mark.parametrize(
    "rows, needle",
    [
        (("HARN1,1,J1,1,J3,1,,24,,,",), "at least two"),
        (
            (
                "HARN1,1,J1,1,J3,1,,24,,,",
                "HARN1,2,J1,2,J3,2,,22,,,",
            ),
            "one gauge",
        ),
        (
            (
                "HARN1,1,J1,1,J3,1,,24,,,",
                "HARN1,2,J1,2,J4,2,,24,,,",
            ),
            "the cable runs",
        ),
        (
            (
                "HARN1,1,J1,1,J3,1,,24,,,",
                "HARN1,1,J1,2,J3,2,,24,,,",
            ),
            "duplicate wire label",
        ),
        (
            (
                "HARN1,1,J1,1,J3,1,,24,,,",
                "HARN1,2,J1,1,J3,2,,24,,,",
            ),
            "pin is used by two rows",
        ),
        (
            (
                "HARN1,1,J1,1,J3,1,,24,,0.5,",
                "HARN1,2,J1,2,J3,2,,24,,,",
            ),
            "Cable OD must not be smaller",
        ),
    ],
)
def test_cable_group_validation_problems(rows, needle) -> None:
    result = connectivity.parse_wire_list(_csv(*rows))
    assert result["groups"] == []
    assert any(needle in problem for problem in result["problems"])


def test_groups_keep_file_order_and_bad_groups_do_not_block_good_ones() -> None:
    result = connectivity.parse_wire_list(
        _csv(
            ",PWR1,J1,1,J2,4,red,22,,,",
            "BAD,1,J1,2,J3,1,,24,,,",  # one-row cable - invalid
            "HARN1,1,J1,3,J3,3,,24,,,",
            "HARN1,2,J1,4,J3,4,,24,,,",
        )
    )
    assert [group["name"] for group in result["groups"]] == ["PWR1", "HARN1"]
    assert any("BAD" in problem for problem in result["problems"])
