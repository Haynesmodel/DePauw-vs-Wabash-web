"""Tests for merging DePauw's and Wabash's records (scraper/merge.py), on made-up games and on the
real pages captured from both sites on 2026-10-28."""
import random
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts  # noqa: E402
import merge  # noqa: E402
import scrape  # noqa: E402
from test_scrape import FIX as scrape_fixtures, full_html, parse, parse_wabash  # noqa: E402


def g(date, d=10, w=5, season=None, loc="home", site=None, note=None, box=None):
    """A game in DePauw's point of view; the result follows from the score."""
    result = "W" if d > w else "L" if d < w else "T"
    return {"date": date, "season": season or date[:4], "location": loc, "site": site, "result": result,
            "depauw": d, "wabash": w, "note": note, "boxscore": box}


def merged(depauw, wabash, **kw):
    return merge.merge_sport(depauw, wabash, **kw)


# ---- the matching passes ------------------------------------------------------------------- #

def test_the_same_date_and_score_is_one_game_from_both_records():
    r = merged([g("2020-11-14", 20, 10)], [g("2020-11-14", 20, 10)])
    assert len(r.games) == 1
    only = r.games[0]
    assert only["source"] == "both" and "disputed" not in only and "date_differs" not in only
    assert r.stats == {"both": 1, "depauw_only": 0, "wabash_only": 0, "disputed": 0, "date_differs": 0,
                       "dates_not_recorded": 0}


def test_a_doubleheader_pairs_by_score_then_by_order():
    d = [g("2024-04-10", 6, 2), g("2024-04-10", 3, 9)]
    w = [g("2024-04-10", 3, 9), g("2024-04-10", 6, 2)]       # Wabash lists the games in the other order
    r = merged(d, w)
    assert r.stats["both"] == 2 and r.stats["depauw_only"] == r.stats["wabash_only"] == 0
    assert [(x["depauw"], x["wabash"]) for x in r.games] == [(6, 2), (3, 9)]    # DePauw's order is kept


def test_a_doubleheader_with_identical_scores_pairs_each_row_once():
    r = merged([g("1992-04-01", 2, 1), g("1992-04-01", 2, 1)], [g("1992-04-01", 2, 1), g("1992-04-01", 2, 1)])
    assert r.stats["both"] == 2 and len(r.games) == 2
    one_short = merged([g("1992-04-01", 2, 1), g("1992-04-01", 2, 1)], [g("1992-04-01", 2, 1)])
    assert (one_short.stats["both"], one_short.stats["depauw_only"], len(one_short.games)) == (1, 1, 2)


def test_a_placeholder_date_matches_by_season_and_score_and_keeps_depauws_date():
    d = [g("1997-04-09", 9, 0, season="1996-97")]
    w = [g("1997-01-01", 9, 0, season="1997")]
    r = merged(d, w)
    game = r.games[0]
    assert game["source"] == "both" and game["date"] == "1997-04-09" and game["season"] == "1996-97"
    assert "date_differs" not in game and "date_known" not in game and r.stats["dates_not_recorded"] == 0


def test_a_placeholder_with_no_match_stays_a_wabash_game_with_no_known_date():
    r = merged([g("1997-04-09", 9, 0, season="1996-97")],
               [g("1915-01-01", 0, 3, season="1915"), g("1997-01-01", 8, 1, season="1997")])
    wabash = [x for x in r.games if x["source"] == "wabash"]
    assert len(wabash) == 2 and all(x["date_known"] is False for x in wabash)
    assert r.stats["dates_not_recorded"] == 2 and r.stats["both"] == 0


def test_only_jan_1_to_3_count_as_placeholders_and_a_confirmed_date_is_real():
    assert [merge.is_placeholder(g(d)) for d in ("2020-01-01", "2020-01-03", "2020-01-04", "2020-02-01")] == \
        [True, True, False, False]
    r = merged([g("1978-01-02", 82, 73)], [g("1978-01-02", 82, 73)])     # DePauw agrees on a Jan 2 date
    assert r.games[0]["source"] == "both" and "date_known" not in r.games[0]
    real = merged([], [g("1889-01-05", 2, 5)])                           # not Jan 1-3: taken at its word
    assert "date_known" not in real.games[0]


@pytest.mark.parametrize("days", [1, 2])
def test_a_date_a_day_or_two_apart_with_the_same_score_is_one_game_flagged(days):
    r = merged([g("2005-03-16", 11, 1)], [g(f"2005-03-{16 + days}", 11, 1)])
    game = r.games[0]
    assert game["source"] == "both" and game["date"] == "2005-03-16"
    assert game["date_differs"] is True and game["wabash_date"] == f"2005-03-{16 + days}"
    assert r.stats["date_differs"] == 1 and len(r.date_differs) == 1


