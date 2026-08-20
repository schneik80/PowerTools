# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Hub navigation for Team Add-ins.

The location is a convention — <active hub>/Assets/Shared Addins — so the things
worth asserting are: it finds an existing folder instead of making a second one,
it only creates when asked, and it reports a missing folder as "not set up yet"
rather than as an error.
"""

import importlib

import pytest

from tests.conftest import PT_PKG

team_fs = importlib.import_module(f"{PT_PKG}.commands.teamaddins.team_fs")


class FakeFolders:
    def __init__(self, names):
        self.names = list(names)
        self.added = []

    @property
    def count(self):
        return len(self.names)

    def item(self, i):
        return FakeFolder(self.names[i])

    def add(self, name):
        self.added.append(name)
        self.names.append(name)
        return FakeFolder(name)


class FakeFolder:
    def __init__(self, name, files=()):
        self.name = name
        self._files = list(files)

    @property
    def dataFiles(self):
        return FakeFiles(self._files)


class FakeFiles:
    def __init__(self, files):
        self._files = files

    @property
    def count(self):
        return len(self._files)

    def item(self, i):
        return self._files[i]


class FakeDataFile:
    def __init__(self, name, extension="", version=1):
        self.name = name
        self.fileExtension = extension
        self.latestVersionNumber = version


class FakeProject:
    def __init__(self, folder_names=(), name="Assets"):
        self.name = name
        self.folders = FakeFolders(folder_names)
        self.rootFolder = type("Root", (), {"dataFolders": self.folders})()


class FakeProjects:
    def __init__(self, projects):
        self._projects = projects

    @property
    def count(self):
        return len(self._projects)

    def item(self, i):
        return self._projects[i]


def fake_app(projects=None, hub_name="Acme", hub_id="hub1", no_hub=False):
    hub = None
    if not no_hub:
        hub = type(
            "Hub",
            (),
            {
                "id": hub_id,
                "name": hub_name,
                "dataProjects": FakeProjects(projects if projects is not None else []),
            },
        )()
    return type("App", (), {"data": type("D", (), {"activeHub": hub})()})()


# ---------------------------------------------------------------------------
# Folder name matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Shared Addins",
        "Shared AddIns",
        "shared addins",
        "Shared add-ins",
        "SharedAddins",
        "Shared  Addins",
        "shared_addins",
    ],
)
def test_existing_folder_is_adopted_however_it_is_spelled(name):
    # Teams name this folder by hand. An exact-only match would quietly create
    # a second folder in a live shared project.
    project = FakeProject([name])
    found = team_fs.find_shared_addins_folder(project, create=True)
    assert found.name == name
    assert project.folders.added == []


def test_an_exact_match_wins_over_a_loose_one():
    project = FakeProject(["shared addins", "Shared Addins"])
    found = team_fs.find_shared_addins_folder(project, create=False)
    assert found.name == "Shared Addins"


@pytest.mark.parametrize("name", ["Shared Data", "Addins Archive", "Templates"])
def test_unrelated_folders_do_not_match(name):
    project = FakeProject([name])
    assert team_fs.find_shared_addins_folder(project, create=False) is None


# ---------------------------------------------------------------------------
# Find vs create
# ---------------------------------------------------------------------------


def test_missing_folder_returns_none_without_create():
    project = FakeProject(["Pn-Cache"])
    assert team_fs.find_shared_addins_folder(project, create=False) is None
    # The launch check must never create cloud folders uninvited.
    assert project.folders.added == []


def test_create_makes_the_folder_once_asked():
    project = FakeProject(["Pn-Cache"])
    created = team_fs.find_shared_addins_folder(project, create=True)
    assert created.name == team_fs.SHARED_ADDINS_FOLDER_NAME
    assert project.folders.added == [team_fs.SHARED_ADDINS_FOLDER_NAME]


def test_create_failure_is_surfaced():
    project = FakeProject([])
    project.folders.add = lambda name: None
    with pytest.raises(team_fs.TeamFsError) as excinfo:
        team_fs.find_shared_addins_folder(project, create=True)
    assert "permissions" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Project resolution
# ---------------------------------------------------------------------------


def test_assets_project_is_found_by_name():
    app = fake_app([FakeProject(name="Other"), FakeProject(name="Assets")])
    assert team_fs.find_assets_project(app).name == "Assets"


def test_no_hub_is_not_configured_not_an_error():
    # NotConfigured is what keeps the launch check silent before setup.
    with pytest.raises(team_fs.NotConfigured):
        team_fs.find_assets_project(fake_app(no_hub=True))


def test_missing_assets_project_explains_it_needs_an_admin():
    app = fake_app([FakeProject(name="Other")])
    with pytest.raises(team_fs.TeamFsError) as excinfo:
        team_fs.find_assets_project(app)
    message = str(excinfo.value)
    assert "Assets" in message
    assert "admin" in message


def test_resolve_folder_reports_a_missing_folder_as_not_configured():
    app = fake_app([FakeProject(["Pn-Cache"], name="Assets")])
    with pytest.raises(team_fs.NotConfigured):
        team_fs.resolve_folder(app)


def test_resolve_folder_returns_the_folder_when_it_exists():
    app = fake_app([FakeProject(["Shared Addins"], name="Assets")])
    assert team_fs.resolve_folder(app).name == "Shared Addins"


def test_active_hub_id_is_empty_when_signed_out():
    assert team_fs.active_hub_id(fake_app(no_hub=True)) == ""


# ---------------------------------------------------------------------------
# Reading the folder
# ---------------------------------------------------------------------------


def test_file_name_keeps_an_extension_it_already_has():
    assert team_fs.file_name_of(FakeDataFile("Widget.zip", "zip")) == "Widget.zip"


def test_file_name_reattaches_a_stripped_extension():
    # Some Fusion builds report DataFile.name without the extension, and the
    # extension is what marks a file as a package.
    assert team_fs.file_name_of(FakeDataFile("Widget", "ptaddin")) == "Widget.ptaddin"


def test_file_name_tolerates_a_dotted_extension():
    assert team_fs.file_name_of(FakeDataFile("Widget", ".zip")) == "Widget.zip"


def test_file_name_with_no_extension_at_all():
    assert team_fs.file_name_of(FakeDataFile("readme", "")) == "readme"


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        ({"latestVersionNumber": 4}, 4),
        ({"latestVersionNumber": "7"}, 7),
        ({"versionNumber": 2}, 2),
        ({}, 0),
        ({"latestVersionNumber": None}, 0),
    ],
)
def test_latest_version_reads_defensively(attrs, expected):
    data_file = type("DF", (), attrs)()
    assert team_fs.latest_version_of(data_file) == expected


def test_list_folder_pairs_names_with_versions():
    folder = FakeFolder(
        "Shared Addins",
        [FakeDataFile("Widget", "zip", 3), FakeDataFile("readme.md", "md", 1)],
    )
    assert team_fs.list_folder(folder) == [("Widget.zip", 3), ("readme.md", 1)]


def test_find_file_matches_the_resolved_name():
    folder = FakeFolder("Shared Addins", [FakeDataFile("Widget", "zip", 1)])
    assert team_fs.find_file(folder, "Widget.zip") is not None
    assert team_fs.find_file(folder, "Missing.zip") is None


# ---------------------------------------------------------------------------
# folder_status — what the Preferences card renders
# ---------------------------------------------------------------------------


def test_status_ready_counts_only_packages():
    folder = FakeFolder(
        "Shared Addins",
        [
            FakeDataFile("Widget", "zip", 1),
            FakeDataFile("Other", "ptaddin", 1),
            FakeDataFile("readme.md", "md", 1),
        ],
    )
    project = FakeProject(name="Assets")
    project.folders.item = lambda i: folder
    project.folders.names = ["Shared Addins"]

    status = team_fs.folder_status(fake_app([project]))
    assert status["state"] == "ready"
    assert status["packageCount"] == 2
    assert status["hubName"] == "Acme"
    assert status["projectName"] == "Assets"


def test_status_missing_offers_to_create():
    status = team_fs.folder_status(fake_app([FakeProject(["Pn-Cache"], name="Assets")]))
    assert status["state"] == "missing"
    assert "Assets" in status["message"]


def test_status_no_hub_when_signed_out():
    status = team_fs.folder_status(fake_app(no_hub=True))
    assert status["state"] == "no_hub"


def test_status_error_when_there_is_no_assets_project():
    status = team_fs.folder_status(fake_app([FakeProject(name="Other")]))
    assert status["state"] == "error"
    assert "Assets" in status["message"]


def test_folder_status_never_raises():
    broken = type("App", (), {})()  # no .data at all
    assert team_fs.folder_status(broken)["state"] in {"no_hub", "error"}
