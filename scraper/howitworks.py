"""
The "How the numbers work" page (/how-it-works/): the same facts as the README's merge section, written for
fans. Every number comes from the data (or from the constants in merge.py and gameday.py that the merge
actually uses), never from this file, so the page cannot go out of date when the data changes.

Standard library only; render.py supplies the page shell and footer.
"""

from __future__ import annotations

import html

import gameday
import merge

TITLE = "How the numbers work | DePauw vs. Wabash"
H1 = "How the numbers work"

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def days(n: int) -> str:
    return f"{n} day" + ("" if n == 1 else "s")


def placeholder_range() -> str:
    """'Jan 1 to Jan 3', from the placeholder days the merge treats as 'no real date'."""
    ds = sorted(merge.PLACEHOLDER_DAYS)
    name = lambda d: f"{MONTH_ABBR[d[0] - 1]} {d[1]}"
    return name(ds[0]) if len(ds) == 1 else f"{name(ds[0])} to {name(ds[-1])}"


def ruling_counts(rules: dict) -> tuple:
    """(same-game, different-games, several-days-of-one-meet rulings) across every sport, from the overrides."""
    same = sum(len(r.get("same_game", [])) for r in rules.values())
    diff = sum(len(r.get("different_games", [])) for r in rules.values())
    days_of_one = sum(len(r.get("session_of", [])) for r in rules.values())
    return same, diff, days_of_one


SWIMMING = "mens-swimming-and-diving"


def unit_note(sports: dict) -> str:
    """'tennis counts matches and swimming and diving counts meets': the sports that call a game something else."""
    notes = [f"{words(s['name'])} counts {s['unit'][1]}" for s in sports.values() if s.get("unit")]
    return " and ".join(notes)


def words(name: str) -> str:
    """"Men's Swimming and Diving" -> "swimming and diving"."""
    return name.replace("Men’s ", "").replace("Men's ", "").lower()


def swimming_lines(sports: dict) -> list:
    """The swimming and diving section, from the data. Empty when the sport is not on the site."""
    s = sports.get(SWIMMING)
    if not s:
        return []
    games = s["games"]
    half = sum(1 for g in games if any(isinstance(g.get(f), float) for f in ("depauw", "wabash")))
    unscored = sum(1 for g in games if g.get("score_known") is False)
    sessions = (s.get("sources") or {}).get("session_rows", 0)
    return [
        '<h3>Swimming and diving</h3>',
        '<p>Only dual meets, where DePauw’s team swims Wabash’s team head to head, are counted. Invitationals, '
        'relays, and conference championships have many teams in the pool at once, so there is no head-to-head '
        'result to add up, and they are left out of the records and out of “Next meeting”. '
        'The site tells a dual meet from a multi-team event by the name the school gives it and by how many '
        'opponents are listed.</p>',
        '<ul>',
        f'<li><strong>Half points:</strong> a meet can end with half a point on the board. Scores like 172.5 are '
        f'shown just as the schools list them (meets with a half point right now: {half:,}), and the point '
        'totals add them up exactly.</li>',
        f'<li><strong>Meets with no score:</strong> a school may list who won a meet without listing the score. '
        f'The meet still counts as a win or a loss, but it has no points to add to the totals, the biggest-win '
        f'list or the close-meet count, and the page says “score not recorded” (right now: {unscored:,}).</li>',
        '<li><strong>A score written the wrong way around:</strong> when a row says one school won but lists '
        'a bigger score for the other, the site trusts the win or loss and swaps the two scores, then says so '
        'beside the game. This is checked on every sport, not only swimming.</li>',
        f'<li><strong>A meet spread over several days:</strong> in March 2021 the two schools swam one '
        f'three-day meet. DePauw’s record has one meet; Wabash’s lists the running scores after each day as if '
        f'they were separate meets (rows set aside right now: {sessions:,}). A person read Wabash’s own write-ups '
        'and ruled that they are days of one meet, so it counts once, and the page shows the running scores '
        'beside it.</li>',
        '</ul>',
    ]


def totals(sports: dict) -> dict:
    keys = ("both", "depauw_only", "wabash_only", "disputed", "date_differs", "dates_not_recorded")
    return {k: sum(s.get("sources", {}).get(k, 0) for s in sports.values()) for k in keys}


def frequent_minutes() -> int:
    """Minutes between game-day runs, from the workflow's frequent schedule (e.g. '7,37 * * * *' is 30)."""
    return 60 // len(gameday.FREQUENT_CRON.split()[0].split(","))


