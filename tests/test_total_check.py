"""The total-points check: each page's own "Total Points/Goals/Runs" box against the sum of its parsed games.

It is a warning for now (the page's data is kept and the run stays green), so these tests pin both halves:
a mismatch is reported, and nothing else about the run changes."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "tests"))
import scrape  # noqa: E402
from test_scrape import SPORT_KEYS, WABASH_BASE, both_dir, fixture_dir, full_html, parse, parse_wabash  # noqa: E402,F401


def page_html(key, school):
    """The captured page: DePauw's soccer, lacrosse and tennis are whole pages, the others are rebuilt."""
    if school == "DePauw" and (FIX / f"{key}.html").exists():
        return (FIX / f"{key}.html").read_text(encoding="utf-8")
    return full_html(key if school == "DePauw" else f"wabash-{key}")


def test_every_captured_page_matches_its_own_total():
    """All 14 pages (7 sports, 2 schools) as captured live: no warning."""
    checked = 0
    for key in SPORT_KEYS:
        for school, parser in (("DePauw", parse), ("Wabash", parse_wabash)):
            html = page_html(key, school)
            games, summary, _ = parser(html)
            assert summary.total is not None, (school, key)
            assert scrape.total_warning(games, summary, school, key) is None, (school, key)
            checked += 1
    assert checked == 14


def test_a_total_that_disagrees_gives_a_warning_with_both_figures_and_the_difference():
    games, summary, _ = parse(full_html("football"))
    summary.total += 3
    found = scrape.total_warning(games, summary, "DePauw", "Football")
    assert found == {"school": "DePauw", "sport": "Football", "label": "points", "page": 1920, "parsed": 1917,
                     "difference": 3}


def test_a_page_without_a_total_box_is_not_checked():
    games, summary, _ = parse(full_html("football"))
    summary.total = None
    assert scrape.total_warning(games, summary, "DePauw", "Football") is None


def test_unscored_results_are_left_out_of_the_sum_and_half_points_stay_exact():
    wabash, summary, _ = parse_wabash(full_html("wabash-mens-swimming-and-diving"))
    assert sum(1 for g in wabash if not g.score_known) == 2                 # the two 1934 meets, "L -"
    assert scrape.printed_total(wabash) == summary.total == 4612
    depauw, summary, _ = parse(full_html("mens-swimming-and-diving"))
    total = scrape.printed_total(depauw)
    assert total == summary.total == 4459.5 and not float(total).is_integer()   # half points kept exact


def test_a_reversed_score_row_counts_as_printed_not_as_swapped():
    wabash, summary, _ = parse_wabash(full_html("wabash-mens-swimming-and-diving"))
    reversed_rows = [g for g in wabash if g.score_order_reversed]
    assert len(reversed_rows) == 1                                          # Nov 12, 2008: "L 153 - 141"
    swapped_sum = sum(g.depauw for g in wabash if g.score_known)
    assert swapped_sum == 4600 and scrape.printed_total(wabash) == 4612     # the page's own box adds what is printed
    assert scrape.total_warning(wabash, summary, "Wabash", "Swimming") is None


def tampered(both_dir, name, new_total):
    page = both_dir / name
    html = page.read_text(encoding="utf-8")
    html, n = re.subn(r'(<h2>Total \w+</h2>\s*<div class="sidearm-opponent-history__item--number">)\s*[\d.,]+\s*', rf"\g<1> {new_total} ", html)
    assert n == 1
    page.write_text(html, encoding="utf-8")


def test_a_mismatch_is_only_a_warning_the_data_is_kept_and_the_run_stays_green(both_dir, tmp_path, capsys, monkeypatch):
    summary_file = tmp_path / "step-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    out = tmp_path / "series.json"
    assert scrape.main(["--fixtures", str(both_dir), "--output", str(out)]) == 0          # clean pages: green, no warning
    assert "total" not in capsys.readouterr().err.lower() and not summary_file.exists()
    before = json.loads(out.read_text(encoding="utf-8"))

    tampered(both_dir, "football.html", 1920)
    tampered(both_dir, "wabash-baseball.html", 1000)
    out2 = tmp_path / "again" / "series.json"
    out2.parent.mkdir()
    assert scrape.main(["--fixtures", str(both_dir), "--output", str(out2)]) == 0          # still green
    err = capsys.readouterr().err
    assert "WARN Football         DePauw  total points: page says 1920, parsed games add up to 1917 (difference +3)" in err
    assert "WARN Baseball         Wabash  total runs: page says 1000, parsed games add up to 1743 (difference -743)" in err
    assert "WARN 2 page(s) whose own total does not match the parsed games (data kept, run not failed):" in err
    after = json.loads(out2.read_text(encoding="utf-8"))
    assert after["sports"] == before["sports"]                  # the games of both pages were kept and merged as before
    listed = summary_file.read_text(encoding="utf-8")
    assert listed.startswith("### Total points check (warning only)")
    assert "Football, DePauw's page: total points 1920, parsed games add up to 1917 (page minus parsed +3)" in listed
    assert "Baseball, Wabash's page: total runs 1000" in listed


def test_the_summary_file_is_only_written_when_there_is_something_to_list(tmp_path, monkeypatch):
    target = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    scrape.report_total_warnings([])
    assert not target.exists()
