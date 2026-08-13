# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Shared "recent documents" cache and thumbnail store for PowerTools.

Two PowerTools commands surface the same list of recently-touched
part/hybrid/assembly documents:

  * **New Assembly** (``commands/assemblyintent``) — the Recent gallery in its
    quick-start palette.
  * **Open Recent** (``commands/openrecent``) — the File-menu flyout.

This module is the single source of truth for that data so the two commands can
never drift: the on-disk cache format and location, the per-document thumbnail
cache, and the record / list / render helpers all live here. It mirrors the
``cache_utils`` philosophy ("this module owns the format so it stays in sync").
Both surfaces call ``list_recent``, which is where the two data sources meet.

**Fusion's own recents list is the source of the entries and their order.**
``fusion_recents`` reads it (see that module for how the per-user, per-hub file is
located). It covers hundreds of documents with real ``lastOpened`` timestamps —
including ones opened before this add-in was installed, or during a session on
another machine — and supplies each entry's Data Panel location for free.

**Our own cache is the memo overlaid on top**, holding the two things Fusion's
file lacks: the design intent for the ~25% of designs whose ``docstruct`` is
empty (permanently — comparing files a month apart shows it is never backfilled),
and the thumbnail. It is also the whole list when no native file can be read:
an unsupported platform, a signed-out session, or an unreadable file all fall
back to it, which is the behaviour that predates the native reader.

The cache file (``cache/recent_docs.json``) is a JSON list, oldest-first, of::

    {"dataFileId": "urn:…", "name": "Doc name", "intent": "part|hybrid|assembly",
     "location": "Project > Folder > Sub"}

``location`` is captured while the document is open (its ``parentFolder`` chain
is available for free) so the Open Recent tooltip needs no cloud round-trip.
Entries written before this field existed simply omit it and degrade to a
name-only tooltip.

Thumbnails are rendered from the live root component with
``Component.createThumbnail`` while a document is open — the only time Fusion can
render one — and cached on disk keyed by ``md5(dataFileId)``. Closed documents
reuse whatever PNG was cached when they were last open.

The pure cache helpers (``touch_entries``, ``read_recent_cache``,
``write_recent_cache``) deliberately avoid any ``adsk`` dependency so they stay
unit-testable outside the Fusion runtime; the Fusion-specific rendering degrades
gracefully behind ``try/except`` and never raises into a caller.
"""

import base64
import hashlib
import json
import os
import tempfile

import adsk.core
import adsk.fusion

from . import fusion_recents, json_utils
from . import general_utils as ptutil
from .cache_utils import CACHE_FOLDER

app = adsk.core.Application.get()

# One-shot guard for log_native_recents: both commands call
# remember_recent_if_eligible on every documentActivated, so the diagnostic
# would otherwise repeat on every tab switch.
_native_logged = False

# Memo for Fusion's own recents list, keyed on the resolved path, the active hub
# and the file's (mtime, size). See _native_recents.
_native_cache: dict = {}

# Cache of recently-touched part/hybrid/assembly documents, shared by the New
# Assembly palette and the Open Recent flyout. Lives beside the other add-in
# caches under ``cache/``.
RECENT_CACHE_PATH = os.path.join(CACHE_FOLDER, "recent_docs.json")

# Per-document thumbnail cache. The historical directory name is kept so
# thumbnails rendered by earlier builds remain valid (the key scheme is
# ``md5(dataFileId)``). It lives in the OS temp dir because the bundled add-in
# cache folder can be read-only on locked-down installs.
THUMB_DIR = os.path.join(tempfile.gettempdir(), "powertools_assembly_thumbs")
THUMB_SIZE = 86  # px; small enough for a gallery card or a menu tool-clip.

# Cap on how many entries the cache retains (newest kept). Sized to cover
# Fusion's own list rather than a gallery page: this cache is now the memo that
# supplies intent and thumbnails for the native entries, so a cap far below the
# native count would leave most of them unmemoized. ~300 entries is ~45 KB.
RECENT_LIMIT = 300

# Design intents the recents cache tracks.
DESIGN_INTENTS = ("part", "hybrid", "assembly")


# ---------------------------------------------------------------------------
# Design-intent helpers
# ---------------------------------------------------------------------------


def design_intent(doc) -> int | None:
    """Return *doc*'s design intent value, or None when it has no Design product."""
    try:
        product = doc.products.itemByProductType("DesignProductType")
        design = adsk.fusion.Design.cast(product)
        if design is None:
            return None
        return design.designIntent
    except Exception:
        return None


