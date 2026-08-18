# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Reader for Fusion's own "recent documents" list.

Every signed-in Fusion user already has a recents list that Fusion maintains on
disk and rewrites live as documents are opened. It is richer than the cache
PowerTools keeps for itself (``recents_utils``): hundreds of entries instead of a
couple of dozen, real ``lastOpened`` timestamps, the Data Panel location for
free, and — in ``docstruct`` — the design intent, without opening the document.
It carries no thumbnails, which stay ``recents_utils``' job.

The file lives at::

    <options root>/<userId>/<hubPrefix>_RecentsWithoutSearch_1.json

Both path segments have to be *discovered*, not assumed:

* Several ``<userId>`` directories coexist on a machine that has signed in as
  more than one account, and stale ones look identical to the live one. The
  directory name matches ``LastUserHubUserId`` in that directory's
  ``NUserMachineSpecificOptions.xml`` (a UTF-16 file) — but Fusion's
  ``Application.userId`` is documented as returning the account's *internal
  name*, which for some accounts is not that value at all. So the user id is a
  tiebreaker here, never the lookup key.
* ``<hubPrefix>`` is the hub's site name (``imallc`` for
  ``https://imallc.autodesk360.com``), and one directory holds a sibling file per
  hub the user has visited. Only the active hub's file is usable — entries from
  another hub would fail ``Data.findFileById``.

Resolution is therefore hub-first and validated: glob the active hub's prefix
across every user directory, confirm each candidate's ``qontextServer`` really
does name that hub, then prefer a directory that matches the signed-in user and
fall back to the most recently written file. Every step degrades to "" so a
caller can fall back to the PowerTools cache; see ``resolution_trace`` for a
DEBUG-time account of which branch was taken.

This module deliberately depends only on the standard library (no ``adsk``) —
every Fusion-derived input is passed in — so all of it is unit-testable outside
the Fusion runtime. Follows the same "never hardcode an Autodesk path" rule as
``commands/changecyclecolor/fusion_install.py``: candidate roots are probed.
"""

import base64
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

# Design intents this reader recognizes. Mirrors recents_utils.DESIGN_INTENTS;
# that module cannot be imported here because it pulls in ``adsk``.
DESIGN_INTENTS = ("part", "hybrid", "assembly")

# Path from a platform's application-data directory down to Fusion's options.
_OPTIONS_REL = os.path.join("Autodesk", "Neutron Platform", "Options")


def _root_candidates(platform: str, environ, home: str) -> tuple[str, ...]:
    """Options-root candidates for *platform*, most likely first.

    Both layouts are confirmed:

    * macOS   ``~/Library/Application Support/Autodesk/Neutron Platform/Options``
    * Windows ``%APPDATA%\\Autodesk\\Neutron Platform\\Options`` — i.e.
      ``C:\\Users\\<user>\\AppData\\Roaming\\Autodesk\\…``, since ``%APPDATA%``
      already ends in ``Roaming``. The expanded home form is kept as a second
      candidate for the rare case where ``APPDATA`` is not set in the
      environment Fusion hands to the add-in.

    Taking the platform and environment as arguments keeps this pure, so the
    Windows layout is verifiable from a macOS test run rather than only on
    Windows. Fusion does not ship for other platforms, so they get no candidates
    and every caller degrades to the PowerTools cache.
    """
    if platform == "darwin":
        return (os.path.join(home, "Library", "Application Support", _OPTIONS_REL),)
    if platform == "win32":
        bases = (environ.get("APPDATA", ""), os.path.join(home, "AppData", "Roaming"))
        out: list[str] = []
        keys = set()
        for base in bases:
            if not base:
                continue
            candidate = os.path.join(base, _OPTIONS_REL)
            # Deduped on a lexical key rather than the raw string: the two bases
            # normally name the same directory, but may differ in separator or
            # casing (and os.path cannot normalize a Windows path from a POSIX
            # host, which is how the tests exercise this branch).
            key = candidate.replace("\\", "/").rstrip("/").lower()
            if key not in keys:
                keys.add(key)
                out.append(candidate)
        return tuple(out)
    return ()


OPTIONS_ROOT_CANDIDATES = _root_candidates(
    sys.platform, os.environ, os.path.expanduser("~")
)

# Recents filenames are "<hubPrefix>_RecentsWithoutSearch_<n>.json".
RECENTS_SUFFIX_GLOB = "_RecentsWithoutSearch_*.json"
RECENTS_GLOB = "*" + RECENTS_SUFFIX_GLOB

# Per-user-directory options file naming the hub and user that directory belongs
# to. UTF-16 encoded, hence the byte-level read in read_user_hub_options.
USER_XML_NAME = "NUserMachineSpecificOptions.xml"

# A signed-out session gets its own directory that never holds a usable list.
_SKIP_DIR_NAMES = ("UnknownUser",)

# Bytes read from the head of a candidate file to identify its hub. The first
# entry's ``qontextServer`` sits ~500 bytes in, so this never needs the whole
# file (they run to several hundred KB).
_HEAD_BYTES = 8192

_QONTEXT_RE = re.compile(rb'"qontextServer"\s*:\s*"([^"]*)"')
_EMPTY_FILES_RE = re.compile(rb'"files"\s*:\s*\[\s*\]')

# Populated by resolve_recents_path for DEBUG logging; see resolution_trace.
_TRACE: list[str] = []


def resolution_trace() -> list[str]:
    """Return the step-by-step account of the last ``resolve_recents_path`` call.

    Intended for a DEBUG-gated log line: it names every root probed, every
    candidate considered and why it was kept or rejected, and the final choice.
    That is enough to diagnose an unverified platform layout from a single log.
    """
    return list(_TRACE)


def _trace(message: str) -> None:
    _TRACE.append(message)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def options_root() -> str:
    """Return Fusion's options directory, or "" when none of the candidates exist."""
    for candidate in OPTIONS_ROOT_CANDIDATES:
        if candidate and os.path.isdir(candidate):
            return candidate
    return ""


