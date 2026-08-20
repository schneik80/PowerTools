# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Verify, extract and live-load a Team Add-ins package.
#
# Ported from the Add-in Market add-in (PowerTools-Addinmarket/commands/
# addinmarket/installer.py), which proved that app.scripts.addExisting() +
# script.run() starts an add-in in the running session with no Fusion restart.
# Four defects in that original are fixed here:
#
#   1. It deleted the install folder while the old add-in was still running, so
#      an upgrade left the OLD code loaded. The order here is stop -> remove ->
#      extract -> run.
#   2. It read script.isRunOnStartup unconditionally; that property is only
#      valid when isAddIn is True, so for a plain script it raised, got
#      swallowed, and produced a false "restart required".
#   3. It called extractall() with no zip-slip guard.
#   4. Nothing stopped a package from overwriting the add-in doing the install.
#
# Everything here runs on the main thread.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
import zipfile
from dataclasses import dataclass

import adsk.core

from ... import config
from ...lib import ptAddInUtils as ptutil
from .catalog import PackageRef

# Windows keeps a handle open for a moment after a script is stopped, so the
# first rmtree of a just-stopped add-in can fail with a sharing violation.
_RMTREE_ATTEMPTS = 4
_RMTREE_BACKOFF_SECONDS = 0.25

_HASH_CHUNK = 1024 * 1024


class InstallError(Exception):
    """Raised when a single package cannot be installed."""


@dataclass
class InstallResult:
    """Outcome for one add-in. Never raises past sync.py: failures are data."""

    addin_id: str
    name: str
    version: str
    action: str  # "install" | "update"
    ok: bool
    started: bool = False
    restart_required: bool = False
    path: str = ""
    message: str = ""
    sha256: str = ""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def pending_dir() -> str:
    """Folder holding packages that could not be swapped in while running."""
    return os.path.join(config.CACHE_PATH, "team-addins", "pending")


def work_dir() -> str:
    """Scratch folder for manifest and package downloads."""
    return os.path.join(config.CACHE_PATH, "team-addins", "work")


def _addin_root() -> str:
    """Absolute path of the running PowerTools add-in folder."""
    return os.path.normcase(os.path.abspath(config.ADDIN_PATH))


def is_self(dest_path: str) -> bool:
    """True when *dest_path* is (or contains) the running PowerTools add-in.

    A team manifest that publishes an add-in whose id happens to match this
    add-in's folder would otherwise delete the code currently executing.
    """
    dest = os.path.normcase(os.path.abspath(dest_path))
    root = _addin_root()
    return dest == root or root.startswith(dest + os.sep)


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------


def sha256_of(path: str) -> str:
    """Return the lowercase hex sha256 of the file at *path*."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_changed(package_path: str, known_sha256: str) -> bool:
    """True when the downloaded bytes differ from what is already installed.

    There is no published checksum to authenticate against — the folder listing
    is the catalogue, and write access to the hub folder is the trust boundary.
    The hash earns its place differently: Fusion bumps a file's version on every
    upload, including a re-upload of identical content, so this is what stops a
    no-op republish from tearing down and restarting a working add-in.
    """
    if not known_sha256:
        return True
    return sha256_of(package_path).lower() != known_sha256.lower()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _is_within(base: str, target: str) -> bool:
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    return target == base or target.startswith(base + os.sep)


def safe_extract(zip_path: str, dest_dir: str) -> None:
    """Extract *zip_path* into *dest_dir*, rejecting any escaping member.

    zipfile.extractall() already sanitises absolute paths on modern Pythons but
    still happily writes through ``..`` on some platforms, so every member is
    resolved and checked before anything is written.
    """
    os.makedirs(dest_dir, exist_ok=True)
    try:
        archive = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise InstallError(
            "The package is not a readable zip archive. Ask whoever published "
            "it to re-upload."
        ) from exc

    with archive:
        for member in archive.namelist():
            resolved = os.path.join(dest_dir, member)
            if not _is_within(dest_dir, resolved):
                raise InstallError(
                    f"The package contains an unsafe path ({member!r}) that "
                    f"would write outside the install folder. Refusing to extract."
                )
        archive.extractall(dest_dir)


def locate_package_root(extract_dir: str, addin_id: str) -> str:
    """Return the folder inside *extract_dir* that should become AddIns/<id>.

    Handles both shapes an admin might produce: a zip of the add-in folder
    (one top-level directory) and a zip of its contents (files at the root).
    """
    entries = [e for e in os.listdir(extract_dir) if not e.startswith("__MACOSX")]
    if len(entries) == 1:
        candidate = os.path.join(extract_dir, entries[0])
        if os.path.isdir(candidate):
            return candidate
    return extract_dir


def validate_package_root(root: str, addin_id: str) -> None:
    """Raise InstallError unless *root* holds a ``<addin_id>.manifest``.

    Fusion matches an add-in folder to its manifest by name, and the folder is
    renamed to the manifest id on install, so a package whose manifest is named
    anything else installs as a folder Fusion silently ignores. Failing loudly
    here is the difference between a clear message and a mystery.
    """
    expected = f"{addin_id}.manifest"
    if os.path.isfile(os.path.join(root, expected)):
        return

    found = [e for e in os.listdir(root) if e.lower().endswith(".manifest")]
    if found:
        raise InstallError(
            f"The package contains {found[0]!r} but the manifest id is "
            f"'{addin_id}', so Fusion would not load it. Either rename the id "
            f"in {addin_id!r} to match, or rename the file to {expected!r}."
        )
    raise InstallError(
        f"The package has no {expected!r} at its root, so Fusion cannot load "
        f"it as an add-in."
    )


def read_manifest_version(root: str, addin_id: str) -> str:
    """Return the add-in's own declared version, or "" when it has none.

    Fusion add-in manifests already carry a version, so the display version
    comes from the package itself. Nobody has to declare it anywhere else.
    """
    path = os.path.join(root, f"{addin_id}.manifest")
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("version") or "").strip()


# ---------------------------------------------------------------------------
# Filesystem swap
# ---------------------------------------------------------------------------


def _on_rm_error(func, path, _exc_info):
    """rmtree onerror hook: clear the read-only bit and retry once."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise


