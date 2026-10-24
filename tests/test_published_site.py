"""What Pages publishes after the weekly collect job, tested in a browser.

The release fill is applied to the tracked files, the collect job's steps run on a saved
workbook (the seed values under a newer release date), docs/ is served under
/commodity-pulse/ as branch Pages serves it, and the page is opened in headless Chromium.
Skips when Playwright or Chromium is missing.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from pages_site import install_routes, pages_root, release_tree, serve, watch

sync_api = pytest.importorskip("playwright.sync_api")
openpyxl = pytest.importorskip("openpyxl")
NAME = "commodity-pulse"


def workbook_from(ds, path, release):
    def idx(m):
        return int(m[:4]) * 12 + int(m[5:]) - 1
    first = min(idx(s["start"]) for s in ds["series"])
    last = max(idx(s["start"]) + len(s["values"]) - 1 for s in ds["series"])
    wb = openpyxl.Workbook()
    wb.active.title = "Index"
    ws = wb.create_sheet("Monthly Prices")
    for r in (["World Bank Commodity Price Data (The Pink Sheet)"], [release], ["Monthly prices in nominal US dollars"]):
        ws.append(r)
    ws.append([None] + [s["name"] for s in ds["series"]])
    ws.append([None] + [f"({s['unit']})" for s in ds["series"]])
    ws.append([None] + [s["id"] for s in ds["series"]])
    for k in range(first, last + 1):
        row = [f"{k // 12}M{k % 12 + 1:02d}"]
        for s in ds["series"]:
            i = k - idx(s["start"])
            v = s["values"][i] if 0 <= i < len(s["values"]) else None
            row.append(".." if v is None else v)
        ws.append(row)
    wb.save(path)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tree = release_tree(tmp_path_factory.mktemp("release"), NAME)
    seed = json.loads((tree / "data" / "monthly.json").read_text(encoding="utf-8"))
    book = tree / "book.xlsx"
    workbook_from(seed, book, "Updated on November 04, 2026")
    env_path = str(tree / "src")
    run = lambda *a: subprocess.run([sys.executable, *a], cwd=tree, check=True, env={"PYTHONPATH": env_path, "PATH": ""})  # noqa: E731
    run("-m", "commodity_pulse.cli", "collect", "--out", "data", "--xlsx", str(book))   # step "Collect"
    run("web/build_pages.py")                                                         # step "Rebuild pages"
    meta = json.loads((tree / "docs" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["release"] == "2026-11-04" and not meta.get("seed")
    with serve(pages_root(tree), NAME) as url:
        yield url


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


def test_site_shows_the_collected_release(site, browser):
    errors: list = []
    ctx = browser.new_context(viewport={"width": 400, "height": 800}, has_touch=True, is_mobile=True)
    install_routes(ctx, site.split("/" + NAME)[0], errors)
    page = ctx.new_page()
    watch(page, errors)
    page.goto(site)
    page.wait_for_function("() => /series/.test(document.getElementById('data-note').textContent)")
    assert "live" in page.inner_text("#chip-mode").lower()
    assert "November 4, 2026" in page.inner_text("#data-note")
    assert page.is_hidden("#data-banner")
    assert page.locator("#spreads .spread").count() == 5
    small = page.evaluate("""() => Array.from(document.querySelectorAll('button')).filter(b => {
        const r = b.getBoundingClientRect(); return r.width && (r.width < 44 || r.height < 44); }).length""")
    assert small == 0
    assert page.evaluate("() => window.__csp") == []
    assert page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    assert errors == []
    ctx.close()


def test_rebase_base_month_moves_to_a_month_with_values(site, browser, tmp_path):
    errors: list = []
    ctx = browser.new_context()
    install_routes(ctx, site.split("/" + NAME)[0], errors)
    page = ctx.new_page()
    watch(page, errors)
    page.goto(site)
    page.wait_for_function("() => /series/.test(document.getElementById('data-note').textContent)")
    f = tmp_path / "tidy.csv"
    rows = ["series_id,name,unit,date,value"]
    rows += [f"X_A,Thing A,$/t,2020-{m:02d},{10 + m}" for m in range(1, 7)]
    rows += [f"X_B,Thing B,$/t,2020-{m:02d},{20 + m}" for m in range(3, 7)]
    f.write_text("\n".join(rows) + "\n", encoding="utf-8")
    page.click("#load-own summary")
    page.set_input_files("#file-in", str(f))
    page.wait_for_function("() => /2 series/.test(document.getElementById('file-msg').textContent)")
    page.select_option("#s1", "X_A")
    page.select_option("#s2", "X_B")
    page.check("#rebase")
    assert page.input_value("#base-month") == "2020-03"
    assert "moved from 2020-01 to 2020-03" in page.inner_text("#chart-note")
    assert errors == []
    ctx.close()