def test_three_days_apart_needs_the_season_pass_and_is_two_games_without_it():
    d, w = [g("1990-04-07", 8, 7)], [g("1990-04-04", 8, 7)]
    assert len(merged(d, w, loose=False).games) == 2
    r = merged(d, w, loose=True)
    assert len(r.games) == 1 and r.games[0]["date_differs"] is True and r.games[0]["wabash_date"] == "1990-04-04"


def test_the_season_pass_only_pairs_when_both_sides_have_the_same_number_left():
    d = [g("1986-03-19", 12, 4), g("1986-03-19", 12, 4)]
    w = [g("1986-03-23", 12, 4)]                      # two on one side, one on the other: a guess, so no
    assert len(merged(d, w, loose=True).games) == 3
    w2 = [g("1986-03-23", 12, 4), g("1986-03-23", 12, 4)]
    assert len(merged(d, w2, loose=True).games) == 2
    other_season = merged([g("1906-01-29", 7, 40, season="1905-06")], [g("1906-12-30", 7, 40, season="1906-07")],
                          loose=True)
    assert len(other_season.games) == 2               # a different season is never the same game


def test_the_same_date_with_a_different_score_is_a_dispute_and_depauws_score_counts():
    r = merged([g("1913-01-15", 20, 46)], [g("1913-01-15", 20, 47)])
    game = r.games[0]
    assert game["source"] == "both" and game["disputed"] is True
    assert (game["depauw"], game["wabash"], game["result"]) == (20, 46, "L")
    assert game["wabash_version"] == {"result": "L", "depauw": 20, "wabash": 47}
    assert r.stats["disputed"] == 1 and merge.tally(r.games) == (0, 1, 0)


def test_a_dispute_can_be_over_who_won():
    r = merged([g("1941-11-15", 19, 7)], [g("1941-11-15", 7, 19)])
    game = r.games[0]
    assert game["disputed"] and game["result"] == "W" and game["wabash_version"]["result"] == "L"
    assert merge.tally(r.games) == (1, 0, 0)          # DePauw's version is the one that counts


def test_a_game_only_one_school_lists_still_counts_and_says_whose_record_it_is():
    r = merged([g("2001-04-01", 3, 2)], [g("2002-04-01", 1, 4)])
    by_source = {x["source"]: x for x in r.games}
    assert set(by_source) == {"depauw", "wabash"} and by_source["wabash"]["result"] == "L"
    assert r.stats["depauw_only"] == r.stats["wabash_only"] == 1 and merge.tally(r.games) == (1, 1, 0)


def test_both_records_fill_each_others_gaps_but_depauws_values_win():
    d = g("2020-11-14", 20, 10, loc="unknown", site=None, note=None, box=None)
    w = g("2020-11-14", 20, 10, loc="home", site="Greencastle, IN", note="2 OT",
          box="https://sports.wabash.edu/boxscore.aspx?id=1")
    game = merged([d], [w]).games[0]
    assert (game["location"], game["site"], game["note"]) == ("home", "Greencastle, IN", "2 OT")
    assert game["boxscore"] == "https://sports.wabash.edu/boxscore.aspx?id=1"
    kept = merged([g("2020-11-14", 20, 10, site="Blackstock Stadium", note="OT")],
                  [g("2020-11-14", 20, 10, site="Greencastle, IN", note="2 OT")]).games[0]
    assert (kept["site"], kept["note"]) == ("Blackstock Stadium", "OT")


def test_seasons_are_written_one_way_on_the_page():
    assert merge.normalize_season("1966-1967", "1967-03-01") == "1966-67"
    assert merge.normalize_season("1999-00", "2000-02-01") == "1999-00"
    assert merge.normalize_season("1997", "1997-04-01") == "1997"
    assert merge.season_key(g("1997-04-09", season="1996-97")) == merge.season_key(g("1997-01-01", season="1997")) \
        == merge.season_key(g("1997-04-09", season="1996-1997")) == 1997
    assert merge.season_key(g("2000-02-01", season="1999-00")) == 2000
    assert merge.season_key(g("1999-11-01", season="odd label")) == 1999        # unreadable: the game's own year


