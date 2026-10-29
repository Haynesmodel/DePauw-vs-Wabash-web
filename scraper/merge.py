"""
Merging DePauw's and Wabash's records of the same series into one history per sport.

Both athletics sites run the same Sidearm "opponent history" page. Each school's page is parsed and
validated on its own (scrape.py); this module only matches the two game lists and combines them.
Everything here is from DePauw's point of view: Wabash's games are flipped first (flip()).

Matching runs in fixed passes, and every pass uses each row at most once:
  1. Same date and same score.
  2. Wabash rows whose date is a placeholder (Jan 1 to Jan 3) match a DePauw row from the same
     season with the same score. The Wabash date is meaningless, so the DePauw date is used.
  3. Dates within MAX_DATE_GAP_DAYS of each other with the same score: one game, flagged date_differs.
  4. Same date, different score or result: one disputed game. DePauw's version counts and Wabash's is
     kept for display.
  5. Same season and same score on dates further apart, when both schools have the same number of such
     games left over: one game, flagged date_differs (LOOSE_SEASON_MATCH).
Several games on one date (doubleheaders) pair by score first, then by order on the page.
What is left is a game only one school lists; it still counts, and says whose record it is from.

A pair of rows that differ in both date and score cannot be told from two separate games, so they
stay separate. near_misses() lists such pairs so a person can check them; nothing is merged for them.

Each merged game is a dict with the fields of a game in series.json plus:
  source          "both", "depauw" or "wabash"
  date_known      False when the only date available was a placeholder (omitted when True)
  disputed        True when the two schools disagree on the score or result (omitted otherwise)
  wabash_version  Wabash's {result, depauw, wabash} for a disputed game, in DePauw's point of view
  date_differs    True when the two schools list the game on different dates (omitted otherwise)
  wabash_date     Wabash's date for such a game
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

MAX_DATE_GAP_DAYS = 2
# A last pass pairs leftover rows of the same season with the same score on any two dates, but only
# when each school has the same number of them. It exists because the schools sometimes disagree on
# a date by more than MAX_DATE_GAP_DAYS (a typo, or a game moved) and the same game would count twice.
# near_misses() lists what is still left over after it.
LOOSE_SEASON_MATCH = True
PLACEHOLDER_DAYS = {(1, 1), (1, 2), (1, 3)}
NEAR_MISS_DAYS = 5

SWAP = {"W": "L", "L": "W", "T": "T"}
FLIP_LOCATION = {"home": "away", "away": "home"}
SEASON_RE = re.compile(r"^(\d{4})(?:\s*[-–]\s*(\d{2}|\d{4}))?$")


class MergeError(Exception):
    pass


def flip(g: dict) -> dict:
    """A game parsed from Wabash's page (its own point of view) as DePauw's point of view: the result
    and the two scores swap, and home and away swap (neutral and unknown stay as they are)."""
    return {**g, "result": SWAP[g["result"]], "depauw": g["wabash"], "wabash": g["depauw"],
            "location": FLIP_LOCATION.get(g["location"], g["location"])}


def season_years(season: str | None, date: str) -> tuple[int, int]:
    """(first year, last year) of a season label: '1966-67' and '1966-1967' are both (1966, 1967) and
    '1997' is (1997, 1997). A label that cannot be read falls back to the game's own year."""
    m = SEASON_RE.match((season or "").strip())
    if not m:
        y = int(date[:4])
        return y, y
    start = int(m.group(1))
    if not m.group(2):
        return start, start
    end = m.group(2)
    last = int(end) if len(end) == 4 else (start // 100) * 100 + int(end)
    if last < start:
        last += 100
    return start, last


def season_key(g: dict) -> int:
    """The year a season ends in, so 'Wabash 1997', 'DePauw 1996-97' and '1996-1997' agree."""
    return season_years(g.get("season"), g["date"])[1]


def normalize_season(season: str | None, date: str) -> str:
    """One spelling for a season on the page: '1966-67' for a two-year season, '1997' for a single one."""
    first, last = season_years(season, date)
    if not SEASON_RE.match((season or "").strip()):
        return (season or "").strip() or str(first)
    return str(first) if first == last else f"{first}-{str(last)[-2:]}"


def is_placeholder(g: dict) -> bool:
    d = dt.date.fromisoformat(g["date"])
    return (d.month, d.day) in PLACEHOLDER_DAYS


def day_gap(a: str, b: str) -> int:
    return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)


