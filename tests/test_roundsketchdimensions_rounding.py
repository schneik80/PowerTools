"""Unit tests for ``commands/roundsketchdimensions/rounding.py``.

``rounding.py`` is a pure module with no ``adsk`` dependency and no relative
import, so it is loaded directly from its file path — no synthetic package or
Fusion stub is needed (contrast ``test_changecyclecolor_colors.py``).
"""

import importlib.util
from pathlib import Path

_RSD = (
    Path(__file__).resolve().parent.parent
    / "commands" / "roundsketchdimensions" / "rounding.py"
)

_spec = importlib.util.spec_from_file_location("rsd_rounding", _RSD)
rounding = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rounding)


# ── is_plain_numeric_expression ────────────────────────────────────────────────
def test_plain_numeric_accepts_value_with_unit() -> None:
    assert rounding.is_plain_numeric_expression("12.5 mm")
    assert rounding.is_plain_numeric_expression("0.0625 in")
    assert rounding.is_plain_numeric_expression("50 ft")


def test_plain_numeric_accepts_bare_number_and_fraction() -> None:
    assert rounding.is_plain_numeric_expression("0.5")
    assert rounding.is_plain_numeric_expression("1/2 in")
    assert rounding.is_plain_numeric_expression("-3 mm")


def test_plain_numeric_rejects_formulas_and_references() -> None:
    assert not rounding.is_plain_numeric_expression("width/2")
    assert not rounding.is_plain_numeric_expression("d1")
    assert not rounding.is_plain_numeric_expression("sin(30 deg)")
    assert not rounding.is_plain_numeric_expression("2*d0")
    assert not rounding.is_plain_numeric_expression("")


def test_plain_numeric_strips_longest_unit_first() -> None:
    # "mm" must be stripped before "m" so a millimetre value is still plain.
    assert rounding.is_plain_numeric_expression("0.5 mm")
    assert rounding.is_plain_numeric_expression("0.5 m")


# ── round_to_increment ─────────────────────────────────────────────────────────
def test_round_to_increment_snaps_to_grid() -> None:
    assert rounding.round_to_increment(12.4837, 0.5) == 12.5
    assert rounding.round_to_increment(0.74, 0.25) == 0.75


def test_round_to_increment_is_idempotent() -> None:
    once = rounding.round_to_increment(12.4837, 0.5)
    assert rounding.round_to_increment(once, 0.5) == once


def test_round_to_increment_handles_zero_and_negatives() -> None:
    assert rounding.round_to_increment(0.0, 0.5) == 0.0
    assert rounding.round_to_increment(-1.24, 0.5) == -1.0


def test_round_to_increment_nonpositive_is_noop() -> None:
    assert rounding.round_to_increment(3.14159, 0.0) == 3.14159
    assert rounding.round_to_increment(3.14159, -1.0) == 3.14159


def test_round_to_increment_exact_for_fraction_grid() -> None:
    # 1/64 in grid is exact in decimal.
    assert rounding.round_to_increment(0.30, 1.0 / 64) == 19.0 / 64


# ── smart_default_index ────────────────────────────────────────────────────────
def test_smart_default_empty_returns_middle() -> None:
    idx = rounding.smart_default_index([], rounding.MM_INCREMENTS)
    assert idx == len(rounding.MM_INCREMENTS) // 2


def test_smart_default_medium_metric_picks_reasonable_grid() -> None:
    # ~50 mm characteristic size -> target 2.5 mm -> largest increment <= 2.5 is 2.0.
    idx = rounding.smart_default_index([48.0, 50.0, 52.0], rounding.MM_INCREMENTS)
    assert rounding.MM_INCREMENTS[idx] == 2.0


def test_smart_default_tiny_clamps_to_smallest() -> None:
    # Everything larger than target -> smallest increment (index 0).
    idx = rounding.smart_default_index([0.1], rounding.MM_INCREMENTS)
    assert idx == 0


def test_smart_default_works_on_fraction_grid() -> None:
    incs = rounding.fraction_increments()
    # ~1 in characteristic size -> target 0.05 in; largest fraction inc <= 0.05
    # is 1/32 (0.03125).
    idx = rounding.smart_default_index([1.0, 1.0, 1.0], incs)
    assert incs[idx] == 1.0 / 32


# ── formatting ─────────────────────────────────────────────────────────────────
def test_format_value_expression_trims_noise() -> None:
    assert rounding.format_value_expression(12.5, "mm") == "12.5 mm"
    assert rounding.format_value_expression(0.015625, "in") == "0.015625 in"
    assert rounding.format_value_expression(-0.0, "mm") == "0 mm"


def test_decimal_increment_label() -> None:
    assert rounding.decimal_increment_label(0.5, "mm") == "0.5 mm"
    assert rounding.decimal_increment_label(0.05, "in") == "0.05 in"


def test_fraction_increment_label() -> None:
    assert rounding.fraction_increment_label(16) == "1/16 in"
    assert rounding.fraction_increment_label(1) == "1 in"
    assert rounding.fraction_increment_label(2) == "1/2 in"


# ── increment list invariants ──────────────────────────────────────────────────
def test_imperial_lists_are_equal_length() -> None:
    # The slider is built once; the fraction and decimal grids must share length.
    assert len(rounding.INCH_FRACTION_DENOMS) == len(rounding.INCH_DECIMAL_INCH)


def test_increment_lists_are_ascending() -> None:
    for lst in (rounding.MM_INCREMENTS, rounding.INCH_DECIMAL_INCH, rounding.fraction_increments()):
        assert lst == sorted(lst)
