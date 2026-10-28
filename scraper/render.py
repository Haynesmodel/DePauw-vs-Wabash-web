"""
Static site generator for the DePauw vs. Wabash page.

Reads data/series.json (and, if present, data/upcoming.json and the uncommitted .checked-at)
and writes a finished site to site/: index.html, 404.html, styles.css, the icons and og-image.png
(drawn by images.py), site.webmanifest, games.csv, data/series.json, robots.txt, sitemap.xml,
.nojekyll. No client-side JavaScript; Pillow is needed only for the images.

Every figure on the page comes from the data file. Anything missing or inconsistent
raises DataError and the script exits non-zero, so a bad data file can never produce
a blank or half-true page.

Usage:
  python scraper/render.py                      # data/series.json -> site/
  python scraper/render.py --data FILE --out DIR
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import io
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

import facts
import images
import meetings

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "series.json"
STATIC = ROOT / "static"
OUT = ROOT / "site"
UPCOMING = ROOT / "data" / "upcoming.json"
CHECKED_AT = ROOT / ".checked-at"  # written by scrape.py after a live run; never committed

SITE_URL = "https://depauwvswabash.com/"
BASE_PATH = urlparse(SITE_URL).path  # "/" on the custom domain
REPO_URL = "https://github.com/jacksonmote/DePauw-vs-Wabash-web"
SOURCE_HOST = "depauwtigers.com"
# Where DePauw's games vs. Wabash are played when the source gives no site (neutral sites are never guessed).
HOME_SITE = "Greencastle, Ind."
AWAY_SITE = "Crawfordsville, Ind."

TITLE = "DePauw University vs. Wabash College: All-Time Head-to-Head Records"
SUBTITLE = "DePauw University vs. Wabash College: all-time head-to-head records in men’s sports."
NOT_INCLUDED = ("cross country, track and field, swimming and diving, and golf. "
                "They are multi-team events rather than head-to-head games.")
DISCLAIMER = "Unofficial fan site, not affiliated with DePauw University or Wabash College."

BELL_URL = "https://en.wikipedia.org/wiki/Monon_Bell"
# Written in our own words. It holds no record, streak or other figure that changes: those come from the data.
BELL_HISTORY = (
    "The Monon Bell is a 300-pound locomotive bell that once rode on a Monon Railroad engine. "
    f"Starting with the {facts.BELL_START} season it became the traveling trophy for the DePauw–Wabash "
    "football game, an idea credited to a DePauw alumnus. The winner takes the Bell home until the next "
    "meeting, and if the game ends in a tie, the team that already has it keeps it. Students from both "
    "schools have also stolen and hidden the Bell many times over the years, which is now part of the lore."
)

CSP = ("default-src 'none'; style-src 'self'; img-src 'self'; manifest-src 'self'; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STREAK_RE = re.compile(r"^([WLT])(\d+)$")


class DataError(Exception):
    """The data file is missing, empty or inconsistent."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def esc(value) -> str:
    return html.escape(str(value), quote=True)


def safe_url(url) -> str | None:
    """Only link to https pages on the source site; drop anything else (javascript:, http:, other hosts)."""
    if not isinstance(url, str):
        return None
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in (SOURCE_HOST, "www." + SOURCE_HOST):
        return None
    return url


def report_url(sport_name: str | None = None) -> str:
    """Opens the data-correction issue form, with the sport filled in when the link comes from a card."""
    query = "template=data-correction.yml"
    if sport_name:
        query += f"&title={quote('Data correction: ' + sport_name)}&sport={quote(sport_name)}"
    return f"{REPO_URL}/issues/new?{query}"


def report_link(sport_name: str | None = None) -> str:
    return f'<a href="{esc(report_url(sport_name))}">Report a data error</a>'


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def fmt_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}"


def _nth_sunday(year: int, month: int, n: int) -> int:
    first = dt.date(year, month, 1)
    return 1 + (6 - first.weekday()) % 7 + 7 * (n - 1)