def score(g: dict) -> tuple:
    return (g["depauw"], g["wabash"])


@dataclass
class MergeResult:
    games: list
    stats: dict
    depauw_only: list = field(default_factory=list)   # the DePauw rows nobody else lists
    wabash_only: list = field(default_factory=list)
    disputed: list = field(default_factory=list)      # (merged game) for each dispute
    date_differs: list = field(default_factory=list)  # (merged game) for each date mismatch


def _pair(edges: list, used_d: set, used_w: set, take) -> None:
    """Take pairs from the cheapest edge up, never using a row twice. An edge is (cost..., di, wi)."""
    for edge in sorted(edges):
        di, wi = edge[-2], edge[-1]
        if di in used_d or wi in used_w:
            continue
        used_d.add(di)
        used_w.add(wi)
        take(di, wi)


def merge_sport(depauw: list, wabash: list, *, loose: bool | None = None) -> MergeResult:
    """Merge DePauw's games with Wabash's (already flipped). Both lists are oldest first, with a
    doubleheader in playing order. Raises MergeError if the bookkeeping does not add up."""
    loose = LOOSE_SEASON_MATCH if loose is None else loose
    d, w = depauw, wabash
    used_d: set = set()
    used_w: set = set()
    pairs: dict = {}                       # di -> (wi, kind)

    def take(kind):
        def _take(di, wi):
            pairs[di] = (wi, kind)
        return _take

    # 1. same date, same score
    edges = [(0, di, wi) for di, gd in enumerate(d) for wi, gw in enumerate(w)
             if gd["date"] == gw["date"] and score(gd) == score(gw)]
    _pair(edges, used_d, used_w, take("exact"))

    # A Wabash row with a placeholder date that no DePauw row confirmed has no usable date.
    placeholder = {wi for wi, gw in enumerate(w) if wi not in used_w and is_placeholder(gw)}

    # 2. placeholder dates: same season, same score
    edges = [(di, wi) for di, gd in enumerate(d) if di not in used_d for wi in placeholder
             if wi not in used_w and season_key(gd) == season_key(w[wi]) and score(gd) == score(w[wi])]
    _pair(edges, used_d, used_w, take("placeholder"))

    # 3. dates a day or two apart, same score
    edges = [(day_gap(gd["date"], gw["date"]), di, wi)
             for di, gd in enumerate(d) if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w and wi not in placeholder
             and score(gd) == score(gw) and 0 < day_gap(gd["date"], gw["date"]) <= MAX_DATE_GAP_DAYS]
    _pair(edges, used_d, used_w, take("date_differs"))

    # 4. same date, different score or result: a dispute (the exact pass already took equal scores)
    edges = [(0, di, wi) for di, gd in enumerate(d) if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w and wi not in placeholder
             and gd["date"] == gw["date"]]
    _pair(edges, used_d, used_w, take("disputed"))

    # 5. optional: the same season and score on dates further apart than the window. Only when both
    # schools have the same number of such leftover games, so which one belongs to which is not a guess.
    if loose:
        left_d: dict = {}
        left_w: dict = {}
        for di, gd in enumerate(d):
            if di not in used_d:
                left_d.setdefault((season_key(gd), score(gd)), []).append(di)
        for wi, gw in enumerate(w):
            if wi not in used_w and wi not in placeholder:
                left_w.setdefault((season_key(gw), score(gw)), []).append(wi)
        edges = [(day_gap(d[di]["date"], w[wi]["date"]), di, wi)
                 for key, dis in left_d.items() if len(dis) == len(left_w.get(key, []))
                 for di in dis for wi in left_w[key]]
        _pair(edges, used_d, used_w, take("date_differs"))

    wabash_for = {wi: di for di, (wi, _) in pairs.items()}
    merged: list = []
    disputed, differs = [], []
    for di, gd in enumerate(d):
        game = _base(gd, "depauw")
        if di in pairs:
            wi, kind = pairs[di]
            gw = w[wi]
            game["source"] = "both"
            _fill_gaps(game, gw)
            if kind == "disputed":
                game["disputed"] = True
                game["wabash_version"] = {"result": gw["result"], "depauw": gw["depauw"], "wabash": gw["wabash"]}
                disputed.append(game)
            elif kind == "date_differs":
                game["date_differs"] = True
                game["wabash_date"] = gw["date"]
                differs.append(game)
        merged.append(game)
    wabash_only = []
    for wi, gw in enumerate(w):
        if wi in wabash_for:
            continue
        game = _base(gw, "wabash")
        if wi in placeholder:
            game["date_known"] = False
        merged.append(game)
        wabash_only.append(gw)
    merged = sorted(merged, key=lambda g: g["date"])       # stable: a doubleheader stays in order
    depauw_only = [gd for di, gd in enumerate(d) if di not in pairs]

    both = len(pairs)
    stats = {"both": both, "depauw_only": len(depauw_only), "wabash_only": len(wabash_only),
             "disputed": len(disputed), "date_differs": len(differs),
             "dates_not_recorded": sum(1 for g in merged if g.get("date_known") is False)}
    result = MergeResult(merged, stats, depauw_only, wabash_only, disputed, differs)
    check(d, w, result)
    return result


