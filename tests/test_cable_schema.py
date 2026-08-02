"""Unit tests for the shared PowerTools.Cable attribute schema.

Exercises ``commands/cable_shared/schema.py`` (authored by Define Wires):
name and payload round-trips, tolerant parsing of damaged values, grouping
raw attribute records into wires (with orphan and garbage bucketing),
recall ordering, AWG validation, wire-set validation, and the
add/update/remove diff. These helpers have no Fusion dependency; the
module uses package-relative imports, so it is loaded via its full package
path with the conftest scaffolding in place (which also fabricates the
``adsk`` package).
"""

import importlib
import json
import re
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.cable_shared.schema")


# ---------------------------------------------------------------------------
# Point attribute names
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["start", "strip", "exit"])
def test_point_attr_name_round_trip(role) -> None:
    name = logic.point_attr_name("7c1d2e3f", role)
    assert logic.parse_point_attr_name(name) == ("7c1d2e3f", role)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "connector",
        "point",
        "point.x",
        "point.a.b.c",
        "point..start",
        "point.7c1d2e3f.middle",  # unknown role
        "other.7c1d2e3f.start",  # wrong prefix
    ],
)
def test_parse_point_attr_name_rejects_malformed(name) -> None:
    assert logic.parse_point_attr_name(name) is None


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------
_WIRE = {"wire_id": "7c1d2e3f", "pin": "3", "awg_min": 16, "awg_max": 24}


def test_point_payload_round_trip() -> None:
    value = logic.build_point_payload("Conn-3f9a2b1c", _WIRE, "strip")
    payload = logic.parse_payload(value)
    assert payload is not None
    assert payload["schema"] == 1
    assert payload["connector_id"] == "Conn-3f9a2b1c"
    assert payload["wire_id"] == "7c1d2e3f"
    assert payload["role"] == "strip"
    assert payload["pin"] == "3"
    assert payload["awg_min"] == 16
    assert payload["awg_max"] == 24


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not json",
        "[1, 2]",  # JSON but not a dict
        '"just a string"',
        json.dumps({"no_schema": True}),
        json.dumps({"schema": 99, "wire_id": "x"}),  # unknown schema version
    ],
)
def test_parse_payload_rejects_garbage(value) -> None:
    assert logic.parse_payload(value) is None


def test_parse_payload_tolerates_extra_keys() -> None:
    value = json.dumps({"schema": 1, "wire_id": "x", "future_field": [1, 2]})
    payload = logic.parse_payload(value)
    assert payload is not None
    assert payload["future_field"] == [1, 2]


def test_manifest_payload_preserves_wire_order() -> None:
    wires = [
        {"wire_id": "b1", "pin": "2", "awg_min": 16, "awg_max": 24},
        {"wire_id": "a1", "pin": "1", "awg_min": 20, "awg_max": 22},
    ]
    manifest = logic.parse_payload(
        logic.build_manifest_payload("Conn-3f9a2b1c", "Conn v3", wires)
    )
    assert manifest is not None
    assert manifest["name"] == "Conn v3"
    assert [w["wire_id"] for w in manifest["wires"]] == ["b1", "a1"]


# ---------------------------------------------------------------------------
# Grouping raw attribute records
# ---------------------------------------------------------------------------
def _point_record(wire_id, role, pin="1", has_parent=True):
    wire = {"wire_id": wire_id, "pin": pin, "awg_min": 16, "awg_max": 24}
    name = logic.point_attr_name(wire_id, role)
    return (name, logic.build_point_payload("cid", wire, role), has_parent)


def test_group_attributes_buckets_wires_and_manifest() -> None:
    wires = [
        {"wire_id": "w1", "pin": "1", "awg_min": 16, "awg_max": 24},
        {"wire_id": "w2", "pin": "2", "awg_min": 16, "awg_max": 24},
    ]
    records = [("connector", logic.build_manifest_payload("cid", "Conn", wires), True)]
    for wire in wires:
        for role in logic.ROLES:
            records.append(_point_record(wire["wire_id"], role, wire["pin"]))

    state = logic.group_attributes_into_wires(records)
    assert state["manifest"]["connector_id"] == "cid"
    assert set(state["wires"].keys()) == {"w1", "w2"}
    for roles in state["wires"].values():
        assert set(roles.keys()) == set(logic.ROLES)
        assert all(entry["has_parent"] for entry in roles.values())
    assert state["orphans"] == []
    assert state["bad"] == []


