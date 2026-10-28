"""Tests for the schedule parser, using game rows captured from depauwtigers.com on 2026-10-28.

The fixtures are the real schedule markup trimmed to a few games. The canceled, postponed and TBA
cases below are made by editing that real markup, because no such game was on the live pages."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import scrape  # noqa: E402
import upcoming  # noqa: E402
from test_scrape import full_html  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
SPORTS = ["football", "mens-basketball", "baseball", "mens-soccer", "mens-lacrosse", "mens-tennis"]


def fixture(sport):
    return (FIX / f"schedule-{sport}.html").read_text(encoding="utf-8")


def parse(html):
    return upcoming.parse_schedule(html, opponent_id=215)


def test_the_2026_football_game_at_scheumann_stadium_is_found():
    assert parse(fixture("football")) == [{
        "date": "2026-11-14", "time": "1:07 PM", "time_note": None, "location": "neutral",
        "site": "Scheumann Stadium, Muncie, Ind.", "status": "scheduled", "doubleheader": False}]


def test_basketball_home_and_away_games_get_their_year_from_the_season():
    home, away = parse(fixture("mens-basketball"))
    assert (home["date"], home["time"], home["location"]) == ("2027-01-06", "7:00 PM", "home")
    assert home["site"] == "Neal Fieldhouse, Greencastle, Ind."
    assert (away["date"], away["location"], away["site"]) == ("2027-01-27", "away", "Crawfordsville, Ind.")
    # The away row has no dated link, so its year came from "2026-27" plus the weekday (Wed).


def test_only_wabash_rows_count_and_finished_games_are_left_to_the_history_page():
    assert parse(fixture("baseball")) == []        # both April 28 games are finished
    assert parse(fixture("mens-tennis")) == []     # fixture has no Wabash row at all


def test_a_canceled_game_is_skipped():
    head, wabash_row = fixture("football").split('data-game-opponent-id="215"')
    wabash_row = wabash_row.replace(
        '<div class="sidearm-schedule-game-conference-conference',
        '<div class="sidearm-schedule-game-result"><span>Canceled</span></div>'
        '<div class="sidearm-schedule-game-conference-conference', 1)
    assert parse(head + 'data-game-opponent-id="215"' + wabash_row) == []


def test_a_postponed_game_is_kept_and_marked():
    html = fixture("football").replace("1:07 p.m.</span>", "Postponed</span>", 1)
    [game] = parse(html)
    assert game["status"] == "postponed" and game["time"] is None and game["date"] == "2026-11-14"


@pytest.mark.parametrize("shown", ["TBA", "TBD", ""])
def test_a_missing_time_is_none_not_a_guess(shown):
    html = re.sub(r"1:07 p\.m\.</span>", shown + "</span>", fixture("football"), count=1)
    [game] = parse(html)
    assert game["time"] is None


def test_second_game_of_a_doubleheader_keeps_its_note():
    html = fixture("football").replace("1:07 p.m.</span>", "Following Game 1</span>", 1)
    assert parse(html)[0]["time_note"] == "Following Game 1"
    assert parse(fixture("football"))[0]["time_note"] is None


def test_wrong_page_is_an_error_not_an_empty_schedule():
    with pytest.raises(upcoming.ScheduleError):
        parse("<html><body>Service unavailable</body></html>")


def test_a_schedule_with_no_wabash_game_is_just_empty():
    html = fixture("football").replace('data-game-opponent-id="215"', 'data-game-opponent-id="99"')
    assert parse(html) == []


def test_unreadable_date_is_skipped_with_a_warning(capsys):
    html = fixture("football").replace("Nov 14 (Sat)", "Sometime", 1)
    assert parse(html) == []
    assert "unreadable date" in capsys.readouterr().err


def test_year_follows_the_season_and_a_weekday_that_fits_only_one_year():
    # Dec 2, 2026 is a Wednesday and belongs to "2026-27"; Feb 3, 2027 is a Wednesday in the second year.
    one = fixture("mens-basketball")
    assert parse(one.replace("Jan 27 (Wed)", "Dec 2 (Wed)", 1))[0]["date"] == "2026-12-02"
    assert parse(one.replace("Jan 27 (Wed)", "Feb 3 (Wed)", 1))[1]["date"] == "2027-02-03"


# ---- the scraper step ------------------------------------------------------ #

def run(tmp_path, pages):
    d = tmp_path / "pages"
    d.mkdir(exist_ok=True)
    for name, text in pages.items():
        (d / name).write_text(text, encoding="utf-8")
    out = tmp_path / "upcoming.json"
    code = scrape.main(["--fixtures", str(d), "--output", str(tmp_path / "series.json"),
                        "--upcoming-output", str(out)])
    return code, out


def test_schedules_are_written_apart_from_the_records(tmp_path):
    _, out = run(tmp_path, {"football-schedule.html": fixture("football"),
                            "mens-basketball-schedule.html": fixture("mens-basketball")})
    data = json.loads(out.read_text())
    assert data["schema_version"] == 1
    assert data["sports"]["football"]["schedule_url"] == "https://depauwtigers.com/sports/football/schedule"
    assert data["sports"]["football"]["games"][0]["date"] == "2026-11-14"
    assert len(data["sports"]["mens-basketball"]["games"]) == 2
    assert "updated_at" not in out.read_text()      # nothing that changes without the games changing
    assert not (tmp_path / "series.json").exists()  # no history pages were given, so none was written


def test_a_broken_schedule_warns_and_keeps_the_last_good_entry(tmp_path, capsys):
    run(tmp_path, {"football-schedule.html": fixture("football")})
    good = (tmp_path / "upcoming.json").read_text()
    _, out = run(tmp_path, {"football-schedule.html": "<html>oops</html>"})
    assert out.read_text() == good
    assert "schedule not updated" in capsys.readouterr().err


def test_schedule_problems_alone_leave_the_exit_code_green(tmp_path):
    d = tmp_path / "pages"
    d.mkdir()
    for key in SPORTS:
        src = FIX / f"{key}.html"
        (d / f"{key}.html").write_text(src.read_text(encoding="utf-8") if src.exists() else full_html(key),
                                       encoding="utf-8")
        (d / f"{key}-schedule.html").write_text("<html>site redesign</html>", encoding="utf-8")
    code = scrape.main(["--fixtures", str(d), "--output", str(tmp_path / "series.json"),
                        "--upcoming-output", str(tmp_path / "upcoming.json")])
    assert code == 0
    assert not (tmp_path / "upcoming.json").exists()


def test_unchanged_schedule_does_not_rewrite_the_file(tmp_path):
    _, out = run(tmp_path, {"football-schedule.html": fixture("football")})
    out.write_text(out.read_text() + " ")             # tamper with the bytes, not the content
    before = out.read_text()
    run(tmp_path, {"football-schedule.html": fixture("football")})
    assert out.read_text() == before
