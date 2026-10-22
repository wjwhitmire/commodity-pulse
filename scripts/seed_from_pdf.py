"""Seed data/ from values transcribed out of official Pink Sheet PDFs.

Run once before the first collector run so the GitHub Pages dashboard has real
data on day one. The weekly collector replaces both files with the full workbook
history (1960 onward); its data hash differs, so it always commits over the seed.

Run: python scripts/seed_from_pdf.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from commodity_pulse.analytics import classify, validate_dataset  # noqa: E402
from commodity_pulse.collect import write_outputs  # noqa: E402

SRC = ROOT / "data" / "snapshot" / "pinksheet_pdf_values.json"


def load_seed() -> tuple[dict, dict]:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    series = []
    for sid, name, unit, values in raw["series"]:
        series.append({"id": sid, "name": name, "unit": unit, "group": classify(sid, name),
                       "start": raw["start"], "values": [float(v) for v in values]})
    return validate_dataset({"series": series}), raw


def main() -> None:
    ds, raw = load_seed()
    latest = raw["editions"][-1]
    write_outputs(
        ds, ROOT / "data", latest["url"], raw["release"], fetched_at="2026-10-21T00:00:00+00:00",
        extra_meta={
            "seed": True,
            "note": "Seed: monthly averages transcribed from five Pink Sheet PDF editions (July 2025 to "
                    "September 2026). The collector replaces this with the full workbook.",
            "editions": raw["editions"],
        },
    )
    print("wrote data/monthly.json and data/meta.json (" + str(len(ds["series"])) + " series)")


if __name__ == "__main__":
    main()
