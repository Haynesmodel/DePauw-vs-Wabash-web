# DePauw vs. Wabash

All-time head-to-head records between DePauw University and Wabash College in every men's sport where the two schools play each other head to head:

| Sport | Source page |
|---|---|
| Football | [depauwtigers.com](https://depauwtigers.com/sports/football/opponent-history/wabash/215) |
| Men's basketball | [depauwtigers.com](https://depauwtigers.com/sports/mens-basketball/opponent-history/wabash/215) |
| Baseball | [depauwtigers.com](https://depauwtigers.com/sports/baseball/opponent-history/wabash/215) |
| Men's soccer | [depauwtigers.com](https://depauwtigers.com/sports/mens-soccer/opponent-history/wabash/215) |
| Men's lacrosse | [depauwtigers.com](https://depauwtigers.com/sports/mens-lacrosse/opponent-history/wabash/215) |
| Men's tennis | [depauwtigers.com](https://depauwtigers.com/sports/mens-tennis/opponent-history/wabash/215) |

Cross country, track and field, swimming and diving, and golf are left out because they are multi-team events rather than head-to-head games.

**Live site: https://depauwvswabash.com/**

Unofficial fan site, not affiliated with DePauw University or Wabash College. Only men's sports are compared because Wabash is an all-male college.

## What the site shows

- **All sports combined** and a card per sport: record, current streak, records since, total points/goals/runs, most recent game, and every game (newest first, with box-score links).
- **Last checked.** The footer shows when the data last changed and when the scraper last reached the source pages, both in Eastern time, so you can tell the twice-daily job is still running.
- **Next meeting.** The soonest upcoming game across all sports sits near the top, and each card shows its sport's next meeting (time or "TBA", postponed games marked, "Result pending" when a played game is not on the history page yet). In the off-season there is simply nothing to show.
- **Monon Bell.** The football card has a Monon Bell block: the record in games from the 1932 season on, who holds the Bell and since when (a tie leaves the Bell where it was, and the run says how many wins and ties it holds), and a short history with a link to [Wikipedia](https://en.wikipedia.org/wiki/Monon_Bell).
- **Fun facts** on each card, calculated from the games: biggest win and longest win streak for each school, one-score games (8 points in football, 3 in basketball, 1 run, goal or match elsewhere), the highest-scoring game, and overtime or extra-inning games. Sports that meet more than once a year (at least one season in five with two or more games) also get a season-by-season list. A fact that makes no sense for a sport is left out; ties never count as wins.
- **Direct links.** Each card has an id from its key in `sources.json` (`#football`, `#mens-basketball`, ...), plus `#monon-bell` and `#next-meeting`, and each heading is itself the link to its section.
- **Download the data.** `data/series.json` (the data file as-is) and `games.csv` (one row per game: sport, date, season, location, site, DePauw score, Wabash score, result, note, box score link) are published with the site and linked in the footer.
- **Report a data error.** Each card and the footer link to a GitHub issue form (`.github/ISSUE_TEMPLATE/data-correction.yml`) asking for the sport, game date, what is wrong and a link to the correct result. The issues are public, so the form asks for nothing personal.
- **Link previews.** Texting or sharing the link shows a card with the current totals and the Monon Bell holder (see "Preview image" below).

Every number on the page comes from the scraped data or is calculated from it.

## How the data updates

```
depauwtigers.com/sports/<sport>/opponent-history/wabash/215      depauwtigers.com/sports/<sport>/schedule
        │  (fetched twice a day by GitHub Actions)                       │  (same run)
        ▼                                                                ▼
scraper/scrape.py ── parses every game row and checks it       scraper/upcoming.py ── finds the Wabash games not played yet
        │            against the page's own summary                      │            (a problem here only logs a warning)
        ▼                                                                ▼
data/series.json ── committed only when the games change       data/upcoming.json ── committed only when the schedule changes
        └──────────────────────────┬─────────────────────────────────────┘
                                   ▼
scraper/render.py ── builds the static site in site/ and deploys it to GitHub Pages
```

A sport's history is accepted only when its parsed wins, losses, ties, home/away records and current streak match the source page's summary, the page is for the right opponent, and the game count has not shrunk. Doubleheaders count as two games. If any check fails, that sport keeps its last good data and the run turns red. Requests identify the project in the User-Agent and are spaced a few seconds apart.

The schedule pages are separate: the yearless URL (`/sports/<sport>/schedule`) always serves the current season, so nothing needs editing each year. Wabash games are found by DePauw's opponent id (215). If a schedule page fails to load or parse, the scraper logs a warning, keeps that sport's last good upcoming games, and the run stays green, because the records never depend on it.

"Last checked" is the time of the last live scrape that reached at least one sport. It is written to an uncommitted `.checked-at` file and read by the render step in the same workflow run, so `data/series.json` still changes only when games change. If every sport fails, or the file is missing (for example in a pull request check), the page leaves "Last checked" off instead of showing the build time. The workflow scrapes on every run (schedule, manual and push), so every deploy carries a fresh check.

The site is plain HTML and CSS with no JavaScript.

## Preview image and icons

`scraper/images.py` draws `og-image.png` (1200x630, the current totals and Monon Bell holder), `apple-touch-icon.png`, `favicon-32.png` and the manifest icons at every build, with Pillow and the bundled Barlow Condensed font (`static/fonts/`, SIL Open Font License, license included), so the result is the same on a laptop and in GitHub Actions. Pillow is pinned to an exact version in `requirements.txt` for that reason. The image URL in the page carries a `?v=` value built from the totals and holder, so chat apps fetch the new picture when the numbers change. No school logos, wordmarks, seals or mascot art are used.

After the first deploy of a change to the preview, test it by texting yourself the link. iMessage caches previews, so use a URL like `https://depauwvswabash.com/?v=1` the first time.

## Run it locally

```bash
pip install -r requirements.txt
python -m pytest -q tests            # scraper and renderer tests (use saved page markup, no network)
python scraper/scrape.py --dry-run   # fetch live pages and report, without writing
python scraper/scrape.py             # fetch and update data/ (and record the check time)
python scraper/render.py             # build the site into site/
python -m http.server 8000 -d site   # preview at http://localhost:8000
```

`site/` is build output and is not committed.

## Adding a sport

Add an entry to `scraper/sources.json`. DePauw's opponent id for Wabash is `215` on every sport, so the history path is `/sports/<sport-slug>/opponent-history/wabash/215` (for example `mens-basketball`, `baseball`, `mens-soccer`) and the schedule path is `/sports/<sport-slug>/schedule`. Run `python scraper/scrape.py --dry-run` to confirm both parse and validate. The page picks the new sport up automatically, in the order the sports are listed in `sources.json`. Only add head-to-head sports. Each sport's total (points, goals, runs) takes its label from the source page; add `"total_label"` to the entry to override it. For the one-score fun fact, add the sport's margin to `ONE_SCORE` in `scraper/facts.py` (a sport that isn't listed just gets no one-score line).

## Data format

`data/series.json` holds `updated_at`, overall `totals`, and one entry per sport with its record, total points/goals/runs (`points`, labelled by `total_label`), and every game (`date`, `location`, `site`, `result`, `depauw`, `wabash`, `note`, `boxscore`). Results and locations are from DePauw's point of view. Football's neutral-site games (1916 to 1922, Indianapolis) are why its home and away records don't add up to the total.

`data/upcoming.json` holds, per sport, the schedule URL and the Wabash games not yet played (`date`, `time`, `time_note`, `location`, `site`, `status`, `doubleheader`). It has no timestamp, so it changes only when the schedule does.

## License

- The code (the scraper, renderer, tests and workflows) is under the MIT License; see [LICENSE](LICENSE).
- The bundled Barlow Condensed font in `static/fonts/` stays under the SIL Open Font License, with its license file (`static/fonts/OFL.txt`) alongside it.
- The site's written text and images are © Jackson Mote and aren't covered by the MIT License.
- Game results are facts drawn from depauwtigers.com. They belong to no one, and the site claims no ownership of them. Don't use the school names or marks to suggest any affiliation.
