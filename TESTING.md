# Testing

This file lists every function of Commodity Pulse, how each was tested, and the result. The point of this pass was to test what the weekly workflow publishes:

1. The tracked files were copied and the release placeholder filled.
2. The collect job's steps ran on a saved workbook in the Pink Sheet layout (the seed values under a newer release date, since the World Bank site was not reachable): `commodity-pulse collect --out data --xlsx ...`, then `python web/build_pages.py`, then `git add data docs`.
3. Pages publishes `docs/` from the main branch, so that folder was served under `/commodity-pulse/` and opened in headless Chromium at 1280 px (light and dark) and 400 px with touch (light and dark). The shipped seed site and `web/app.html` from `file://` were tested too.

## The publishing bug

The collect job pushed its commit with the Actions token. GitHub does not start a Pages build for a push made with that token (GitHub Docs, "Configuring a publishing source for your GitHub Pages site", troubleshooting note), and this site publishes from a branch. Every weekly data commit would have landed in the repository while the live page kept the old data. The job now asks Pages to rebuild after it pushes (`POST /repos/{repo}/pages/builds`, with `pages: write` on that job only). `tests/test_workflows.py` checks this.

## Numbers checked against independent references

| Check | Reference | Result |
|---|---|---|
| Latest value, month over month, year over year, 12-month z-score, midrank percentile for all 38 series | Python `statistics.stdev` and the README formulas | Equal within 1e-9 |
| Spreads at 2026-09: Brent minus WTI, TTF minus Henry Hub, TTF / Henry Hub, urea / TTF, gold / silver | Hand calculation; README Brent minus WTI 19.9 | Match |
| Rebase | P_t / P_base x 100 | Match |
| Workbook round trip | Seed values written in the Pink Sheet layout and parsed back | Identical series, units, starts and values |

## Function inventory

| # | Area | Function | How it was tested | Result |
|---|---|---|---|---|
| 1 | Workflow | Collect on a workbook | Exit 0; meta release 2026-11-04, latest 2026-09, seed flag gone | Pass |
| 2 | Workflow | Rebuild pages and commit only on change | `docs/data` changes on a new release; same release again commits nothing | Pass |
| 3 | Workflow | Changed workbook layout | Fails with a message, data untouched | Pass |
| 4 | Workflow | Pages rebuild after the data commit | Was missing (see above) | Pass after fix |
| 5 | Page | Live data after a collect run | "Live from repo", release November 4, 2026, no seed banner | Pass |
| 6 | Page | Light and dark, 400 px | No sideways scroll; link buttons at least 44 px wide after the fix below; no CSP violations | Pass after fix |
| 7 | Movers | Top 5 month over month and year over year | Pass | Pass |
| 8 | Movers | Group tabs, arrow keys, Home and End | Pass | Pass |
| 9 | Movers | Sort by month, year, name; remembered after reload | Pass | Pass |
| 10 | Movers | Copy results as CSV | Header and rows | Pass |
| 11 | Chart | Four series pickers; click a mover to add it | Pass | Pass |
| 12 | Chart | Mixed units rebase automatically; same units chart real prices | Note shown; Rebase box disabled when forced | Pass |
| 13 | Chart | Rebase with a base month | Table shows 100.00 at the base month | Pass |
| 14 | Chart | 1Y, 5Y, 10Y, All, From and To | 5Y and 10Y disabled on 15 months; From after To swaps | Pass |
| 15 | Chart | Tooltip, data table | Pass | Pass |
| 16 | Spreads | 5 cards with sparklines | Values as above | Pass |
| 17 | Your file | Tidy CSV, dataset JSON; bad JSON, wrong shape, over 5 MB refused; Back to bundled data | Pass | Pass |
| 18 | Fallback | `monthly.json` 404 or invalid values | Banner names the error; snapshot shown | Pass |
| 19 | Seed | Site as shipped | Live chip with the seed banner | Pass |
| 20 | file:// | `web/app.html` | "Snapshot as of the October 2, 2026 release" | Pass |
| 21 | CLI | `parse`, `movers --group --by --top`, `spreads` | Pass | Pass |
| 22 | CLI | Errors: bad group, missing workbook | Exit non-zero | Pass |
| 23 | Library | Analytics and collector | `pytest` and `web/parity.test.mjs` | Pass |

## Bugs fixed in this pass

| Bug | Severity | Fix |
|---|---|---|
| Weekly data commits never reached the live page (no Pages build on Actions-token pushes) | High | Collect job requests a Pages build after pushing |
| Short mover names (for example "Tin") were 27 px wide link buttons on touch screens | Low | 44 px minimum width |
| README step 5 quoted the placeholder, so the release fill turned it into nonsense | Low | Step removed; the release fills the link |

## Decisions the app now makes for you

| Decision point | Before | After |
|---|---|---|
| Base month when a picked series has no value there | Dead end: "Pick another base month" | Moves to the first month in the range where every picked series has a value, with a line saying so |
| Rebasing mixed units | Already automatic | No change |
| Chart range, default series | Already defaulted (last 10 years, four core series) | No change |

## How to rerun

```
pip install -e .[dev] playwright
python -m playwright install chromium
pytest -q                                   # includes tests/test_published_site.py and tests/test_workflows.py
python tests/make_vectors.py && node web/parity.test.mjs
python web/build_pages.py
```

Test counts: 100 Python tests before this pass, 104 after, plus the parity script.

## Known limits

- The live World Bank workbook was not reachable from the test machine. The parser has been tested on synthetic workbooks and on the seed values in the Pink Sheet layout, not on the live file (as the README says).
- The Pages rebuild request needs the repository's Pages source to be "Deploy from a branch", as the README setup describes.
