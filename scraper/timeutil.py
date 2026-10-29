"""
US Eastern time without zoneinfo, shared by the page renderer and the game-day gate (stdlib only, so the
gate job needs no dependencies). Hand-coded because zoneinfo needs the tzdata package on Windows.
"""

from __future__ import annotations

import datetime as dt


def nth_sunday(year: int, month: int, n: int) -> int:
    first = dt.date(year, month, 1)
    return 1 + (6 - first.weekday()) % 7 + 7 * (n - 1)


def to_eastern(utc: dt.datetime) -> tuple[dt.datetime, str]:
    """UTC -> US Eastern with the current US DST rule (second Sunday of March to first
    Sunday of November). Returns (local time, "EDT" or "EST")."""
    utc = utc.astimezone(dt.timezone.utc)
    y = utc.year
    start = dt.datetime(y, 3, nth_sunday(y, 3, 2), 7, tzinfo=dt.timezone.utc)   # 2:00 EST
    end = dt.datetime(y, 11, nth_sunday(y, 11, 1), 6, tzinfo=dt.timezone.utc)   # 2:00 EDT
    if start <= utc < end:
        return utc + dt.timedelta(hours=-4), "EDT"
    return utc + dt.timedelta(hours=-5), "EST"


def from_eastern(local: dt.datetime) -> dt.datetime:
    """A naive Eastern wall-clock time as an aware UTC time. (The hour that repeats when the clocks go
    back is read as the first one, EDT; the hour that does not exist when they go forward as EST.)"""
    for offset in (4, 5):
        utc = (local + dt.timedelta(hours=offset)).replace(tzinfo=dt.timezone.utc)
        if to_eastern(utc)[0].replace(tzinfo=None) == local:
            return utc
    return (local + dt.timedelta(hours=5)).replace(tzinfo=dt.timezone.utc)


def parse_clock(text: str | None) -> dt.time | None:
    """'1:07 PM' / '12 PM' / '7:00 p.m.' as a time of day, or None when there is no readable time."""
    import re
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([AaPp])\.?[Mm]\.?\s*$", text or "")
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if not (1 <= hour <= 12 and minute < 60):
        return None
    return dt.time(hour % 12 + (12 if m.group(3).lower() == "p" else 0), minute)
