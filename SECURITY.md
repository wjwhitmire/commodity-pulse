# Security

## What the browser tool does with your data

- `web/app.html` (the published demo) makes no network requests of any kind: no fetch, XHR, WebSocket, beacons, or analytics. Its data is embedded in the page. The only external resource is the Google Fonts stylesheet.
- `docs/index.html` (the GitHub Pages build) adds one small loader that makes two same-origin GET requests, for `data/monthly.json` and `data/meta.json`, served by the same Pages site. It sends nothing. Its Content-Security-Policy allows `connect-src 'self'` and nothing else.
- Files you load with "Load your own data" are read locally with `<input type=file>` and FileReader and never leave the tab. Files over 5 MB or with more than 50,000 rows are rejected.
- localStorage is used only for the last selected tab and sort order. No data is stored.
- No eval, no `new Function`, no inline event handlers. Text from data files (series names, units) is inserted with textContent, never innerHTML.

## Collector (GitHub Actions)

- Runs weekly with `contents: write` on the collect job only. Every other job is read-only.
- Downloads only over https and only from worldbank.org hosts, including after redirects. Downloads are size-capped.
- Parses the workbook with openpyxl in read-only, values-only mode. Formulas and macros are never executed.
- Commits with the github-actions bot identity. No secrets are used beyond the built-in token.

## Python library

- No pickle, no eval, no shell calls. The CLI reads only the paths you pass it, with size caps.

## Reporting an issue

Open a GitHub issue titled "Security" with a description and steps to reproduce. For anything sensitive, use GitHub's private vulnerability reporting on this repository instead of a public issue.
