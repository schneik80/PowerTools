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

Both resources here sit at different depths on macOS and Windows, because the
macOS install wraps everything in an ``Autodesk Fusion.app`` bundle and the
Windows one does not. The helpers that encode those shapes take the platform
(and the interpreter values they read) as arguments, so the Windows layout is
verifiable from a macOS test run rather than only on Windows.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Stable tail of the RiverRubicon path, below whatever wrapper directories the
# platform's install puts above it.
_RIVER_RUBICON_TAIL = os.path.join(
    "Neutron",
    "Server",
    "Scene",
    "Resources",
    "Environments",
    "RiverRubicon",
    "RiverRubicon.xml",
)

# Directories between an ancestor of the walk and the tail above. macOS is the
# confirmed first entry: ``Autodesk Fusion.app/Contents/Libraries/Neutron`` +
# the tail (the doubled "Neutron" is real — the prefix ends in one and the tail
# begins with another). The shorter forms cover the Windows webdeploy layout,
# which has no ``.app`` wrapper and may hold the libraries at the install root.
# Every prefix is tried on every platform: a miss costs one stat, and covering
# all the shapes keeps the palette working rather than silently empty if a
# layout differs from what we expect.
_RIVER_RUBICON_PREFIXES = (
    os.path.join("Contents", "Libraries", "Neutron"),
    os.path.join("Libraries", "Neutron"),
    "Neutron",
    "",
)

