"""Unit tests for ``commands/changecyclecolor/fusion_install.py``.

The module resolves paths inside the running Fusion install, and those paths
have a different shape on macOS (everything under an ``Autodesk Fusion.app``
bundle) than on Windows (no bundle wrapper; the interpreter sits directly in
``sys.exec_prefix`` and is named ``python.exe``). The shape-encoding helpers
are pure and take the platform plus the interpreter values they read as
arguments, so the Windows branches are exercised from a macOS test run.

``fusion_install`` has no relative imports of its own, but it lives in a
package, so it is loaded from its file path under a synthetic parent package —
the same trick ``test_changecyclecolor_colors.py`` uses to avoid importing the
``commands`` package and its heavy Fusion dependencies.
"""

import importlib.util
import os
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_CCC_DIR = Path(__file__).resolve().parent.parent / "commands" / "changecyclecolor"

_pkg = types.ModuleType("ccc_fi_pkg")
_pkg.__path__ = [str(_CCC_DIR)]
sys.modules["ccc_fi_pkg"] = _pkg

_spec = importlib.util.spec_from_file_location(
    "ccc_fi_pkg.fusion_install", _CCC_DIR / "fusion_install.py"
)
fusion_install = importlib.util.module_from_spec(_spec)
sys.modules["ccc_fi_pkg.fusion_install"] = fusion_install
_spec.loader.exec_module(fusion_install)


def _norm(path: str) -> str:
    """Compare paths without caring which separator the host uses.

    ``os.path.join`` on a POSIX host builds the Windows candidates with forward
    slashes, so the assertions normalize rather than hardcode a separator.
    """
    return path.replace("\\", "/")


# ── RiverRubicon.xml relative paths ───────────────────────────────────────────
def test_river_rubicon_rels_include_confirmed_macos_layout() -> None:
    """The macOS bundle layout is the confirmed path and must be present.

    Real path, relative to ``Autodesk Fusion.app``:
    ``Contents/Libraries/Neutron/Neutron/Server/Scene/Resources/Environments/
    RiverRubicon/RiverRubicon.xml`` — note the doubled "Neutron".
    """
    rels = [_norm(r) for r in fusion_install.RIVER_RUBICON_RELS]
    assert (
        "Contents/Libraries/Neutron/Neutron/Server/Scene/Resources/Environments/"
        "RiverRubicon/RiverRubicon.xml" in rels
    )


def test_river_rubicon_rels_include_unwrapped_layouts() -> None:
    """Windows has no ``.app`` wrapper, so shallower variants are also tried."""
    rels = [_norm(r) for r in fusion_install.RIVER_RUBICON_RELS]
    tail = "Neutron/Server/Scene/Resources/Environments/RiverRubicon/RiverRubicon.xml"
    assert f"Libraries/Neutron/{tail}" in rels
    assert tail in rels


def test_river_rubicon_rels_are_unique() -> None:
    """No prefix collapses into another — every candidate is a distinct stat."""
    rels = [_norm(r) for r in fusion_install.RIVER_RUBICON_RELS]
    assert len(rels) == len(set(rels))


# ── is_python_binary ─────────────────────────────────────────────────────────
def test_is_python_binary_accepts_posix_versioned_name() -> None:
    """Fusion's macOS interpreter is ``python3.14``, whose extension-looking
    ``.14`` suffix must not defeat the check."""
    assert fusion_install.is_python_binary(
        "/Applications/Autodesk Fusion.app/Contents/Frameworks/"
        "Python.framework/Versions/3.14/bin/python3.14"
    )


def test_is_python_binary_accepts_windows_names() -> None:
    """Both the console and GUI Windows interpreters are accepted."""
    assert fusion_install.is_python_binary(r"C:\webdeploy\hash\Python\python.exe")
    assert fusion_install.is_python_binary(r"C:\webdeploy\hash\Python\pythonw.exe")


def test_is_python_binary_rejects_the_fusion_host() -> None:
    """The bug this guard exists for: inside Fusion on Windows,
    ``sys.executable`` is the host app, and handing that to subprocess opens no
    picker while raising no error."""
    assert not fusion_install.is_python_binary(r"C:\webdeploy\hash\Fusion360.exe")
    assert not fusion_install.is_python_binary(
        "/Applications/Autodesk Fusion.app/Contents/MacOS/Autodesk Fusion"
    )


def test_is_python_binary_rejects_empty() -> None:
    """An unset ``sys.executable`` is not a candidate."""
    assert not fusion_install.is_python_binary("")


