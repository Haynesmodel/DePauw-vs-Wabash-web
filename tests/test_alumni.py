"""Curated alumni validation, count derivation, and generated-page integration."""
import copy
import html
import re
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
    assert page.count(">Endowment source</a>") == 2 and page.count(">Enrollment source</a>") == 2
    assert "FY2025" in page and "Jun 30, 2025" in page
    assert "<script" not in page
    assert "ranked #340 in the 2008 Fortune 500" in page
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


def visible_text(page):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def committed_page():
    return alumni.render_page(alumni.validate_alumni(read_data()), alumni.validate_endowment(read_endowment()),
                              head_html="<head><title>Test</title></head>")


def test_no_iso_date_shows_in_visible_text_and_dates_match_the_athletics_style():
    text = visible_text(committed_page())
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text)
    assert "Verified Oct 29, 2026" in text and "as of Jun 30, 2025" in text
    for iso in ("2025-06-30", "2026-10-29", "2026-01-05", "1999-12-31"):
        assert alumni.fmt_date(iso) == render.fmt_date(iso)


@pytest.mark.parametrize("amount, expected", [
    (1_041_801_089, ("$1.04", "billion")), (442_957_416, ("$443", "million")),
    (1_005_000_000, ("$1.01", "billion")), (999_500_000, ("$1,000", "million")),
    (442_500_000, ("$443", "million")), (442_499_999, ("$442", "million")), (950_000, ("$950,000", "")),
])
def test_compact_endowment_rounds_half_up_from_the_exact_amount(amount, expected):
    assert alumni.compact_usd(amount) == expected


def test_endowment_card_leads_with_per_student_and_supports_it_with_total_and_enrollment():
    page = committed_page()
    text = visible_text(page)
    assert '<p class="tile-num money">$543,000</p><p class="tile-label">endowment per student</p>' in page
    assert '<p class="tile-num money">$511,000</p>' in page
    assert "Endowment: $1.04 billion ($1,041,801,089)" in text
    assert "Endowment: $443 million ($442,957,416)" in text
    assert "Enrollment: 1,917 students, fall 2024" in text and "Enrollment: 866 students, fall 2024" in text
    assert 'href="https://nces.ed.gov/collegenavigator/?id=150400"' in page
    assert 'href="https://nces.ed.gov/collegenavigator/?id=152673"' in page


def test_per_student_is_computed_from_exact_amounts_and_rounded_half_up_to_the_thousand():
    assert alumni.per_student(read_endowment()) == {"depauw": 543000, "wabash": 511000}   # 543,453.9 and 511,498.2
    # rounding from the compact "$443 million" would give 512,000; the exact amount must be used
    assert round(443_000_000 / 866, -3) == 512000
    def one(amount, students):
        data = copy.deepcopy(read_endowment())
        data["schools"]["depauw"]["amount_usd"] = amount
        data["schools"]["depauw"]["enrollment"]["count"] = students
        return alumni.per_student(data)["depauw"]
    assert one(1_500_000, 3) == 500000
    assert one(1_499_999, 1) == 1_500_000 and one(1_500_000, 1) == 1_500_000
    assert one(1_250_000, 2) == 625000
    assert one(2_500, 1) == 3000 and one(2_499, 1) == 2000 and one(500, 1) == 1000 and one(499, 1) == 0


def test_per_student_is_never_stored_in_the_data():
    assert "per_student" not in json.dumps(read_endowment()) and "per student" not in json.dumps(read_endowment())