RIVER_RUBICON_RELS: Tuple[str, ...] = tuple(
    # join("", tail) is just tail, so the empty prefix needs no special case.
    os.path.join(prefix, _RIVER_RUBICON_TAIL)
    for prefix in _RIVER_RUBICON_PREFIXES
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
            for rel in RIVER_RUBICON_RELS:
                candidate = os.path.join(cur, rel)
                if os.path.isfile(candidate):
                    return candidate
            prev = cur
            cur = os.path.dirname(cur)
    return None


# ---------------------------------------------------------------------------
# Lighting environments
#
# Every environment ships its own ColorCycleTable, and they are not the same
# table: the twelve shipped environments carry three distinct palettes, and
# RiverRubicon's is the outlier (34 colors under its own naming scheme, where
# every other environment carries the same 32 colors in a different cycle
# order). So the palette has to come from the environment Fusion is actually
# rendering with, not from a fixed file.
# ---------------------------------------------------------------------------

_ENV_SUFFIX = "LightingEnvironment"


def find_environments_dir() -> Optional[str]:
    """Return the shipped ``Environments`` directory, or ``None``.

    Anchored on RiverRubicon.xml rather than probed for directly: that file is
    present in every install, so locating it validates the whole path shape,
    and the ``Environments`` directory is simply its grandparent. Probing for a
    bare directory named ``Environments`` would accept a false positive higher
    up the tree.
    """
    xml = find_river_rubicon_xml()
    if not xml:
        return None
    return os.path.dirname(os.path.dirname(xml))


def is_safe_environment_name(name: str) -> bool:
    """True if *name* is usable as a single path component.

    Environment names come from an ``adsk.core.LightingEnvironments`` attribute
    name, so they are already well-formed — this only keeps a surprising future
    enum value from being joined into a path unchecked.
    """
    return bool(name) and name.isalnum()


def find_environment_xml(name: str) -> Optional[str]:
    """Return the XML for the named environment, or ``None`` if absent.

    Each environment stores its resources in a self-named folder, so
    ``GreyRoom`` resolves to ``Environments/GreyRoom/GreyRoom.xml``.
    """
    if not is_safe_environment_name(name):
        return None
    directory = find_environments_dir()
    if not directory:
        return None
    candidate = os.path.join(directory, name, f"{name}.xml")
    return candidate if os.path.isfile(candidate) else None


def lighting_environment_dirs(enum_cls: object) -> Dict[int, str]:
    """Map ``adsk.core.LightingEnvironments`` values to environment folder names.

    Built by introspecting the enum rather than hardcoding its integers, so a
    Fusion update that reorders or extends the list stays correct instead of
    silently loading the wrong palette. Each member is named
    ``<Folder>LightingEnvironment`` and the folder it names ships under
    ``Environments/`` — ``GreyRoomLightingEnvironment`` → ``GreyRoom``.
    """
    out: Dict[int, str] = {}
    for attr in dir(enum_cls):
        if not attr.endswith(_ENV_SUFFIX) or attr == _ENV_SUFFIX:
            continue
        value = getattr(enum_cls, attr, None)
        # Guard against bool, which is an int subclass, and against the
        # descriptor objects a stub class can expose instead of plain values.
        if isinstance(value, int) and not isinstance(value, bool):
            out[value] = attr[: -len(_ENV_SUFFIX)]
    return out


# ---------------------------------------------------------------------------
# Bundled Python interpreter (for the out-of-process color picker)
# ---------------------------------------------------------------------------


def is_python_binary(path: str) -> bool:
    """True if *path* names a Python interpreter rather than some other binary.

    Inside Fusion, ``sys.executable`` is the host application — ``Fusion360.exe``
    on Windows — not a Python binary, so any fallback to it has to be filtered.
    Handing the host executable to ``subprocess`` would fail silently from the
    user's point of view: no picker appears and no error is raised.

    ``splitext`` leaves the POSIX ``python3.14`` as ``python3`` and turns
    ``pythonw.exe`` into ``pythonw``; both start with "python", while
    ``Fusion360`` does not.

    The basename is taken on both separators rather than via ``os.path``, which
    only understands the host's own. In production that makes no difference —
    Windows paths are only ever evaluated on Windows — but it lets the Windows
    behavior be tested from a macOS run, as the module docstring promises.
    """
    if not path:
        return False
    base = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    stem = os.path.splitext(base)[0].lower()
    return stem.startswith("python")


def _python_candidates(
    platform: str,
    exec_prefix: str,
    executable: str,
    version_info: Sequence[int],
) -> List[str]:
    """Interpreter-path candidates for *platform*, most likely first.

    Windows keeps the interpreter directly in the prefix (``<prefix>\\python.exe``)
    while POSIX keeps it in a ``bin`` subdirectory with a version-suffixed name
    (``<prefix>/bin/python3.14``) — so neither platform's candidates exist on the
    other. On Windows, ``pythonw.exe`` is tried first: it is the GUI build of the
    interpreter, so spawning it does not flash a console window behind the picker.
    """
    out: List[str] = []
    if exec_prefix:
        if platform == "win32":
            for directory in (exec_prefix, os.path.join(exec_prefix, "Scripts")):
                for name in ("pythonw.exe", "python.exe"):
                    out.append(os.path.join(directory, name))
        else:
            bin_dir = os.path.join(exec_prefix, "bin")
            major, minor = version_info[0], version_info[1]
            for name in (f"python{major}.{minor}", f"python{major}", "python"):
                out.append(os.path.join(bin_dir, name))
    if is_python_binary(executable):
        out.append(executable)
    return out


def _is_runnable_file(path: str) -> bool:
    """True if *path* is a file we can execute.

    The executable bit is only checked on POSIX. On Windows ``os.access``
    ignores ``X_OK`` entirely and reduces to an existence test, so testing it
    there would wrongly accept any file that happens to exist.
    """
    if not path or not os.path.isfile(path):
        return False
    if os.name == "nt":
        return True
    return os.access(path, os.X_OK)


def find_bundled_python() -> Optional[str]:
    """Locate the Python interpreter bundled with Fusion, or ``None``.

    ``sys.executable`` inside Fusion points at the host application rather than
    a Python binary, so the path is derived from ``sys.exec_prefix``.
    """
    for path in _python_candidates(
        sys.platform, sys.exec_prefix, sys.executable, sys.version_info
    ):
        if _is_runnable_file(path):
            return path
    return None