def to_eastern(utc: dt.datetime) -> tuple[dt.datetime, str]:
    """UTC -> US Eastern with the current US DST rule (second Sunday of March to first
    Sunday of November). Hand-coded because zoneinfo needs the tzdata package on Windows."""
    utc = utc.astimezone(dt.timezone.utc)
    y = utc.year
    start = dt.datetime(y, 3, _nth_sunday(y, 3, 2), 7, tzinfo=dt.timezone.utc)   # 2:00 EST
    end = dt.datetime(y, 11, _nth_sunday(y, 11, 1), 6, tzinfo=dt.timezone.utc)   # 2:00 EDT
    if start <= utc < end:
        return utc + dt.timedelta(hours=-4), "EDT"
    return utc + dt.timedelta(hours=-5), "EST"


def fmt_stamp(iso: str, now: dt.datetime) -> str:
    """Short Eastern-time stamp for the footer: 'Oct 27, 11:48 PM', with the year only when it isn't this year."""
    local, _ = to_eastern(dt.datetime.fromisoformat(iso))
    hour = local.hour % 12 or 12
    year = f", {local.year}" if local.year != to_eastern(now)[0].year else ""
    return f"{MONTHS[local.month - 1][:3]} {local.day}{year}, {hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def read_checked(path: Path | None) -> str | None:
    """The time of the last successful scrape, or None when there is no (valid) record of one.
    A build without a recorded check (a PR check, or a run where every sport failed) simply
    leaves 'Last checked' off the page instead of showing the build time."""
    if path is None:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
        stamp = dt.datetime.fromisoformat(text)
    except (OSError, ValueError):
        return None
    return text if stamp.tzinfo is not None else None


def streak_text(code: str) -> str:
    kind, n = STREAK_RE.match(code).groups()
    n = int(n)
    if kind == "W":
        return "DePauw won the last meeting" if n == 1 else f"DePauw has won {n} straight"
    if kind == "L":
        return "Wabash won the last meeting" if n == 1 else f"Wabash has won {n} straight"
    return "The last meeting ended in a tie" if n == 1 else f"The last {n} meetings ended in ties"


def derive_streak(games: list) -> str:
    last = games[-1]["result"]
    n = 0
    for g in reversed(games):
        if g["result"] != last:
            break
        n += 1
    return f"{last}{n}"


def score_text(g: dict) -> str:
    """Winner first: 'DePauw 41, Wabash 20', 'Wabash 24, DePauw 17', 'Tie 7–7'."""
    d, w = g["depauw"], g["wabash"]
    if g["result"] == "W":
        return f"DePauw {d}, Wabash {w}"
    if g["result"] == "L":
        return f"Wabash {w}, DePauw {d}"
    return f"Tie {d}–{w}"


def where_text(g: dict) -> str:
    label = {"home": "Home", "away": "Away", "neutral": "Neutral"}.get(g["location"], "Site unknown")
    site = g.get("site") or {"home": HOME_SITE, "away": AWAY_SITE}.get(g["location"])
    return f"{label} · {site}" if site else label


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_when(g: dict, today: dt.date) -> str:
    """'Sat, Nov 14 · 1:07 PM'. The year appears only when the game is not in this year."""
    d = dt.date.fromisoformat(g["date"])
    year = f", {d.year}" if d.year != today.year else ""
    day = f"{WEEKDAYS[d.weekday()]}, {MONTHS[d.month - 1][:3]} {d.day}{year}"
    if g.get("status") == "postponed":
        return f"{day} · Postponed"
    return f"{day} · {g.get('time') or g.get('time_note') or 'Time TBA'}"


def meeting_site(g: dict) -> str:
    site = g.get("site") or {"home": HOME_SITE, "away": AWAY_SITE}.get(g.get("location"))
    return site or ("Neutral site" if g.get("location") == "neutral" else "Site TBA")


def meeting_html(g: dict, today: dt.date) -> str:
    return (f'<time datetime="{esc(g["date"])}">{esc(fmt_when(g, today))}</time>'
            f' · {esc(meeting_site(g))}')


