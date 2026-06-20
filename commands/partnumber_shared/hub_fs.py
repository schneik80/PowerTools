# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
"""Hub / project / folder navigation helpers.

The Pn-Cache JSON lives at:  <active hub> / Assets / Pn-Cache / pn-cache.json

- The ``Assets`` project must already exist (project creation requires admin
  rights in Fusion Team and is deliberately not automated).
- The ``Pn-Cache`` folder is auto-created on first use.
- ``pn-cache.json`` is auto-created on first write.
"""

from __future__ import annotations

from typing import Optional

import adsk.core


ASSETS_PROJECT_NAME = "Assets"
PN_CACHE_FOLDER_NAME = "Pn-Cache"
PN_CACHE_FILENAME = "pn-cache.json"


class HubFsError(Exception):
    """Raised when the hub/project/folder layout can't be resolved."""


def find_assets_project(app: adsk.core.Application) -> adsk.core.DataProject:
    """Return the ``Assets`` DataProject in the active hub or raise HubFsError."""
    data = app.data
    hub = data.activeHub
    if hub is None:
        raise HubFsError(
            "No active hub. Sign in to a Fusion Team hub and try again."
        )

    projects = hub.dataProjects
    if projects is None:
        raise HubFsError(
            "The active hub does not expose a project list "
            "(personal hubs cannot be used for shared part numbering)."
        )

    for i in range(projects.count):
        p = projects.item(i)
        if p.name == ASSETS_PROJECT_NAME:
            return p

    raise HubFsError(
        f"An '{ASSETS_PROJECT_NAME}' project is required in this hub. "
        f"Ask your admin to create it."
    )


def find_or_create_pn_cache_folder(project: adsk.core.DataProject) -> adsk.core.DataFolder:
    """Return the ``Pn-Cache`` folder under the Assets project root, creating it if needed."""
    root = project.rootFolder
    if root is None:
        raise HubFsError(
            f"Could not access the root folder of project '{project.name}'."
        )

    # Search existing.
    folders = root.dataFolders
    for i in range(folders.count):
        f = folders.item(i)
        if f.name == PN_CACHE_FOLDER_NAME:
            return f

    # Create.
    created = folders.add(PN_CACHE_FOLDER_NAME)
    if created is None:
        raise HubFsError(
            f"Could not create '{PN_CACHE_FOLDER_NAME}' folder "
            f"under '{project.name}'. Check your project permissions."
        )
    return created


def find_pn_cache_file(folder: adsk.core.DataFolder) -> Optional[adsk.core.DataFile]:
    """Return the ``pn-cache.json`` DataFile in the given folder, or None."""
    files = folder.dataFiles
    for i in range(files.count):
        f = files.item(i)
        if f.name == PN_CACHE_FILENAME:
            return f
        # Some Fusion calls return names without extension; handle both.
        base = PN_CACHE_FILENAME.rsplit(".", 1)[0]
        if f.name == base:
            return f
    return None
