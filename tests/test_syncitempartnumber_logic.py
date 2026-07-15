"""Unit tests for the Sync Item to Part Number pure-logic helpers.

Exercises the "sync needed" decision (``needs_sync``) and the value
normalization used by the execute-time "no item number" / "already match"
guards. These helpers have no Fusion dependency; the module uses
package-relative imports, so it is loaded via its full package path with the
conftest scaffolding in place (which also fabricates the ``adsk`` package).
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.syncitempartnumber.logic")

_AUTO_PN = "2024-01-02-03-04-05-678"
_AUTO_PN_NAMED = "Widget: 2024-01-02-03-04-05-678"


@pytest.mark.parametrize(
    "item, part, expected",
    [
        (None, "A-100", False),  # no item number
        ("", "A-100", False),  # no item number
        ("A-100", "A-100", False),  # exact match
        ("  A-100 ", "A-100", False),  # match after strip
        ("A-100", "  A-100  ", False),  # match after strip (part side)
        ("A-100", "B-200", True),  # genuine mismatch
        ("A-100", "", True),  # item exists, no part number
        ("A-100", None, True),  # item exists, no part number
        ("A-100", _AUTO_PN, True),  # part is Fusion auto-PN -> normalizes to ""
        ("A-100", _AUTO_PN_NAMED, True),  # auto-PN "Name: timestamp" form
        ("PN-000038", "PN-000038", False),  # real Manage item number, matches part
        ("PN-000038", "Chassis Bottom", True),  # item differs from a named part
    ],
)
def test_needs_sync(item, part, expected) -> None:
    assert logic.needs_sync(item, part) is expected


def test_normalize_item_strips_and_handles_empty() -> None:
    assert logic.normalize_item("  X ") == "X"
    assert logic.normalize_item("") == ""
    assert logic.normalize_item(None) == ""


def test_normalize_pn_strips() -> None:
    assert logic.normalize_pn("  A-100 ") == "A-100"


def test_normalize_pn_empty() -> None:
    assert logic.normalize_pn("") == ""
    assert logic.normalize_pn(None) == ""


def test_normalize_pn_treats_auto_timestamp_as_empty() -> None:
    assert logic.normalize_pn(_AUTO_PN) == ""
    assert logic.normalize_pn(_AUTO_PN_NAMED) == ""
