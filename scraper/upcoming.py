"""
Parser for DePauw's Sidearm schedule pages (https://depauwtigers.com/sports/<sport>/schedule).

Finds the games against one opponent (matched by the opponent id Sidearm puts on each game, never
by name) that have not been played yet, and returns them as plain dicts for data/upcoming.json.
The yearless schedule URL always serves the current season, so sources.json needs no yearly edit.

The page's embedded JSON is a widget feed cut off after 20 games, so it is not used; everything
comes from the visible game list.

A game is kept when it has no result and is not canceled. Whether it is "upcoming" or
"result pending" is decided when the page is rendered, against today's date, not here.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from typing import Optional

from bs4 import BeautifulSoup

DATE_RE = re.compile(r"^([A-Z][a-z]{2})\w*\.?\s+(\d{1,2})(?:\s*\(([A-Z][a-z]{2})\))?$")
TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?$", re.I)
FULL_DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
                          r" (\d{1,2}), (\d{4})\b")
TITLE_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})(?:-\d{2})?\b")
CANCELED_RE = re.compile(r"\b(cancell?ed|ccd)\b", re.I)
POSTPONED_RE = re.compile(r"\b(postponed|ppd|suspended)\b", re.I)

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
FULL_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleError(Exception):
    pass


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def warn(message: str) -> None:
    print(f"WARN {message}", file=sys.stderr)


def _season_start_year(soup: BeautifulSoup) -> Optional[int]:
    """'2026-27 Men's Basketball Schedule' and '2026 Football Schedule' both start in 2026."""
    title = _text(soup.title)
    m = TITLE_YEAR_RE.search(title)
    return int(m.group(1)) if m else None


def _year_for(month: int, day: int, weekday: Optional[str], li, season_year: Optional[int]) -> Optional[int]:
    """The schedule shows 'Nov 14 (Sat)' with no year. Prefer a full date written in the game's own
    links ('...on November 14, 2026 at 1:07 p.m.'), then the season's start year or the next one,
    whichever puts the weekday right (or, with no weekday, whichever keeps Aug-Dec in the first year)."""
    for el in li.find_all(attrs={"aria-label": True}):
        m = FULL_DATE_RE.search(el["aria-label"])
        if m and FULL_MONTHS[m.group(1)] == month and int(m.group(2)) == day:
            return int(m.group(3))
    if season_year is None:
        return None
    candidates = []
    for year in (season_year, season_year + 1):
        try:
            d = dt.date(year, month, day)
        except ValueError:
            continue
        if weekday is None or WEEKDAYS[d.weekday()] == weekday:
            candidates.append(year)
    if not candidates:
        return None
    if len(candidates) == 2 or weekday is None:
        return season_year if month >= 8 else season_year + 1
    return candidates[0]


def _clock(text: str) -> Optional[str]:
    m = TIME_RE.match(text.strip())
    if not m:
        return None
    hour, minute, half = int(m.group(1)), m.group(2) or "00", m.group(3).upper()
    return f"{hour}:{minute} {half}M"


def _site(li) -> Optional[str]:
    loc = li.select_one(".sidearm-schedule-game-location")
    spans = [_text(s) for s in loc.find_all("span")] if loc else []
    spans = [s for s in spans if s and s.upper() != "TBA"]
    if not spans:
        return None
    # Home games list "Greencastle, Ind." then the facility; neutral sites give "Facility; City, State".
    site = ", ".join(reversed(spans)) if len(spans) > 1 else spans[0]
    return site.replace("; ", ", ")


def _game_date(li, season_year) -> Optional[str]:
    """The ISO date of one schedule row, or None when it cannot be read (the caller decides whether to warn)."""
    spans = [_text(s) for s in li.select(".sidearm-schedule-game-opponent-date > span")]
    m = DATE_RE.match(spans[0]) if spans else None
    if not m or m.group(1) not in MONTHS:
        return None
    month, day = MONTHS[m.group(1)], int(m.group(2))
    year = _year_for(month, day, m.group(3), li, season_year)
    try:
        return dt.date(year, month, day).isoformat() if year else None
    except ValueError:
        return None


