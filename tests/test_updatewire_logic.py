"""Unit tests for the Update Wire pure-logic helpers.

Exercises the route-end resolution ladder (entity token, then unique
connector id), the wire lookup by id with pin fallback, and route-payload
parameter validation. These helpers have no Fusion dependency; the module
uses package-relative imports, so it is loaded via its full package path
with the conftest scaffolding in place (which also fabricates the ``adsk``
package).
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.updatewire.logic")

_CANDIDATES = [
    {"token": "tok-a", "connector_id": "ConnA-3f9a2b1c"},
    {"token": "tok-b", "connector_id": "ConnB-9ab04d12"},
    {"token": "tok-b2", "connector_id": "ConnB-9ab04d12"},  # second instance
    {"token": "tok-x", "connector_id": ""},  # not a connector
]


# ---------------------------------------------------------------------------
# choose_end_occurrence
# ---------------------------------------------------------------------------
def test_choose_end_token_match_wins() -> None:
    end = {"occ_token": "tok-b2", "connector_id": "ConnB-9ab04d12"}
    assert logic.choose_end_occurrence(_CANDIDATES, end) == (2, "token")


def test_choose_end_token_beats_connector_id() -> None:
    # Token points at A even though the connector_id says B.
    end = {"occ_token": "tok-a", "connector_id": "ConnB-9ab04d12"}
    assert logic.choose_end_occurrence(_CANDIDATES, end) == (0, "token")


def test_choose_end_unique_connector_id_fallback() -> None:
    end = {"occ_token": "tok-dead", "connector_id": "ConnA-3f9a2b1c"}
    assert logic.choose_end_occurrence(_CANDIDATES, end) == (0, "connector_id")


def test_choose_end_ambiguous_connector_id() -> None:
    end = {"occ_token": "tok-dead", "connector_id": "ConnB-9ab04d12"}
    assert logic.choose_end_occurrence(_CANDIDATES, end) == (None, "ambiguous")


def test_choose_end_not_found() -> None:
    end = {"occ_token": "tok-dead", "connector_id": "ConnZ-00000000"}
    assert logic.choose_end_occurrence(_CANDIDATES, end) == (None, "not_found")


def test_choose_end_empty_fields() -> None:
    assert logic.choose_end_occurrence(_CANDIDATES, {}) == (None, "not_found")
    # An empty connector_id must not match candidates that also have "".
    end = {"occ_token": "", "connector_id": ""}
    assert logic.choose_end_occurrence(_CANDIDATES, end) == (None, "not_found")


def test_choose_end_no_candidates() -> None:
    end = {"occ_token": "tok-a", "connector_id": "ConnA-3f9a2b1c"}
    assert logic.choose_end_occurrence([], end) == (None, "not_found")


# ---------------------------------------------------------------------------
# find_wire
# ---------------------------------------------------------------------------
_WIRES = {
    "1": {"wire_id": "w-one", "pin": "1"},
    "2": {"wire_id": "w-two", "pin": "2"},
}


def test_find_wire_by_wire_id() -> None:
    assert logic.find_wire(_WIRES, "w-two", "1")["pin"] == "2"


def test_find_wire_pin_fallback() -> None:
    # Wire id gone (wire redefined) - fall back to the stored pin.
    assert logic.find_wire(_WIRES, "w-dead", "1")["pin"] == "1"


def test_find_wire_missing() -> None:
    assert logic.find_wire(_WIRES, "w-dead", "9") is None
    assert logic.find_wire({}, "w-one", "1") is None


# ---------------------------------------------------------------------------
# coerce_route_params
# ---------------------------------------------------------------------------
def test_coerce_route_params_valid() -> None:
    payload = {"name": " PWR1 ", "awg": 22, "od_mm": 1.54}
    assert logic.coerce_route_params(payload) == {
        "name": "PWR1",
        "awg": 22,
        "od_mm": pytest.approx(1.54),
    }


def test_coerce_route_params_numeric_strings() -> None:
    payload = {"name": "S", "awg": "20", "od_mm": "2.0"}
    params = logic.coerce_route_params(payload)
    assert params is not None
    assert params["awg"] == 20
    assert params["od_mm"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "", "awg": 22, "od_mm": 1.5},  # empty name
        {"name": "X", "awg": "junk", "od_mm": 1.5},  # bad gauge
        {"name": "X", "awg": 99, "od_mm": 1.5},  # gauge out of range
        {"name": "X", "awg": 22, "od_mm": 0.0},  # non-positive diameter
        {"name": "X", "awg": 22},  # missing diameter
    ],
)
def test_coerce_route_params_damaged(payload) -> None:
    assert logic.coerce_route_params(payload) is None
