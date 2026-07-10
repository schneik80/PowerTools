"""Unit tests for recents_utils — the shared recents cache used by the New
Assembly Recent gallery and the Open Recent File-menu flyout.

Only the pure cache layer is exercised here (touch_entries, plus the read/write
round-trip): the thumbnail render path needs a live Fusion design and is not
reachable outside the host. The module uses package-relative imports, so it is
loaded via its full package path with the conftest scaffolding in place (which
also fabricates the ``adsk`` package as a mock).
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
recents = importlib.import_module(f"{PT_PKG}.lib.ptAddInUtils.recents_utils")


def test_touch_entries_appends_new_newest_last() -> None:
    """A brand-new id is appended (oldest-first ordering keeps newest last)."""
    out = recents.touch_entries([], "id1", "Doc 1", "part", "Proj > A")
    assert out == [
        {"dataFileId": "id1", "name": "Doc 1", "intent": "part", "location": "Proj > A"}
    ]


def test_touch_entries_moves_existing_to_end_and_preserves_fields() -> None:
    """Re-touching an id moves it to newest and keeps prior fields a light
    touch omits (empty name/intent/location)."""
    entries = [
        {"dataFileId": "a", "name": "A", "intent": "part", "location": "P > A"},
        {"dataFileId": "b", "name": "B", "intent": "assembly"},
    ]
    out = recents.touch_entries(entries, "a", "", "", "")
    assert [e["dataFileId"] for e in out] == ["b", "a"]
    assert out[-1] == {
        "dataFileId": "a",
        "name": "A",
        "intent": "part",
        "location": "P > A",
    }


def test_touch_entries_updates_location_when_provided() -> None:
    """A non-empty location overrides the previously-stored one."""
    entries = [{"dataFileId": "a", "name": "A", "intent": "part"}]
    out = recents.touch_entries(entries, "a", "A", "part", "New > Loc")
    assert out[-1]["location"] == "New > Loc"


def test_touch_entries_omits_location_key_when_unknown() -> None:
    """No location is recorded (and no empty key added) when none is known."""
    out = recents.touch_entries([], "a", "A", "part")
    assert out == [{"dataFileId": "a", "name": "A", "intent": "part"}]


def test_touch_entries_ignores_blank_id() -> None:
    """A blank id is a no-op, returning a copy of the input."""
    assert recents.touch_entries([], "", "x", "part") == []


def test_read_write_round_trip(tmp_path, monkeypatch) -> None:
    path = tmp_path / "recent_docs.json"
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(path))
    entries = [{"dataFileId": "a", "name": "A", "intent": "part"}]
    recents.write_recent_cache(entries)
    assert recents.read_recent_cache() == entries


def test_read_missing_cache_returns_empty(tmp_path, monkeypatch) -> None:
    path = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(path))
    assert recents.read_recent_cache() == []


def test_write_caps_to_limit_keeping_newest(tmp_path, monkeypatch) -> None:
    path = tmp_path / "recent_docs.json"
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(path))
    monkeypatch.setattr(recents, "RECENT_LIMIT", 3)
    entries = [
        {"dataFileId": f"id{i}", "name": str(i), "intent": "part"} for i in range(5)
    ]
    recents.write_recent_cache(entries)
    kept = recents.read_recent_cache()
    assert [e["dataFileId"] for e in kept] == ["id2", "id3", "id4"]


def test_thumb_path_is_stable_and_md5_keyed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path))
    p1 = recents.thumb_path_for("urn:abc")
    p2 = recents.thumb_path_for("urn:abc")
    assert p1 == p2 and p1.endswith(".png")
    assert recents.thumb_path_for("urn:def") != p1
