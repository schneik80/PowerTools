# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Team Add-ins orchestration: look -> plan -> apply -> report.
#
# There is no index file and no publish step. The folder listing is the
# catalogue, and Fusion's own per-file version numbers are the change signal:
#
#   1. List the Shared Addins folder once and fingerprint it as {filename: version}.
#      Identical to the cached snapshot -> stop. This is the whole cost of a
#      normal launch, and it catches additions, removals and re-uploads at once.
#   2. Download only the packages whose version number moved (or that are new).
#   3. Hash each download. Unchanged bytes -> record the new version and skip
#      the install, so a no-op republish never restarts a working add-in.
#
# Runs on the main thread (the Fusion Data API requires it). entry.py is what
# keeps it off the launch hot path.

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import adsk.core

from ... import config
from ...lib import ptAddInUtils as ptutil
from . import catalog, installer, team_fs

CMD_LABEL = "Team Add-ins"

INSTALLED_FILE = os.path.join(config.CACHE_PATH, "team-addins-installed.json")

# Report status values, also used by the palette to pick a banner style.
STATUS_UP_TO_DATE = "up_to_date"
STATUS_APPLIED = "applied"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


@dataclass
class Row:
    """One line in the report palette.

    Two notions of version, and they are not interchangeable. ``version`` is
    what the add-in's own manifest declares — the friendliest label when a
    developer maintains it, and worthless when they do not. ``revision`` is the
    hub's file version, which moves on every upload no matter what. The palette
    falls back to the revision so an update never renders as "1.0.0 → 1.0.0".
    """

    name: str
    addin_id: str
    version: str = ""
    from_version: str = ""
    revision: int = 0
    from_revision: int = 0
    action: str = ""  # "install" | "update"
    state: str = ""  # "loaded" | "restart" | "failed"
    message: str = ""


@dataclass
class Report:
    """Everything the user might be told about one check."""

    status: str = STATUS_UP_TO_DATE
    headline: str = ""
    detail: str = ""
    rows: List[Row] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    # Installed add-ins whose package has disappeared from the folder. Only the
    # ones not already mentioned on a previous run, so this is news once.
    orphans: List[str] = field(default_factory=list)
    restart_required: bool = False
    folder_name: str = ""
    project_name: str = ""
    checked_at: str = ""
    trigger: str = "startup"
    # True when this exact set of failures was already surfaced on an earlier
    # run. The automatic check uses it to stay quiet; a manual check ignores it,
    # so a click always gets an answer.
    repeat_failure: bool = False

    @property
    def is_news(self) -> bool:
        """True when this deserves the user's attention unprompted.

        The rule the whole deferred check is built around: a quiet result stays
        quiet — no palette, no dialog, nothing.
        """
        return bool(self.rows) or bool(self.errors) or bool(self.orphans)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "headline": self.headline,
            "detail": self.detail,
            "rows": [vars(row) for row in self.rows],
            "errors": list(self.errors),
            "orphans": list(self.orphans),
            "restartRequired": self.restart_required,
            "folderName": self.folder_name,
            "projectName": self.project_name,
            "checkedAt": self.checked_at,
            "trigger": self.trigger,
        }


# ---------------------------------------------------------------------------
# Local install state
# ---------------------------------------------------------------------------


def _load_file() -> dict:
    data = ptutil.read_json(INSTALLED_FILE, {})
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("hubs"), dict):
        data["hubs"] = {}
    return data


