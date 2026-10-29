"""The footer is one function, so every page (home, how-it-works, 404) carries the same lines."""

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 12, 1, 15, 0, tzinfo=dt.timezone.utc)
MEN_ONLY = ("Only men’s head-to-head sports are compared: Wabash is an all-male college, and multi-team sports "
            "(cross country, track and field, swimming and diving, golf) aren’t head-to-head.")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("footer") / "site"
    render.build(ROOT / "data" / "series.json", out, now=NOW, upcoming_path=out / "none.json")
    return out


def footer(site, name):
    html = (site / name).read_text(encoding="utf-8")
    return html[html.index('<footer class="site-footer">'):]


PAGES = {"index.html": "", "how-it-works/index.html": "../", "404.html": "/"}


@pytest.mark.parametrize("name", PAGES)
def test_every_page_has_the_new_lines_in_order(site, name):
    f = footer(site, name)
    how, git, men, disclaimer, copyright_ = (f.index(x) for x in (
        "How the numbers work", "Built in the open: code and data on GitHub", MEN_ONLY, render.DISCLAIMER, "© 2026"))
    assert how < git < men < disclaimer < copyright_
    assert f.count("How the numbers work") == 1
    assert f'href="{PAGES[name]}how-it-works/"' in f
    assert f'<a href="{render.REPO_URL}">Built in the open: code and data on GitHub</a>' in f
    assert 'class="copyright"' in f[-200:]                       # the copyright is still the last line


@pytest.mark.parametrize("name", PAGES)
def test_the_old_men_only_line_is_gone(site, name):
    assert "Only men’s sports are compared because" not in footer(site, name)


@pytest.mark.parametrize("name", ["index.html", "how-it-works/index.html"])
def test_the_links_sit_next_to_the_source_links(site, name):
    f = footer(site, name)
    assert f.index('class="sources"') < f.index("How the numbers work") < f.index(MEN_ONLY)


def test_the_not_included_note_under_the_totals_is_unchanged(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    assert render.NOT_INCLUDED in html and "<strong>Not included:</strong>" in html


def test_the_totals_heading_is_renamed_and_keeps_its_anchor(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    assert '<h2 id="overall-h">All head-to-head sports</h2>' in html
    assert 'aria-labelledby="overall-h"' in html                  # the id old links and the section label rely on
    assert "All sports combined" not in html
