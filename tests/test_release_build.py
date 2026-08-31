"""Unit tests for ``tools/release/build_release.py``.

The script has no ``adsk`` dependency, so it is loaded directly from its file
path (same pattern as ``test_json_utils.py``). Tests cover the ship/strip
decision for representative paths, the forbidden-file guard, version parsing,
and the zip layout — git itself is never invoked (``tracked_files`` is
exercised with a mocked ``subprocess.run``).
"""

import importlib.util
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "tools" / "release" / "build_release.py"
)
_spec = importlib.util.spec_from_file_location("pt_build_release", _SCRIPT_PATH)
build_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_release)


@pytest.mark.parametrize(
    "path",
    [
        "tests/conftest.py",
        "tests/test_json_utils.py",
        "tools/pandoc/build_readme_pdf.py",
        "tools/release/build_release.py",
        ".github/workflows/ci.yml",
        ".gitignore",
        ".git-blame-ignore-revs",
        "pyproject.toml",
        "hub.json",
        "docs/arch/architecture.md",
        "docs/dev/index.md",
        "commands/assignpartnumbers/resources/generate_icons.py",
        "commands/assemblystats/resources/assystats.idraw",
        "commands/docinfo/resources/docinfo.idraw",
        "commands/getandupdate/resources/force rebuild 2.pxd/QuickLook/Thumbnail.webp",
        "commands/linkGlobalParameters/resources/fusion_icon_resources.zip",
        "commands/linkGlobalParameters/resources/fusion_icon_resources/GlobalParameters/resources/16x16.png",
    ],
)
def test_dev_only_paths_are_excluded(path: str) -> None:
    """Dev tooling, CI, architecture docs, and design sources do not ship."""
    assert build_release.is_excluded(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "PowerTools.py",
        "PowerTools.manifest",
        "config.py",
        "command_registry.py",
        "settings_store.py",
        "LICENSE",
        "README.md",
        "README.pdf",
        "docs/assemblystats.md",
        "docs/assets/example.png",
        "commands/__init__.py",
        "commands/timelinecompute/resources/frame-001.svg",
        "commands/relateddata/Sample data.json",
        "lib/ptAddInUtils/intent_icons.py",
        "lib/ptAddInUtils/assets/intent_icons/joint.svg",
    ],
)
def test_runtime_paths_ship(path: str) -> None:
    """Everything the add-in needs at runtime (plus user docs) ships."""
    assert build_release.is_excluded(path) is False


def test_release_files_filters_and_sorts() -> None:
    """Filtering drops dev paths and returns a sorted list."""
    tracked = [
        "config.py",
        "tests/conftest.py",
        "PowerTools.py",
        "hub.json",
    ]

    assert build_release.release_files(tracked) == ["PowerTools.py", "config.py"]


@pytest.mark.parametrize("forbidden", [".debug", ".env", "settings/preferences.json"])
def test_release_files_refuses_forbidden_tracked_files(forbidden: str) -> None:
    """A tracked machine-local file aborts the build instead of shipping."""
    tracked = ["PowerTools.py", forbidden]

    with pytest.raises(RuntimeError, match="forbidden"):
        build_release.release_files(tracked)


def test_tracked_files_parses_nul_separated_output() -> None:
    """``git ls-files -z`` output is split on NUL with no empty entries."""
    fake = MagicMock()
    fake.stdout = b"PowerTools.py\0commands/relateddata/Sample data.json\0"

    with patch.object(build_release.subprocess, "run", return_value=fake) as run:
        paths = build_release.tracked_files(Path("unused"))

    assert paths == ["PowerTools.py", "commands/relateddata/Sample data.json"]
    assert run.call_args.args[0] == ["git", "ls-files", "-z"]


