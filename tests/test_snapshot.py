"""Data snapshots: release files and notes, the unchanged check, tags and best-effort archiving."""

import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import snapshot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "snapshot.yml").read_text(encoding="utf-8")
SERIES = json.loads((ROOT / "data" / "series.json").read_text(encoding="utf-8"))
DAY = dt.date(2027, 1, 2)


def quiet(*a, **k):
    pass


def fake_gh(releases=(), bodies=None):
    def run(*args):
        if args[:2] == ("release", "list"):
            return json.dumps([{"tagName": t} for t in releases])
        if args[:2] == ("release", "view"):
            return json.dumps({"body": (bodies or {})[args[2]]})
        raise AssertionError(args)
    return run


def data_copy(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(ROOT / "data", d)
    return d


def test_the_notes_list_the_totals_and_every_sports_record():
    t = SERIES["totals"]
    notes = snapshot.release_notes(SERIES, ["https://web.archive.org/web/2027/https://a"], [], "abc123", DAY)
    assert f"DePauw {t['depauw_wins']}, Wabash {t['wabash_wins']}, {t['ties']} ties, {t['games_played']} games" in notes
    for s in SERIES["sports"].values():
        r = s["record"]
        assert f"- {s['name']}: DePauw {r['depauw_wins']}, Wabash {r['wabash_wins']}, {r['ties']} ties" in notes
    assert "Tennis: " in notes and "matches)" in notes                       # tennis counts matches
    assert "- https://web.archive.org/web/2027/https://a" in notes
    assert snapshot.recorded_hash(notes) == "abc123"


def test_the_notes_say_when_the_archive_saved_nothing():
    notes = snapshot.release_notes(SERIES, [], ["https://x/1"], "abc", DAY)
    assert "saved none" in notes and "Not saved (1): https://x/1" in notes


def test_the_source_urls_are_the_six_history_pages_of_each_school():
    cfg = json.loads((ROOT / "scraper" / "sources.json").read_text(encoding="utf-8"))
    urls = snapshot.source_urls(cfg)
    assert len(urls) == 12 and len(set(urls)) == 12
    assert sum("depauwtigers.com" in u for u in urls) == 6 and sum("sports.wabash.edu" in u for u in urls) == 6
    assert all("opponent-history" in u for u in urls)


def test_the_tag_is_the_date_and_only_gains_a_suffix_when_taken():
    assert snapshot.pick_tag(DAY, set()) == "data-2027-01-02"
    assert snapshot.pick_tag(DAY, {"data-2027-01-02"}) == "data-2027-01-02-2"
    assert snapshot.pick_tag(DAY, {"data-2027-01-02", "data-2027-01-02-2"}) == "data-2027-01-02-3"


def test_a_first_snapshot_counts_as_a_change():
    assert snapshot.changed_since_last_release(fake_gh([]))[0] is True
    assert snapshot.changed_since_last_release(fake_gh(["v1.0"]))[0] is True       # only data-* releases count


def test_unchanged_data_is_skipped_and_changed_data_is_not(tmp_path):
    d = data_copy(tmp_path)
    body = snapshot.release_notes(SERIES, [], [], snapshot.data_hash(d), DAY)
    run = fake_gh(["data-2026-07-01", "data-2027-01-02"], {"data-2027-01-02": body})
    assert snapshot.changed_since_last_release(run, d)[0] is False
    (d / "wabash.json").write_text((d / "wabash.json").read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert snapshot.changed_since_last_release(run, d)[0] is True


def test_the_schedule_file_does_not_count_as_a_change(tmp_path):
    d = data_copy(tmp_path)
    before = snapshot.data_hash(d)
    (d / "upcoming.json").write_text("{}", encoding="utf-8")
    assert snapshot.data_hash(d) == before


def test_archiving_collects_links_and_survives_failures():
    calls = []

    class Resp:
        def __init__(self, link):
            self.headers = {"Content-Location": link}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def geturl(self):
            return "https://web.archive.org/save/x"

    def opener(req, timeout):
        calls.append((req.full_url, timeout))
        if req.full_url.endswith("/bad"):
            raise OSError("429 Too Many Requests")
        return Resp("/web/20270102030405/" + req.full_url.removeprefix(snapshot.SAVE_URL))

    pauses = []
    links, failed = snapshot.wayback_save(["https://a/1", "https://a/bad", "https://a/3"], opener=opener,
                                          sleep=pauses.append, log=quiet)
    assert links == ["https://web.archive.org/web/20270102030405/https://a/1",
                     "https://web.archive.org/web/20270102030405/https://a/3"]
    assert failed == ["https://a/bad"] and len(calls) == 3 and pauses == [snapshot.SAVE_PAUSE] * 2
    assert all(t == snapshot.SAVE_TIMEOUT for _, t in calls)


def test_building_writes_every_file_and_the_notes(tmp_path):
    out = tmp_path / "release"
    tag = snapshot.build(out, run=fake_gh(["data-2027-01-02"]), data_dir=ROOT / "data",
                         saver=lambda urls: (["https://web.archive.org/web/1/x"], []), today=DAY)
    assert tag == "data-2027-01-02-2" and (out / "TAG").read_text(encoding="utf-8").strip() == tag
    for name in ("series.json", "depauw.json", "wabash.json", "overrides.json", "upcoming.json", "games.csv", "NOTES.md"):
        assert (out / name).stat().st_size > 0, name
    rows = (out / "games.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == SERIES["totals"]["games_played"] + 1                    # fresh, one row per game
    assert snapshot.recorded_hash((out / "NOTES.md").read_text(encoding="utf-8")) == snapshot.data_hash(ROOT / "data")


def test_the_workflow_is_scheduled_twice_a_year_and_pinned():
    assert 'cron: "23 14 1 7 *"' in WORKFLOW and 'cron: "41 15 2 1 *"' in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    for line in re.findall(r"uses: (\S+)", WORKFLOW):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", line), line
    assert all(re.search(r"uses: \S+@[0-9a-f]{40} # v\d", l) for l in WORKFLOW.splitlines() if "uses:" in l)


def test_only_the_release_job_can_write():
    assert len(re.findall(r"^\s+contents: write$", WORKFLOW, re.M)) == 1
    release = WORKFLOW.split("\n  release:\n")[1]
    assert "contents: write" in release and "contents: write" not in WORKFLOW.split("\n  release:\n")[0]
    assert re.search(r"^permissions:\n  contents: read", WORKFLOW, re.M)
