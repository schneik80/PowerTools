# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# What is published in the team folder, and what has changed since last time.
#
# There is no index file and no publish step: the folder listing IS the
# catalogue. An admin drops MyAddin.ptaddin in the folder and that is the whole
# workflow. Fusion versions every file on upload, so a re-upload bumps
# DataFile.latestVersionNumber for free — that is the change signal.
#
# This module has no ``adsk`` import and does no I/O. It takes a plain list of
# (filename, hub_version) pairs, which is all team_fs reads off the hub.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Accepted package extensions. ``.ptaddin`` is a plain zip with an opaque
# extension so Fusion Team never treats it as an archive to expand or translate;
# ``.zip`` is accepted too because zipfile does not care about the extension.
PACKAGE_SUFFIXES = (".ptaddin", ".zip")

# The package filename (minus extension) becomes the folder name under the
# Fusion AddIns directory, so it has to be a safe single path segment. Anything
# outside this charset is rejected rather than sanitised: a silently renamed
# folder would not match the ``<id>.manifest`` inside the package and would
# install as an add-in Fusion ignores.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


@dataclass(frozen=True)
class PackageRef:
    """One package file as it currently exists in the team folder."""

    addin_id: str
    filename: str
    hub_version: int


@dataclass(frozen=True)
class Change:
    """One planned action against the local AddIns directory."""

    ref: PackageRef
    action: str  # "install" | "update"
    previous_version: str = ""

    @property
    def is_update(self) -> bool:
        return self.action == "update"


@dataclass
class Plan:
    """The outcome of diffing the folder listing against local install state."""

    changes: List[Change] = field(default_factory=list)
    unchanged: List[PackageRef] = field(default_factory=list)
    # Installed ids whose package is no longer in the folder. Reported once,
    # never uninstalled: a hub hiccup or a permissions change can make a file
    # look absent, and silently stripping working add-ins over that is worse
    # than leaving something stale behind.
    orphans: List[str] = field(default_factory=list)
    # Files that look like packages but cannot be used.
    errors: List[str] = field(default_factory=list)

    @property
    def has_work(self) -> bool:
        return bool(self.changes)


def is_valid_addin_id(value) -> bool:
    """True when *value* is safe to use as a folder name under AddIns/."""
    if not isinstance(value, str):
        return False
    if value in (".", ".."):
        return False
    return bool(_ID_RE.match(value))


def split_package_name(filename: str) -> Optional[str]:
    """Return the add-in id for *filename*, or None when it is not a package.

    The id is simply the filename without its extension — that is the whole
    naming convention, and it is what makes a publish step unnecessary.
    """
    if not isinstance(filename, str):
        return None
    lowered = filename.lower()
    for suffix in PACKAGE_SUFFIXES:
        if lowered.endswith(suffix):
            return filename[: -len(suffix)]
    return None


def build_catalog(listing) -> Tuple[List[PackageRef], List[str]]:
    """Turn a raw folder listing into package references.

    ``listing`` is an iterable of ``(filename, hub_version)``. Non-package files
    are ignored silently — the folder is allowed to hold a readme or anything
    else. A file that IS a package but cannot be used is reported.
    """
    refs: List[PackageRef] = []
    errors: List[str] = []
    seen: Dict[str, str] = {}

    for filename, hub_version in listing:
        addin_id = split_package_name(filename)
        if addin_id is None:
            continue  # not a package; not our business

        if not is_valid_addin_id(addin_id):
            errors.append(
                f"'{filename}' cannot be installed: the name before the "
                f"extension must contain only letters, digits, dot, dash and "
                f"underscore."
            )
            continue

        # MyAddin.zip and MyAddin.ptaddin would fight over the same folder.
        if addin_id in seen:
            errors.append(
                f"'{filename}' and '{seen[addin_id]}' would both install as "
                f"'{addin_id}'. Remove one from the team folder."
            )
            continue

        try:
            version = int(hub_version)
        except (TypeError, ValueError):
            version = 0

        seen[addin_id] = filename
        refs.append(
            PackageRef(addin_id=addin_id, filename=filename, hub_version=version)
        )

    refs.sort(key=lambda r: r.addin_id.lower())
    return refs, errors


def fingerprint(listing) -> Dict[str, int]:
    """A cheap comparable snapshot of the folder: {filename: hub_version}.

    Comparing this against the cached copy catches additions, removals and
    re-uploads in one shot, which is the entire cost of a normal launch check.
    """
    snapshot: Dict[str, int] = {}
    for filename, hub_version in listing:
        if split_package_name(filename) is None:
            continue
        try:
            snapshot[filename] = int(hub_version)
        except (TypeError, ValueError):
            snapshot[filename] = 0
    return snapshot


def plan_changes(refs: List[PackageRef], installed) -> Plan:
    """Diff the folder *refs* against the local ``installed`` record.

    ``installed`` is the ``addins`` map from cache/team-addins-installed.json:
    ``{id: {"hub_version": int, "sha256": str, "version": str, ...}}``.

    The hub version number decides what is worth downloading. Whether the bytes
    actually changed is settled after the download, by hashing — a re-upload of
    identical content bumps the version but should not reinstall anything.
    """
    plan = Plan()
    installed = installed if isinstance(installed, dict) else {}
    present_ids = set()

    for ref in refs:
        present_ids.add(ref.addin_id)
        record = installed.get(ref.addin_id)
        if not isinstance(record, dict):
            plan.changes.append(Change(ref=ref, action="install"))
            continue

        try:
            known = int(record.get("hub_version") or 0)
        except (TypeError, ValueError):
            known = 0

        if known and known == ref.hub_version:
            plan.unchanged.append(ref)
            continue

        plan.changes.append(
            Change(
                ref=ref,
                action="update",
                previous_version=str(record.get("version") or ""),
            )
        )

    plan.orphans = sorted(set(installed) - present_ids)
    return plan
