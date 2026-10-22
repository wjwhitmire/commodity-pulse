# Commodity Pulse

Commodity Pulse is a free monthly commodity price dashboard built on the World Bank Commodity Price Data (the "Pink Sheet"). It covers energy, metals, agriculture and fertilizers, with monthly history back to 1960. For each series it shows the latest price, the month-over-month and year-over-year change, a 12-month z-score, and the percentile against the series' own history. It also shows the largest movers, a line chart of up to four series with an optional rebase to 100, and the spreads that matter: Brent minus WTI, Europe gas against US gas, urea against gas, and gold against silver.

Live tool: https://wjwhitmire.github.io/commodity-pulse/

There are no servers and no cost. A weekly GitHub Actions job downloads the World Bank workbook, rebuilds `data/`, and commits only when a new release appears ("git scraping"). GitHub Pages serves the dashboard and the data from the same repo.

## Data source and license

Data: World Bank, Commodity Price Data (The Pink Sheet), https://www.worldbank.org/en/research/commodity-markets

License: Creative Commons Attribution 4.0 International (CC BY 4.0). The World Bank Data Catalog lists the dataset "Commodity Prices - History and Projections" (https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections) under CC BY 4.0. License terms: https://datacatalog.worldbank.org/public-licenses?fragment=cc

Attribution used in this repo and on the page:

> Source: World Bank, Commodity Price Data (The Pink Sheet), https://www.worldbank.org/en/research/commodity-markets. Licensed under CC BY 4.0. Reformatted and derived statistics computed by Commodity Pulse; the World Bank does not endorse this tool.

Changes made: the workbook is reshaped into per-series JSON. Changes, z-scores, percentiles, spreads, ratios and rebased series are computed here. The World Bank's data license terms include its dispute-resolution provisions; read the license page before reuse.

The code in this repo is MIT licensed. The data in `data/` and `docs/data/` stays under CC BY 4.0 with the attribution above.

## Turn it on

1. Push this repo to GitHub (public).
2. Settings, Pages: Source "Deploy from a branch", branch `main`, folder `/docs`.
3. Settings, Actions, General, Workflow permissions: leave "Read repository contents" as the default. The collect workflow asks for `contents: write` on its own job.
4. Actions tab: enable workflows if GitHub asks, then run "collect" once with "Run workflow". The first run replaces the seed data with the full history and commits it.
5. Replace `https://wjwhitmire.github.io/commodity-pulse/` in this README with the Pages URL.

The workflow then runs every Wednesday at 09:17 UTC. The World Bank usually publishes on the second business day of the month, so a new release shows up within a week.

## What ships before the first collector run

The collector downloads the World Bank workbook on its first scheduled run. Until then, `data/` holds a seed of real values transcribed from five official Pink Sheet PDF editions (October 2025, January, April, July and October 2026). It covers July 2025 to September 2026 for 38 series. `data/snapshot/pinksheet_pdf_values.json` lists the source URL of each edition.

The transcription was checked against the quarterly averages printed in the October 2026 edition: all 190 quarter averages (Q3 2025 to Q3 2026) across the 38 series match the mean of the transcribed monthly values within print rounding. Soybeans, soybean meal, soybean oil and palm oil are left out because the October 2026 edition revised or replaced those series. Japan LNG is left out because the Pink Sheet prints its latest two months as estimates and later revises them (the October 2026 edition prints Q1 2026 at 11.41 $/mmbtu, against 12.55 for the months as first printed), so the transcribed months cannot be confirmed.

The published demo page (`web/app.html`) embeds the same seed and says "Snapshot as of the October 2, 2026 release. The GitHub version updates automatically." Percentiles in the demo rank against 15 months only, and the page says so.

## Quick start

Browser: open the live tool, or serve `docs/` locally (`python -m http.server -d docs`) and open it. `web/app.html` also works opened straight from disk, with its embedded snapshot.

Python:

```
pip install -e .[dev]
commodity-pulse collect --out data                      # download latest workbook, write data/
commodity-pulse collect --out data --xlsx CMO-Historical-Data-Monthly.xlsx   # use a local copy
commodity-pulse parse CMO-Historical-Data-Monthly.xlsx > tidy.csv            # tidy rows
commodity-pulse movers --group energy --by yoy --top 5
commodity-pulse spreads
```

```python
import json
from commodity_pulse import validate_dataset, summarize, spreads, movers, rebase

ds = validate_dataset(json.load(open("data/monthly.json")))
for r in movers(ds, "metals", "yoy", 3):
    print(r["name"], r["value"], r["yoy"], r["z12"], r["pct"])
for s in spreads(ds):
    print(s["label"], s["summary"]["value"], s["unit"])
```

## Data files

`data/monthly.json` is compact, one object per series:

```
{"series": [{"id": "CRUDE_BRENT", "name": "Crude oil, Brent", "unit": "$/bbl", "group": "energy",
             "start": "1960-01", "values": [1.63, 1.63, ..., 116.8]}, ...]}
```

`values` has one entry per calendar month from `start`. `null` marks a missing month.

`data/meta.json` holds the source page, the workbook URL, the release date, the latest month, `fetched_at`, a SHA-256 of the data, and the license block. The collector skips writing (and the workflow skips committing) when the release date and the data hash both match the last run.

## How the collector reads the workbook

