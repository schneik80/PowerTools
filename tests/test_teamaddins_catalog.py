# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Team Add-ins change detection: the folder listing is the catalogue.

``commands/teamaddins/catalog.py`` has no ``adsk`` import and does no I/O, so it
is loaded straight from its file path rather than through the add-in package.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "commands" / "teamaddins" / "catalog.py"
)
_spec = importlib.util.spec_from_file_location("teamaddins_catalog", MODULE_PATH)
catalog = importlib.util.module_from_spec(_spec)
# @dataclass resolves its own module out of sys.modules while the class body is
# processed, so the module has to be registered before exec_module.
sys.modules[_spec.name] = catalog
_spec.loader.exec_module(catalog)


def refs_of(*pairs):
    refs, _ = catalog.build_catalog(pairs)
    return refs


# ---------------------------------------------------------------------------
# Filename -> add-in id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Widget.ptaddin", "Widget"),
        ("Widget.zip", "Widget"),
        ("Widget.ZIP", "Widget"),  # hub casing is not ours to control
        ("PowerTools-PlusProject.ptaddin", "PowerTools-PlusProject"),
        ("some.dotted.name.zip", "some.dotted.name"),
    ],
)
def test_package_names_yield_their_id(filename, expected):
    assert catalog.split_package_name(filename) == expected


@pytest.mark.parametrize(
    "filename",
    ["readme.md", "notes.txt", "Widget", "Widget.exe", "archive.7z", "", None],
)
def test_non_packages_are_not_packages(filename):
    assert catalog.split_package_name(filename) is None


@pytest.mark.parametrize(
    "value",
    ["Widget", "PowerTools-PlusProject", "a", "a.b_c-d", "X" * 100],
)
def test_valid_ids(value):
    assert catalog.is_valid_addin_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "../escape",
        "a/b",
        "a\\b",
        ".hidden",
        "-lead",
        "has space",
        "X" * 101,
        None,
        123,
    ],
)
def test_invalid_ids(value):
    assert not catalog.is_valid_addin_id(value)


# ---------------------------------------------------------------------------
# build_catalog
# ---------------------------------------------------------------------------


def test_only_packages_are_catalogued():
    refs, errors = catalog.build_catalog(
        [("Widget.ptaddin", 1), ("readme.md", 4), ("logo.png", 2)]
    )
    assert [r.addin_id for r in refs] == ["Widget"]
    # A folder is allowed to hold other things; that is not an error.
    assert errors == []


def test_catalog_is_sorted_for_stable_reporting():
    refs = refs_of(("Zulu.zip", 1), ("alpha.zip", 1), ("Mike.zip", 1))
    assert [r.addin_id for r in refs] == ["alpha", "Mike", "Zulu"]


def test_unusable_filename_is_reported_and_skipped():
    refs, errors = catalog.build_catalog([("Good.zip", 1), ("bad name.zip", 1)])
    assert [r.addin_id for r in refs] == ["Good"]
    assert len(errors) == 1
    assert "bad name.zip" in errors[0]


def test_two_packages_claiming_one_id_is_reported():
    refs, errors = catalog.build_catalog([("Widget.zip", 1), ("Widget.ptaddin", 2)])
    assert len(refs) == 1
    assert "would both install as" in errors[0]


def test_unreadable_version_degrades_to_zero():
    refs = refs_of(("Widget.zip", None), ("Other.zip", "not-a-number"))
    assert [r.hub_version for r in refs] == [0, 0]


def test_empty_folder_is_an_empty_catalogue():
    refs, errors = catalog.build_catalog([])
    assert refs == []
    assert errors == []


# ---------------------------------------------------------------------------
# fingerprint — the cheap tier
# ---------------------------------------------------------------------------


def test_fingerprint_ignores_non_packages():
    fp = catalog.fingerprint([("Widget.zip", 3), ("readme.md", 9)])
    assert fp == {"Widget.zip": 3}


