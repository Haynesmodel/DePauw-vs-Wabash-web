# DePauw vs. Wabash Alumni and Endowment Implementation Plan

**Plan date:** October 29, 2026
**Status:** Implementation authorized; Luna implements, parent independently reviews and tests.
**Measured baseline:** `9802f1fcff4f8a9d25bc40ba7d4d2a0052309d51`, clean `main`, synchronized with `origin/main`.
**Repository:** `/Users/josephhaynes/Documents/Projects/DePauw/DePauw-vs-Wabash-web`
**Delivery:** One GitHub PR against `main`, initially draft, ready only after independent review, exact-head checks and screenshot evidence. No merge or production deployment.
**Primary outcome:** Readers navigate Athletics and Alumni, inspect sourced people behind each alumni count, and compare dated endowment values.

## 1. Executive decision and scope

Keep Athletics at `/` and existing sport fragment URLs. Add `/alumni/` as a static generated page with top-level navigation `Athletics | Alumni`, the existing gold/scarlet comparison style, accessible native disclosure lists, and a separate Endowment section. Reuse Python generation, shared CSS, metadata/security helpers and the existing GitHub Pages workflow. Add no client JavaScript, runtime services or third-party dependencies.

Research all ten agreed categories: Nobel Prize winners, U.S. vice presidents, U.S. senators, U.S. representatives, U.S. state governors, Fortune 500 CEOs, Pulitzer Prize winners, Rhodes Scholars, astronauts who flew in space, and Academy Award winners. Exclude a category from rendered cards and jump links only when both schools have verified zero qualifying people. Count distinct people per school per category. Do not sum unlike achievements into an overall score.

Assumptions: Alumni counts include earned degree holders of any gender, including historical school names, but exclude honorary-only degrees, faculty-only connections, speakers, and attendees who never earned a degree. A person can appear in multiple categories. Endowment uses audited institution-reported endowment amounts, not total assets or donor-restricted funds alone. Compare the same fiscal date and label each institution’s reported scope. The FY2025 statements differ: DePauw total endowment net assets include pledges receivable and perpetual trusts, while Wabash reports pooled endowment net assets. These amounts are not identical market-value bases or cash available for general spending. Show total USD only; per-student and investment-return comparisons are outside this request.

## 2. Current-state evidence and constraints

- `scraper/render.py` generates plain HTML/CSS with no client script. `render_index` is the Athletics home; `render_how` and `render_404` have shared footer conventions.
- `build()` loads athletics JSON, generates pages, then replaces the output directory. Generated `site/` is ignored. Validate new data and render all page strings before deleting existing output.
- `static/styles.css` already has school color tokens, dark mode, win tiles, responsive cards, and focus styling. Extend these rather than replacing branding or fonts. UI/UX skill recommendations are general guidance; established site styling is authoritative for this extension.
- `.github/workflows/checks.yml` runs `python -m pytest -q tests`, `python scraper/render.py`, pinned `html-validate@11.17.0` for three current pages, and Mermaid rendering of README diagrams. Extend HTML validation to Alumni wherever the same gate appears.
- Existing sports data and scraper/merge/snapshot behavior must remain unchanged. Athletics metadata, downloads, direct links, Monon Bell and game-day behavior remain functional.
- GitHub `gh` authentication is available. Local Python 3.14 initially lacks pytest; install existing requirements into ignored `.venv`. CI uses Python 3.12.
- No applicable AGENTS.md found in this checkout/parent project search. Worktree was clean before plan authoring.

## 3. Alternatives

**Adopt:** separate `/alumni/` static page with real navigation links and `aria-current="page"`; allows direct linking, browser back, keyboard access and no JavaScript. Keep the root URL as Athletics to preserve existing links.

**Reject:** client-side tab panels or a new framework. They add state and dependencies to a static site without a necessary benefit. Revisit only for a separately requested interactive application.

**Adopt:** manually maintained, validated JSON with primary-source citations and a dated verification record. Automated web research/scraping at each build is inappropriate for slow-changing, heterogeneous biographical evidence. Builds must remain offline and deterministic for the same inputs/time.

## 4. Requirements and data contracts

### Navigation and presentation

