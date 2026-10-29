"""The review hold: a school's edit to an old game waits for a person (scraper/review.py)."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge  # noqa: E402
import review  # noqa: E402
import review_issue  # noqa: E402
import scrape  # noqa: E402
from test_scrape import both_dir, fixture_dir  # noqa: E402,F401  (pytest fixtures)

ROOT = Path(__file__).resolve().parent.parent


def game(date, us, them, season=None, **kw):
    result = "W" if us > them else "L" if us < them else "T"
    return {"date": date, "season": season or date[:4], "location": "Home", "site": "Greencastle, Ind.",
            "result": result, "depauw": us, "wabash": them, "note": None, "boxscore": None, **kw}


def settle(old, new, current=2025, pending=(), rules=(), apply=False, sport_rules=None):
    return review.settle("depauw", "football", old, new, current, "https://x/y", pending=list(pending),
                         rules=list(rules), sport_rules=sport_rules, apply_reviewed=apply,
                         now="2026-10-29T01:00:00+00:00")


# ---- the decision ------------------------------------------------------------------------------- #

def test_an_edited_old_score_is_held_and_keeps_the_saved_game():
    old = [game("1957-11-16", 37, 6), game("2025-11-15", 41, 20)]
    new = [game("1957-11-16", 37, 7), game("2025-11-15", 41, 20)]
    games, entries, _, _ = settle(old, new)
    assert games == old
    [e] = entries
    assert (e["kind"], e["school"], e["sport"], e["source_url"]) == ("edited", "depauw", "football", "https://x/y")
    assert (e["old"]["wabash"], e["new"]["wabash"], e["first_seen"]) == (6, 7, "2026-10-29T01:00:00+00:00")


def test_a_current_season_change_goes_straight_through():
    old = [game("1957-11-16", 37, 6), game("2025-11-15", 41, 20)]
    new = [game("1957-11-16", 37, 6), game("2025-11-15", 41, 21)]
    games, entries, _, _ = settle(old, new)
    assert games == new and entries == []


def test_the_current_season_is_the_newest_in_either_schools_data():
    # Wabash's page has a 2026 game; DePauw's saved copy ends in 2025, so 2025 is no longer current.
    assert review.current_season([game("2025-11-15", 1, 0)], [game("2026-11-14", 1, 0)]) == 2026
    old = [game("2025-11-15", 41, 20)]
    new = [game("2025-11-15", 41, 21)]
    _, entries, _, _ = settle(old, new, current=2026)
    assert len(entries) == 1


def test_an_added_old_game_is_held():
    old = [game("1957-11-16", 37, 6)]
    new = [game("1950-10-14", 7, 0), game("1957-11-16", 37, 6)]
    games, entries, _, _ = settle(old, new)
    assert games == old
    assert [(e["kind"], e["old"], e["new"]["date"]) for e in entries] == [("added", None, "1950-10-14")]


def test_a_removed_old_game_is_held_and_kept_in_place():
    old = [game("1950-10-14", 7, 0), game("1957-11-16", 37, 6), game("2025-11-15", 41, 20)]
    new = [game("1950-10-14", 7, 0), game("2025-11-15", 41, 20)]
    games, entries, _, _ = settle(old, new)
    assert games == old
    assert [(e["kind"], e["new"]) for e in entries] == [("removed", None)]


def test_an_edited_date_site_note_or_result_is_held_too():
    old = [game("1957-11-16", 37, 6)]
    for change in ({"date": "1957-11-17"}, {"site": "Muncie, Ind."}, {"note": "(OT)"}, {"result": "L"}):
        _, entries, _, _ = settle(old, [{**old[0], **change}])
        assert [e["kind"] for e in entries] == ["edited"], change


def test_whitespace_alone_is_not_a_change():
    old = [game("1957-11-16", 37, 6)]
    assert settle(old, [{**old[0], "site": " Greencastle,   Ind. "}])[1] == []


def test_approving_applies_only_what_still_matches_pending():
    old = [game("1957-11-16", 37, 6), game("1958-11-15", 24, 8)]
    new = [game("1957-11-16", 37, 7), game("1958-11-15", 24, 9)]
    _, first, _, _ = settle(old, new)
    approved = [first[0]]                                    # the 1957 entry is approved, the 1958 one is not
    games, entries, notes, _ = settle(old, new, pending=approved, apply=True)
    assert [g["wabash"] for g in games] == [7, 8]
    assert [e["new"]["date"] for e in entries] == ["1958-11-15"] and any("applied" in n for n in notes)
    # A page that changed again after the entry was recorded no longer matches, so it is held afresh.
    newer = [game("1957-11-16", 37, 8), game("1958-11-15", 24, 8)]
    games, entries, _, _ = settle(old, newer, pending=approved, apply=True)
    assert games == old and len(entries) == 1 and entries[0]["id"] != approved[0]["id"]


def test_a_keep_previous_ruling_ignores_the_change_and_raises_nothing():
    old = [game("1957-11-16", 37, 6)]
    new = [game("1957-11-16", 37, 7)]
    rule = {"school": "depauw", "old": {"date": "1957-11-16", "score": "37-6"},
            "new": {"date": "1957-11-16", "score": "37-7"}, "reason": "checked the box score"}
    games, entries, notes, used = settle(old, new, rules=[rule])
    assert games == old and entries == [] and used == [rule] and "keep_previous" in notes[0]
    other = {**rule, "school": "wabash"}
    assert settle(old, new, rules=[other])[1] != []          # a ruling is for one school


def test_a_change_to_a_row_a_ruling_names_is_flagged():
    old = [game("1957-11-16", 37, 6)]
    rules = {"same_game": [{"depauw": {"date": "1957-11-16", "score": (37, 6)},
                            "wabash": {"date": "1957-11-17", "score": (37, 6)}, "reason": ""}],
             "different_games": []}
    [e] = settle(old, [game("1957-11-16", 37, 7)], sport_rules=rules)[1]
    assert e["touches_ruling"] is True
    assert "ruling" in review.render_body([e]).lower()


# ---- the whole scraper -------------------------------------------------------------------------- #

def edit_score(page_dir, date, old, new):
    p = page_dir / "football.html"
    rows = p.read_text(encoding="utf-8").split("</tr>")
    hits = [i for i, r in enumerate(rows) if f">{date}<" in r]
    assert len(hits) == 1
    assert old in rows[hits[0]]
    rows[hits[0]] = rows[hits[0]].replace(old, new)
    p.write_text("</tr>".join(rows), encoding="utf-8")


def run(pages, tmp_path, *extra):
    return scrape.main(["--fixtures", str(pages), "--output", str(tmp_path / "series.json"),
                        "--upcoming-output", str(tmp_path / "upcoming.json"), *extra])


def pending_of(tmp_path):
    return json.loads((tmp_path / "pending-changes.json").read_text(encoding="utf-8"))["changes"]


def football(tmp_path, name="series.json"):
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))["sports"]["football"]


def test_a_fixture_run_never_writes_into_the_real_data_folder(both_dir, tmp_path):
    before = {p.name: p.read_bytes() for p in (ROOT / "data").iterdir()}
    assert run(both_dir, tmp_path) == 0
    assert {p.name: p.read_bytes() for p in (ROOT / "data").iterdir()} == before
    assert pending_of(tmp_path) == []


def test_an_edited_1950s_score_is_held_end_to_end(both_dir, tmp_path):
    assert run(both_dir, tmp_path) == 0
    base = (tmp_path / "series.json").read_text(encoding="utf-8")
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    assert run(both_dir, tmp_path) == 0                       # the page still matches its own summary
    [e] = pending_of(tmp_path)
    assert (e["school"], e["sport"], e["kind"]) == ("depauw", "football", "edited")
    assert (e["old"]["wabash"], e["new"]["wabash"]) == (6, 7)
    assert (tmp_path / "series.json").read_text(encoding="utf-8") == base      # the page still shows the old score
    saved = json.loads((tmp_path / "depauw.json").read_text(encoding="utf-8"))["sports"]["football"]
    assert [g["wabash"] for g in saved["games"] if g["date"] == "1957-11-16"] == [6]
    body = review.render_body([e])
    assert "1957-11-16" in body and "DePauw 37-6" in body and "DePauw 37-7" in body and e["source_url"] in body


def test_approving_applies_the_change_and_clears_pending(both_dir, tmp_path):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    run(both_dir, tmp_path)
    assert len(pending_of(tmp_path)) == 1
    assert run(both_dir, tmp_path, "--apply-reviewed") == 0
    assert pending_of(tmp_path) == []
    saved = json.loads((tmp_path / "depauw.json").read_text(encoding="utf-8"))["sports"]["football"]
    assert [g["wabash"] for g in saved["games"] if g["date"] == "1957-11-16"] == [7]
    merged = football(tmp_path)
    assert merged["sources"]["disputed"] >= 1 or merged["points"]["wabash"]       # the merge saw the new score


def test_apply_with_nothing_pending_changes_nothing_new(both_dir, tmp_path):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    # Approving only accepts what was already pending: a first sighting is held, never applied.
    assert run(both_dir, tmp_path, "--apply-reviewed") == 0
    assert len(pending_of(tmp_path)) == 1


def test_a_current_season_edit_is_not_held(both_dir, tmp_path):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/15/2025", " W 41 - 20 ", " W 41 - 21 ")
    assert run(both_dir, tmp_path) == 0
    assert pending_of(tmp_path) == []
    saved = json.loads((tmp_path / "depauw.json").read_text(encoding="utf-8"))["sports"]["football"]
    assert [g["wabash"] for g in saved["games"] if g["date"] == "2025-11-15"] == [21]


def test_a_keep_previous_ruling_stops_the_change_being_raised(both_dir, tmp_path, capsys):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    (tmp_path / "overrides.json").write_text(json.dumps({"schema_version": 1, "sports": {"football": {
        "keep_previous": [{"school": "depauw", "old": {"date": "1957-11-16", "score": "37-6"},
                           "new": {"date": "1957-11-16", "score": "37-7"}, "reason": "box score says 37-6"}]}}}),
        encoding="utf-8")
    capsys.readouterr()
    assert run(both_dir, tmp_path) == 0
    assert pending_of(tmp_path) == []
    assert "HOLD" not in capsys.readouterr().err
    saved = json.loads((tmp_path / "depauw.json").read_text(encoding="utf-8"))["sports"]["football"]
    assert [g["wabash"] for g in saved["games"] if g["date"] == "1957-11-16"] == [6]


def test_a_run_with_nothing_new_leaves_pending_untouched(both_dir, tmp_path):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    run(both_dir, tmp_path)
    path = tmp_path / "pending-changes.json"
    first, stamp = path.read_text(encoding="utf-8"), path.stat().st_mtime_ns
    assert run(both_dir, tmp_path) == 0
    assert (path.read_text(encoding="utf-8"), path.stat().st_mtime_ns) == (first, stamp)


def test_a_page_that_fails_keeps_its_pending_entries(both_dir, tmp_path):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    run(both_dir, tmp_path)
    held = pending_of(tmp_path)
    (both_dir / "football.html").write_text("<html>not a history page</html>", encoding="utf-8")
    assert run(both_dir, tmp_path, "--apply-reviewed") == 1
    assert pending_of(tmp_path) == held


def test_a_dry_run_writes_nothing(both_dir, tmp_path):
    run(both_dir, tmp_path)
    edit_score(both_dir, "11/16/1957", " W 37 - 6 ", " W 37 - 7 ")
    assert run(both_dir, tmp_path, "--dry-run") == 0
    assert pending_of(tmp_path) == []


# ---- the rulings file --------------------------------------------------------------------------- #

def test_keep_previous_is_validated(tmp_path):
    p = tmp_path / "overrides.json"
    p.write_text(json.dumps({"sports": {"football": {"keep_previous": [{"school": "nobody"}]}}}), encoding="utf-8")
    with pytest.raises(merge.MergeError, match="keep_previous"):
        review.load_keep_previous(p)
    p.write_text(json.dumps({"sports": {"football": {"keep_previous": [
        {"school": "wabash", "old": None, "new": {"date": "1950-10-14", "score": "7-0"}}]}}}), encoding="utf-8")
    assert merge.load_overrides(p)["football"]["same_game"] == []      # the merge ignores it
    assert review.load_keep_previous(p)["football"][0]["old"] is None


def test_the_committed_files_are_valid():
    assert review.load_pending(ROOT / "data" / "pending-changes.json") == []
    review.load_keep_previous(ROOT / "data" / "overrides.json")


# ---- the issue ---------------------------------------------------------------------------------- #

def entries(n, sport="football"):
    out = []
    for i in range(n):
        old = game(f"19{10 + i % 80}-10-{1 + i % 28:02d}", 7, 0)
        out.append(review.entry("depauw", sport, {"kind": "edited", "old": old, "new": {**old, "wabash": 1}},
                                "https://x/y", "2026-10-29T01:00:00+00:00", False))
    return out


def test_the_issue_body_is_capped_and_always_fits():
    body = review.render_body(entries(900) + entries(900, "baseball"))
    assert len(body) < 65536 and "more, see `data/pending-changes.json`" in body
    small = review.render_body(entries(3))
    assert "more, see" not in small and small.count("- **DePauw, edited**") == 3


def test_the_issue_body_tells_how_to_approve_and_reject():
    body = review.render_body(entries(1))
    assert "Apply the changes to old games waiting for review" in body and "keep_previous" in body
    workflow = (ROOT / ".github" / "workflows" / "update-and-deploy.yml").read_text(encoding="utf-8")
    assert "apply_reviewed_changes:" in workflow
    assert re.search(r'description: "Apply the changes to old games waiting for review', workflow)


class FakeGh:
    def __init__(self, issues=(), labels=()):
        self.issues, self.labels, self.calls = list(issues), list(labels), []

    def __call__(self, *args, stdin=None):
        self.calls.append((args, stdin))
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        if args[:2] == ("label", "list"):
            return json.dumps([{"name": n} for n in self.labels])
        return ""

    def verbs(self):
        return [" ".join(a[:2]) for a, _ in self.calls]


def test_the_first_sync_creates_the_label_and_one_issue():
    gh = FakeGh()
    assert review_issue.sync(entries(2), False, "", run=gh) == "opened a new issue"
    assert gh.verbs() == ["issue list", "label list", "label create", "issue create"]
    assert "--label" in gh.calls[-1][0] and "data-review" in gh.calls[-1][0]


def test_a_later_sync_edits_the_same_issue_only_when_the_text_changed():
    pend = entries(2)
    body = review.render_body(pend)
    same = FakeGh(issues=[{"number": 7, "body": body}])
    assert "up to date" in review_issue.sync(pend, False, "", run=same)
    assert same.verbs() == ["issue list"]                              # nothing written
    changed = FakeGh(issues=[{"number": 9, "body": "x"}, {"number": 7, "body": "old text"}])
    assert review_issue.sync(pend, False, "", run=changed) == "updated #7"      # the oldest open issue
    assert changed.verbs() == ["issue list", "issue edit"]


def test_an_approved_sync_comments_and_closes():
    gh = FakeGh(issues=[{"number": 7, "body": "x"}])
    assert review_issue.sync([], True, "https://run", run=gh) == "closed #7"
    assert gh.verbs() == ["issue list", "issue comment", "issue close"]
    assert "applied" in gh.calls[1][1] and "https://run" in gh.calls[1][1]
    quiet = FakeGh()
    assert review_issue.sync([], False, "", run=quiet) == "nothing pending and no open issue"
    assert quiet.verbs() == ["issue list"]


def test_only_the_issue_job_may_write_issues():
    workflow = (ROOT / ".github" / "workflows" / "update-and-deploy.yml").read_text(encoding="utf-8")
    assert len(re.findall(r"^\s+issues: write$", workflow, re.M)) == 1
    job = workflow.split("  issues:\n")[1].split("\n  report:")[0]
    assert "issues: write" in job and "group: review-issue" in job and "needs: build" in job
