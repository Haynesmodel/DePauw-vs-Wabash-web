# DePauw vs. Wabash

All-time head-to-head records between DePauw University and Wabash College in every men's sport where the two schools play each other head to head. Each sport's record combines both schools' own history pages, so it is the most complete history either school has:

| Sport | DePauw's page | Wabash's page |
|---|---|---|
| Football | [depauwtigers.com](https://depauwtigers.com/sports/football/opponent-history/wabash/215) | [sports.wabash.edu](https://sports.wabash.edu/sports/football/opponent-history/depauw-university/4) |
| Men's basketball | [depauwtigers.com](https://depauwtigers.com/sports/mens-basketball/opponent-history/wabash/215) | [sports.wabash.edu](https://sports.wabash.edu/sports/mens-basketball/opponent-history/depauw-university/4) |
| Baseball | [depauwtigers.com](https://depauwtigers.com/sports/baseball/opponent-history/wabash/215) | [sports.wabash.edu](https://sports.wabash.edu/sports/baseball/opponent-history/depauw-university/4) |
| Men's soccer | [depauwtigers.com](https://depauwtigers.com/sports/mens-soccer/opponent-history/wabash/215) | [sports.wabash.edu](https://sports.wabash.edu/sports/mens-soccer/opponent-history/depauw-university/4) |
| Men's lacrosse | [depauwtigers.com](https://depauwtigers.com/sports/mens-lacrosse/opponent-history/wabash/215) | [sports.wabash.edu](https://sports.wabash.edu/sports/mens-lacrosse/opponent-history/depauw-university/4) |
| Men's tennis | [depauwtigers.com](https://depauwtigers.com/sports/mens-tennis/opponent-history/wabash/215) | [sports.wabash.edu](https://sports.wabash.edu/sports/tennis/opponent-history/depauw-university/4) |

Cross country, track and field, swimming and diving, and golf are left out because they are multi-team events rather than head-to-head games.

**Live site: https://depauwvswabash.com/**

Unofficial fan site, not affiliated with DePauw University or Wabash College. Only men's sports are compared because Wabash is an all-male college.

## What the site shows

- **All sports combined** and a card per sport: record, current streak, records since, total points/goals/runs, most recent game, and every game (newest first, with box-score links). Tennis counts matches rather than games.
- **Both schools' records, merged.** Each card says where its record comes from ("Combined from DePauw and Wabash records: 140 games listed by both, 174 by Wabash only, 1 by DePauw only, 0 disputed", or "DePauw and Wabash records agree"). In the game list, a game only one school lists is marked "Wabash record only" or "DePauw record only". When the schools disagree on a score or winner, DePauw's version is the one counted and the game shows both ("DePauw 5, Wabash 3 (Wabash's record: Wabash 5, DePauw 3)"). Wabash's oldest games have no real date on its page, so they show the year and "date not recorded". The 1954 basketball tie is footnoted because both schools list it.
- **Last checked.** The footer shows when the data last changed and when the scraper last reached the source pages, both in Eastern time, so you can tell the twice-daily job is still running.
- **Next meeting.** The soonest upcoming game across all sports sits near the top, and each card shows its sport's next meeting (time or "TBA", postponed games marked, "Result pending" when a played game is not on the history page yet). Both schools' schedule pages are read; a game only Wabash's schedule lists is shown and says so. In the off-season there is simply nothing to show.
- **Monon Bell.** The football card has a Monon Bell block: the record in games from the 1932 season on, who holds the Bell and since when (a tie leaves the Bell where it was, and the run says how many wins and ties it holds), and a short history with a link to [Wikipedia](https://en.wikipedia.org/wiki/Monon_Bell).
- **Fun facts** on each card, calculated from the games: biggest win and longest win streak for each school, one-score games (8 points in football, 3 in basketball, 1 run, goal or match elsewhere), the highest-scoring game, and overtime or extra-inning games. Sports that meet more than once a year (at least one season in five with two or more games) also get a season-by-season list. A fact that makes no sense for a sport is left out; ties never count as wins.
- **Direct links.** Each card has an id from its key in `sources.json` (`#football`, `#mens-basketball`, ...), plus `#monon-bell` and `#next-meeting`, and each heading is itself the link to its section.
- **Download the data.** `data/series.json` (the merged data file as-is) and `games.csv` (one row per game: sport, date, season, location, site, DePauw score, Wabash score, result, note, box score link, plus which record it comes from, whether its date is recorded, whether the schools disagree on the score or the date, and Wabash's date and score when they differ) are published with the site and linked in the footer.
- **Report a data error.** Each card and the footer link to a GitHub issue form (`.github/ISSUE_TEMPLATE/data-correction.yml`) asking for the sport, game date, which school's record looks wrong (DePauw's, Wabash's, both, not sure), what is wrong and a link to the correct result. The issues are public, so the form asks for nothing personal.
- **Link previews.** Texting or sharing the link shows a card with the current totals and the Monon Bell holder (see "Preview image" below).

Every number on the page comes from the scraped data or is calculated from it.

## How the data updates

```
depauwtigers.com/.../opponent-history/wabash/215          sports.wabash.edu/.../opponent-history/depauw-university/4
        │  (fetched twice a day by GitHub Actions)                 │
        ▼                                                          ▼
scraper/scrape.py ── parses every game row and checks each page against its own summary
        │            (Wabash's games are flipped to DePauw's point of view)
        ▼
data/depauw.json  data/wabash.json ── each school's games as read, committed only when they change
        │
        ▼
scraper/merge.py ── matches the two lists game by game
        ▼
data/series.json ── the merged record the site reads, committed only when it changes

both schools' /sports/<sport>/schedule pages ──► scraper/upcoming.py ──► data/upcoming.json (a problem here only logs a warning)

        └── series.json and upcoming.json ──► scraper/render.py ── builds the static site in site/ and deploys it to GitHub Pages
```

Each school's page for a sport is accepted only when its parsed wins, losses, ties, home/away records and current streak match that page's own summary, the page is for the right opponent, and its game count has not shrunk against that school's saved copy. Doubleheaders count as two games. If any check fails, that school keeps its last good games for that sport, the merge is redone from the two saved copies, and the run turns red; everything that passed still updates. Requests identify the project in the User-Agent and are spaced a few seconds apart.

**How the two lists are merged** (`scraper/merge.py`). Games are matched per sport, in passes, and a row is never used twice:

1. Same date and same score.
2. A Wabash row dated Jan 1 to Jan 3 (Wabash's oldest games sit on placeholder dates) matches a DePauw row from the same season with the same score; DePauw's date is used. A placeholder row with no match is kept with its date unknown and shows only its year.
3. Dates within 2 days with the same score: one game, flagged as having different dates.
4. Same date but a different score or result: one disputed game. DePauw's version is counted and Wabash's is kept to show beside it.
5. Same season and score on dates further apart, when both schools have the same number of such games left: one game, flagged as having different dates. (Without this, a mistyped date makes one game count twice.)

Several games on one date pair by score first, then by order on the page. A game left over is one only a school lists; it still counts and says whose record it is from. Each run logs the matched, DePauw-only, Wabash-only, disputed and date-differs counts per sport, and lists leftover pairs that look like the same game (`CHECK` lines) without merging them.

The schedule pages are separate: the yearless URL (`/sports/<sport>/schedule`) always serves the current season, so nothing needs editing each year. Wabash games are found by the opponent id the site puts on each game (215 on DePauw's site, 4 on Wabash's). A game on both schedules shows as DePauw lists it, and any difference in date, time, site or status is logged as a warning; a game only Wabash lists is shown as Wabash's. If a schedule page fails to load or parse, the scraper logs a warning, keeps that school's last good upcoming games, and the run stays green, because the records never depend on it.

"Last checked" is the time of the last live scrape that reached at least one page. It is written to an uncommitted `.checked-at` file and read by the render step in the same workflow run, so the data files still change only when games change. If every page fails, or the file is missing (for example in a pull request check), the page leaves "Last checked" off instead of showing the build time. The workflow scrapes on every run (schedule, manual and push), so every deploy carries a fresh check.

The site is plain HTML and CSS with no JavaScript.

## Preview image and icons

`scraper/images.py` draws `og-image.png` (1200x630, the current totals and Monon Bell holder), `apple-touch-icon.png`, `favicon-32.png` and the manifest icons at every build, with Pillow and the bundled Barlow Condensed font (`static/fonts/`, SIL Open Font License, license included), so the result is the same on a laptop and in GitHub Actions. Pillow is pinned to an exact version in `requirements.txt` for that reason. The image URL in the page carries a `?v=` value built from the totals and holder, so chat apps fetch the new picture when the numbers change. No school logos, wordmarks, seals or mascot art are used.

After the first deploy of a change to the preview, test it by texting yourself the link. iMessage caches previews, so use a URL like `https://depauwvswabash.com/?v=1` the first time.

## Run it locally

```bash
pip install -r requirements.txt
python -m pytest -q tests            # scraper and renderer tests (use saved page markup, no network)
python scraper/scrape.py --dry-run   # fetch both schools' live pages and report, without writing
python scraper/scrape.py             # fetch and update data/ (and record the check time)
python scraper/render.py             # build the site into site/
python -m http.server 8000 -d site   # preview at http://localhost:8000
```

`site/` is build output and is not committed.

## Adding a sport

Add an entry to `scraper/sources.json`. DePauw's opponent id for Wabash is `215` on every sport, so the history path is `/sports/<sport-slug>/opponent-history/wabash/215` (for example `mens-basketball`, `baseball`, `mens-soccer`) and the schedule path is `/sports/<sport-slug>/schedule`. Wabash's pages use opponent id `4` and the same layout: `wabash_path` is `/sports/<slug>/opponent-history/depauw-university/4` and `wabash_schedule_path` is `/sports/<slug>/schedule`. Confirm Wabash's slug on its site (men's tennis is `tennis` there, not `mens-tennis`). Run `python scraper/scrape.py --dry-run` to confirm every page parses and validates and to read the merge counts. The page picks the new sport up automatically, in the order the sports are listed in `sources.json`. Only add head-to-head sports. Each sport's total (points, goals, runs) takes its label from the source page; add `"total_label"` to the entry to override it, and `"unit": ["match", "matches"]` if the sport plays something other than games. For the one-score fun fact, add the sport's margin to `ONE_SCORE` in `scraper/facts.py` (a sport that isn't listed just gets no one-score line).

## Data format

`data/series.json` is the merged record the site reads. It holds `updated_at`, overall `totals`, and one entry per sport with its record, total points/goals/runs (`points`, labelled by `total_label`), `sources` (how many games both schools list, only DePauw, only Wabash, disputed, with different dates, and with no recorded date), and every game (`date`, `season`, `location`, `site`, `result`, `depauw`, `wabash`, `note`, `boxscore`). Each game also has a `source` (`both`, `depauw` or `wabash`), and, only when they apply, `date_known: false` (the date was a placeholder, so `date` holds Jan 1 of the year and must not be shown), `disputed` with `wabash_version` (Wabash's result and scores), and `date_differs` with `wabash_date`. Results and locations are from DePauw's point of view. Football's neutral-site games (1916 to 1922, Indianapolis) are why its home and away records don't add up to the total.

`data/depauw.json` and `data/wabash.json` hold each school's games for each sport as they were read, both in DePauw's point of view (Wabash's page is flipped: wins and losses, scores, and home and away swap). `series.json` is always the merge of these two files, so a run can re-merge without fetching.

`data/upcoming.json` holds, per sport, the two schedule URLs and the Wabash games not yet played (`date`, `time`, `time_note`, `location`, `site`, `status`, `doubleheader`, `source`). It has no timestamp, so it changes only when the schedule does.

## License

- The code (the scraper, renderer, tests and workflows) is under the MIT License; see [LICENSE](LICENSE).
- The bundled Barlow Condensed font in `static/fonts/` stays under the SIL Open Font License, with its license file (`static/fonts/OFL.txt`) alongside it.
- The site's written text and images are © Jackson Mote and aren't covered by the MIT License.
- Game results are facts drawn from depauwtigers.com and sports.wabash.edu. They belong to no one, and the site claims no ownership of them. The DePauw University and Wabash College names belong to their respective schools; this project is not affiliated with or endorsed by either.