- **FUNC-001:** The home and Alumni headers expose Athletics and Alumni as real links. Exactly the current destination is marked current; secondary pages provide consistent navigation without falsely marking the wrong page.
- **FUNC-002:** `/alumni/` has a unique title, description, canonical URL, OG URL and an Alumni heading. It must not advertise athletic win totals as the Alumni page preview. Reuse existing icon/security metadata; an existing generic image is acceptable only without misleading athletic preview text.
- **FUNC-003:** Each visible category shows its definition, DePauw and Wabash counts calculated from included people, and expandable named lists for each school. Include full name, class/degree year, achievement and relevant award/service year(s), plus clearly labeled clickable school-connection and achievement sources. A source can prove both when explicit.
- **FUNC-004:** A verified 0–0 category has no card or category jump link. A one-sided zero remains visible and explicitly says no qualifying graduates were found in the reviewed sources. All ten category records remain in source data with research/audit evidence, including exclusions. Missing research must not silently become zero.
- **FUNC-005:** Distinct people count once per school/category regardless of awards, terms or companies. Each person may qualify in several categories; no overall Alumni total or overall winner is rendered.
- **FUNC-006:** Endowment is a separate linked section of Alumni, with side-by-side school labels and USD values, common fiscal year/as-of date, reporting basis, source links (PDF page/table where applicable), and a brief plain-language explanation. Use the newest jointly verifiable fiscal year, preferring audited statements or a common NACUBO study. Do not mix a current marketing estimate with an older audited figure. Store integer dollars, format from data, and retain precision/source units in data. No inferred live value or alumni achievement score.
- **FUNC-007:** Explain the counting rules, omissions and verification date on the page. Label curated counts as verified named graduates from reviewed sources, avoiding an unsupported claim of exhaustive all-time coverage. Research should reasonably cover both schools' notable-alumni rosters and category authority lists, not select only one famous example.
- **A11Y-001:** Navigation and disclosure lists work by keyboard with visible focus; native details/summary is preferred. School names appear as text; color alone does not encode school or leader. No duplicate IDs or broken category anchors.
- **A11Y-002:** At 320px and desktop widths, all new content fits the viewport without horizontal document overflow. Long names and citations wrap. Existing light/dark tokens remain readable. Forced-colors mode retains a discernible current navigation item and focus indication.

### Research and integrity

- **DATA-001:** Add `data/alumni.json` (schema version 1) containing verification date, counting methodology, ten stable category IDs/definitions, named people associated with schools/categories, and explicit reviewed-source/audit notes per category/school. The implementer may choose a compact structure but must derive counts from people rather than maintain independent totals.
- **DATA-002:** Each included person has a stable ID, school, earned degree/class year, concise factual achievement, source URLs and qualification year(s) appropriate to the category. Entries must establish both graduation and achievement; document exclusions such as a nominee, a nongraduate, honorary-only degree, subsidiary executive or company chair without CEO service.
- **DATA-003:** Fortune 500 means the U.S. Fortune 500 and a company/year overlapping the person's CEO tenure. A subsidiary CEO, chairman alone, Fortune Global 500 or a company that joined after the tenure does not qualify. Keep explicit qualifying company and ranking year with evidence. Historical list access can require research; do not invent a ranking or call an unresearched school zero.
- **DATA-004:** Pulitzer/Oscar people must be named recipients, not merely employees of a winning organization or cast members. Nobel nominees do not qualify. Astronauts must have flown in space, rather than merely been selected. Governors means U.S. states, not lieutenant governors; senators and representatives mean federal U.S. offices, not state legislatures. Rhodes finalists do not qualify.
- **DATA-005:** Add `data/endowment.json` (or an equally clear subsection of the Alumni file) with schema version, verification date, one common fiscal year/as-of date, valuation basis, and per-school integer USD values, source URLs and page/table notes. Reject mismatched periods, negative/nonfinite/bool amounts, absent school or source, and malformed dates.
- **REL-001:** Validate new files before output deletion; missing, malformed or unsupported-version data must fail the build clearly and preserve existing output. Reject invalid school/category references, duplicate person IDs/memberships, unsafe URLs and missing evidence fields. Escape all rendered text and link attributes. Accept only absolute HTTP(S) source URLs with nonempty hosts.
- **ARCH-001:** No network during rendering/tests, no client script, no new dependency or framework, and no modifications to scraped athletics datasets. Expose an optional build/CLI file override for deterministic malformed/empty data tests if needed; defaults use committed curated files.
- **ARCH-002:** Include Alumni in generated sitemap using the new content verification date, publish the curated JSON for audit/download, and distinguish manually verified Alumni/endowment dates from the automatic athletics scraper's last-check date. Shared footer language must not imply only men are included in Alumni or that its sources/refresh schedule are athletic records.
- **CI-001:** Existing tests and generation pass; generated Alumni HTML passes the existing pinned HTML validator in PR/deploy validation wherever applicable. Preserve existing workflow permissions and deployment triggers.
- **DOC-001:** README documents navigation, eligible people, source maintenance, zero–zero exclusion, new JSON contracts, endowment basis/year, adding/correcting entries, and the same verification commands. Preserve valid Mermaid blocks and update architecture prose only where needed.