def fmt_note(note) -> str:
    """Tidy the source's overtime notes: "(1ot)" -> "1 OT", "2OT" -> "2 OT", "(7 inn.)" -> "7 inn."."""
    text = str(note or "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return re.sub(r"(?i)\b(\d+)\s*ot\b", r"\1 OT", text)


# --------------------------------------------------------------------------- #
# Loading and validation
# --------------------------------------------------------------------------- #

GAME_FIELDS = ("date", "location", "result", "depauw", "wabash")


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DataError(f"{path} not found") from None
    except json.JSONDecodeError as exc:
        raise DataError(f"{path} is not valid JSON: {exc}") from None

    if not isinstance(data, dict):
        raise DataError("data file is not a JSON object")
    sports = data.get("sports")
    if not isinstance(sports, dict) or not sports:
        raise DataError("data file has no sports")
    totals = data.get("totals")
    if not isinstance(totals, dict):
        raise DataError("data file has no totals")
    try:
        dt.datetime.fromisoformat(str(data.get("updated_at")))
    except ValueError:
        raise DataError("data file has no valid updated_at timestamp") from None

    sums = {"depauw_wins": 0, "wabash_wins": 0, "ties": 0, "games_played": 0}
    for key, s in sports.items():
        if not KEY_RE.match(str(key)):
            raise DataError(f"unsafe sport key {key!r}")
        games = s.get("games") if isinstance(s, dict) else None
        if not games:
            raise DataError(f"{key}: no games")
        for g in games:
            missing = [f for f in GAME_FIELDS if g.get(f) is None]
            if missing:
                raise DataError(f"{key}: game {g.get('date')} is missing {missing}")
            if g["result"] not in ("W", "L", "T"):
                raise DataError(f"{key}: game {g['date']} has result {g['result']!r}")
            try:
                dt.date.fromisoformat(g["date"])
            except ValueError:
                raise DataError(f"{key}: bad date {g['date']!r}") from None
        for field in ("name", "source_url", "record", "games_played", "points"):
            if s.get(field) in (None, ""):
                raise DataError(f"{key}: missing {field}")
        if s["games_played"] != len(games):
            raise DataError(f"{key}: games_played {s['games_played']} but {len(games)} games listed")
        rec = s["record"]
        by_result = {r: sum(1 for g in games if g["result"] == r) for r in "WLT"}
        if (rec["depauw_wins"], rec["wabash_wins"], rec["ties"]) != (by_result["W"], by_result["L"], by_result["T"]):
            raise DataError(f"{key}: record does not match the game list")
        sums["depauw_wins"] += rec["depauw_wins"]
        sums["wabash_wins"] += rec["wabash_wins"]
        sums["ties"] += rec["ties"]
        sums["games_played"] += s["games_played"]
    if {k: totals.get(k) for k in sums} != sums:
        raise DataError("totals do not match the sum of the sports")
    return data


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

# Icon files written to the site root (see build()): link tag attributes and the manifest entries.
THEME_LIGHT, THEME_DARK = "#111111", "#000000"   # the header band's color in each mode
BACKGROUND = "#f6f4ee"                           # the page's light-mode background


def preview_info(data: dict) -> dict:
    """What the share card shows, all from the data: the totals and the current Monon Bell holder. The
    image URL carries a version that changes only when those do, so chat apps refetch a new picture."""
    t = data["totals"]
    football = data["sports"].get("football")
    bell = facts.bell(football["games"]) if football else None
    holder = bell["holder"] if bell else None
    alt = (f"DePauw vs. Wabash all-time totals: DePauw {t['depauw_wins']:,} wins, "
           f"Wabash {t['wabash_wins']:,} wins" + (f", {plural(t['ties'], 'tie')}" if t["ties"] else "") + "."
           + (f" {holder} holds the Monon Bell." if holder else ""))
    return {"image": f"{SITE_URL}og-image.png?v={images.og_version(t, holder)}", "alt": alt, "holder": holder}


def render_manifest() -> str:
    icons = [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
             {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
             {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]
    return json.dumps({"name": "DePauw vs. Wabash", "short_name": "DePauw v Wabash",
                       "description": SUBTITLE, "start_url": BASE_PATH, "scope": BASE_PATH,
                       "display": "browser", "theme_color": THEME_LIGHT, "background_color": BACKGROUND,
                       "icons": icons}, indent=2) + "\n"


def head(title: str, description: str, *, prefix: str, canonical: str | None, noindex: bool = False,
         preview: dict | None = None) -> str:
    """preview, when given, is {"image": absolute og-image URL with ?v=, "alt": ...} for the share cards."""
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta http-equiv="Content-Security-Policy" content="{esc(CSP)}">',
        '<meta name="referrer" content="strict-origin-when-cross-origin">',
        f'<title>{esc(title)}</title>',
        f'<meta name="description" content="{esc(description)}">',
        '<meta name="color-scheme" content="light dark">',
        f'<meta name="theme-color" content="{THEME_LIGHT}" media="(prefers-color-scheme: light)">',
        f'<meta name="theme-color" content="{THEME_DARK}" media="(prefers-color-scheme: dark)">',
    ]
    if noindex:
        lines.append('<meta name="robots" content="noindex">')
    if canonical:
        lines += [
            f'<link rel="canonical" href="{esc(canonical)}">',
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="DePauw vs. Wabash">',
            f'<meta property="og:title" content="{esc(title)}">',
            f'<meta property="og:description" content="{esc(description)}">',
            f'<meta property="og:url" content="{esc(canonical)}">',
        ]
    if canonical and preview:
        lines += [
            f'<meta property="og:image" content="{esc(preview["image"])}">',
            '<meta property="og:image:type" content="image/png">',
            f'<meta property="og:image:width" content="{images.OG_SIZE[0]}">',
            f'<meta property="og:image:height" content="{images.OG_SIZE[1]}">',
            f'<meta property="og:image:alt" content="{esc(preview["alt"])}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{esc(title)}">',
            f'<meta name="twitter:description" content="{esc(description)}">',
            f'<meta name="twitter:image" content="{esc(preview["image"])}">',
            f'<meta name="twitter:image:alt" content="{esc(preview["alt"])}">',
        ]
    elif canonical:
        lines.append('<meta name="twitter:card" content="summary">')
    lines += [
        f'<link rel="icon" href="{esc(prefix)}favicon.svg" type="image/svg+xml">',
        f'<link rel="icon" href="{esc(prefix)}favicon-32.png" type="image/png" sizes="32x32">',
        f'<link rel="apple-touch-icon" href="{esc(prefix)}apple-touch-icon.png" sizes="180x180">',
        f'<link rel="manifest" href="{esc(prefix)}site.webmanifest">',
        f'<link rel="stylesheet" href="{esc(prefix)}styles.css">',
        '</head>',
    ]
    return "\n".join(lines)


def heading(level: int, anchor: str, text: str) -> str:
    """A heading whose text is the permalink to its own section, so a visitor can copy a direct link
    without devtools. The link carries the heading's id, so the section is announced as just 'Football'."""
    return f'<h{level}><a class="permalink" id="{esc(anchor)}-h" href="#{esc(anchor)}">{esc(text)}</a></h{level}>'


def tiles(depauw: int, wabash: int, ties: int, css_class: str = "") -> str:
    def tile(cls, name, n, label):
        return (f'<div class="tile {cls}"><span class="tile-name">{esc(name)}</span>'
                f'<span class="tile-num">{n:,}</span><span class="tile-label">{esc(label)}</span></div>')
    parts = [tile("tile-depauw", "DePauw", depauw, "wins" if depauw != 1 else "win"),
             tile("tile-wabash", "Wabash", wabash, "wins" if wabash != 1 else "win")]
    if ties:
        parts.append(tile("tile-tie", "Ties", ties, "tie" if ties == 1 else "ties"))
    classes = f"tiles {css_class}" if css_class else "tiles"
    return f'<div class="{classes}">' + "".join(parts) + "</div>"


UNITS = {"points": ("point", "points"), "runs": ("run", "runs"), "goals": ("goal", "goals"),
         "individual matches": ("match", "matches")}


def unit(n: int, label: str) -> str:
    one, many = UNITS.get(label, (label, label))
    return f"{n:,} {one if n == 1 else many}"


def year_span(first: str, last: str) -> str:
    return first if first == last else f"{first}–{last}"


def game_line(g: dict) -> str:
    return f"{score_text(g)} · {fmt_date(g['date'])}"


def times_text(n: int) -> str:
    return "twice" if n == 2 else f"{n} times"


def fun_facts(key: str, s: dict) -> list:
    """[(label, text)] worked out from the game list. A fact that makes no sense for the sport is left out."""
    games, label = s["games"], s.get("total_label") or "points"
    out = []
    for who, result in (("DePauw", "W"), ("Wabash", "L")):
        g = facts.biggest_win(games, result)
        if g:
            n = len(facts.biggest_wins(games, result))
            tie = f" · happened {times_text(n)}, most recent shown" if n > 1 else ""
            out.append((f"Biggest {who} win", f"{game_line(g)} · by {unit(facts.margin(g), label)}{tie}"))
    for who, result in (("DePauw", "W"), ("Wabash", "L")):
        run = facts.longest_streak(games, result)
        if run:
            span = year_span(run["first"], run["last"])
            text = (f"{run['games']} straight ({times_text(run['times'])}, most recently {span})"
                    if run["times"] > 1 else f"{run['games']} straight · {span}")
            out.append((f"Longest {who} win streak", text))
    close = facts.one_score_games(key, games)
    if close:
        limit = facts.ONE_SCORE[key]
        by = f"by {unit(limit, label)}" + (" or fewer" if limit > 1 else "")
        out.append(("One-score games", f"{len(close):,} decided {by} · most recent: {game_line(close[-1])}"))
    if label != "individual matches":  # nine matches are always played, so the total never varies
        tops = facts.highest_scoring_games(games)
        top = tops[-1]
        tie = f" · happened {times_text(len(tops))}, most recent shown" if len(tops) > 1 else ""
        out.append(("Highest-scoring game",
                    f"{game_line(top)} · {unit(top['depauw'] + top['wabash'], label)} combined{tie}"))
    for title, found in (("Overtime games", facts.overtime_games(games)),
                         ("Extra-inning games", facts.extra_inning_games(games))):
        if found:
            last = found[-1]
            out.append((title, f"{len(found):,} · most recent: {game_line(last)} ({fmt_note(last.get('note'))})"))
    return out


def fun_facts_html(items: list) -> str:
    if not items:
        return ""
    lis = "\n".join(f'<li><span class="fun-label">{esc(k)}:</span> {esc(v)}</li>' for k, v in items)
    return f'<div class="fun-facts">\n<h3>Fun facts</h3>\n<ul>\n{lis}\n</ul>\n</div>'


def series_html(rows: list) -> str:
    if not rows:
        return ""
    lis = "\n".join(f'<li><strong>{esc(season)}:</strong> {esc(text)}</li>' for season, text in rows)
    return f'<h3 class="series-h">Season by season</h3>\n<ul class="series">\n{lis}\n</ul>\n'


def games_table(key: str, games: list) -> str:
    rows = []
    # games arrive oldest first (doubleheaders in playing order), so reverse for newest first
    for g in reversed(sorted(games, key=lambda g: g["date"])):
        winner = {"W": "win-depauw", "L": "win-wabash", "T": "tied"}[g["result"]]
        box = safe_url(g.get("boxscore"))
        box_html = f'<a href="{esc(box)}">Box score</a>' if box else ""
        rows.append(
            "<tr>"
            f'<th scope="row" data-label="Date"><time datetime="{esc(g["date"])}">{esc(fmt_date(g["date"]))}</time></th>'
            f'<td data-label="Site">{esc(where_text(g))}</td>'
            f'<td data-label="Result" class="{winner}">{esc(score_text(g))}</td>'
            f'<td data-label="Notes">{esc(fmt_note(g.get("note")))}</td>'
            f'<td data-label="Box score">{box_html}</td>'
            "</tr>"
        )
    return (
        f'<details class="games">\n<summary>All {plural(len(games), "game")}</summary>\n'
        f'{series_html(facts.season_series(games))}'
        '<p class="hint">Newest first. Home and away are from DePauw’s point of view.</p>\n'
        '<table>\n'
        f'<caption class="sr-only">Every {esc(key.replace("-", " "))} game, newest first</caption>\n'
        '<thead><tr><th scope="col">Date</th><th scope="col">Site</th><th scope="col">Result</th>'
        '<th scope="col">Notes</th><th scope="col">Box score</th></tr></thead>\n'
        '<tbody>\n' + "\n".join(rows) + '\n</tbody>\n</table>\n</details>'
    )


def bell_held_text(b: dict) -> str:
    wins, ties = b["held_wins"], b["held_ties"]
    if not ties:
        return f"{wins} straight wins" if wins > 1 else "1 win"
    return f'{plural(b["held_games"], "game")}: {plural(wins, "win")} and {plural(ties, "tie")}'


def bell_block(games: list) -> str:
    """The Monon Bell section of the football card: holder, Bell-era record and short history. The last and
    next games are the football card's own "Most recent" and "Next meeting" stats."""
    b = facts.bell(games)
    if b is None:
        return ""
    rows = []
    if b["holder"]:
        rows.append(f'<p class="bell-holder"><strong>{esc(b["holder"])} has held the Bell since {b["since"]}</strong>'
                    f' <span class="bell-note">({esc(bell_held_text(b))})</span></p>')
    record = tiles(b["depauw"], b["wabash"], b["ties"], "tiles-small")
    return "\n".join([
        '<section class="bell" id="monon-bell" aria-labelledby="monon-bell-h">',
        heading(3, "monon-bell", "The Monon Bell"),
        *rows,
        f'<dl class="facts bell-facts">\n<div><dt>Bell record since {facts.BELL_START}</dt><dd>{record}</dd></div>\n</dl>',
        f'<p class="bell-history">{esc(BELL_HISTORY)} <a href="{esc(BELL_URL)}">Read more on Wikipedia</a></p>',
        '</section>',
    ])


def card(key: str, s: dict, ahead: list, pending: list, schedule_url: str | None, today: dt.date) -> str:
    games = sorted(s["games"], key=lambda g: g["date"])
    rec = s["record"]
    code = s.get("current_streak")
    if not (isinstance(code, str) and STREAK_RE.match(code)):
        code = derive_streak(games)
    last = games[-1]
    src = safe_url(s["source_url"])
    since = games[0]["date"][:4]
    facts = [
        ("Current streak", esc(streak_text(code))),
        ("Records since", esc(since)),
        ("Games played", esc(f"{len(games):,}")),
        (f"Total {s.get('total_label') or 'points'}",
         f'DePauw {s["points"]["depauw"]:,}, Wabash {s["points"]["wabash"]:,}'),
        ("Most recent",
         f'<time datetime="{esc(last["date"])}">{esc(fmt_date(last["date"]))}</time>'
         f' · {esc(score_text(last))}'),
    ]
    if ahead:
        facts.append(("Next meeting", meeting_html(ahead[0], today)))
    if pending:
        day = fmt_when(pending[0], today).split(" · ")[0]
        facts.append(("Result pending", esc(day) + " · not on the history page yet"))
    dl = "\n".join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in facts)
    sched = safe_url(schedule_url)
    links = []
    if src:
        links.append(f'<a href="{esc(src)}">Source: depauwtigers.com {esc(s["name"])} history</a>')
    if sched:
        links.append(f'<a href="{esc(sched)}">Schedule</a>')
    links.append(report_link(s["name"]))
    source = f'<p class="source">{" · ".join(links)}</p>'
    return (
        f'<article class="sport" id="{esc(key)}" aria-labelledby="{esc(key)}-h">\n'
        f'{heading(2, key, s["name"])}\n'
        f'{tiles(rec["depauw_wins"], rec["wabash_wins"], rec["ties"])}\n'
        f'<dl class="facts">\n{dl}\n</dl>\n{source}\n'
        f'{bell_block(games) if key == "football" else ""}\n'
        f'{fun_facts_html(fun_facts(key, s))}\n'
        f'{games_table(key, games)}\n</article>'
    )


def updated_line(updated: str, checked: str | None, now: dt.datetime) -> str:
    def stamp(iso):
        return f'<time datetime="{esc(iso)}">{esc(fmt_stamp(iso, now))}</time>'
    parts = [f"Data last changed {stamp(updated)}"]
    if checked:
        parts.append(f"Last checked {stamp(checked)}")
    return f'<p>{" · ".join(parts)} (Eastern time).</p>'


def next_meeting_section(per_sport: dict, pending: dict, sports: dict, today: dt.date) -> str:
    """The soonest meeting across all sports, near the top. Empty string (no box at all) when there is none."""
    best = meetings.next_overall(per_sport)
    lines = []
    if best:
        key, g = best
        lines.append(f'<p class="next-line"><strong>{esc(sports[key]["name"])}</strong>, '
                     f'{meeting_html(g, today)}</p>')
    for key, games in pending.items():
        if games:
            lines.append(f'<p class="next-pending">{esc(sports[key]["name"])}: result pending</p>')
    if not lines:
        return ""
    return "\n".join(['<section class="next-meeting" id="next-meeting" aria-labelledby="next-meeting-h">',
                      heading(2, "next-meeting", "Next meeting"), *lines, '</section>'])


def render_index(data: dict, checked: str | None = None, now: dt.datetime | None = None,
                 upcoming: dict | None = None) -> str:
    t = data["totals"]
    sports = data["sports"]
    n_sports = len(sports)
    summary = f"DePauw {t['depauw_wins']:,} wins, Wabash {t['wabash_wins']:,}" + \
              (f", {plural(t['ties'], 'tie')}" if t["ties"] else "")
    description = (f"{SUBTITLE} {summary}, across {plural(t['games_played'], 'game')} "
                   f"in {plural(n_sports, 'sport')}.")
    updated = data["updated_at"]
    now = now or dt.datetime.now(dt.timezone.utc)
    today = to_eastern(now)[0].date()
    upcoming = upcoming or {}
    ahead, pending = {}, {}
    for key, s in sports.items():
        ahead[key], pending[key] = meetings.split_games(
            upcoming.get(key, {}).get("games", []), s["games"], today)

    sources = "\n".join(
        f'<li><a href="{esc(u)}">{esc(s["name"])}</a></li>'
        for s in sports.values() if (u := safe_url(s["source_url"])))

    return "\n".join([
        head(TITLE, description, prefix="", canonical=SITE_URL, preview=preview_info(data)),
        '<body>',
        '<header class="site-header">',
        '<div class="wrap">',
        '<h1>DePauw vs. Wabash</h1>',
        f'<p class="subtitle">{esc(SUBTITLE)}</p>',
        '</div>',
        '</header>',
        '<main class="wrap">',
        next_meeting_section(ahead, pending, sports, today),
        '<section class="overall" aria-labelledby="overall-h">',
        '<h2 id="overall-h">All sports combined</h2>',
        tiles(t["depauw_wins"], t["wabash_wins"], t["ties"], "tiles-big"),
        f'<p class="overall-meta">{esc(plural(t["games_played"], "game"))} across {esc(plural(n_sports, "sport"))}</p>',
        f'<p class="not-included"><strong>Not included:</strong> {esc(NOT_INCLUDED)}</p>',
        '</section>',
        *(card(k, s, ahead[k], pending[k], upcoming.get(k, {}).get("schedule_url"), today)
          for k, s in sports.items()),
        '</main>',
        '<footer class="site-footer">',
        '<div class="wrap">',
        updated_line(updated, checked, now),
        '<p class="downloads">Download the data: <a href="data/series.json">series.json</a> (every game, as JSON)'
        ' · <a href="games.csv">games.csv</a> (one row per game, for spreadsheets). '
        f'{report_link()}.</p>',
        '<p>Data from <a href="https://depauwtigers.com/">depauwtigers.com</a>. Source pages:</p>',
        f'<ul class="sources">\n{sources}\n</ul>',
        '<p>Only men’s sports are compared because Wabash is an all-male college.</p>',
        f'<p>{esc(DISCLAIMER)}</p>',
        '</div>',
        '</footer>',
        '</body>',
        '</html>',
        '',
    ])


def render_404() -> str:
    # GitHub Pages serves this file for any missing path, including nested ones, so relative
    # URLs would break. It is the one page that uses root-relative URLs, built from BASE_PATH.
    return "\n".join([
        head("Page not found | DePauw vs. Wabash", "That page does not exist.",
             prefix=BASE_PATH, canonical=None, noindex=True),
        '<body>',
        '<header class="site-header"><div class="wrap"><h1>DePauw vs. Wabash</h1>',
        f'<p class="subtitle">{esc(SUBTITLE)}</p></div></header>',
        '<main class="wrap">',
        '<h2>Page not found</h2>',
        f'<p><a href="{esc(BASE_PATH)}">Back to the head-to-head records</a></p>',
        '</main>',
        f'<footer class="site-footer"><div class="wrap"><p>{esc(DISCLAIMER)}</p></div></footer>',
        '</body>',
        '</html>',
        '',
    ])


def render_sitemap(data: dict, checked: str | None = None) -> str:
    """lastmod is the Eastern date of the newest time the page states: when the data last changed or,
    when there is one, when they were last checked."""
    newest = max(dt.datetime.fromisoformat(s) for s in (data["updated_at"], checked) if s)
    lastmod = to_eastern(newest)[0].date().isoformat()
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>{esc(SITE_URL)}</loc><lastmod>{lastmod}</lastmod></url>\n'
            '</urlset>\n')


