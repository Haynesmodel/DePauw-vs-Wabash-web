"""The seven requested rivalry jokes, page-scoped script policy, and asset budgets."""

import datetime as dt
import html
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scraper"))
import render  # noqa: E402

NOW = dt.datetime(2026, 10, 30, 12, tzinfo=dt.timezone.utc)
BASE_CSP = "default-src 'none'; style-src 'self'; img-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'"
HOME_CSP = BASE_CSP + "; script-src 'self'"
PAGES = (
    "index.html", "alumni/index.html", "how-it-works/index.html",
    "how-it-works/athletics/index.html", "how-it-works/alumni/index.html",
    "404.html", "bell-heist/index.html",
)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("easter-eggs") / "site"
    render.build(ROOT / "data" / "series.json", out, now=NOW, upcoming_path=out / "missing.json")
    return out


def page(site, path):
    return (site / path).read_text(encoding="utf-8")


def csp(source):
    return html.unescape(re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', source).group(1))


def test_seven_page_inventory_and_script_csp_are_exact(site):
    assert {p.relative_to(site).as_posix() for p in site.rglob("*.html")} == set(PAGES)
    for name in PAGES:
        source = page(site, name)
        if name == "index.html":
            assert csp(source) == HOME_CSP
            assert source.count('<script src="easter-eggs.js" defer></script>') == 1
        else:
            assert csp(source) == BASE_CSP
            assert "<script" not in source
        assert "unsafe-" not in csp(source) and "*" not in csp(source)
        assert "style=" not in source and "<style" not in source


def test_bell_heist_is_a_discoverable_unindexed_story_not_in_the_sitemap(site):
    home = page(site, "index.html")
    heist = page(site, "bell-heist/index.html")
    assert 'href="bell-heist/" aria-label="A little Bell business"' in home
    assert '<h2>Mission accomplished</h2>' in heist
    assert "You’ve successfully relocated the Monon Bell to Greencastle. Your alumni association has no knowledge of this operation." in heist
    assert "An entirely fictional mission." in heist
    assert '<a href="../#monon-bell">Check the real Bell holder</a>' in heist
    assert 'name="robots" content="noindex"' in heist and "canonical" not in heist
    assert len(re.findall(r'<p class="back">', heist)) == 1
    assert "bell-heist" not in page(site, "sitemap.xml")


def test_each_nonempty_history_gets_one_reward_and_empty_history_gets_none():
    data = render.load(ROOT / "data" / "series.json")
    home = render.render_index(data, now=NOW, upcoming={})
    reward = "You’ve reached the bottom. Wabash jokes practically write themselves."
    assert home.count(reward) == sum(bool(sport["games"]) for sport in data["sports"].values())
    empty = render.games_table("football", [])
    assert reward not in empty
    assert home.count('<details class="tiger-note">') == 1
    assert home.count('src="easter-paw.svg"') == min(3, len(data["sports"]))


def test_alumni_disclosure_is_scoped_and_native(site):
    alumni = page(site, "alumni/index.html")
    assert alumni.count("How can Wabash improve these numbers?") == 1
    assert "We recommend transferring to DePauw." in alumni
    for name in PAGES:
        if name != "alumni/index.html":
            assert "How can Wabash improve these numbers?" not in page(site, name)
    assert '<details class="admissions-note"><summary>' in alumni


def test_title_entrance_is_progressive_and_uses_one_native_click_handler(site):
    home = page(site, "index.html")
    script = (site / "easter-eggs.js").read_text(encoding="utf-8")
    assert 'id="entrance-fallback">DePauw vs. Wabash</span>' in home
    assert 'id="tiger-entrance" class="entrance-button" type="button" hidden' in home
    assert 'id="entrance-status" class="entrance-status" role="status" aria-live="polite"' in home
    assert 'id="entrance-hint"' in home and "five times" in home
    assert script.count('addEventListener("click"') == 1
    assert 'activations === 5' in script and 'activations = Math.min(5, activations + 1)' in script
    assert 'status.textContent = "Your education has been verified."' in script
    assert "innerHTML" not in script and "keydown" not in script and "touchstart" not in script
    css = (ROOT / "static/styles.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".entrance-button:focus-visible" in css and ".tiger-note summary:focus-visible" in css


def test_shared_footer_comment_and_disclosure_are_exactly_once_on_all_seven_pages(site):
    for name in PAGES:
        source = page(site, name)
        assert source.count("<!-- Both schools supplied the records. Only one supplied the developers. -->") == 1
        assert source.count("A note on impartiality") == 1
        assert source.count("The data is independently sourced. The developers were educated correctly.") == 1
        assert source.index("<!-- Both schools supplied") < source.index('<p class="footer-links">')
        assert source.index("Unofficial fan site") < source.index("A note on impartiality") < source.index('class="copyright"')
        without_comments = re.sub(r"<!--.*?-->", "", source, flags=re.S)
        assert "Only one supplied the developers." not in without_comments
    for export in ("games.csv", "data/series.json", "data/alumni.json", "data/endowment.json", "site.webmanifest"):
        assert "Only one supplied the developers." not in (site / export).read_text(encoding="utf-8")


def test_new_assets_and_stylesheet_stay_within_the_approved_budgets():
    assert len((ROOT / "static/easter-eggs.js").read_bytes()) <= 4096
    assert sum((ROOT / f"static/{asset}").stat().st_size for asset in
               ("easter-bell.svg", "easter-paw.svg", "easter-tiger.svg")) <= 12288
    # Baseline stylesheet on c9fcced: 13,666 bytes; feature allowance: 6,144 bytes.
    assert (ROOT / "static/styles.css").stat().st_size <= 19810


@pytest.mark.parametrize(("result", "holder"), [("W", "DePauw"), ("L", "Wabash")])
def test_rendered_assets_exist_and_heist_link_works_for_either_bell_holder(site, result, holder):
    games = [{"date": "2024-11-09", "result": result, "depauw": 20, "wabash": 10}]
    block = render.bell_block(games)
    assert 'href="bell-heist/" aria-label="A little Bell business"' in block
    assert holder in block
    for asset in ("easter-bell.svg", "easter-paw.svg", "easter-tiger.svg", "easter-eggs.js"):
        assert (site / asset).read_bytes() == (ROOT / "static" / asset).read_bytes()
    assert render.bell_block([]) == ""
