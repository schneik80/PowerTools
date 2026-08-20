# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Hub navigation for Team Add-ins.
#
# The location is a convention, not a setting:
#
#     <active hub> / Assets / Shared Addins /
#
# the same shape commands/partnumber_shared uses for Assets/Pn-Cache. Nobody
# browses for it and nothing is saved to disk — the folder either exists in the
# active hub or it does not, and PowerTools Preferences offers to create it.
# The navigation is deliberately mirrored from hub_fs rather than imported: the
# messages there are written for the part-numbering flow and would read as
# nonsense here.
#
# Everything in this module touches the Fusion Data API and must run on the
# main thread.

from __future__ import annotations

import os

import adsk.core

from ...lib import ptAddInUtils as ptutil
from .catalog import PACKAGE_SUFFIXES

# The project must already exist — creating a project needs admin rights in
# Fusion Team, so that is deliberately not automated. The folder inside it is
# created on request from Preferences.
ASSETS_PROJECT_NAME = "Assets"
SHARED_ADDINS_FOLDER_NAME = "Shared Addins"


class TeamFsError(Exception):
    """Raised when the hub, project or folder cannot be reached."""


class NotConfigured(TeamFsError):
    """The Shared Addins folder does not exist in the active hub yet.

    Distinct from TeamFsError because this is the normal state before setup:
    it must stay silent, not surface as an error.
    """


def active_hub(app: adsk.core.Application):
    """Return the active DataHub, or None when the user is not signed in yet."""
    try:
        return app.data.activeHub
    except Exception:
        return None


def active_hub_id(app: adsk.core.Application) -> str:
    hub = active_hub(app)
    return (getattr(hub, "id", "") or "") if hub is not None else ""


def find_assets_project(app: adsk.core.Application):
    """Return the ``Assets`` DataProject in the active hub."""
    hub = active_hub(app)
    if hub is None:
        raise NotConfigured("No active hub. Sign in to a Fusion Team hub.")

    try:
        projects = hub.dataProjects
    except Exception as exc:
        raise TeamFsError(f"Could not read the projects in this hub: {exc}") from exc

    if projects is None:
        raise TeamFsError(
            f"This hub does not expose a project list, so a shared "
            f"'{ASSETS_PROJECT_NAME}' project cannot be used. Team Add-ins needs "
            f"a Fusion Team hub."
        )

    for i in range(projects.count):
        project = projects.item(i)
        if project.name == ASSETS_PROJECT_NAME:
            return project

    raise TeamFsError(
        f"This hub has no '{ASSETS_PROJECT_NAME}' project. Ask your Fusion Team "
        f"administrator to create one — creating a project needs admin rights, "
        f"so PowerTools will not do it for you."
    )


