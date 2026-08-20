"""Unit tests for recents_utils — the shared recents cache used by the New
Assembly Recent gallery and the Open Recent File-menu flyout.

Covers the pure cache layer (touch_entries plus the read/write round-trip) and
the ``list_recent`` merge, where Fusion's own recents list supplies the entries
and their order while this cache supplies the intent gap and thumbnails. The
native side is injected — ``fusion_recents`` has its own tests, and reaching it
for real would need a Fusion install — and the thumbnail render path needs a live
Fusion design, so neither is exercised here.

The module uses package-relative imports, so it is loaded via its full package
path with the conftest scaffolding in place (which also fabricates the ``adsk``
package as a mock).
"""

import importlib
from pathlib import Path
from types import SimpleNamespace

PT_PKG = Path(__file__).resolve().parent.parent.name
recents = importlib.import_module(f"{PT_PKG}.lib.ptAddInUtils.recents_utils")
# log_native_recents reads config.DEBUG lazily, so tests force the flag on the
# same module object it imports.
_config = importlib.import_module(f"{PT_PKG}.config")


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


def test_resolve_thumb_dir_prefers_the_addin_cache_folder(
    tmp_path, monkeypatch
) -> None:
    """The cache folder wins when it is writable — the temp dir gets purged."""
    monkeypatch.setattr(recents, "CACHE_FOLDER", str(tmp_path / "cache"))
    assert recents._resolve_thumb_dir() == str(tmp_path / "cache" / "thumbs")


def test_resolve_thumb_dir_falls_back_when_the_cache_folder_is_unwritable(
    tmp_path, monkeypatch
) -> None:
    """Locked-down installs can have a read-only add-in folder; temp still works.

    The probe is a real write, so this simulates the failure at ``open`` rather
    than by faking a permission bit — which is the case ``os.access`` misses.
    """
    monkeypatch.setattr(recents, "CACHE_FOLDER", str(tmp_path / "cache"))

    import builtins

    real_open = builtins.open

    def deny(path, *args, **kwargs):
        if str(path).endswith(".writable"):
            raise PermissionError("read-only install")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", deny)
    assert recents._resolve_thumb_dir() == recents._LEGACY_THUMB_DIR


def test_cached_thumbnail_path_finds_a_legacy_temp_dir_png(
    tmp_path, monkeypatch
) -> None:
    """A thumbnail written before the cache moved is reused, not re-downloaded."""
    current = tmp_path / "current"
    legacy = tmp_path / "legacy"
    current.mkdir()
    legacy.mkdir()
    monkeypatch.setattr(recents, "THUMB_DIR", str(current))
    monkeypatch.setattr(recents, "_LEGACY_THUMB_DIR", str(legacy))

    key = recents._thumb_key("urn:abc")
    stale = legacy / f"{key}.png"
    stale.write_bytes(b"PNG")

    assert recents.cached_thumbnail_path("urn:abc") == str(stale)


def test_cached_thumbnail_path_prefers_the_current_dir_over_the_legacy_one(
    tmp_path, monkeypatch
) -> None:
    """With both present the current cache wins, so a refresh actually takes."""
    current = tmp_path / "current"
    legacy = tmp_path / "legacy"
    current.mkdir()
    legacy.mkdir()
    monkeypatch.setattr(recents, "THUMB_DIR", str(current))
    monkeypatch.setattr(recents, "_LEGACY_THUMB_DIR", str(legacy))

    key = recents._thumb_key("urn:abc")
    (legacy / f"{key}.png").write_bytes(b"old")
    fresh = current / f"{key}.png"
    fresh.write_bytes(b"new")

    assert recents.cached_thumbnail_path("urn:abc") == str(fresh)


def test_cached_thumbnail_path_ignores_a_zero_byte_file(tmp_path, monkeypatch) -> None:
    """A truncated write must not masquerade as a usable thumbnail."""
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path))
    monkeypatch.setattr(recents, "_LEGACY_THUMB_DIR", str(tmp_path))
    (tmp_path / f"{recents._thumb_key('urn:abc')}.png").write_bytes(b"")

    assert recents.cached_thumbnail_path("urn:abc") == ""