def test_fingerprint_is_stable_across_listing_order():
    a = catalog.fingerprint([("A.zip", 1), ("B.zip", 2)])
    b = catalog.fingerprint([("B.zip", 2), ("A.zip", 1)])
    assert a == b


@pytest.mark.parametrize(
    ("changed", "why"),
    [
        ([("A.zip", 2)], "version bumped"),
        ([("A.zip", 1), ("B.zip", 1)], "package added"),
        ([], "package removed"),
    ],
)
def test_fingerprint_detects_every_kind_of_change(changed, why):
    before = catalog.fingerprint([("A.zip", 1)])
    assert catalog.fingerprint(changed) != before, why


def test_fingerprint_unchanged_when_only_a_non_package_moves():
    before = catalog.fingerprint([("A.zip", 1), ("readme.md", 1)])
    after = catalog.fingerprint([("A.zip", 1), ("readme.md", 7)])
    assert after == before


# ---------------------------------------------------------------------------
# plan_changes
# ---------------------------------------------------------------------------


def test_new_package_is_an_install():
    plan = catalog.plan_changes(refs_of(("Widget.zip", 1)), {})
    assert [(c.ref.addin_id, c.action) for c in plan.changes] == [("Widget", "install")]
    assert plan.has_work


def test_same_revision_is_unchanged():
    installed = {"Widget": {"hub_version": 1, "sha256": "x"}}
    plan = catalog.plan_changes(refs_of(("Widget.zip", 1)), installed)
    assert plan.changes == []
    assert [r.addin_id for r in plan.unchanged] == ["Widget"]
    assert not plan.has_work


def test_bumped_revision_is_an_update_carrying_the_old_version():
    installed = {"Widget": {"hub_version": 1, "version": "1.0.0"}}
    plan = catalog.plan_changes(refs_of(("Widget.zip", 2)), installed)
    assert len(plan.changes) == 1
    change = plan.changes[0]
    assert change.action == "update"
    assert change.is_update
    assert change.previous_version == "1.0.0"


def test_update_is_detected_even_when_the_addin_never_bumps_its_version():
    # Plenty of add-in authors never touch the version in their manifest. The
    # hub revision is what decides, so this still comes through as an update.
    installed = {"Widget": {"hub_version": 3, "version": "1.0.0"}}
    plan = catalog.plan_changes(refs_of(("Widget.zip", 4)), installed)
    assert [c.action for c in plan.changes] == ["update"]
    assert plan.changes[0].previous_version == "1.0.0"


def test_missing_recorded_revision_forces_a_re_download():
    installed = {"Widget": {"version": "1.0.0"}}
    plan = catalog.plan_changes(refs_of(("Widget.zip", 1)), installed)
    assert [c.action for c in plan.changes] == ["update"]


def test_corrupt_installed_record_forces_a_reinstall():
    plan = catalog.plan_changes(refs_of(("Widget.zip", 1)), {"Widget": "corrupt"})
    assert [c.action for c in plan.changes] == ["install"]


def test_installed_not_a_dict_is_tolerated():
    plan = catalog.plan_changes(refs_of(("Widget.zip", 1)), None)
    assert [c.action for c in plan.changes] == ["install"]


def test_removed_package_is_an_orphan_never_a_removal():
    installed = {
        "Widget": {"hub_version": 1},
        "Retired": {"hub_version": 1},
    }
    plan = catalog.plan_changes(refs_of(("Widget.zip", 1)), installed)
    assert plan.orphans == ["Retired"]
    # Nothing is ever planned that would uninstall it.
    assert plan.changes == []


def test_orphans_are_sorted():
    installed = {
        "c": {"hub_version": 1},
        "a": {"hub_version": 1},
        "b": {"hub_version": 1},
    }
    plan = catalog.plan_changes([], installed)
    assert plan.orphans == ["a", "b", "c"]
