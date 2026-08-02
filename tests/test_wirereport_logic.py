"""Unit tests for the Wire Report pure-logic helpers.

Exercises the report summarization: single-wire totals, the cable rule
that the LONGEST wire path sets the cable length, and the rollup totals.
These helpers have no Fusion dependency; the module uses package-relative
imports, so it is loaded via its full package path with the conftest
scaffolding in place (which also fabricates the ``adsk`` package).
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.wirereport.logic")


def test_summarize_single_total_is_stubs_plus_sheath() -> None:
    entry = logic.summarize_single(
        {
            "name": "PWR1",
            "awg": 22,
            "od_mm": 1.54,
            "ends": [{"connector": "A", "pins": ["1"]}],
            "conductor_cm": 1.2,
            "sheath_cm": 14.3,
        }
    )
    assert entry["kind"] == "single"
    assert entry["total_cm"] == pytest.approx(15.5)
    assert entry["name"] == "PWR1"
    assert entry["ends"][0]["connector"] == "A"


def test_summarize_single_tolerates_missing_lengths() -> None:
    entry = logic.summarize_single({"name": "X"})
    assert entry["total_cm"] == 0.0
    assert entry["ends"] == []


def test_summarize_cable_longest_wire_sets_cable_length() -> None:
    entry = logic.summarize_cable(
        {
            "name": "HARN1",
            "awg": 24,
            "od_mm": 1.41,
            "cable_od_mm": 4.33,
            "jacket_cm": 30.0,
            "wires": [
                {"pin": "1", "extra_cm": 4.0},
                {"pin": "2", "extra_cm": 6.5},  # the longest path
                {"pin": "3", "extra_cm": 5.0},
            ],
        }
    )
    assert entry["kind"] == "cable"
    paths = {wire["pin"]: wire["path_cm"] for wire in entry["wires"]}
    assert paths == {
        "1": pytest.approx(34.0),
        "2": pytest.approx(36.5),
        "3": pytest.approx(35.0),
    }
    assert entry["cable_cm"] == pytest.approx(36.5)
    assert entry["longest_pin"] == "2"


def test_summarize_cable_without_wires_falls_back_to_jacket() -> None:
    entry = logic.summarize_cable({"name": "H", "jacket_cm": 12.0, "wires": []})
    assert entry["cable_cm"] == pytest.approx(12.0)
    assert entry["longest_pin"] == ""


def test_summarize_routes_rollup() -> None:
    report = logic.summarize_routes(
        [
            {"kind": "single", "name": "W1", "conductor_cm": 1.0, "sheath_cm": 9.0},
            {
                "kind": "cable",
                "name": "C1",
                "jacket_cm": 20.0,
                "wires": [
                    {"pin": "1", "extra_cm": 2.0},
                    {"pin": "2", "extra_cm": 4.0},
                ],
            },
            {"kind": "ribbon", "name": "R1"},  # unknown to the report - skipped
        ]
    )
    assert len(report["assemblies"]) == 2
    assert report["skipped"] == 1
    totals = report["totals"]
    assert totals["wire_count"] == 1
    assert totals["cable_count"] == 1
    # 10.0 (W1) + 22.0 + 24.0 (both C1 wire paths).
    assert totals["conductor_cm"] == pytest.approx(56.0)


def test_summarize_routes_kind_defaults_to_single() -> None:
    report = logic.summarize_routes(
        [{"name": "legacy", "conductor_cm": 1.0, "sheath_cm": 2.0}]
    )
    assert report["assemblies"][0]["kind"] == "single"
    assert report["totals"]["wire_count"] == 1


def test_summarize_routes_empty() -> None:
    report = logic.summarize_routes([])
    assert report["assemblies"] == []
    assert report["totals"] == {
        "wire_count": 0,
        "cable_count": 0,
        "conductor_cm": 0.0,
    }