def load_state(hub_id: str) -> dict:
    """Return the install record for *hub_id*, with defaults filled in.

    State is per hub because the folder is resolved live rather than saved:
    switching hubs points at a different Shared Addins folder, and carrying one
    hub's fingerprint over to another would either suppress a real change or
    report every add-in as an orphan.
    """
    state = _load_file()["hubs"].get(hub_id)
    if not isinstance(state, dict):
        state = {}
    for key in ("fingerprint", "addins", "failed"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not isinstance(state.get("reported_orphans"), list):
        state["reported_orphans"] = []
    return state


def save_state(hub_id: str, state: dict) -> None:
    data = _load_file()
    data["hubs"][hub_id] = state
    ptutil.write_json_atomic(INSTALLED_FILE, data)


def installed_summary(hub_id: str) -> dict:
    """Small read-only view for the Preferences status card."""
    state = load_state(hub_id)
    return {
        "installedCount": len(state.get("addins", {})),
        "checkedAt": state.get("checked_at", ""),
    }


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def check_and_apply(
    trigger: str = "startup",
    force: bool = False,
    allow_reload: bool = True,
) -> Report:
    """Look at the Shared Addins folder and install whatever changed.

    Args:
        trigger: "startup" or "manual" — only affects reporting.
        force: skip the fingerprint short-circuit and re-examine the folder
            anyway. The manual refresh sets this so a click always has looked.
        allow_reload: when False, updates are written to disk but never
            stopped/started in this session (the conservative preference).

    Returns a Report. This function does not raise.
    """
    report = Report(trigger=trigger, checked_at=_now())
    app = adsk.core.Application.get()
    hub_id = team_fs.active_hub_id(app)

    try:
        folder = team_fs.resolve_folder(app)
    except team_fs.NotConfigured as exc:
        report.status = STATUS_NOT_CONFIGURED
        report.headline = (
            f"No '{team_fs.SHARED_ADDINS_FOLDER_NAME}' folder in this hub"
        )
        report.detail = (
            f"PowerTools Preferences → Team Add-ins can create it in the "
            f"'{team_fs.ASSETS_PROJECT_NAME}' project."
        )
        ptutil.log(f"{CMD_LABEL}: not set up ({exc})")
        return report
    except team_fs.TeamFsError as exc:
        report.status = STATUS_ERROR
        report.headline = "Could not reach the Shared Addins folder"
        report.detail = str(exc)
        report.errors.append(str(exc))
        ptutil.log(f"{CMD_LABEL}: {exc}")
        return report
    except Exception as exc:
        report.status = STATUS_UNAVAILABLE
        report.headline = "Could not reach the Shared Addins folder"
        report.detail = str(exc)
        ptutil.log(f"{CMD_LABEL}: unexpected error resolving folder: {exc}")
        return report

    report.folder_name = getattr(folder, "name", "") or ""
    try:
        report.project_name = getattr(folder.parentProject, "name", "") or ""
    except Exception:
        report.project_name = ""

    state = load_state(hub_id)
    previous_failures = dict(state.get("failed", {}))

    # --- Tier 1: one folder listing ----------------------------------------
    try:
        listing = team_fs.list_folder(folder)
    except team_fs.TeamFsError as exc:
        report.status = STATUS_ERROR
        report.headline = "Could not read the Shared Addins folder"
        report.detail = str(exc)
        report.errors.append(str(exc))
        return report

    snapshot = catalog.fingerprint(listing)
    if not force and snapshot and snapshot == state.get("fingerprint"):
        state["checked_at"] = report.checked_at
        save_state(hub_id, state)
        report.status = STATUS_UP_TO_DATE
        report.headline = "Team add-ins are up to date"
        ptutil.log(f"{CMD_LABEL}: folder unchanged ({len(snapshot)} packages).")
        return report

    refs, catalog_errors = catalog.build_catalog(listing)
    plan = catalog.plan_changes(refs, state.get("addins", {}))
    plan.errors.extend(catalog_errors)
    report.errors.extend(plan.errors)

    # Orphans are news exactly once. Repeating them every launch would be
    # nagging about something Team Add-ins deliberately will not act on.
    already_reported = set(state.get("reported_orphans", []))
    report.orphans = [o for o in plan.orphans if o not in already_reported]
    state["reported_orphans"] = sorted(set(plan.orphans))

    if not plan.has_work:
        state["fingerprint"] = snapshot
        state["checked_at"] = report.checked_at
        state["failed"] = {}
        save_state(hub_id, state)
        report.status = STATUS_ERROR if report.errors else STATUS_UP_TO_DATE
        report.headline = (
            "The Shared Addins folder has problems"
            if report.errors
            else "Team add-ins are up to date"
        )
        if report.orphans and not report.errors:
            report.headline = "Some team add-ins are no longer published"
        return report

    # --- Tiers 2 and 3: download what moved, install what actually changed --
    scratch = installer.work_dir()
    os.makedirs(scratch, exist_ok=True)
    failures = {}
    skipped_identical = 0

    for change in plan.changes:
        ref = change.ref
        record = state["addins"].get(ref.addin_id) or {}
        row = Row(
            name=ref.addin_id,
            addin_id=ref.addin_id,
            from_version=change.previous_version,
            revision=ref.hub_version,
            from_revision=_as_int(record.get("hub_version")),
            action=change.action,
        )
        package_local = os.path.join(scratch, ref.filename)
        try:
            package_file = team_fs.find_file(folder, ref.filename)
            if package_file is None:
                raise installer.InstallError(
                    f"'{ref.filename}' disappeared from the Shared Addins folder while "
                    f"it was being read."
                )
            team_fs.download(package_file, package_local)

            # A re-upload of identical bytes bumps the hub version but is not a
            # change worth restarting a running add-in for.
            if not installer.content_changed(
                package_local, str(record.get("sha256") or "")
            ):
                record["hub_version"] = ref.hub_version
                state["addins"][ref.addin_id] = record
                skipped_identical += 1
                ptutil.log(
                    f"{CMD_LABEL}: {ref.filename} re-uploaded unchanged; skipped."
                )
                continue

            result = installer.install_package(
                ref,
                package_local,
                change.action,
                scratch,
                allow_reload=allow_reload,
            )
            row.name = result.name
            row.version = result.version
            row.state = "restart" if result.restart_required else "loaded"
            row.message = result.message
            if result.restart_required:
                report.restart_required = True

            state["addins"][ref.addin_id] = {
                "hub_version": ref.hub_version,
                "sha256": result.sha256,
                "version": result.version,
                "installed_at": report.checked_at,
                "path": result.path,
                "pending_restart": bool(result.restart_required),
            }
        except installer.InstallError as exc:
            failures[ref.filename] = ref.hub_version
            row.state = "failed"
            row.message = str(exc)
            ptutil.log(f"{CMD_LABEL}: {ref.filename} failed: {exc}")
        except Exception as exc:
            failures[ref.filename] = ref.hub_version
            row.state = "failed"
            row.message = f"Unexpected error: {exc}"
            ptutil.handle_error(f"{CMD_LABEL}.{ref.addin_id}")
        finally:
            try:
                if os.path.exists(package_local):
                    os.remove(package_local)
            except OSError:
                pass

        if row.state:
            report.rows.append(row)

    # Only trust the fingerprint when everything landed. Leaving the old one in
    # place means the next launch retries rather than silently skipping a
    # package the user never received.
    if not failures:
        state["fingerprint"] = snapshot
    state["checked_at"] = report.checked_at

    # A package that is broken at the source would otherwise re-report on every
    # launch. Remember which file+version failed; a re-upload changes the
    # version and so is reported again.
    report.repeat_failure = bool(failures) and failures == previous_failures
    state["failed"] = failures

    save_state(hub_id, state)
    _clean_scratch(scratch)

    installed_count = sum(1 for r in report.rows if r.state != "failed")
    report.status = (
        STATUS_APPLIED if installed_count else (STATUS_ERROR if failures else STATUS_UP_TO_DATE)
    )
    report.headline = _headline(
        installed_count, len(failures), report.restart_required, skipped_identical
    )
    return report


def _headline(installed: int, failures: int, restart_required: bool, skipped: int) -> str:
    parts = []
    if installed:
        noun = "add-in" if installed == 1 else "add-ins"
        parts.append(
            f"Downloaded {installed} team {noun}"
            if restart_required
            else f"Updated {installed} team {noun}"
        )
    if failures:
        noun = "add-in" if failures == 1 else "add-ins"
        parts.append(f"{failures} {noun} could not be installed")
    if not parts and skipped:
        return "Team add-ins are up to date"
    return " — ".join(parts) if parts else "Nothing to do"


def _clean_scratch(scratch: str) -> None:
    try:
        shutil.rmtree(scratch, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pending updates staged by a previous session
# ---------------------------------------------------------------------------


def apply_pending() -> Optional[Report]:
    """Apply staged packages at start-up. Returns None when there were none."""
    try:
        results = installer.apply_pending()
    except Exception:
        ptutil.handle_error(f"{CMD_LABEL}.apply_pending")
        return None

    if not results:
        return None

    report = Report(trigger="pending", checked_at=_now(), status=STATUS_APPLIED)
    # Staged packages are applied whatever hub is active; the bookkeeping below
    # only clears the pending flag, so it is written against whichever hub's
    # record holds the add-in.
    hub_id = team_fs.active_hub_id(adsk.core.Application.get())
    state = load_state(hub_id)
    applied = 0
    for result in results:
        report.rows.append(
            Row(
                name=result.name,
                addin_id=result.addin_id,
                action=result.action,
                state=(
                    "failed"
                    if not result.ok
                    else ("restart" if result.restart_required else "loaded")
                ),
                message=result.message,
            )
        )
        if result.restart_required:
            report.restart_required = True
        if result.ok:
            applied += 1
            record = state["addins"].get(result.addin_id)
            if isinstance(record, dict):
                record["pending_restart"] = bool(result.restart_required)

    save_state(hub_id, state)
    report.headline = _headline(
        applied, len(results) - applied, report.restart_required, 0
    )
    return report
