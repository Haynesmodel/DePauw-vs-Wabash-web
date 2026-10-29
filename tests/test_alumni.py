"""Curated alumni validation, count derivation, and generated-page integration."""
import copy
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))
import alumni  # noqa: E402
import render  # noqa: E402


def read_data():
    return alumni.load_json(ROOT / "data" / "alumni.json", "alumni")


def read_endowment():
    return alumni.load_json(ROOT / "data" / "endowment.json", "endowment")


def test_committed_records_cover_ten_categories_and_derive_counts():
    data = alumni.validate_alumni(read_data())
    assert len(data["categories"]) == 10
    assert all(set(category["review"]) == {"depauw", "wabash"} for category in data["categories"])
    assert alumni.counts(data)["academy-awards"] == {"depauw": 1, "wabash": 0}
    assert alumni.counts(data)["pulitzer"] == {"depauw": 3, "wabash": 1}
    assert alumni.counts(data)["rhodes-scholars"] == {"depauw": 3, "wabash": 9}
    assert alumni.counts(data)["representatives"] == {"depauw": 19, "wabash": 11}
    assert alumni.counts(data)["fortune-500-ceos"] == {"depauw": 8, "wabash": 3}
    assert "james-keyes" not in {person["id"] for person in data["people"]}
    assert all(alumni.counts(data)[c["id"]]["depauw"] + alumni.counts(data)[c["id"]]["wabash"]
               for c in alumni.visible_categories(data))


def test_rhodes_scholar_dates_match_official_records():
    people = {person["id"]: person for person in alumni.validate_alumni(read_data())["people"]}
    pifer = people["claude-pifer"]["qualifications"]["rhodes-scholars"]
    osborne = people["insley-osborne"]["qualifications"]["rhodes-scholars"]
    assert pifer["years"] == [1908]
    assert pifer["source"]["url"] == "https://www.rhodeshouse.ox.ac.uk/umbraco/api/ScholarApi/Scholars?lastname=Pifer"
    assert osborne["years"] == [1911]
    assert osborne["source"]["url"] == "https://www.rhodeshouse.ox.ac.uk/umbraco/api/ScholarApi/Scholars?lastname=Osborne"


def test_membership_can_span_categories_but_cannot_repeat():
    data = read_data()
    multi = next(person for person in data["people"] if person["id"] == "dan-quayle")
    assert {"vice-presidents", "senators", "representatives"} <= set(multi["categories"])
    broken = copy.deepcopy(data)
    broken["people"][0]["categories"].append(broken["people"][0]["categories"][0])
    with pytest.raises(alumni.AlumniError, match="duplicate category membership"):
        alumni.validate_alumni(broken)


def test_zero_zero_categories_are_hidden_but_one_sided_zero_is_kept():
    data = {
        "categories": [
            {"id": "one-sided"},
            {"id": "empty"},
            {"id": "both"},
        ],
        "people": [
            {"id": "graduate", "school": "depauw", "categories": ["one-sided", "both"]},
        ],
    }
    assert alumni.counts(data) == {
        "one-sided": {"depauw": 1, "wabash": 0},
        "empty": {"depauw": 0, "wabash": 0},
        "both": {"depauw": 1, "wabash": 0},
    }
    assert [category["id"] for category in alumni.visible_categories(data)] == ["one-sided", "both"]


@pytest.mark.parametrize("mutation, message", [
    (lambda x: x.update(schema_version=2), "schema_version 1"),
    (lambda x: x["people"][0].update(school="other"), "invalid school"),
    (lambda x: x["people"][0]["school_source"].update(url="javascript:alert(1)"), r"HTTP\(S\) URL"),
    (lambda x: x["people"][0]["qualifications"].clear(), "qualifications must document"),
])
def test_invalid_curated_data_is_rejected(mutation, message):
    data = read_data()
    mutation(data)
    with pytest.raises(alumni.AlumniError, match=message):
        alumni.validate_alumni(data)


@pytest.mark.parametrize("mutation, message", [
    (lambda x: x.update(as_of="2025-13-40"), "ISO date"),
    (lambda x: x.update(as_of="20250630"), "ISO date"),
    (lambda x: x["schools"]["wabash"].update(amount_usd=True), "non-negative integer"),
    (lambda x: x["schools"].pop("depauw"), "exactly depauw and wabash"),
    (lambda x: x["schools"]["depauw"].update(source_url="file:///tmp/a"), r"HTTP\(S\) URL"),
    (lambda x: x.update(as_of="2024-06-30"), "match the fiscal-year end date"),
])
def test_invalid_endowment_data_is_rejected(mutation, message):
    data = read_endowment()
    mutation(data)
    with pytest.raises(alumni.AlumniError, match=message):
        alumni.validate_endowment(data)