# ── _python_candidates ───────────────────────────────────────────────────────
def test_windows_candidates_live_in_the_prefix_root() -> None:
    """Windows keeps the interpreter in ``sys.exec_prefix`` itself, not ``bin``.

    The original code only ever built ``<prefix>/bin/python3.x`` paths, so on
    Windows every candidate missed.
    """
    got = [
        _norm(p)
        for p in fusion_install._python_candidates(
            "win32",
            r"C:\webdeploy\hash\Python",
            r"C:\webdeploy\hash\Fusion360.exe",
            (3, 14),
        )
    ]
    assert "C:/webdeploy/hash/Python/pythonw.exe" in got
    assert "C:/webdeploy/hash/Python/python.exe" in got
    # No POSIX-shaped candidate is offered on Windows.
    assert not any("/bin/" in p for p in got)


def test_windows_prefers_the_windowless_interpreter() -> None:
    """``pythonw.exe`` is tried before ``python.exe`` so no console window
    flashes up behind the picker dialog."""
    got = [
        _norm(p)
        for p in fusion_install._python_candidates("win32", r"C:\Python", "", (3, 14))
    ]
    assert got.index("C:/Python/pythonw.exe") < got.index("C:/Python/python.exe")


def test_windows_candidates_exclude_the_fusion_host_fallback() -> None:
    """The ``sys.executable`` fallback is filtered, so the Fusion host binary
    never becomes the "interpreter" the picker is launched with."""
    got = fusion_install._python_candidates(
        "win32", r"C:\Python", r"C:\webdeploy\hash\Fusion360.exe", (3, 14)
    )
    assert not any("Fusion360" in p for p in got)


def test_posix_candidates_keep_the_versioned_bin_layout() -> None:
    """macOS behavior is unchanged: ``<prefix>/bin/python3.14`` first, then the
    less specific names."""
    got = fusion_install._python_candidates(
        "darwin",
        "/Fusion.app/Contents/Frameworks/Python.framework/Versions/3.14",
        "",
        (3, 14),
    )
    base = "/Fusion.app/Contents/Frameworks/Python.framework/Versions/3.14/bin"
    assert got == [f"{base}/python3.14", f"{base}/python3", f"{base}/python"]


def test_posix_appends_a_real_interpreter_executable() -> None:
    """A ``sys.executable`` that genuinely is Python stays a last-resort
    candidate."""
    got = fusion_install._python_candidates("darwin", "", "/usr/bin/python3", (3, 14))
    assert got == ["/usr/bin/python3"]


def test_no_candidates_without_a_prefix_or_usable_executable() -> None:
    """Nothing to try means ``find_bundled_python`` reports failure rather than
    guessing."""
    assert fusion_install._python_candidates("win32", "", "", (3, 14)) == []


# ── Lighting environment → palette XML ───────────────────────────────────────
class _FakeLightingEnvironments:
    """Mirror of ``adsk.core.LightingEnvironments`` as Fusion ships it."""

    DarkSkyLightingEnvironment = 0
    GreyRoomLightingEnvironment = 1
    PhotoBoothLightingEnvironment = 2
    TranquilityBlueLightingEnvironment = 3
    InfinityPoolLightingEnvironment = 4
    RiverRubiconLightingEnvironment = 5


def test_lighting_environment_dirs_maps_every_member() -> None:
    """Each enum member yields the environment folder that holds its palette."""
    assert fusion_install.lighting_environment_dirs(_FakeLightingEnvironments) == {
        0: "DarkSky",
        1: "GreyRoom",
        2: "PhotoBooth",
        3: "TranquilityBlue",
        4: "InfinityPool",
        5: "RiverRubicon",
    }


def test_lighting_environment_dirs_survives_reordering() -> None:
    """The mapping is introspected, not hardcoded, so renumbering the enum does
    not silently point the palette at the wrong environment."""

    class Reordered:
        GreyRoomLightingEnvironment = 5
        RiverRubiconLightingEnvironment = 0

    got = fusion_install.lighting_environment_dirs(Reordered)
    assert got == {5: "GreyRoom", 0: "RiverRubicon"}


def test_lighting_environment_dirs_picks_up_new_members() -> None:
    """A Fusion update that adds an environment needs no code change here."""

    class Extended(_FakeLightingEnvironments):
        BrandNewStudioLightingEnvironment = 6

    assert fusion_install.lighting_environment_dirs(Extended)[6] == "BrandNewStudio"


def test_lighting_environment_dirs_ignores_unrelated_attributes() -> None:
    """Only ``<Folder>LightingEnvironment`` members count — not the bare suffix,
    not non-integer attributes, and not booleans (an int subclass)."""

    class Noisy:
        GreyRoomLightingEnvironment = 1
        LightingEnvironment = 99
        SomeOtherThing = 7
        DocstringLightingEnvironment = "not an int"
        FlagLightingEnvironment = True

    assert fusion_install.lighting_environment_dirs(Noisy) == {1: "GreyRoom"}


def test_is_safe_environment_name_rejects_path_traversal() -> None:
    """Names are joined into a path, so separators and traversal are refused."""
    assert fusion_install.is_safe_environment_name("GreyRoom")
    assert not fusion_install.is_safe_environment_name("../../etc")
    assert not fusion_install.is_safe_environment_name("Grey/Room")
    assert not fusion_install.is_safe_environment_name("")


