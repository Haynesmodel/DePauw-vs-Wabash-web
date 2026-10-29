"""
Merging DePauw's and Wabash's records of the same series into one history per sport.

Both athletics sites run the same Sidearm "opponent history" page. Each school's page is parsed and
validated on its own (scrape.py); this module only matches the two game lists and combines them.
Everything here is from DePauw's point of view: Wabash's games are flipped first (flip()).

Matching runs in fixed passes, and every pass uses each row at most once. A row is never paired with a
row a ruling in data/overrides.json says is a different game.
  0. Rulings in data/overrides.json: games a person confirmed are the same game, and rows a person ruled
     are only days of a longer meet (session_of): those are set aside, not counted as games.
  1. Same date and same score.
  2. Rows with no usable date match by season and score. A date is unusable when it is a placeholder
     (a Wabash row on Jan 1 to Jan 3) or falls in a month the sport is not played (season_months).
     The usable date, if either row has one, is the game's date.
  3. Dates within MAX_DATE_GAP_DAYS of each other with the same score: one game, flagged date_differs.
  4. Same date, different score or result: one disputed game.
  5. Dates within MAX_DATE_GAP_DAYS, the same winner and scores within SCORE_TOLERANCE of each other:
     one disputed game, also flagged date_differs.
  6. Dates further apart with the same score, only when the dates differ by a single-field typo (the
     year off by one, the month off by one with the same day, or one digit wrong in the day): one game,
     flagged date_differs.
Several games on one date (doubleheaders) pair by score first, then by order on the page.
What is left is a game only one school lists; it still counts, and says whose record it is from.
A disputed game counts DePauw's version; Wabash's is kept for display.

Why each rule exists, what it risks, why the numbers are what they are, and how to change them
safely are written up in the README ("Why the merge works this way"). Keep the two in step.

Rows that differ in both date and score cannot be told from two separate games, so they stay separate
unless a ruling says otherwise. near_misses() lists such pairs so a person can check them.

Each merged game is a dict with the fields of a game in series.json plus:
  source          "both", "depauw" or "wabash"
  date_known      False when no usable date was available (omitted when True); "date" is then not shown
  disputed        True when the two schools disagree on the score or result (omitted otherwise)
  wabash_version  Wabash's {result, depauw, wabash} for a disputed game, in DePauw's point of view
  date_differs    True when the two schools list the game on different dates (omitted otherwise)
  wabash_date     Wabash's date for such a game
  score_known     False when the school lists the result but no score (omitted when True); depauw and wabash
                  are then null, and the game counts in the record but in no point total
  score_order_reversed  ["Wabash"] etc.: the school's page printed the two scores in the other order from
                  its result letter; the letter was trusted and the scores swapped (omitted otherwise)
  sessions        the running-score rows a session_of ruling set aside, on the meet they belong to
  depauw_date     DePauw's date, only when DePauw's was unusable and Wabash's date was used instead
A disputed game can also have different dates. Games are stored oldest first; games with no usable date
come first within their season, in the order the school's page listed them.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_DATE_GAP_DAYS = 2
SCORE_TOLERANCE = 3       # how far each side's score may differ (points, runs, goals) in a near-date dispute
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


def norm_num(x):
    """A sum or a score as the number it is: 4459.0 is 4459, 4459.5 stays 4459.5."""
    return int(x) if isinstance(x, float) and x.is_integer() else x


def score_known(g: dict) -> bool:
    return g.get("score_known", True)


def score(g: dict) -> tuple:
    return (g["depauw"], g["wabash"])


def score_distance(a: dict, b: dict) -> float:
    """How far apart two games' scores are. A game with no score is as far from a scored game as can be,
    and no distance from another game with no score."""
    if not (score_known(a) and score_known(b)):
        return 0 if score_known(a) == score_known(b) else 10 ** 6
    return abs(a["depauw"] - b["depauw"]) + abs(a["wabash"] - b["wabash"])


def typo_kind(a: str, b: str) -> str | None:
    """How two different dates could be one date with a single typo: "year" (off by one, same month and
    day), "month" (off by one, same year and day) or "day" (same year and month, exactly one of the two
    day digits wrong). None when the dates differ in any other way."""
    ya, ma, da = (int(x) for x in a.split("-"))
    yb, mb, db = (int(x) for x in b.split("-"))
    if (ma, da) == (mb, db) and abs(ya - yb) == 1:
        return "year"
    if (ya, da) == (yb, db) and abs(ma - mb) == 1:
        return "month"
    if (ya, ma) == (yb, mb) and da != db:
        if sum(x != y for x, y in zip(f"{da:02d}", f"{db:02d}")) == 1:
            return "day"
    return None


# --------------------------------------------------------------------------- #
# Rulings (data/overrides.json)
# --------------------------------------------------------------------------- #

def load_overrides(path: Path) -> dict:
    """The per-sport rulings, {sport key: {"same_game": [...], "different_games": [...], "session_of": [...]}}. ("keep_previous"
    rulings, which reject a school's edit to an old game, are read by review.load_keep_previous and take no
    part in the merge.) A missing file is no rulings. A malformed file raises MergeError, because a typo must not silently turn rulings off."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise MergeError(f"{path.name} is not valid JSON: {exc}") from None
    sports = data.get("sports") if isinstance(data, dict) else None
    if not isinstance(sports, dict):
        raise MergeError(f'{path.name} needs a "sports" object')
    out = {}
    for key, rules in sports.items():
        if not isinstance(rules, dict) or set(rules) - {"same_game", "different_games", "session_of", "keep_previous"}:
            raise MergeError(f'{path.name}: {key} may only have "same_game", "different_games", "session_of" '
                             f'and "keep_previous"')
        out[key] = {kind: [_ruling(path.name, key, kind, r) for r in rules.get(kind, [])]
                    for kind in ("same_game", "different_games")}
        out[key]["session_of"] = [_session_ruling(path.name, key, r) for r in rules.get("session_of", [])]
    return out