def parse_schedule(html: str, *, opponent_id: int, canceled: Optional[list] = None) -> list:
    """The games against one opponent that have no result and are not canceled. When `canceled` is a list,
    the dates of the canceled games are appended to it (scrape.py needs them to stop carrying a game over)."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("ul.sidearm-schedule-games-container")
    if container is None:
        raise ScheduleError("schedule list not found (layout changed or wrong page)")
    season_year = _season_start_year(soup)

    games = []
    for li in container.select("li.sidearm-schedule-game"):
        if li.get("data-game-opponent-id") != str(opponent_id):
            continue

        status = _text(li.select_one(".sidearm-schedule-game-result"))
        header = _text(li.select_one(".sidearm-schedule-game-opponent-date"))
        tail = f"{status} {header} {' '.join(li.get('class', []))}"
        if CANCELED_RE.search(tail):
            if canceled is not None and (when := _game_date(li, season_year)):
                canceled.append(when)
            continue
        # A finished game has a result in the history page; the schedule only repeats it.
        classes = li.get("class", [])
        if "sidearm-schedule-game-completed" in classes or re.match(r"^[WLT],?\s", status):
            continue

        spans = [_text(s) for s in li.select(".sidearm-schedule-game-opponent-date > span")]
        m = DATE_RE.match(spans[0]) if spans else None
        if not m or m.group(1) not in MONTHS:
            warn(f"schedule: unreadable date {spans[:1]!r} on game {li.get('data-game-id')}")
            continue
        month, day, weekday = MONTHS[m.group(1)], int(m.group(2)), m.group(3)
        year = _year_for(month, day, weekday, li, season_year)
        if year is None:
            warn(f"schedule: could not work out the year for {spans[0]!r}")
            continue
        try:
            date = dt.date(year, month, day).isoformat()
        except ValueError:
            warn(f"schedule: impossible date {year}-{month}-{day}")
            continue

        clock = _clock(spans[1]) if len(spans) > 1 else None
        time_note = spans[1] if len(spans) > 1 and clock is None and spans[1].lower().startswith("following") else None
        kind = "neutral" if "sidearm-schedule-neutral-game" in classes else \
               "away" if "sidearm-schedule-away-game" in classes else \
               "home" if "sidearm-schedule-home-game" in classes else "unknown"

        games.append({
            "date": date,
            "time": clock,
            "time_note": time_note,
            "location": kind,
            "site": _site(li),
            "status": "postponed" if POSTPONED_RE.search(tail) else "scheduled",
            "doubleheader": "(DH)" in _text(li.select_one(".sidearm-schedule-game-opponent-name")),
        })
    return sorted(games, key=lambda g: g["date"])  # stable, so a doubleheader stays game 1 then game 2


# --------------------------------------------------------------------------- #
# Cross-checking DePauw's schedule against Wabash's
# --------------------------------------------------------------------------- #

FLIP_LOCATION = {"home": "away", "away": "home"}
SITE_WORDS = re.compile(r"[^a-z0-9 ]")
STATE_FIXES = {"ind": "in", "indiana": "in"}
SCHEDULE_DATE_WINDOW = 3


def flip_location(g: dict) -> dict:
    """A game from Wabash's schedule, written from Wabash's side, as DePauw's point of view."""
    return {**g, "location": FLIP_LOCATION.get(g["location"], g["location"])}


def _site_words(site: Optional[str]) -> set:
    words = SITE_WORDS.sub(" ", (site or "").lower()).split()
    return {STATE_FIXES.get(w, w) for w in words}


def same_site(a: Optional[str], b: Optional[str]) -> bool:
    """'Scheumann Stadium, Muncie, Ind.' and 'Scheumann Stadium, Muncie, IN' are the same place, and
    'Greencastle, IN' is a shorter way to name 'Neal Fieldhouse, Greencastle, Ind.'."""
    wa, wb = _site_words(a), _site_words(b)
    return not wa or not wb or wa <= wb or wb <= wa