def content(data: dict, rules: dict, kept: int, *, sources_html: str, not_included: str, repo_url: str) -> list:
    """The page's <main> section as lines of HTML. `rules` is merge.load_overrides, `kept` the number of
    keep_previous rulings, `sources_html` the same per-sport source links the footer shows."""
    sports = data["sports"]
    t = data["totals"]
    n = totals(sports)
    same, diff, days_of_one = ruling_counts(rules)
    names = [s["name"] for s in sports.values()]
    names_text = (" and ".join(names) if len(names) <= 2        # a serial comma from three items on
                  else ", ".join(names[:-1]) + f", and {names[-1]}")
    both_listed = n["both"]
    one_school = n["depauw_only"] + n["wabash_only"]
    overrides_url = f"{repo_url}/blob/main/data/overrides.json"
    out = [
        '<section class="prose" aria-labelledby="how-h">',
        f'<h2 id="how-h">{esc(H1)}</h2>',
        '<p>This site adds up every game DePauw and Wabash have played against each other. Here is where '
        'the numbers come from and what the site does when the two schools’ records do not line up.</p>',

        '<h3>Where the data comes from</h3>',
        '<p>Nothing is typed in by hand. The site reads each school’s own athletics website: the '
        '“opponent history” page for each sport (every game ever recorded against the other school) and '
        'the schedule page (upcoming games). Those pages are checked automatically, and you can open any '
        'of them yourself to compare:</p>',
        f'<ul class="sources">\n{sources_html}\n</ul>',

        '<h3>What is counted</h3>',
        f'<p>Only men’s sports that DePauw and Wabash play head to head: {esc(names_text)}. Wabash is an '
        f'all-male college, so women’s sports have no Wabash side to compare with. Left out: {esc(not_included)} '
        f'Together the sports above add up to {t["games_played"]:,} games so far'
        + (f' ({esc(unit_note(sports))}).</p>' if unit_note(sports) else '.</p>'),

        '<h3>How the two schools’ records are combined</h3>',
        '<p>Each school keeps its own list of these games, and the two lists are not always identical, so the '
        'site compares them game by game instead of trusting either one alone.</p>',
        '<ul>',
        '<li><strong>Same date and same score:</strong> the same game. Most games match this way.</li>',
        '<li><strong>Doubleheaders:</strong> two games on one date are paired up by score first, then in '
        'the order each school lists them.</li>',
        f'<li><strong>Small date differences and typos:</strong> a game with the same score listed up to '
        f'{esc(days(merge.MAX_DATE_GAP_DAYS))} apart is treated as one game, and so is one whose date has a single '
        'obvious slip (a digit wrong in the day, the month off by one or the year off by one).</li>',
        f'<li><strong>Only the year is known:</strong> some old games have no real date: a school lists them '
        f'on a placeholder such as {esc(placeholder_range())}, or on a date in a month the sport is not played. '
        f'Games with no recorded date right now: {n["dates_not_recorded"]:,}. They are shown with their '
        'season and “date not recorded”, matched by season and score, and never counted as the most '
        'recent game.</li>',
        f'<li><strong>Listed by one school only:</strong> a game that only one school lists still counts, and '
        f'is marked “Wabash record only” or “DePauw record only”. Right now both schools list {both_listed:,} '
        f'games and only one school lists {one_school:,} ({n["wabash_only"]:,} Wabash only, '
        f'{n["depauw_only"]:,} DePauw only).</li>',
        '</ul>',
        '<p>The site would rather leave a doubtful pair as two separate one-school games, which is visible '
        'and can be checked, than quietly merge two real games into one.</p>',

        *swimming_lines(sports),

        '<h3>Disputed games</h3>',
        f'<p>Sometimes the schools disagree on a score or even on who won. Disputed games right now: '
        f'{n["disputed"]:,}. In those cases DePauw’s version counts in the totals, so the totals come '
        'from one version and are repeatable. That is a convention, not a judgement that DePauw is right: '
        'every disputed game shows both versions, each labelled with whose record it is. '
        f'Games the two schools list on different dates are flagged as well ({n["date_differs"]:,} right '
        'now).</p>',

        '<h3>Rulings</h3>',
        f'<p>When the automatic rules cannot decide, a person checks the box scores and records a ruling, '
        f'with a reason. Rulings made so far: {same + diff + days_of_one:,} ({same:,} saying two entries '
        f'are the same game, {diff:,} saying they are different games'
        + (f', {days_of_one:,} saying several entries are days of one meet' if days_of_one else '')
        + f'). They are public: '
        f'<a href="{esc(overrides_url)}">data/overrides.json</a> on GitHub.</p>',

        '<h3>How often it updates</h3>',
        f'<p>The site checks both schools’ pages twice a day, and every {frequent_minutes()} minutes while a '
        'DePauw vs. Wabash game is being played. “Last checked” at the bottom of the home page is the last time '
        'the site reached the schools’ pages. “Data last changed” is the last time a result actually changed, '
        'which can be much earlier, because nothing changes between games. Checks run on GitHub’s servers '
        'and GitHub can start a scheduled run late, so a new result may take a while to appear.</p>',

        '<h3>Corrections</h3>',
        f'<p>If something looks wrong, use the “Report a data error” link on any sport card or in the footer. '
        'Changes to old games are held for review before they appear: if a school edits a result from a past season, '
        'the site keeps showing the old version until a person reviews the change'
        + (f' ({kept:,} rejected so far)' if kept else '')
        + '. Results from the current season update as soon as the school’s page does.</p>',

        '<h3>Full technical details</h3>',
        f'<p>The exact matching rules, the numbers behind them and how to change them are written up in the '
        f'<a href="{esc(repo_url)}#readme">README on GitHub</a>.</p>',
        '</section>',
    ]
    return out
