"""Unit tests for the shared cable routing math.

Exercises ``commands/cable_shared/routing.py``: the AWG sizing math, the
allowed-gauge intersections, the spline guide-point fallback geometry, the
route attribute payload, and the build-result summary notes. These helpers
have no Fusion dependency; the module uses package-relative imports, so it
is loaded via its full package path with the conftest scaffolding in place
(which also fabricates the ``adsk`` package).
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.cable_shared.routing")
schema = importlib.import_module(f"{PT_PKG}.commands.cable_shared.schema")


# ---------------------------------------------------------------------------
# AWG sizing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "awg, expected_mm",
    [
        (10, 2.588),
        (16, 1.291),
        (20, 0.812),
        (24, 0.511),
        (30, 0.255),
        (36, 0.127),  # the formula's anchor point
    ],
)
def test_conductor_diameter_known_values(awg, expected_mm) -> None:
    assert logic.conductor_diameter_mm(awg) == pytest.approx(expected_mm, rel=5e-3)


def test_conductor_diameter_monotonic() -> None:
    diameters = [logic.conductor_diameter_mm(awg) for awg in range(0, 41)]
    assert diameters == sorted(diameters, reverse=True)


def test_recommended_od_adds_sheath_walls() -> None:
    conductor = logic.conductor_diameter_mm(24)
    assert logic.recommended_od_mm(24) == pytest.approx(conductor + 0.9)
    assert logic.recommended_od_mm(24, wall_mm=0.2) == pytest.approx(conductor + 0.4)


# ---------------------------------------------------------------------------
# Allowed-gauge intersection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "range_a, range_b, expected",
    [
        ((16, 24), (16, 24), list(range(16, 25))),  # identical
        ((16, 24), (20, 28), list(range(20, 25))),  # partial overlap
        ((16, 24), (24, 30), [24]),  # single shared size
        ((16, 20), (22, 26), []),  # disjoint
        ((22, 26), (16, 20), []),  # disjoint, reversed
        ((18, 18), (16, 24), [18]),  # degenerate range
    ],
)
def test_awg_overlap(range_a, range_b, expected) -> None:
    assert logic.awg_overlap(range_a, range_b) == expected


def test_awg_overlap_thickest_first() -> None:
    sizes = logic.awg_overlap((16, 24), (16, 24))
    assert sizes[0] == 16  # smallest AWG number = thickest wire


# ---------------------------------------------------------------------------
# Spline guide points (tangency fallback)
# ---------------------------------------------------------------------------
def test_spline_guide_points_continue_line_directions() -> None:
    # Wire A exits along +x at the origin; wire B exits along -x at (10,0,0).
    points = logic.spline_guide_points(
        strip_a=(-2.0, 0.0, 0.0),
        exit_a=(0.0, 0.0, 0.0),
        strip_b=(12.0, 0.0, 0.0),
        exit_b=(10.0, 0.0, 0.0),
    )
    assert len(points) == 4
    assert points[0] == (0.0, 0.0, 0.0)
    assert points[3] == (10.0, 0.0, 0.0)
    # reach = 25% of the 10-unit span, continuing each strip->exit direction.
    assert points[1] == pytest.approx((2.5, 0.0, 0.0))
    assert points[2] == pytest.approx((7.5, 0.0, 0.0))


def test_spline_guide_points_off_axis() -> None:
    points = logic.spline_guide_points(
        strip_a=(0.0, 0.0, -4.0),
        exit_a=(0.0, 0.0, 0.0),
        strip_b=(0.0, 8.0, 0.0),
        exit_b=(0.0, 8.0, -6.0),
    )
    span = (0.0**2 + 8.0**2 + 6.0**2) ** 0.5
    reach = 0.25 * span
    assert points[1] == pytest.approx((0.0, 0.0, reach))
    assert points[2] == pytest.approx((0.0, 8.0, -6.0 - reach))


def test_spline_guide_points_degenerate_line_falls_back() -> None:
    # strip == exit on side A: guide must fall back to the exit-to-exit
    # direction instead of dividing by zero.
    points = logic.spline_guide_points(
        strip_a=(0.0, 0.0, 0.0),
        exit_a=(0.0, 0.0, 0.0),
        strip_b=(10.0, 0.0, 0.0),
        exit_b=(8.0, 0.0, 0.0),
    )
    assert points[1] == pytest.approx((2.0, 0.0, 0.0))  # toward exit_b
    assert points[2] == pytest.approx((6.0, 0.0, 0.0))


def test_spline_guide_points_custom_fraction() -> None:
    points = logic.spline_guide_points(
        strip_a=(-1.0, 0.0, 0.0),
        exit_a=(0.0, 0.0, 0.0),
        strip_b=(11.0, 0.0, 0.0),
        exit_b=(10.0, 0.0, 0.0),
        fraction=0.1,
    )
    assert points[1] == pytest.approx((1.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# Cable sizing (bundle factors per standard cable-design tables)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "count, factor",
    [
        (1, 1.0),
        (2, 2.0),
        (3, 2.155),
        (4, 2.414),
        (7, 3.0),
        (12, 4.03),
    ],
)
def test_bundle_factor_table(count, factor) -> None:
    assert logic.bundle_factor(count) == pytest.approx(factor)


def test_bundle_factor_large_counts_use_sqrt_approximation() -> None:
    assert logic.bundle_factor(19) == pytest.approx(1.155 * 19**0.5)
    # Continuous with the table at the changeover point.
    assert logic.bundle_factor(13) > logic.bundle_factor(12)


def test_bundle_factor_degenerate_counts() -> None:
    assert logic.bundle_factor(0) == 1.0
    assert logic.bundle_factor(-3) == 1.0


def test_cable_od_three_conductors() -> None:
    # 3 x 1.5 mm wires: bundle 1.5 * 2.155 * 1.03 + 2 * 0.6 jacket.
    expected = 1.5 * 2.155 * 1.03 + 1.2
    assert logic.cable_od_mm(1.5, 3) == pytest.approx(expected)


def test_cable_od_custom_jacket_wall() -> None:
    got = logic.cable_od_mm(1.0, 2, jacket_wall_mm=0.0)
    assert got == pytest.approx(2.0 * 1.03)


# ---------------------------------------------------------------------------
# Pin sorting and multi-range gauge intersection
# ---------------------------------------------------------------------------
def test_sort_pins_numeric_aware() -> None:
    assert logic.sort_pins(["10", "2", "1"]) == ["1", "2", "10"]
    assert logic.sort_pins(["B", "2", "A", "1"]) == ["1", "2", "A", "B"]
    assert logic.sort_pins([]) == []


def test_wire_color_palette_has_twelve_unique_keys() -> None:
    assert len(logic.WIRE_COLOR_KEYS) == 12
    assert len(set(logic.WIRE_COLOR_KEYS)) == 12
    for _key, rgb in logic.WIRE_COLORS:
        assert len(rgb) == 3
        assert all(0 <= channel <= 255 for channel in rgb)


def test_wire_color_rgb_and_default() -> None:
    assert logic.wire_color_rgb("black") == (25, 25, 25)
    assert logic.wire_color_rgb("nonsense") == logic.wire_color_rgb(
        logic.DEFAULT_WIRE_COLOR
    )


def test_normalize_wire_color() -> None:
    assert logic.normalize_wire_color("Dark Blue") == "dark blue"
    assert logic.normalize_wire_color("  red ") == "red"
    assert logic.normalize_wire_color("chartreuse") == logic.DEFAULT_WIRE_COLOR
    assert logic.normalize_wire_color(None) == logic.DEFAULT_WIRE_COLOR


def test_assign_wire_colors_follows_palette_and_cycles() -> None:
    assert logic.assign_wire_colors(3) == ["red", "black", "white"]
    colors = logic.assign_wire_colors(14)
    assert colors[:12] == list(logic.WIRE_COLOR_KEYS)
    assert colors[12:] == ["red", "black"]
    assert logic.assign_wire_colors(0) == []


def test_sort_pins_unicode_digits_never_crash() -> None:
    # Superscript/circled digits pass str.isdigit() but int() raises
    # ValueError - they must sort lexically instead of crashing the dialog.
    assert logic.sort_pins(["²", "2", "b"]) == ["2", "b", "²"]
    assert logic.sort_pins(["②", "10", "1"]) == ["1", "10", "②"]


@pytest.mark.parametrize(
    "ranges, expected",
    [
        ([], []),
        ([(16, 24)], list(range(16, 25))),
        ([(16, 24), (20, 28), (18, 22)], [20, 21, 22]),
        ([(16, 24), (26, 30)], []),  # one disjoint pair empties the set
        ([(16, 24), (24, 16)], []),  # inverted range contributes nothing
    ],
)
def test_awg_overlap_many(ranges, expected) -> None:
    assert logic.awg_overlap_many(ranges) == expected


# ---------------------------------------------------------------------------
# Fan-out guide points (cable tangency fallback)
# ---------------------------------------------------------------------------
def test_fanout_guide_points_continue_exit_direction() -> None:
    points = logic.fanout_guide_points(
        strip=(-2.0, 0.0, 0.0),
        exit_pt=(0.0, 0.0, 0.0),
        cable_pt=(0.0, 8.0, 0.0),
    )
    assert len(points) == 3
    assert points[0] == (0.0, 0.0, 0.0)
    assert points[2] == (0.0, 8.0, 0.0)
    # Guide continues the +x exit direction by 25% of the 8-unit span.
    assert points[1] == pytest.approx((2.0, 0.0, 0.0))


def test_fanout_guide_points_degenerate_exit_line() -> None:
    points = logic.fanout_guide_points(
        strip=(0.0, 0.0, 0.0),
        exit_pt=(0.0, 0.0, 0.0),
        cable_pt=(4.0, 0.0, 0.0),
    )
    assert points[1] == pytest.approx((1.0, 0.0, 0.0))  # toward the cable


# ---------------------------------------------------------------------------
# Route payload
# ---------------------------------------------------------------------------
def test_route_payload_round_trip() -> None:
    ends = [
        {"connector_id": "ConnA-3f9a2b1c", "wire_id": "7c1d2e3f", "pin": "1"},
        {"connector_id": "ConnB-9ab04d12", "wire_id": "55aa66bb", "pin": "4"},
    ]
    value = logic.build_route_payload(
        {"name": "PWR1", "awg": 22, "od_mm": 1.54, "ends": ends}
    )
    payload = schema.parse_payload(value)
    assert payload is not None
    assert payload["schema"] == schema.SCHEMA_VERSION
    assert payload["kind"] == "single"  # default when not given
    assert payload["name"] == "PWR1"
    assert payload["awg"] == 22
    assert payload["od_mm"] == pytest.approx(1.54)
    assert payload["ends"] == ends
    assert "cable_od_mm" not in payload


def test_route_payload_cable_kind() -> None:
    ends = [
        {
            "connector_id": "A",
            "occ_token": "t1",
            "pins": ["1", "2"],
            "wire_ids": ["w1", "w2"],
        },
        {
            "connector_id": "B",
            "occ_token": "t2",
            "pins": ["1", "2"],
            "wire_ids": ["w3", "w4"],
        },
    ]
    value = logic.build_route_payload(
        {
            "kind": logic.KIND_CABLE,
            "name": "HARN1",
            "awg": 24,
            "od_mm": 1.41,
            "cable_od_mm": 4.33,
            "ends": ends,
        }
    )
    payload = schema.parse_payload(value)
    assert payload is not None
    assert payload["kind"] == "cable"
    assert payload["cable_od_mm"] == pytest.approx(4.33)
    assert payload["ends"] == ends


def test_route_payload_carries_colors() -> None:
    single = schema.parse_payload(
        logic.build_route_payload(
            {"name": "W", "awg": 22, "od_mm": 1.5, "ends": [], "color": "pink"}
        )
    )
    assert single is not None
    assert single["color"] == "pink"
    cable = schema.parse_payload(
        logic.build_route_payload(
            {
                "kind": logic.KIND_CABLE,
                "name": "C",
                "awg": 24,
                "od_mm": 1.4,
                "cable_od_mm": 5.0,
                "colors": ["red", "black"],
                "ends": [],
            }
        )
    )
    assert cable is not None
    assert cable["colors"] == ["red", "black"]
    # Colors stay optional - a legacy payload omits them entirely.
    legacy = schema.parse_payload(
        logic.build_route_payload({"name": "L", "awg": 22, "od_mm": 1.5, "ends": []})
    )
    assert legacy is not None
    assert "color" not in legacy
    assert "colors" not in legacy


# ---------------------------------------------------------------------------
# Build-result summary notes (shared by Route Wire and Update Wire)
# ---------------------------------------------------------------------------
def test_result_notes_clean_result_is_empty() -> None:
    result = {"spline_fallback": False, "baked_points": 0, "dropped_tangents": 0}
    assert logic.result_notes(result) == ""
    assert logic.result_notes({}) == ""  # missing keys read as clean


def test_result_notes_each_flag_appears() -> None:
    notes = logic.result_notes(
        {"spline_fallback": True, "baked_points": 2, "dropped_tangents": 1}
    )
    assert "guide points" in notes
    assert "2 point(s)" in notes
    assert "1 fan-out tangency" in notes


def test_result_notes_single_flag_only_mentions_itself() -> None:
    notes = logic.result_notes({"baked_points": 3})
    assert "3 point(s)" in notes
    assert "guide points" not in notes
    assert "tangency" not in notes
