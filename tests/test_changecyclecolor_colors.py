"""Unit tests for ``commands/changecyclecolor/colors.py``.

``colors.py`` does ``from .fusion_install import find_river_rubicon_xml`` (a
relative import), so it cannot be loaded as a bare top-level module — and
importing the ``commands`` package ``__init__`` would pull in heavy Fusion
dependencies. Instead we build a synthetic parent package (``ccc_pkg``) pointed
at the ``changecyclecolor`` directory and load each module directly from its
file path via ``importlib.util.spec_from_file_location``. The relative import
then resolves against the synthetic package without touching ``commands``.

Tests target the pure-logic color helpers only — hex/RGB conversion, unit-float
coercion, RGB parsing, and rainbow sorting. ``load_color_cycle``'s file I/O is
not exercised because it needs the Fusion install's RiverRubicon.xml.
"""

import importlib.util
import sys
import types
from pathlib import Path

_CCC_DIR = Path(__file__).resolve().parent.parent / "commands" / "changecyclecolor"

# Synthetic parent package so colors.py's `from .fusion_install import ...` resolves.
_pkg = types.ModuleType("ccc_pkg")
_pkg.__path__ = [str(_CCC_DIR)]
sys.modules["ccc_pkg"] = _pkg


def _load(mod_name):
    spec = importlib.util.spec_from_file_location(
        f"ccc_pkg.{mod_name}", _CCC_DIR / f"{mod_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ccc_pkg.{mod_name}"] = module
    spec.loader.exec_module(module)
    return module


_load("fusion_install")  # dependency must exist before colors.py loads
colors = _load("colors")


# ── hex_to_rgb / rgb_to_hex ────────────────────────────────────────────────────
def test_rgb_to_hex_uppercases_and_prefixes() -> None:
    """RGB tuple serializes to an uppercase, hash-prefixed hex string."""
    assert colors.rgb_to_hex((233, 72, 40)) == "#E94828"


def test_hex_to_rgb_with_hash() -> None:
    """A leading ``#`` is stripped before parsing."""
    assert colors.hex_to_rgb("#E94828") == (233, 72, 40)


def test_hex_to_rgb_without_hash() -> None:
    """The hash is optional; a bare 6-char hex string parses too."""
    assert colors.hex_to_rgb("e94828") == (233, 72, 40)


def test_hex_to_rgb_roundtrip() -> None:
    """``hex_to_rgb`` is the inverse of ``rgb_to_hex``."""
    rgb = (233, 72, 40)
    assert colors.hex_to_rgb(colors.rgb_to_hex(rgb)) == rgb


def test_hex_to_rgb_wrong_length_returns_none() -> None:
    """A string that is not exactly 6 hex digits yields ``None``."""
    assert colors.hex_to_rgb("#FFF") is None
    assert colors.hex_to_rgb("#E948288") is None


def test_hex_to_rgb_non_hex_returns_none() -> None:
    """A 6-char string with non-hex characters yields ``None``."""
    assert colors.hex_to_rgb("#GGGGGG") is None
    assert colors.hex_to_rgb("zzzzzz") is None


# ── _coerce_unit_float ──────────────────────────────────────────────────────────
def test_coerce_unit_float_plain_values() -> None:
    """Well-formed unit floats pass through unchanged."""
    assert colors._coerce_unit_float("0.5") == 0.5
    assert colors._coerce_unit_float("1") == 1.0
    assert colors._coerce_unit_float("0") == 0.0


def test_coerce_unit_float_missing_decimal_repair() -> None:
    """A decimal-less token > 1 is repaired by prepending a decimal point."""
    assert colors._coerce_unit_float("5412") == 0.5412


def test_coerce_unit_float_garbage_returns_none() -> None:
    """A non-numeric token yields ``None``."""
    assert colors._coerce_unit_float("abc") is None


def test_coerce_unit_float_out_of_range_with_decimal_returns_none() -> None:
    """A value > 1 that already has a decimal point is not repairable."""
    assert colors._coerce_unit_float("1.5") is None


# ── _parse_rgb ──────────────────────────────────────────────────────────────────
def test_parse_rgb_valid_triple() -> None:
    """Three space-separated unit floats scale to 0..255 ints.

    ``int(round(0.5 * 255))`` is 128 (round-half-to-even on 127.5).
    """
    assert colors._parse_rgb("0 0.5 1") == (0, 128, 255)


def test_parse_rgb_wrong_arity_returns_none() -> None:
    """A token count other than 3 yields ``None``."""
    assert colors._parse_rgb("0 0.5") is None


# ── sort_rainbow ────────────────────────────────────────────────────────────────
def test_sort_rainbow_neutral_last_and_hue_ordered() -> None:
    """Neutrals sink to the end; saturated colors order by hue (red < blue)."""
    red = ("Red", (233, 72, 40))
    blue = ("Blue", (40, 90, 233))
    gray = ("Gray", (128, 128, 128))

    result = colors.sort_rainbow([blue, gray, red])
    names = [name for name, _ in result]

    # The near-neutral gray is pushed to the end of the band.
    assert names[-1] == "Gray"
    # Within the saturated rainbow, red (lower hue) precedes blue.
    assert names.index("Red") < names.index("Blue")
    # Sorting preserves the swatch set.
    assert set(names) == {"Red", "Blue", "Gray"}


if __name__ == "__main__":
    for _name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[_name]()
        print(f"PASS {_name}")
    print("ALL TEST FUNCS PASSED")
