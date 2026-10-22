"""Generate tests/vectors.json from the Python library.

web/parity.test.mjs runs the JavaScript core in web/app.html against these
vectors. Run: python tests/make_vectors.py
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from commodity_pulse import analytics as A  # noqa: E402


def synthetic_series(seed: int, n: int, start: str, sid: str, nulls: bool = True) -> dict:
    """Random walk used only to exercise the math. Not prices."""
    rnd = random.Random(seed)
    v = 50 + 50 * rnd.random()
    vals = []
    for k in range(n):
        v = max(0.01, v * (1 + rnd.gauss(0, 0.05)))
        x = round(v, rnd.choice([0, 1, 2, 3, 6]))
        if nulls and rnd.random() < 0.05:
            x = None
        if k % 37 == 5 and k > 0 and vals[-1] is not None:
            x = vals[-1]  # ties for the percentile
        vals.append(x)
    return {"id": sid, "start": start, "values": vals}


def err_case(fn):
    try:
        fn()
    except A.AnalyticsError as e:
        return {"code": e.code, "message": str(e)}
    raise AssertionError("expected an error")


def main() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from seed_from_pdf import load_seed  # noqa: E402

    seed_ds = load_seed()[0]  # fixed real values, so vectors do not move when data/ updates
    synth = [synthetic_series(i, n, start, f"S{i}") for i, (n, start) in enumerate(
        [(40, "1960-01"), (240, "1999-07"), (13, "2025-09"), (1, "2026-09"), (90, "2010-12"), (25, "2024-01")])]
    synth.append({"id": "FLAT", "start": "2020-01", "values": [5.0] * 14})
    synth.append({"id": "NEG", "start": "2020-01", "values": [-3.0, -1.5, 0.0, 2.0, -0.25, None, 1e-9, 12345.678]})
    synth.append({"id": "ALLNULL", "start": "2020-01", "values": [None, None, None]})

    summarize = []
    for s in seed_ds["series"] + synth:
        for kind in ("pct", "abs"):
            summarize.append({"series": s, "kind": kind, "out": A.summarize(s, kind)})

    zp = []
    for si, s in enumerate(synth[:3]):
        for idx in range(len(s["values"])):
            zp.append({"series": si, "idx": idx, "window": 12, "z": A.zscore(s, idx, 12), "pct": A.percentile(s, idx)})
        zp.append({"series": si, "idx": len(s["values"]) - 1, "window": 6, "z": A.zscore(s, len(s["values"]) - 1, 6),
                   "pct": A.percentile(s, len(s["values"]) - 1)})

    rebase = []
    for s in synth[:3] + [synth[-2]]:
        for base in (s["start"], A.month_add(s["start"], 3), A.month_add(s["start"], -2), A.month_add(s["start"], 2)):
            rebase.append({"series": s, "base": base, "out": A.rebase(s, base)})
    for s in seed_ds["series"][:6]:
        rebase.append({"series": s, "base": "2026-01", "out": A.rebase(s, "2026-01")})

    windows = []
    for s in synth[:3]:
        for first, last in ((A.month_add(s["start"], -3), A.month_add(s["start"], 5)), (A.month_add(s["start"], 2), A.month_add(s["start"], 2)),
                            (A.month_add(s["start"], 10), A.month_add(s["start"], 400))):
            windows.append({"series": s, "first": first, "last": last, "out": A.window(s, first, last)})

    combine = []
    pairs = [(synth[0], synth[2]), (synth[1], synth[4]), (synth[4], synth[1]), (synth[-2], synth[-3]), (synth[5], synth[2]),
             (synth[0], synth[3])]
    for a, b in pairs:
        for op in ("diff", "ratio"):
            combine.append({"a": a, "b": b, "op": op, "out": A.combine(a, b, op)})

    spreads = [{"dataset": "seed", "out": A.spreads(seed_ds)}]
    alt = {"series": [dict(synth[1], id="CRUDE_BRENT"), dict(synth[4], id="CRUDE_WTI"), dict(synth[0], id="GOLD"),
                      dict(synth[-2], id="SILVER"), dict(synth[5], id="NGAS_EUR")]}
    spreads.append({"dataset": "alt", "out": A.spreads(alt)})

    movers = []
    for g in (None, "energy", "metals", "agriculture", "fertilizers", "other"):
        for by in ("mom", "yoy"):
            for top in (None, 5, 0):
                movers.append({"dataset": "seed", "group": g, "by": by, "top": top, "out": A.movers(seed_ds, g, by, top)})
    mixed = A.validate_dataset({"series": [dict(s, group="other") for s in synth]})
    for by in ("mom", "yoy"):
        movers.append({"dataset": "mixed", "group": None, "by": by, "top": None, "out": A.movers(mixed, None, by, None)})

    classify = []
    names = [("CRUDE_BRENT", ""), ("crude_wti", ""), ("ZZ", "Natural gas, Europe"), ("ZZ", "Palm oil"), ("ZZ", "Urea, E. Europe"),
             ("ZZ", "Iron ore, cfr spot"), ("ZZ", "Tin"), ("ZZ", "Tinted glass"), ("ZZ", "Tobacco, US import u.v."),
             ("ZZ", "Mystery index"), ("", ""), ("POTASH", ""), ("ZZ", "Liquefied natural gas, Japan"), ("ZZ", "Shrimps, Mexican"),
             ("ZZ", "Coconut oil"), ("ZZ", "Crude oil, average"), ("ZZ", "Sawnwood, Malaysian"), ("ZZ", "Phosphate rock"),
             ("ZZ", "Fish meal"), ("ZZ", "Lead"), ("ZZ", "Gold")]
    for code, name in names:
        classify.append({"code": code, "name": name, "group": A.classify(code, name)})

    rnd = random.Random(7)
    fmt_vals = [0.0, 1.005, 2.5, -2.5, 0.125, -0.004, 1e-7, 123456.789, 9.995, 999.95, 99.995, 1234.5, -1234.5,
                1e16, 1.5e21, 5e-5, 0.045, 14474.0, 116.8, 2.95, 66.85758513931889, -0.0, 1e300]
    fmt_vals += [round(rnd.uniform(-20000, 20000), rnd.choice([0, 1, 2, 3, 5])) for _ in range(150)]
    fmt_vals += [rnd.uniform(-5, 5) for _ in range(50)]
    fmt = []
    for x in fmt_vals:
        fmt.append({"x": x, "r0": A.round_half_away(x, 0), "r1": A.round_half_away(x, 1), "r2": A.round_half_away(x, 2),
                    "value": A.format_value(x), "pct": A.format_pct(x), "signed": A.format_signed(x)})
    fmt.append({"x": None, "r0": "", "r1": "", "r2": "", "value": "n/a", "pct": "n/a", "signed": "n/a"})

    months = []
    for s in ("1960-01", "1999-12", "2026-09", "0002-03"):
        months.append({"month": s, "idx": A.parse_month(s), "plus": A.month_add(s, 13), "minus": A.month_add(s, -13)})
    month_errors = [{"input": x, **err_case(lambda x=x: A.parse_month(x))} for x in ["2026-13", "2026-00", "26-01", "x", None, 5]]

    valid_ok = [
        {"input": {"series": [{"id": "GOLD", "start": "2020-01", "values": [1, None, 2.5]}]}},
        {"input": {"series": [{"id": "A.b-c_1", "name": "", "unit": "$/t", "group": "metals", "start": "2020-01", "values": [0]}]}},
        {"input": {"series": [{"id": "Z", "name": "Palm oil", "group": "nonsense", "start": "1960-01", "values": [1e-9, 3]}]}},
    ]
    for v in valid_ok:
        v["out"] = A.validate_dataset(v["input"])
    bad_inputs = [
        [], {"series": []}, {"series": "x"}, {"series": [1]}, {"series": [None]},
        {"series": [{"id": "a b", "start": "2020-01", "values": [1]}]},
        {"series": [{"id": "", "start": "2020-01", "values": [1]}]},
        {"series": [{"id": "A", "start": "2020-01", "values": [1]}, {"id": "A", "start": "2020-01", "values": [1]}]},
        {"series": [{"id": "A", "start": "2020-13", "values": [1]}]},
        {"series": [{"id": "A", "start": 2020, "values": [1]}]},
        {"series": [{"id": "A", "start": "2020-01", "values": []}]},
        {"series": [{"id": "A", "start": "2020-01", "values": {"0": 1}}]},
        {"series": [{"id": "A", "start": "2020-01", "values": ["1"]}]},
        {"series": [{"id": "A", "start": "2020-01", "values": [True]}]},
        {"series": [{"id": "A", "start": "2020-01", "values": [1], "unit": 5}]},
        {"series": [{"id": "A", "start": "2020-01", "values": [1], "name": None}]},
        {"series": [{"id": "A", "start": "2020-01", "values": [1], "name": "x" * 201}]},
        {"series": [{"id": "A", "start": "2020-01", "values": [0.0] * 2401}]},
    ]
    valid_err = [{"input": b, **err_case(lambda b=b: A.validate_dataset(b))} for b in bad_inputs]

    csv_ok = [
        "series_id,name,unit,date,value\nGOLD,Gold,$/toz,2026-08,4411\nGOLD,Gold,$/toz,2026M09,4319\n",
        "\ufeffdate,value,series_id,extra\r\n2026-01,1.5,A,x\r\n2026-03,2,A,y\r\n2026-02,..,A,z\r\n",
        "A\t2020-01\t1\nA\t2020-03\t3e2\n\nB\t1960M1\t-0.5",
        'X,"Crude oil, Brent",$/bbl,2026-09,116.8\nX,"Crude oil, Brent",$/bbl,2026-08,90.9\nY,"say ""hi""",u,2026-09,NaN\nY,y,u,2026-08,.5',
        "code,date,value\nURE.A-1,2025-12,+400\nURE.A-1,2026-01,\n",
    ]
    csv_bad = [
        "", "\n\n", "a,b\n", "series_id,date,value\nA,2026-13,1", "A,2026-01,abc", "A,2026-01,1\nA,2026-01,2",
        "bad id,2026-01,1", 'A,"2026-01,1', "name,date,value\nx,2026-01,1", "series_id,name,unit,date,value\nA,n,u,2026-01",
        "A,2026-01,1e999", "A,26-01,1", "A,2026-01,0x10", "A,1800-01,1\nA,2026-01,2",
    ]
    csv_cases = [{"text": t, "out": A.parse_tidy_csv(t)} for t in csv_ok]
    csv_cases += [{"text": t, **err_case(lambda t=t: A.parse_tidy_csv(t))} for t in csv_bad]

    csv_text = [{"x": x, "out": A.csv_text(x)} for x in
                ["=CMD|'/c calc'!A1", "+1", "-2", "@SUM(1)", "\tx", "\rx", "Crude oil, Brent", "", "a=b", "$/bbl", "'quoted"]]

    out = {
        "csv_text": csv_text,
        "csv": csv_cases,
        "datasets": {"seed": seed_ds, "alt": alt, "mixed": mixed},
        "synth": synth,
        "spread_defs": A.SPREADS,
        "code_groups": A.CODE_GROUPS,
        "name_keywords": A.NAME_KEYWORDS,
        "summarize": summarize,
        "zscore_percentile": zp,
        "rebase": rebase,
        "window": windows,
        "window_errors": [{"first": "2020-03", "last": "2020-01", **err_case(lambda: A.window(synth[0], "2020-03", "2020-01"))}],
        "combine": combine,
        "spreads": spreads,
        "movers": movers,
        "classify": classify,
        "format": fmt,
        "months": months,
        "month_errors": month_errors,
        "validate_ok": valid_ok,
        "validate_errors": valid_err,
    }
    text = json.dumps(out, allow_nan=False, separators=(",", ":"))
    for v in fmt_vals:
        assert math.isfinite(v)
    (ROOT / "tests" / "vectors.json").write_text(text + "\n", encoding="utf-8")
    print(f"wrote tests/vectors.json: {len(summarize)} summarize, {len(zp)} z/pct, {len(rebase)} rebase, "
          f"{len(combine)} combine, {len(movers)} movers, {len(fmt)} format, {len(valid_err)} validation errors")


if __name__ == "__main__":
    main()