def test_wabashs_view_flips_to_depauws():
    w = {"date": "2025-11-15", "season": "2025", "location": "home", "site": "Crawfordsville, Ind.",
         "result": "L", "depauw": 20, "wabash": 41, "note": None, "boxscore": None}     # Wabash's own page
    f = merge.flip(w)
    assert (f["result"], f["depauw"], f["wabash"], f["location"]) == ("W", 41, 20, "away")
    assert merge.flip(merge.flip(w)) == w
    assert merge.flip({**w, "location": "neutral"})["location"] == "neutral"
    assert merge.flip({**w, "location": "unknown", "result": "T"})["result"] == "T"


# ---- no row is ever used twice ---------------------------------------------------------------- #

def test_one_wabash_row_cannot_match_two_depauw_games():
    d = [g("2005-03-15", 11, 1), g("2005-03-17", 11, 1)]       # both within 2 days of Wabash's one row
    w = [g("2005-03-16", 11, 1)]
    r = merged(d, w, loose=False)
    assert r.stats["both"] == 1 and r.stats["depauw_only"] == 1 and len(r.games) == 2


@pytest.mark.parametrize("seed", range(40))
def test_every_row_is_accounted_for_exactly_once_on_random_data(seed):
    rnd = random.Random(seed)

    def games():
        out = []
        for _ in range(rnd.randint(0, 25)):
            day = rnd.choice(["01-01", "01-02", "03-14", "03-15", "03-16", "04-02", "04-02", "11-09"])
            out.append(g(f"{rnd.choice([1990, 1991])}-{day}", rnd.randint(0, 3), rnd.randint(0, 3)))
        return sorted(out, key=lambda x: x["date"])

    d, w = games(), games()
    for loose in (False, True):
        r = merged(d, w, loose=loose)            # raises MergeError if the books do not balance
        s = r.stats
        assert s["both"] + s["depauw_only"] == len(d) and s["both"] + s["wabash_only"] == len(w)
        assert len(r.games) == s["both"] + s["depauw_only"] + s["wabash_only"]
        assert merge.tally(r.games) == tuple(a + b for a, b in zip(merge.tally(d), merge.tally(r.wabash_only)))
        assert sum(1 for x in r.games if x["source"] == "both") == s["both"]
        assert [x["date"] for x in r.games] == sorted(x["date"] for x in r.games)


def test_a_merge_that_does_not_add_up_is_an_error_not_wrong_data():
    r = merged([g("2020-11-14", 20, 10)], [g("2020-11-14", 20, 10)])
    r.stats["both"] = 2
    with pytest.raises(merge.MergeError):
        merge.check([g("2020-11-14", 20, 10)], [g("2020-11-14", 20, 10)], r)


def test_leftovers_that_look_like_the_same_game_are_listed_not_merged():
    r = merged([g("1984-04-25", 12, 5)], [g("1984-04-24", 11, 5)], loose=True)
    assert len(r.games) == 2
    near = merge.near_misses(r)
    assert len(near) == 1 and near[0]["days"] == 1 and near[0]["same_score"] is False
    assert merge.near_misses(merged([g("2000-04-01", 2, 1)], [g("2001-04-01", 2, 1)])) == []


def test_the_run_summary_names_every_count():
    r = merged([g("2020-11-14", 20, 10), g("2021-11-13", 3, 0)], [g("2020-11-14", 20, 10), g("2022-11-12", 1, 2)])
    assert merge.summary_line("Football", r.stats) == \
        "Football: 1 matched, 1 DePauw only, 1 Wabash only, 0 disputed, 0 date-differs"


# ---- the real pages -------------------------------------------------------------------------- #

def both_schools(key):
    """(DePauw's games, Wabash's games flipped to DePauw's view), parsed and validated as the scraper does."""
    subset = scrape_fixtures / f"{key}-subset.html"       # the big pages are stored as subset + expected games
    dg, ds, _ = parse(full_html(key) if subset.exists() else (scrape_fixtures / f"{key}.html").read_text(encoding="utf-8"))
    wg, ws, _ = parse_wabash(full_html(f"wabash-{key}"))
    assert scrape.validate(dg, ds) == [] and scrape.validate(wg, ws) == []     # each page against its own summary
    return scrape.game_dicts(dg, "depauw"), scrape.game_dicts(wg, "wabash")


