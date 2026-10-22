"""Build the pages.

1. Embed the snapshot (real values from data/snapshot/pinksheet_pdf_values.json)
   into web/app.html, the self-contained demo page that makes no network requests.
2. Wrap web/app.html into docs/index.html for GitHub Pages, adding one small
   loader that reads data/monthly.json and data/meta.json from the same origin.
3. Copy data/monthly.json and data/meta.json to docs/data/ so Pages can serve them.

Run: python web/build_pages.py
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "app.html"
OUT = ROOT / "docs" / "index.html"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from seed_from_pdf import load_seed  # noqa: E402

HEAD_RE = re.compile(r"\A\s*(<title>.*?</title>.*?</style>)\s*", re.S)
SNAP_RE = re.compile(r'(<script type="application/json" id="snapshot">)(.*?)(</script>)', re.S)
META_RE = re.compile(r'(<script type="application/json" id="snapshot-meta">)(.*?)(</script>)', re.S)

LOADER = """<script id="live-loader">
// GitHub Pages only: read the collector's output from this same site.
// Same-origin GETs of two static JSON files. Nothing is sent anywhere.
window.COMMODITY_PULSE_LIVE = (function () {
  "use strict";
  var MAX = 30 * 1024 * 1024;
  function get(url) {
    return fetch(url, { credentials: "omit", cache: "no-cache", redirect: "error" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
      return r.text();
    }).then(function (t) {
      if (t.length > MAX) throw new Error(url + " is too large");
      return JSON.parse(t);
    });
  }
  return Promise.all([get("data/monthly.json"), get("data/meta.json").catch(function () { return {}; })])
    .then(function (r) { return { monthly: r[0], meta: r[1] }; });
})();
</script>
"""


def script_json(obj) -> str:
    """JSON safe to place inside a <script> element."""
    s = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def embed_snapshot(src: str) -> str:
    ds, raw = load_seed()
    meta = {
        "release": raw["release"],
        "seed": True,
        "source": "World Bank Commodity Price Data (The Pink Sheet)",
        "editions": [e["url"] for e in raw["editions"]],
        "license": "CC BY 4.0",
    }
    if not SNAP_RE.search(src) or not META_RE.search(src):
        raise SystemExit("app.html must contain the snapshot and snapshot-meta script blocks")
    src = SNAP_RE.sub(lambda m: m.group(1) + script_json(ds) + m.group(3), src, count=1)
    src = META_RE.sub(lambda m: m.group(1) + script_json(meta) + m.group(3), src, count=1)
    return src


def build(src: str) -> str:
    m = HEAD_RE.match(src)
    if not m:
        raise SystemExit("app.html must start with <title>, meta, font link, and <style>")
    head = m.group(1)
    body = src[m.end():]
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="description" content="Free monthly commodity price dashboard on World Bank Pink Sheet data: movers, z-scores, percentiles, spreads.">\n'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src data:; connect-src 'self'; "
        "form-action 'none'; base-uri 'none'\">\n"
        '<meta name="referrer" content="no-referrer">\n'
        + head
        + "\n<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
        "[hidden]{display:none!important}img{max-width:100%}</style>\n"
        "</head>\n"
        "<body>\n"
        + LOADER
        + body.rstrip()
        + "\n</body>\n</html>\n"
    )


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    new_src = embed_snapshot(src)
    if new_src != src:
        SRC.write_text(new_src, encoding="utf-8")
        print("updated snapshot in web/app.html")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(new_src), encoding="utf-8")
    print("wrote " + str(OUT.relative_to(ROOT)))
    dest = ROOT / "docs" / "data"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("monthly.json", "meta.json"):
        f = ROOT / "data" / name
        if f.exists():
            shutil.copyfile(f, dest / name)
            print("copied data/" + name + " to docs/data/")
    (ROOT / "docs" / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
