"""Unit tests for the Document Refresh pure-logic helpers.

Exercises the version check the command now turns on — reading the open and
latest version numbers off DataFile stand-ins, deciding whether a reload would
bring anything new, and the wording of the three messages that report it. These
helpers have no Fusion dependency and are duck-typed on the ``DataFile`` shape,
so they run against the stand-ins below; the module uses package-relative
imports, so it is loaded via its full package path with the conftest scaffolding
in place.
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
logic = importlib.import_module(f"{PT_PKG}.commands.refresh.logic")


class FakeDataFile:
    """Stand-in for adsk.core.DataFile.

    ``latest`` is left off entirely (rather than set to None) when not given, so
    the "no latestVersionNumber at all" build is covered too.
    """

    def __init__(self, name="Widget", version=None, latest=None):
        self.name = name
        if version is not None:
            self.versionNumber = version
        if latest is not None:
            self.latestVersionNumber = latest


class RaisingDataFile:
    """DataFile whose every attribute raises, to exercise the guard paths."""

    @property
    def name(self):
        raise RuntimeError("name unavailable")

    @property
    def versionNumber(self):
        raise RuntimeError("versionNumber unavailable")

    @property
    def latestVersionNumber(self):
        raise RuntimeError("latestVersionNumber unavailable")


# ── open_version ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "data_file, expected",
    [
        (FakeDataFile(version=4), 4),  # plain read
        (FakeDataFile(version="7"), 7),  # numeric string coerces
        (FakeDataFile(version=0), None),  # 0 means "not populated yet"
        (FakeDataFile(version=-1), None),  # nonsense reads as unknown
        (FakeDataFile(), None),  # attribute absent
        (FakeDataFile(version="latest"), None),  # non-numeric
        (RaisingDataFile(), None),  # unreadable handle
    ],
)
def test_open_version(data_file, expected) -> None:
    assert logic.open_version(data_file) is expected


# ── latest_version ────────────────────────────────────────────────────────────


def test_latest_version_prefers_the_highest_number_reported() -> None:
    """The freshly looked-up file wins when the document's copy is stale."""
    hub = FakeDataFile(version=6, latest=6)
    open_copy = FakeDataFile(version=3, latest=3)
    assert logic.latest_version(hub, open_copy) == 6


def test_latest_version_catches_a_stale_lookup() -> None:
    """A stale lookup cannot hide a new version the document's copy knows about."""
    stale_hub = FakeDataFile(version=3, latest=3)
    open_copy = FakeDataFile(version=3, latest=5)
    assert logic.latest_version(stale_hub, open_copy) == 5


def test_latest_version_falls_back_to_version_number() -> None:
    """Without latestVersionNumber, the version a file is at is still a floor."""
    assert logic.latest_version(FakeDataFile(version=4)) == 4


def test_latest_version_unknown_when_nothing_is_readable() -> None:
    assert logic.latest_version(RaisingDataFile(), FakeDataFile()) is None


def test_latest_version_with_no_files() -> None:
    assert logic.latest_version() is None


# ── newer_version_available ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "current, latest, expected",
    [
        (3, 4, True),  # the case the command exists for
        (3, 9, True),  # several versions behind
        (4, 4, False),  # already latest
        (5, 4, False),  # open ahead of the Hub (never seen; do not reload)
        (None, 4, True),  # unknown open version -> reload as before
        (3, None, True),  # unknown Hub version -> reload as before
        (None, None, True),  # nothing readable -> reload as before
    ],
)
def test_newer_version_available(current, latest, expected) -> None:
    assert logic.newer_version_available(current, latest) is expected


# ── message wording ───────────────────────────────────────────────────────────


def test_display_name_falls_back_when_unreadable() -> None:
    assert logic.display_name(FakeDataFile(name="Chassis")) == "Chassis"
    assert logic.display_name(FakeDataFile(name="")) == "This document"
    assert logic.display_name(RaisingDataFile()) == "This document"


def test_up_to_date_message_names_the_version_checked() -> None:
    message = logic.up_to_date_message("Chassis", 4)
    assert "Chassis" in message
    assert "version 4" in message
    assert "no newer version" in message.lower()


def test_up_to_date_message_without_a_version() -> None:
    message = logic.up_to_date_message("Chassis", None)
    assert message.startswith("Chassis is already at the latest Team Hub version.")
    assert "None" not in message


def test_discard_to_reload_prompt_says_what_is_lost() -> None:
    message = logic.discard_to_reload_prompt("Chassis", 4)
    assert "version 4" in message
    assert "discard" in message.lower()
    assert message.endswith("Continue?")


def test_discard_for_newer_prompt_reports_both_versions() -> None:
    message = logic.discard_for_newer_prompt("Chassis", 3, 5)
    assert "version 5 of Chassis" in message
    assert "open at version 3" in message
    assert "discarded" in message
    assert message.endswith("Continue?")


@pytest.mark.parametrize("current, latest", [(None, 5), (3, None), (None, None)])
def test_discard_for_newer_prompt_without_version_numbers(current, latest) -> None:
    """No version to quote, so the prompt stays vague instead of printing None."""
    message = logic.discard_for_newer_prompt("Chassis", current, latest)
    assert "None" not in message
    assert "may be available" in message
    assert message.endswith("Continue?")


def test_refresh_log_message() -> None:
    assert logic.refresh_log_message("Chassis", 3, 5) == (
        "Chassis: open at version 3, Team Hub latest is 5"
    )
    assert logic.refresh_log_message("Chassis", None, None) == (
        "Chassis: open at version unknown, Team Hub latest is unknown"
    )
