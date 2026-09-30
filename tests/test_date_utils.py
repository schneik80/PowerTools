# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Unit tests for lib/ptAddInUtils/date_utils.py.

The "Later" quick-date label used ``strftime('%p')``, which is locale-dependent
and empty under e.g. de_DE / fr_FR. The am/pm marker is now derived from the
hour; these tests pin the label around midnight and noon, where the 12-hour
clock wraps.
"""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

_PATH = (
    Path(__file__).resolve().parent.parent / "lib" / "ptAddInUtils" / "date_utils.py"
)
_spec = importlib.util.spec_from_file_location("date_utils", _PATH)
date_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(date_utils)


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (0, 5, "12:05 am"),
        (1, 0, "1:00 am"),
        (11, 59, "11:59 am"),
        (12, 0, "12:00 pm"),
        (13, 7, "1:07 pm"),
        (23, 30, "11:30 pm"),
    ],
)
def test_later_label_am_pm_from_hour(hour, minute, expected) -> None:
    assert date_utils.later_label(datetime(2026, 3, 9, hour, minute)) == expected


def test_later_label_matches_english_strftime() -> None:
    """The explicit marker reproduces the former '%I'/'%p' output on a C locale."""
    for hour in range(24):
        dt = datetime(2026, 3, 9, hour, 42)
        legacy = (
            f"{int(dt.strftime('%I'))}:{dt.strftime('%M')} {dt.strftime('%p').lower()}"
        )
        assert date_utils.later_label(dt) == legacy


def test_compute_quick_dates_later_wraps_midnight() -> None:
    now = datetime(2026, 3, 9, 23, 10)  # Monday
    label, value = date_utils.compute_quick_dates(now)[1]
    assert label == "Later — 1:10 am"
    assert value == "2026-03-10 01:10"


def test_compute_quick_dates_later_crosses_noon() -> None:
    now = datetime(2026, 3, 9, 10, 30)
    label, value = date_utils.compute_quick_dates(now)[1]
    assert label == "Later — 12:30 pm"
    assert value == "2026-03-09 12:30"


def test_next_business_day_skips_weekend() -> None:
    sat = datetime(2026, 3, 14)
    sun = datetime(2026, 3, 15)
    mon = datetime(2026, 3, 16)
    assert date_utils.next_business_day(sat) == mon
    assert date_utils.next_business_day(sun) == mon
    assert date_utils.next_business_day(mon) == mon
