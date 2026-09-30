# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

from datetime import datetime, timedelta


def next_business_day(dt: datetime) -> datetime:
    """Return *dt* unchanged if it is a weekday (Mon–Fri).
    If it falls on Saturday, advance to the following Monday (+2 days).
    If it falls on Sunday, advance to Monday (+1 day).
    This ensures every returned date is a US business day (weekend-free).
    """
    weekday = dt.weekday()  # 0 = Monday … 6 = Sunday
    if weekday == 5:  # Saturday → Monday
        dt += timedelta(days=2)
    elif weekday == 6:  # Sunday → Monday
        dt += timedelta(days=1)
    return dt


def later_label(dt: datetime) -> str:
    """Return ``'3:07 pm'`` style text for *dt*: 12-hour clock, no leading zero.

    The am/pm marker is derived from ``dt.hour`` rather than ``strftime('%p')``,
    which is locale-dependent and empty on e.g. de_DE / fr_FR.
    """
    hour_12 = dt.hour % 12 or 12
    ampm = "am" if dt.hour < 12 else "pm"
    return f"{hour_12}:{dt.strftime('%M')} {ampm}"


def compute_quick_dates(now: datetime | None = None) -> list:
    """Pre-calculate quick-date options relative to *now* (default: current time).

    Returns a list of (display_label, date_value) tuples where date_value is
    either 'YYYY-MM-DD' (date-only) or 'YYYY-MM-DD HH:MM' (for Later).
    Weekend adjustments are applied where appropriate.
    """
    if now is None:
        now = datetime.now()

    def _fmt(dt):
        """'Mon 9 Mar' style — no leading zero on day."""
        return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')}"

    results = []

    # 1. Today
    results.append(
        (
            f"Today \u2014 {now.strftime('%a')}",
            now.strftime("%Y-%m-%d"),
        )
    )

    # 2. Later (now + 2 hours) — carries a time component for ClickUp
    later = now + timedelta(hours=2)
    results.append(
        (
            f"Later \u2014 {later_label(later)}",
            later.strftime("%Y-%m-%d %H:%M"),
        )
    )

    # 3. Tomorrow — next business day
    tomorrow = next_business_day(now + timedelta(days=1))
    results.append(
        (
            f"Tomorrow \u2014 {tomorrow.strftime('%a')}",
            tomorrow.strftime("%Y-%m-%d"),
        )
    )

    # 4. End of Week — this Friday; if Sat/Sun, next Friday
    days_to_eow = (4 - now.weekday()) % 7
    eow = now + timedelta(days=days_to_eow)
    results.append(
        (
            f"End of Week \u2014 {_fmt(eow)}",
            eow.strftime("%Y-%m-%d"),
        )
    )

    # 5. Next Week — coming Monday (if today is Mon, goes to next Mon)
    days_to_monday = ((7 - now.weekday()) % 7) or 7
    next_mon = now + timedelta(days=days_to_monday)
    results.append(
        (
            f"Next Week \u2014 {_fmt(next_mon)}",
            next_mon.strftime("%Y-%m-%d"),
        )
    )

    # 6. Next Friday — always the Friday one week after End-of-Week Friday
    next_fri = eow + timedelta(days=7)
    results.append(
        (
            f"Next Friday \u2014 {_fmt(next_fri)}",
            next_fri.strftime("%Y-%m-%d"),
        )
    )

    # 7. 2 Weeks — today + 14 days, weekend-adjusted
    two_wk = next_business_day(now + timedelta(days=14))
    results.append(
        (
            f"2 Weeks \u2014 {_fmt(two_wk)}",
            two_wk.strftime("%Y-%m-%d"),
        )
    )

    # 8. 4 Weeks — today + 28 days, weekend-adjusted; shorter 'D Mon' format
    four_wk = next_business_day(now + timedelta(days=28))
    results.append(
        (
            f"4 Weeks \u2014 {four_wk.day} {four_wk.strftime('%b')}",
            four_wk.strftime("%Y-%m-%d"),
        )
    )

    return results