def test_find_environment_xml_resolves_self_named_folder(tmp_path, monkeypatch) -> None:
    """An environment lives in a self-named folder: GreyRoom/GreyRoom.xml."""
    envs = tmp_path / "Environments"
    (envs / "GreyRoom").mkdir(parents=True)
    (envs / "GreyRoom" / "GreyRoom.xml").write_text("<Environment/>")
    (envs / "RiverRubicon").mkdir()
    river = envs / "RiverRubicon" / "RiverRubicon.xml"
    river.write_text("<Environment/>")

    monkeypatch.setattr(fusion_install, "find_river_rubicon_xml", lambda: str(river))

    assert fusion_install.find_environments_dir() == str(envs)
    assert fusion_install.find_environment_xml("GreyRoom") == str(
        envs / "GreyRoom" / "GreyRoom.xml"
    )


def test_find_environment_xml_returns_none_for_absent_environment(
    tmp_path, monkeypatch
) -> None:
    """A missing environment reports None so the caller can fall back rather
    than handing a non-existent path to the XML parser."""
    envs = tmp_path / "Environments"
    (envs / "RiverRubicon").mkdir(parents=True)
    river = envs / "RiverRubicon" / "RiverRubicon.xml"
    river.write_text("<Environment/>")

    monkeypatch.setattr(fusion_install, "find_river_rubicon_xml", lambda: str(river))

    assert fusion_install.find_environment_xml("Studio4") is None


def test_find_environments_dir_none_when_install_not_found(monkeypatch) -> None:
    """No anchor file means no environments directory, not a bogus path."""
    monkeypatch.setattr(fusion_install, "find_river_rubicon_xml", lambda: None)
    assert fusion_install.find_environments_dir() is None
    assert fusion_install.find_environment_xml("GreyRoom") is None


# ── Against a real install, when one is present ──────────────────────────────
def _installed_environments_dir():
    """The shipped ``Environments`` directory, or None when Fusion is absent.

    The resolution under test walks up from the ``adsk`` package inside the
    running Fusion process, which is not what a test runner is. So this locates
    an install independently, purely to check the enum-derived folder names
    against what Fusion actually ships. CI has no Fusion install, hence the
    skip rather than a hard requirement.
    """
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
                candidate = base / rel
                if (candidate / "RiverRubicon/RiverRubicon.xml").is_file():
                    return candidate
    return None


_ENV_DIR = _installed_environments_dir()
_needs_install = pytest.mark.skipif(
    _ENV_DIR is None, reason="no local Fusion install to check shipped names against"
)


@_needs_install
def test_every_enum_environment_ships_a_folder() -> None:
    """The enum-derived names must be real folder names — the whole mapping
    rests on ``<Member>LightingEnvironment`` matching ``Environments/<Member>``."""
    missing = [
        name
        for name in fusion_install.lighting_environment_dirs(
            _FakeLightingEnvironments
        ).values()
        if not (_ENV_DIR / name / f"{name}.xml").is_file()
    ]
    assert not missing, f"no shipped XML for: {missing}"


@_needs_install
def test_every_enum_environment_defines_a_color_cycle_table() -> None:
    """Each selectable environment carries its own palette, so switching
    environments always yields a usable table."""
    empty = []
    for name in fusion_install.lighting_environment_dirs(
        _FakeLightingEnvironments
    ).values():
        root = ET.parse(_ENV_DIR / name / f"{name}.xml").getroot()
        table = root.find("ColorCycleTable")
        if table is None or not table.findall("ColorCycle"):
            empty.append(name)
    assert not empty, f"no ColorCycleTable in: {empty}"


@_needs_install
def test_environments_do_not_share_one_palette() -> None:
    """The reason this command cannot read a fixed file: the shipped
    environments carry genuinely different tables, and RiverRubicon — the file
    the command used to hardcode — is the outlier rather than the norm."""

    def table(name):
        root = ET.parse(_ENV_DIR / name / f"{name}.xml").getroot()
        return [
            (e.get("name"), e.get("RGB"))
            for e in root.find("ColorCycleTable").findall("ColorCycle")
        ]

    grey, river = table("GreyRoom"), table("RiverRubicon")
    assert grey != river
    # Different palettes outright, not a reordering of the same colors.
    assert {c for _, c in grey} != {c for _, c in river}

    # DarkSky holds GreyRoom's colors in a different cycle order, so reading
    # the wrong one of those two changes the order rather than the palette.
    dark = table("DarkSky")
    assert dark != grey
    assert {c for _, c in dark} == {c for _, c in grey}


if __name__ == "__main__":
    for _name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[_name]()
        print(f"PASS {_name}")
    print("ALL TEST FUNCS PASSED")
