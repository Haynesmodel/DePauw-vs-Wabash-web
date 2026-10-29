"""Game-day mode: the gate that decides whether a frequent run does anything, the banner for each phase, the
schedule carry-over that keeps a just-finished game visible until its result is in, and the workflow wiring."""
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gameday  # noqa: E402
import images  # noqa: E402
import render  # noqa: E402
import scrape  # noqa: E402
import upcoming  # noqa: E402
from test_render import build, game, lacrosse, sport, text_of  # noqa: E402
from timeutil import from_eastern  # noqa: E402

FREQ = gameday.FREQUENT_CRON
WORKFLOW = (ROOT / ".github" / "workflows" / "update-and-deploy.yml").read_text(encoding="utf-8")


def et(text):
    """An Eastern wall-clock time ('2026-11-14 13:07') as an aware UTC time."""
    return from_eastern(dt.datetime.fromisoformat(text))


def sched(date="2026-11-14", time="1:07 PM", status="scheduled", location="neutral",
          site="Scheumann Stadium, Muncie, IN", source="both"):
    return {"date": date, "time": time, "time_note": None, "location": location, "site": site,
            "status": status, "doubleheader": False, "source": source}


def played(date="2026-11-14", result="W", d=41, w=20, **kw):
    return game(date, result, d, w, kw.pop("location", "neutral"), kw.pop("site", "Scheumann Stadium, Muncie, IN"), **kw)


def football(*extra):
    return sport("football", "Football", [
        game("2024-11-16", "W", 21, 14), game("2025-11-15", "W", 41, 20), *extra])


def inputs(games=(), history=(), key="football", name="Football"):
    up = {key: {"games": list(games)}}
    sports = {key: {"name": name, "games": [game("2025-11-15", "W", 41, 20), *history]}}
    return up, sports


def gate(now, games=(), history=(), schedule=FREQ):
    up, sports = inputs(games, history)
    return gameday.gate(et(now), schedule, up, sports)


# ---- the gate ------------------------------------------------------------ #

def test_no_game_scheduled_means_the_frequent_run_does_nothing():
    run, why = gate("2026-11-14 14:00")
    assert run is False and "no game-day window" in why


def test_before_the_window_opens_nothing_runs():
    assert gate("2026-11-14 13:06", [sched()])[0] is False        # a minute before the 1:07 PM start
    assert gate("2026-11-13 20:00", [sched()])[0] is False        # the night before
    assert gate("2026-11-14 07:07", [sched()])[0] is False        # game day morning: the daily run covers it


def test_inside_the_window_the_run_does_the_real_work():
    assert gate("2026-11-14 13:07", [sched()])[0] is True         # exactly at the start
    assert gate("2026-11-14 16:37", [sched()])[0] is True
    assert gate("2026-11-14 23:37", [sched()])[0] is True
    run, why = gate("2026-11-14 14:07", [sched()])
    assert run and "Football 2026-11-14: 0 of 1 result(s) in" in why


def test_once_the_result_is_on_a_history_page_the_run_stops():
    assert gate("2026-11-14 16:37", [sched()], [played("2026-11-14")])[0] is False


def test_the_window_closes_at_3_am_eastern_the_next_day():
    assert gate("2026-11-15 02:59", [sched()])[0] is True          # the carried game, result still missing
    assert gate("2026-11-15 03:00", [sched()])[0] is False
    assert gate("2026-11-15 12:00", [sched()])[0] is False


def test_a_game_with_no_time_opens_at_noon_eastern():
    assert gate("2026-11-14 11:59", [sched(time=None)])[0] is False
    assert gate("2026-11-14 12:00", [sched(time=None)])[0] is True