def test_real_football_merges_to_the_same_131_games_both_schools_list():
    d, w = both_schools("football")
    r = merged(d, w)
    assert len(r.games) == 131 and merge.tally(r.games) == (59, 63, 9)
    assert r.stats == {"both": 131, "depauw_only": 0, "wabash_only": 0, "disputed": 2, "date_differs": 3,
                       "dates_not_recorded": 0}
    # The two schools disagree on two scores (1901 and 1941); neither changes who won.
    assert sorted(x["date"] for x in r.disputed) == ["1901-11-11", "1941-11-15"]
    assert all(x["wabash_version"]["result"] == x["result"] for x in r.disputed)
    b = facts.bell(r.games)
    assert (b["depauw"], b["wabash"], b["ties"]) == (43, 44, 6)               # the Monon Bell record is unchanged
    assert (b["holder"], b["since"]) == ("DePauw", 2022)


def test_real_football_would_count_a_game_twice_without_the_season_pass():
    d, w = both_schools("football")
    r = merged(d, w, loose=False)        # DePauw dates the 1891 game Nov 21 and Wabash Nov 2, both 1-0
    assert len(r.games) == 132 and merge.tally(r.games) == (60, 63, 9)
    assert [(m["depauw"]["date"], m["wabash"]["date"]) for m in merge.near_misses(r)] == \
        [("1891-11-21", "1891-11-02")]


def test_real_tennis_gains_88_old_matches_with_no_date_and_two_with_dates():
    d, w = both_schools("mens-tennis")
    r = merged(d, w)
    assert (len(d), len(w), len(r.games)) == (33, 123, 123)
    assert merge.tally(r.games) == (115, 7, 1)
    assert r.stats == {"both": 33, "depauw_only": 0, "wabash_only": 90, "disputed": 1, "date_differs": 0,
                       "dates_not_recorded": 88}
    assert [x["date"] for x in r.disputed] == ["2011-04-13"] and r.disputed[0]["depauw"] == 9
    one_nine_ninety_seven = [x for x in r.games if x["date"].startswith("1997")]
    assert [(x["source"], x["date"]) for x in one_nine_ninety_seven] == [("both", "1997-04-09")]
    # No Wabash-only game sits on a Jan 1 date as if it were real.
    assert not any(x["date"].endswith("-01-01") and x.get("date_known") is not False
                   for x in r.games if x["source"] == "wabash")


def test_real_baseball_is_mostly_wabash_games_from_before_1978():
    d, w = both_schools("baseball")
    r = merged(d, w)
    assert (len(d), len(w), len(r.games)) == (141, 314, 316)
    assert merge.tally(r.games) == (157, 156, 3)
    assert r.stats["both"] == 139 and r.stats["depauw_only"] == 2 and r.stats["wabash_only"] == 175
    assert r.stats["dates_not_recorded"] == 61 and r.stats["disputed"] == 0
    assert r.games[0]["date"] == "1888-01-03" and r.games[0]["date_known"] is False
    before = [x for x in r.games if x["date"] < "1978"]
    assert len(before) == 172 and all(x["source"] == "wabash" for x in before)


def test_real_basketball_has_seven_disputed_scores_and_the_1954_tie_in_both_records():
    d, w = both_schools("mens-basketball")
    r = merged(d, w)
    assert (len(d), len(w), len(r.games)) == (231, 233, 234) and merge.tally(r.games) == (133, 100, 1)
    assert r.stats["disputed"] == 7 and r.stats["date_differs"] == 17
    tie = next(x for x in r.games if x["result"] == "T")
    assert (tie["date"], tie["source"]) == ("1954-12-04", "both") and "disputed" not in tie
    assert r.stats["dates_not_recorded"] == 0       # the one Jan 1, 1967 row is confirmed by DePauw's Mar 1 game
    assert next(x for x in r.games if x["depauw"] == 81 and x["wabash"] == 70)["date"] == "1967-03-01"


def test_real_soccer_is_one_game_short_at_wabash_and_lacrosse_agrees_completely():
    d, w = both_schools("mens-soccer")
    r = merged(d, w)
    assert (len(d), len(w), len(r.games)) == (65, 64, 65) and merge.tally(r.games) == (41, 18, 6)
    assert r.stats == {"both": 64, "depauw_only": 1, "wabash_only": 0, "disputed": 0, "date_differs": 5,
                       "dates_not_recorded": 0}
    d, w = both_schools("mens-lacrosse")
    r = merged(d, w)
    assert r.stats == {"both": 12, "depauw_only": 0, "wabash_only": 0, "disputed": 0, "date_differs": 0,
                       "dates_not_recorded": 0}
    assert merge.tally(r.games) == (12, 0, 0)


def test_real_games_load_through_the_merge_without_losing_a_boxscore():
    d, w = both_schools("football")
    r = merged(d, w)
    assert sum(1 for x in r.games if x["boxscore"]) >= sum(1 for x in d if x["boxscore"])