@pytest.mark.parametrize("mutation, message", [
    (lambda x: x["schools"]["depauw"].pop("enrollment"), "enrollment must be an object"),
    (lambda x: x["schools"]["depauw"]["enrollment"].update(count=0), "positive integer"),
    (lambda x: x["schools"]["wabash"]["enrollment"].update(count=True), "positive integer"),
    (lambda x: x["schools"]["wabash"]["enrollment"].update(count=866.5), "positive integer"),
    (lambda x: x["schools"]["wabash"]["enrollment"].update(term="Fall 2023"), "must be Fall 2024"),
    (lambda x: x["schools"]["wabash"]["enrollment"].update(source_url="ftp://nces.ed.gov/x"), r"HTTP\(S\) URL"),
    (lambda x: x["schools"]["depauw"]["enrollment"].update(source_label=" "), "source_label"),
    (lambda x: x["schools"]["depauw"]["enrollment"].update(verified_at="10/29/2026"), "ISO date"),
])
def test_invalid_enrollment_data_is_rejected(mutation, message):
    data = read_endowment()
    mutation(data)
    with pytest.raises(alumni.AlumniError, match=message):
        alumni.validate_endowment(data)


def test_enrollment_term_follows_the_fiscal_year():
    data = read_endowment()
    data["fiscal_year"], data["as_of"] = "FY2026", "2026-06-30"
    with pytest.raises(alumni.AlumniError, match="must be Fall 2025"):
        alumni.validate_endowment(data)
    for item in data["schools"].values():
        item["enrollment"]["term"] = "Fall 2025"
    assert alumni.validate_endowment(data)


def test_the_scope_caveat_and_enrollment_basis_show_wherever_per_student_figures_show():
    text = visible_text(committed_page())
    assert "$543,000" in text
    assert "pledges receivable and perpetual trusts" in text and "pooled endowment net assets" in text
    assert "not cash available for general spending" in text
    assert "fall 2024 total undergraduate headcount" in text and "College Navigator (IPEDS)" in text


def test_degree_labels_say_what_is_recorded_and_never_the_vague_graduate():
    people = {p["id"]: p for p in read_data()["people"]}
    assert alumni.degree_label({"degree": "B.A.", "degree_year": 1969}) == "B.A., 1969"
    assert alumni.degree_label({"degree": "Graduate", "degree_year": 1885}) == "Class of 1885"
    assert alumni.degree_label({"degree": "Law department graduate", "degree_year": 1866}) == "Law department graduate, 1866"
    assert alumni.degree_label(people["mike-braun"]) == "Class of 1976"
    demotte = next(p for p in people.values() if p["degree"].startswith("Literary department"))
    assert alumni.degree_label(demotte) == demotte["degree"]          # already names its years
    page = committed_page()
    assert "Graduate (" not in page and "Class of 1976" in page and "B.A., 1955" in page


def test_open_terms_read_present_and_only_braun_has_one():
    data = read_data()
    open_terms = [(p["id"], c) for p in data["people"] for c, q in p["qualifications"].items() if q.get("present")]
    assert open_terms == [("mike-braun", "governors")]
    page = committed_page()
    assert "Governor of Indiana (2025–present)" in page and "U.S. senator from Indiana (2019–2025)" in page
    assert alumni._format_years([2025], True) == "2025–present"
    assert alumni._format_years([1981, 1989, 1993, 2001], True) == "1981–1989, 1993–present"
    assert alumni._format_years([1989, 1993]) == "1989–1993"


def test_present_must_be_a_boolean_on_a_start_year_or_ranges():
    data = read_data()
    braun = next(p for p in data["people"] if p["id"] == "mike-braun")
    braun["qualifications"]["governors"]["present"] = "yes"
    with pytest.raises(alumni.AlumniError, match="present must be true or false"):
        alumni.validate_alumni(data)


def test_fortune_entries_show_the_ranking_year_as_a_ranking_not_a_tenure():
    page = committed_page()
    assert "CEO of Lincoln National Corporation · ranked #199 in the 1996 Fortune 500" in page
    assert "Lincoln National Corporation (1996)" not in page