def _folder_key(name: str) -> str:
    """Normalise a folder name for comparison: case, spaces and dashes."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def find_shared_addins_folder(project, create: bool = False):
    """Return the ``Shared Addins`` folder in *project*, or None.

    With ``create=True`` the folder is created when it is missing. The check
    never passes True: silently creating cloud folders at Fusion start-up is
    not something an add-in should do uninvited.
    """
    root = project.rootFolder
    if root is None:
        raise TeamFsError(
            f"Could not open the root folder of project '{project.name}'."
        )

    # Match loosely before creating anything. Teams name this folder by hand,
    # so "Shared AddIns" and "Shared add-ins" are both likely; an exact-only
    # match would quietly create a second folder in a live shared project,
    # which is a nuisance to undo. An exact hit always wins.
    wanted = _folder_key(SHARED_ADDINS_FOLDER_NAME)
    fallback = None
    try:
        folders = root.dataFolders
        for i in range(folders.count):
            folder = folders.item(i)
            name = getattr(folder, "name", "") or ""
            if name == SHARED_ADDINS_FOLDER_NAME:
                return folder
            if fallback is None and _folder_key(name) == wanted:
                fallback = folder
    except Exception as exc:
        raise TeamFsError(f"Could not read folders in '{project.name}': {exc}") from exc

    if fallback is not None:
        ptutil.log(
            f"Team Add-ins: using existing folder '{fallback.name}' in "
            f"'{project.name}'."
        )
        return fallback

    if not create:
        return None

    try:
        created = folders.add(SHARED_ADDINS_FOLDER_NAME)
    except Exception as exc:
        raise TeamFsError(
            f"Could not create '{SHARED_ADDINS_FOLDER_NAME}' in '{project.name}': {exc}"
        ) from exc

    if created is None:
        raise TeamFsError(
            f"Could not create '{SHARED_ADDINS_FOLDER_NAME}' in "
            f"'{project.name}'. Check your permissions on that project."
        )
    ptutil.log(f"Team Add-ins: created {project.name}/{SHARED_ADDINS_FOLDER_NAME}.")
    return created


def resolve_folder(app: adsk.core.Application, create: bool = False):
    """Return the Shared Addins folder for the active hub.

    Raises NotConfigured when it does not exist yet, which the check treats as
    "stay silent" rather than as an error.
    """
    project = find_assets_project(app)
    folder = find_shared_addins_folder(project, create=create)
    if folder is None:
        raise NotConfigured(
            f"No '{SHARED_ADDINS_FOLDER_NAME}' folder in the "
            f"'{project.name}' project yet."
        )
    return folder


def folder_status(app: adsk.core.Application) -> dict:
    """Describe the Shared Addins folder for the Preferences status card.

    Never raises: every outcome is reported as data so the palette can render
    it. ``state`` is one of "ready", "missing", "no_hub" or "error".
    """
    status = {
        "state": "error",
        "hubName": "",
        "projectName": ASSETS_PROJECT_NAME,
        "folderName": SHARED_ADDINS_FOLDER_NAME,
        "message": "",
        "packageCount": 0,
    }

    hub = active_hub(app)
    if hub is None:
        status["state"] = "no_hub"
        status["message"] = "Sign in to a Fusion Team hub."
        return status
    status["hubName"] = getattr(hub, "name", "") or ""

    try:
        project = find_assets_project(app)
    except NotConfigured as exc:
        status["state"] = "no_hub"
        status["message"] = str(exc)
        return status
    except TeamFsError as exc:
        status["message"] = str(exc)
        return status

    status["projectName"] = project.name
    try:
        folder = find_shared_addins_folder(project, create=False)
    except TeamFsError as exc:
        status["message"] = str(exc)
        return status

    if folder is None:
        status["state"] = "missing"
        status["message"] = (
            f"Not created yet. PowerTools can make it in '{project.name}'."
        )
        return status

    status["state"] = "ready"
    try:
        status["packageCount"] = sum(
            1
            for name, _ in list_folder(folder)
            if name.lower().endswith(PACKAGE_SUFFIXES)
        )
    except TeamFsError:
        status["packageCount"] = 0
    return status


# ---------------------------------------------------------------------------
# Reading the folder
# ---------------------------------------------------------------------------


def file_name_of(data_file) -> str:
    """Return the full filename of *data_file*, extension included.

    Some Fusion builds report ``DataFile.name`` without the extension (the same
    inconsistency hub_fs.find_pn_cache_file defends against). The extension is
    load-bearing here — it is what marks a file as an add-in package — so it is
    reattached from ``fileExtension`` when it is missing.
    """
    name = getattr(data_file, "name", "") or ""
    extension = (getattr(data_file, "fileExtension", "") or "").lstrip(".")
    if not extension or name.lower().endswith("." + extension.lower()):
        return name
    return f"{name}.{extension}"


def latest_version_of(data_file) -> int:
    """Return the newest version number of *data_file*, or 0 when unknown.

    Fusion bumps this on every upload, which is what lets Team Add-ins detect a
    republished package without anyone maintaining an index.
    """
    for attr in ("latestVersionNumber", "versionNumber"):
        try:
            value = getattr(data_file, attr)
        except Exception:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def list_folder(folder):
    """Return ``[(filename, hub_version), ...]`` for everything in *folder*.

    This one listing is the entire steady-state cost of the launch check: the
    caller fingerprints it and stops when it matches the cached snapshot.
    """
    listing = []
    try:
        files = folder.dataFiles
        for i in range(files.count):
            data_file = files.item(i)
            listing.append((file_name_of(data_file), latest_version_of(data_file)))
    except Exception as exc:
        raise TeamFsError(f"Could not list the Shared Addins folder: {exc}") from exc
    return listing


def find_file(folder, filename: str):
    """Return the DataFile whose resolved filename is *filename*, or None."""
    try:
        files = folder.dataFiles
        for i in range(files.count):
            data_file = files.item(i)
            if file_name_of(data_file) == filename:
                return data_file
    except Exception as exc:
        raise TeamFsError(f"Could not list the Shared Addins folder: {exc}") from exc
    return None


def download(data_file, local_path: str) -> str:
    """Download *data_file* to *local_path* and return the path.

    ``DataFile.download`` is synchronous when the handler argument is None.
    """
    directory = os.path.dirname(local_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # Any stale copy from a previous run would be indistinguishable from a
    # successful download, so clear it first.
    try:
        if os.path.exists(local_path):
            os.remove(local_path)
    except OSError:
        pass

    try:
        ok = data_file.download(local_path, None)
    except Exception as exc:
        raise TeamFsError(
            f"Could not download '{getattr(data_file, 'name', '?')}': {exc}"
        ) from exc

    if not ok or not os.path.exists(local_path):
        raise TeamFsError(
            f"Download of '{getattr(data_file, 'name', '?')}' did not produce a file."
        )
    ptutil.log(f"Team Add-ins: downloaded {local_path}")
    return local_path