def test_group_attributes_routes_orphans_and_bad() -> None:
    records = [
        _point_record("w1", "start"),
        _point_record("w1", "exit", has_parent=False),  # entity deleted
        ("point.w1.strip", "not json", True),  # damaged value
        ("mystery", '{"schema": 1}', True),  # unknown name
        ("connector", "also not json", True),  # damaged manifest
    ]
    state = logic.group_attributes_into_wires(records)
    assert state["manifest"] is None
    assert set(state["wires"]["w1"].keys()) == {"start", "exit"}
    assert state["wires"]["w1"]["exit"]["has_parent"] is False
    assert [name for name, _payload in state["orphans"]] == ["point.w1.exit"]
    assert sorted(state["bad"]) == ["connector", "mystery", "point.w1.strip"]


def test_group_attributes_empty_input() -> None:
    state = logic.group_attributes_into_wires([])
    assert state == {
        "manifest": None,
        "cable": None,
        "wires": {},
        "orphans": [],
        "bad": [],
    }


def test_group_attributes_recognizes_cable_point() -> None:
    records = [
        ("cablepoint", logic.build_cable_point_payload("cid"), True),
        _point_record("w1", "start"),
    ]
    state = logic.group_attributes_into_wires(records)
    assert state["cable"] == {
        "payload": {"schema": 1, "connector_id": "cid", "role": "cable"},
        "has_parent": True,
    }
    assert state["bad"] == []  # must NOT be treated as cleanup garbage


def test_group_attributes_orphaned_cable_point() -> None:
    records = [("cablepoint", logic.build_cable_point_payload("cid"), False)]
    state = logic.group_attributes_into_wires(records)
    assert state["cable"]["has_parent"] is False


def test_group_attributes_damaged_cable_point_is_bad() -> None:
    state = logic.group_attributes_into_wires([("cablepoint", "not json", True)])
    assert state["cable"] is None
    assert state["bad"] == ["cablepoint"]


def test_cable_point_payload_round_trip() -> None:
    payload = logic.parse_payload(logic.build_cable_point_payload("Conn-3f9a2b1c"))
    assert payload is not None
    assert payload["schema"] == 1
    assert payload["connector_id"] == "Conn-3f9a2b1c"
    assert payload["role"] == "cable"


# ---------------------------------------------------------------------------
# Member payloads (stamped on built child components)
# ---------------------------------------------------------------------------
def test_member_payload_round_trip_without_pin() -> None:
    payload = logic.parse_payload(logic.build_member_payload(logic.MEMBER_SHEATH))
    assert payload is not None
    assert payload["schema"] == 1
    assert payload["role"] == "sheath"
    assert "pin" not in payload


def test_member_payload_round_trip_with_pin() -> None:
    payload = logic.parse_payload(
        logic.build_member_payload(logic.MEMBER_WIRE, pin="4")
    )
    assert payload is not None
    assert payload["role"] == "wire"
    assert payload["pin"] == "4"


def test_member_roles_are_distinct() -> None:
    roles = {logic.MEMBER_CONDUCTOR, logic.MEMBER_SHEATH, logic.MEMBER_WIRE}
    assert len(roles) == 3


# ---------------------------------------------------------------------------
# Pin defaults
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "pins, expected",
    [
        ([], "1"),  # first wire of a fresh dialog
        (["1"], "2"),
        (["1", "2", "3"], "4"),
        (["3", "1"], "4"),  # unordered
        (["1", "5"], "6"),  # gaps are not filled - always highest + 1
        (["A", "B"], "1"),  # non-numeric pins ignored
        (["A", "2"], "3"),  # mixed
        (["", " 7 "], "8"),  # whitespace-tolerant
        # Unicode digits (superscript two, circled two) pass str.isdigit()
        # but int() rejects them - they must be ignored, never crash Add.
        (["²"], "1"),
        (["²", "2"], "3"),
        (["②", "9"], "10"),
    ],
)
def test_next_pin(pins, expected) -> None:
    assert logic.next_pin(pins) == expected


# ---------------------------------------------------------------------------
# Recall ordering and field extraction
# ---------------------------------------------------------------------------
def test_ordered_wire_ids_manifest_first_then_pin_sorted() -> None:
    records = [
        _point_record("w1", "start", pin="9"),
        _point_record("w2", "start", pin="2"),
        _point_record("w3", "start", pin="1"),
    ]
    state = logic.group_attributes_into_wires(records)
    manifest = {"wires": [{"wire_id": "w2"}, {"wire_id": "missing"}]}
    assert logic.ordered_wire_ids(manifest, state["wires"]) == ["w2", "w3", "w1"]
    assert logic.ordered_wire_ids(None, state["wires"]) == ["w3", "w2", "w1"]


def test_manifest_entry_lookup() -> None:
    manifest = {"wires": [{"wire_id": "a", "pin": "1"}, "junk"]}
    assert logic.manifest_entry(manifest, "a") == {"wire_id": "a", "pin": "1"}
    assert logic.manifest_entry(manifest, "b") is None
    assert logic.manifest_entry(None, "a") is None


