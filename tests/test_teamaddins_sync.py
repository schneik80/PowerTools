# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""End-to-end behaviour of the Team Add-ins check.

The hub is stood up as an ordinary local directory and the four ``team_fs``
entry points are pointed at it, so the tiering, the quiet rule, the per-hub
bookkeeping and the failure handling are all exercised for real — only the
Fusion Data API calls are substituted.
"""

import hashlib
import importlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from tests.conftest import PT_PKG

sync = importlib.import_module(f"{PT_PKG}.commands.teamaddins.sync")
installer = importlib.import_module(f"{PT_PKG}.commands.teamaddins.installer")
team_fs = importlib.import_module(f"{PT_PKG}.commands.teamaddins.team_fs")


class FakeDataFile:
    def __init__(self, name, source, version=1):
        self.name = name
        self.fileExtension = Path(name).suffix.lstrip(".")
        self.latestVersionNumber = version
        self._source = source


class FakeFolder:
    def __init__(self, path, name="Shared Addins"):
        self.path = Path(path)
        self.name = name
        self.parentProject = type("P", (), {"name": "Assets"})()


@pytest.fixture
def hub(tmp_path, monkeypatch):
    """A fake Shared Addins folder plus a wired-up sync module."""
    hub_dir = tmp_path / "hub"
    hub_dir.mkdir()
    addins_dir = tmp_path / "AddIns"
    cache = tmp_path / "cache"
    cache.mkdir()

    monkeypatch.setattr(sync, "INSTALLED_FILE", str(cache / "installed.json"))
    monkeypatch.setattr(installer.config, "CACHE_PATH", str(cache))
    monkeypatch.setattr(installer.config, "ADDIN_PATH", str(tmp_path / "PowerTools"))
    monkeypatch.setattr(installer.config, "fusion_addins_dir", lambda: str(addins_dir))
    monkeypatch.setattr(installer, "load_addin", lambda path, addin_id: True)
    monkeypatch.setattr(installer, "stop_addin", lambda path: True)

    box = {"hub_id": "hubA", "exists": True, "versions": {}, "downloads": []}

    def resolve_folder(app, create=False):
        if not box["exists"]:
            raise team_fs.NotConfigured("no Shared Addins folder yet")
        return FakeFolder(hub_dir)

    def list_folder(folder):
        return [
            (p.name, box["versions"].get(p.name, 1))
            for p in sorted(folder.path.iterdir())
        ]

    def find_file(folder, name):
        path = folder.path / name
        return FakeDataFile(name, path) if path.is_file() else None

    def download(data_file, local_path):
        box["downloads"].append(data_file.name)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(data_file._source, local_path)
        return local_path

    monkeypatch.setattr(sync.team_fs, "resolve_folder", resolve_folder)
    monkeypatch.setattr(sync.team_fs, "list_folder", list_folder)
    monkeypatch.setattr(sync.team_fs, "find_file", find_file)
    monkeypatch.setattr(sync.team_fs, "download", download)
    monkeypatch.setattr(sync.team_fs, "active_hub_id", lambda app: box["hub_id"])

    class Harness:
        def __init__(self):
            self.dir = hub_dir
            self.addins_dir = addins_dir

        def drop(
            self,
            addin_id,
            version="1.0.0",
            body="pass",
            corrupt=False,
            suffix=".ptaddin",
        ):
            """Put a package in the folder, bumping its hub revision."""
            pkg = hub_dir / f"{addin_id}{suffix}"
            if corrupt:
                pkg.write_bytes(b"not a zip at all")
            else:
                with zipfile.ZipFile(pkg, "w") as z:
                    z.writestr(
                        f"{addin_id}/{addin_id}.manifest",
                        json.dumps({"type": "addin", "version": version}),
                    )
                    z.writestr(f"{addin_id}/{addin_id}.py", f"# {body}\n")
            box["versions"][pkg.name] = box["versions"].get(pkg.name, 0) + 1
            return pkg

        def bump_only(self, filename):
            """Re-upload identical bytes: revision moves, content does not."""
            box["versions"][filename] = box["versions"].get(filename, 1) + 1

        def remove(self, filename):
            (hub_dir / filename).unlink()
            box["versions"].pop(filename, None)

        def set_hub(self, hub_id):
            box["hub_id"] = hub_id

        def set_exists(self, value):
            box["exists"] = value

        @property
        def downloads(self):
            return box["downloads"]

        def clear(self):
            box["downloads"].clear()

        def saved(self, hub_id="hubA"):
            data = json.loads(Path(sync.INSTALLED_FILE).read_text())
            return data["hubs"].get(hub_id, {})

        def sha_of(self, filename):
            return hashlib.sha256((hub_dir / filename).read_bytes()).hexdigest()

    return Harness()


def run(**kwargs):
    return sync.check_and_apply(**kwargs)


# ---------------------------------------------------------------------------
# Before setup
# ---------------------------------------------------------------------------


def test_missing_folder_is_silent_not_an_error(hub):
    hub.set_exists(False)
    report = run()
    assert report.status == sync.STATUS_NOT_CONFIGURED
    assert not report.is_news
    assert hub.downloads == []


def test_empty_folder_is_silent(hub):
    report = run()
    assert report.status == sync.STATUS_UP_TO_DATE
    assert not report.is_news


# ---------------------------------------------------------------------------
# Install and the quiet rule
# ---------------------------------------------------------------------------


def test_a_dropped_package_is_installed(hub):
    hub.drop("Alpha", "1.0.0")
    report = run()

    assert report.status == sync.STATUS_APPLIED
    assert report.is_news
    assert [(r.addin_id, r.action, r.state, r.version) for r in report.rows] == [
        ("Alpha", "install", "loaded", "1.0.0")
    ]
    assert (hub.addins_dir / "Alpha" / "Alpha.manifest").is_file()


def test_a_plain_zip_works_too(hub):
    hub.drop("Alpha", suffix=".zip")
    report = run()
    assert [r.addin_id for r in report.rows] == ["Alpha"]


def test_nothing_changed_costs_no_downloads_and_says_nothing(hub):
    hub.drop("Alpha")
    run()
    hub.clear()

    report = run()

    assert report.status == sync.STATUS_UP_TO_DATE
    assert not report.is_news
    # The whole point of the fingerprint tier.
    assert hub.downloads == []


def test_a_manual_check_always_looks_even_when_unchanged(hub):
    hub.drop("Alpha")
    run()
    hub.clear()

    report = run(trigger="manual", force=True)

    assert hub.downloads == []  # listing is not a download
    assert report.status == sync.STATUS_UP_TO_DATE
    assert report.rows == []


def test_non_package_files_are_ignored(hub):
    hub.drop("Alpha")
    (hub.dir / "readme.md").write_text("team notes")
    report = run()
    assert [r.addin_id for r in report.rows] == ["Alpha"]


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------


def test_only_the_changed_package_is_downloaded(hub):
    hub.drop("Stable")
    hub.drop("Moving", "1.0.0")
    run()
    hub.clear()

    hub.drop("Moving", "2.0.0", body="new")
    report = run()

    assert [r.addin_id for r in report.rows] == ["Moving"]
    assert hub.downloads == ["Moving.ptaddin"]


def test_an_update_reports_both_declared_versions_and_revisions(hub):
    hub.drop("Alpha", "1.0.0")
    run()
    hub.drop("Alpha", "2.0.0", body="new")

    row = run().rows[0]

    assert (row.action, row.from_version, row.version) == ("update", "1.0.0", "2.0.0")
    assert (row.from_revision, row.revision) == (1, 2)
    assert "new" in (hub.addins_dir / "Alpha" / "Alpha.py").read_text()


def test_an_update_is_detected_when_the_author_never_bumps_the_version(hub):
    # The common real-world case: the manifest version never moves.
    hub.drop("Alpha", "1.0.0")
    run()
    hub.drop("Alpha", "1.0.0", body="different code")

    row = run().rows[0]

    assert row.action == "update"
    assert row.from_version == row.version == "1.0.0"
    # The revision is what makes it legible as a change in the palette.
    assert (row.from_revision, row.revision) == (1, 2)
    assert "different code" in (hub.addins_dir / "Alpha" / "Alpha.py").read_text()


def test_an_addin_with_no_declared_version_still_installs(hub):
    pkg = hub.dir / "Bare.ptaddin"
    with zipfile.ZipFile(pkg, "w") as z:
        z.writestr("Bare/Bare.manifest", '{"type": "addin"}')
    report = run()
    assert [(r.addin_id, r.state, r.version) for r in report.rows] == [
        ("Bare", "loaded", "")
    ]


def test_a_re_upload_of_identical_bytes_installs_nothing(hub):
    hub.drop("Alpha")
    run()
    hub.clear()

    hub.bump_only("Alpha.ptaddin")
    report = run()

    # Downloaded to find out, then correctly left alone.
    assert hub.downloads == ["Alpha.ptaddin"]
    assert report.rows == []
    assert not report.is_news
    # The new revision is recorded, so the next launch short-circuits again.
    assert hub.saved()["addins"]["Alpha"]["hub_version"] == 2
    assert hub.saved()["fingerprint"] == {"Alpha.ptaddin": 2}


def test_reload_can_be_deferred_to_a_restart(hub):
    hub.drop("Alpha")
    report = run(allow_reload=False)
    assert report.restart_required
    assert [r.state for r in report.rows] == ["restart"]
    assert (hub.addins_dir / "Alpha" / "Alpha.manifest").is_file()


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_one_bad_package_does_not_block_the_others(hub):
    hub.drop("Good")
    hub.drop("Bad", corrupt=True)

    report = run()

    assert {r.addin_id: r.state for r in report.rows} == {
        "Good": "loaded",
        "Bad": "failed",
    }
    assert (hub.addins_dir / "Good").is_dir()
    assert not (hub.addins_dir / "Bad").exists()


def test_a_failure_leaves_the_fingerprint_so_the_next_launch_retries(hub):
    hub.drop("Bad", corrupt=True)
    run()
    assert hub.saved()["fingerprint"] == {}
    assert hub.saved()["failed"] == {"Bad.ptaddin": 1}


def test_the_first_failure_is_news_and_the_repeat_is_not(hub):
    hub.drop("Bad", corrupt=True)

    first = run()
    assert first.is_news and not first.repeat_failure

    second = run()
    assert second.is_news and second.repeat_failure  # automatic check goes quiet


def test_a_re_uploaded_broken_package_is_news_again(hub):
    hub.drop("Bad", corrupt=True)
    run()
    hub.drop("Bad", corrupt=True)  # bumps the revision
    assert not run().repeat_failure


def test_a_fixed_package_clears_the_failure_record(hub):
    hub.drop("Alpha", corrupt=True)
    run()
    hub.drop("Alpha", "1.0.0")

    report = run()

    assert [r.state for r in report.rows] == ["loaded"]
    assert hub.saved()["failed"] == {}


def test_an_unusable_filename_is_reported_without_blocking_others(hub):
    hub.drop("Good")
    (hub.dir / "bad name.ptaddin").write_bytes(b"x")

    report = run()

    assert [r.addin_id for r in report.rows] == ["Good"]
    assert len(report.errors) == 1
    assert "bad name.ptaddin" in report.errors[0]


def test_a_hub_error_is_reported_and_nothing_is_touched(hub, monkeypatch):
    def broken(app, create=False):
        raise team_fs.TeamFsError("hub is unreachable")

    monkeypatch.setattr(sync.team_fs, "resolve_folder", broken)
    report = run()

    assert report.status == sync.STATUS_ERROR
    assert report.is_news
    assert "unreachable" in report.detail


# ---------------------------------------------------------------------------
# Orphans — reported once, never uninstalled
# ---------------------------------------------------------------------------


def test_a_removed_package_is_reported_once_and_left_installed(hub):
    hub.drop("Keep")
    hub.drop("Drop")
    run()

    hub.remove("Drop.ptaddin")
    first = run()

    assert first.orphans == ["Drop"]
    assert first.is_news
    assert (hub.addins_dir / "Drop").is_dir()  # never uninstalled

    second = run()
    assert second.orphans == []
    assert not second.is_news  # does not nag every launch


def test_an_orphan_returning_to_the_folder_is_not_an_orphan(hub):
    hub.drop("Alpha")
    run()
    hub.remove("Alpha.ptaddin")
    run()

    hub.drop("Alpha", "1.0.0")
    report = run()

    assert report.orphans == []
    assert hub.saved()["reported_orphans"] == []


# ---------------------------------------------------------------------------
# Per-hub state
# ---------------------------------------------------------------------------


def test_each_hub_keeps_its_own_record(hub):
    hub.drop("Alpha")
    run()

    hub.set_hub("hubB")
    hub.drop("Beta")
    run()

    assert set(hub.saved("hubA")["addins"]) == {"Alpha"}
    assert set(hub.saved("hubB")["addins"]) == {"Alpha", "Beta"}


def test_switching_hubs_does_not_reuse_the_other_hubs_fingerprint(hub):
    hub.drop("Alpha")
    run()
    hub.clear()

    # Same folder contents, different hub: it must look rather than assume.
    hub.set_hub("hubB")
    report = run()

    assert hub.downloads == ["Alpha.ptaddin"]
    assert [r.addin_id for r in report.rows] == ["Alpha"]


def test_returning_to_the_first_hub_is_quiet_again(hub):
    hub.drop("Alpha")
    run()
    hub.set_hub("hubB")
    run()
    hub.set_hub("hubA")
    hub.clear()

    report = run()

    assert hub.downloads == []
    assert not report.is_news


# ---------------------------------------------------------------------------
# Reporting details
# ---------------------------------------------------------------------------


def test_report_records_where_it_looked(hub):
    hub.drop("Alpha")
    report = run()
    assert report.folder_name == "Shared Addins"
    assert report.project_name == "Assets"
    assert report.checked_at


def test_report_serialises_for_the_palette(hub):
    hub.drop("Alpha")
    payload = run().to_dict()
    assert payload["status"] == sync.STATUS_APPLIED
    assert payload["rows"][0]["addin_id"] == "Alpha"
    assert payload["rows"][0]["revision"] == 1
    assert set(payload) >= {"headline", "rows", "errors", "orphans", "restartRequired"}


def test_installed_summary_feeds_the_preferences_card(hub):
    hub.drop("Alpha")
    run()
    summary = sync.installed_summary("hubA")
    assert summary["installedCount"] == 1
    assert summary["checkedAt"]
