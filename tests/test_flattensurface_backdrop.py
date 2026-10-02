"""Tests for the Flatten Surface marker ink.

The Min and Max markers are black or white to suit the viewport backdrop of
the active lighting environment. The XML fragments below carry the values the
shipped environments declare, so the expected ink for each is pinned whether
or not Fusion is installed; the last test re-checks them against a real install
when one is present.
"""

import importlib.util
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "fs_backdrop", REPO_ROOT / "commands" / "flattensurface" / "backdrop.py"
)
backdrop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backdrop)


def _env(grid=None, background=None):
    parts = ["<Env>"]
    if grid is not None:
        parts.append(f'<GridBackground ARGB="{grid}" />')
    if background is not None:
        parts.append(f'<Background RGB="{background}" />')
    parts.append("</Env>")
    return ET.fromstring("".join(parts))


# (environment, GridBackground ARGB, Background RGB, expected ink) as shipped.
SHIPPED = [
    ("DarkSky", "0.1 1 1 1", "0.1647 0.1647 0.1647", "white"),
    ("RiverRubicon", "0.1 1 1 1", ".1804 .2039 .2510", "white"),
    ("TranquilityBlue", "0.1 1 1 1", "0 .329 .65", "white"),
    ("InfinityPool", "0.1 1 1 1", "1.0 1.0 1.0", "white"),
    ("PhotoBooth", "0.1 0 0 0", "1.0 1.0 1.0", "black"),
    ("GreyRoom", "0.1 0 0 0", ".506 .506 .506", "black"),
    ("Studio3", "0.1 0 0 0", ".5 .5 .5", "black"),
]


def _name(ink):
    return {backdrop.WHITE: "white", backdrop.BLACK: "black"}.get(ink)


@pytest.mark.parametrize("env, grid, background, expected", SHIPPED)
def test_shipped_environments_get_contrasting_ink(env, grid, background, expected):
    assert _name(backdrop.ink_for_environment(_env(grid, background))) == expected


def test_the_grid_outranks_the_declared_background():
    """Infinity Pool declares a white background yet renders dark; its white
    grid is what says so."""
    assert backdrop.ink_for_environment(_env("0.1 1 1 1", "1 1 1")) == backdrop.WHITE


def test_background_decides_when_the_grid_is_missing_or_unreadable():
    assert backdrop.ink_for_environment(_env(None, "0.9 0.9 0.9")) == backdrop.BLACK
    assert backdrop.ink_for_environment(_env(None, "0.1 0.1 0.1")) == backdrop.WHITE
    assert backdrop.ink_for_environment(_env("bad", "0.1 0.1 0.1")) == backdrop.WHITE
    assert backdrop.ink_for_environment(_env("0.1 1", "0.9 0.9 0.9")) == backdrop.BLACK


def test_nothing_readable_gives_none():
    assert backdrop.ink_for_environment(_env()) is None
    assert backdrop.ink_for_environment(_env("x", "y")) is None


def test_missing_or_malformed_file_gives_none(tmp_path):
    assert backdrop.ink_for_environment_xml(None) is None
    assert backdrop.ink_for_environment_xml("") is None
    assert backdrop.ink_for_environment_xml(str(tmp_path / "absent.xml")) is None
    broken = tmp_path / "broken.xml"
    broken.write_text("<Env>", encoding="utf-8")
    assert backdrop.ink_for_environment_xml(str(broken)) is None


def test_reads_a_file(tmp_path):
    path = tmp_path / "DarkSky.xml"
    path.write_text(
        '<DarkSky><GridBackground ARGB="0.1 1 1 1" /></DarkSky>', encoding="utf-8"
    )
    assert backdrop.ink_for_environment_xml(str(path)) == backdrop.WHITE


def _installed_environments_dir():
    """A shipped ``Environments`` directory, or None when Fusion is absent."""
    roots = [
        Path.home() / "Library/Application Support/Autodesk/webdeploy/production",
        Path(os.environ.get("LOCALAPPDATA", "/nonexistent"))
        / "Autodesk/webdeploy/production",
    ]
    rel = "Libraries/Neutron/Neutron/Server/Scene/Resources/Environments"
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            for base in (entry / "Autodesk Fusion.app/Contents", entry):
                for candidate in (base / rel, base / rel.split("/", 2)[2]):
                    if (candidate / "RiverRubicon/RiverRubicon.xml").is_file():
                        return candidate
    return None


_ENV_DIR = _installed_environments_dir()


@pytest.mark.skipif(_ENV_DIR is None, reason="no local Fusion install")
def test_installed_environments_match_the_pinned_ink():
    for env, _grid, _background, expected in SHIPPED:
        path = _ENV_DIR / env / f"{env}.xml"
        if path.is_file():
            assert _name(backdrop.ink_for_environment_xml(str(path))) == expected, env
