# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Locate Fusion install resources relative to the running process.

The webdeploy hash in the install path changes with every Fusion update, so
callers must never hardcode a path. We anchor on the bundled ``adsk`` Python
package (``adsk.__file__``) and walk up looking for the well-known relative
sub-path that contains the resource we want.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Optional

# Relative path to RiverRubicon.xml from the install root, on each platform.
# macOS bundles everything under ``Autodesk Fusion.app/Contents/...``.
_RIVER_RUBICON_RELS = (
    os.path.join(
        "Contents",
        "Libraries",
        "Neutron",
        "Neutron",
        "Server",
        "Scene",
        "Resources",
        "Environments",
        "RiverRubicon",
        "RiverRubicon.xml",
    ),
    os.path.join(
        "Libraries",
        "Neutron",
        "Neutron",
        "Server",
        "Scene",
        "Resources",
        "Environments",
        "RiverRubicon",
        "RiverRubicon.xml",
    ),
)


def _candidate_seeds() -> Iterable[str]:
    """Directories to start the upward walk from. ``adsk`` is bundled inside
    the Fusion install, so its ``__file__`` is always under the install root.
    ``sys.executable`` is a fallback in case adsk's import shape changes.
    """
    try:
        import adsk.core as _adsk_core  # type: ignore

        path = getattr(_adsk_core, "__file__", None)
        if path:
            yield os.path.dirname(os.path.abspath(path))
    except Exception:
        pass
    exe = sys.executable
    if exe:
        yield os.path.dirname(os.path.abspath(exe))


def find_river_rubicon_xml() -> Optional[str]:
    """Return absolute path to RiverRubicon.xml in the running Fusion install,
    or ``None`` if it could not be located.
    """
    seen: set = set()
    for seed in _candidate_seeds():
        cur = seed
        prev = None
        while cur and cur != prev and cur not in seen:
            seen.add(cur)
            for rel in _RIVER_RUBICON_RELS:
                candidate = os.path.join(cur, rel)
                if os.path.isfile(candidate):
                    return candidate
            prev = cur
            cur = os.path.dirname(cur)
    return None