SCORE_PAIR = re.compile(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)")


def _row(r: dict) -> dict:
    """A ruling's name for one row: that school's date and the score as DePauw-Wabash ("12-5", "147.5-143.5")."""
    return {"date": dt.date.fromisoformat(r["date"]).isoformat(),
            "score": tuple(norm_num(float(x)) for x in SCORE_PAIR.fullmatch(r["score"]).groups())}


def _ruling(name: str, key: str, kind: str, r) -> dict:
    try:
        parsed = {side: _row(r[side]) for side in ("depauw", "wabash")}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MergeError(f'{name}: {key} {kind}: each ruling needs "depauw" and "wabash", each with a '
                         f'"date" (YYYY-MM-DD) and a "score" ("DePauw-Wabash", e.g. "12-5"): {r!r}') from None
    parsed["reason"] = r.get("reason", "")
    return parsed


def _session_ruling(name: str, key: str, r) -> dict:
    """A session_of ruling: one school's rows ("sessions") that are only parts of one meet ("meet", also a
    row of that school's page). The sessions are set aside; the meet is matched like any other game."""
    try:
        if r["school"] not in ("depauw", "wabash"):
            raise ValueError
        parsed = {"school": r["school"], "meet": _row(r["meet"]),
                  "sessions": [_row(x) for x in r["sessions"]]}
        if not parsed["sessions"] or any(x["date"] > parsed["meet"]["date"] for x in parsed["sessions"]):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MergeError(f'{name}: {key} session_of: each ruling needs a "school" ("depauw" or "wabash"), a '
                         f'"meet" and a non-empty list of "sessions" (each a "date" and a "score" '
                         f'"DePauw-Wabash"; no session may be dated after the meet): {r!r}') from None
    parsed["reason"] = r.get("reason", "")
    parsed["sources"] = list(r.get("sources", []))
    return parsed


def _identity(g: dict) -> tuple:
    return (g["date"], score(g))


def _ruled(side: dict) -> tuple:
    return (side["date"], side["score"])


# --------------------------------------------------------------------------- #
# The merge
# --------------------------------------------------------------------------- #

@dataclass
class MergeResult:
    games: list
    stats: dict
    depauw_only: list = field(default_factory=list)   # the DePauw rows nobody else lists
    wabash_only: list = field(default_factory=list)
    disputed: list = field(default_factory=list)      # (merged game) for each dispute
    date_differs: list = field(default_factory=list)  # (merged game) for each date mismatch
    pairs: list = field(default_factory=list)         # {"kind", "depauw", "wabash", "gap"} for each match
    sessions: list = field(default_factory=list)      # the rows a session_of ruling set aside


