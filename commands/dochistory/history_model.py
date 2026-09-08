# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Bucketing for the Document History palette. Pure - no ``adsk``, no I/O.

``entry.py`` reads the version records out of Fusion and hands them here; this
module turns that flat list into the day rows the page draws, and nothing else.
The split follows the repo rule that anything capable of producing a plausible
wrong number lives in an ``adsk``-free module with tests.

The view is a stack of day rows, newest at the top. Inside a row each author
gets a track, and the dots sit on one of two x mappings:

  * Day view (default) - x is the clock: 00:00 at the left edge, 24:00 at the
    right, the same scale in every row, so noon is the same column all the way
    down and one day's shape is comparable to the day above it.
  * Thread view (checkbox) - x is the version's position in the whole history,
    one column pitch apart, so empty time costs no width and consecutive saves
    can be threaded with a polyline across rows.

Only the *bucketing* is here. The width-dependent geometry (declutter, hour
ticks, the two x mappings, the stack's y offsets) lives in
``resources/html/app.js`` because it needs the panel width the browser
measures; sending a width to Python and a layout back on every resize would
put a round trip in the middle of a drag.

Days are LOCAL calendar days: a 23:30 save must stay on the day the author saw
on their own clock, not the UTC day it lands in east of Greenwich.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timezone

# Above this many authors in one day, the tail merges into a single overflow
# track. Nothing is hidden - every dot still renders and still carries its own
# author in its hover card - only the row height is bounded.
TRACKS_PER_DAY_CAP = 6

# Fusion writes a milestone for its own reasons as well as the user's, and the
# auto-generated ones are named to a pattern ("Milestone V7", "Item Update").
# A milestone named anything else is a revision the user typed - what the
# History view draws as a release. Same rule as commands/versiondiff.
AUTO_MILESTONE_PREFIXES = ("Milestone ", "Item Update")


# ---------------------------------------------------------------------------
# Merging the two halves of a cloud history
# ---------------------------------------------------------------------------


def person_name(user: dict | None) -> str:
    """Render an MFGDM ``User`` as a display name.

    Args:
        user: The GraphQL ``User`` object, or None.

    Returns:
        "First Last" where both are present, else whichever exists, else the
        account name, else "".
    """
    if not user:
        return ""
    full = " ".join(
        part for part in (user.get("firstName"), user.get("lastName")) if part
    ).strip()
    return full or user.get("userName") or ""


def merge_cloud_history(versions: list[dict], writes: list[dict]) -> list[dict]:
    """Combine MFGDM's two views of a history into version records.

    The authorship lives in one place and the save comment in another:

    * ``DesignItemVersion`` carries ``versionNumber``, ``createdOn`` and
      ``createdBy`` - the identity of each version, and the only per-version
      author Fusion exposes anywhere.
    * ``ModelWrittenHistoryChange`` carries the ``description`` the author
      typed at save time. ``DesignItemVersion.description`` exists but comes
      back empty.

    The two lists are matched **by position**, newest first, not by timestamp:
    the same save is stamped up to 35 seconds apart in the two views, so a
    timestamp join would mismatch. Position is only trusted when the two lists
    are the same length. When they are not, every version keeps its author and
    date and simply has no comment - a save wearing the wrong person's comment
    is worse than a save with none.

    Args:
        versions: ``DesignItemVersion`` rows, newest first.
        writes: ``ModelWrittenHistoryChange`` rows, newest first.

    Returns:
        Version records in the shape :func:`bucket_by_day` consumes.
    """
    comments: list[str] = []
    if len(writes) == len(versions):
        comments = [(write.get("description") or "") for write in writes]

    records = []
    for index, row in enumerate(versions):
        number = row.get("versionNumber")
        if number is None:
            continue
        user = row.get("createdBy") or {}
        records.append(
            {
                "number": int(number),
                "createdOnMs": iso_to_epoch_ms(row.get("createdOn")),
                "createdBy": person_name(user),
                "createdById": user.get("id") or "",
                "comment": comments[index] if index < len(comments) else "",
                "isMilestone": False,
                "revision": "",
                "publicShare": False,
                "versionId": str(int(number)),
            }
        )
    return records


# MFGDM's history carries more than saves. These are the other change types it
# has been observed to return, mapped to what a reader should see. The raw
# names are GraphQL ``__typename`` values, and an unmapped one falls back to a
# de-camel-cased form rather than being dropped: the schema has ten change
# types and only the ones a test design happened to produce are pinned here.
CHANGE_LABELS = {
    "PropertiesUpdatedHistoryChange": "Property change",
    "ComponentPrimaryHistoryChange": "Component change",
    "ComponentPartNumberHistoryChange": "Part number change",
    "ModelComponentHistoryChange": "Component update",
    "VersionCreatedHistoryChange": "Milestone",
    "RevisionCreatedHistoryChange": "Release",
    "MarkerHistoryChange": "Marker",
    "DrawingItemWrittenHistoryChange": "Drawing saved",
    "BasicItemWrittenHistoryChange": "File saved",
}

# Releases and milestones arrive twice: once here, as the audit-trail entry for
# the act of creating one, and once as the decoration DataFile.milestones puts on
# the save it was created against (entry._decorate_cloud_records). The save dot
# is the one that carries the version number, the ring and the revision name, so
# these rows are dropped rather than drawn a second time as a bare change.
DUPLICATE_CHANGE_TYPES = frozenset(
    {"RevisionCreatedHistoryChange", "VersionCreatedHistoryChange"}
)


def change_label(typename: str) -> str:
    """Render a ``HistoryChange`` type name as something a reader can use.

    Args:
        typename: The GraphQL ``__typename``.

    Returns:
        A mapped label, or the type name split on its capitals with the
        "HistoryChange" suffix dropped. An unmapped type still says something
        truthful rather than vanishing from the history.
    """
    known = CHANGE_LABELS.get(typename)
    if known:
        return known
    stem = (
        typename[: -len("HistoryChange")]
        if typename.endswith("HistoryChange")
        else typename
    )
    words = re.findall(r"[A-Z][a-z0-9]*|[A-Z]+(?![a-z])", stem)
    return " ".join(words) if words else (stem or "Change")


def change_records(rows: list[dict]) -> list[dict]:
    """Turn non-save history entries into records the day rows can carry.

    These are edits that did not produce a version - a property changed, a
    milestone marked, a part number set. They have an author and an instant but
    no version number, no description of their own beyond what the change was,
    and nothing to show a thumbnail of.

    They matter because a design's history is not only its saves: on the test
    document two of the nine people who touched it never saved a version, so a
    saves-only view credits the design to eight.

    Args:
        rows: ``HistoryChange`` rows other than the save event, each with
            ``__typename``, ``timestamp``, ``description`` and ``author``.

    Returns:
        Records in the shape :func:`bucket_by_day` consumes, marked
        ``kind == "change"`` so the page can draw them as the lighter thing
        they are. Rows in :data:`DUPLICATE_CHANGE_TYPES` are dropped - the
        release or milestone they record is already drawn on its save dot.
    """
    records = []
    for row in rows:
        if (row.get("__typename") or "") in DUPLICATE_CHANGE_TYPES:
            continue
        user = row.get("author") or {}
        records.append(
            {
                "kind": "change",
                "number": None,
                "changeLabel": change_label(row.get("__typename") or ""),
                "createdOnMs": iso_to_epoch_ms(row.get("timestamp")),
                "createdBy": person_name(user),
                "createdById": user.get("id") or "",
                "comment": row.get("description") or "",
                "isMilestone": False,
                "revision": "",
                "publicShare": False,
                "versionId": "",
            }
        )
    return records


def iso_to_epoch_ms(stamp: str | None) -> int | None:
    """Parse an RFC 3339 / ISO 8601 UTC timestamp into epoch milliseconds.

    MFGDM returns "2025-07-28T21:13:34.000Z". Python's ``fromisoformat`` did
    not accept a trailing "Z" before 3.11 and this add-in has to keep working
    if Fusion's bundled interpreter is ever older than the one it ships today,
    so the suffix is normalised rather than assumed.

    Args:
        stamp: The timestamp string, or None.

    Returns:
        Epoch milliseconds, or None when there is nothing usable to parse -
        which puts the version in the undated bucket rather than dropping it.
    """
    if not stamp:
        return None
    text = stamp.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Milestones and releases
# ---------------------------------------------------------------------------


def is_release_name(name: str) -> bool:
    """Report whether a milestone name is a user-typed revision.

    Args:
        name: The ``Milestone.name`` as Fusion returned it.

    Returns:
        True for a revision label the user chose ("A", "Rev B", "Prototype"),
        False for an empty name or one of Fusion's auto-generated milestones.
    """
    if not name:
        return False
    return not any(name.startswith(prefix) for prefix in AUTO_MILESTONE_PREFIXES)


def stamp_index_labels(versions: list[dict]) -> None:
    """Write an ``indexLabel`` semantic version onto every record, in place.

    A release bumps major, a save or a milestone bumps minor, and an edit that
    made no version bumps patch - each resetting what sits below it, as a
    version number should. Counting starts at 0.0.0, so a document's first save
    is 0.1.0 and the first release someone names is 1.0.0.

    The resetting is what makes the label survive the "Show other changes"
    toggle. A save's label depends only on the releases and the saves before it,
    never on how many no-version edits were interleaved, so ticking that box adds
    patch labels beside the rings without renumbering a single save dot. That
    matters because ``entry`` buckets twice, once with the changes and once
    without, and both stacks share these record dicts - see
    ``test_save_labels_do_not_move_when_the_changes_are_included``.

    Args:
        versions: Save and change records in any order. Mutated in place: each
            gains ``indexLabel``. Ordering is :func:`_ordered_oldest_first`, the
            same order that gives a dot its thread-axis ``index``, so a label and
            a position can never disagree.
    """
    major = minor = patch = 0
    for record in _ordered_oldest_first(versions):
        if record.get("kind") == "change":
            patch += 1
        elif record.get("revision"):
            # A user-typed revision name is what this view draws as a release.
            major += 1
            minor = patch = 0
        else:
            # Saves and milestones alike: a milestone is a save someone marked,
            # not a step of its own.
            minor += 1
            patch = 0
        record["indexLabel"] = f"{major}.{minor}.{patch}"


# ---------------------------------------------------------------------------
# Calendar-day arithmetic
# ---------------------------------------------------------------------------


def parse_day(day: str) -> date | None:
    """Read a ``YYYY-MM-DD`` day string.

    Args:
        day: The day string, or "" for the undated bucket.

    Returns:
        The date, or None if *day* is empty or malformed.
    """
    if not day:
        return None
    try:
        return date.fromisoformat(day)
    except ValueError:
        return None


def days_between(older: date, newer: date) -> int:
    """Count whole calendar days from *older* to *newer*."""
    return (newer - older).days


def add_months(anchor: date, months: int) -> date:
    """Advance *anchor* by *months*, clamping to the target month's length.

    31 January plus one month is 28/29 February, not 3 March. The clamp is what
    makes :func:`calendar_breakdown` call that span "1 month".
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last))


def calendar_breakdown(older: date, newer: date) -> dict:
    """Split the span between two days into calendar years, months and days.

    This is the shape the between-day labels render ("1 year, 2 months and 3
    days later"). It walks the anchor forward with :func:`add_months` rather
    than subtracting date fields, so it inherits that function's end-of-month
    clamp.

    Args:
        older: The earlier day.
        newer: The later day. Swapped with *older* if the two are reversed.

    Returns:
        A ``{"years": int, "months": int, "days": int}`` mapping.
    """
    if newer < older:
        older, newer = newer, older
    months = (newer.year - older.year) * 12 + (newer.month - older.month)
    if add_months(older, months) > newer:
        months -= 1
    days = days_between(add_months(older, months), newer)
    return {"years": months // 12, "months": months % 12, "days": days}


def gap_between(newer_row: dict, older_row: dict) -> dict | None:
    """Describe the elapsed time from the older day row to the newer one.

    Args:
        newer_row: The row above (later day).
        older_row: The row below (earlier day).

    Returns:
        A ``{"tier", "days", "breakdown"}`` mapping, or None when there is
        nothing to say - the same day, or either side being the undated bucket.
    """
    newer = parse_day(newer_row.get("day", ""))
    older = parse_day(older_row.get("day", ""))
    if newer is None or older is None:
        return None
    days = days_between(older, newer)
    if days <= 0:
        return None
    tier = "nextDay" if days == 1 else "days" if days < 7 else "wide"
    return {"tier": tier, "days": days, "breakdown": calendar_breakdown(older, newer)}


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


def author_key(version: dict) -> str:
    """Return the key that groups a version onto a track.

    The Autodesk user id is preferred so two people who share a display name
    stay apart and a rename does not split one person into two tracks; the
    display name is the fallback for versions whose author id Fusion did not
    resolve.
    """
    return version.get("createdById") or version.get("createdBy") or ""


def _local_stamp(version: dict) -> tuple[str, int] | None:
    """Split a version's timestamp into its local day and time of day.

    Args:
        version: A version record; ``createdOnMs`` is epoch milliseconds.

    Returns:
        ``(day, ms_since_local_midnight)``, or None for a version with no
        usable timestamp - which is bucketed rather than dropped.
    """
    raw = version.get("createdOnMs")
    if not raw:
        return None
    try:
        moment = datetime.fromtimestamp(raw / 1000.0)
    except (OSError, OverflowError, ValueError, TypeError):
        return None
    ms = (
        moment.hour * 3_600_000
        + moment.minute * 60_000
        + moment.second * 1000
        + moment.microsecond // 1000
    )
    return moment.strftime("%Y-%m-%d"), ms


def _ordered_oldest_first(versions: list[dict]) -> list[dict]:
    """Order records oldest to newest, undated last in their input order.

    This is the history's one canonical order. :func:`bucket_by_day` numbers a
    dot's thread-axis ``index`` from it and :func:`stamp_index_labels` counts
    along it, so they are kept in one place: a label that disagreed with a
    position would be a plausible wrong answer, which is the kind this module
    exists to prevent.

    Args:
        versions: Records in any order. ``createdOnMs`` is epoch milliseconds;
            a record without one is undated.

    Returns:
        A new list; the input is not reordered. The sort is stable, so undated
        records keep the order they arrived in.
    """
    stamped = [(version, _local_stamp(version)) for version in versions]
    ordered = sorted(
        stamped,
        key=lambda pair: (1, 0) if pair[1] is None else (0, pair[0]["createdOnMs"]),
    )
    return [version for version, _ in ordered]


def tracks_for_day(dots: list[dict]) -> list[dict]:
    """Split one day's dots into per-author tracks, ordered by who saved first.

    Ordering by first save rather than by volume keeps a person's slot stable
    within the day; a globally fixed slot per person was rejected because a day
    with one of five authors would then reserve four empty tracks.

    Args:
        dots: The day's dots, each ``{"v", "index", "ms"}``.

    Returns:
        At most :data:`TRACKS_PER_DAY_CAP` tracks. Past the cap the tail merges
        into one overflow track carrying every remaining dot in chronological
        order.
    """
    by_author: dict[str, list[dict]] = {}
    for dot in dots:
        by_author.setdefault(author_key(dot["v"]), []).append(dot)

    tracks = [
        {
            "key": key,
            "name": group[0]["v"].get("createdBy") or "",
            "dots": group,
            "overflow": False,
            "authorCount": 1,
        }
        for key, group in by_author.items()
    ]
    tracks.sort(key=lambda track: track["dots"][0]["index"])

    if len(tracks) <= TRACKS_PER_DAY_CAP:
        return tracks

    head = tracks[: TRACKS_PER_DAY_CAP - 1]
    tail = tracks[TRACKS_PER_DAY_CAP - 1 :]
    merged: list[dict] = []
    for track in tail:
        merged.extend(track["dots"])
    merged.sort(key=lambda dot: dot["index"])
    head.append(
        {
            "key": " ".join(track["key"] for track in tail),
            "name": ", ".join(track["name"] for track in tail),
            "dots": merged,
            "overflow": True,
            "authorCount": len(tail),
        }
    )
    return head


def bucket_by_day(versions: list[dict]) -> list[dict]:
    """Turn a flat version list into day rows, newest day first.

    Args:
        versions: Version records in any order. ``createdOnMs`` is epoch
            milliseconds; a record without one is undated.

    Returns:
        One row per local calendar day, newest first, each with its per-author
        tracks, its save count, and ``gap`` - the elapsed time to the row above
        it, or None for the top row and either side of the undated bucket.
        Undated versions collect in one trailing bucket rather than vanishing.
    """
    # `index` is the position on the thread axis, so it counts along the one
    # canonical order - the same one stamp_index_labels counts along.
    by_day: dict[str, list[dict]] = {}
    for index, version in enumerate(_ordered_oldest_first(versions)):
        stamp = _local_stamp(version)
        day, ms = stamp if stamp else ("", 0)
        by_day.setdefault(day, []).append({"v": version, "index": index, "ms": ms})

    undated = by_day.pop("", None)

    # ISO day strings sort lexicographically = chronologically.
    rows = [
        {
            "day": day,
            "count": len(by_day[day]),
            "tracks": tracks_for_day(by_day[day]),
        }
        for day in sorted(by_day, reverse=True)
    ]
    if undated:
        rows.append(
            {"day": "", "count": len(undated), "tracks": tracks_for_day(undated)}
        )

    for i, row in enumerate(rows):
        row["gap"] = gap_between(rows[i - 1], row) if i else None
    return rows
