"""Validation and rendering for the manually researched Alumni page."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from urllib.parse import urlparse


SCHOOLS = {"depauw": "DePauw", "wabash": "Wabash"}


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
    return data


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


def _esc(value):
    return html.escape(str(value), quote=True)


def _source(source):
    return f'<a href="{_esc(source["url"])}">{_esc(source["label"])}</a>'


def render_page(data: dict, endowment: dict, *, head_html: str, copyright_year: int = 2026) -> str:
    counts_by_id = counts(data)
    categories = visible_categories(data)
    links = " · ".join(f'<a href="#{_esc(c["id"])}">{_esc(c["name"])}</a>' for c in categories)
    cards = []
    for category in categories:
        cid = category["id"]
        members = [p for p in data["people"] if cid in p["categories"]]
        schools_html = []
        for school, label in SCHOOLS.items():
            people = [p for p in members if p["school"] == school]
            count = counts_by_id[cid][school]
            if people:
                rows = []
                for p in people:
                    q = p["qualifications"][cid]
                    years = (", ".join(str(year) for year in q["years"]) if cid == "astronauts"
                             else _format_years(q["years"]))
                    evidence = _source(q["source"])
                    if cid == "fortune-500-ceos":
                        evidence += (f' · {_esc(q["company"])} ranked #{q["rank"]} in the U.S. Fortune 500 '
                                     f'{q["rank_year"]} ({_source(q["ranking_source"])})')
                    rows.append(
                        f'<li><strong>{_esc(p["name"])}</strong> · {_esc(p["degree"])} ({p["degree_year"]})'
                        f'<br>{_esc(q["achievement"])} ({years})'
                        f'<br>Sources: {_source(p["school_source"])} · {evidence}</li>')
                details = f'<details><summary>{label}: {count} verified graduate{"s" if count != 1 else ""}</summary><ul>{"".join(rows)}</ul></details>'
            else:
                details = f'<p class="alumni-zero"><strong>{label}: 0.</strong> No qualifying graduates were found in the reviewed sources.</p>'
            schools_html.append(f'<div class="tile tile-{school} alumni-school"><h3 class="tile-name">{label} <span>({count})</span></h3>{details}</div>')
        cards.append(f'<section class="sport alumni-card" id="{_esc(cid)}"><h2>{_esc(category["name"])}</h2>'
                     f'<p>{_esc(category["definition"])}</p><div class="tiles alumni-schools">{"".join(schools_html)}</div></section>')
    endow_cards = []
    for key, label in SCHOOLS.items():
        item = endowment["schools"][key]
        endow_cards.append(f'<div class="tile tile-{key} endowment-value"><h3 class="tile-name">{label}</h3>'
                           f'<p class="tile-num money">${item["amount_usd"]:,}</p><p><a href="{_esc(item["source_url"])}">'
                           f'{_esc(item["source_label"])} · {_esc(item["source_note"])}</a></p></div>')
    return "\n".join([
        head_html, '<body>',
        '<header class="site-header"><div class="wrap"><h1>DePauw vs. Wabash</h1>',
        '<nav class="site-nav" aria-label="Main navigation"><a href="../">Athletics</a> <a href="./" aria-current="page">Alumni</a></nav>',
        '<p class="subtitle">Verified named graduates and endowment comparison</p></div></header>',
        '<main class="wrap alumni-main"><nav class="category-nav" aria-label="Alumni categories">' + links + ' · <a href="#endowment">Endowment</a></nav>',
        f'<p class="alumni-method">Counts show named graduates verified in the reviewed sources. Verified {_esc(data["verified_at"])}.</p>',
        '<details class="alumni-method-details"><summary>Who counts and how sources were reviewed</summary>'
        f'<p>{_esc(data["methodology"])} A person may appear in more than one category; each person counts once per school and category. There is no overall alumni score.</p></details>',
        *cards,
        f'<section class="overall endowment" id="endowment"><h2>Endowment</h2><p>{_esc(endowment["explanation"])}</p>'
        f'<p>Fiscal year { _esc(endowment["fiscal_year"]) } · as of { _esc(endowment["as_of"]) } · {_esc(endowment["basis"])}</p>'
        f'<div class="tiles endowment-values">{"".join(endow_cards)}</div><p>Verified { _esc(endowment["verified_at"]) }.</p></section>',
        '<p class="alumni-download">Download the curated records: <a href="../data/alumni.json">alumni.json</a> · '
        '<a href="../data/endowment.json">endowment.json</a> · <a href="../how-it-works/">How the athletics numbers work</a></p>',
        '</main>', '<footer class="site-footer"><div class="wrap"><p class="footer-links"><a href="../">Athletics</a> · '
        '<a href="./" aria-current="page">Alumni</a> · <a href="../how-it-works/">How the athletics numbers work</a> · '
        '<a href="https://github.com/jacksonmote/DePauw-vs-Wabash-web">Code and data on GitHub</a></p>',
        '<p>Alumni and endowment records use manually reviewed sources; athletic data has its own update record and scope.</p>',
        '<p>Unofficial fan site, not affiliated with DePauw University or Wabash College.</p>'
        f'<p class="copyright">© {_esc(copyright_year)} Jackson Mote</p></div></footer>',
        '</body>', '</html>', ''])


def _format_years(years: list[int]) -> str:
    if len(years) == 1:
        return str(years[0])
    if len(years) == 2:
        return f"{years[0]}–{years[1]}"
    return ", ".join(f"{years[i]}–{years[i + 1]}" for i in range(0, len(years), 2))