Primary research starting points (verify contents rather than trusting names): school notable-alumni pages, https://www.nobelprize.org/, https://bioguide.congress.gov/, https://www.senate.gov/about/officers-staff/vice-presidents.htm, https://www.nga.org/former-governors/, https://www.pulitzer.org/, https://www.rhodeshouse.ox.ac.uk/scholar-network/rhodes-scholar-database/, https://www.nasa.gov/humans-in-space/astronauts/former-astronauts/, https://www.oscars.org/oscars/awards-databases, Fortune historical rankings and corporate biographies. Wabash FY2025 audited statements: https://www.wabash.edu/businessoffice/docs/2025-Wabash-College-Audited-Financial-Statements.pdf (endowment note, not restricted-net-assets note). NACUBO FY2025 study is published and offers common-year institution market values. Parent will independently audit sources and send corrections.

## 5. Code anchors and workstreams

Line numbers refer to the measured baseline and may move after rebasing.

| File / symbol | Change |
|---|---|
| `scraper/render.py:827` — `site_footer` | Add consistent category navigation/footer links and appropriate Alumni source/update context without weakening Athletics footer contracts. |
| `scraper/render.py:857` — `render_index` | Add Athletics/Alumni header navigation; keep root page and sports content. |
| `scraper/render.py:906` — `render_how`, `:939` — `render_404` | Ensure navigation resolves correctly from nested and missing paths. |
| `scraper/render.py:960` — `render_sitemap` | Add Alumni URL with truthful content lastmod. |
| `scraper/render.py:1005` — `build`, `:1052` — `main` | Load/validate/render/publish Alumni and endowment before output replacement; add overrides if needed. |
| `scraper/alumni.py` (new) | Cohesive validation/counting/rendering helpers, keeping biographical concerns out of sports logic. Reuse helpers or pass callbacks without circular imports. |
| `data/alumni.json`, `data/endowment.json` (new) | Sourced curated data and audit notes. |
| `static/styles.css:1`, `:91` | Reuse tokens, header/card/tiles/disclosure patterns; add only navigation/people/endowment rules needed. |
| `tests/test_alumni.py` (new), existing render/footer/link tests | Rule/validation/data coverage and full generated-page integration. |
| `.github/workflows/checks.yml`, matching deploy validation, `README.md` | Extend generated HTML checks and document maintenance. |

Ordered work:

1. **Baseline:** synchronize main, branch `codex/alumni-endowment`, record base SHA, install existing requirements in `.venv`, run existing tests. Any baseline failure must be diagnosed separately.
2. **Research/data:** audit both school rosters and award/office sources; document included/excluded people and category review status. Select and verify common-year endowment values. This is required product content, not placeholder work.
3. **Validation/rendering:** add curated data schemas and validations, derive unique counts and visible categories, generate people/endowment sections with native disclosure and links; test rejection before output mutation.
4. **Integration/style:** add two-category navigation across existing pages and Alumni metadata/sitemap/downloads; extend existing visual patterns, ensure footer dates/scope are truthful; cover integration in tests.
5. **Documentation/CI:** update README and HTML validation paths, run relevant checks, inspect full change, commit and push draft PR with plan/acceptance checklist. Implementer self-reviews with github-review and fixes its findings privately.
6. **Handoff:** stop implementation writes. Send parent branch/PR/head, changed files, criteria coverage, commands/results/logs, unresolved issues, and running processes. Parent independently reviews full change; same Luna agent makes requested fixes. Parent owns final browser verification, screenshot upload/evidence comment, refreshing exact remote head and CI, and readiness.

## 6. Verification and acceptance matrix