def merge_schedules(label: str, depauw: list, wabash: list) -> tuple:
    """DePauw's upcoming games with Wabash's schedule folded in. Returns (games, warnings).

    A game on both schedules is shown as DePauw lists it (source "both"); any difference in date,
    time, site, place or status becomes a warning. A game only Wabash lists is shown too, with source
    "wabash". Games match by date first (a doubleheader pairs in order), then by dates a few days
    apart. This never affects the records."""
    warnings = []
    pairs: dict = {}
    used_w: set = set()
    for di, gd in enumerate(depauw):
        for wi, gw in enumerate(wabash):
            if wi not in used_w and gw["date"] == gd["date"] and di not in pairs:
                pairs[di] = wi
                used_w.add(wi)
    edges = sorted((abs((dt.date.fromisoformat(gd["date"]) - dt.date.fromisoformat(gw["date"])).days), di, wi)
                   for di, gd in enumerate(depauw) if di not in pairs
                   for wi, gw in enumerate(wabash) if wi not in used_w)
    for gap, di, wi in edges:
        if gap <= SCHEDULE_DATE_WINDOW and di not in pairs and wi not in used_w:
            pairs[di] = wi
            used_w.add(wi)

    merged = []
    for di, gd in enumerate(depauw):
        game = dict(gd)
        game["source"] = "depauw"
        if di in pairs:
            gw = wabash[pairs[di]]
            game["source"] = "both"
            diffs = []
            if gw["date"] != gd["date"]:
                diffs.append(f"date (Wabash {gw['date']})")
            if gd.get("time") and gw.get("time") and gd["time"] != gw["time"]:
                diffs.append(f"time (Wabash {gw['time']})")
            if not same_site(gd.get("site"), gw.get("site")):
                diffs.append(f"site (Wabash {gw.get('site')})")
            if "unknown" not in (gd["location"], gw["location"]) and gd["location"] != gw["location"]:
                diffs.append(f"home/away (Wabash {gw['location']})")
            if gd["status"] != gw["status"]:
                diffs.append(f"status (Wabash {gw['status']})")
            if diffs:
                warnings.append(f"{label} {gd['date']}: DePauw's schedule and Wabash's differ on "
                                f"{', '.join(diffs)}; showing DePauw's")
            for k in ("time", "site"):
                if not game.get(k) and gw.get(k):
                    game[k] = gw[k]
        merged.append(game)
    for wi, gw in enumerate(wabash):
        if wi not in used_w:
            warnings.append(f"{label} {gw['date']}: only on Wabash's schedule; showing it as Wabash's")
            merged.append({**gw, "source": "wabash"})
    return sorted(merged, key=lambda g: g["date"]), warnings


# --------------------------------------------------------------------------- #
# A game that has just finished
# --------------------------------------------------------------------------- #

CARRY_DAYS = 1


def _clock_key(g: dict):
    return g.get("time") or ""


def carry_over(old: list, new: list, *, history_dates: list, canceled: set, today: dt.date) -> list:
    """Games from the last run that the schedule pages no longer list but the history does not have yet.

    A school's schedule page can show the final score before its history page does. The scraper drops a
    finished game, so without this the game would vanish from data/upcoming.json while it is still missing
    from the records, and the game-day job (which reads that file) would stop checking for the result.
    A game is carried only when it is dated today or yesterday (Eastern), it is no longer on the schedule
    (matched by date and start time) and the history has fewer games on that date than have dropped off,
    so for a doubleheader only the game that dropped off and is still missing is carried. A canceled game (`canceled`: dates the schedule marks canceled) is
    never carried. After CARRY_DAYS it is dropped even if the result never arrives, so nothing lingers."""
    out = []
    for date in sorted({g["date"] for g in old}):
        age = (today - dt.date.fromisoformat(date)).days
        if not 0 <= age <= CARRY_DAYS or date in canceled:
            continue
        still = [_clock_key(g) for g in new if g["date"] == date]
        dropped = []
        for g in [g for g in old if g["date"] == date]:
            if _clock_key(g) in still:
                still.remove(_clock_key(g))     # this one is still on the schedule
            elif g.get("status") != "postponed":
                dropped.append(g)
        waiting = len(dropped) - sum(1 for d in history_dates if d == date)   # dropped but not in the history yet
        if waiting > 0:
            out.extend(dropped[len(dropped) - waiting:])
    return out