def read_user_hub_options(user_dir: str) -> dict:
    """Parse a user directory's ``NUserMachineSpecificOptions.xml``.

    The file is UTF-16 and shaped as a flat list of elements carrying a ``Value``
    attribute, so every ``<Tag Value="…"/>`` is collected and the interesting
    ones are surfaced under friendlier names. Returns {} on any failure — a
    missing or unreadable file just means this directory cannot be identified.

    Returns:
        Dict with any of ``userId``, ``hubUrlWip``, ``hubName``, ``edition`` and
        ``regionId`` that the file provided.
    """
    path = os.path.join(user_dir, USER_XML_NAME)
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return {}
    try:
        # ElementTree honours the XML declaration's encoding when handed bytes,
        # which is what makes the UTF-16 payload readable without decoding first.
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {}
    values = {
        element.tag: element.attrib["Value"]
        for element in root.iter()
        if "Value" in element.attrib
    }
    out = {}
    for key, tag in (
        ("userId", "LastUserHubUserId"),
        ("hubUrlWip", "LastUserHubUrlWip"),
        ("hubName", "LastUserHubName"),
        ("edition", "LastUserHubEdition"),
        ("regionId", "LastUserHubRegionId"),
    ):
        if values.get(tag):
            out[key] = values[tag]
    return out


def hub_prefix_from_web_url(url: str) -> str:
    """Return the hub site name from a hub URL, e.g. "imallc".

    ``https://imallc.autodesk360.com`` -> ``imallc``. This is the primary signal:
    ``DataHub.fusionWebURL`` supplies it live, and it is exactly the string
    Fusion uses to name the recents file and to fill each entry's
    ``qontextServer``.
    """
    if not url:
        return ""
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    label = host.split(".", 1)[0].strip().lower()
    return label


def hub_prefix_from_hub_id(hub_id: str) -> str:
    """Derive the hub site name from a ``DataHub.id``, or "" if it does not encode one.

    Team hub ids are ``a.<base64>`` where the payload is ``<edition>:<site>`` —
    ``a.YnVzaW5lc3M6aW1hbGxj`` decodes to ``business:imallc`` -> ``imallc``. This
    is only a fallback for ``hub_prefix_from_web_url``: the API documents
    ``a.45637`` as a valid id shape, which encodes no site name, so a "" result
    is an ordinary outcome rather than an error.
    """
    if not hub_id:
        return ""
    payload = hub_id.split(".", 1)[-1]
    if not payload:
        return ""
    try:
        decoded = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return ""
    if ":" not in decoded or not decoded.isprintable():
        return ""
    return decoded.rsplit(":", 1)[-1].strip().lower()


