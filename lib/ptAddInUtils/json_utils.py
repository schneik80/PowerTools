# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Shared JSON read/write helpers.

Every PowerTools cache, settings, and config file is small JSON. These two
helpers replace the ~20 hand-rolled ``open()`` + ``json.load/dump`` + try/except
blocks scattered across the add-in so the read/write contract stays uniform and,
critically, so that *writes are atomic*.

``write_json_atomic`` writes to a temporary file in the same directory and then
swaps it into place with ``os.replace`` (atomic on Windows and POSIX). A crash,
exception, or power loss mid-write therefore can never truncate or corrupt an
existing file — readers either see the old complete file or the new complete
file, never a half-written one. This matters most for user-authored state with
no cloud backing (favorites, hub config, preferences).

This module deliberately depends only on the standard library (no ``adsk``), so
it is importable for unit testing outside the Fusion runtime.
"""

import json
import os
import tempfile
from typing import Any


def read_json(path: str, default: Any = None) -> Any:
    """Return the parsed JSON contents of *path*, or *default* on any failure.

    A missing file, an unreadable file, or invalid JSON all yield *default*, so
    callers can treat "no file" and "corrupt file" identically — the documented
    contract for every cache/settings reader in this add-in. ``Any`` is used by
    design: JSON values are heterogeneous (dict, list, scalar).

    Args:
        path: Absolute path to the JSON file.
        default: Value returned when the file is absent or cannot be parsed.

    Returns:
        The parsed JSON object, or *default*.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        # ValueError covers json.JSONDecodeError and UnicodeDecodeError; OSError
        # covers read failures. Corrupt/unreadable caches degrade to *default*.
        return default


def write_json_atomic(path: str, data: Any, *, indent: int = 2) -> None:
    """Write *data* to *path* as JSON atomically.

    Serializes to a temporary file in the same directory, fsyncs it, then
    atomically replaces *path* with ``os.replace``. The destination directory is
    created if it does not exist. On any failure the temporary file is removed so
    no ``*.tmp`` litter is left behind, and the original exception propagates.

    Args:
        path: Absolute path to write.
        data: Any JSON-serializable object.
        indent: Indentation passed to ``json.dump`` (default 2).

    Raises:
        OSError: If the directory cannot be created or the file written.
        TypeError: If *data* is not JSON-serializable.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=indent)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        replaced = True
    finally:
        if not replaced and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