def intent_name(intent: int | None) -> str:
    """Map a Fusion design-intent value to "part" / "hybrid" / "assembly" / ""."""
    types = adsk.fusion.DesignIntentTypes
    if intent == types.PartDesignIntentType:
        return "part"
    if intent == types.HybridDesignIntentType:
        return "hybrid"
    if intent == types.AssemblyDesignIntentType:
        return "assembly"
    return ""


# ---------------------------------------------------------------------------
# Cache read / write / touch  (pure — no adsk dependency)
# ---------------------------------------------------------------------------


def read_recent_cache() -> list[dict]:
    """Return the recents cache as a list (oldest-first), or [] if absent/corrupt."""
    if not os.path.exists(RECENT_CACHE_PATH):
        return []
    try:
        with open(RECENT_CACHE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except Exception:
        ptutil.log("recents: cache unreadable — starting fresh.")
    return []


def write_recent_cache(entries: list[dict]) -> None:
    """Persist *entries* (only the newest RECENT_LIMIT are kept).

    Written atomically because both New Assembly and Open Recent record from
    their own ``documentActivated`` handler, so two writes race on this file on
    every tab switch; a plain truncating write can leave a reader with a
    half-written file. ``write_json_atomic`` also creates the directory.

    Imported from ``json_utils`` directly: ``ptutil`` is ``general_utils`` here,
    not the package the other callers of this helper alias.
    """
    try:
        json_utils.write_json_atomic(RECENT_CACHE_PATH, entries[-RECENT_LIMIT:])
    except Exception as e:
        ptutil.log(f"recents: could not write cache — {e}")


def touch_entries(
    entries: list[dict],
    df_id: str,
    name: str,
    intent_name_str: str,
    location: str = "",
) -> list[dict]:
    """Return *entries* with *df_id* moved to the end (newest).

    Pure and IO-free so it can be unit-tested. A field the caller omits (empty
    string) is filled from the document's previous entry, so a lightweight touch
    (e.g. an insert with no location) never discards richer data recorded earlier
    while the document was open.
    """
    if not df_id:
        return list(entries)
    prev = next((e for e in entries if e.get("dataFileId") == df_id), {})
    kept = [e for e in entries if e.get("dataFileId") != df_id]
    merged = {
        "dataFileId": df_id,
        "name": name or prev.get("name", ""),
        "intent": intent_name_str or prev.get("intent", ""),
    }
    loc = location or prev.get("location", "")
    if loc:
        merged["location"] = loc
    kept.append(merged)
    return kept


def touch_recent(
    df_id: str, name: str, intent_name_str: str, location: str = ""
) -> None:
    """Record (or refresh) a recents entry on disk. Safe to call redundantly."""
    try:
        if not df_id:
            return
        entries = read_recent_cache()
        merged = touch_entries(entries, df_id, name, intent_name_str, location)
        # documentActivated fires on every tab switch, so re-activating the same
        # document is the common case and usually changes nothing. Skipping the
        # write there removes most of the disk churn — and most of the contention
        # between the two commands' handlers.
        if merged == entries:
            return
        write_recent_cache(merged)
    except Exception as e:
        ptutil.log(f"recents: touch_recent failed — {e}")


# ---------------------------------------------------------------------------
# Thumbnail cache
# ---------------------------------------------------------------------------


def thumb_path_for(df_id: str) -> str:
    """On-disk PNG path (whether or not it exists) for *df_id*'s thumbnail."""
    safe = hashlib.md5(df_id.encode("utf-8")).hexdigest()
    return os.path.join(THUMB_DIR, f"{safe}.png")


def png_to_data_url(path: str) -> str:
    """Read a PNG and return it as a ``data:image/png;base64,…`` URL, or ""."""
    try:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def cached_thumbnail_path(df_id: str) -> str:
    """Return the cached PNG path for *df_id* if one exists on disk, else ""."""
    if not df_id:
        return ""
    path = thumb_path_for(df_id)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    return ""


def cached_thumbnail_data_url(df_id: str) -> str:
    """Return a cached thumbnail as a data: URL if present, else "".

    Used by the New Assembly Recent gallery, whose closed documents cannot be
    rendered live and reuse the PNG cached while they were last open.
    """
    path = cached_thumbnail_path(df_id)
    return png_to_data_url(path) if path else ""


def _save_thumbnail_object(data_object, cache_path: str) -> str:
    """Persist a ``createThumbnail`` DataObject to *cache_path*, returning it on
    success or "" on failure.

    Tries ``saveToFile`` first, then falls back to decoding the object's base64
    PNG bytes ourselves — the latter works on every DataObject and sidesteps any
    path-handling quirks in ``saveToFile``.
    """
    saver = getattr(data_object, "saveToFile", None)
    if callable(saver):
        try:
            if (
                saver(cache_path)
                and os.path.exists(cache_path)
                and os.path.getsize(cache_path) > 0
            ):
                return cache_path
        except Exception:
            pass

    b64_getter = getattr(data_object, "getAsBase64String", None)
    if callable(b64_getter):
        try:
            b64 = b64_getter()
            if b64:
                with open(cache_path, "wb") as fh:
                    fh.write(base64.b64decode(b64))
                if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                    return cache_path
        except Exception:
            pass
    return ""


def render_thumbnail_for_doc(doc, df_id: str) -> str:
    """Render *doc*'s root component to a cached PNG and return a data: URL.

    Only works while the document is open (``Component.createThumbnail`` needs a
    live design). Returns the cached PNG immediately when one already exists, so
    calling this on every ``documentActivated`` renders each document at most
    once. All failures degrade to "" — never a raise.
    """
    if not df_id:
        return ""
    cache_path = thumb_path_for(df_id)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return png_to_data_url(cache_path)
    try:
        os.makedirs(THUMB_DIR, exist_ok=True)
        product = doc.products.itemByProductType("DesignProductType")
        design = adsk.fusion.Design.cast(product)
        if design is None:
            return ""
        root = design.rootComponent
        if not hasattr(root, "createThumbnail"):
            return ""
        data_object = root.createThumbnail(THUMB_SIZE, THUMB_SIZE, "PNG")
        if data_object is None:
            return ""
        produced = _save_thumbnail_object(data_object, cache_path)
        return png_to_data_url(produced) if produced else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Recording + listing
# ---------------------------------------------------------------------------


def folder_lineage(folder) -> str:
    """Return a "Project > Folder > Sub" display path for *folder*, or ""."""
    parts: list[str] = []
    current = folder
    depth = 0
    while current is not None and depth < 10:
        try:
            parts.insert(0, current.name)
            current = current.parentFolder
        except Exception:
            break
        depth += 1
    return " > ".join(parts)


def native_recents_path() -> str:
    """Resolve Fusion's own recents file for the active user and hub, or "".

    Supplies ``fusion_recents`` (which is deliberately ``adsk``-free) with the
    live values it cannot look up itself. ``DataHub.fusionWebURL`` is the primary
    signal because the hub's site name is what Fusion uses to name the file;
    ``DataHub.id`` is a fallback for hubs whose URL is unavailable.

    Nothing consumes the parsed list yet — this exists so ``log_native_recents``
    can report where resolution lands on platforms not yet verified.
    """
    hub_url = ""
    hub_id = ""
    try:
        hub = app.data.activeHub
        # str() so fusion_recents only ever sees the plain strings it is typed
        # for, whatever shape the API hands back.
        hub_url = str(getattr(hub, "fusionWebURL", "") or "")
        hub_id = str(getattr(hub, "id", "") or getattr(hub, "hubId", "") or "")
    except Exception:
        pass  # signed out, offline, or the data layer is not up yet
    try:
        user_id = str(app.userId or "")
    except Exception:
        user_id = ""
    try:
        return fusion_recents.resolve_recents_path(
            hub_url=hub_url, hub_id=hub_id, user_id=user_id
        )
    except Exception:
        return ""


def log_native_recents() -> None:
    """DEBUG-only: log where Fusion's own recents file resolved to, once.

    The macOS layout is verified; the Windows one is not. Dropping a ``.debug``
    marker in the add-in root and opening a document writes the full resolution
    trace to ``cache/powertools-debug.log`` — every root probed, every candidate
    kept or rejected and why, and the entry count of the winner. That is enough
    to pin down an unverified layout without a debugger.

    Entirely inert when DEBUG is off, which is how it ships.
    """
    global _native_logged
    if _native_logged:
        return
    try:
        # Imported here, not at module scope: config.py imports ptAddInUtils
        # before defining its flags, so a module-level read would capture a
        # half-initialized module (see the CAUTION in general_utils). By the time
        # a document is activated, config is complete.
        from ... import config

        if not config.DEBUG:
            return
    except Exception:
        return
    _native_logged = True
    try:
        path = native_recents_path()
        designs = fusion_recents.list_native_recents(path) if path else []
        every = (
            fusion_recents.list_native_recents(path, file_types=None) if path else []
        )
        lines = fusion_recents.resolution_trace()
        lines.append(f"native recents: {len(designs)} designs of {len(every)} entries")
        ptutil.log("recents: native resolution\n  " + "\n  ".join(lines))
    except Exception as exc:
        ptutil.log(f"recents: native resolution failed — {exc}")


def remember_recent_if_eligible(doc) -> None:
    """Record *doc* in the recents cache and pre-warm its thumbnail.

    A no-op unless *doc* is a saved part/hybrid/assembly document. Called from
    both commands' ``documentActivated`` handlers so the cache and thumbnail
    store grow as the user works, regardless of which command is enabled.
    """
    log_native_recents()
    try:
        if doc is None or not doc.isSaved:
            return
        name_of_intent = intent_name(design_intent(doc))
        if name_of_intent not in DESIGN_INTENTS:
            return
        df = getattr(doc, "dataFile", None)
        if df is None:
            return
        df_id = getattr(df, "id", "")
        try:
            location = folder_lineage(getattr(df, "parentFolder", None))
        except Exception:
            location = ""
        touch_recent(df_id, getattr(df, "name", ""), name_of_intent, location)
        # Render + cache now, while the document is open — the only time we can.
        render_thumbnail_for_doc(doc, df_id)
    except Exception:
        pass


def _native_recents(file_types=("f3d",)) -> list[dict]:
    """Fusion's own recents list, memoized on the file's identity and mtime.

    Both surfaces rebuild on every ``documentActivated`` — which fires on each tab
    switch — so re-parsing a few hundred KB per call is not affordable. The
    ``stat`` is microseconds and Fusion rewrites the file live as documents open,
    so mtime plus size is a sufficient invalidation key. The resolved path is
    re-checked when the active hub changes, since each hub has its own file.
    """
    global _native_cache
    try:
        hub_url = str(getattr(app.data.activeHub, "fusionWebURL", "") or "")
    except Exception:
        hub_url = ""
    cached = _native_cache
    path = cached.get("path", "")
    if not path or cached.get("hub") != hub_url:
        path = native_recents_path()
    try:
        stamp = os.stat(path) if path else None
        stamp_key = (stamp.st_mtime_ns, stamp.st_size) if stamp else None
    except OSError:
        stamp_key = None
    if (
        path == cached.get("path")
        and stamp_key == cached.get("stamp")
        and file_types == cached.get("types")
        and cached.get("hub") == hub_url
    ):
        return cached["entries"]
    entries = (
        fusion_recents.list_native_recents(path, file_types=file_types) if path else []
    )
    _native_cache = {
        "path": path,
        "hub": hub_url,
        "stamp": stamp_key,
        "types": file_types,
        "entries": entries,
    }
    return entries


def list_recent(
    exclude_ids=None, limit: int | None = None, *, file_types=("f3d",)
) -> list[dict]:
    """Return recents newest-first, deduped by DataFile id.

    Each item is ``{dataFileId, name, intent, location, thumbPath, version}``
    where ``thumbPath`` is a cached PNG path (for a tooltip tool-clip) or "".

    Fusion's own recents list is the source of the entries and their order — it
    covers hundreds of documents with real timestamps, including ones opened
    before this add-in was installed. Our cache is overlaid on top because it
    holds the two things Fusion's file lacks: the design intent for the ~25% of
    designs whose ``docstruct`` is empty (permanently — Fusion never backfills
    it), and the thumbnail. With no native list available (unsupported platform,
    signed out, or an unreadable file) this falls back to our cache alone.

    Args:
        exclude_ids: DataFile ids to omit (e.g. the active document).
        limit: Maximum number of items to return (None → all).
        file_types: Fusion file extensions to include, or None for every type.
            Defaults to designs only, which is what can be inserted as a
            component; the Open Recent flyout passes None so it also lists
            drawings.
    """
    exclude = set(exclude_ids or ())
    native = _native_recents(file_types)
    if not native:
        return _list_recent_from_cache(exclude, limit)

    memo = {e.get("dataFileId", ""): e for e in read_recent_cache()}
    out: list[dict] = []
    for entry in native:
        df_id = entry["dataFileId"]
        if df_id in exclude:
            continue
        prev = memo.get(df_id, {})
        out.append(
            {
                "dataFileId": df_id,
                "name": entry["name"] or prev.get("name", ""),
                "intent": entry["intent"] or prev.get("intent", ""),
                "location": entry["location"] or prev.get("location", ""),
                "thumbPath": cached_thumbnail_path(df_id),
                "version": entry["version"],
            }
        )
        if limit and len(out) >= limit:
            break
    return out


def _list_recent_from_cache(exclude: set, limit: int | None) -> list[dict]:
    """Fallback list built only from our own cache (oldest-first on disk)."""
    out: list[dict] = []
    seen: set[str] = set()
    for entry in reversed(read_recent_cache()):
        df_id = entry.get("dataFileId", "")
        if not df_id or df_id in seen or df_id in exclude:
            continue
        seen.add(df_id)
        out.append(
            {
                "dataFileId": df_id,
                "name": entry.get("name", ""),
                "intent": entry.get("intent", ""),
                "location": entry.get("location", ""),
                "thumbPath": cached_thumbnail_path(df_id),
                "version": "",
            }
        )
        if limit and len(out) >= limit:
            break
    return out
