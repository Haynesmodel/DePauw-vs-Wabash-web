"""Locations are shown in AP style (Ind., Ohio, Ill.) whichever way the source wrote the state, and only
there: the data files, games.csv and the schedule cross-check keep the sources' own words."""
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import places  # noqa: E402
import render  # noqa: E402
from test_render import build, game, sport, text_of  # noqa: E402


@pytest.mark.parametrize("raw, shown", [
    ("Greencastle, IN", "Greencastle, Ind."),
    ("Greencastle, Ind.", "Greencastle, Ind."),
    ("Greencastle, Indiana", "Greencastle, Ind."),
    ("Neal Fieldhouse, Greencastle, IN", "Neal Fieldhouse, Greencastle, Ind."),
    ("Wooster, OH", "Wooster, Ohio"),
    ("Wooster, Ohio", "Wooster, Ohio"),
    ("Naperville, IL", "Naperville, Ill."),
    ("Naperville, Illinois", "Naperville, Ill."),
    ("Louisville, KY", "Louisville, Ky."),
    ("Ann Arbor, MI", "Ann Arbor, Mich."),
    ("Jersey City, NJ", "Jersey City, N.J."),
    ("Charleston, WV", "Charleston, W.Va."),
    ("Washington, DC", "Washington, D.C."),
    ("Dallas, TX", "Dallas, Texas"),
    ("Scheumann Stadium, Muncie, in", "Scheumann Stadium, Muncie, in"),      # not a postal code (wrong case): left alone
])
def test_states_are_written_the_ap_way(raw, shown):
    assert places.ap_place(raw) == shown


@pytest.mark.parametrize("raw", [
    "Crawfordsville High School",                       # no state at all
    "College of Wooster; Wooster, Ohio",                # already AP, venue string kept
    "Denison University; Granville, Ohio",
    "Lucas Oil Stadium, Indianapolis",                  # a city is not a state
    "Greencastle IN",                                   # no comma: an unknown format, not guessed at
    "Springfield, Illinoi",                             # near miss
    "Toronto, ON",                                      # not a US state
    "", None, 5,
])
def test_unknown_formats_are_left_untouched(raw):
    assert places.ap_place(raw) == raw


def test_every_us_state_has_an_ap_form_and_both_spellings_agree():
    assert len(places.STATES) == 51
    for code, (ap, name) in places.STATES.items():
        assert places.ap_place(f"X, {code}") == f"X, {ap}" == places.ap_place(f"X, {name}")


def football_with_sites():
    return sport("football", "Football", [
        game("2001-11-10", "L", 17, 24, "away", "Crawfordsville, IN"),
        game("2003-11-08", "W", 41, 20, "home", "Neal Fieldhouse, Greencastle, Ind."),
        game("2004-11-13", "W", 28, 3, "neutral", "Indianapolis, IN"),
        game("2005-11-12", "W", 10, 3, "away", "College of Wooster; Wooster, Ohio"),
    ])


def test_game_lists_show_one_style_for_every_game(tmp_path):
    _, page = build(tmp_path, {"football": football_with_sites()})
    t = text_of(page)
    assert "Away · Crawfordsville, Ind." in t and "Neutral · Indianapolis, Ind." in t
    assert "Home · Neal Fieldhouse, Greencastle, Ind." in t and "Wooster, Ohio" in t
    assert ", IN" not in t and " IN " not in t


def test_next_meeting_shows_ap_style_on_the_top_box_and_the_card(tmp_path):
    from test_meetings import page, entry, sched
    html = page(tmp_path, {"football": entry(sched("2026-11-14", "1:07 PM", "away", "Goodrich Ballpark, Crawfordsville, IN"))})
    assert html.count("Goodrich Ballpark, Crawfordsville, Ind.") == 2          # top box and card
    assert "Crawfordsville, IN" not in html


def test_a_game_with_no_site_still_falls_back_to_the_ap_style_home_and_away_towns(tmp_path):
    from test_meetings import page, entry, sched
    html = page(tmp_path, {"football": entry(sched("2026-11-14", "1:07 PM", "home", None))})
    assert "Greencastle, Ind." in text_of(html)


def test_the_data_and_the_csv_keep_the_sources_own_spelling(tmp_path):
    out, page = build(tmp_path, {"football": football_with_sites()})
    assert "Crawfordsville, Ind." in page
    shipped = json.loads((out / "data" / "series.json").read_text(encoding="utf-8"))
    assert [g["site"] for g in shipped["sports"]["football"]["games"]][0] == "Crawfordsville, IN"
    sites = [row["site"] for row in csv.DictReader((out / "games.csv").read_text(encoding="utf-8").splitlines())]
    assert "Crawfordsville, IN" in sites and "Indianapolis, IN" in sites and "Crawfordsville, Ind." not in sites


def test_the_committed_data_files_are_not_rewritten_by_display_styling():
    for name in ("depauw.json", "wabash.json", "series.json"):
        raw = (ROOT / "data" / name).read_text(encoding="utf-8")
        assert '"site"' in raw
    wabash = (ROOT / "data" / "wabash.json").read_text(encoding="utf-8")
    assert re.search(r'"site": "[^"]*, IN"', wabash)          # Wabash's own style is still in the file


def test_the_schedule_cross_check_still_sees_the_sources_raw_wording():
    import upcoming
    assert upcoming.same_site("Scheumann Stadium, Muncie, Ind.", "Scheumann Stadium, Muncie, IN")


def test_the_preview_image_text_has_no_locations():
    import images
    import inspect
    assert "site" not in inspect.signature(images.og_image).parameters
