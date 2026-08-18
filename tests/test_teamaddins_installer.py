# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Everything that decides whether a package may touch the filesystem.

The Fusion session calls (load_addin / stop_addin) are stubbed: conftest
fabricates ``adsk`` as a MagicMock, so asserting on them proves nothing. What is
asserted here is the extraction guards, the ``<id>.manifest`` invariant, the
self-install guard, and the stop-before-swap ordering that the Add-in Market
original got wrong.
"""

import hashlib
import importlib
import os
import zipfile

import pytest

from tests.conftest import PT_PKG

installer = importlib.import_module(f"{PT_PKG}.commands.teamaddins.installer")
catalog = importlib.import_module(f"{PT_PKG}.commands.teamaddins.catalog")


def ref(addin_id="Widget", version=1, filename=None):
    return catalog.PackageRef(
        addin_id=addin_id,
        filename=filename or f"{addin_id}.ptaddin",
        hub_version=version,
    )


def write_package(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for arcname, text in members.items():
            archive.writestr(arcname, text)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def good_package(tmp_path, addin_id="Widget", version="1.0.0", top_folder=True,
                 body="pass"):
    """A package Fusion would actually load: <id>/<id>.manifest + code."""
    prefix = f"{addin_id}/" if top_folder else ""
    path = tmp_path / f"{addin_id}.ptaddin"
    sha = write_package(
        str(path),
        {
            f"{prefix}{addin_id}.manifest":
                '{"type": "addin", "version": "%s"}' % version,
            f"{prefix}{addin_id}.py": f"# {body}\n",
        },
    )
    return str(path), sha


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point the installer at a temporary AddIns directory and cache."""
    addins = tmp_path / "AddIns"
    monkeypatch.setattr(installer.config, "ADDIN_PATH", str(tmp_path / "PowerTools"))
    monkeypatch.setattr(installer.config, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(installer.config, "fusion_addins_dir", lambda: str(addins))
    monkeypatch.setattr(installer, "load_addin", lambda path, addin_id: True)
    monkeypatch.setattr(installer, "stop_addin", lambda path: True)
    return addins


# ---------------------------------------------------------------------------
# Content hashing — change confirmation, not authenticity
# ---------------------------------------------------------------------------


def test_sha256_of_matches_hashlib(tmp_path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"power tools")
    assert installer.sha256_of(str(target)) == hashlib.sha256(b"power tools").hexdigest()


def test_identical_bytes_are_not_a_change(tmp_path):
    package, sha = good_package(tmp_path)
    # A re-upload bumps the hub revision even when nothing inside changed;
    # this is what stops that from restarting a working add-in.
    assert not installer.content_changed(package, sha)


def test_different_bytes_are_a_change(tmp_path):
    package, _ = good_package(tmp_path)
    assert installer.content_changed(package, "f" * 64)


def test_no_known_hash_counts_as_changed(tmp_path):
    package, _ = good_package(tmp_path)
    assert installer.content_changed(package, "")


def test_hash_comparison_ignores_case(tmp_path):
    package, sha = good_package(tmp_path)
    assert not installer.content_changed(package, sha.upper())


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_safe_extract_writes_normal_members(tmp_path):
    package, _ = good_package(tmp_path)
    dest = tmp_path / "out"
    installer.safe_extract(package, str(dest))
    assert (dest / "Widget" / "Widget.manifest").is_file()


def test_safe_extract_rejects_a_zip_slip_member(tmp_path):
    package = tmp_path / "evil.ptaddin"
    write_package(str(package), {"../../escaped.txt": "pwned"})
    with pytest.raises(installer.InstallError) as excinfo:
        installer.safe_extract(str(package), str(tmp_path / "out"))
    assert "unsafe path" in str(excinfo.value)
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_safe_extract_rejects_a_non_zip(tmp_path):
    bogus = tmp_path / "not.ptaddin"
    bogus.write_bytes(b"this is not a zip")
    with pytest.raises(installer.InstallError) as excinfo:
        installer.safe_extract(str(bogus), str(tmp_path / "out"))
    assert "not a readable zip" in str(excinfo.value)


def test_locate_package_root_finds_the_single_top_level_folder(tmp_path):
    package, _ = good_package(tmp_path, top_folder=True)
    dest = tmp_path / "out"
    installer.safe_extract(package, str(dest))
    assert os.path.basename(installer.locate_package_root(str(dest), "Widget")) == "Widget"


def test_locate_package_root_handles_a_flat_archive(tmp_path):
    # An admin who zips the folder CONTENTS rather than the folder.
    package, _ = good_package(tmp_path, top_folder=False)
    dest = tmp_path / "out"
    installer.safe_extract(package, str(dest))
    root = installer.locate_package_root(str(dest), "Widget")
    assert root == str(dest)
    assert os.path.isfile(os.path.join(root, "Widget.manifest"))


def test_locate_package_root_ignores_macos_metadata(tmp_path):
    package = tmp_path / "Widget.ptaddin"
    write_package(
        str(package),
        {"Widget/Widget.manifest": "{}", "__MACOSX/._Widget": "junk"},
    )
    dest = tmp_path / "out"
    installer.safe_extract(str(package), str(dest))
    assert os.path.basename(installer.locate_package_root(str(dest), "Widget")) == "Widget"


# ---------------------------------------------------------------------------
# The <id>.manifest invariant
# ---------------------------------------------------------------------------


def test_matching_manifest_is_accepted(tmp_path):
    root = tmp_path / "Widget"
    root.mkdir()
    (root / "Widget.manifest").write_text("{}")
    installer.validate_package_root(str(root), "Widget")


def test_mismatched_manifest_names_both_sides(tmp_path):
    # Fusion matches an add-in folder to its manifest by name, so this would
    # otherwise install a folder Fusion silently ignores.
    root = tmp_path / "Widget"
    root.mkdir()
    (root / "SomethingElse.manifest").write_text("{}")
    with pytest.raises(installer.InstallError) as excinfo:
        installer.validate_package_root(str(root), "Widget")
    message = str(excinfo.value)
    assert "SomethingElse.manifest" in message and "Widget" in message


def test_package_with_no_manifest_is_rejected(tmp_path):
    root = tmp_path / "Widget"
    root.mkdir()
    (root / "readme.md").write_text("hi")
    with pytest.raises(installer.InstallError) as excinfo:
        installer.validate_package_root(str(root), "Widget")
    assert "cannot load" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Declared version — display only, and often absent
# ---------------------------------------------------------------------------


def test_manifest_version_is_read_when_present(tmp_path):
    root = tmp_path / "Widget"
    root.mkdir()
    (root / "Widget.manifest").write_text('{"type":"addin","version":"3.1.4"}')
    assert installer.read_manifest_version(str(root), "Widget") == "3.1.4"


def test_manifest_version_tolerates_a_bom(tmp_path):
    root = tmp_path / "Widget"
    root.mkdir()
    (root / "Widget.manifest").write_bytes(
        b"\xef\xbb\xbf" + b'{"type":"addin","version":"1.2.3"}'
    )
    assert installer.read_manifest_version(str(root), "Widget") == "1.2.3"


@pytest.mark.parametrize(
    "body", ['{"type":"addin"}', "not json at all", "[]", ""]
)
def test_missing_or_unreadable_version_is_empty_not_fatal(tmp_path, body):
    # Add-in authors frequently omit or never update this, so it can never be
    # load-bearing.
    root = tmp_path / "Widget"
    root.mkdir()
    (root / "Widget.manifest").write_text(body)
    assert installer.read_manifest_version(str(root), "Widget") == ""


def test_absent_manifest_file_yields_no_version(tmp_path):
    root = tmp_path / "Widget"
    root.mkdir()
    assert installer.read_manifest_version(str(root), "Widget") == ""


# ---------------------------------------------------------------------------
# Self-install guard
# ---------------------------------------------------------------------------


def test_is_self_detects_the_running_addin_folder(monkeypatch, tmp_path):
    running = tmp_path / "PowerTools"
    running.mkdir()
    monkeypatch.setattr(installer.config, "ADDIN_PATH", str(running))
    assert installer.is_self(str(running))
    assert installer.is_self(str(running).upper())  # Windows path casing
    assert not installer.is_self(str(tmp_path / "SomeOtherAddin"))


def test_is_self_detects_a_parent_of_the_running_addin(monkeypatch, tmp_path):
    running = tmp_path / "AddIns" / "PowerTools"
    running.mkdir(parents=True)
    monkeypatch.setattr(installer.config, "ADDIN_PATH", str(running))
    assert installer.is_self(str(tmp_path / "AddIns"))


def test_install_refuses_to_overwrite_powertools(monkeypatch, tmp_path, sandbox):
    monkeypatch.setattr(installer.config, "ADDIN_PATH", str(sandbox / "Widget"))
    package, _ = good_package(tmp_path)
    with pytest.raises(installer.InstallError) as excinfo:
        installer.install_package(ref(), package, "install", str(tmp_path / "work"))
    assert "Refusing to overwrite" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def test_install_places_the_folder_and_reports_the_declared_version(tmp_path, sandbox):
    package, sha = good_package(tmp_path, version="1.4.0")
    result = installer.install_package(ref(), package, "install", str(tmp_path / "work"))

    assert result.ok and result.started and not result.restart_required
    assert result.version == "1.4.0"
    assert result.sha256 == sha
    assert (sandbox / "Widget" / "Widget.manifest").is_file()


def test_install_reports_restart_when_reload_is_disabled(tmp_path, sandbox):
    package, _ = good_package(tmp_path)
    result = installer.install_package(
        ref(), package, "install", str(tmp_path / "work"), allow_reload=False
    )
    assert result.ok and not result.started and result.restart_required
    assert (sandbox / "Widget" / "Widget.manifest").is_file()


def test_install_stops_the_old_addin_before_replacing_it(monkeypatch, tmp_path, sandbox):
    old = sandbox / "Widget"
    old.mkdir(parents=True)
    (old / "stale.py").write_text("old code")

    stopped = []
    monkeypatch.setattr(
        installer, "stop_addin", lambda path: stopped.append(path) or True
    )

    package, _ = good_package(tmp_path, body="new code")
    result = installer.install_package(ref(), package, "update", str(tmp_path / "work"))

    assert result.ok
    # Stop BEFORE the swap: the Add-in Market original deleted files under a
    # live module and left the old code loaded.
    assert stopped == [str(old)]
    assert not (old / "stale.py").exists()
    assert "new code" in (old / "Widget.py").read_text()


def test_install_stages_pending_when_the_folder_is_locked(monkeypatch, tmp_path, sandbox):
    old = sandbox / "Widget"
    old.mkdir(parents=True)
    cache = tmp_path / "cache"

    # Simulate a Windows sharing violation on the live folder only.
    monkeypatch.setattr(
        installer, "remove_tree", lambda path: not str(path).endswith("Widget")
    )

    package, _ = good_package(tmp_path)
    result = installer.install_package(ref(), package, "update", str(tmp_path / "work"))

    assert result.ok and result.restart_required
    assert "next Fusion launch" in result.message
    assert (cache / "team-addins" / "pending" / "Widget" / "Widget.manifest").is_file()


def test_install_rejects_a_mismatched_inner_manifest(tmp_path, sandbox):
    package = tmp_path / "Widget.ptaddin"
    write_package(str(package), {"Widget/Wrong.manifest": "{}"})
    with pytest.raises(installer.InstallError):
        installer.install_package(
            ref(), str(package), "install", str(tmp_path / "work")
        )
    assert not (sandbox / "Widget").exists()


# ---------------------------------------------------------------------------
# Pending updates
# ---------------------------------------------------------------------------


def test_apply_pending_is_a_no_op_when_nothing_is_staged(tmp_path, sandbox):
    assert installer.apply_pending() == []


def test_apply_pending_installs_a_staged_package(monkeypatch, tmp_path, sandbox):
    staged = tmp_path / "cache" / "team-addins" / "pending" / "Widget"
    staged.mkdir(parents=True)
    (staged / "Widget.manifest").write_text("{}")

    results = installer.apply_pending()

    assert [(r.addin_id, r.ok, r.started) for r in results] == [("Widget", True, True)]
    assert (sandbox / "Widget" / "Widget.manifest").is_file()
    assert not staged.exists()


def test_apply_pending_refuses_to_overwrite_powertools(monkeypatch, tmp_path, sandbox):
    monkeypatch.setattr(installer.config, "ADDIN_PATH", str(sandbox / "Widget"))
    staged = tmp_path / "cache" / "team-addins" / "pending" / "Widget"
    staged.mkdir(parents=True)
    (staged / "Widget.manifest").write_text("{}")

    results = installer.apply_pending()

    assert results[0].ok is False
    assert "PowerTools add-in itself" in results[0].message
    assert not staged.exists()