def test_name_lists_stack_below_600px_while_the_count_tiles_stay_side_by_side():
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.alumni-schools \{[^}]*grid-template-columns: minmax\(0, 1fr\);", css)
    assert re.search(r"@media \(min-width: 37\.5rem\) \{\s*\.alumni-schools \{ grid-template-columns: repeat\(2", css)
    page = committed_page()
    assert page.count('<div class="alumni-schools">') == len(alumni.visible_categories(read_data()))
    assert "money { overflow-wrap" not in css and "white-space: nowrap" in css


def test_header_subtitle_and_page_heading_match_the_athletics_page_structure():
    page = committed_page()
    assert '<p class="subtitle">Notable graduates and endowments, side by side, with a source for every name.</p>' in page
    assert "Verified named graduates and endowment comparison" not in page
    main = page[page.index("<main"):]
    assert main.index('<h2 id="alumni-h">Alumni and endowment</h2>') < main.index('class="scoreboard"')
    assert 'class="category-nav"' not in page and "Alumni categories" not in page


def scoreboard_table(page):
    return page[page.index('<table class="scoreboard">'):page.index("</table>")]


def test_scoreboard_is_a_real_table_with_one_linked_row_per_card_and_endowment_first():
    page = committed_page()
    table = scoreboard_table(page)
    ids = re.findall(r'<tr><th scope="row"><a href="#([^"]+)">', table)
    cards = re.findall(r'<section class="sport alumni-card" id="([^"]+)"', page)
    assert ids[0] == "endowment" and ids[1:] == cards and len(cards) == 10
    for target in ids:
        assert f'id="{target}"' in page
    assert "<caption>" in table and table.count('scope="col"') == 3 and table.count('scope="row"') == 11
    first = re.findall(r"<tr>.*?</tr>", table)[1]
    assert "$543,000" in first and "$511,000" in first


def test_scoreboard_marks_the_larger_count_in_its_school_accent_and_leaves_ties_plain():
    table = scoreboard_table(committed_page())
    senators = re.search(r'<tr><th scope="row"><a href="#senators">.*?</tr>', table).group(0)
    assert 'class="score lead lead-depauw"><strong>8</strong><span class="sr-only"> (higher)</span>' in senators
    assert '<td class="score">3</td>' in senators
    rhodes = re.search(r'<tr><th scope="row"><a href="#rhodes-scholars">.*?</tr>', table).group(0)
    assert 'lead lead-wabash"><strong>9</strong>' in rhodes
    endow = re.search(r'<tr><th scope="row"><a href="#endowment">.*?</tr>', table).group(0)
    assert 'lead-depauw"><strong>$543,000' in endow
    tie = read_data()
    murad = next(p for p in tie["people"] if p["id"] == "ferid-murad")
    tie["people"].append(dict(copy.deepcopy(murad), id="ferid-murad-2", school="wabash"))
    tied = alumni.render_page(alumni.validate_alumni(tie), alumni.validate_endowment(read_endowment()),
                              head_html="<head></head>")
    row = re.search(r'<tr><th scope="row"><a href="#nobel">.*?</tr>', scoreboard_table(tied)).group(0)
    assert "lead" not in row and row.count('<td class="score">1</td>') == 2


def test_no_overall_alumni_score_or_leads_line_appears():
    text = visible_text(committed_page())
    assert "There is no overall alumni score." in text
    assert not re.search(r"leads in \d+|overall (winner|leader|total)|total graduates|categories led", text, re.I)
    assert "All head-to-head" not in text


def test_count_tiles_use_the_athletics_tile_with_a_plural_aware_label():
    page = committed_page()
    assert ('<div class="tile tile-depauw"><span class="tile-name">DePauw</span><span class="tile-num">8</span>'
            '<span class="tile-label">senators</span></div>') in page
    assert '<span class="tile-num">1</span><span class="tile-label">Nobel laureate</span>' in page
    assert '<span class="tile-num">0</span><span class="tile-label">Nobel laureates</span>' in page
    zeros = sum(1 for c in alumni.counts(read_data()).values() for n in c.values() if n == 0)
    assert zeros == 3 and page.count("No qualifying graduates found in the reviewed sources.") == zeros
    assert "DePauw (" not in page and "Wabash (" not in page
    assert set(alumni.TILE_LABELS) == {c["id"] for c in read_data()["categories"]}