def remove_tree(path: str) -> bool:
    """Remove *path*, retrying briefly through Windows sharing violations."""
    for attempt in range(_RMTREE_ATTEMPTS):
        if not os.path.exists(path):
            return True
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
            return True
        except Exception as exc:
            ptutil.log(
                f"Team Add-ins: rmtree attempt {attempt + 1} on {path} failed: {exc}"
            )
            time.sleep(_RMTREE_BACKOFF_SECONDS)
    return not os.path.exists(path)


def stage_pending(addin_id: str, root: str) -> str:
    """Park an extracted package for the next Fusion launch to apply."""
    target = os.path.join(pending_dir(), addin_id)
    os.makedirs(pending_dir(), exist_ok=True)
    remove_tree(target)
    shutil.move(root, target)
    ptutil.log(f"Team Add-ins: staged {addin_id} for next launch at {target}")
    return target


# ---------------------------------------------------------------------------
# Fusion session
# ---------------------------------------------------------------------------


def _scripts():
    return adsk.core.Application.get().scripts


def load_addin(dest_path: str, addin_id: str) -> bool:
    """Register and start the add-in at *dest_path* in the running session.

    Returns True when it is running, False when Fusion has to be restarted.

    Note: addExisting() on a path inside the standard AddIns directory adds a
    *linked* entry, and Fusion also scans that directory on the next launch, so
    Scripts and Add-Ins can show the same add-in twice until this is confirmed
    on a real build (see docs/Team Add-ins.md, "Open questions").
    """
    try:
        scripts = _scripts()
        script = scripts.itemByPath(dest_path)
        if script is None:
            script = scripts.addExisting(dest_path)
        if script is None:
            ptutil.log(f"Team Add-ins: addExisting returned None for {addin_id}")
            return False

        # isRunOnStartup is only valid for an add-in; reading it on a plain
        # script raises. Standard-location add-ins are auto-discovered anyway,
        # so a failure here is not worth reporting as an install failure.
        try:
            if script.isAddIn:
                script.isRunOnStartup = True
        except Exception as exc:
            ptutil.log(
                f"Team Add-ins: could not set isRunOnStartup for {addin_id}: {exc}"
            )

        if not script.isRunning:
            script.run()

        ptutil.log(f"Team Add-ins: started {addin_id}")
        return True

    except Exception as exc:
        ptutil.log(f"Team Add-ins: could not start {addin_id}: {exc}")
        return False