1. Fetch https://www.worldbank.org/en/research/commodity-markets and find the link to `CMO-Historical-Data-Monthly.xlsx`. The URL changes with each release. Only https URLs on worldbank.org hosts are accepted, including after redirects.
2. Open the "Monthly Prices" sheet with openpyxl (read-only, values only).
3. Find the first row whose column A looks like `1960M01`. Above it, classify the header rows as codes (`CRUDE_BRENT`), units (`($/bbl)`) and names (`Crude oil, Brent`). Rows are found by content, not fixed row numbers, so an extra title row does not break the parse.
4. Read "Updated on October 02, 2026" style text for the release date.
5. Turn each cell into a tidy row (series_id, name, unit, date YYYY-MM, value). `..`, `…`, blanks and text are missing. If a workbook has no code row, known names map to Pink Sheet codes, and anything else gets a slug of its name.

The parser is tested against synthetic workbooks generated with openpyxl that mirror this layout (`tests/synthetic_workbook.py`). It has not yet run against the live file. If the World Bank changes the layout, the collector fails with a specific message and commits nothing.

## Method

Notation: `P_t` is the price in month t, using the latest month with a value.

- Month over month: `MoM = (P_t - P_t-1) / |P_t-1| x 100`
- Year over year: `YoY = (P_t - P_t-12) / |P_t-12| x 100`
- Blank when the earlier month is missing or zero.
- For spreads and ratios, MoM and YoY are plain differences in the spread's own units, because a spread can be zero or negative.
- 12-month z-score: `z = (P_t - mean) / sd` over the 12 months ending at t (t included). `sd` is the sample standard deviation, `sqrt(sum((x - mean)^2) / 11)`. Blank if any of the 12 months is missing or `sd = 0`.
- Percentile against history: `100 x (count below P_t + 0.5 x count equal to P_t) / n`, over every non-missing month from the start through t (midrank convention).
- Rebase: `R_t = P_t / P_base x 100`. Blank if the base month is missing or zero. The chart rebases automatically when the picked series have different units, so there is never a second y-axis.
- Spreads, month by month over the overlapping months:
  - Brent minus WTI ($/bbl)
  - Europe gas (TTF) minus US gas (Henry Hub) ($/mmbtu), and the ratio Europe / US
  - Urea (Middle East f.o.b., "Urea, E. Europe" in the Pink Sheet) / Europe gas: mmbtu of gas per tonne of urea. A rough feedstock-margin gauge only. It ignores plant efficiency, capital, freight and other inputs.
  - Gold / silver (both $/troy oz)
- Rounding for display: 0 decimals at 1,000 and above, 1 at 100 and above, else 2. Halves round away from zero, decided on the shortest decimal form of the number, so Python and JavaScript print the same text.

## Limits

- Monthly averages. Intra-month highs and lows are not visible.
- Nominal US dollars. No inflation adjustment, so 1960s and 2020s prices are not comparable in real terms.
- Copying CSV from the page puts a single quote in front of any text cell that starts with = + - @ so spreadsheets do not run it as a formula. `commodity-pulse parse` does the same.
- The World Bank revises recent months and sometimes replaces series (for example palm oil from January 2026, fish meal from July 2026). The tool shows the latest release as published and does not splice or adjust series.
- Z-scores and percentiles describe a price against its own loaded history. They are not forecasts, fair values, or trading signals. A short history (like the 15-month demo) makes the percentile coarse.
- Groups follow the Pink Sheet's sections by series code, with name keywords as a fallback. Unknown series go to "Other".
- The collector depends on the World Bank page linking the workbook by its usual file name. If that changes, the job fails loudly and the last good data stays up.
- Not investment advice.

## Validation

- `pytest -q`: analytics with hand-checked values (z-score against `statistics.stdev`, midrank percentiles, change formulas), edge cases (missing months, zero bases, flat windows, ties), bad input, the workbook parser against synthetic workbooks, the collector's commit-only-on-change rule, the CLI, and the seed values (for example Brent September 2026 = 116.8 $/bbl, Brent minus WTI = 19.9).
- `python tests/make_vectors.py && node web/parity.test.mjs`: the JavaScript core in `web/app.html` reproduces the Python results for summaries, z-scores, percentiles, rebasing, windows, spreads, movers, grouping, formatting, CSV parsing and validation. Tolerance is 1e-9 relative. In practice the results are bit-identical, because the sums are written as explicit loops on both sides.

## Repo layout

```
src/commodity_pulse/analytics.py   math (no I/O, no dependencies)
src/commodity_pulse/collect.py     find, download, parse, write data/ (openpyxl)
src/commodity_pulse/cli.py         commodity-pulse collect | parse | movers | spreads
data/monthly.json, data/meta.json  collector output (seed until the first run)
data/snapshot/                     real values transcribed from Pink Sheet PDFs
scripts/seed_from_pdf.py           writes the seed into data/
web/app.html                       the dashboard, with an embedded snapshot (demo)
web/build_pages.py                 embeds the snapshot, builds docs/index.html, copies data to docs/data/
docs/                              GitHub Pages site
.github/workflows/collect.yml      weekly collector
.github/workflows/ci.yml           tests, parity, gitleaks
```

## License

Code: MIT, copyright 2026 Will Whitmire. See LICENSE.

Data: World Bank, CC BY 4.0, attribution as above.