def test_manifest_version_reads_manifest(tmp_path: Path) -> None:
    """The version comes from PowerTools.manifest's ``version`` field."""
    manifest = tmp_path / "PowerTools.manifest"
    manifest.write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")

    assert build_release.manifest_version(tmp_path) == "1.2.3"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.0", "1.2.0"),
        ("V2.0", "2.0"),
        ("1.2.0", "1.2.0"),
        ("vNext", "vNext"),
    ],
)
def test_normalize_version_strips_tag_prefix(tag: str, expected: str) -> None:
    """A leading ``v``/``V`` before a digit is dropped; other labels pass through."""
    assert build_release.normalize_version(tag) == expected


def test_release_manifest_stamps_version_and_locks_editing() -> None:
    """The shipped manifest carries the release version and editEnabled=false."""
    source = json.dumps(
        {
            "autodeskProduct": "Fusion",
            "type": "addin",
            "version": "0.1.0",
            "runOnStartup": True,
            "editEnabled": True,
        }
    )

    stamped = json.loads(build_release.release_manifest(source, "2.5.0"))

    assert stamped["version"] == "2.5.0"
    assert stamped["editEnabled"] is False
    assert stamped["autodeskProduct"] == "Fusion"
    assert stamped["runOnStartup"] is True


def test_build_zip_prefixes_entries_with_addin_folder(tmp_path: Path) -> None:
    """Zip entries live under ``PowerTools/`` so extraction names the folder."""
    repo = tmp_path / "repo"
    (repo / "commands").mkdir(parents=True)
    (repo / "PowerTools.py").write_text("# entry\n", encoding="utf-8")
    (repo / "commands" / "__init__.py").write_text("", encoding="utf-8")
    out_path = tmp_path / "dist" / "PowerTools-9.9.9.zip"

    build_release.build_zip(
        repo, out_path, ["PowerTools.py", "commands/__init__.py"], "9.9.9"
    )

    with zipfile.ZipFile(out_path) as archive:
        assert sorted(archive.namelist()) == [
            "PowerTools/PowerTools.py",
            "PowerTools/commands/__init__.py",
        ]


def test_build_zip_ships_stamped_manifest(tmp_path: Path) -> None:
    """The zipped manifest is version-stamped and locked; the repo copy is not."""
    repo = tmp_path / "repo"
    repo.mkdir()
    source = json.dumps({"version": "0.1.0", "editEnabled": True})
    (repo / "PowerTools.manifest").write_text(source, encoding="utf-8")
    out_path = tmp_path / "dist" / "PowerTools-3.0.0.zip"

    build_release.build_zip(repo, out_path, ["PowerTools.manifest"], "3.0.0")

    with zipfile.ZipFile(out_path) as archive:
        shipped = json.loads(archive.read("PowerTools/PowerTools.manifest"))
    assert shipped == {"version": "3.0.0", "editEnabled": False}
    assert (repo / "PowerTools.manifest").read_text(encoding="utf-8") == source


def test_refresh_readme_pdf_invokes_the_builder_in_if_stale_mode() -> None:
    """The release build asks the PDF script to rebuild only when needed."""
    done = MagicMock(returncode=0, stdout="  current: README.pdf matches\n", stderr="")

    with patch.object(build_release.subprocess, "run", return_value=done) as run:
        build_release.refresh_readme_pdf(Path("/repo"))

    command = run.call_args.args[0]
    assert command[1:] == [str(build_release.PDF_BUILDER), "--if-stale"]
    assert run.call_args.kwargs["cwd"] == Path("/repo")


def test_refresh_readme_pdf_aborts_when_the_pdf_cannot_be_rebuilt() -> None:
    """A stale PDF with no toolchain stops the release instead of shipping."""
    failed = MagicMock(
        returncode=1, stdout="", stderr="FAILED: pandoc not found on PATH"
    )

    with patch.object(build_release.subprocess, "run", return_value=failed):
        with pytest.raises(RuntimeError, match="README.pdf is out of date"):
            build_release.refresh_readme_pdf(Path("/repo"))


def test_pdf_builder_path_points_at_the_pandoc_script() -> None:
    """The release build resolves its sibling script, which must exist."""
    assert build_release.PDF_BUILDER.is_file()
    assert build_release.PDF_BUILDER.name == "build_readme_pdf.py"