def _base(g: dict, source: str) -> dict:
    game = {k: g.get(k) for k in ("date", "season", "location", "site", "result", "depauw", "wabash",
                                  "note", "boxscore")}
    game["season"] = normalize_season(g.get("season"), g["date"])
    game["source"] = source
    return game


def _fill_gaps(game: dict, other: dict) -> None:
    """DePauw's row is the base of a game both schools list. Fill what it lacks from Wabash's row."""
    if game["site"] is None and other.get("site"):
        game["site"] = other["site"]
    if game["location"] == "unknown" and other.get("location") not in (None, "unknown"):
        game["location"] = other["location"]
    for k in ("note", "boxscore"):
        if not game[k] and other.get(k):
            game[k] = other[k]


def tally(games: list) -> tuple:
    return tuple(sum(1 for g in games if g["result"] == r) for r in "WLT")


def check(depauw: list, wabash: list, result: MergeResult) -> None:
    """The merge must account for every row exactly once. Raises MergeError otherwise."""
    s = result.stats
    if s["both"] + s["depauw_only"] != len(depauw):
        raise MergeError(f"{s['both']} matched + {s['depauw_only']} DePauw only != {len(depauw)} DePauw games")
    if s["both"] + s["wabash_only"] != len(wabash):
        raise MergeError(f"{s['both']} matched + {s['wabash_only']} Wabash only != {len(wabash)} Wabash games")
    if len(result.games) != s["both"] + s["depauw_only"] + s["wabash_only"]:
        raise MergeError("merged game count does not add up")
    expected = tuple(a + b for a, b in zip(tally(depauw), tally(result.wabash_only)))
    if tally(result.games) != expected:
        raise MergeError(f"merged record {tally(result.games)} != DePauw's page plus Wabash-only games {expected}")


def near_misses(result: MergeResult) -> list:
    """Pairs among the games only one school lists that look like the same game: the same season and
    either the same score or a date within NEAR_MISS_DAYS. Nothing here is merged; a person decides."""
    out = []
    for gd in result.depauw_only:
        for gw in result.wabash_only:
            if is_placeholder(gw) or season_key(gd) != season_key(gw):
                continue
            gap = day_gap(gd["date"], gw["date"])
            same_score = score(gd) == score(gw)
            if same_score or gap <= NEAR_MISS_DAYS:
                out.append({"depauw": gd, "wabash": gw, "days": gap, "same_score": same_score})
    return sorted(out, key=lambda m: (m["depauw"]["date"], m["days"]))


def summary_line(name: str, stats: dict) -> str:
    return (f"{name}: {stats['both']} matched, {stats['depauw_only']} DePauw only, "
            f"{stats['wabash_only']} Wabash only, {stats['disputed']} disputed, "
            f"{stats['date_differs']} date-differs")
