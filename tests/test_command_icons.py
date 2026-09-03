"""Asset contract for the committed command-icon sets.

The icons are drawn by the ``resources/generate_icons.py`` scripts and
committed; Fusion reads the folder directly and picks the ``-dark`` /
``-disabled`` variant itself, so nothing in the add-in validates them at
runtime. These checks stand in for that: every expected file is present, is the
8-bit RGBA PNG Fusion wants, matches the size in its own filename, and no stray
variant is left behind.

They also guard the specific bug these sets replaced. Each command below
originally shipped a byte-identical copy of another command's icon, which left
it indistinguishable from that command in the panel and in the Preferences
list.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 32, 64)
THEME_VARIANTS = ("", "-dark")
ALL_VARIANTS = (*THEME_VARIANTS, "-disabled")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class IconSet:
    """One command's icon folder and the placeholder its art replaced.

    Attributes:
        command: The command module name under ``commands/``.
        variants: The filename suffixes this set is expected to ship.
        placeholder: The command whose icons it used to be a copy of, or None for
            a set that shipped with original art and so never had one. The
            duplicate-art risk for those is covered by
            :func:`test_every_command_looks_different_from_every_other`.
    """

    command: str
    variants: tuple[str, ...]
    placeholder: str | None

    @property
    def resources(self) -> Path:
        """Locate the command's resource folder.

        Returns:
            The folder Fusion reads the icons from.
        """
        return REPO_ROOT / "commands" / self.command / "resources"


ICON_SETS = (
    IconSet("teamaddins", ALL_VARIANTS, "confighub"),
    IconSet("configteamaddins", ALL_VARIANTS, "confighub"),
    IconSet("assignpartnumbers", THEME_VARIANTS, "docinfo"),
    IconSet("syncitempartnumber", THEME_VARIANTS, "docinfo"),
    IconSet("assigndrawingnumber", THEME_VARIANTS, "docinfo"),
    IconSet("measurepath", THEME_VARIANTS, None),
    IconSet("flattensurface", THEME_VARIANTS, None),
    IconSet("dochistory", ALL_VARIANTS, None),
)


def _expected_names(icon_set: IconSet) -> list[str]:
    """List the PNG filenames a set is expected to ship.

    Args:
        icon_set: The set to enumerate.

    Returns:
        Every ``<size>x<size><variant>.png`` name, in size order.
    """
    return [
        f"{size}x{size}{variant}.png" for size in SIZES for variant in icon_set.variants
    ]


def _read_ihdr(path: Path) -> tuple[int, int, int, int]:
    """Decode a PNG's IHDR chunk.

    Args:
        path: The PNG to inspect.

    Returns:
        Width, height, bit depth and colour type.

    Raises:
        AssertionError: If the file is not a PNG whose first chunk is IHDR.
    """
    blob = path.read_bytes()
    assert blob[:8] == PNG_SIGNATURE, f"{path.name} is not a PNG"
    assert blob[12:16] == b"IHDR", f"{path.name} does not start with IHDR"
    width, height, depth, color_type = struct.unpack(">IIBB", blob[16:26])
    return width, height, depth, color_type


@pytest.mark.parametrize("icon_set", ICON_SETS, ids=lambda icon_set: icon_set.command)
def test_every_variant_is_an_rgba_png_of_its_declared_size(icon_set: IconSet) -> None:
    """Each expected file exists and is an 8-bit RGBA PNG of its filename's size."""
    for name in _expected_names(icon_set):
        path = icon_set.resources / name
        assert path.is_file(), f"missing icon: {path}"
        assert path.stat().st_size > 100, f"{name} is too small to hold a glyph"

        width, height, depth, color_type = _read_ihdr(path)
        size = int(name.split("x", 1)[0])

        assert (width, height) == (size, size), f"{name} is {width}x{height}"
        assert depth == 8, f"{name} is not 8-bit"
        assert color_type == 6, f"{name} is not truecolour with alpha"


@pytest.mark.parametrize("icon_set", ICON_SETS, ids=lambda icon_set: icon_set.command)
def test_no_stray_variants(icon_set: IconSet) -> None:
    """The folder holds exactly the expected PNGs.

    A regenerated set that drops a variant would otherwise leave the old
    command's art behind for Fusion to pick up.
    """
    found = sorted(path.name for path in icon_set.resources.glob("*.png"))

    assert found == sorted(_expected_names(icon_set))


@pytest.mark.parametrize("icon_set", ICON_SETS, ids=lambda icon_set: icon_set.command)
def test_icons_are_not_the_placeholders_they_replaced(icon_set: IconSet) -> None:
    """The shipped art is drawn for this command, not copied from another."""
    if icon_set.placeholder is None:
        pytest.skip("shipped with original art; it never replaced a placeholder")

    placeholder_dir = REPO_ROOT / "commands" / icon_set.placeholder / "resources"

    for name in _expected_names(icon_set):
        placeholder = placeholder_dir / name
        if not placeholder.is_file():
            continue
        assert (icon_set.resources / name).read_bytes() != placeholder.read_bytes(), (
            f"{icon_set.command}/{name} is still a copy of {icon_set.placeholder}'s"
        )


def test_every_command_looks_different_from_every_other() -> None:
    """No two sets converge.

    The commands share motifs on purpose -- two use the puzzle piece, three use
    the number sign -- and the panel shows them side by side, so the badges have
    to keep every pair apart at every size.
    """
    for size in SIZES:
        name = f"{size}x{size}.png"
        seen: dict[bytes, str] = {}
        for icon_set in ICON_SETS:
            blob = (icon_set.resources / name).read_bytes()
            assert blob not in seen, (
                f"{icon_set.command} and {seen[blob]} ship the same {name}"
            )
            seen[blob] = icon_set.command
