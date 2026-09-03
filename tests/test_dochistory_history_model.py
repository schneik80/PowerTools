"""Bucketing contract for the Document History palette.

``commands/dochistory/history_model.py`` decides which day a save belongs to,
which track inside that day, and how long the design sat untouched between two
days. Every one of those is a number the palette draws as fact, so each is
pinned here rather than left to be eyeballed in Fusion.

The cases are a port of the vitest suite that covers the same bucketing in the
web view this palette was modelled on, so the two presentations cannot drift
apart in what they claim about a history.

Versions are built with LOCAL wall-clock times, matching what the view shows:
the day a save belongs to is the day the author saw on their own clock.
"""

from datetime import date, datetime

import pytest
from PowerTools.commands.dochistory import history_model as model

ADA = ("user-ada", "Ada Lovelace")
GRACE = ("user-grace", "Grace Hopper")


def v(number: int, local: str = "", who: tuple[str, str] | None = None) -> dict:
    """Build a version record the way ``entry.py`` does.

    Args:
        number: The version number.
        local: Local wall-clock ``YYYY-MM-DD HH:MM`` stamp, or "" for a version
            Fusion gave no usable date for.
        who: ``(user id, display name)``, or None for an unattributed save.

    Returns:
        The record shape :func:`history_model.bucket_by_day` consumes.
    """
    created_ms = None
    if local:
        day, _, clock = local.partition(" ")
        hour, _, minute = (clock or "12:00").partition(":")
        stamp = datetime(*(int(p) for p in day.split("-")), int(hour), int(minute))
        created_ms = int(stamp.timestamp() * 1000)
    return {
        "number": number,
        "createdOnMs": created_ms,
        "createdById": who[0] if who else "",
        "createdBy": who[1] if who else "",
    }


def dots_of(rows: list[dict]) -> list[dict]:
    """Flatten every dot out of a stack of day rows."""
    return [dot for row in rows for track in row["tracks"] for dot in track["dots"]]


# ---------------------------------------------------------------------------
# author_key
# ---------------------------------------------------------------------------


def test_author_key_prefers_the_user_id():
    assert model.author_key({"createdById": "u1", "createdBy": "Ada"}) == "u1"


def test_author_key_falls_back_to_the_display_name_then_to_empty():
    assert model.author_key({"createdBy": "Ada"}) == "Ada"
    assert model.author_key({}) == ""


def test_author_key_keeps_two_people_with_the_same_display_name_apart():
    a = {"createdById": "u1", "createdBy": "Chris Smith"}
    b = {"createdById": "u2", "createdBy": "Chris Smith"}
    assert model.author_key(a) != model.author_key(b)


# ---------------------------------------------------------------------------
# bucket_by_day
# ---------------------------------------------------------------------------


def test_groups_by_local_calendar_day_newest_first():
    rows = model.bucket_by_day(
        [
            v(3, "2026-08-12 09:00"),
            v(2, "2026-08-11 23:30"),
            v(1, "2026-08-11 08:00"),
        ]
    )
    assert [row["day"] for row in rows] == ["2026-08-12", "2026-08-11"]
    assert rows[0]["count"] == 1
    assert rows[1]["count"] == 2


def test_buckets_a_late_evening_save_on_the_local_day_not_the_utc_one():
    # 23:30 local is the next UTC day in any positive-offset zone; it must stay
    # on the day the author actually saw.
    rows = model.bucket_by_day([v(1, "2026-08-11 23:30")])
    assert rows[0]["day"] == "2026-08-11"


def test_indexes_versions_oldest_first_across_the_whole_history():
    rows = model.bucket_by_day(
        [
            v(3, "2026-08-12 09:00"),
            v(2, "2026-08-11 15:00"),
            v(1, "2026-08-11 08:00"),
        ]
    )
    by_number = {dot["v"]["number"]: dot["index"] for dot in dots_of(rows)}
    assert by_number == {1: 0, 2: 1, 3: 2}


def test_computes_ms_from_the_local_clock():
    rows = model.bucket_by_day([v(1, "2026-08-11 06:30")])
    assert rows[0]["tracks"][0]["dots"][0]["ms"] == (6 * 60 + 30) * 60_000


def test_collects_undated_versions_in_one_trailing_bucket_rather_than_dropping():
    rows = model.bucket_by_day([v(2), v(1, "2026-08-11 08:00"), v(3)])
    assert [row["day"] for row in rows] == ["2026-08-11", ""]
    assert rows[1]["count"] == 2
    # Undated saves keep their input order, so the trailing bucket is not a
    # reshuffle of whatever the dict happened to hold.
    assert [dot["v"]["number"] for dot in rows[1]["tracks"][0]["dots"]] == [2, 3]


def test_returns_nothing_for_an_empty_history():
    assert model.bucket_by_day([]) == []


# ---------------------------------------------------------------------------
# tracks_for_day
# ---------------------------------------------------------------------------


def tracks_of(versions: list[dict]) -> list[dict]:
    """Bucket *versions* and return the newest day's tracks."""
    return model.bucket_by_day(versions)[0]["tracks"]


def test_gives_a_single_author_one_track():
    tracks = tracks_of([v(1, "2026-08-11 08:00", ADA), v(2, "2026-08-11 09:00", ADA)])
    assert len(tracks) == 1
    assert len(tracks[0]["dots"]) == 2
    assert tracks[0]["name"] == "Ada Lovelace"


