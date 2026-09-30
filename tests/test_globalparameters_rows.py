"""Unit tests for ``commands/globalParameters/rows.py``.

``rows.py`` is a pure module with no ``adsk`` dependency and no relative
import, so it is loaded directly from its file path — no synthetic package or
Fusion stub is needed (contrast ``test_flattensurface_entry.py``).

The module exists because the dialog's validator skipped blank-name rows while
``_collect_rows`` did not, so the always-present empty row reached
``userParameters.add("", ...)``. Both now call the functions tested here.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_ROWS = (
    Path(__file__).resolve().parent.parent / "commands" / "globalParameters" / "rows.py"
)

_spec = importlib.util.spec_from_file_location("gp_rows", _ROWS)
rows = importlib.util.module_from_spec(_spec)
# ``@dataclass`` under ``from __future__ import annotations`` resolves string
# annotations through ``sys.modules[cls.__module__]``, so register before exec.
sys.modules[_spec.name] = rows
_spec.loader.exec_module(rows)


def _row(
    name: str,
    value: str = "1.0",
    unit: str = "mm",
    comment: str = "",
    enabled: bool = True,
    row: int = 1,
) -> "rows.ParameterRow":
    return rows.ParameterRow(
        row=row, enabled=enabled, name=name, value=value, unit=unit, comment=comment
    )


# ── module hygiene ─────────────────────────────────────────────────────────────
def test_module_is_adsk_free() -> None:
    source = _ROWS.read_text(encoding="utf-8")
    assert "adsk" not in source.replace("``adsk``", "")
    assert "from ." not in source


# ── the shared skip rule ───────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["", "   ", "\t", " \n "])
def test_blank_or_whitespace_name_is_blank_row(name: str) -> None:
    assert rows.is_blank_row(_row(name))


def test_named_row_is_not_blank() -> None:
    assert not rows.is_blank_row(_row("width"))
    assert not rows.is_blank_row(_row("  width  "))


def test_collector_skips_blank_rows() -> None:
    table = [_row(""), _row("width", "10"), _row("   ", "5"), _row("depth", "2")]
    assert [p["name"] for p in rows.collect_parameter_rows(table)] == [
        "width",
        "depth",
    ]


def test_collector_of_only_the_default_blank_row_is_empty() -> None:
    # The dialog always opens with one blank row; it must collect to nothing.
    assert rows.collect_parameter_rows([_row("", "0.0", "mm", "", True)]) == []


def test_validator_skips_blank_rows_by_the_same_rule() -> None:
    table = [_row(""), _row("   ", value="not a number"), _row("width", "10")]
    assert rows.validate_parameter_rows(table) == ""


def test_collector_and_validator_agree_on_every_row() -> None:
    table = [
        _row("", row=1),
        _row("a", "1", row=2),
        _row("  ", "x", row=3),
        _row("b", "2", row=4),
    ]
    kept = {p["name"] for p in rows.collect_parameter_rows(table)}
    considered = {r.name.strip() for r in table if not rows.is_blank_row(r)}
    assert kept == considered == {"a", "b"}
    assert rows.validate_parameter_rows(table) == ""


# ── collector output shape ─────────────────────────────────────────────────────
def test_collector_preserves_order_and_dict_shape() -> None:
    table = [
        _row("width", "25.4", "mm", "outer", True, row=1),
        _row(" depth ", "", "in", "", False, row=2),
        _row("height", " 3 ", "cm", " padded ", True, row=3),
    ]
    assert rows.collect_parameter_rows(table) == [
        {
            "enabled": True,
            "name": "width",
            "value": 25.4,
            "unit": "mm",
            "comment": "outer",
        },
        {"enabled": False, "name": "depth", "value": 0.0, "unit": "in", "comment": ""},
        {
            "enabled": True,
            "name": "height",
            "value": 3.0,
            "unit": "cm",
            "comment": " padded ",
        },
    ]


def test_collector_value_is_a_float() -> None:
    (p,) = rows.collect_parameter_rows([_row("w", "7")])
    assert isinstance(p["value"], float) and p["value"] == 7.0


def test_collector_raises_on_unparseable_value() -> None:
    # The validator blocks execute first; the collector does not paper over it.
    with pytest.raises(ValueError):
        rows.collect_parameter_rows([_row("w", "abc")])


# ── parse_value ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text, expected",
    [("", 0.0), ("   ", 0.0), ("1", 1.0), (" 2.5 ", 2.5), ("-3", -3.0)],
)
def test_parse_value(text: str, expected: float) -> None:
    assert rows.parse_value(text) == expected


# ── is_valid_param_name ────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["a", "Width", "w_1", 'a"b', "a$b", "a°", "aµ", "A9"])
def test_valid_param_names(name: str) -> None:
    assert rows.is_valid_param_name(name) == (True, "")


def test_empty_name_is_required() -> None:
    assert rows.is_valid_param_name("") == (False, "Name is required")


@pytest.mark.parametrize("name", ["1abc", "_abc", "$x", "9"])
def test_name_must_start_with_a_letter(name: str) -> None:
    ok, reason = rows.is_valid_param_name(name)
    assert not ok and reason == "Must start with a letter"


@pytest.mark.parametrize("name", ["a b", "a-b", "a.b", "a/b", "a(b)"])
def test_name_rejects_disallowed_characters(name: str) -> None:
    ok, reason = rows.is_valid_param_name(name)
    assert not ok and reason.startswith("Only letters, digits")


@pytest.mark.parametrize("name", ["mm", "in", "deg", "pi", "kg", "psi", "s", "hr"])
def test_reserved_units_are_rejected(name: str) -> None:
    ok, reason = rows.is_valid_param_name(name)
    assert not ok and reason == f'"{name}" is a reserved Fusion unit name'


def test_reserved_units_are_case_sensitive() -> None:
    # Fusion expressions are case-sensitive: "MM" is not the millimetre unit.
    assert rows.is_valid_param_name("MM") == (True, "")
    assert rows.is_valid_param_name("Pi") == (True, "")
    assert not rows.is_valid_param_name("N")[0]


def test_reserved_units_table_is_frozen_and_nonempty() -> None:
    assert isinstance(rows.RESERVED_UNITS, frozenset)
    assert {"mm", "cm", "m", "in", "ft"} <= rows.RESERVED_UNITS


# ── validate_parameter_rows ────────────────────────────────────────────────────
def test_validator_accepts_empty_table() -> None:
    assert rows.validate_parameter_rows([]) == ""


def test_validator_reports_invalid_name_with_row_number() -> None:
    table = [_row("ok", row=1), _row("1bad", row=2)]
    assert (
        rows.validate_parameter_rows(table)
        == 'Row 2: "1bad" — Must start with a letter'
    )


def test_validator_reports_reserved_unit_name() -> None:
    assert (
        rows.validate_parameter_rows([_row("mm", row=3)])
        == 'Row 3: "mm" — "mm" is a reserved Fusion unit name'
    )


def test_validator_strips_name_before_checking() -> None:
    assert rows.validate_parameter_rows([_row("  width  ")]) == ""
    assert rows.validate_parameter_rows([_row("  mm  ", row=2)]).startswith(
        'Row 2: "mm"'
    )


def test_validator_rejects_duplicate_names() -> None:
    table = [_row("width", row=1), _row(" width ", row=2)]
    assert rows.validate_parameter_rows(table) == 'Duplicate parameter name: "width"'


def test_validator_duplicates_are_case_sensitive() -> None:
    assert rows.validate_parameter_rows([_row("width"), _row("Width")]) == ""


def test_validator_rejects_non_numeric_value() -> None:
    table = [_row("width", " abc ", row=4)]
    assert (
        rows.validate_parameter_rows(table)
        == 'Row 4: value "abc" is not a valid number'
    )


def test_validator_accepts_empty_value_as_zero() -> None:
    assert rows.validate_parameter_rows([_row("width", "")]) == ""


def test_validator_reports_first_failure_in_table_order() -> None:
    table = [_row("width", "x", row=1), _row("mm", row=2)]
    assert rows.validate_parameter_rows(table).startswith("Row 1:")