def stop_addin(dest_path: str) -> bool:
    """Stop the add-in at *dest_path*. Returns True when it is not running.

    Called before the folder is replaced. The Add-in Market original skipped
    this and left the old module loaded over new files.
    """
    if not dest_path:
        return True
    try:
        script = _scripts().itemByPath(dest_path)
        if script is None:
            return True
        if script.isRunning:
            script.stop()
            ptutil.log(f"Team Add-ins: stopped add-in at {dest_path}")
        return not script.isRunning
    except Exception as exc:
        ptutil.log(f"Team Add-ins: could not stop add-in at {dest_path}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def install_package(
    ref: PackageRef,
    package_path: str,
    action: str,
    extract_parent: str,
    allow_reload: bool = True,
) -> InstallResult:
    """Extract and install one downloaded package.

    *extract_parent* is a scratch directory the caller owns and cleans up.
    Raises InstallError; sync.py turns that into a failed InstallResult.
    """
    addin_id = ref.addin_id
    result = InstallResult(
        addin_id=addin_id,
        name=addin_id,
        version="",
        action=action,
        ok=False,
        sha256=sha256_of(package_path),
    )

    extract_dir = os.path.join(extract_parent, f"{addin_id}__extract")
    remove_tree(extract_dir)
    safe_extract(package_path, extract_dir)

    root = locate_package_root(extract_dir, addin_id)
    validate_package_root(root, addin_id)
    result.version = read_manifest_version(root, addin_id)

    addins_dir = config.fusion_addins_dir()
    if not addins_dir:
        raise InstallError(
            "Could not determine the Fusion AddIns directory on this machine."
        )
    os.makedirs(addins_dir, exist_ok=True)
    dest_path = os.path.join(addins_dir, addin_id)
    result.path = dest_path

    if is_self(dest_path):
        raise InstallError(
            f"'{addin_id}' resolves to the PowerTools add-in itself. Refusing to "
            f"overwrite the add-in that is running this update."
        )

    # Stop first, then remove: replacing files under a live module leaves the
    # old code loaded and the new code ignored.
    if os.path.exists(dest_path):
        stop_addin(dest_path)
        if not remove_tree(dest_path):
            stage_pending(addin_id, root)
            result.ok = True
            result.restart_required = True
            result.message = (
                "Downloaded, but the running copy could not be replaced while "
                "Fusion has it open. It will be applied on the next Fusion "
                "launch."
            )
            return result

    shutil.move(root, dest_path)
    ptutil.log(f"Team Add-ins: installed {addin_id} to {dest_path}")

    result.ok = True
    if allow_reload:
        result.started = load_addin(dest_path, addin_id)
        result.restart_required = not result.started
        result.message = (
            "Loaded and running."
            if result.started
            else "Installed. Restart Fusion to activate it."
        )
    else:
        result.restart_required = True
        result.message = "Installed. Restart Fusion to activate it."

    return result


def apply_pending() -> list:
    """Apply packages staged by a previous session. Runs at add-in start-up.

    At this point Fusion has just launched, so the target add-in has not been
    started from the old files yet on a cold start; when it has (a mid-session
    add-in reload), stop_addin still clears the way.
    """
    results = []
    staged_root = pending_dir()
    if not os.path.isdir(staged_root):
        return results

    addins_dir = config.fusion_addins_dir()
    for addin_id in sorted(os.listdir(staged_root)):
        source = os.path.join(staged_root, addin_id)
        if not os.path.isdir(source):
            continue

        dest_path = os.path.join(addins_dir, addin_id)
        result = InstallResult(
            addin_id=addin_id,
            name=addin_id,
            version="",
            action="update",
            ok=False,
            path=dest_path,
        )

        if is_self(dest_path):
            remove_tree(source)
            result.message = "Refused: resolves to the PowerTools add-in itself."
            results.append(result)
            continue

        try:
            if os.path.exists(dest_path):
                stop_addin(dest_path)
                if not remove_tree(dest_path):
                    result.restart_required = True
                    result.message = (
                        "Still in use. It will be retried on the next launch."
                    )
                    results.append(result)
                    continue
            shutil.move(source, dest_path)
            result.ok = True
            result.started = load_addin(dest_path, addin_id)
            result.restart_required = not result.started
            result.message = (
                "Pending update applied."
                if result.started
                else "Pending update applied. Restart Fusion to activate it."
            )
        except Exception as exc:
            result.message = f"Could not apply the pending update: {exc}"
            ptutil.log(f"Team Add-ins: apply_pending failed for {addin_id}: {exc}")

        results.append(result)

    # Remove the staging root when it has been drained, so a stale empty tree
    # never survives to confuse the next session.
    try:
        if not os.listdir(staged_root):
            os.rmdir(staged_root)
    except OSError:
        pass

    return results