def _read_head(path: str) -> bytes | None:
    """Return the first ``_HEAD_BYTES`` of *path*, or None if it cannot be read.

    Never holds the handle open: Fusion rewrites these files in place while it
    runs, and at least one sibling file has been observed mode 0o400.
    """
    try:
        with open(path, "rb") as handle:
            return handle.read(_HEAD_BYTES)
    except OSError:
        return None


def _site_of(head: bytes) -> str:
    """Hub site name named by the first ``qontextServer`` in a file's head, or ""."""
    match = _QONTEXT_RE.search(head)
    return (
        hub_prefix_from_web_url(match.group(1).decode("utf-8", "replace"))
        if match
        else ""
    )


def _dir_matches_user(user_dir: str, user_id: str) -> bool:
    """Whether *user_dir* belongs to *user_id*.

    Checks the directory name first (the observed invariant) and then the
    directory's own options file, because ``Application.userId`` may report an
    internal account name where the directory is named with a numeric id.
    """
    if not user_id:
        return False
    if os.path.basename(user_dir.rstrip(os.sep)) == user_id:
        return True
    return read_user_hub_options(user_dir).get("userId", "") == user_id


def _candidate_paths(root: str, prefix: str) -> list[str]:
    """Recents files under *root*, the active hub's prefix first, then all hubs."""
    patterns = []
    if prefix:
        patterns.append(os.path.join(root, "*", prefix + RECENTS_SUFFIX_GLOB))
    patterns.append(os.path.join(root, "*", RECENTS_GLOB))
    out: list[str] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            parent = os.path.basename(os.path.dirname(path))
            if parent in _SKIP_DIR_NAMES:
                continue
            if path not in out:
                out.append(path)
    return out


def resolve_recents_path(
    *, hub_url: str = "", hub_id: str = "", user_id: str = ""
) -> str:
    """Locate the active hub's recents file, or "" when there is none to read.

    Args:
        hub_url: ``DataHub.fusionWebURL`` for the active hub. The primary signal.
        hub_id: ``DataHub.id``, used only if *hub_url* yields no prefix.
        user_id: ``Application.userId``, used only to break a tie between two
            equally-recent directories holding a file for this hub.

    Returns:
        Absolute path to the best candidate, or "" if nothing usable was found.
    """
    _TRACE.clear()
    root = options_root()
    _trace(f"options root: {root or '(none of the candidates exist)'}")
    if not root:
        _trace(f"probed: {list(OPTIONS_ROOT_CANDIDATES)}")
        return ""

    prefix = hub_prefix_from_web_url(hub_url) or hub_prefix_from_hub_id(hub_id)
    _trace(f"hub prefix: {prefix or '(unknown)'} (url={hub_url!r} id={hub_id!r})")
    _trace(f"user id: {user_id or '(unknown)'}")

    scored: list[tuple[int, int, float, str]] = []
    for path in _candidate_paths(root, prefix):
        head = _read_head(path)
        if head is None:
            _trace(f"  reject {path}: unreadable")
            continue
        if _EMPTY_FILES_RE.search(head):
            # A placeholder Fusion leaves for a hub with no history. Skipping it
            # keeps an empty stub from outranking a real list on mtime alone.
            _trace(f"  reject {path}: empty stub")
            continue
        site = _site_of(head)
        if prefix and site and site != prefix:
            _trace(f"  reject {path}: belongs to hub {site!r}")
            continue
        hub_ok = bool(prefix) and site == prefix
        user_ok = _dir_matches_user(os.path.dirname(path), user_id)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            _trace(f"  reject {path}: cannot stat")
            continue
        _trace(f"  keep   {path}: hub={hub_ok} user={user_ok} mtime={mtime:.0f}")
        scored.append((int(hub_ok), mtime, int(user_ok), path))

    if not scored:
        _trace("no usable candidate")
        return ""
    # Confirmed hub, then recency, then a matching user directory. Recency
    # outranks the user match deliberately: one machine here has two directories
    # whose options files both name the same hub, so they are plausibly the same
    # person under two directory-keying schemes. Fusion rewrites the live file
    # continuously, so a directory it has not touched in weeks is not the active
    # one whatever its recorded user id says — while ``Application.userId``
    # returns an *internal account name* that may well match the stale one. The
    # user match therefore only breaks a tie between equally-recent candidates.
    scored.sort()
    chosen = scored[-1][-1]
    _trace(f"chosen: {chosen}")
    return chosen


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_recents(path: str) -> list[dict]:
    """Return the raw ``files`` array from a recents file, or [] on any failure.

    Missing, truncated and unparseable files are all "" -> [] so callers can
    treat them identically, matching ``json_utils.read_json``'s contract. Fusion
    may replace this file while we read it, so one retry is allowed.
    """
    if not path:
        return []
    for attempt in (0, 1):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            break
        except OSError:
            if attempt:
                return []
        except ValueError:
            return []
    else:  # pragma: no cover - the loop always breaks or returns
        return []
    if not isinstance(payload, dict):
        return []
    files = payload.get("files")
    return files if isinstance(files, list) else []