CSV_COLUMNS = ["sport", "date", "season", "location", "site", "depauw_score", "wabash_score",
               "result", "note", "boxscore_url"]
RESULT_WORDS = {"W": "DePauw win", "L": "Wabash win", "T": "Tie"}


def csv_text(value) -> str:
    """Text for a spreadsheet cell. A value that starts with =, +, - or @ would run as a formula in
    Excel or Sheets, so it gets a leading apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def render_csv(data: dict) -> str:
    """One row per game, oldest first within each sport, in the order the sports appear on the page."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for s in data["sports"].values():
        for g in sorted(s["games"], key=lambda g: g["date"]):
            writer.writerow([csv_text(s["name"]), g["date"], csv_text(g.get("season")), g["location"],
                             csv_text(g.get("site")), g["depauw"], g["wabash"], RESULT_WORDS[g["result"]],
                             csv_text(fmt_note(g.get("note"))), safe_url(g.get("boxscore")) or ""])
    return buf.getvalue()


def build(data_path: Path, out: Path, *, checked_at: str | None = None,
          now: dt.datetime | None = None, upcoming_path: Path | None = None) -> None:
    data = load(data_path)
    upcoming = meetings.load_upcoming(upcoming_path)
    pages = {
        "index.html": render_index(data, checked_at, now, upcoming),
        "404.html": render_404(),
        "games.csv": render_csv(data),
        "site.webmanifest": render_manifest(),
        "sitemap.xml": render_sitemap(data, checked_at),
        "robots.txt": f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n",
        ".nojekyll": "",
    }
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, text in pages.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    for asset in ("styles.css", "favicon.svg"):
        shutil.copyfile(STATIC / asset, out / asset)
    # Images are drawn at build time from the bundled font, so every deploy has a card that matches the data.
    info = preview_info(data)
    (out / "og-image.png").write_bytes(images.og_image(data["totals"], info["holder"]))
    (out / "apple-touch-icon.png").write_bytes(images.icon_png(180))
    (out / "favicon-32.png").write_bytes(images.icon_png(32))
    (out / "icon-192.png").write_bytes(images.icon_png(192))
    (out / "icon-512.png").write_bytes(images.icon_png(512))
    (out / "icon-maskable-512.png").write_bytes(images.icon_png(512, maskable=True))
    (out / "data").mkdir()
    shutil.copyfile(data_path, out / "data" / "series.json")  # the data file as-is


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--upcoming", type=Path, default=UPCOMING,
                    help="upcoming meetings from the schedule pages (optional)")
    ap.add_argument("--checked-file", type=Path, default=CHECKED_AT,
                    help="file holding the time of the last successful scrape (optional)")
    args = ap.parse_args(argv)
    try:
        build(args.data, args.out, checked_at=read_checked(args.checked_file),
              upcoming_path=args.upcoming)
    except (DataError, KeyError, TypeError, ValueError, AttributeError) as exc:
        print(f"render failed: {exc!r}", file=sys.stderr)
        return 1
    print(f"Wrote site to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