def test_splits_two_authors_and_orders_them_by_who_saved_first():
    tracks = tracks_of(
        [
            v(1, "2026-08-11 15:00", GRACE),
            v(2, "2026-08-11 08:00", ADA),
            v(3, "2026-08-11 16:00", GRACE),
        ]
    )
    assert [track["key"] for track in tracks] == ["user-ada", "user-grace"]
    assert [dot["v"]["number"] for dot in tracks[1]["dots"]] == [1, 3]


def test_groups_by_name_when_no_id_is_present():
    tracks = tracks_of(
        [
            v(1, "2026-08-11 08:00", ("", "Ada Lovelace")),
            v(2, "2026-08-11 09:00", ("", "Ada Lovelace")),
        ]
    )
    assert len(tracks) == 1
    assert tracks[0]["key"] == "Ada Lovelace"


def test_merges_the_tail_into_one_overflow_track_past_the_cap_losing_no_dots():
    versions = [
        v(i + 1, f"2026-08-11 0{i}:00", (f"u{i}", f"User {i}")) for i in range(9)
    ]
    tracks = tracks_of(versions)
    assert len(tracks) == model.TRACKS_PER_DAY_CAP
    overflow = tracks[-1]
    assert overflow["overflow"] is True
    assert overflow["authorCount"] == 9 - (model.TRACKS_PER_DAY_CAP - 1)
    assert sum(len(track["dots"]) for track in tracks) == 9


def test_keeps_the_overflow_track_in_chronological_order():
    versions = [
        v(i + 1, f"2026-08-11 0{i}:00", (f"u{i}", f"User {i}")) for i in range(8)
    ]
    overflow = tracks_of(versions)[-1]
    indexes = [dot["index"] for dot in overflow["dots"]]
    assert indexes == sorted(indexes)


# ---------------------------------------------------------------------------
# gap_between
# ---------------------------------------------------------------------------


def rows_for(days: list[str]) -> list[dict]:
    """Bucket one 12:00 save on each of *days*."""
    return model.bucket_by_day([v(i + 1, f"{day} 12:00") for i, day in enumerate(days)])


def test_calls_one_day_a_next_day_gap():
    rows = rows_for(["2026-08-11", "2026-08-12"])
    assert model.gap_between(rows[0], rows[1])["tier"] == "nextDay"
    assert model.gap_between(rows[0], rows[1])["days"] == 1


@pytest.mark.parametrize(
    ("days", "tier", "count"),
    [
        (["2026-08-08", "2026-08-11"], "days", 3),
        (["2026-08-01", "2026-08-11"], "wide", 10),
    ],
)
def test_tiers_a_few_days_apart_from_a_week_or_more(days, tier, count):
    rows = rows_for(days)
    gap = model.gap_between(rows[0], rows[1])
    assert gap["tier"] == tier
    assert gap["days"] == count


def test_carries_a_calendar_breakdown_for_long_gaps():
    rows = rows_for(["2025-06-09", "2026-08-12"])
    assert model.gap_between(rows[0], rows[1])["breakdown"] == {
        "years": 1,
        "months": 2,
        "days": 3,
    }


def test_has_nothing_to_say_about_the_undated_bucket():
    rows = model.bucket_by_day([v(1, "2026-08-11 12:00"), v(2)])
    assert model.gap_between(rows[0], rows[1]) is None


def test_bucket_by_day_attaches_each_rows_gap_to_the_row_above_it():
    rows = model.bucket_by_day(
        [
            v(1, "2026-05-10 09:00"),
            v(2, "2026-08-11 09:00"),
            v(3, "2026-08-12 09:00"),
        ]
    )
    assert rows[0]["gap"] is None  # nothing above the newest row
    assert rows[1]["gap"]["tier"] == "nextDay"
    assert rows[2]["gap"]["tier"] == "wide"
    assert rows[2]["gap"]["breakdown"] == {"years": 0, "months": 3, "days": 1}


# ---------------------------------------------------------------------------
# Calendar arithmetic
# ---------------------------------------------------------------------------


def test_add_months_clamps_to_the_target_months_length():
    assert model.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert model.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert model.add_months(date(2026, 11, 30), 2) == date(2027, 1, 30)


def test_calendar_breakdown_calls_end_of_january_to_end_of_february_one_month():
    assert model.calendar_breakdown(date(2026, 1, 31), date(2026, 2, 28)) == {
        "years": 0,
        "months": 1,
        "days": 0,
    }


def test_calendar_breakdown_is_symmetric_and_zero_for_the_same_day():
    span = model.calendar_breakdown(date(2026, 8, 12), date(2025, 6, 9))
    assert span == model.calendar_breakdown(date(2025, 6, 9), date(2026, 8, 12))
    assert model.calendar_breakdown(date(2026, 8, 12), date(2026, 8, 12)) == {
        "years": 0,
        "months": 0,
        "days": 0,
    }


def test_parse_day_rejects_a_malformed_day_instead_of_raising():
    assert model.parse_day("2026-02-31") is None
    assert model.parse_day("not a date") is None
    assert model.parse_day("") is None


# ---------------------------------------------------------------------------
# Milestones and releases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("A", True),
        ("Rev B", True),
        ("Prototype", True),
        ("Milestone V7", False),  # Fusion's own name for an auto milestone
        ("Item Update", False),
        ("", False),
    ],
)
def test_is_release_name_tells_a_typed_revision_from_an_auto_milestone(name, expected):
    assert model.is_release_name(name) is expected
