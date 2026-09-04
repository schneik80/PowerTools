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


# ---------------------------------------------------------------------------
# Merging MFGDM's two views of a history
# ---------------------------------------------------------------------------


def dv(number: int, iso: str, first: str = "", last: str = "", uid: str = "") -> dict:
    """Build a DesignItemVersion row the way MFGDM returns one."""
    return {
        "versionNumber": number,
        "createdOn": iso,
        "createdBy": {"id": uid, "firstName": first, "lastName": last},
    }


def mw(iso: str, description: str) -> dict:
    """Build a ModelWrittenHistoryChange row."""
    return {"timestamp": iso, "description": description}


def test_person_name_prefers_the_full_name_then_the_account_name():
    assert model.person_name({"firstName": "Ada", "lastName": "Lovelace"}) == (
        "Ada Lovelace"
    )
    assert model.person_name({"firstName": "Ada"}) == "Ada"
    assert model.person_name({"userName": "ada.l"}) == "ada.l"
    assert model.person_name({}) == ""
    assert model.person_name(None) == ""


def test_iso_to_epoch_ms_reads_the_trailing_z_as_utc():
    # 1970-01-01T00:00:01Z is one second after the epoch, wherever we run.
    assert model.iso_to_epoch_ms("1970-01-01T00:00:01.000Z") == 1000
    assert model.iso_to_epoch_ms("1970-01-01T00:00:01+00:00") == 1000
    # A naive stamp is read as UTC rather than as local time, so a history does
    # not shift by the reader's offset.
    assert model.iso_to_epoch_ms("1970-01-01T00:00:01") == 1000


def test_iso_to_epoch_ms_returns_none_for_junk_rather_than_raising():
    assert model.iso_to_epoch_ms("") is None
    assert model.iso_to_epoch_ms(None) is None
    assert model.iso_to_epoch_ms("not a date") is None


def test_merge_carries_the_per_version_author_that_the_desktop_api_could_not():
    versions = [
        dv(2, "2026-08-12T09:00:00.000Z", "Grace", "Hopper", "u-grace"),
        dv(1, "2026-08-11T08:00:00.000Z", "Ada", "Lovelace", "u-ada"),
    ]
    records = model.merge_cloud_history(versions, [])
    assert [r["number"] for r in records] == [2, 1]
    assert [r["createdBy"] for r in records] == ["Grace Hopper", "Ada Lovelace"]
    assert [r["createdById"] for r in records] == ["u-grace", "u-ada"]


def test_merge_takes_comments_by_position_when_the_counts_agree():
    versions = [
        dv(2, "2026-08-12T09:00:00.000Z", "Grace", "Hopper"),
        dv(1, "2026-08-11T08:00:00.000Z", "Ada", "Lovelace"),
    ]
    # Deliberately NOT the same instants as the versions: MFGDM stamps the same
    # save up to 35 seconds apart in its two views, which is why the join is by
    # position and a timestamp join would be wrong.
    writes = [
        mw("2026-08-12T09:00:34.000Z", "Reworked the bracket"),
        mw("2026-08-11T08:00:03.000Z", "Imported from a step file"),
    ]
    records = model.merge_cloud_history(versions, writes)
    assert [r["comment"] for r in records] == [
        "Reworked the bracket",
        "Imported from a step file",
    ]


def test_merge_drops_every_comment_when_the_two_lists_disagree_in_length():
    """A save wearing the wrong person's comment is worse than a bare save."""
    versions = [
        dv(3, "2026-08-13T09:00:00.000Z", "Ada", "Lovelace"),
        dv(2, "2026-08-12T09:00:00.000Z", "Grace", "Hopper"),
        dv(1, "2026-08-11T08:00:00.000Z", "Ada", "Lovelace"),
    ]
    records = model.merge_cloud_history(versions, [mw("2026-08-13T09:00:01.000Z", "x")])
    assert [r["comment"] for r in records] == ["", "", ""]
    # The authorship still survives — only the comments are withheld.
    assert [r["createdBy"] for r in records] == [
        "Ada Lovelace",
        "Grace Hopper",
        "Ada Lovelace",
    ]