def test_a_category_without_a_tile_label_is_rejected_loudly():
    data = read_data()
    data["categories"][0]["id"] = "new-thing"
    for person in data["people"]:
        person["categories"] = ["new-thing" if c == "nobel" else c for c in person["categories"]]
        person["qualifications"] = {("new-thing" if c == "nobel" else c): q
                                    for c, q in person["qualifications"].items()}
    with pytest.raises(alumni.AlumniError, match="no count-tile label"):
        alumni.validate_alumni(data)


def test_each_category_heading_links_to_its_own_existing_anchor():
    page = committed_page()
    assert '<section class="sport alumni-card" id="senators" aria-labelledby="senators-h">' in page
    assert '<h2><a class="permalink" id="senators-h" href="#senators">U.S. senators</a></h2>' in page
    assert '<h2><a class="permalink" id="endowment-h" href="#endowment">Endowment</a></h2>' in page
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.sport[^{]*\.overall[^{]*\{ scroll-margin-top: 1rem; \}", css)


def test_every_card_and_the_endowment_card_offer_a_prefilled_correction_form():
    page = committed_page()
    base = "https://github.com/jacksonmote/DePauw-vs-Wabash-web/issues/new?template=alumni-correction.yml"
    assert alumni.REPO_URL == render.REPO_URL
    assert page.count("Suggest a correction</a>") == 11
    assert f'href="{base}&amp;title=Alumni%20correction%3A%20U.S.%20senators&amp;category=U.S.%20senators"' in page
    assert 'category=Endowment"' in page
    assert alumni.correction_url("Rhodes Scholars") == (
        f"{base}&title=Alumni%20correction%3A%20Rhodes%20Scholars&category=Rhodes%20Scholars")


def test_the_alumni_issue_form_asks_for_the_right_fields_and_nothing_personal():
    form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "alumni-correction.yml").read_text(encoding="utf-8")
    for field in ("id: school", "id: category", "id: person", "id: what_is_wrong", "id: source_link"):
        assert field in form
    assert re.search(r"- type: input\s+id: category", form)        # an input, so ?category= prefills it
    assert "someone missing" in form and "This issue will be public" in form
    config = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in config


def test_the_alumni_footer_is_unchanged_by_the_polish():
    page = committed_page()
    footer = page[page.index('<footer class="site-footer">'):]
    assert footer == (
        '<footer class="site-footer"><div class="wrap"><p class="footer-links"><a href="../">Athletics</a> · '
        '<a href="./" aria-current="page">Alumni</a> · <a href="../how-it-works/">How the athletics numbers work</a> · '
        '<a href="https://github.com/jacksonmote/DePauw-vs-Wabash-web">Code and data on GitHub</a></p>\n'
        '<p>Alumni and endowment records use manually reviewed sources; athletic data has its own update record and scope.</p>\n'
        '<p>Unofficial fan site, not affiliated with DePauw University or Wabash College.</p>'
        '<p class="copyright">© 2026 Jackson Mote</p></div></footer>\n</body>\n</html>\n')


def test_sitemap_lastmod_for_the_alumni_page_follows_the_newest_verified_date(tmp_path):
    alumni_data, endowment = read_data(), read_endowment()
    alumni_data["verified_at"], endowment["verified_at"] = "2026-11-02", "2026-11-09"
    a, e = tmp_path / "alumni.json", tmp_path / "endowment.json"
    a.write_text(json.dumps(alumni_data), encoding="utf-8")
    e.write_text(json.dumps(endowment), encoding="utf-8")
    out = tmp_path / "site"
    render.build(render.DATA, out, alumni_path=a, endowment_path=e)
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://depauwvswabash.com/alumni/</loc><lastmod>2026-11-09</lastmod>" in sitemap
