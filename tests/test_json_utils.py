"""Unit tests for ``lib/ptAddInUtils/json_utils.py``.

The helper has no ``adsk`` dependency, so it is loaded directly from its file
path — this avoids importing the ``ptAddInUtils`` package (whose ``__init__``
pulls in ``adsk``). Tests focus on the read/default contract and, critically, on
the atomic-write guarantees: an existing file is never corrupted and no ``*.tmp``
litter is left behind, even when serialization fails.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_HELPER_PATH = (
    Path(__file__).resolve().parent.parent / "lib" / "ptAddInUtils" / "json_utils.py"
)
_spec = importlib.util.spec_from_file_location("pt_json_utils", _HELPER_PATH)
json_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(json_utils)


def test_read_json_missing_returns_default(tmp_path: Path) -> None:
    """A non-existent path yields the supplied default, not an exception."""
    missing = tmp_path / "nope.json"

    assert json_utils.read_json(missing.as_posix(), {"fallback": True}) == {
        "fallback": True
    }


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    """Data written atomically reads back identically."""
    path = (tmp_path / "data.json").as_posix()
    payload = {"hubs": [{"id": "abc", "name": "Acme"}], "count": 2}

    json_utils.write_json_atomic(path, payload)

    assert json_utils.read_json(path) == payload


def test_read_json_corrupt_returns_default(tmp_path: Path) -> None:
    """Invalid JSON degrades to the default rather than raising."""
    path = tmp_path / "broken.json"
    path.write_text("{ this is not valid json", encoding="utf-8")

    assert json_utils.read_json(path.as_posix(), []) == []


def test_write_creates_missing_parent_dirs(tmp_path: Path) -> None:
    """Intermediate directories are created as needed."""
    path = (tmp_path / "nested" / "deeper" / "out.json").as_posix()

    json_utils.write_json_atomic(path, {"ok": 1})

    assert json_utils.read_json(path) == {"ok": 1}


def test_write_overwrites_existing(tmp_path: Path) -> None:
    """A second write fully replaces the first."""
    path = (tmp_path / "data.json").as_posix()

    json_utils.write_json_atomic(path, {"v": 1})
    json_utils.write_json_atomic(path, {"v": 2})

    assert json_utils.read_json(path) == {"v": 2}


def test_write_leaves_no_tmp_litter_on_success(tmp_path: Path) -> None:
    """A successful write leaves only the target file in the directory."""
    path = (tmp_path / "data.json").as_posix()

    json_utils.write_json_atomic(path, {"v": 1})

    leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_failed_serialization_preserves_existing_file(tmp_path: Path) -> None:
    """If serialization fails, the original file is intact and no tmp remains.

    This is the core atomic-write guarantee: a write that raises mid-flight must
    never corrupt or truncate the previously good file.
    """
    path = tmp_path / "data.json"
    json_utils.write_json_atomic(path.as_posix(), {"good": True})

    # A set() is not JSON-serializable, so json.dump raises TypeError.
    with pytest.raises(TypeError):
        json_utils.write_json_atomic(path.as_posix(), {"bad": {1, 2, 3}})

    # Original content survives unchanged...
    assert json.loads(path.read_text(encoding="utf-8")) == {"good": True}
    # ...and no temp litter is left behind.
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []
