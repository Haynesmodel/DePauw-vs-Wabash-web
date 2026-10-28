"""
DePauw vs. Wabash head-to-head scraper.

Reads DePauw's Sidearm "opponent history" pages (one per sport), parses every
game in the history table, checks the parsed games against the page's own
summary block (wins / losses / ties, home and away records), and writes
data/series.json.

Safety rules, so a bad night never wipes good data:
  * A sport whose page fails to load, parses to zero games, or disagrees with
    its own summary is NOT updated; the previous data for that sport is kept.
  * A sport whose game count shrinks compared with the saved file is NOT
    updated unless --allow-shrink is passed.
  * The file is only rewritten when the game data actually changed, so the
    scheduled job doesn't make empty commits.
  * Exit code is non-zero if any sport failed, so the GitHub Action shows red.
  * The "last checked" time (.checked-at, uncommitted) is written only after a live run in which
    at least one sport loaded and validated. A run where every sport failed leaves it alone.

Upcoming meetings (data/upcoming.json) come from each sport's schedule page and are separate from
the records: a schedule that fails to load or parse only logs a warning, keeps that sport's last
good entry, and never changes the exit code or the validation of the history.

Usage:
  python scraper/scrape.py                      # fetch live pages, update data/series.json
  python scraper/scrape.py --fixtures DIR       # parse saved HTML (DIR/<sport-key>.html) instead
  python scraper/scrape.py --dry-run            # parse and report, don't write
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

import upcoming

ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(__file__).resolve().parent / "sources.json"
OUTPUT = ROOT / "data" / "series.json"
UPCOMING = ROOT / "data" / "upcoming.json"
# Time of the last scrape that actually reached at least one sport. Never committed (it is
# gitignored and lives outside data/), so series.json still changes only when games change.
CHECKED_AT = ROOT / ".checked-at"

USER_AGENT = (
    "DePauw-Wabash-Series-Tracker/0.1 "
    "(fan project; fetches twice a day; contact via GitHub repo)"
)
REQUEST_GAP_SECONDS = 3  # be polite between page requests

SCORE_RE = re.compile(r"^([WLT])\s+(\d+)\s*-\s*(\d+)$")
RECORD_RE = re.compile(r"^(\d+)-(\d+)(?:-(\d+))?$")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class Game:
    date: str                      # ISO yyyy-mm-dd
    season: str
    location: str                  # "home" | "away" | "neutral" | "unknown" (DePauw's perspective)
    site: Optional[str]            # "Crawfordsville, Ind." etc., None when the page says N/A
    result: str                    # "W" | "L" | "T" for DePauw
    depauw: int
    wabash: int
    note: Optional[str] = None     # e.g. "2 OT"
    boxscore: Optional[str] = None # absolute URL when the page links one


@dataclass
class Summary:
    """The page's own summary block, used to cross-check our parse."""
    wins: Optional[int] = None
    losses: Optional[int] = None
    ties: Optional[int] = None
    home: Optional[tuple] = None
    away: Optional[tuple] = None
    streak: Optional[str] = None        # e.g. "W4", "L1"
    total: Optional[int] = None         # DePauw's total points / goals / runs, as the page reports it
    total_label: Optional[str] = None   # "points", "goals", "runs", ...


@dataclass
class SportResult:
    key: str
    name: str
    source_url: str
    total_label: str = "points"
    games: list = field(default_factory=list)
    summary: Summary = field(default_factory=Summary)
    skipped_rows: list = field(default_factory=list)


class ParseError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _parse_date(th) -> str:
    """Rows carry the date twice: '11/15/2025' (short) and 'November 15, 2025' (long)."""
    short = th.select_one("span.hide-on-medium-down")
    if short and _text(short):
        return dt.datetime.strptime(_text(short), "%m/%d/%Y").date().isoformat()
    long_ = th.select_one("span.hide-on-large")
    if long_ and _text(long_):
        return dt.datetime.strptime(_text(long_), "%B %d, %Y").date().isoformat()
    raise ParseError(f"no date in row header: {_text(th)!r}")


def _parse_record(text: str) -> Optional[tuple]:
    m = RECORD_RE.match(text.strip())
    if not m:
        return None
    w, l, t = m.groups()
    return (int(w), int(l), int(t or 0))


def parse_summary(soup: BeautifulSoup) -> Summary:
    s = Summary()
    for item in soup.select("section.sidearm-opponent-history__data .sidearm-opponent-history__item"):
        label = _text(item.find("h2")).lower()
        number = _text(item.select_one(".sidearm-opponent-history__item--number"))
        if label == "wins":
            s.wins = int(number)
        elif label == "losses":
            s.losses = int(number)
        elif label == "ties":
            s.ties = int(number)
        elif label == "home record":
            s.home = _parse_record(number)
        elif label == "away record":
            s.away = _parse_record(number)
        elif label == "streak":
            m = re.match(r"^([WLT])(\d+)$", number.replace(" ", ""))
            s.streak = m.group(0) if m else None
        elif label.startswith("total ") and number.replace(",", "").isdigit():
            s.total = int(number.replace(",", ""))
            s.total_label = label[len("total "):].strip()
    if s.wins is not None and s.ties is None:
        s.ties = 0  # the page omits the Ties box when there have never been any
    return s


def parse_page(html: str, *, base_url: str, opponent_match: str) -> tuple[list, Summary, list]:
    """Return (games, summary, skipped_rows) for one opponent-history page."""
    soup = BeautifulSoup(html, "html.parser")

    article = soup.select_one("article.sidearm-opponent-history")
    if article is None:
        raise ParseError("opponent-history article not found (layout changed or wrong page)")

    opponent = _text(article.select_one(".sidearm-opponent-history-breadcrumbs-opponent"))
    if opponent_match.lower() not in opponent.lower():
        raise ParseError(f"page is for {opponent!r}, expected an opponent matching {opponent_match!r}")

    table = article.select_one("table.sidearm-table")
    if table is None:
        raise ParseError("history table not found")

    headers = [_text(th).lower() for th in table.select("thead th")]
    for needed in ("date", "location", "score"):
        if needed not in headers:
            raise ParseError(f"history table is missing a {needed!r} column (headers: {headers})")

    games, skipped = [], []
    for row in table.select("tbody tr"):
        th = row.find("th")
        if th is None:
            continue
        date = _parse_date(th)
        season = _text(row.select_one('td[data-label="Season"]'))

        loc_cell = row.select_one("td.location")
        loc_spans = loc_cell.find_all("span") if loc_cell else []
        loc_type = _text(loc_spans[0]).lower() if loc_spans else ""
        location = loc_type if loc_type in ("home", "away", "neutral") else "unknown"
        site = _text(loc_spans[1]) if len(loc_spans) > 1 else ""
        site = None if site in ("", "N/A") else site

        score_cell = row.select_one("td.score")
        spans = score_cell.find_all("span") if score_cell else []
        post = score_cell.select_one(".post-score") if score_cell else None
        note = _text(post) or None
        score_text = _text(spans[-1]) if spans else ""
        m = SCORE_RE.match(score_text)
        if not m:
            # Canceled / postponed / no-score rows: keep a record but don't count them.
            skipped.append({"date": date, "season": season, "text": score_text or _text(score_cell)})
            continue
        result, ours, theirs = m.group(1), int(m.group(2)), int(m.group(3))

        # The cell's CSS class (score W / L / T) should agree with the text.
        classes = score_cell.get("class", [])
        if any(c in ("W", "L", "T") for c in classes) and result not in classes:
            raise ParseError(f"{date}: score text says {result} but cell class says {classes}")

        box = None
        for a in row.select(".media-list a"):
            if "boxscore" in (a.get("href") or "").lower():
                href = a["href"]
                box = href if href.startswith("http") else base_url.rstrip("/") + href
                break

        games.append(Game(date=date, season=season, location=location, site=site,
                          result=result, depauw=ours, wabash=theirs, note=note, boxscore=box))

    return games, parse_summary(soup), skipped


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def tally(games: list) -> dict:
    out = {"W": 0, "L": 0, "T": 0}
    by_loc: dict = {}
    for g in games:
        out[g.result] += 1
        rec = by_loc.setdefault(g.location, [0, 0, 0])
        rec["WLT".index(g.result)] += 1
    return {"wins": out["W"], "losses": out["L"], "ties": out["T"],
            "by_location": {k: tuple(v) for k, v in by_loc.items()}}


def chronological(games: list) -> list:
    """Oldest first. The page lists games newest first, so reversing before the (stable) date sort
    keeps a doubleheader in playing order: game 1, then game 2."""
    return sorted(reversed(games), key=lambda g: g.date)


def streak_code(games: list) -> str:
    """Current streak from DePauw's side, e.g. "W4". Expects games oldest first."""
    r, n = games[-1].result, 0
    for g in reversed(games):
        if g.result != r:
            break
        n += 1
    return f"{r}{n}"


def validate(games: list, summary: Summary) -> list:
    """Return a list of problems (empty list means the parse agrees with the page)."""
    problems = []
    if not games:
        problems.append("parsed zero games")
        return problems
    t = tally(games)
    for k in ("wins", "losses", "ties"):
        page_val = getattr(summary, k)
        if page_val is None:
            problems.append(f"page summary has no {k} figure")
        elif page_val != t[k]:
            problems.append(f"{k}: parsed {t[k]}, page says {page_val}")
    for loc in ("home", "away"):
        page_rec = getattr(summary, loc)
        mine = t["by_location"].get(loc, (0, 0, 0))
        if page_rec is not None and tuple(page_rec) != tuple(mine):
            problems.append(f"{loc} record: parsed {'-'.join(map(str, mine))}, "
                            f"page says {'-'.join(map(str, page_rec))}")
    if summary.streak is not None and streak_code(chronological(games)) != summary.streak:
        problems.append(f"streak: parsed {streak_code(chronological(games))}, page says {summary.streak}")
    # Doubleheaders put two real games on one date, sometimes with the same score, so a repeated
    # date and score is not a duplicate by itself. A page that really repeats rows is caught by a
    # box-score link appearing on two rows, by three or more identical games on one date, and by
    # the tally check above (repeated rows make the totals disagree with the page's summary).
    boxes = [g.boxscore for g in games if g.boxscore]
    if len(set(boxes)) != len(boxes):
        problems.append("duplicate game rows (the same box score appears on more than one row)")
    same_day = Counter((g.date, g.depauw, g.wabash) for g in games)
    if any(n > 2 for n in same_day.values()):
        problems.append("duplicate game rows (three or more identical games on one date)")
    return problems


# --------------------------------------------------------------------------- #
# Fetching and output
# --------------------------------------------------------------------------- #

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def fetch(url: str) -> str:
    import requests  # imported here so fixture runs and tests don't need it
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def scrape_schedules(cfg: dict, previous: dict, fixtures: Optional[Path]) -> dict:
    """Upcoming Wabash games per sport. Never raises: a schedule problem is a warning, and the
    sport keeps whatever it had before."""
    sports = dict(previous)
    first = True
    for sport in cfg["sports"]:
        key, path = sport["key"], sport.get("schedule_path")
        if not path:
            continue
        url = cfg["base_url"].rstrip("/") + path
        try:
            if fixtures:
                page = fixtures / f"{key}-schedule.html"
                if not page.exists():
                    continue
                html = page.read_text(encoding="utf-8")
            else:
                if not first:
                    time.sleep(REQUEST_GAP_SECONDS)
                first = False
                html = fetch(url)
            games = upcoming.parse_schedule(html, opponent_id=cfg["opponent_id"])
            sports[key] = {"schedule_url": url, "games": games}
            print(f"OK   {sport['name']:<16} schedule: {len(games)} game(s) not yet played")
        except Exception as exc:  # a schedule problem must never block the records
            print(f"WARN {sport['name']:<16} schedule not updated: {exc}", file=sys.stderr)
    return {k: sports[k] for k in (s["key"] for s in cfg["sports"]) if k in sports}


def sport_payload(sr: SportResult) -> dict:
    games = chronological(sr.games)
    t = tally(games)
    first = games[0] if games else None
    last = games[-1] if games else None
    # Current streak, from DePauw's perspective.
    streak = streak_code(games) if games else None
    return {
        "name": sr.name,
        "source_url": sr.source_url,
        "record": {"depauw_wins": t["wins"], "wabash_wins": t["losses"], "ties": t["ties"]},
        "games_played": len(games),
        "first_game": first.date if first else None,
        "last_game": last.date if last else None,
        "current_streak": streak,
        "points": {"depauw": sum(g.depauw for g in games), "wabash": sum(g.wabash for g in games)},
        "total_label": sr.total_label,
        "games": [asdict(g) for g in games],
        "skipped_rows": sr.skipped_rows,
    }


def build_output(sports: dict, previous: dict) -> dict:
    totals = {"depauw_wins": 0, "wabash_wins": 0, "ties": 0, "games_played": 0}
    for s in sports.values():
        totals["depauw_wins"] += s["record"]["depauw_wins"]
        totals["wabash_wins"] += s["record"]["wabash_wins"]
        totals["ties"] += s["record"]["ties"]
        totals["games_played"] += s["games_played"]
    return {
        "schema_version": 1,
        "updated_at": previous.get("updated_at"),
        "perspective": "DePauw",
        "totals": totals,
        "sports": sports,  # in sources.json order, which is the order the page shows
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", type=Path, help="read <dir>/<sport-key>.html instead of fetching")
    ap.add_argument("--output", type=Path, default=OUTPUT)
    ap.add_argument("--upcoming-output", type=Path, default=UPCOMING)
    ap.add_argument("--checked-file", type=Path, default=CHECKED_AT,
                    help="where to record the time of a successful live check")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="accept a sport whose game count went down")
    args = ap.parse_args(argv)

    cfg = json.loads(SOURCES.read_text())
    previous = json.loads(args.output.read_text()) if args.output.exists() else {}
    prev_sports = previous.get("sports", {})

    new_sports: dict = {}
    failures = []

    for i, sport in enumerate(cfg["sports"]):
        key = sport["key"]
        url = cfg["base_url"].rstrip("/") + sport["path"]
        try:
            if args.fixtures:
                html = (args.fixtures / f"{key}.html").read_text()
            else:
                if i:
                    time.sleep(REQUEST_GAP_SECONDS)
                html = fetch(url)
            games, summary, skipped = parse_page(html, base_url=cfg["base_url"],
                                                 opponent_match=cfg["opponent_match"])
            problems = validate(games, summary)
            if problems:
                raise ParseError("; ".join(problems))
            old_count = prev_sports.get(key, {}).get("games_played", 0)
            if len(games) < old_count and not args.allow_shrink:
                raise ParseError(f"game count fell from {old_count} to {len(games)}; "
                                 f"rerun with --allow-shrink if that's expected")
            # sources.json can override the label (tennis: the page's "points" are individual matches).
            label = sport.get("total_label") or summary.total_label or "points"
            sr = SportResult(key=key, name=sport["name"], source_url=url, total_label=label,
                             games=games, summary=summary, skipped_rows=skipped)
            new_sports[key] = sport_payload(sr)
            t = new_sports[key]["record"]
            print(f"OK   {sport['name']:<16} {len(games):>3} games  "
                  f"DePauw {t['depauw_wins']}-{t['wabash_wins']}-{t['ties']}"
                  + (f"  ({len(skipped)} non-score rows skipped)" if skipped else ""))
        except Exception as exc:  # keep going; one bad sport shouldn't block the rest
            failures.append(key)
            print(f"FAIL {sport['name']:<16} {exc}", file=sys.stderr)
            if key in prev_sports:
                new_sports[key] = prev_sports[key]  # keep last known-good data

    out = build_output(new_sports, previous)
    changed = (json.dumps(out["sports"], sort_keys=True) != json.dumps(prev_sports, sort_keys=True)
               or list(out["sports"]) != list(prev_sports))  # a reorder in sources.json also counts
    tot = out["totals"]
    print(f"All sports: DePauw {tot['depauw_wins']}-{tot['wabash_wins']}-{tot['ties']} "
          f"over {tot['games_played']} games. Data {'changed' if changed else 'unchanged'}.")

    if changed and not args.dry_run:
        out["updated_at"] = now_utc().isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2) + "\n")
        print(f"Wrote {args.output}")

    old_upcoming = json.loads(args.upcoming_output.read_text()) if args.upcoming_output.exists() else {}
    new_upcoming = scrape_schedules(cfg, old_upcoming.get("sports", {}), args.fixtures)
    if new_upcoming != old_upcoming.get("sports", {}) and not args.dry_run:
        args.upcoming_output.parent.mkdir(parents=True, exist_ok=True)
        args.upcoming_output.write_text(
            json.dumps({"schema_version": 1, "sports": new_upcoming}, indent=2) + "\n")
        print(f"Wrote {args.upcoming_output}")

    # A fixture run or a dry run is not a check of the live site, and a run where every sport failed
    # proves nothing about the data, so only a real run with at least one good sport advances the time.
    if len(failures) < len(cfg["sports"]) and not args.fixtures and not args.dry_run:
        args.checked_file.write_text(now_utc().isoformat() + "\n")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
