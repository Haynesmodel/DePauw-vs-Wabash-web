"""
Which Wabash games are still ahead, and which are waiting for their result.

Pure functions over data/upcoming.json (written by scrape.py) and the game history, so they can be
tested without HTML. "Today" is passed in (Eastern date) and nothing here reads the clock.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

# A game that was played but is still missing from the history page stays "result pending" for this
# long. After that the history page is not going to get it (a forfeit, a no-contest), so it is dropped
# instead of sitting on the card forever.
PENDING_DAYS = 14


def load_upcoming(path: Path | None) -> dict:
    """Sport key -> {"schedule_url": ..., "wabash_schedule_url": ..., "games": [...]}. A missing or damaged file gives {}, because
    the schedule is a nice-to-have and must never stop the records from being published."""
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        sports = data["sports"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if not isinstance(sports, dict):
        return {}
    clean = {}
    for key, entry in sports.items():
        games = []
        for g in (entry.get("games") if isinstance(entry, dict) else None) or []:
            try:
                dt.date.fromisoformat(g["date"])
            except (KeyError, TypeError, ValueError):
                continue
            games.append(g)
        clean[key] = {"schedule_url": entry.get("schedule_url"),
                      "wabash_schedule_url": entry.get("wabash_schedule_url"), "games": games}
    return clean


def split_games(games: list, history: list, today: dt.date) -> tuple[list, list]:
    """Return (ahead, pending) for one sport.

    ahead   - games dated today or later, in date order (postponed ones are kept and marked).
    pending - games from the last PENDING_DAYS days that are not in the history yet. A date counts as
              reported when the history has at least as many games on it as the schedule lists, so a
              doubleheader is not hidden by its first game.
    """
    on_date: dict = {}
    for h in history:
        on_date[h["date"]] = on_date.get(h["date"], 0) + 1

    ahead = sorted((g for g in games if dt.date.fromisoformat(g["date"]) >= today), key=lambda g: g["date"])
    past = [g for g in games
            if g.get("status") != "postponed"          # a postponed game has no result to wait for
            and today - dt.timedelta(days=PENDING_DAYS) <= dt.date.fromisoformat(g["date"]) < today]
    pending, seen = [], {}
    for g in sorted(past, key=lambda g: g["date"]):
        seen[g["date"]] = seen.get(g["date"], 0) + 1
        if on_date.get(g["date"], 0) < seen[g["date"]]:
            pending.append(g)
    return ahead, pending


def next_overall(per_sport: dict) -> tuple[str, dict] | None:
    """The soonest game ahead across all sports, as (sport key, game); ties go to the earlier sport in
    the page order. per_sport maps key -> list of games ahead, in page order."""
    best = None
    for key, ahead in per_sport.items():
        for g in ahead:
            if g.get("status") == "postponed":
                continue  # a postponed game has no real date to count down to
            if best is None or g["date"] < best[1]["date"]:
                best = (key, g)
            break
    return best