def _stale(r: dict, kind: str, missing_depauw: bool, missing_wabash: bool) -> str:
    """The error for a ruling whose rows are gone: which ruling, and which school's row cannot be found."""
    d, w = r["depauw"], r["wabash"]
    gone = " and ".join(name for name, m in (("DePauw", missing_depauw), ("Wabash", missing_wabash)) if m)
    return (f"overrides.json {kind} ruling no longer finds {gone}'s row: DePauw {d['date']} "
            f"{d['score'][0]}-{d['score'][1]} / Wabash {w['date']} {w['score'][0]}-{w['score'][1]}"
            f" (a source page changed, or the ruling was mistyped)")


def _pair(edges: list, used_d: set, used_w: set, take) -> None:
    """Take pairs from the cheapest edge up, never using a row twice. An edge is (cost..., di, wi)."""
    for edge in sorted(edges):
        di, wi = edge[-2], edge[-1]
        if di in used_d or wi in used_w:
            continue
        used_d.add(di)
        used_w.add(wi)
        take(di, wi)


def merge_sport(depauw: list, wabash: list, *, season_months=None, rules=None) -> MergeResult:
    """Merge DePauw's games with Wabash's (already flipped). Both lists are oldest first, with a
    doubleheader in playing order. season_months is the months the sport is played in (None: any month
    is plausible); rules is this sport's entry from load_overrides(). Raises MergeError if the
    bookkeeping does not add up."""
    months = set(season_months) if season_months else None
    rules = rules or {}
    d, w, set_aside, attach = _set_aside_sessions(depauw, wabash, rules.get("session_of", []))
    used_d: set = set()
    used_w: set = set()
    pairs: dict = {}                       # di -> (wi, kind)

    def take(kind):
        def _take(di, wi):
            pairs[di] = (wi, kind)
        return _take

    different = {(_ruled(r["depauw"]), _ruled(r["wabash"])) for r in rules.get("different_games", [])}

    def allowed(gd, gw) -> bool:
        return (_identity(gd), _identity(gw)) not in different

    # A ruling that no longer finds both rows it names means a source page changed under it. Stop
    # rather than let a ruling silently stop applying (or keep a game counted twice).
    for r in rules.get("different_games", []):
        has_d = any(_identity(g) == _ruled(r["depauw"]) for g in d)
        has_w = any(_identity(g) == _ruled(r["wabash"]) for g in w)
        if not (has_d and has_w):
            raise MergeError(_stale(r, "different_games", not has_d, not has_w))

    # 0. rulings: games a person confirmed are the same game
    for r in rules.get("same_game", []):
        di = next((i for i, g in enumerate(d) if i not in used_d and _identity(g) == _ruled(r["depauw"])), None)
        wi = next((i for i, g in enumerate(w) if i not in used_w and _identity(g) == _ruled(r["wabash"])), None)
        if di is None or wi is None:
            raise MergeError(_stale(r, "same_game", di is None, wi is None))
        used_d.add(di)
        used_w.add(wi)
        pairs[di] = (wi, "ruling")

    # 1. same date, same score
    edges = [(0, di, wi) for di, gd in enumerate(d) if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w
             and gd["date"] == gw["date"] and score(gd) == score(gw) and allowed(gd, gw)]
    _pair(edges, used_d, used_w, take("exact"))

    # A date is unusable when it is a placeholder or falls outside the months the sport is played in.
    def out_of_season(g) -> bool:
        return months is not None and int(g["date"][5:7]) not in months

    unknown_d = {di for di, gd in enumerate(d) if di not in used_d and out_of_season(gd)}
    unknown_w = {wi for wi, gw in enumerate(w)
                 if wi not in used_w and (is_placeholder(gw) or out_of_season(gw))}

    # 2. rows with no usable date: same season, same score
    edges = [(day_gap(gd["date"], gw["date"]), di, wi)
             for di, gd in enumerate(d) if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w
             and (di in unknown_d or wi in unknown_w)
             and season_key(gd) == season_key(gw) and score(gd) == score(gw) and allowed(gd, gw)]
    _pair(edges, used_d, used_w, take("no_date"))

    live = [(di, gd) for di, gd in enumerate(d) if di not in used_d and di not in unknown_d]

    # 3. dates a day or two apart, same score
    edges = [(day_gap(gd["date"], gw["date"]), di, wi)
             for di, gd in live
             for wi, gw in enumerate(w) if wi not in used_w and wi not in unknown_w
             and score(gd) == score(gw) and 0 < day_gap(gd["date"], gw["date"]) <= MAX_DATE_GAP_DAYS
             and allowed(gd, gw)]
    _pair(edges, used_d, used_w, take("near_date"))

    # 4. same date, different score or result: a dispute (the exact pass already took equal scores)
    edges = [(score_distance(gd, gw), di, wi)
             for di, gd in live if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w and wi not in unknown_w
             and gd["date"] == gw["date"] and allowed(gd, gw)]
    _pair(edges, used_d, used_w, take("disputed"))

    # 5. a day or two apart, same winner, close scores: a dispute over the score and the date
    edges = [(day_gap(gd["date"], gw["date"]), score_distance(gd, gw), di, wi)
             for di, gd in live if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w and wi not in unknown_w
             and 0 < day_gap(gd["date"], gw["date"]) <= MAX_DATE_GAP_DAYS and gd["result"] == gw["result"]
             and score_known(gd) and score_known(gw)
             and abs(gd["depauw"] - gw["depauw"]) <= SCORE_TOLERANCE
             and abs(gd["wabash"] - gw["wabash"]) <= SCORE_TOLERANCE and allowed(gd, gw)]
    _pair(edges, used_d, used_w, take("near_dispute"))

    # 6. further apart than the window, same score, and the dates differ by one typo
    edges = [(day_gap(gd["date"], gw["date"]), di, wi)
             for di, gd in live if di not in used_d
             for wi, gw in enumerate(w) if wi not in used_w and wi not in unknown_w
             and score(gd) == score(gw) and day_gap(gd["date"], gw["date"]) > MAX_DATE_GAP_DAYS
             and typo_kind(gd["date"], gw["date"]) and allowed(gd, gw)]
    _pair(edges, used_d, used_w, take("typo"))

    wabash_for = {wi: di for di, (wi, _) in pairs.items()}
    for_meet = attach
    merged: list = []
    matches: list = []
    disputed, differs = [], []
    for di, gd in enumerate(d):
        game = _base(gd, "depauw")
        game["_order"] = (0, di)
        if di in pairs:
            wi, kind = pairs[di]
            gw = w[wi]
            _combine(game, gd, gw, di in unknown_d, wi in unknown_w)
            if sessions := for_meet.get(("depauw", di)) or for_meet.get(("wabash", wi)):
                game["sessions"] = sessions
            placeholder = wi in unknown_w and is_placeholder(gw)
            matches.append({"kind": kind, "depauw": gd, "wabash": gw,
                            "gap": None if placeholder else day_gap(gd["date"], gw["date"])})
            if game.get("disputed"):
                disputed.append(game)
            if game.get("date_differs"):
                differs.append(game)
        elif di in unknown_d:
            game["date_known"] = False
        merged.append(game)
    wabash_only = []
    for wi, gw in enumerate(w):
        if wi in wabash_for:
            continue
        game = _base(gw, "wabash")
        game["_order"] = (1, wi)
        if sessions := for_meet.get(("wabash", wi)):
            game["sessions"] = sessions
        if wi in unknown_w:
            game["date_known"] = False
        merged.append(game)
        wabash_only.append(gw)
    merged = _in_order(merged)
    depauw_only = [gd for di, gd in enumerate(d) if di not in pairs]

    stats = {"both": len(pairs), "depauw_only": len(depauw_only), "wabash_only": len(wabash_only),
             "disputed": len(disputed), "date_differs": len(differs),
             "dates_not_recorded": sum(1 for g in merged if g.get("date_known") is False)}
    if set_aside:
        stats["session_rows"] = len(set_aside)
    result = MergeResult(merged, stats, depauw_only, wabash_only, disputed, differs, matches, set_aside)
    check(d, w, result)
    return result