def test_wire_fields_prefers_point_payload_then_fallback() -> None:
    roles = {
        "strip": {
            "payload": {"pin": "7", "awg_min": 18, "awg_max": 20},
            "has_parent": True,
        }
    }
    assert logic.wire_fields(roles) == {"pin": "7", "awg_min": 18, "awg_max": 20}
    fallback = {"pin": "9", "awg_min": 10, "awg_max": 12}
    assert logic.wire_fields({}, fallback) == {
        "pin": "9",
        "awg_min": 10,
        "awg_max": 12,
    }
    assert logic.wire_fields({}) == {
        "pin": "",
        "awg_min": logic.AWG_DEFAULT_MIN,
        "awg_max": logic.AWG_DEFAULT_MAX,
    }


def test_wire_fields_coerces_damaged_awg() -> None:
    roles = {
        "start": {
            "payload": {"pin": 4, "awg_min": "junk", "awg_max": 99},
            "has_parent": True,
        }
    }
    assert logic.wire_fields(roles) == {
        "pin": "4",
        "awg_min": logic.AWG_DEFAULT_MIN,
        "awg_max": logic.AWG_DEFAULT_MAX,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "awg_min, awg_max, valid",
    [
        (16, 24, True),
        (20, 20, True),  # equal is a valid (single-size) range
        (0, 40, True),  # full bounds
        (24, 16, False),  # inverted
        (-1, 24, False),  # below bounds
        (16, 41, False),  # above bounds
        ("16", 24, False),  # non-int
        (None, 24, False),
    ],
)
def test_validate_awg_range(awg_min, awg_max, valid) -> None:
    reason = logic.validate_awg_range(awg_min, awg_max)
    assert (reason == "") is valid


def _summary(pin="1", awg_min=16, awg_max=24, points_set=3):
    return {
        "pin": pin,
        "awg_min": awg_min,
        "awg_max": awg_max,
        "points_set": points_set,
    }


def test_validate_wires_clean_set() -> None:
    assert logic.validate_wires([_summary("1"), _summary("2")]) == []


def test_validate_wires_flags_problems() -> None:
    problems = logic.validate_wires(
        [
            _summary(pin=""),  # blank pin
            _summary(pin="5", points_set=1),  # incomplete points
            _summary(pin="9", awg_min=30, awg_max=20),  # inverted gauge
            _summary(pin="9"),  # duplicate pin with the row above
        ]
    )
    text = " ".join(problems)
    assert "pin is empty" in text
    assert "all three points" in text
    assert "Min gauge" in text
    assert "Duplicate pin(s): 9" in text


def test_validate_wires_empty_set() -> None:
    assert logic.validate_wires([]) == ["Add at least one wire."]


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------
def test_diff_wires_pure_add() -> None:
    diff = logic.diff_wires([], ["a", "b"], [])
    assert diff == {"add": {"a", "b"}, "update": set(), "remove": set()}


def test_diff_wires_pure_remove() -> None:
    diff = logic.diff_wires(["a", "b"], [], [])
    assert diff == {"add": set(), "update": set(), "remove": {"a", "b"}}


def test_diff_wires_update_and_mixed() -> None:
    diff = logic.diff_wires(["a", "b"], ["b", "c"], [])
    assert diff == {"add": {"c"}, "update": {"b"}, "remove": {"a"}}


def test_diff_wires_deleted_wins_over_desired() -> None:
    diff = logic.diff_wires(["a", "b"], ["a", "b"], ["b"])
    assert diff == {"add": set(), "update": {"a"}, "remove": {"b"}}


def test_diff_wires_deleted_unknown_id_removes_nothing() -> None:
    diff = logic.diff_wires(["a"], ["a"], ["ghost"])
    assert diff == {"add": set(), "update": {"a"}, "remove": set()}


# ---------------------------------------------------------------------------
# Ids
# ---------------------------------------------------------------------------
def test_connector_id_keeps_existing() -> None:
    assert logic.connector_id_for("Conn", "Conn-deadbeef") == "Conn-deadbeef"


def test_connector_id_new_format() -> None:
    cid = logic.connector_id_for("Pigtail Conn v3 (rev B)")
    assert re.fullmatch(r"[A-Za-z0-9-]+-[0-9a-f]{8}", cid)
    assert cid.startswith("Pigtail-Conn-v3-rev-B-")


def test_slugify_truncates_and_survives_garbage() -> None:
    assert logic.slugify("  ** ") == "connector"
    assert len(logic.slugify("x" * 99)) == 24
    assert logic.slugify("A B", max_len=3) == "A-B"
    # A dash landing on the truncation boundary is trimmed, not kept.
    assert not logic.slugify("AB CD", max_len=3).endswith("-")


def test_new_id_shape_and_uniqueness() -> None:
    ids = {logic.new_id() for _ in range(64)}
    assert len(ids) == 64
    assert all(re.fullmatch(r"[0-9a-f]{8}", i) for i in ids)