def test_a_doubleheader_stays_open_until_both_results_are_in():
    dh = [sched("2027-04-28", "12:00 PM", site="Goodrich Ballpark, Crawfordsville, IN"),
          sched("2027-04-28", "3:30 PM", site="Goodrich Ballpark, Crawfordsville, IN")]
    assert gate("2027-04-28 11:59", dh)[0] is False
    assert gate("2027-04-28 12:07", dh)[0] is True                  # opens at the first game's start
    assert gate("2027-04-28 15:37", dh, [played("2027-04-28", "W", 5, 3)])[0] is True       # one of two
    assert gate("2027-04-28 17:37", dh, [played("2027-04-28", "W", 5, 3), played("2027-04-28", "L", 2, 4)])[0] is False


def test_a_postponed_game_opens_no_window():
    assert gate("2026-11-14 14:00", [sched(status="postponed")])[0] is False


def test_only_the_frequent_schedule_can_be_skipped():
    for schedule in ("", "19 10 * * *", "47 3 * * *"):               # push / dispatch, and the two daily crons
        run, why = gate("2026-11-14 04:00", [], schedule=schedule)
        assert run is True and "always runs" in why


def test_a_game_with_no_usable_date_in_the_history_never_counts_as_the_result():
    undated = {**played("2026-11-14"), "date_known": False}
    assert gate("2026-11-14 16:37", [sched()], [undated])[0] is True


def test_the_cli_reads_the_committed_files_and_writes_only_the_output_file(tmp_path, monkeypatch, capsys):
    up, series = tmp_path / "upcoming.json", tmp_path / "series.json"
    up.write_text(json.dumps({"schema_version": 1, "sports": {"football": {"schedule_url": "x", "games": [sched()]}}}))
    series.write_text(json.dumps({"sports": {"football": {"name": "Football", "games": [game("2025-11-15", "W", 41, 20)]}}}))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    out = tmp_path.parent / f"{tmp_path.name}-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    code = gameday.main(["gate", "--schedule", FREQ, "--now", "2026-11-12T12:00:00-05:00",
                         "--upcoming", str(up), "--series", str(series)])
    assert code == 0 and out.read_text() == "run=false\n"
    assert "run=false: no game-day window is open" in capsys.readouterr().out
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()} == before   # no commits to make

    out.unlink()
    gameday.main(["gate", "--schedule", FREQ, "--now", "2026-11-14T14:00:00-05:00",
                  "--upcoming", str(up), "--series", str(series)])
    assert out.read_text() == "run=true\n"


