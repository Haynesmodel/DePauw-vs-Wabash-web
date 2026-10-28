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

## How the data updates

```
depauwtigers.com/sports/<sport>/opponent-history/wabash/215
        │  (fetched twice a day by GitHub Actions)
        ▼
scraper/scrape.py ── parses every game row and checks it against the page's own summary
        ▼
data/series.json ── committed only when the data changes
        ▼
scraper/render.py ── builds the static page in site/ and deploys it to GitHub Pages
```

A sport is accepted only when its parsed wins, losses, ties, home/away records and current streak match the source page's summary, the page is for the right opponent, and the game count has not shrunk. Doubleheaders count as two games. If any check fails, that sport keeps its last good data and the run turns red. Requests identify the project in the User-Agent and are spaced a few seconds apart.

The site is plain HTML and CSS with no JavaScript. Every number on the page comes from `data/series.json`.

## Run it locally

```bash
pip install -r requirements.txt
python -m pytest -q tests            # scraper and renderer tests (use saved page markup, no network)
python scraper/scrape.py --dry-run   # fetch live pages and report, without writing
python scraper/scrape.py             # fetch and update data/series.json
python scraper/render.py             # build the site into site/
python -m http.server -d site        # preview at http://localhost:8000
```

`site/` is build output and is not committed.

## Adding a sport

Add an entry to `scraper/sources.json`. DePauw's opponent id for Wabash is `215` on every sport, so the path is `/sports/<sport-slug>/opponent-history/wabash/215` (for example `mens-basketball`, `baseball`, `mens-soccer`). Run `python scraper/scrape.py --dry-run` to confirm it parses and validates. The page picks the new sport up automatically, in the order the sports are listed in `sources.json`. Only add head-to-head sports. Each sport's total (points, goals, runs) takes its label from the source page; add `"total_label"` to the entry to override it.

## Data format

`data/series.json` holds `updated_at`, overall `totals`, and one entry per sport with its record, total points/goals/runs (`points`, labelled by `total_label`), and every game (`date`, `location`, `site`, `result`, `depauw`, `wabash`, `note`, `boxscore`). Results and locations are from DePauw's point of view. Football's neutral-site games (1916 to 1922, Indianapolis) are why its home and away records don't add up to the total.