def test_store_thumbnail_object_writes_the_cloud_png_into_the_cache(
    tmp_path, monkeypatch
) -> None:
    """A downloaded DataObject lands where both galleries and Open Recent read."""
    dest = tmp_path / "thumbs"
    monkeypatch.setattr(recents, "THUMB_DIR", str(dest))

    class FakeDataObject:
        """DataObject that only exposes the base64 route, as the cloud one does."""

        def getAsBase64String(self):
            import base64

            return base64.b64encode(b"PNGDATA").decode("ascii")

    path = recents.store_thumbnail_object(FakeDataObject(), "urn:abc")

    assert path == str(dest / f"{recents._thumb_key('urn:abc')}.png")
    assert (dest / f"{recents._thumb_key('urn:abc')}.png").read_bytes() == b"PNGDATA"


def test_store_thumbnail_object_tolerates_a_null_object(tmp_path, monkeypatch) -> None:
    """A failed future hands back None; storing it is a quiet no-op."""
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path))
    assert recents.store_thumbnail_object(None, "urn:abc") == ""


def test_touch_recent_skips_the_write_when_nothing_changed(
    tmp_path, monkeypatch
) -> None:
    """documentActivated fires on every tab switch, so the no-change case is the
    common one and must not rewrite the file."""
    path = tmp_path / "recent_docs.json"
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(path))
    recents.touch_recent("a", "A", "part", "P > A")
    first = path.stat().st_mtime_ns
    writes = []
    monkeypatch.setattr(recents, "write_recent_cache", lambda e: writes.append(e))

    recents.touch_recent("a", "A", "part", "P > A")

    assert writes == []
    assert path.stat().st_mtime_ns == first


# ---------------------------------------------------------------------------
# list_recent — the merge of Fusion's list with our cache
# ---------------------------------------------------------------------------


def _use_native(monkeypatch, entries) -> None:
    """Stand in for Fusion's parsed recents file (fusion_recents is tested
    separately, and reaching it here would need a real Fusion install)."""
    monkeypatch.setattr(recents, "_native_recents", lambda file_types=("f3d",): entries)


def _native(df_id, name="", intent="", location="", version="1"):
    return {
        "dataFileId": df_id,
        "name": name,
        "intent": intent,
        "location": location,
        "version": version,
        "lastOpened": 0,
        "versionUrn": "",
        "fileType": "f3d",
    }


def test_list_recent_takes_order_from_the_native_list(tmp_path, monkeypatch) -> None:
    """Fusion's ordering wins — our cache's positional order is not consulted."""
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path / "thumbs"))
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(tmp_path / "r.json"))
    recents.write_recent_cache([{"dataFileId": "a", "name": "A", "intent": "part"}])
    _use_native(monkeypatch, [_native("c", "C"), _native("b", "B"), _native("a", "A")])

    assert [i["dataFileId"] for i in recents.list_recent()] == ["c", "b", "a"]


def test_list_recent_fills_the_intent_gap_from_our_cache(tmp_path, monkeypatch) -> None:
    """The point of merging rather than replacing.

    Fusion records no design intent for ~25% of designs and never backfills it,
    but our cache knows the intent of anything opened while the add-in ran.
    """
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path / "thumbs"))
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(tmp_path / "r.json"))
    recents.write_recent_cache(
        [{"dataFileId": "a", "name": "A", "intent": "hybrid", "location": "P > Old"}]
    )
    _use_native(monkeypatch, [_native("a", "A", intent="", location="P > New")])

    item = recents.list_recent()[0]

    assert item["intent"] == "hybrid"  # from our cache
    assert item["location"] == "P > New"  # native wins where it has a value


def test_list_recent_prefers_native_intent_over_our_cache(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path / "thumbs"))
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(tmp_path / "r.json"))
    recents.write_recent_cache([{"dataFileId": "a", "name": "A", "intent": "part"}])
    _use_native(monkeypatch, [_native("a", "A", intent="assembly")])

    assert recents.list_recent()[0]["intent"] == "assembly"


def test_list_recent_falls_back_to_our_cache_without_a_native_list(
    tmp_path, monkeypatch
) -> None:
    """Unsupported platform, signed out, or an unreadable file — behave as before."""
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path / "thumbs"))
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(tmp_path / "r.json"))
    recents.write_recent_cache(
        [
            {"dataFileId": "a", "name": "A", "intent": "part"},
            {"dataFileId": "b", "name": "B", "intent": "assembly"},
        ]
    )
    _use_native(monkeypatch, [])

    # Cache is oldest-first on disk, so the fallback reverses it.
    assert [i["dataFileId"] for i in recents.list_recent()] == ["b", "a"]


