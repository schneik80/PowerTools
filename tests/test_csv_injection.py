"""Unit tests for the CSV/formula-injection guard in exportbomcsv (_csv_cell).

These lock in the security fix (T7): a BOM cell whose first character a
spreadsheet would treat as a formula (``= + - @``) or as a control character
(tab/CR) is prefixed with a single quote so it imports as literal text, while
ordinary values pass through untouched. The command module imports ``adsk`` and
uses package-relative imports, so it is loaded via its full package path with
the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
entry = importlib.import_module(f"{PT_PKG}.commands.exportbomcsv.entry")


def test_plain_value_passes_through_unchanged() -> None:
    """A value with no risky leading character is returned as-is."""
    # Arrange / Act / Assert
    assert entry._csv_cell("Widget-A") == "Widget-A"


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_risky_leading_character_is_neutralized(prefix: str) -> None:
    """A cell starting with a formula/control char gains a single-quote guard."""
    # Arrange
    value = f"{prefix}danger"

    # Act
    result = entry._csv_cell(value)

    # Assert
    assert result == f"'{value}"


def test_empty_value_is_not_prefixed() -> None:
    """An empty string has no leading character to guard and stays empty."""
    assert entry._csv_cell("") == ""


def test_non_string_is_stringified_then_checked() -> None:
    """Non-string cell values are coerced with str() before inspection."""
    assert entry._csv_cell(5) == "5"


def test_interior_formula_character_is_ignored() -> None:
    """Only the FIRST character matters; an interior '=' is left untouched."""
    assert entry._csv_cell("PN=1234") == "PN=1234"
