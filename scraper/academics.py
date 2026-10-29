"""Validation and rendering for the manually reviewed Academics comparison."""

from __future__ import annotations

import datetime as dt
import html
from urllib.parse import urlparse


SCHOOLS = (("depauw", "DePauw"), ("wabash", "Wabash"))


class AcademicsError(ValueError):
    """Curated academics data is missing or inconsistent."""


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise AcademicsError(f"{field} must be a non-empty string")


def _source(value, field):
    if not isinstance(value, dict):
        raise AcademicsError(f"{field} must be a source object")
    _text(value.get("label"), f"{field}.label")
    _text(value.get("url"), f"{field}.url")
    parsed = urlparse(value["url"])
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise AcademicsError(f"{field}.url must be an absolute HTTP(S) URL")


def validate(data: dict) -> dict:
    if isinstance(data.get("schema_version"), bool) or data.get("schema_version") != 1:
        raise AcademicsError("academics data must use schema_version 1")
    _text(data.get("verified_at"), "academics.verified_at")
    try:
        dt.date.fromisoformat(data["verified_at"])
    except ValueError as exc:
        raise AcademicsError("academics.verified_at must be an ISO date") from exc
    _text(data.get("methodology"), "academics.methodology")
    metrics = data.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise AcademicsError("academics.metrics must be a non-empty list")
    ids = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise AcademicsError("each academic metric must be an object")
        mid = metric.get("id")
        if not isinstance(mid, str) or not mid or mid in ids:
            raise AcademicsError(f"invalid or duplicate academic metric id: {mid!r}")
        ids.add(mid)
        for field in ("name", "group", "interpretation"):
            _text(metric.get(field), f"metric {mid}.{field}")
        for school, _ in SCHOOLS:
            _text(metric.get(school), f"metric {mid}.{school}")
            _text(metric.get(f"{school}_detail"), f"metric {mid}.{school}_detail")
            _source(metric.get(f"{school}_source"), f"metric {mid}.{school}_source")
    return data


def _esc(value):
    return html.escape(str(value), quote=True)


def render_page(data: dict, *, head_html: str, copyright_year: int = 2026) -> str:
    cards = []
    for metric in data["metrics"]:
        school_tiles = []
        for school, label in SCHOOLS:
            source = metric[f"{school}_source"]
            school_tiles.append(
                f'<div class="tile tile-{school} academic-school"><h3 class="tile-name">{label}</h3>'
                f'<p class="tile-num">{_esc(metric[school])}</p>'
                f'<p>{_esc(metric[f"{school}_detail"])}</p>'
                f'<p><a href="{_esc(source["url"])}">{_esc(source["label"])}</a></p></div>')
        cards.append(
            f'<section class="sport academic-card" id="{_esc(metric["id"])}">'
            f'<p class="academic-group">{_esc(metric["group"])}</p><h2>{_esc(metric["name"])}</h2>'
            f'<div class="tiles academic-values">{"".join(school_tiles)}</div>'
            f'<p>{_esc(metric["interpretation"])}</p></section>')
    return "\n".join([
        head_html, "<body>",
        '<header class="site-header"><div class="wrap"><h1>DePauw vs. Wabash</h1>',
        '<nav class="site-nav" aria-label="Main navigation"><a href="../">Athletics</a> '
        '<a href="../alumni/">Alumni</a> <a href="./" aria-current="page">Academics</a></nav>',
        '<p class="subtitle">Academic profile and student outcomes</p></div></header>',
        '<main class="wrap academics-main">',
        '<nav class="category-nav" aria-label="Academic categories">'
        + " · ".join(f'<a href="#{_esc(m["id"])}">{_esc(m["name"])}</a>' for m in data["metrics"])
        + '</nav>',
        f'<p class="alumni-method">{_esc(data["methodology"])} Verified {_esc(data["verified_at"])}.</p>',
        *cards,
        '<p class="alumni-download">Download the reviewed figures: <a href="../data/academics.json">academics.json</a></p>',
        '</main>',
        '<footer class="site-footer"><div class="wrap"><p class="footer-links"><a href="../">Athletics</a> · '
        '<a href="../alumni/">Alumni</a> · <a href="./" aria-current="page">Academics</a> · '
        '<a href="../how-it-works/">How the athletics numbers work</a> · '
        '<a href="https://github.com/jacksonmote/DePauw-vs-Wabash-web">Code and data on GitHub</a></p>',
        '<p>Academic figures use school-published sources and have their own dates, cohorts, and definitions.</p>',
        '<p>Unofficial fan site, not affiliated with DePauw University or Wabash College.</p>',
        f'<p class="copyright">© {_esc(copyright_year)} Jackson Mote</p></div></footer>',
        '</body>', '</html>', ''])
