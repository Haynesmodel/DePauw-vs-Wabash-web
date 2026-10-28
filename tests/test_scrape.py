"""Tests for the DePauw vs. Wabash scraper, run against markup captured from depauwtigers.com."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import scrape  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
BASE = "https://depauwtigers.com"


def parse(html):
    return scrape.parse_page(html, base_url=BASE, opponent_match="wabash")


def full_football_html() -> str:
    """Rebuild the full 131-game football page: the real page markup from the subset fixture,
    with its table body filled from the complete captured game list."""
    page = (FIX / "football-subset.html").read_text()
    ref = json.loads((FIX / "football-expected.json").read_text())
    rows = []
    for date, season, loc, site, res, us, them, note in ref["games"]:
        m, d, y = date.split("/")
        long_date = f"{['January','February','March','April','May','June','July','August','September','October','November','December'][int(m)-1]} {int(d)}, {y}"
        rows.append(
            f'<tr><th scope="row"><span class="hide-on-large">{long_date}</span><span class="hide-on-medium-down">{date}</span></th>'
            f'<td class="sidearm-table-custom-field" data-label="Season"> {season} </td>'
            f'<td class="sidearm-table-custom-field location" data-label="Location"><div><span class="hide-on-medium-down"> {loc} </span><span>{site}</span></div></td>'
            f'<td class="sidearm-table-custom-field score {res}" data-label="Score"><div><span class="hide-on-medium-down post-score">{(" " + note + " ") if note else ""}</span><span> {res} {us} - {them} </span></div></td>'
            f'<td class="sidearm-table-custom-field" data-label="Media"><div class="media-list"></div></td></tr>'
        )
    # Replace only the history table's body (the last-matchup box score has its own <tbody>).
    head, table = page.split('<table class="sidearm-table"', 1)
    table = re.sub(r"<tbody>.*?</tbody>", "<tbody>" + "".join(rows) + "</tbody>", table, flags=re.S, count=1)
    return head + '<table class="sidearm-table"' + table


# --------------------------------------------------------------------------- #
# Row parsing (real markup)
# --------------------------------------------------------------------------- #

def test_football_rows_parse_correctly():
    games, summary, skipped = parse((FIX / "football-subset.html").read_text())
    assert len(games) == 18 and skipped == []

    latest = games[0]
    assert (latest.date, latest.season, latest.location, latest.site) == ("2025-11-15", "2025", "away", "Crawfordsville, Ind.")
    assert (latest.result, latest.depauw, latest.wabash) == ("W", 41, 20)
    assert latest.boxscore == "https://depauwtigers.com/boxscore.aspx?id=18817&path=football"

    ot = next(g for g in games if g.date == "2023-11-11")
    assert ot.note == "2 OT" and (ot.depauw, ot.wabash) == (33, 30)

    tie = next(g for g in games if g.date == "1992-11-14")
    assert tie.result == "T" and tie.depauw == tie.wabash == 17

    neutral = next(g for g in games if g.date == "1922-11-25")
    assert neutral.location == "neutral" and neutral.site == "Irwin Field; Indianapolis, Ind."

    first = games[-1]
    assert first.date == "1890-11-22" and first.site is None and first.boxscore is None

    # Summary block read straight from the page
    assert (summary.wins, summary.losses, summary.ties) == (59, 63, 9)
    assert summary.home == (29, 29, 3) and summary.away == (28, 31, 5)


def test_validation_catches_missing_games():
    """The subset fixture only has 18 of 131 games, so validation must flag it."""
    games, summary, _ = parse((FIX / "football-subset.html").read_text())
    problems = scrape.validate(games, summary)
    assert any(p.startswith("wins:") for p in problems)


# --------------------------------------------------------------------------- #
# Full-series tallies agree with the page's own summary
# --------------------------------------------------------------------------- #

def test_full_football_matches_page_summary():
    games, summary, _ = parse(full_football_html())
    assert len(games) == 131
    assert scrape.validate(games, summary) == []
    t = scrape.tally(games)
    assert (t["wins"], t["losses"], t["ties"]) == (59, 63, 9)
    assert t["by_location"]["neutral"] == (2, 3, 1)  # neutral-site games aren't in the page's home/away boxes


def test_lacrosse_matches_page_summary():
    games, summary, _ = parse((FIX / "mens-lacrosse.html").read_text())
    assert len(games) == 12
    assert summary.ties == 0  # page has no Ties box; treated as zero
    assert scrape.validate(games, summary) == []
    assert all(g.result == "W" for g in games)
    assert games[0].date == "2026-04-04" and (games[0].depauw, games[0].wabash) == (14, 5)


# --------------------------------------------------------------------------- #
# Guard rails
# --------------------------------------------------------------------------- #

def test_wrong_opponent_is_rejected():
    html = (FIX / "mens-lacrosse.html").read_text().replace(
        'breadcrumbs-opponent">Wabash College', 'breadcrumbs-opponent">Denison University')
    with pytest.raises(scrape.ParseError, match="Denison"):
        parse(html)


def test_layout_change_is_rejected():
    with pytest.raises(scrape.ParseError, match="article not found"):
        parse("<html><body><div>Site redesign</div></body></html>")


def test_class_and_text_disagreement_is_rejected():
    html = (FIX / "mens-lacrosse.html").read_text().replace("score W", "score L", 1)
    with pytest.raises(scrape.ParseError, match="cell class"):
        parse(html)


def test_canceled_row_is_skipped_not_counted():
    html = (FIX / "mens-lacrosse.html").read_text().replace("<span> W 9 - 8 </span>", "<span> Canceled </span>", 1)
    games, summary, skipped = parse(html)
    assert len(games) == 11 and skipped[0]["text"] == "Canceled"
    assert scrape.validate(games, summary)  # and the count mismatch is reported


# --------------------------------------------------------------------------- #
# End to end: fixtures in, series.json out
# --------------------------------------------------------------------------- #

@pytest.fixture
def fixture_dir(tmp_path):
    d = tmp_path / "pages"
    d.mkdir()
    (d / "football.html").write_text(full_football_html())
    (d / "mens-lacrosse.html").write_text((FIX / "mens-lacrosse.html").read_text())
    return d


def test_end_to_end_writes_series_json(fixture_dir, tmp_path, capsys):
    out = tmp_path / "series.json"
    assert scrape.main(["--fixtures", str(fixture_dir), "--output", str(out)]) == 0
    data = json.loads(out.read_text())

    fb = data["sports"]["football"]
    assert fb["record"] == {"depauw_wins": 59, "wabash_wins": 63, "ties": 9}
    assert fb["first_game"] == "1890-11-22" and fb["last_game"] == "2025-11-15"
    assert fb["current_streak"] == "W4"
    assert data["sports"]["mens-lacrosse"]["current_streak"] == "W12"
    assert data["totals"] == {"depauw_wins": 71, "wabash_wins": 63, "ties": 9, "games_played": 143}
    assert data["updated_at"]

    # A second run with identical pages must not rewrite the file (no empty nightly commits).
    stamp = data["updated_at"]
    assert scrape.main(["--fixtures", str(fixture_dir), "--output", str(out)]) == 0
    assert json.loads(out.read_text())["updated_at"] == stamp
    assert "unchanged" in capsys.readouterr().out


def test_bad_page_keeps_last_good_data(fixture_dir, tmp_path):
    out = tmp_path / "series.json"
    scrape.main(["--fixtures", str(fixture_dir), "--output", str(out)])
    good = json.loads(out.read_text())["sports"]["football"]

    (fixture_dir / "football.html").write_text("<html><body>Service unavailable</body></html>")
    assert scrape.main(["--fixtures", str(fixture_dir), "--output", str(out)]) == 1
    assert json.loads(out.read_text())["sports"]["football"] == good


def test_shrinking_history_is_refused(fixture_dir, tmp_path):
    out = tmp_path / "series.json"
    scrape.main(["--fixtures", str(fixture_dir), "--output", str(out)])
    lax = (fixture_dir / "mens-lacrosse.html").read_text()
    # Drop the oldest game *and* adjust the summary so the page is self-consistent but shorter.
    lax = re.sub(r'<tr><th scope="row"><span class="hide-on-large">April 2, 2015.*?</tr>', "", lax, flags=re.S)
    lax = lax.replace('number">12</div>', 'number">11</div>').replace(" 6-0 ", " 5-0 ", 1)
    (fixture_dir / "mens-lacrosse.html").write_text(lax)
    assert scrape.main(["--fixtures", str(fixture_dir), "--output", str(out)]) == 1
    assert json.loads(out.read_text())["sports"]["mens-lacrosse"]["games_played"] == 12
    assert scrape.main(["--fixtures", str(fixture_dir), "--output", str(out), "--allow-shrink"]) == 0
    assert json.loads(out.read_text())["sports"]["mens-lacrosse"]["games_played"] == 11
