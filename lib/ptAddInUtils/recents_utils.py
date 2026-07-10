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

from . import general_utils as ptutil
from .cache_utils import CACHE_FOLDER

app = adsk.core.Application.get()

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

# Cap on how many entries the cache retains (newest kept).
RECENT_LIMIT = 24

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
    """Persist *entries* (only the newest RECENT_LIMIT are kept)."""
    try:
        os.makedirs(os.path.dirname(RECENT_CACHE_PATH), exist_ok=True)
        with open(RECENT_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(entries[-RECENT_LIMIT:], fh, indent=2)
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
        write_recent_cache(
            touch_entries(read_recent_cache(), df_id, name, intent_name_str, location)
        )
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


def remember_recent_if_eligible(doc) -> None:
    """Record *doc* in the recents cache and pre-warm its thumbnail.

    A no-op unless *doc* is a saved part/hybrid/assembly document. Called from
    both commands' ``documentActivated`` handlers so the cache and thumbnail
    store grow as the user works, regardless of which command is enabled.
    """
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


def list_recent(exclude_ids=None, limit: int | None = None) -> list[dict]:
    """Return recents newest-first, deduped by DataFile id.

    Each item is ``{dataFileId, name, intent, location, thumbPath}`` where
    ``thumbPath`` is a cached PNG path (for a tooltip tool-clip) or "".

    Args:
        exclude_ids: DataFile ids to omit (e.g. the active document).
        limit: Maximum number of items to return (None → all, up to the cache).
    """
    exclude = set(exclude_ids or ())
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
            }
        )
        if limit and len(out) >= limit:
            break
    return out
