"""Unit tests for the Route Wire pure-logic helpers.

Exercises the AWG sizing math, the allowed-gauge intersection, the spline
guide-point fallback geometry, and the route attribute payload. These helpers
have no Fusion dependency; the module uses package-relative imports, so it is
loaded via its full package path with the conftest scaffolding in place (which
also fabricates the ``adsk`` package).
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.routewire.logic")
schema = importlib.import_module(f"{PT_PKG}.commands.definewires.logic")


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
    assert payload["name"] == "PWR1"
    assert payload["awg"] == 22
    assert payload["od_mm"] == pytest.approx(1.54)
    assert payload["ends"] == ends