def test_failed_curated_input_preserves_existing_output(tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    sentinel = out / "keep.txt"
    sentinel.write_text("old site", encoding="utf-8")
    invalid = tmp_path / "alumni.json"
    invalid.write_text('{"schema_version": 99}', encoding="utf-8")
    with pytest.raises(alumni.AlumniError, match="schema_version 1"):
        render.build(render.DATA, out, alumni_path=invalid)
    assert sentinel.read_text(encoding="utf-8") == "old site"


def test_compact_verification_date_is_rejected_before_output_replacement(tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    sentinel = out / "keep.txt"
    sentinel.write_text("old site", encoding="utf-8")
    invalid = copy.deepcopy(read_data())
    invalid["verified_at"] = "20261029"
    path = tmp_path / "alumni.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(alumni.AlumniError, match=r"ISO date \(YYYY-MM-DD\)"):
        render.build(render.DATA, out, alumni_path=path)
    assert sentinel.read_text(encoding="utf-8") == "old site"


@pytest.mark.parametrize("years, rank_year, message", [
    ([1990, 1995, 2000, 2005], 1997, "ranking year must overlap"),
    ([1995, 1990], 1996, "ordered, non-overlapping ranges"),
])
def test_fortune_rank_year_must_fall_in_an_ordered_ceo_interval(years, rank_year, message):
    data = read_data()
    rales = next(person for person in data["people"] if person["id"] == "steven-rales")
    qualification = rales["qualifications"]["fortune-500-ceos"]
    qualification["years"] = years
    qualification["rank_year"] = rank_year
    with pytest.raises(alumni.AlumniError, match=message):
        alumni.validate_alumni(data)


def test_build_emits_navigation_alumni_and_auditable_json(tmp_path):
    out = tmp_path / "site"
    render.build(render.DATA, out, now=dt.datetime(2026, 10, 29, tzinfo=dt.timezone.utc))
    page = (out / "alumni" / "index.html").read_text(encoding="utf-8")
    home = (out / "index.html").read_text(encoding="utf-8")
    how = (out / "how-it-works" / "index.html").read_text(encoding="utf-8")
    missing = (out / "404.html").read_text(encoding="utf-8")
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert 'aria-current="page">Alumni</a>' in page
    assert 'aria-current="page">Athletics</a>' in home
    assert 'href="./" aria-current="page">Athletics</a>' in home
    assert 'aria-current="page"' not in how and 'aria-current="page"' not in missing
    assert 'rel="canonical" href="https://depauwvswabash.com/alumni/"' in page
    assert 'property="og:url" content="https://depauwvswabash.com/alumni/"' in page
    assert "Steven Rales" in page and "The Wonderful Story of Henry Sugar" in page
    assert "Byron Price" in page and "special citation" in page
    assert "Robert Montgomery Stephenson" in page
    assert "1982, 1984" in page
    assert "Joseph Walker Barr" in page and "John Lockwood Wilson" in page
    assert "Luke Messer" in page
    assert "Albert J. Beveridge" in page and "The Life of John Marshall" in page
    assert 'id="endowment"' in page and "$1,041,801,089" in page and "$442,957,416" in page
    assert "reported accounting scopes differ" in page
    assert page.count(">Source</a>") == 2
    assert "FY2025" in page and "2025-06-30" in page
    assert "<script" not in page
    assert "Fortune 500 2008" in page and "#340" in page
    assert "https://depauwvswabash.com/alumni/" in sitemap
    assert "© 2026 Jackson Mote" in page
    assert page.count("<!DOCTYPE html>") == 1
    for name in ("alumni.json", "endowment.json"):
        assert (out / "data" / name).is_file()


def test_render_escapes_curated_text_and_source_attributes():
    data = alumni.validate_alumni(read_data())
    evil = copy.deepcopy(data)
    evil["people"][0]["name"] = '<img src=x onerror="alert(1)">'
    page = alumni.render_page(alumni.validate_alumni(evil), alumni.validate_endowment(read_endowment()),
                              head_html="<head><title>Test</title></head>")
    assert "<img" not in page
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in page