def test_list_recent_honours_excludes_and_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path / "thumbs"))
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(tmp_path / "r.json"))
    _use_native(monkeypatch, [_native("a"), _native("b"), _native("c"), _native("d")])

    assert [i["dataFileId"] for i in recents.list_recent(exclude_ids={"b"})] == [
        "a",
        "c",
        "d",
    ]
    assert [i["dataFileId"] for i in recents.list_recent(limit=2)] == ["a", "b"]
    assert [
        i["dataFileId"] for i in recents.list_recent(exclude_ids={"a"}, limit=2)
    ] == ["b", "c"]


def test_list_recent_items_carry_the_documented_shape(tmp_path, monkeypatch) -> None:
    """Open Recent reads these keys by name, so the contract is pinned."""
    monkeypatch.setattr(recents, "THUMB_DIR", str(tmp_path / "thumbs"))
    monkeypatch.setattr(recents, "RECENT_CACHE_PATH", str(tmp_path / "r.json"))
    _use_native(monkeypatch, [_native("a", "A", "part", "P > A", "7")])

    assert recents.list_recent()[0] == {
        "dataFileId": "a",
        "name": "A",
        "intent": "part",
        "location": "P > A",
        "thumbPath": "",
        "version": "7",
    }


# ---------------------------------------------------------------------------
# Fusion's own recents list — the bridge that supplies the adsk-free reader
# (fusion_recents, covered by tests/test_fusion_recents.py) with live values.
# ---------------------------------------------------------------------------


def test_native_recents_path_survives_a_hostile_data_layer(monkeypatch) -> None:
    """Resolution must degrade to "" rather than raise into documentActivated.

    ``adsk`` is a MagicMock here, so ``app.data.activeHub`` yields mock values —
    a reasonable stand-in for the signed-out / offline / data-layer-not-up cases
    where these properties raise or return junk.
    """
    assert recents.native_recents_path() == ""


def test_native_recents_path_passes_hub_and_user_through(monkeypatch) -> None:
    """The hub URL is the primary signal and the user id is passed as a tiebreak."""
    seen = {}

    def fake_resolve(*, hub_url, hub_id, user_id):
        seen.update(hub_url=hub_url, hub_id=hub_id, user_id=user_id)
        return "/tmp/imallc_RecentsWithoutSearch_1.json"

    hub = SimpleNamespace(fusionWebURL="https://imallc.autodesk360.com", id="a.abc")
    fake_app = SimpleNamespace(data=SimpleNamespace(activeHub=hub), userId="2007072417")
    monkeypatch.setattr(recents, "app", fake_app)
    monkeypatch.setattr(recents.fusion_recents, "resolve_recents_path", fake_resolve)

    assert recents.native_recents_path().endswith("_RecentsWithoutSearch_1.json")
    assert seen == {
        "hub_url": "https://imallc.autodesk360.com",
        "hub_id": "a.abc",
        "user_id": "2007072417",
    }


def test_log_native_recents_is_inert_without_debug(monkeypatch) -> None:
    """Ships inert: with DEBUG off it must not resolve, log, or set its guard.

    DEBUG is forced rather than assumed — a developer checkout carries a
    ``.debug`` marker, so config.DEBUG is genuinely True here.
    """
    monkeypatch.setattr(recents, "_native_logged", False)
    monkeypatch.setattr(_config, "DEBUG", False)
    called = []
    monkeypatch.setattr(recents, "native_recents_path", lambda: called.append(1) or "")

    recents.log_native_recents()

    assert called == []
    assert recents._native_logged is False


def test_log_native_recents_runs_once_when_debug(monkeypatch) -> None:
    """Both commands call this on every documentActivated, so it must self-limit."""
    monkeypatch.setattr(recents, "_native_logged", False)
    monkeypatch.setattr(_config, "DEBUG", True)
    calls = []
    monkeypatch.setattr(recents, "native_recents_path", lambda: calls.append(1) or "")
    logged = []
    monkeypatch.setattr(recents.ptutil, "log", lambda msg, *a, **k: logged.append(msg))

    recents.log_native_recents()
    recents.log_native_recents()

    assert len(calls) == 1
    assert logged and "native resolution" in logged[0]
