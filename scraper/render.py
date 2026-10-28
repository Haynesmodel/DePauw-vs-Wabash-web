"""
Static site generator for the DePauw vs. Wabash page.

Reads data/series.json and writes a finished site to site/ (index.html, 404.html,
styles.css, favicon.svg, robots.txt, sitemap.xml, .nojekyll). Standard library only,
no client-side JavaScript.

Every figure on the page comes from the data file. Anything missing or inconsistent
raises DataError and the script exits non-zero, so a bad data file can never produce
a blank or half-true page.

Usage:
  python scraper/render.py                      # data/series.json -> site/
  python scraper/render.py --data FILE --out DIR
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "series.json"
STATIC = ROOT / "static"
OUT = ROOT / "site"

SITE_URL = "https://jacksonmote.github.io/DePauw-vs-Wabash-web/"
BASE_PATH = urlparse(SITE_URL).path  # "/DePauw-vs-Wabash-web/"
SOURCE_HOST = "depauwtigers.com"

TITLE = "DePauw vs. Wabash: All-Time Head-to-Head Records"
SUBTITLE = "All-time head-to-head records in men’s sports."
DISCLAIMER = "Unofficial fan site, not affiliated with DePauw University or Wabash College."

CSP = ("default-src 'none'; style-src 'self'; img-src 'self'; "
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


def fmt_updated(iso: str) -> str:
    local, abbr = to_eastern(dt.datetime.fromisoformat(iso))
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{MONTHS[local.month - 1]} {local.day}, {local.year}, {hour}:{local.minute:02d} {ampm} {abbr}"


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
    return f"{label} · {g['site']}" if g.get("site") else label


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

def head(title: str, description: str, *, prefix: str, canonical: str | None, noindex: bool = False) -> str:
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
            '<meta name="twitter:card" content="summary">',
        ]
    lines += [
        f'<link rel="icon" href="{esc(prefix)}favicon.svg" type="image/svg+xml">',
        f'<link rel="stylesheet" href="{esc(prefix)}styles.css">',
        '</head>',
    ]
    return "\n".join(lines)


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


def games_table(key: str, games: list) -> str:
    rows = []
    for g in sorted(games, key=lambda g: g["date"], reverse=True):
        winner = {"W": "win-depauw", "L": "win-wabash", "T": "tied"}[g["result"]]
        box = safe_url(g.get("boxscore"))
        box_html = f'<a href="{esc(box)}">Box score</a>' if box else ""
        rows.append(
            "<tr>"
            f'<th scope="row" data-label="Date"><time datetime="{esc(g["date"])}">{esc(fmt_date(g["date"]))}</time></th>'
            f'<td data-label="Site">{esc(where_text(g))}</td>'
            f'<td data-label="Result" class="{winner}">{esc(score_text(g))}</td>'
            f'<td data-label="Notes">{esc(g.get("note") or "")}</td>'
            f'<td data-label="Box score">{box_html}</td>'
            "</tr>"
        )
    return (
        f'<details class="games">\n<summary>All {plural(len(games), "game")}</summary>\n'
        '<p class="hint">Newest first. Home and away are from DePauw’s point of view.</p>\n'
        '<table>\n'
        f'<caption class="sr-only">Every {esc(key.replace("-", " "))} game, newest first</caption>\n'
        '<thead><tr><th scope="col">Date</th><th scope="col">Site</th><th scope="col">Result</th>'
        '<th scope="col">Notes</th><th scope="col">Box score</th></tr></thead>\n'
        '<tbody>\n' + "\n".join(rows) + '\n</tbody>\n</table>\n</details>'
    )


def card(key: str, s: dict) -> str:
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
        ("Total points", f'DePauw {s["points"]["depauw"]:,}, Wabash {s["points"]["wabash"]:,}'),
        ("Most recent",
         f'<time datetime="{esc(last["date"])}">{esc(fmt_date(last["date"]))}</time>'
         f' · {esc(score_text(last))}'),
    ]
    dl = "\n".join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in facts)
    source = (f'<p class="source"><a href="{esc(src)}">Source: depauwtigers.com {esc(s["name"])} history</a></p>'
              if src else "")
    return (
        f'<article class="sport" id="{esc(key)}" aria-labelledby="{esc(key)}-h">\n'
        f'<h2 id="{esc(key)}-h">{esc(s["name"])}</h2>\n'
        f'{tiles(rec["depauw_wins"], rec["wabash_wins"], rec["ties"])}\n'
        f'<dl class="facts">\n{dl}\n</dl>\n{source}\n'
        f'{games_table(key, games)}\n</article>'
    )


def render_index(data: dict) -> str:
    t = data["totals"]
    sports = data["sports"]
    n_sports = len(sports)
    summary = f"DePauw {t['depauw_wins']:,} wins, Wabash {t['wabash_wins']:,}" + \
              (f", {plural(t['ties'], 'tie')}" if t["ties"] else "")
    description = (f"{SUBTITLE} {summary}, over {plural(t['games_played'], 'game')} "
                   f"in {plural(n_sports, 'sport')}.")
    updated = data["updated_at"]

    sources = "\n".join(
        f'<li><a href="{esc(u)}">{esc(s["name"])}</a></li>'
        for s in sports.values() if (u := safe_url(s["source_url"])))

    return "\n".join([
        head(TITLE, description, prefix="", canonical=SITE_URL),
        '<body>',
        '<header class="site-header">',
        '<div class="wrap">',
        '<h1>DePauw vs. Wabash</h1>',
        f'<p class="subtitle">{esc(SUBTITLE)}</p>',
        '</div>',
        '</header>',
        '<main class="wrap">',
        '<section class="overall" aria-labelledby="overall-h">',
        '<h2 id="overall-h">All sports combined</h2>',
        tiles(t["depauw_wins"], t["wabash_wins"], t["ties"], "tiles-big"),
        f'<p class="overall-meta">{esc(plural(t["games_played"], "game"))} across {esc(plural(n_sports, "sport"))}</p>',
        '</section>',
        *(card(k, s) for k, s in sports.items()),
        '</main>',
        '<footer class="site-footer">',
        '<div class="wrap">',
        f'<p>Last updated <time datetime="{esc(updated)}">{esc(fmt_updated(updated))}</time> (Eastern time).</p>',
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


def render_sitemap(data: dict) -> str:
    lastmod = to_eastern(dt.datetime.fromisoformat(data["updated_at"]))[0].date().isoformat()
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>{esc(SITE_URL)}</loc><lastmod>{lastmod}</lastmod></url>\n'
            '</urlset>\n')


def build(data_path: Path, out: Path) -> None:
    data = load(data_path)
    pages = {
        "index.html": render_index(data),
        "404.html": render_404(),
        "sitemap.xml": render_sitemap(data),
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    try:
        build(args.data, args.out)
    except (DataError, KeyError, TypeError, ValueError, AttributeError) as exc:
        print(f"render failed: {exc!r}", file=sys.stderr)
        return 1
    print(f"Wrote site to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