def test_merge_skips_a_row_with_no_version_number():
    versions = [
        dv(1, "2026-08-11T08:00:00.000Z", "Ada", "Lovelace"),
        {"createdOn": "x"},
    ]
    assert [r["number"] for r in model.merge_cloud_history(versions, [])] == [1]


def test_merged_records_bucket_into_day_rows_by_author():
    versions = [
        dv(3, "2026-08-12T09:00:00.000Z", "Grace", "Hopper", "u-grace"),
        dv(2, "2026-08-12T08:00:00.000Z", "Ada", "Lovelace", "u-ada"),
        dv(1, "2026-08-11T08:00:00.000Z", "Ada", "Lovelace", "u-ada"),
    ]
    rows = model.bucket_by_day(model.merge_cloud_history(versions, []))
    # Two authors on the newest day means two tracks — the whole point of the
    # cloud read.
    assert len(rows[0]["tracks"]) == 2
    assert {t["key"] for t in rows[0]["tracks"]} == {"u-ada", "u-grace"}


# ---------------------------------------------------------------------------
# History entries that are not saves
# ---------------------------------------------------------------------------


def ch(typename: str, iso: str, description: str = "", first: str = "") -> dict:
    """Build a non-save HistoryChange row the way MFGDM returns one."""
    return {
        "__typename": typename,
        "timestamp": iso,
        "description": description,
        "author": {"id": "u-" + (first or "x"), "firstName": first, "lastName": ""},
    }


@pytest.mark.parametrize(
    ("typename", "expected"),
    [
        ("PropertiesUpdatedHistoryChange", "Property change"),
        ("VersionCreatedHistoryChange", "Milestone"),
        ("RevisionCreatedHistoryChange", "Release"),
        # Unmapped types still say something truthful. The schema has ten
        # change types and only the ones a real design produced are pinned.
        ("BomEditHistoryChange", "Bom Edit"),
        ("SomethingBrandNewHistoryChange", "Something Brand New"),
        ("Unrecognised", "Unrecognised"),
    ],
)
def test_change_label_names_every_type_including_ones_we_have_not_seen(
    typename, expected
):
    assert model.change_label(typename) == expected


def test_change_records_carry_the_author_and_the_detail():
    rows = [
        ch(
            "PropertiesUpdatedHistoryChange",
            "2026-08-12T09:00:00Z",
            "Cost: 100",
            "Cyan",
        )
    ]
    (record,) = model.change_records(rows)
    assert record["kind"] == "change"
    assert record["number"] is None
    assert record["changeLabel"] == "Property change"
    assert record["comment"] == "Cost: 100"
    assert record["createdBy"] == "Cyan"
    assert record["createdById"] == "u-Cyan"
    # Nothing to preview and no version to mark.
    assert record["versionId"] == ""
    assert record["isMilestone"] is False


def test_changes_surface_people_who_never_saved_a_version():
    """The reason this exists: a saves-only history under-credits a design."""
    versions = [dv(1, "2026-08-11T08:00:00Z", "Ada", "Lovelace", "u-ada")]
    changes = model.change_records(
        [
            ch(
                "PropertiesUpdatedHistoryChange",
                "2026-08-11T10:00:00Z",
                "Cost: 5",
                "Cyan",
            )
        ]
    )
    saves_only = model.bucket_by_day(model.merge_cloud_history(versions, []))
    with_changes = model.bucket_by_day(
        model.merge_cloud_history(versions, []) + changes
    )
    assert len(saves_only[0]["tracks"]) == 1
    assert len(with_changes[0]["tracks"]) == 2
    assert {t["name"] for t in with_changes[0]["tracks"]} == {"Ada Lovelace", "Cyan"}


def test_changes_bucket_onto_their_own_day_and_stay_in_order():
    changes = model.change_records(
        [
            ch("PropertiesUpdatedHistoryChange", "2026-08-12T09:00:00Z", "b", "Cyan"),
            ch("PropertiesUpdatedHistoryChange", "2026-08-11T09:00:00Z", "a", "Cyan"),
        ]
    )
    rows = model.bucket_by_day(changes)
    assert [row["day"] for row in rows] == ["2026-08-12", "2026-08-11"]
    assert [d["v"]["comment"] for d in dots_of(rows)] == ["b", "a"]
