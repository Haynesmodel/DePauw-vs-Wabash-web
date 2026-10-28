"""Tests for the Monon Bell numbers and how the block appears in the football card."""
import re
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts  # noqa: E402
import render  # noqa: E402
import scrape  # noqa: E402
from test_meetings import entry, page, sched  # noqa: E402
from test_render import football  # noqa: E402
from test_scrape import BASE, full_football_html  # noqa: E402


def real_football():
    """All 131 football games, parsed from the page markup captured on 2026-10-27."""
    games, _, _ = scrape.parse_page(full_football_html(), base_url=BASE, opponent_match="wabash")
    return [asdict(g) for g in scrape.chronological(games)]


def g(year, result, d=10, w=7):
    return {"date": f"{year}-11-15", "season": str(year), "location": "home", "site": None,
            "result": result, "depauw": d, "wabash": w, "note": None, "boxscore": None}


# ---- the standings --------------------------------------------------------- #

def test_bell_record_matches_wikipedia_through_the_2025_season():
    b = facts.bell(real_football())
    assert (b["wabash"], b["depauw"], b["ties"]) == (44, 43, 6)
    assert b["games"] == 93
    assert b["last"]["date"] == "2025-11-15"


def test_games_before_1932_are_not_bell_games():
    games = [g(1931, "W"), g(1932, "T"), g(1933, "L")]
    b = facts.bell(games)
    assert (b["depauw"], b["wabash"], b["ties"], b["games"]) == (0, 1, 1, 2)


def test_depauw_has_held_the_bell_since_2022():
    b = facts.bell(real_football())
    assert (b["holder"], b["since"], b["held_games"]) == ("DePauw", 2022, 4)


def test_a_tie_leaves_the_bell_where_it_was_and_counts_toward_the_hold():
    b = facts.bell([g(2018, "L"), g(2019, "W"), g(2020, "T"), g(2021, "T"), g(2022, "W")])
    assert (b["holder"], b["since"], b["held_games"]) == ("DePauw", 2019, 4)


def test_ties_before_the_first_win_do_not_start_the_hold():
    b = facts.bell([g(2018, "L"), g(2019, "T"), g(2020, "W")])
    assert (b["holder"], b["since"], b["held_games"]) == ("DePauw", 2020, 1)


def test_wabash_can_hold_it_and_a_late_tie_does_not_take_it_away():
    b = facts.bell([g(2018, "W"), g(2019, "L"), g(2020, "L"), g(2021, "T")])
    assert (b["holder"], b["since"], b["held_games"]) == ("Wabash", 2019, 3)


def test_no_decided_game_means_no_holder():
    b = facts.bell([g(1932, "T"), g(1933, "T")])
    assert b["holder"] is None and b["ties"] == 2 and b["games"] == 2
    assert facts.bell([g(1920, "W")]) is None


# ---- the block on the page ------------------------------------------------- #

def block(html):
    start = html.index('<section class="bell"')
    return html[start:html.index("</section>", start)]


def test_bell_block_sits_in_the_football_card_above_the_game_list(tmp_path):
    html = page(tmp_path, {})
    card = html[html.index('id="football"'):html.index("</article>", html.index('id="football"'))]
    assert card.index('id="monon-bell"') < card.index('<details class="games">')
    assert "mens-lacrosse" not in block(html) and html.count('id="monon-bell"') == 1


def test_bell_block_shows_record_holder_last_game_and_the_wikipedia_link(tmp_path):
    # made-up football(): 1999 tie, 2001 L, then three DePauw wins (2002 to 2004)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block(page(tmp_path, {}))))
    assert "DePauw has held the Bell since 2002" in text and "3 games, counting any ties" in text
    assert "Bell record since 1932" in text
    assert "Last Bell game Nov 13, 2004" in text and "DePauw 28, Wabash 3" in text
    assert "Next Bell game" not in text
    html = block(page(tmp_path, {}))
    assert '<a href="https://en.wikipedia.org/wiki/Monon_Bell">Read more on Wikipedia</a>' in html


def test_next_bell_game_comes_from_the_football_schedule(tmp_path):
    html = block(page(tmp_path, {"football": entry(sched("2026-11-14"))}))
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Next Bell game Sat, Nov 14 · 1:07 PM · Scheumann Stadium, Muncie, Ind." in text


def test_the_hand_written_history_has_no_changing_numbers_and_stays_short():
    numbers = set(re.findall(r"\d+", render.BELL_HISTORY))
    assert numbers == {"300", str(facts.BELL_START)}      # the bell's weight and the year it became a trophy
    sentences = [s for s in re.split(r"(?<=\.) ", render.BELL_HISTORY) if s]
    assert 3 <= len(sentences) <= 5
    assert "tie" in render.BELL_HISTORY and "stolen" in render.BELL_HISTORY