def intent_from_docstruct(raw: str) -> str:
    """Map an entry's ``docstruct`` to "part" / "hybrid" / "assembly", or "".

    ``docstruct`` is normally a JSON string whose ``type`` is ``<intent>-<flavour>``
    (``part-design``, ``assembly-standard``), but a bare token such as
    ``assembly-experience`` also occurs. Taking the segment before the first
    hyphen and accepting it only when it names a known intent handles both, and
    tolerates flavours Fusion has not shipped yet.

    Roughly a quarter of designs carry an empty ``docstruct``, and comparing
    files a month apart shows it is never backfilled — so "" is a permanent
    answer for those documents, not a not-yet.
    """
    if not raw:
        return ""
    text = raw
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        pass  # a bare token rather than a JSON object
    else:
        if isinstance(parsed, dict):
            text = str(parsed.get("type", ""))
    head = text.split("-", 1)[0].strip().lower()
    return head if head in DESIGN_INTENTS else ""


def normalize_entry(entry: dict, file_types=("f3d",)) -> dict | None:
    """Convert one native entry to the shape ``recents_utils`` deals in, or None.

    None means "skip this entry": no lineage id, an unwanted ``fileType``, or an
    unparseable ``lastOpened``. Pass ``file_types=None`` to accept every type
    (the Open Recent flyout lists drawings too; the Assembly Palette gallery inserts
    components and so takes designs only).

    ``location`` is re-punctuated from Fusion's ``A/B`` to the ``A > B`` form the
    add-in already displays; that costs a cloud round-trip to derive ourselves.
    """
    if not isinstance(entry, dict):
        return None
    df_id = str(entry.get("id") or "").strip()
    if not df_id:
        return None
    if file_types is not None and entry.get("fileType") not in file_types:
        return None
    try:
        last_opened = int(entry.get("lastOpened") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "dataFileId": df_id,
        "name": str(entry.get("name") or ""),
        "intent": intent_from_docstruct(str(entry.get("docstruct") or "")),
        "location": str(entry.get("location") or "").replace("/", " > "),
        "lastOpened": last_opened,
        "version": str(entry.get("version") or ""),
        "versionUrn": str(entry.get("versionUrn") or ""),
        "fileType": str(entry.get("fileType") or ""),
    }


def list_native_recents(path: str, *, file_types=("f3d",), limit=None) -> list[dict]:
    """Read *path* and return normalized entries, newest first.

    The stored order is *nearly* newest-first but not reliably so — inversions
    occur, including inside the first few dozen entries — so the sort is
    explicit rather than inherited from the file.
    """
    out = []
    seen = set()
    for entry in parse_recents(path):
        item = normalize_entry(entry, file_types)
        if item is None or item["dataFileId"] in seen:
            continue
        seen.add(item["dataFileId"])
        out.append(item)
    out.sort(key=lambda item: item["lastOpened"], reverse=True)
    return out[:limit] if limit else out