def test_the_gate_stops_and_says_so_when_it_cannot_read_the_data(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    code = gameday.main(["gate", "--schedule", FREQ, "--series", str(tmp_path / "missing.json"),
                         "--upcoming", str(tmp_path / "missing2.json")])
    assert code == 1 and out.read_text() == "run=false\n" and "could not read" in capsys.readouterr().err


def test_the_gate_imports_nothing_outside_the_standard_library():
    import ast
    modules = set()
    for name in ("gameday", "meetings", "timeutil"):
        tree = ast.parse((ROOT / "scraper" / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules.add(node.module.split(".")[0])
    assert modules <= set(sys.stdlib_module_names) | {"meetings", "timeutil"}, modules


# ---- the banner ---------------------------------------------------------- #

def banner(tmp_path, now, games, sports=None, text=True):
    sports = sports or {"football": football()}
    up = tmp_path / "upcoming.json"
    up.write_text(json.dumps({"schema_version": 1, "sports": {
        k: {"schedule_url": "https://depauwtigers.com/sports/x/schedule", "games": g} for k, g in games.items()}}))
    out, html = build(tmp_path, sports, now=et(now), upcoming_path=up)
    m = re.search(r'<section class="game-day".*?</section>', html, re.S)
    return (text_of(m.group(0)).strip() if text else m.group(0)) if m else None, html, out


def test_before_the_start_it_says_game_day_with_the_time_and_place(tmp_path):
    t, html, _ = banner(tmp_path, "2026-11-14 07:30", {"football": [sched()]})
    assert t == "Game day: Football vs. Wabash today, 1:07 PM · Scheumann Stadium, Muncie, Ind."
    assert html.index('class="game-day"') < html.index('id="next-meeting"') < html.index('id="overall-h"')


def test_after_the_scheduled_start_it_says_underway_until_the_result_is_in(tmp_path):
    t, _, _ = banner(tmp_path, "2026-11-14 13:07", {"football": [sched()]})
    assert t == ("Football vs. Wabash is underway or just finished. "
                 "The result will appear here soon after it's posted.")
    t, _, _ = banner(tmp_path, "2026-11-14 22:00", {"football": [sched()]})
    assert t.startswith("Football vs. Wabash is underway or just finished.")


def test_once_the_result_is_in_it_shows_the_final_winner_first_and_links_to_the_card(tmp_path):
    sports = {"football": football(played("2026-11-14", "W", 41, 20))}
    t, _, _ = banner(tmp_path, "2026-11-14 17:00", {"football": [sched()]}, sports)
    assert t == "Final: DePauw 41, Wabash 20 · DePauw holds the Monon Bell."
    sports = {"football": football(played("2026-11-14", "L", 20, 27))}
    t, html, _ = banner(tmp_path, "2026-11-14 17:00", {"football": [sched()]}, sports)
    assert t == "Final: Wabash 27, DePauw 20 · Wabash holds the Monon Bell."
    assert '<a href="#football">Final: Wabash 27, DePauw 20</a>' in html and 'id="football"' in html


def test_the_final_stays_up_after_the_game_drops_off_the_schedule(tmp_path):
    sports = {"football": football(played("2026-11-14", "W", 41, 20))}
    t, _, _ = banner(tmp_path, "2026-11-14 23:50", {"football": []}, sports)      # schedule page already dropped it
    assert t.startswith("Final: DePauw 41, Wabash 20")


def test_a_tie_is_a_final_too_and_the_bell_stays_where_it_was(tmp_path):
    sports = {"football": football(played("2026-11-14", "T", 7, 7))}
    t, _, _ = banner(tmp_path, "2026-11-14 17:00", {"football": [sched()]}, sports)
    assert t == "Final: Tie 7–7 · DePauw holds the Monon Bell."


def test_only_football_mentions_the_bell(tmp_path):
    sports = {"mens-lacrosse": sport("mens-lacrosse", "Men's Lacrosse", lacrosse()["games"] + [
        played("2026-04-10", "W", 12, 4, location="home", site="Greencastle, IN")])}
    t, _, _ = banner(tmp_path, "2026-04-10 20:00", {"mens-lacrosse": [sched("2026-04-10", "1:00 PM", location="home", site="Greencastle, IN")]}, sports)
    assert t == "Final: DePauw 12, Wabash 4" and "Bell" not in t


def test_two_sports_on_one_day_share_one_banner_each_in_its_own_phase(tmp_path):
    sports = {"football": football(played("2026-11-14", "W", 41, 20)), "mens-lacrosse": lacrosse()}
    games = {"football": [sched()], "mens-lacrosse": [sched(time="3:00 PM", location="home", site="Greencastle, IN")]}
    t, html, _ = banner(tmp_path, "2026-11-14 14:00", games, sports)
    assert html.count('class="game-day"') == 1
    assert t == ("Final, Football: DePauw 41, Wabash 20 · DePauw holds the Monon Bell. "
                 "Game day: Men's Lacrosse vs. Wabash today, 3:00 PM · Greencastle, Ind.")


def test_a_doubleheader_banner_lists_every_game(tmp_path):
    bs = sport("baseball", "Baseball", [game("2026-04-28", "L", 3, 15)])
    dh = [sched("2027-04-28", "12:00 PM", location="away", site="Goodrich Ballpark, Crawfordsville, IN"),
          sched("2027-04-28", None, location="away", site="Goodrich Ballpark, Crawfordsville, IN")]
    t, _, _ = banner(tmp_path, "2027-04-28 08:00", {"baseball": dh}, {"baseball": bs})
    assert t == ("Game day: Baseball vs. Wabash today (doubleheader), 12:00 PM and TBA · "
                 "Goodrich Ballpark, Crawfordsville, Ind.")
    both = [*bs["games"], played("2027-04-28", "W", 5, 3), played("2027-04-28", "L", 2, 4)]
    t, _, _ = banner(tmp_path, "2027-04-28 19:00", {"baseball": []}, {"baseball": sport("baseball", "Baseball", both)})
    assert t == "Final: DePauw 5, Wabash 3 and Wabash 4, DePauw 2"
    one = sport("baseball", "Baseball", both[:-1])
    t, _, _ = banner(tmp_path, "2027-04-28 15:00", {"baseball": dh}, {"baseball": one})
    assert t.startswith("Baseball vs. Wabash is underway")               # game 1 is in, game 2 is not


def test_a_game_with_no_time_says_so_and_counts_as_underway_from_noon(tmp_path):
    t, _, _ = banner(tmp_path, "2026-11-14 09:00", {"football": [sched(time=None)]})
    assert t == "Game day: Football vs. Wabash today, time TBA · Scheumann Stadium, Muncie, Ind."
    t, _, _ = banner(tmp_path, "2026-11-14 12:00", {"football": [sched(time=None)]})
    assert t.startswith("Football vs. Wabash is underway")


def test_no_banner_when_nothing_is_played_today_or_the_game_is_postponed(tmp_path):
    for now, games in (("2026-11-13 12:00", [sched()]), ("2026-11-14 12:00", [sched(status="postponed")]),
                       ("2026-11-14 12:00", [])):
        t, html, _ = banner(tmp_path, now, {"football": games})
        assert t is None and "game-day" not in html


def test_the_banner_is_gone_at_the_first_deploy_after_game_day(tmp_path):
    sports = {"football": football(played("2026-11-14", "W", 41, 20))}
    assert banner(tmp_path, "2026-11-14 23:47", {"football": []}, sports)[0].startswith("Final")   # the 11:47 PM run
    assert banner(tmp_path, "2026-11-15 06:19", {"football": []}, sports)[0] is None                # the 6:19 AM run
    assert banner(tmp_path, "2026-11-15 01:00", {"football": [sched()]})[0] is None   # after midnight, even if the window is open


def test_a_game_already_in_the_history_is_not_also_shown_as_the_next_meeting(tmp_path):
    sports = {"football": football(played("2026-11-14", "W", 41, 20))}
    _, html, _ = banner(tmp_path, "2026-11-14 17:00", {"football": [sched()]}, sports)
    assert 'id="next-meeting"' not in html and "Next meeting" not in text_of(html)


def test_the_banner_is_static_html_with_no_script_or_inline_style(tmp_path):
    _, html, _ = banner(tmp_path, "2026-11-14 17:00", {"football": [sched()]})
    assert "<script" not in html and "style=" not in html


# ---- the share image ----------------------------------------------------- #

def test_the_share_image_gets_a_game_day_or_final_line_and_a_new_version(tmp_path):
    plain = images.og_image({"depauw_wins": 5, "wabash_wins": 3, "ties": 1}, "DePauw")
    day = images.og_image({"depauw_wins": 5, "wabash_wins": 3, "ties": 1}, "DePauw", "Game day")
    final = images.og_image({"depauw_wins": 5, "wabash_wins": 3, "ties": 1}, "DePauw", "Final")
    assert len({plain, day, final}) == 3
    t = {"depauw_wins": 5, "wabash_wins": 3, "ties": 1}
    assert len({images.og_version(t, "DePauw"), images.og_version(t, "DePauw", "Game day"),
                images.og_version(t, "DePauw", "Final")}) == 3
    assert images.og_version(t, "DePauw", None) == images.og_version(t, "DePauw")      # a normal day is unchanged


def test_the_page_points_at_the_matching_image_version_and_describes_it(tmp_path):
    _, html, out = banner(tmp_path, "2026-11-14 08:00", {"football": [sched()]})
    version = lambda page: re.search(r"og-image\.png\?v=(\w+)", page).group(1)
    _, normal, _ = banner(tmp_path, "2026-11-13 08:00", {"football": [sched()]})
    assert version(html) != version(normal) and "Game day." in html
    sports = {"football": football(played("2026-11-14", "W", 41, 20))}
    _, final, _ = banner(tmp_path, "2026-11-14 18:00", {"football": []}, sports)
    assert "Final." in final and version(final) not in (version(html), version(normal))
    assert (out / "og-image.png").exists()


# ---- carrying a just-finished game over --------------------------------- #

TODAY = dt.date(2026, 11, 14)


def test_a_game_that_dropped_off_the_schedule_is_kept_until_the_history_has_it():
    kept = upcoming.carry_over([sched()], [], history_dates=[], canceled=set(), today=TODAY)
    assert kept == [sched()]
    assert upcoming.carry_over([sched()], [], history_dates=["2026-11-14"], canceled=set(), today=TODAY) == []


def test_it_is_still_kept_the_next_day_and_then_let_go():
    assert upcoming.carry_over([sched()], [], history_dates=[], canceled=set(), today=dt.date(2026, 11, 15)) == [sched()]
    assert upcoming.carry_over([sched()], [], history_dates=[], canceled=set(), today=dt.date(2026, 11, 16)) == []


def test_a_game_still_on_the_schedule_is_not_carried_twice_and_a_canceled_one_is_never_carried():
    assert upcoming.carry_over([sched()], [sched()], history_dates=[], canceled=set(), today=TODAY) == []
    assert upcoming.carry_over([sched()], [], history_dates=[], canceled={"2026-11-14"}, today=TODAY) == []


def test_a_game_from_the_future_or_a_postponed_one_is_not_carried():
    assert upcoming.carry_over([sched("2026-11-20")], [], history_dates=[], canceled=set(), today=TODAY) == []
    assert upcoming.carry_over([sched(status="postponed")], [], history_dates=[], canceled=set(), today=TODAY) == []


def test_for_a_doubleheader_only_the_game_that_dropped_off_and_is_missing_is_carried():
    g1, g2 = sched("2026-11-14", "12:00 PM"), sched("2026-11-14", "3:30 PM")
    assert upcoming.carry_over([g1, g2], [g2], history_dates=[], canceled=set(), today=TODAY) == [g1]
    assert upcoming.carry_over([g1, g2], [g2], history_dates=["2026-11-14"], canceled=set(), today=TODAY) == []
    assert upcoming.carry_over([g1, g2], [], history_dates=["2026-11-14"], canceled=set(), today=TODAY) == [g2]


def test_the_parser_reports_canceled_dates_for_the_carry_over():
    head, row = (ROOT / "tests" / "fixtures" / "schedule-football.html").read_text(encoding="utf-8").split(
        'data-game-opponent-id="215"')
    row = row.replace('<div class="sidearm-schedule-game-conference-conference',
                      '<div class="sidearm-schedule-game-result"><span>Canceled</span></div>'
                      '<div class="sidearm-schedule-game-conference-conference', 1)
    seen = []
    assert upcoming.parse_schedule(head + 'data-game-opponent-id="215"' + row, opponent_id=215, canceled=seen) == []
    assert seen == ["2026-11-14"]


def finished_football_page():
    """The real football schedule fixture with the Wabash game marked finished, as a schedule page does just
    after the game (it then lists a result, so the parser leaves the game out)."""
    html = (ROOT / "tests" / "fixtures" / "schedule-football.html").read_text(encoding="utf-8")
    return html.replace("sidearm-schedule-game-upcoming", "sidearm-schedule-game-completed")


def schedule_run(tmp_path, page, previous, history, today):
    d = tmp_path / "pages"
    d.mkdir(exist_ok=True)
    (d / "football-schedule.html").write_text(page, encoding="utf-8")
    cfg = json.loads(scrape.SOURCES.read_text(encoding="utf-8"))
    cfg["sports"] = [s for s in cfg["sports"] if s["key"] == "football"]
    return scrape.scrape_schedules(cfg, previous, d, scrape.Pacer(), history=history, today=today)


def test_the_scraper_keeps_the_game_when_the_schedule_posts_the_final_before_the_history_does(tmp_path):
    previous = {"football": {"schedule_url": "x", "games": [sched()]}}
    got = schedule_run(tmp_path, finished_football_page(), previous, {"football": ["2025-11-15"]}, TODAY)
    assert [g["date"] for g in got["football"]["games"]] == ["2026-11-14"]
    # the history now has it: the game leaves the file and the window closes
    got = schedule_run(tmp_path, finished_football_page(), previous, {"football": ["2026-11-14"]}, TODAY)
    assert got["football"]["games"] == []
    # without history information (an older caller) nothing is carried
    assert schedule_run(tmp_path, finished_football_page(), previous, None, None)["football"]["games"] == []


# ---- the workflow --------------------------------------------------------- #

def job(name):
    m = re.search(rf"^  {name}:\n(.*?)(?=^  \w[\w-]*:\n|\Z)", WORKFLOW, re.S | re.M)
    assert m, name
    return m.group(1)


def test_the_frequent_cron_in_the_workflow_is_the_one_the_gate_recognises_and_is_jittered():
    crons = re.findall(r'^\s+- cron: "([^"]+)"', WORKFLOW, re.M)
    assert crons == ["19 10 * * *", "47 3 * * *", FREQ]                  # the two daily runs are unchanged
    minutes = FREQ.split()[0].split(",")
    assert minutes == ["7", "37"] and "0" not in minutes and "30" not in minutes


def test_only_the_gate_decides_and_build_deploy_and_report_follow_it():
    assert "needs: gate" in job("build") and "needs.gate.outputs.run == 'true'" in job("build")
    assert "needs: build" in job("deploy") and "needs.build.result == 'success'" in job("deploy")
    assert "needs.build.outputs.problems" in job("report")
    for step in ("Scrape", "Commit if data changed", "Render site", "upload-pages-artifact"):
        assert step in job("build") and step not in job("gate")        # nothing that changes anything runs in the gate
    assert "git push" not in job("gate") and "git commit" not in job("gate")


def test_a_skipped_build_means_no_commit_no_deploy_and_no_new_check_time():
    # build is skipped when the gate says no, so its commit and scrape steps (the only place .checked-at and
    # data/ are written) never run, and deploy only runs when build succeeded.
    assert "contents: write" in job("build") and "contents: write" not in job("gate")
    assert "checked" not in job("gate").lower()
    assert "!cancelled() && needs.build.result == 'success'" in job("deploy")


def test_the_gate_installs_nothing_and_uses_the_runners_own_python():
    g = job("gate")
    assert "setup-python" not in g and "pip install" not in g and "python3 scraper/gameday.py gate" in g
    assert "SCHEDULE: ${{ github.event.schedule }}" in g                 # passed through env, never spliced into the shell


def test_frequent_runs_cannot_pile_up_or_cancel_a_running_scheduled_run():
    assert not re.search(r"^concurrency:", WORKFLOW, re.M)               # no workflow-level group for no-op runs to queue in
    assert "group: update-and-deploy" in job("build") and "group: pages" in job("deploy")
    assert "group:" not in job("gate")
    assert WORKFLOW.count("cancel-in-progress: false") == 2 and "cancel-in-progress: true" not in WORKFLOW


def test_the_preview_only_now_option_never_reaches_the_workflow():
    assert "--now" not in WORKFLOW
    assert "--now" in (ROOT / "scraper" / "render.py").read_text(encoding="utf-8")


def test_now_option_reads_eastern_without_an_offset_and_utc_with_one():
    assert render.parse_now(None) is None
    assert render.parse_now("2026-11-14T13:07") == dt.datetime(2026, 11, 14, 18, 7, tzinfo=dt.timezone.utc)   # EST
    assert render.parse_now("2026-10-14T13:07") == dt.datetime(2026, 10, 14, 17, 7, tzinfo=dt.timezone.utc)   # EDT
    assert render.parse_now("2026-11-14T13:07:00+00:00") == dt.datetime(2026, 11, 14, 13, 7, tzinfo=dt.timezone.utc)
