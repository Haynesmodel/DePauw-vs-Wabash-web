"""
Numbers worked out from a sport's game list: the Monon Bell standings and (later) the per-sport fun facts.

Pure functions over the games in data/series.json (dicts with date, result, depauw, wabash, ...).
Results are from DePauw's side: "W" is a DePauw win, "L" a Wabash win, "T" a tie.
"""

from __future__ import annotations

# The football game became the Monon Bell game with the 1932 season.
BELL_START = 1932


def bell(games: list) -> dict | None:
    """The Monon Bell standings from the games played for it.

    The holder is whoever won the most recent Bell game that was not a tie: a tie leaves the Bell where
    it is. "since" is the year of the holder's first win in the unbroken run of wins and ties that
    ends today, and "held_games" counts the games in that run, split into "held_wins" and "held_ties".
    Returns None when there are no Bell games, or when none was ever decided.
    """
    played = sorted((g for g in games if int(g["date"][:4]) >= BELL_START), key=lambda g: g["date"])
    if not played:
        return None
    out = {
        "depauw": sum(1 for g in played if g["result"] == "W"),
        "wabash": sum(1 for g in played if g["result"] == "L"),
        "ties": sum(1 for g in played if g["result"] == "T"),
        "games": len(played),
        "holder": None, "since": None, "held_games": 0, "held_wins": 0, "held_ties": 0,
    }
    decided = [g for g in played if g["result"] != "T"]
    if not decided:
        return out
    holder_result = decided[-1]["result"]               # "W": DePauw holds it, "L": Wabash does
    run_start = None
    for i in range(len(played) - 1, -1, -1):
        r = played[i]["result"]
        if r == "T":
            continue
        if r != holder_result:
            break
        run_start = i
    out["holder"] = "DePauw" if holder_result == "W" else "Wabash"
    out["since"] = int(played[run_start]["date"][:4])
    out["held_games"] = len(played) - run_start
    out["held_ties"] = sum(1 for g in played[run_start:] if g["result"] == "T")
    out["held_wins"] = out["held_games"] - out["held_ties"]
    return out


# --------------------------------------------------------------------------- #
# Per-sport fun facts
# --------------------------------------------------------------------------- #

import re  # noqa: E402

# What counts as a "one-score" game in each sport: decided by this many points/runs/goals/matches or fewer.
# A sport that isn't listed gets no one-score fact rather than a guess.
ONE_SCORE = {"football": 8, "mens-basketball": 3, "baseball": 1, "mens-soccer": 1,
             "mens-lacrosse": 1, "mens-tennis": 1}
UNIT = {"points": "point", "runs": "run", "goals": "goal", "individual matches": "match"}
# Sports that meet more than once a year get a season-by-season list when at least one season in five
# has two or more games. Football (two such seasons) and soccer don't qualify; basketball, baseball and
# tennis do.
MULTI_SEASON_SHARE = 0.2
EXTRA_INNING_FROM = 10

OT_RE = re.compile(r"\b\d*\s*ot\b", re.I)
INNINGS_RE = re.compile(r"(\d+)\s*inn", re.I)


def chronological(games: list) -> list:
    return sorted(games, key=lambda g: g["date"])  # stable, so a doubleheader stays in playing order


def margin(g: dict) -> int:
    return abs(g["depauw"] - g["wabash"])


def biggest_wins(games: list, result: str) -> list:
    """Every game of DePauw's ("W") or Wabash's ("L") widest margin, oldest first."""
    wins = [g for g in chronological(games) if g["result"] == result]
    if not wins:
        return []
    best = max(margin(g) for g in wins)
    return [g for g in wins if margin(g) == best]


def biggest_win(games: list, result: str) -> dict | None:
    """The widest win for one side. When several share the margin, the most recent."""
    found = biggest_wins(games, result)
    return found[-1] if found else None


def longest_streak(games: list, result: str) -> dict | None:
    """Longest run of straight wins for one side (a tie ends a streak). "times" is how many separate runs
    reached that length; the years are those of the most recent one. Returns None for a run shorter than
    two, which isn't worth a line."""
    best, times, run = None, 0, []
    for g in chronological(games) + [None]:
        if g is not None and g["result"] == result:
            run.append(g)
            continue
        if len(run) >= 2:
            if best is None or len(run) > len(best):
                best, times = run, 1
            elif len(run) == len(best):
                best, times = run, times + 1
        run = []
    if best is None:
        return None
    return {"games": len(best), "first": best[0]["date"][:4], "last": best[-1]["date"][:4], "times": times}


def one_score_games(key: str, games: list) -> list:
    """Decided games (not ties) won by no more than the sport's one-score margin, oldest first."""
    limit = ONE_SCORE.get(key)
    if limit is None:
        return []
    return [g for g in chronological(games) if g["result"] != "T" and margin(g) <= limit]


def highest_scoring_games(games: list) -> list:
    """Every game with the most combined points/goals/runs, oldest first."""
    if not games:
        return []
    best = max(g["depauw"] + g["wabash"] for g in games)
    return [g for g in chronological(games) if g["depauw"] + g["wabash"] == best]


def highest_scoring(games: list) -> dict | None:
    """Most combined points/goals/runs in one game; the most recent when tied."""
    found = highest_scoring_games(games)
    return found[-1] if found else None


def overtime_games(games: list) -> list:
    return [g for g in chronological(games) if OT_RE.search(str(g.get("note") or ""))]


def extra_inning_games(games: list) -> list:
    """Baseball notes look like '(7 inn.)' for a shortened game; only a count past nine is extra innings."""
    out = []
    for g in chronological(games):
        m = INNINGS_RE.search(str(g.get("note") or ""))
        if m and int(m.group(1)) >= EXTRA_INNING_FROM:
            out.append(g)
    return out


def meets_more_than_once_a_year(games: list) -> bool:
    per_season: dict = {}
    for g in games:
        s = g.get("season") or g["date"][:4]
        per_season[s] = per_season.get(s, 0) + 1
    return bool(per_season) and sum(1 for n in per_season.values() if n >= 2) / len(per_season) >= MULTI_SEASON_SHARE


def season_series(games: list) -> list:
    """[(season, 'DePauw 2-0'), ...] newest first, for sports that meet more than once a year; [] otherwise."""
    if not meets_more_than_once_a_year(games):
        return []
    per_season: dict = {}
    for g in chronological(games):
        s = g.get("season") or g["date"][:4]
        rec = per_season.setdefault(s, {"W": 0, "L": 0, "T": 0})
        rec[g["result"]] += 1
    rows = []
    for season, r in per_season.items():
        tail = f"-{r['T']}" if r["T"] else ""
        if r["W"] > r["L"]:
            text = f"DePauw {r['W']}-{r['L']}{tail}"
        elif r["L"] > r["W"]:
            text = f"Wabash {r['L']}-{r['W']}{tail}"
        else:
            text = f"Split {r['W']}-{r['L']}{tail}"
        rows.append((season, text))
    return list(reversed(rows))