def _set_aside_sessions(depauw: list, wabash: list, rulings: list) -> tuple:
    """Take the rows session_of rulings name out of the school's list. Returns (DePauw rows, Wabash rows,
    the rows set aside, {(school, index of the meet in the remaining rows): [session summaries]}).
    A ruling that no longer finds every row it names raises MergeError, like any other ruling."""
    lists = {"depauw": list(depauw), "wabash": list(wabash)}
    aside, named = [], []
    for r in rulings:
        rows = lists[r["school"]]
        found = []
        for want in r["sessions"]:
            i = next((k for k, g in enumerate(rows) if _identity(g) == _ruled(want) and k not in found), None)
            found.append(i)
        meet = next((k for k, g in enumerate(rows) if _identity(g) == _ruled(r["meet"])), None)
        if meet is None or None in found:
            gone = ([f"the meet {r['meet']['date']} {r['meet']['score'][0]}-{r['meet']['score'][1]}"] if meet is None else []) \
                + [f"the session {w['date']} {w['score'][0]}-{w['score'][1]}" for w, i in zip(r["sessions"], found) if i is None]
            raise MergeError(f"overrides.json session_of ruling no longer finds {' and '.join(gone)} on "
                             f"{r['school'].title()}'s page (a source page changed, or the ruling was mistyped)")
        named.append((r, meet, found))
    attach, drop = {}, {"depauw": set(), "wabash": set()}
    for r, meet, found in named:
        sessions = []
        for i in found:
            g = lists[r["school"]][i]
            drop[r["school"]].add(i)
            aside.append({**g, "school": r["school"].title()})
            sessions.append({"date": g["date"], "depauw": g["depauw"], "wabash": g["wabash"],
                             "school": r["school"].title()})
        attach[(r["school"], meet)] = sorted(sessions, key=lambda x: x["date"])
    # indexes in `attach` must point into the remaining rows, so renumber after the rows are removed
    out, remap = {}, {}
    for school, rows in lists.items():
        keep = [k for k in range(len(rows)) if k not in drop[school]]
        remap[school] = {old: new for new, old in enumerate(keep)}
        out[school] = [rows[k] for k in keep]
    attach = {(school, remap[school][i]): v for (school, i), v in attach.items()}
    return out["depauw"], out["wabash"], aside, attach


