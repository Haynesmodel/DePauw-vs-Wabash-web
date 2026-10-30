"""Validation and rendering for the manually researched Alumni page."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote, urlparse


SCHOOLS = {"depauw": "DePauw", "wabash": "Wabash"}
SUBTITLE = "Notable graduates and endowments, side by side, with a source for every name."


class AlumniError(ValueError):
    """Curated alumni or endowment data is missing or inconsistent."""


def _fail(message):
    raise AlumniError(message)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string")


def _url(value, field):
    _text(value, field)
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        _fail(f"{field} must be an absolute HTTP(S) URL with a host")


def _date(value, field):
    _text(value, field)
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        _fail(f"{field} must be an ISO date (YYYY-MM-DD)")
    if parsed.isoformat() != value:
        _fail(f"{field} must be an ISO date (YYYY-MM-DD)")


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read {label} data at {path}: {exc}")
    if not isinstance(value, dict):
        _fail(f"{label} data must be a JSON object")
    if isinstance(value.get("schema_version"), bool) or value.get("schema_version") != 1:
        _fail(f"{label} data must use schema_version 1")
    return value


def validate_alumni(data: dict) -> dict:
    if isinstance(data.get("schema_version"), bool) or data.get("schema_version") != 1:
        _fail("alumni data must use schema_version 1")
    _date(data.get("verified_at"), "alumni.verified_at")
    _text(data.get("methodology"), "alumni.methodology")
    categories = data.get("categories")
    if not isinstance(categories, list) or len(categories) != 10:
        _fail("alumni.categories must contain all ten researched categories")
    by_id = {}
    for category in categories:
        if not isinstance(category, dict):
            _fail("each alumni category must be an object")
        cid = category.get("id")
        if not isinstance(cid, str) or not cid or cid in by_id:
            _fail(f"invalid or duplicate alumni category id: {cid!r}")
        _text(category.get("name"), f"category {cid}.name")
        _text(category.get("definition"), f"category {cid}.definition")
        if cid not in TILE_LABELS:
            _fail(f"category {cid} has no count-tile label; add it to TILE_LABELS in alumni.py")
        reviews = category.get("review")
        if not isinstance(reviews, dict) or set(reviews) != set(SCHOOLS):
            _fail(f"category {cid}.review must document both schools")
        for school, review in reviews.items():
            if not isinstance(review, dict):
                _fail(f"category {cid}.review.{school} must be an object")
            _text(review.get("notes"), f"category {cid}.review.{school}.notes")
            sources = review.get("sources")
            if not isinstance(sources, list) or not sources:
                _fail(f"category {cid}.review.{school}.sources must be a non-empty list")
            for i, source in enumerate(sources):
                if not isinstance(source, dict):
                    _fail(f"category {cid}.review.{school}.sources[{i}] must be an object")
                _text(source.get("label"), f"category {cid}.review.{school}.sources[{i}].label")
                _url(source.get("url"), f"category {cid}.review.{school}.sources[{i}].url")
        by_id[cid] = category

    people = data.get("people")
    if not isinstance(people, list):
        _fail("alumni.people must be a list")
    ids, memberships = set(), set()
    for person in people:
        if not isinstance(person, dict):
            _fail("each alumni person must be an object")
        pid = person.get("id")
        if not isinstance(pid, str) or not pid or pid in ids:
            _fail(f"invalid or duplicate alumni person id: {pid!r}")
        ids.add(pid)
        _text(person.get("name"), f"person {pid}.name")
        school = person.get("school")
        if school not in SCHOOLS:
            _fail(f"person {pid} has invalid school {school!r}")
        _text(person.get("degree"), f"person {pid}.degree")
        year = person.get("degree_year")
        if isinstance(year, bool) or not isinstance(year, int) or not 1700 <= year <= 2100:
            _fail(f"person {pid}.degree_year must be a valid earned-degree year")
        for field in ("school_source",):
            source = person.get(field)
            if not isinstance(source, dict):
                _fail(f"person {pid}.{field} must have label and url")
            _text(source.get("label"), f"person {pid}.{field}.label")
            _url(source.get("url"), f"person {pid}.{field}.url")
        cats = person.get("categories")
        if not isinstance(cats, list) or not cats:
            _fail(f"person {pid}.categories must be non-empty")
        if len(cats) != len(set(cats)):
            _fail(f"person {pid} has duplicate category membership")
        for cid in cats:
            if cid not in by_id:
                _fail(f"person {pid} references unknown category {cid!r}")
            membership = (pid, cid)
            if membership in memberships:
                _fail(f"duplicate alumni membership {membership}")
            memberships.add(membership)
        qualifications = person.get("qualifications")
        if not isinstance(qualifications, dict) or set(qualifications) != set(cats):
            _fail(f"person {pid}.qualifications must document each category membership exactly once")
        for cid, qualification in qualifications.items():
            if not isinstance(qualification, dict):
                _fail(f"person {pid}.qualifications.{cid} must be an object")
            _text(qualification.get("achievement"), f"person {pid}.qualifications.{cid}.achievement")
            years = qualification.get("years")
            if (not isinstance(years, list) or not years or (len(years) > 2 and len(years) % 2 != 0) or any(isinstance(y, bool) or not isinstance(y, int)
                    or not 1700 <= y <= 2100 for y in years)):
                _fail(f"person {pid}.qualifications.{cid}.years must contain qualifying years")
            intervals = [(years[0], years[0])] if len(years) == 1 else [
                (years[i], years[i + 1]) for i in range(0, len(years), 2)
            ]
            if any(start > end for start, end in intervals) or any(
                intervals[i][0] <= intervals[i - 1][1] for i in range(1, len(intervals))
            ):
                _fail(f"person {pid}.qualifications.{cid}.years must use ordered, non-overlapping ranges")
            present = qualification.get("present", False)
            if not isinstance(present, bool):
                _fail(f"person {pid}.qualifications.{cid}.present must be true or false")
            if present and (len(years) > 1 and len(years) % 2):
                _fail(f"person {pid}.qualifications.{cid}.present needs a start year or ordered year ranges")
            source = qualification.get("source")
            if not isinstance(source, dict):
                _fail(f"person {pid}.qualifications.{cid}.source must have label and url")
            _text(source.get("label"), f"person {pid}.qualifications.{cid}.source.label")
            _url(source.get("url"), f"person {pid}.qualifications.{cid}.source.url")
            if cid == "fortune-500-ceos":
                _text(qualification.get("company"), f"person {pid}.qualifications.{cid}.company")
                rank_year = qualification.get("rank_year")
                if isinstance(rank_year, bool) or not isinstance(rank_year, int) or not 1955 <= rank_year <= 2100:
                    _fail(f"person {pid}.qualifications.{cid}.rank_year must name a U.S. Fortune 500 ranking year")
                rank = qualification.get("rank")
                if isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= 500:
                    _fail(f"person {pid}.qualifications.{cid}.rank must be between 1 and 500")
                if not any(start <= rank_year <= end for start, end in intervals):
                    _fail(f"person {pid}.qualifications.{cid}.ranking year must overlap the CEO tenure")
                ranking = qualification.get("ranking_source")
                if not isinstance(ranking, dict):
                    _fail(f"person {pid}.qualifications.{cid}.ranking_source must have label and url")
                _text(ranking.get("label"), f"person {pid}.qualifications.{cid}.ranking_source.label")
                _url(ranking.get("url"), f"person {pid}.qualifications.{cid}.ranking_source.url")
    return data


def validate_endowment(data: dict) -> dict:
    _date(data.get("verified_at"), "endowment.verified_at")
    _date(data.get("as_of"), "endowment.as_of")
    _text(data.get("fiscal_year"), "endowment.fiscal_year")
    year = data["fiscal_year"]
    if not year.startswith("FY") or not year[2:].isdigit() or len(year) != 6:
        _fail("endowment.fiscal_year must use FYyyyy format")
    if data["as_of"] != f"{year[2:]}-06-30":
        _fail("endowment.as_of must match the fiscal-year end date")
    _text(data.get("basis"), "endowment.basis")
    if not isinstance(data.get("explanation"), str) or not data["explanation"].strip():
        _fail("endowment.explanation must be a non-empty string")
    schools = data.get("schools")
    if not isinstance(schools, dict) or set(schools) != set(SCHOOLS):
        _fail("endowment.schools must contain exactly depauw and wabash")
    for key, item in schools.items():
        if not isinstance(item, dict):
            _fail(f"endowment.schools.{key} must be an object")
        amount = item.get("amount_usd")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            _fail(f"endowment.schools.{key}.amount_usd must be a non-negative integer USD amount")
        for field in ("source_label", "source_note"):
            _text(item.get(field), f"endowment.schools.{key}.{field}")
        _url(item.get("source_url"), f"endowment.schools.{key}.source_url")
        enrolled = item.get("enrollment")
        if not isinstance(enrolled, dict):
            _fail(f"endowment.schools.{key}.enrollment must be an object")
        count = enrolled.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            _fail(f"endowment.schools.{key}.enrollment.count must be a positive integer")
        # the endowment is as of June 30 of the fiscal year, so the matching academic year began the fall before
        if enrolled.get("term") != f"Fall {int(year[2:]) - 1}":
            _fail(f"endowment.schools.{key}.enrollment.term must be Fall {int(year[2:]) - 1} "
                  f"to match {year}")
        _text(enrolled.get("measure"), f"endowment.schools.{key}.enrollment.measure")
        _text(enrolled.get("source_label"), f"endowment.schools.{key}.enrollment.source_label")
        _url(enrolled.get("source_url"), f"endowment.schools.{key}.enrollment.source_url")
        _date(enrolled.get("verified_at"), f"endowment.schools.{key}.enrollment.verified_at")
    return data


def per_student(endowment: dict) -> dict:
    """{"depauw": 543000, "wabash": 511000}: endowment divided by headcount, to the nearest $1,000, half up.
    Integer arithmetic from the exact amounts, never from a rounded figure. Calculated here, never stored."""
    result = {}
    for school, item in endowment["schools"].items():
        amount, students = item["amount_usd"], item["enrollment"]["count"]
        result[school] = (2 * amount + 1000 * students) // (2000 * students) * 1000
    return result


def counts(data: dict) -> dict:
    result = {c["id"]: {school: 0 for school in SCHOOLS} for c in data["categories"]}
    seen = {cid: {school: set() for school in SCHOOLS} for cid in result}
    for person in data["people"]:
        for cid in person["categories"]:
            seen[cid][person["school"]].add(person["id"])
    for cid, school_counts in seen.items():
        for school, ids in school_counts.items():
            result[cid][school] = len(ids)
    return result


def visible_categories(data: dict) -> list:
    counts_by_id = counts(data)
    return [c for c in data["categories"] if any(counts_by_id[c["id"]].values())]


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_date(iso: str) -> str:
    """"Oct 29, 2026": the same style as the athletics page (render.fmt_date; a test keeps them equal).
    The JSON keeps ISO dates; they never show in the page text."""
    d = dt.date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def compact_usd(amount: int) -> tuple[str, str]:
    """("$1.04", "billion") or ("$443", "million"): billions to two decimals, millions to whole numbers,
    always from the exact integer (half up), so two figures are rounded the same way."""
    if amount >= 1_000_000_000:
        return f"${(Decimal(amount) / 1_000_000_000).quantize(Decimal('0.01'), ROUND_HALF_UP)}", "billion"
    if amount >= 1_000_000:
        return f"${(Decimal(amount) / 1_000_000).quantize(Decimal('1'), ROUND_HALF_UP):,}", "million"
    return f"${amount:,}", ""


def per_student_note(endowment: dict) -> str:
    """How the per-student figure is made. Shown wherever a per-student figure is shown."""
    term = next(iter(endowment["schools"].values()))["enrollment"]["term"].lower()
    return (f"Endowment per student divides each school’s audited endowment by its {term} total undergraduate "
            f"headcount from the U.S. Department of Education’s College Navigator (IPEDS), rounded to the "
            f"nearest $1,000.")


def degree_label(person: dict) -> str:
    """"B.A., 1969" when the degree is recorded, "Class of 1885" when only the year is known. A degree
    text that already names its years ("Literary department (1853), law department (1855)") is not repeated."""
    degree, year = person["degree"].strip(), person["degree_year"]
    if degree.lower() == "graduate":
        return f"Class of {year}"
    if re.search(r"\b(1[7-9]|20)\d\d\b", degree):
        return degree
    return f"{degree}, {year}"


def _esc(value):
    return html.escape(str(value), quote=True)


def _source(source):
    return f'<a href="{_esc(source["url"])}">{_esc(source["label"])}</a>'


REPO_URL = "https://github.com/jacksonmote/DePauw-vs-Wabash-web"     # a test keeps this equal to render.REPO_URL

# What a count tile calls one and many of each category's graduates. A new category must be added here.
TILE_LABELS = {
    "nobel": ("Nobel laureate", "Nobel laureates"),
    "vice-presidents": ("vice president", "vice presidents"),
    "senators": ("senator", "senators"),
    "representatives": ("representative", "representatives"),
    "governors": ("governor", "governors"),
    "fortune-500-ceos": ("Fortune 500 CEO", "Fortune 500 CEOs"),
    "pulitzer": ("Pulitzer winner", "Pulitzer winners"),
    "rhodes-scholars": ("Rhodes Scholar", "Rhodes Scholars"),
    "astronauts": ("astronaut", "astronauts"),
    "academy-awards": ("Academy Award winner", "Academy Award winners"),
}


def tile_label(cid: str, count: int) -> str:
    one, many = TILE_LABELS[cid]
    return one if count == 1 else many


def correction_url(category: str, repo_url: str = REPO_URL) -> str:
    """Opens the alumni-correction issue form with the category filled in."""
    return (f"{repo_url}/issues/new?template=alumni-correction.yml"
            f"&title={quote('Alumni correction: ' + category)}&category={quote(category)}")


def _tile(cls: str, name: str, number: str, label: str) -> str:
    return (f'<div class="tile {cls}"><span class="tile-name">{_esc(name)}</span>'
            f'<span class="tile-num">{_esc(number)}</span><span class="tile-label">{_esc(label)}</span></div>')


def _heading(anchor: str, text: str) -> str:
    """The heading text is the link to its own section, like the athletics cards."""
    return f'<h2><a class="permalink" id="{_esc(anchor)}-h" href="#{_esc(anchor)}">{_esc(text)}</a></h2>'


def _score_cell(school: str, text: str, lead: bool) -> str:
    if lead:
        return (f'<td class="score lead lead-{school}"><strong>{_esc(text)}</strong>'
                f'<span class="sr-only"> (higher)</span></td>')
    return f'<td class="score">{_esc(text)}</td>'


def scoreboard(categories: list, counts_by_id: dict, per: dict) -> str:
    """One row per category: the two counts, the larger one marked in its school's accent (and in bold, and
    for screen readers), ties plain. The endowment per student comes first. There is deliberately no total."""
    rows = []

    def row(href, name, depauw, wabash, shown):
        lead = "depauw" if depauw > wabash else "wabash" if wabash > depauw else None
        rows.append(f'<tr><th scope="row"><a href="#{_esc(href)}">{_esc(name)}</a></th>'
                    f'{_score_cell("depauw", shown[0], lead == "depauw")}'
                    f'{_score_cell("wabash", shown[1], lead == "wabash")}</tr>')

    row("endowment", "Endowment per student", per["depauw"], per["wabash"],
        (f'${per["depauw"]:,}', f'${per["wabash"]:,}'))
    for category in categories:
        c = counts_by_id[category["id"]]
        row(category["id"], category["name"], c["depauw"], c["wabash"], (str(c["depauw"]), str(c["wabash"])))
    return ('<table class="scoreboard"><caption>Named graduates by category, and endowment per student</caption>'
            '<thead><tr><th scope="col">Category</th><th scope="col">DePauw</th><th scope="col">Wabash</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def render_page(data: dict, endowment: dict, *, head_html: str, copyright_year: int = 2026,
                repo_url: str = REPO_URL) -> str:
    counts_by_id = counts(data)
    categories = visible_categories(data)
    per = per_student(endowment)
    cards = []
    for category in categories:
        cid = category["id"]
        members = [p for p in data["people"] if cid in p["categories"]]
        schools_html, tiles_html = [], []
        for school, label in SCHOOLS.items():
            people = [p for p in members if p["school"] == school]
            count = counts_by_id[cid][school]
            if people:
                rows = []
                for p in people:
                    q = p["qualifications"][cid]
                    evidence = _source(q["source"])
                    if cid == "fortune-500-ceos":
                        # the year is the Fortune ranking year, not a tenure, so say so
                        what = f'{_esc(q["achievement"])} · ranked #{q["rank"]} in the {q["rank_year"]} Fortune 500'
                        evidence += f' · {_source(q["ranking_source"])}'
                    else:
                        years = (", ".join(str(year) for year in q["years"]) if cid == "astronauts"
                                 else _format_years(q["years"], q.get("present", False)))
                        what = f'{_esc(q["achievement"])} ({years})'
                    rows.append(
                        f'<li><strong>{_esc(p["name"])}</strong> · {_esc(degree_label(p))}'
                        f'<br>{what}'
                        f'<br>Sources: {_source(p["school_source"])} · {evidence}</li>')
                details = f'<details><summary>Names and sources</summary><ul>{"".join(rows)}</ul></details>'
            else:
                details = '<p class="alumni-zero">No qualifying graduates found in the reviewed sources.</p>'
            schools_html.append(f'<div class="alumni-school alumni-school-{school}"><h3 class="alumni-school-name">{label}</h3>{details}</div>')
            tiles_html.append(_tile(f"tile-{school}", label, str(count), tile_label(cid, count)))
        cards.append(f'<section class="sport alumni-card" id="{_esc(cid)}" aria-labelledby="{_esc(cid)}-h">'
                     f'{_heading(cid, category["name"])}'
                     f'<p>{_esc(category["definition"])}</p><div class="tiles">{"".join(tiles_html)}</div>'
                     f'<div class="alumni-schools">{"".join(schools_html)}</div>'
                     f'<p class="alumni-report"><a href="{_esc(correction_url(category["name"], repo_url))}">'
                     f'Suggest a correction</a></p></section>')
    endow_cards = []
    for key, label in SCHOOLS.items():
        item = endowment["schools"][key]
        enrolled = item["enrollment"]
        figure, unit = compact_usd(item["amount_usd"])
        endow_cards.append(
            f'<div class="tile tile-{key} endowment-value"><h3 class="tile-name">{label}</h3>'
            f'<p class="tile-num money">${per[key]:,}</p><p class="tile-label">endowment per student</p>'
            f'<p class="money-line">Endowment: <span class="nowrap">{figure}{" " + unit if unit else ""}</span> '
            f'<span class="nowrap">(${item["amount_usd"]:,})</span></p>'
            f'<p class="money-line">Enrollment: <span class="nowrap">{enrolled["count"]:,}</span> students, '
            f'{_esc(enrolled["term"].lower())}</p>'
            f'<p class="money-line"><a href="{_esc(item["source_url"])}">Endowment source</a> · '
            f'<a href="{_esc(enrolled["source_url"])}">Enrollment source</a></p></div>')
    return "\n".join([
        head_html, '<body>',
        '<header class="site-header"><div class="wrap"><h1>DePauw vs. Wabash</h1>',
        '<nav class="site-nav" aria-label="Main navigation"><a href="../">Athletics</a> <a href="./" aria-current="page">Alumni</a></nav>',
        f'<p class="subtitle">{_esc(SUBTITLE)}</p></div></header>',
        '<main class="wrap alumni-main">',
        '<section class="overall alumni-overview" aria-labelledby="alumni-h">',
        '<h2 id="alumni-h">Alumni and endowment</h2>',
        '<p class="alumni-lede">Named graduates in award and public-service categories, and endowment per student, '
        'for DePauw and Wabash.</p>',
        scoreboard(categories, counts_by_id, per),
        f'<p class="alumni-method">Counts show named graduates verified in the reviewed sources. '
        f'Verified {_esc(fmt_date(data["verified_at"]))}. Endowment per student: audited '
        f'{_esc(endowment["fiscal_year"])} endowment divided by {_esc(next(iter(endowment["schools"].values()))["enrollment"]["term"].lower())} '
        f'headcount; the two schools’ endowment figures cover different scopes (see Endowment below).</p>',
        '<details class="alumni-method-details"><summary>Who counts and how sources were reviewed</summary>'
        f'<p>{_esc(data["methodology"])} A person may appear in more than one category; each person counts once per school and category. There is no overall alumni score.</p></details>',
        '</section>',
        f'<section class="overall endowment" id="endowment" aria-labelledby="endowment-h">{_heading("endowment", "Endowment")}'
        f'<p>Audited {_esc(endowment["fiscal_year"])} figures as of {_esc(fmt_date(endowment["as_of"]))}; reported accounting scopes differ.</p>'
        f'<div class="tiles endowment-values">{"".join(endow_cards)}</div>'
        f'<p class="endowment-caveat">{_esc(endowment["explanation"])} {_esc(per_student_note(endowment))}</p>'
        f'<p class="alumni-report"><a href="{_esc(correction_url("Endowment", repo_url))}">Suggest a correction</a></p>'
        f'<p>Verified {_esc(fmt_date(endowment["verified_at"]))}.</p></section>',
        *cards,
        '<p class="alumni-download">Download the curated records: <a href="../data/alumni.json">alumni.json</a> · '
        '<a href="../data/endowment.json">endowment.json</a> · <a href="../how-it-works/">How the athletics numbers work</a></p>',
        '</main>', '<footer class="site-footer"><div class="wrap"><p class="footer-links"><a href="../">Athletics</a> · '
        '<a href="./" aria-current="page">Alumni</a> · <a href="../how-it-works/">How the athletics numbers work</a> · '
        '<a href="https://github.com/jacksonmote/DePauw-vs-Wabash-web">Code and data on GitHub</a></p>',
        '<p>Alumni and endowment records use manually reviewed sources; athletic data has its own update record and scope.</p>',
        '<p>Unofficial fan site, not affiliated with DePauw University or Wabash College.</p>'
        f'<p class="copyright">© {_esc(copyright_year)} Jackson Mote</p></div></footer>',
        '</body>', '</html>', ''])


def _format_years(years: list[int], present: bool = False) -> str:
    """"2025", "1989–1993", "1981–1989, 1993–1995"; with present, the open term reads "2025–present"."""
    if len(years) == 1:
        return f"{years[0]}–present" if present else str(years[0])
    pairs = [f"{years[i]}–{years[i + 1]}" for i in range(0, len(years), 2)]
    if present:
        pairs[-1] = f"{years[-2]}–present"
    return ", ".join(pairs)
