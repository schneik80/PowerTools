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
from datetime import date, datetime

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
    # Oldest to newest, so `index` is the position on the thread axis. Undated
    # versions sort last and keep their input order (the sort is stable).
    stamped = [(version, _local_stamp(version)) for version in versions]
    ordered = sorted(
        stamped,
        key=lambda pair: (1, 0) if pair[1] is None else (0, pair[0]["createdOnMs"]),
    )

    by_day: dict[str, list[dict]] = {}
    for index, (version, stamp) in enumerate(ordered):
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