def _combine(game: dict, gd: dict, gw: dict, d_unknown: bool, w_unknown: bool) -> None:
    """Fill a merged game from DePauw's row and Wabash's: the date to use, then what the schools disagree on."""
    game["source"] = "both"
    _fill_gaps(game, gw)
    if d_unknown and w_unknown:
        game["date_known"] = False
    elif d_unknown:
        game["date"] = gw["date"]                      # DePauw's date was unusable; Wabash's is in season
        if gd["date"] != gw["date"]:
            game["depauw_date"] = gd["date"]
            game["date_differs"] = True
    elif gw["date"] != gd["date"] and not (w_unknown and is_placeholder(gw)):
        game["date_differs"] = True                    # a placeholder says nothing about the date; anything else does
        game["wabash_date"] = gw["date"]
    if score_known(gd) and score_known(gw):
        differ = (gd["depauw"], gd["wabash"], gd["result"]) != (gw["depauw"], gw["wabash"], gw["result"])
    else:
        # A school that lists no score for the meet cannot disagree about it: only the result can differ.
        differ = gd["result"] != gw["result"]
        if not score_known(gd) and score_known(gw):
            game["depauw"], game["wabash"] = gw["depauw"], gw["wabash"]      # the other school has the score
            game.pop("score_known", None)
    if differ:
        game["disputed"] = True
        game["wabash_version"] = {"result": gw["result"], "depauw": gw["depauw"], "wabash": gw["wabash"]}
    if gw.get("score_order_reversed"):
        game["score_order_reversed"] = sorted(set(game.get("score_order_reversed", [])) | {"Wabash"})


def _in_order(games: list) -> list:
    """Oldest first. A game with no usable date goes first within its season (before that season's dated
    games), in the order its school's page listed it, so it never poses as a game on a particular day."""
    first_dated: dict = {}
    for g in games:
        if g.get("date_known") is not False:
            k = season_key(g)
            first_dated[k] = min(first_dated.get(k, g["date"]), g["date"])

    def key(g):
        if g.get("date_known") is False:
            first, last = season_years(g.get("season"), g["date"])
            fallback = f"{first}-01-01" if first == last else f"{first}-07-01"
            return (first_dated.get(season_key(g), fallback), 0, g["_order"])
        return (g["date"], 1, g["_order"])

    out = sorted(games, key=key)
    for g in out:
        del g["_order"]
    return out


def _base(g: dict, source: str) -> dict:
    game = {k: g.get(k) for k in ("date", "season", "location", "site", "result", "depauw", "wabash",
                                  "note", "boxscore")}
    game["season"] = normalize_season(g.get("season"), g["date"])
    game["source"] = source
    if not score_known(g):
        game["score_known"] = False
    if g.get("score_order_reversed"):
        game["score_order_reversed"] = ["DePauw" if source == "depauw" else "Wabash"]
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


def beyond_window(result: MergeResult) -> list:
    """Matches whose two dates are more than MAX_DATE_GAP_DAYS apart, for a person to review. A match to a
    placeholder date is not listed: that date says nothing."""
    return [m for m in result.pairs if m["gap"] is not None and m["gap"] > MAX_DATE_GAP_DAYS]


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
