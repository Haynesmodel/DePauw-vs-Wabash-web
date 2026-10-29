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
- **Both schools' records, merged.** Each card says where its record comes from ("Combined from DePauw and Wabash records: 140 games listed by both, 174 by Wabash only, 1 by DePauw only, 0 disputed", or "DePauw and Wabash records agree"). In the game list, a game only one school lists is marked "Wabash record only" or "DePauw record only". When the schools disagree on a score or winner, DePauw's version is the one counted and the game shows both, each labelled with whose record it is and in DePauw-Wabash order ("DePauw's record (DePauw-Wabash): 12-5 · Wabash's record (DePauw-Wabash): 11-5"). Games with no usable date (Wabash's oldest games sit on placeholder dates, and a date in a month the sport is not played in is treated the same way) show their season or year and "date not recorded", are listed first within their season, and never count as the "most recent" game. The 1954 basketball tie is footnoted because both schools list it.
- **Last checked.** The footer shows when the data last changed and when the scraper last reached the source pages, both in Eastern time, so you can tell the twice-daily job is still running.
- **Next meeting.** The soonest upcoming game across all sports sits near the top, and each card shows its sport's next meeting (time or "TBA", postponed games marked, "Result pending" when a played game is not on the history page yet). Both schools' schedule pages are read; a game only Wabash's schedule lists is shown and says so. Several games on one date (a doubleheader) show as one meeting with every start time ("Doubleheader · 12:00 PM and 3:30 PM"; a game without a time says TBA). In the off-season there is simply nothing to show.
- **Game day.** On a day DePauw plays Wabash in any sport, a banner at the very top says so: "Game day: Football vs. Wabash today, 1:07 PM · Scheumann Stadium, Muncie, Ind." until the start, "... is underway or just finished" after it, and "Final: DePauw 41, Wabash 20" (winner first, linking to the sport's card, with who holds the Monon Bell for football) once the result is in. Two sports on one day share one banner. The link preview card gets a small "Game day" or "Final" label while the banner shows. The banner is plain HTML written at each deploy and is gone at the first deploy after game day.
- **Monon Bell.** The football card has a Monon Bell block: the record in games from the 1932 season on, who holds the Bell and since when (a tie leaves the Bell where it was, and the run says how many wins and ties it holds), and a short history with a link to [Wikipedia](https://en.wikipedia.org/wiki/Monon_Bell).
- **Fun facts** on each card, calculated from the games: biggest win and longest win streak for each school (a record several games share reads like "DePauw 9, Wabash 0 · by 9 matches (36 times, most recently Apr 24, 2026)"), one-score games (8 points in football, 3 in basketball, 1 run, goal or match elsewhere), the highest-scoring game, and overtime or extra-inning games. Sports that meet more than once a year (at least one season in five with two or more games) also get a season-by-season list. A fact that makes no sense for a sport is left out; ties never count as wins.
- **Direct links.** Each card has an id from its key in `sources.json` (`#football`, `#mens-basketball`, ...), plus `#monon-bell` and `#next-meeting`, and each heading is itself the link to its section.
- **Download the data.** `data/series.json` (the merged data file as-is) and `games.csv` (one row per game: sport, date, season, location, site, DePauw score, Wabash score, result, note, box score link, plus which record it comes from, whether its date is recorded, whether the schools disagree on the score or the date, and Wabash's date and both schools' scores, in DePauw-Wabash order, when they differ) are published with the site and linked in the footer.
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
                                                                   (a game that just finished stays until the history lists it)

        └── series.json and upcoming.json ──► scraper/render.py ── builds the static site in site/ and deploys it to GitHub Pages
```

Each school's page for a sport is accepted only when its parsed wins, losses, ties, home/away records and current streak match that page's own summary, the page is for the right opponent, and its game count has not shrunk against that school's saved copy. Doubleheaders count as two games. If any check fails, that school keeps its last good games for that sport, the merge is redone from the two saved copies, and the run turns red; everything that passed still updates. Requests identify the project in the User-Agent and are spaced a few seconds apart.

**How the two lists are merged** (`scraper/merge.py`). Games are matched per sport, in passes, and a row is never used twice:

0. Rulings in `data/overrides.json` (see below) come first.
1. Same date and same score.
2. A row with no usable date matches a row from the same season with the same score. A date is unusable when it is a placeholder (a Wabash row dated Jan 1 to Jan 3, where Wabash keeps its oldest games) or falls in a month the sport is not played in (`season_months` in `sources.json`, for example basketball in September). The other row's date, if usable, is used; a date the schools list differently is flagged and shown. A row left with no usable date shows only its season or year.
3. Dates within 2 days with the same score: one game, flagged as having different dates.
4. Same date but a different score or result: one disputed game, DePauw's version counted.
5. Dates within 2 days, the same winner and each score within 3 of the other's: one disputed game, also flagged as having different dates.
6. Dates further apart with the same score, only when the dates differ by a single typo: the year off by one, the month off by one with the same day, or one digit wrong in the day. Two games are never merged across seasons in any other way.

Several games on one date pair by score first, then by order on the page. A game left over is one only a school lists; it still counts and says whose record it is from. Each run logs the matched, DePauw-only, Wabash-only, disputed and date-differs counts per sport, a `REVIEW` line for every match made more than 2 days apart, and a `CHECK` line for leftover pairs that look like the same game (same season, and the same score or dates within 5 days) without merging them.

**Rulings** (`data/overrides.json`). When a person has checked two rows and knows they are the same game (or different games), the ruling goes here and is applied before any automatic matching:

```json
{
  "schema_version": 1,
  "sports": {
    "football": {
      "same_game": [
        {"depauw": {"date": "1891-11-21", "score": "1-0"},
         "wabash": {"date": "1891-11-02", "score": "1-0"},
         "reason": "same 1-0 win; checked the box score"}
      ],
      "different_games": []
    }
  }
}
```

Dates are as each school's page lists them, and scores are always DePauw-Wabash (Wabash's page is already flipped). A `same_game` pair becomes one game even when the dates or scores differ (flagged accordingly); a `different_games` pair is never matched by any pass. Every ruling must still find the rows it names: if a source page changes and a ruling no longer finds both of its rows, the merge for that sport fails (that sport keeps its last good data and the run turns red) instead of the ruling silently stopping. A malformed file stops the run before anything is written.

### Why the merge works this way

The two pages are two independent hand-kept records of the same games, so the merge has to decide, for every row, "is this the same game as a row on the other page?" There is no shared game id. The rules exist to answer that question without quietly inventing or losing a game.

**Principles**

1. **Both mistakes change the record.** Merging two real games into one drops a game from the totals; leaving one game as two adds a game. The rules merge only on strong evidence. Anything doubtful stays as two games marked "Wabash record only" / "DePauw record only", which is visible and checkable, instead of a silent merge.
2. **Nothing is hidden.** Every disagreement (score, winner, date, one-school game) is flagged on the page and in `games.csv`, and every match made on weaker evidence is logged by the scraper (`REVIEW`).
3. **People decide the hard cases, in writing.** A judgement call becomes a ruling in `data/overrides.json` with a reason, so it is repeatable and reviewable instead of buried in code.
4. **Each page must first be right about itself.** A page is accepted only when its games add up to its own summary. Merging never loosens that check, and one page failing never blocks the other.
5. **The merge is a pure function** of the two saved lists plus the rulings. `data/series.json` can always be rebuilt from `data/depauw.json`, `data/wabash.json` and `data/overrides.json`, and a test checks that the committed files agree.

**Why each pass is there**

| Pass | Why it exists | What it risks |
|---|---|---|
| 0. Rulings | A person checked and knows. Beats every automatic rule. | A ruling that goes stale. That is why a ruling that can't find both its rows fails the run. |
| 1. Same date and score | The common case: both schools record the game identically. | Essentially none. |
| 2. No usable date: season and score | Wabash lists its oldest games on placeholder dates (Jan 1 to Jan 3), and some dates fall in a month the sport is never played, so the date carries no information. Season plus score is the best evidence left. | Two different games in one season with the same score would be merged. The per-sport counts and the logs make that visible. |
| 3. Within 2 days, same score | Schools can differ by a day or two on the same game. An identical score that close together is treated as one game. | Two real games 1 to 2 days apart with identical scores. |
| 4. Same date, different score | The same day is strong evidence of one game; the schools simply disagree on the result. | A doubleheader with no matching score on either side. Doubleheaders pair by score first, so this only happens when nothing matches. |
| 5. Within 2 days, same winner, scores each within 3 | A game with a slightly different date and a slightly different score is treated as one disputed game. The same-winner and small-difference limits keep clearly different games apart. | A different game 1 to 2 days later with the same winner and a similar score. |
| 6. Further apart, same score, single-field date typo | Date typos tend to be one slip: the year off by one, the month off by one, or one wrong digit in the day. Requiring exactly one such slip plus an identical score keeps this from being a catch-all. | Two games with the same score a month or a year apart. Every such match is logged for a person to confirm, and the confirmed ones are pinned as rulings. |

Games more than 2 days apart that match no typo pattern are never merged automatically, even with the same score. They show as two one-school games and can be joined with a ruling once someone checks a box score.

**The numbers are judgement calls, not measurements.** They were chosen to be wide enough for ordinary record-keeping drift and narrow enough that two genuinely different games rarely qualify. Changing one is allowed, but it affects every sport and season, so follow the steps below.

- `MAX_DATE_GAP_DAYS = 2`: how far apart two dates may be and still count as the same game when the score also agrees.
- `SCORE_TOLERANCE = 3` (points, goals or runs, per side): only used together with "same winner" and "within 2 days".
- `PLACEHOLDER_DAYS` (Jan 1 to Jan 3): the dates Wabash's page uses for games it has no real date for.
- `NEAR_MISS_DAYS = 5`: only for the `CHECK` log. It lists leftover one-school pairs worth a human look and never merges anything.
- `season_months` (in `sources.json`): the months a sport is actually played. A date outside them is treated as unknown rather than believed.

**Why DePauw's version wins a dispute.** This is a convention, not a finding that DePauw is right. The totals must come from one version so they are repeatable, and the other version is always shown beside it ("DePauw's record (DePauw-Wabash): 12-5 · Wabash's record (DePauw-Wabash): 11-5"). In the current data (12 disputed scores) it never changes who won. If a dispute ever would, check the box score before relying on either version.

**Why undated games are handled separately.** A made-up date would corrupt "most recent game", streaks and the season list. A game with no usable date keeps `date_known: false`, shows only its season or year plus "date not recorded", sorts first within its season, and is never used for a dated fact.

### Reading and adjusting the logic

**How to explain any one game.** Look it up in `data/series.json` (or `games.csv`):

- `source: both` and no flags: both schools list it the same way.
- `source: both` with `date_differs` (and `wabash_date`): the same game, listed on different dates.
- `disputed` (and `wabash_version`): the same game, listed with different scores or winners.
- `source: wabash` or `depauw`: only that school lists it, even after matching and rulings.
- `date_known: false`: no usable date; only the season is shown.

To see why a pair was matched, run `python scraper/scrape.py --dry-run` and read the `REVIEW` lines (matches made more than 2 days apart, with the kind: a typo kind or `ruling`) and the `CHECK` lines (look-alike leftovers that were not merged).

**When a school fixes its page.** The next scrape reads the corrected page and the merge changes by itself (a disputed game becomes agreed, a one-school game becomes matched). If a ruling named a row that changed, the run goes red with `overrides.json ... no longer finds ...`: check both pages, then update the ruling's date or score, or delete it if the pages now agree.

**When you decide a pair is the same (or different) game.** Check a box score or the schools' pages, add a `same_game` or `different_games` ruling with a reason (format above), and run `python scraper/scrape.py --dry-run` to see the new counts. Prefer a ruling over changing a rule, because a rule change affects every sport and season.

**When you want to change a rule or number.** They all live in `scraper/merge.py` (the passes, `MAX_DATE_GAP_DAYS`, `SCORE_TOLERANCE`, `PLACEHOLDER_DAYS`, `NEAR_MISS_DAYS`) and `season_months` in `scraper/sources.json`. Change one, then:

1. Run the tests. `tests/test_merge.py` covers the passes, and `tests/test_overrides.py` pins the real-data totals, so a change that moves any sport's record fails loudly.
2. Run `python scraper/scrape.py --dry-run` on the live pages and compare the per-sport counts and `REVIEW` lines with the previous run.
3. Update the pinned totals in `tests/test_overrides.py` only after confirming each changed game is right, never just to make a test pass.
4. Update this section and `CLAUDE.md` to match.

**Worked examples from the real data**

- *Football 1891:* DePauw lists a 1-0 win on 1891-11-21, Wabash on 1891-11-02. Both pages have one 1-0 game that year and 131 games in total, so it is one game. The dates are 19 days apart, beyond the automatic window, so a ruling pins it.
- *Basketball 1962:* DePauw lists 66-69 on 1962-12-10, Wabash on 1962-09-03. September is outside basketball season, so Wabash's date is unusable; a ruling pins it as the same game.
- *Basketball 1928:* DePauw lists 23-22 on 1928-02-14 and Wabash lists 32-30 on 1928-02-29. Neither the date nor the score agrees, so they are two different games, and a `different_games` ruling stops any rule from joining them. Each still counts, as a one-school game.
- *Baseball 1986:* DePauw lists a doubleheader on 1986-03-19 (12-4 and 16-4), Wabash lists both on 1986-03-23. Same scores, 4 days apart, so rulings pin both; with them the merged baseball record equals Wabash's own page.
- *A dispute:* both schools list the same date with different scores (for example 19-27 against 9-27). It is one game, DePauw's score counts, and both are shown.

The schedule pages are separate: the yearless URL (`/sports/<sport>/schedule`) always serves the current season, so nothing needs editing each year. Wabash games are found by the opponent id the site puts on each game (215 on DePauw's site, 4 on Wabash's). A game on both schedules shows as DePauw lists it, and any difference in date, time, site or status is logged as a warning; a game only Wabash lists is shown as Wabash's. If a schedule page fails to load or parse, the scraper logs a warning, keeps that school's last good upcoming games, and the run stays green, because the records never depend on it.

"Last checked" is the time of the last live scrape that reached at least one page. It is written to an uncommitted `.checked-at` file and read by the render step in the same workflow run, so the data files still change only when games change. If every page fails, or the file is missing (for example in a pull request check), the page leaves "Last checked" off instead of showing the build time. The workflow scrapes on every run (schedule, manual and push), so every deploy carries a fresh check.

Locations are shown in one style, AP style ("Ind.", "Ohio", "Ill."), wherever the page shows one, because the two schools write states differently (DePauw "Greencastle, Ind.", Wabash "Greencastle, IN"). This is display only (`scraper/places.py`): the data files and `games.csv` keep each source's own spelling, and a location that does not end in a recognised state is left exactly as it was.

**Game-day mode** (`scraper/gameday.py`, `.github/workflows/update-and-deploy.yml`). Besides the two daily runs, the workflow starts every 30 minutes (at :07 and :37). A first, fast `gate` job reads only the committed `data/upcoming.json` and `data/series.json` with the runner's own Python (nothing is installed) and decides whether a game is being played. On almost every run it says no and the run ends there: no scrape, no commit, no deploy, and "Last checked" does not change. Only runs started by the 30-minute schedule can be skipped; the two daily runs, pushes to `main` and manual runs always run in full.

A game's window, per sport and date:

- It opens at the first game's scheduled start, or at noon Eastern when no game that day has a time.
- It closes when the history pages (either school's) list as many games on that date as the schedule did, or at 3 AM Eastern the next day, whichever comes first. A postponed game opens no window.
- Inside the window the run scrapes, merges, commits data changes and deploys, exactly like a scheduled run.

A schedule page can post the final score before the history page lists the game, and the scraper normally drops a finished game from `data/upcoming.json`. So that the window does not close early, a game dated today or yesterday that disappears from a schedule stays in the file until the history has it (unless the schedule marks it canceled, and never for more than a day).

The banner phases come from the same files: before the start, after the start until the history has the result, and final. The banner shows for the calendar day only (Eastern); it goes away at the first deploy after midnight, the regular 6:19 AM run at the latest, even if the window stays open until 3 AM so the result is still scraped.

The build and deploy jobs each have their own concurrency group (`cancel-in-progress: false`), so a run that is already going is never cancelled, and a no-op frequent run never queues behind or replaces a waiting push or scheduled run. To preview game day locally without waiting, render as if it were another time: `python scraper/render.py --now 2026-11-14T13:30` (Eastern unless the time has an offset). `--now` is for previews and tests only and is never used by the workflow.

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
python scraper/render.py --now 2026-11-14T13:30   # preview game-day mode as if it were this Eastern time
python -m http.server 8000 -d site   # preview at http://localhost:8000
```

`site/` is build output and is not committed.

## Adding a sport

Add an entry to `scraper/sources.json`. DePauw's opponent id for Wabash is `215` on every sport, so the history path is `/sports/<sport-slug>/opponent-history/wabash/215` (for example `mens-basketball`, `baseball`, `mens-soccer`) and the schedule path is `/sports/<sport-slug>/schedule`. Wabash's pages use opponent id `4` and the same layout: `wabash_path` is `/sports/<slug>/opponent-history/depauw-university/4` and `wabash_schedule_path` is `/sports/<slug>/schedule`. Add `season_months` (the months the sport is played, for example `[2, 3, 4, 5]`). Confirm Wabash's slug on its site (men's tennis is `tennis` there, not `mens-tennis`). Run `python scraper/scrape.py --dry-run` to confirm every page parses and validates and to read the merge counts. The page picks the new sport up automatically, in the order the sports are listed in `sources.json`. Only add head-to-head sports. Each sport's total (points, goals, runs) takes its label from the source page; add `"total_label"` to the entry to override it, and `"unit": ["match", "matches"]` if the sport plays something other than games. For the one-score fun fact, add the sport's margin to `ONE_SCORE` in `scraper/facts.py` (a sport that isn't listed just gets no one-score line).

## Data format

`data/series.json` is the merged record the site reads. It holds `updated_at`, overall `totals`, and one entry per sport with its record, total points/goals/runs (`points`, labelled by `total_label`), `sources` (how many games both schools list, only DePauw, only Wabash, disputed, with different dates, and with no recorded date), and every game (`date`, `season`, `location`, `site`, `result`, `depauw`, `wabash`, `note`, `boxscore`). Games are stored oldest first, and games with no usable date come first within their season, in the order the school's page listed them. Each game also has a `source` (`both`, `depauw` or `wabash`), and, only when they apply, `date_known: false` (the date was a placeholder or fell outside the sport's season, so `date` must not be shown; show the `season`), `disputed` with `wabash_version` (Wabash's result and scores), and `date_differs` with `wabash_date` (or `depauw_date`, when DePauw's date was the unusable one). A game can be both disputed and have different dates. Results and locations are from DePauw's point of view. Football's neutral-site games (1916 to 1922, Indianapolis) are why its home and away records don't add up to the total.

`data/depauw.json` and `data/wabash.json` hold each school's games for each sport as they were read, both in DePauw's point of view (Wabash's page is flipped: wins and losses, scores, and home and away swap). `series.json` is always the merge of these two files, so a run can re-merge without fetching.

`data/overrides.json` holds the rulings described above, each with a short reason.

`data/upcoming.json` holds, per sport, the two schedule URLs and the Wabash games not yet played (`date`, `time`, `time_note`, `location`, `site`, `status`, `doubleheader`, `source`). It has no timestamp, so it changes only when the schedule does.

## License

- The code (the scraper, renderer, tests and workflows) is under the MIT License; see [LICENSE](LICENSE).
- The bundled Barlow Condensed font in `static/fonts/` stays under the SIL Open Font License, with its license file (`static/fonts/OFL.txt`) alongside it.
- The site's written text and images are © Jackson Mote and aren't covered by the MIT License.
- Game results are facts drawn from depauwtigers.com and sports.wabash.edu. They belong to no one, and the site claims no ownership of them. The DePauw University and Wabash College names belong to their respective schools; this project is not affiliated with or endorsed by either.