| Layer | Required cases and assertions |
|---|---|
| Counting | All ten definitions present; duplicates rejected or uniquely counted; multiple awards/terms/company records don't inflate counts; cross-category appearances allowed; actual zero–zero hidden; asymmetric zero shown; category nav matches visible cards. |
| Curated data | Every included name has graduation and qualifying achievement evidence; both schools reviewed for every category; exact source-year overlap for Fortune CEOs; excluded nongraduates/nominees documented. Parent spot-checks all high-impact and boundary entries and audits known rosters for omissions. |
| Endowment | Same fiscal period and basis, both amounts match cited table, total not restricted subtotal, USD formatting correct, source/page visible; mismatch/missing school/invalid amount rejects. |
| Failure/security | Bad schema, bad school/category, duplicate IDs, missing evidence, invalid dates, unsafe links and malformed JSON fail with actionable message; existing output sentinel survives failure. HTML escapes malicious fixture text/attributes. |
| Generated integration | Build emits `/alumni/index.html`, downloadable curated data, canonical/OG URLs, sitemap entry, working root/nested nav and fragment anchors; no script; athletics values/downloads and Monon Bell unchanged. |
| Browser | Visit root, click Alumni, open category people disclosure, inspect both names and source links, jump to Endowment, navigate back to Athletics, visit how-it-works and 404 navigation. Check keyboard disclosure/focus. |
| Responsive/themes | Desktop ~1440px and mobile 375px plus overflow assertion at 320px; light/dark states; forced colors current/focus discernible; no horizontal page overflow or clipped amounts. |
| CI | Repository pytest suite, generation, pinned HTML validator all pages, existing hosted Checks including README Mermaid pass on exact head; no unrelated diffs. |

Commands (activate `.venv` or use `.venv/bin/python`):

```bash
python -m pytest -q tests
python scraper/render.py --out /tmp/depauw-wabash-alumni-validation
npx --yes html-validate@11.17.0 /tmp/depauw-wabash-alumni-validation/index.html /tmp/depauw-wabash-alumni-validation/404.html /tmp/depauw-wabash-alumni-validation/how-it-works/index.html /tmp/depauw-wabash-alumni-validation/alumni/index.html
git diff --check
```

Parent uses Playwright CLI and local HTTP server against final generated output, stores screenshots/logs outside tracked product sources, visually inspects them, then invokes `/Users/josephhaynes/.codex/skills/github-test-branch/scripts/post_test_evidence.py` to host screenshots on isolated evidence branch and post one PASS/FAIL/BLOCKED comment with the precise SHA. No testing of a different commit is claimed as final-head proof.

## 7. Delivery, rollout, rollback and risks

One PR, scoped to curated data, generator, styles, tests, docs and necessary existing HTML validation paths. Include the plan in the PR (copy the finalized plan to repository docs if useful for durable review). No changes to repository settings, automatic athletics schedules, infrastructure, or production deployment. Once merged by maintainer, the existing main deployment publishes the new page; production smoke-checking is a postmerge maintainer action, not claimed in this task.

Rollback by reverting this PR and letting the existing generator rebuild; no database migration or destructive operation is involved. Preserve all athletics inputs throughout.

Risks: alumni marketing lists mix graduates/attendees and honorary degrees (mitigate by explicit graduation evidence); historical CEO titles and ranking scope differ (require tenure/ranking overlap); award-team claims inflate people counts (named individual recipients only); endowment totals differ by date and accounting scope (same-period common definition and exact cited table); false completeness claims (transparent reviewed-source methodology and audit trail); footer inherits athletics restrictions/dates (explicit Alumni context); slow research on historical archives (continue implementation and available validation, clearly identify only genuine unresolved prerequisites; never invent data to pass).

## 8. Definition of done and checklist

- [ ] Baseline synchronized; no unrelated changes overwritten.
- [ ] All ten categories researched for both schools; included names and exclusions documented.
- [ ] Counts derive from unique qualified people; 0–0 categories hidden; one-sided zero retained.
- [ ] Dated same-year endowment amounts and sources verified.
- [ ] Athletics/Alumni navigation, people lists, endowment, metadata, sitemap and downloads work.
- [ ] Invalid data fails before replacing output; escaping, keyboard and mobile/theme checks pass.
- [ ] Existing athletics functionality and data preserved; docs/CI updated.
- [ ] Luna implementation and self-review complete; parent independent full review has no actionable findings.
- [ ] Parent personally tests exact final commit, verifies screenshots and posts durable PR evidence using github-test-branch.
- [ ] Remote head/checks refreshed, description truthful, worktree clean, PR ready and returned to user; no merge/deploy performed.
