"""Command line interface.

    commodity-pulse collect [--out data] [--xlsx FILE]
    commodity-pulse parse FILE.xlsx [--csv | --json]
    commodity-pulse movers [--data data/monthly.json] [--group energy] [--by mom|yoy] [--top 10] [--json]
    commodity-pulse spreads [--data data/monthly.json] [--json]
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

from . import analytics as A

MAX_JSON_BYTES = 50 * 1024 * 1024


def _load_dataset(path: str) -> dict:
    p = pathlib.Path(path)
    if not p.is_file():
        raise SystemExit("error: no such file: " + path)
    if p.stat().st_size > MAX_JSON_BYTES:
        raise SystemExit("error: file is larger than 50 MB: " + path)
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit("error: not valid JSON: " + path + " (" + str(e) + ")") from None
    try:
        return A.validate_dataset(obj)
    except A.AnalyticsError as e:
        raise SystemExit("error: " + str(e)) from None


def _cmd_collect(args) -> int:
    from . import collect as C

    try:
        changed = C.collect(pathlib.Path(args.out), xlsx_path=pathlib.Path(args.xlsx) if args.xlsx else None)
    except C.CollectError as e:
        print("error: " + str(e), file=sys.stderr)
        return 2
    print("data changed" if changed else "no change")
    return 0


def _cmd_parse(args) -> int:
    from . import collect as C

    p = pathlib.Path(args.file)
    if not p.is_file():
        print("error: no such file: " + args.file, file=sys.stderr)
        return 2
    if p.stat().st_size > C.MAX_XLSX_BYTES:
        print("error: workbook too large", file=sys.stderr)
        return 2
    try:
        parsed = C.parse_workbook(p.read_bytes())
    except C.CollectError as e:
        print("error: " + str(e), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(C.to_dataset(parsed["rows"]), separators=(",", ":")))
    else:
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(["series_id", "name", "unit", "date", "value"])
        for r in parsed["rows"]:
            w.writerow([A.csv_text(r["series_id"]), A.csv_text(r["name"]), A.csv_text(r["unit"]), r["date"], repr(r["value"])])
    return 0


def _cmd_movers(args) -> int:
    ds = _load_dataset(args.data)
    try:
        rows = A.movers(ds, args.group, args.by, args.top)
    except A.AnalyticsError as e:
        print("error: " + str(e), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'Series':32} {'Month':8} {'Value':>12} {'MoM':>8} {'YoY':>8} {'z12':>6} {'Pctl':>6}")
    for r in rows:
        z = "n/a" if r["z12"] is None else A.round_half_away(r["z12"], 2)
        pc = "n/a" if r["pct"] is None else A.round_half_away(r["pct"], 0)
        print(f"{r['name'][:32]:32} {r['date'] or '':8} {A.format_value(r['value']):>12} "
              f"{A.format_pct(r['mom']):>8} {A.format_pct(r['yoy']):>8} {z:>6} {pc:>6}")
    return 0


def _cmd_spreads(args) -> int:
    ds = _load_dataset(args.data)
    out = A.spreads(ds)
    if args.json:
        print(json.dumps([{k: v for k, v in s.items() if k != "series"} for s in out], indent=2))
        return 0
    for s in out:
        m = s["summary"]
        print(f"{s['label']:34} {m['date'] or '':8} {A.format_value(m['value']):>10} {s['unit']:14} "
              f"MoM {A.format_signed(m['mom']):>8}  YoY {A.format_signed(m['yoy']):>8}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="commodity-pulse", description="World Bank monthly commodity prices: collect and analyze.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="download the latest workbook and write data/monthly.json + meta.json")
    c.add_argument("--out", default="data")
    c.add_argument("--xlsx", help="parse this local workbook instead of downloading")
    c.set_defaults(func=_cmd_collect)

    pa = sub.add_parser("parse", help="parse a local CMO-Historical-Data-Monthly.xlsx to tidy rows")
    pa.add_argument("file")
    g = pa.add_mutually_exclusive_group()
    g.add_argument("--csv", action="store_true", help="tidy CSV (default)")
    g.add_argument("--json", action="store_true", help="compact per-series JSON")
    pa.set_defaults(func=_cmd_parse)

    m = sub.add_parser("movers", help="largest month-over-month or year-over-year moves")
    m.add_argument("--data", default="data/monthly.json")
    m.add_argument("--group", choices=list(A.GROUPS))
    m.add_argument("--by", choices=["mom", "yoy"], default="mom")
    m.add_argument("--top", type=int, default=10)
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=_cmd_movers)

    s = sub.add_parser("spreads", help="Brent-WTI, gas Europe vs US, urea/gas, gold/silver")
    s.add_argument("--data", default="data/monthly.json")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_spreads)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
