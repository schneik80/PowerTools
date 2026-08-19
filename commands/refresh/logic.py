# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Pure, Fusion-free helpers for the Document Refresh command.

Kept separate from ``entry.py`` so the version comparison that decides whether a
close-and-reopen is worth doing — and the wording that reports it — can be
unit-tested without a live Fusion runtime (see ``tests/test_refresh_logic.py``).

Nothing here imports ``adsk``. The helpers are duck-typed on ``DataFile``
(``name`` / ``versionNumber`` / ``latestVersionNumber``), the same approach
``closealldocuments.logic`` uses so tests can drive them with stand-ins.

Every attribute read is guarded and unreadable version numbers read as ``None``
("unknown"). An unknown version deliberately resolves to "reload" in
``newer_version_available``: the command's job is to pull the latest version, so
a version number Fusion will not report falls back to the unconditional
close-and-reopen this command did before the check existed, rather than silently
doing nothing.
"""

from __future__ import annotations


def _version_number(data_file, attr: str) -> int | None:
    """Read one integer version attribute, or ``None`` when unavailable.

    Zero and negatives are treated as unknown: Fusion reports 0 for a DataFile
    whose version information has not been populated yet, and a zero would
    otherwise compare as a real version and make an up-to-date document look
    stale (or vice versa).
    """
    try:
        value = getattr(data_file, attr)
    except Exception:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def display_name(data_file) -> str:
    """File name for message text, tolerating an unreadable handle."""
    try:
        name = data_file.name
    except Exception:
        name = None
    return name or "This document"


def open_version(data_file) -> int | None:
    """Version number the document is currently open at, or ``None``."""
    return _version_number(data_file, "versionNumber")


def latest_version(*data_files) -> int | None:
    """Highest version Team Hub reports across *data_files*, or ``None``.

    Two DataFiles describe the same file at refresh time: the one the open
    document carries (populated when it was opened, so it can be stale) and the
    one ``app.data.findFileById`` just looked up. Taking the highest version
    either reports means a single stale read cannot hide a new version — only
    both being stale can, which then falls back to "already latest" and leaves
    the user exactly where they were.

    ``versionNumber`` is included in the comparison because a DataFile that
    reports no ``latestVersionNumber`` still pins a floor: the version it is
    itself at cannot be newer than the newest one on the Hub.
    """
    versions = []
    for data_file in data_files:
        for attr in ("latestVersionNumber", "versionNumber"):
            number = _version_number(data_file, attr)
            if number is not None:
                versions.append(number)
    return max(versions) if versions else None


def newer_version_available(current: int | None, latest: int | None) -> bool:
    """Whether reopening the document would bring in anything new.

    A version that could not be read answers ``True`` so the refresh still
    happens; see the module docstring.
    """
    if current is None or latest is None:
        return True
    return latest > current


def up_to_date_message(name: str, version: int | None) -> str:
    """Report that there is nothing to load, naming the version checked."""
    return (
        f"{name} is already at the latest Team Hub version"
        f"{_version_suffix(version)}.\n\nThere is no newer version to load."
    )


def discard_to_reload_prompt(name: str, version: int | None) -> str:
    """Ask whether to reload an up-to-date document that has unsaved edits.

    Nothing new would come down from the Hub, so the only effect is discarding
    the local changes. That is worth doing on request — it is how the command
    was used to revert a document before the version check existed — but never
    without asking.
    """
    return (
        f"{name} is already at the latest Team Hub version"
        f"{_version_suffix(version)}, but it has unsaved changes.\n\n"
        "Reloading it from Team Hub will discard those changes.\n\nContinue?"
    )


def discard_for_newer_prompt(name: str, current: int | None, latest: int | None) -> str:
    """Ask whether to discard unsaved edits to load a newer Hub version."""
    if current is None or latest is None:
        detail = f"A newer version of {name} may be available on Team Hub."
    else:
        detail = (
            f"Team Hub has version {latest} of {name}; "
            f"this document is open at version {current}."
        )
    return (
        f"{detail}\n\nThe unsaved changes in this document will be discarded "
        "when the newer version is loaded.\n\nContinue?"
    )


def refresh_log_message(name: str, current: int | None, latest: int | None) -> str:
    """One-line record of what the version check saw, for the debug log."""
    return (
        f"{name}: open at version {_number_or_unknown(current)}, "
        f"Team Hub latest is {_number_or_unknown(latest)}"
    )


def _version_suffix(version: int | None) -> str:
    """`` (version 4)`` for a known version, empty when it is unknown."""
    return f" (version {version})" if version is not None else ""


def _number_or_unknown(version: int | None) -> str:
    return str(version) if version is not None else "unknown"
