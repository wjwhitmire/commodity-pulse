import math
import pathlib
import statistics
import sys

import pytest

from commodity_pulse import analytics as A

ROOT = pathlib.Path(__file__).resolve().parent.parent


def S(values, start="2020-01", sid="X", **kw):
    return dict({"id": sid, "start": start, "values": values}, **kw)


# ------------------------------------------------------------ months

def test_month_math():
    assert A.parse_month("1960-01") == 1960 * 12
    assert A.format_month(A.parse_month("2026-09")) == "2026-09"
    assert A.month_add("2025-11", 3) == "2026-02"
    assert A.month_add("2026-01", -1) == "2025-12"
    assert A.month_diff("2026-09", "2025-09") == 12


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-01", "2026-1", "2026-01\n", "x", None, 202601])
def test_bad_month(bad):
    with pytest.raises(A.AnalyticsError) as e:
        A.parse_month(bad)
    assert e.value.code == "bad_month"


# ------------------------------------------------------------ changes

def test_pct_and_abs_change():
    assert A.pct_change(110, 100) == pytest.approx(10.0)
    assert A.pct_change(90, 100) == pytest.approx(-10.0)
    assert A.pct_change(-5, -10) == pytest.approx(50.0)  # |prev| in the denominator
    assert A.pct_change(1, 0) is None
    assert A.pct_change(None, 1) is None
    assert A.abs_change(3.5, 1.0) == 2.5
    assert A.abs_change(None, 1) is None


def test_summarize_hand_checked():
    vals = [100.0 + k for k in range(13)] + [130.0]
    r = A.summarize(S(vals))
    assert r["date"] == "2021-02"
    assert r["value"] == 130.0
    assert r["mom"] == pytest.approx((130 - 112) / 112 * 100)
    assert r["yoy"] == pytest.approx((130 - 101) / 101 * 100)
    window = vals[-12:]
    z = (130 - statistics.mean(window)) / statistics.stdev(window)
    assert r["z12"] == pytest.approx(z, rel=1e-12)
    assert r["pct"] == pytest.approx(100 * 13.5 / 14)
    assert r["n"] == 14


def test_summarize_trailing_nulls_and_short():
    r = A.summarize(S([1.0, 2.0, None, None]))
    assert r["date"] == "2020-02" and r["mom"] == pytest.approx(100.0) and r["yoy"] is None and r["z12"] is None
    assert A.summarize(S([None, None]))["value"] is None
    r = A.summarize(S([5.0]))
    assert r["mom"] is None and r["pct"] == 50.0


def test_summarize_abs_kind_for_spreads():
    r = A.summarize(S([1.0, -2.0]), "abs")
    assert r["mom"] == -3.0


def test_zscore_rules():
    flat = S([4.0] * 12)
    assert A.zscore(flat, 11) is None  # sd 0
    gap = S([1.0] * 5 + [None] + [2.0] * 6)
    assert A.zscore(gap, 11) is None
    assert A.zscore(S([1.0, 2.0]), 1) is None  # not enough history
    vals = [float(k * k) for k in range(15)]
    w = vals[3:15]
    assert A.zscore(S(vals), 14) == pytest.approx((vals[14] - statistics.mean(w)) / statistics.stdev(w), rel=1e-12)
    assert A.zscore(S([1.0, 3.0, 2.0]), 2, window=3) == pytest.approx(0.0)


def test_percentile_midrank():
    s = S([3.0, 1.0, 2.0, None, 2.0])
    assert A.percentile(s, 4) == pytest.approx(100 * (1 + 0.5 * 2) / 4)
    assert A.percentile(s, 1) == pytest.approx(100 * 0.5 / 2)
    assert A.percentile(s, 3) is None
    assert A.percentile(s, 99) is None


# ------------------------------------------------------------ transforms

def test_rebase_and_window():
    s = S([50.0, 100.0, None, 200.0])
    r = A.rebase(s, "2020-02")
    assert r["values"] == [50.0, 100.0, None, 200.0]
    assert A.rebase(s, "2020-03")["values"] == [None] * 4
    assert A.rebase(s, "2019-01")["values"] == [None] * 4
    assert A.rebase(S([0.0, 1.0]), "2020-01")["values"] == [None, None]
    w = A.window(s, "2019-12", "2020-02")
    assert w == {"id": "X", "start": "2019-12", "values": [None, 50.0, 100.0]}
    with pytest.raises(A.AnalyticsError):
        A.window(s, "2020-03", "2020-01")


def test_combine_alignment():
    a = S([10.0, 11.0, 12.0, 13.0], start="2020-01", sid="A")
    b = S([2.0, 0.0, 4.0], start="2020-02", sid="B")
    d = A.combine(a, b, "diff")
    assert d == {"id": "A-B", "start": "2020-02", "values": [9.0, 12.0, 9.0]}
    r = A.combine(a, b, "ratio")
    assert r["values"] == [5.5, None, 3.25]
    assert A.combine(a, S([1.0], start="2021-01"), "diff")["values"] == []
    with pytest.raises(A.AnalyticsError):
        A.combine(a, b, "sum")


def test_spreads_and_movers():
    ds = {"series": [
        S([80.0, 90.0], sid="CRUDE_BRENT", group="energy", name="Brent"),
        S([75.0, 80.0], sid="CRUDE_WTI", group="energy", name="WTI"),
        S([3000.0, 3300.0], sid="GOLD", group="metals", name="Gold"),
        S([30.0, 30.0], sid="SILVER", group="metals", name="Silver"),
        S([None, None], sid="EMPTY", group="metals", name="Empty"),
    ]}
    sp = {s["id"]: s for s in A.spreads(ds)}
    assert set(sp) == {"brent_wti", "gold_silver"}
    assert sp["brent_wti"]["summary"]["value"] == 10.0 and sp["brent_wti"]["summary"]["mom"] == 5.0
    assert sp["gold_silver"]["summary"]["value"] == pytest.approx(110.0)
    m = A.movers(ds)
    assert [r["id"] for r in m] == ["CRUDE_BRENT", "GOLD", "CRUDE_WTI", "SILVER", "EMPTY"]
    assert [r["id"] for r in A.movers(ds, "metals", top=1)] == ["GOLD"]
    with pytest.raises(A.AnalyticsError):
        A.movers(ds, by="qoq")


@pytest.mark.parametrize("code,name,group", [
    ("CRUDE_BRENT", "x", "energy"), ("ZZ", "Natural gas, Europe", "energy"), ("ZZ", "Palm oil", "agriculture"),
    ("ZZ", "Urea, E. Europe", "fertilizers"), ("ZZ", "Iron ore, cfr spot", "metals"), ("ZZ", "Tin", "metals"),
    ("ZZ", "Tobacco, US import u.v.", "agriculture"), ("ZZ", "Mystery index", "other"), ("POTASH", "", "fertilizers"),
])
def test_classify(code, name, group):
    assert A.classify(code, name) == group


# ------------------------------------------------------------ formatting

@pytest.mark.parametrize("x,d,want", [
    (1.005, 2, "1.01"), (2.5, 0, "3"), (-2.5, 0, "-3"), (0.125, 2, "0.13"), (-0.004, 2, "0.00"),
    (1e-7, 2, "0.00"), (123456.789, 1, "123456.8"), (9.995, 2, "10.00"), (0.0, 1, "0.0"), (12, 0, "12"),
])
def test_round_half_away(x, d, want):
    assert A.round_half_away(x, d) == want


def test_format_helpers():
    assert A.format_value(14474.0) == "14,474"
    assert A.format_value(116.8) == "116.8"
    assert A.format_value(2.95) == "2.95"
    assert A.format_value(-1234.5) == "-1,235"
    assert A.format_value(None) == "n/a"
    assert A.format_pct(3.44) == "+3.4%"
    assert A.format_pct(-0.04) == "0.0%"
    assert A.format_pct(0.0) == "0.0%"
    assert A.format_pct(float("nan")) == "n/a"
    assert A.format_signed(1234.567) == "+1,234.57"
    assert A.format_signed(-0.001) == "0.00"


# ------------------------------------------------------------ validation

def test_validate_dataset_ok_and_normalizes():
    ds = A.validate_dataset({"series": [{"id": "GOLD", "start": "2020-01", "values": [1, None, 2.5]}]})
    s = ds["series"][0]
    assert s["group"] == "metals" and s["name"] == "GOLD" and s["values"] == [1.0, None, 2.5]


@pytest.mark.parametrize("obj,code", [
    ([], "bad_shape"), ({"series": []}, "empty"), ({"series": [1]}, "bad_series"),
    ({"series": [{"id": "a b", "start": "2020-01", "values": [1]}]}, "bad_id"),
    ({"series": [{"id": "A", "start": "2020-01", "values": [1]}, {"id": "A", "start": "2020-01", "values": [1]}]}, "dup_id"),
    ({"series": [{"id": "A", "start": "2020-13", "values": [1]}]}, "bad_start"),
    ({"series": [{"id": "A", "start": "2020-01", "values": []}]}, "bad_values"),
    ({"series": [{"id": "A", "start": "2020-01", "values": ["1"]}]}, "bad_value"),
    ({"series": [{"id": "A", "start": "2020-01", "values": [True]}]}, "bad_value"),
    ({"series": [{"id": "A", "start": "2020-01", "values": [1], "unit": 5}]}, "bad_unit"),
    ({"series": [{"id": "A", "start": "2020-01", "values": [0.0] * 2401}]}, "too_long"),
])
def test_validate_dataset_errors(obj, code):
    with pytest.raises(A.AnalyticsError) as e:
        A.validate_dataset(obj)
    assert e.value.code == code


# ------------------------------------------------------------ real seed data

def test_seed_data_real_values():
    sys.path.insert(0, str(ROOT / "scripts"))
    from seed_from_pdf import load_seed

    ds = load_seed()[0]
    by = {s["id"]: s for s in ds["series"]}
    assert A.value_at(by["CRUDE_BRENT"], "2026-09") == 116.8
    assert A.value_at(by["GOLD"], "2026-09") == 4319
    sp = {s["id"]: s["summary"] for s in A.spreads(ds)}
    assert sp["brent_wti"]["value"] == pytest.approx(19.9)
    assert sp["gold_silver"]["value"] == pytest.approx(4319 / 64.6)
    r = A.summarize(by["CRUDE_BRENT"])
    assert r["yoy"] == pytest.approx((116.8 - 68.0) / 68.0 * 100)
    for s in ds["series"]:
        assert s["group"] in ("energy", "metals", "agriculture", "fertilizers")
        assert all(v is not None and math.isfinite(v) and v > 0 for v in s["values"])


# ------------------------------------------------------------ tidy CSV

def test_parse_tidy_csv_header_any_order_and_missing():
    ds = A.parse_tidy_csv("﻿date,value,series_id,extra\r\n2026-01,1.5,A,x\r\n2026-03,2,A,y\r\n2026-02,..,A,z\r\n")
    assert ds["series"][0]["values"] == [1.5, None, 2.0] and ds["series"][0]["start"] == "2026-01"


def test_parse_tidy_csv_quotes_tabs_and_groups():
    ds = A.parse_tidy_csv('CRUDE_BRENT,"Crude oil, Brent",$/bbl,2026-09,116.8\nCRUDE_BRENT,"Crude oil, Brent",$/bbl,2026M08,90.9')
    s = ds["series"][0]
    assert s["name"] == "Crude oil, Brent" and s["start"] == "2026-08" and s["values"] == [90.9, 116.8]
    assert s["group"] == "energy"
    ds = A.parse_tidy_csv("A\t2020-01\t1\nB\t2020-02\t2")
    assert [x["id"] for x in ds["series"]] == ["A", "B"]


@pytest.mark.parametrize("text,code", [
    ("", "empty"), ("a,b\n", "bad_columns"), ("A,2026-13,1", "bad_date"), ("A,2026-01,abc", "bad_value"),
    ("A,2026-01,1\nA,2026-01,2", "dup_month"), ("bad id,2026-01,1", "bad_id"), ('A,"2026-01,1', "bad_csv"),
    ("name,date,value\nx,2026-01,1", "bad_header"), ("A,2026-01,1e999", "bad_value"),
    ("A,1800-01,1\nA,2026-01,2", "too_long"),
])
def test_parse_tidy_csv_errors(text, code):
    with pytest.raises(A.AnalyticsError) as e:
        A.parse_tidy_csv(text)
    assert e.value.code == code


def test_parse_tidy_csv_row_cap():
    text = "\n".join(f"S{k % 40},{1960 + (k // 40) // 12}-{(k // 40) % 12 + 1:02d},1" for k in range(50001))
    with pytest.raises(A.AnalyticsError) as e:
        A.parse_tidy_csv(text)
    assert e.value.code == "too_many_rows"


# ------------------------------------------------------------ review fixes

def test_csv_text_neutralizes_formula_leads():
    for s in ("=CMD|'/c calc'!A1", "+1", "-2", "@SUM(1)", "\tx", "\rx"):
        assert A.csv_text(s) == "'" + s
    for s in ("Crude oil, Brent", "", "a=b", "$/bbl", None):
        assert A.csv_text(s) == ("" if s is None else s)


# Values re-read from the five cited Pink Sheet PDFs during review, one per
# energy, metals, agriculture and fertilizer row across all five editions.
PDF_SPOT_CHECKS = [
    ("CRUDE_BRENT", "2025-07", 71.0), ("CRUDE_BRENT", "2026-04", 120.4), ("CRUDE_BRENT", "2026-09", 116.8),
    ("CRUDE_WTI", "2026-03", 91.2), ("CRUDE_WTI", "2026-09", 96.9), ("NGAS_US", "2026-01", 7.58),
    ("NGAS_US", "2026-09", 2.95), ("NGAS_EUR", "2025-12", 9.48), ("NGAS_EUR", "2026-09", 25.42),
    ("GOLD", "2026-02", 5020), ("GOLD", "2025-10", 4058), ("SILVER", "2026-01", 92.1), ("SILVER", "2026-09", 64.6),
    ("COPPER", "2025-12", 11785), ("COPPER", "2026-09", 14474), ("UREA_EE_BULK", "2026-04", 856.9),
    ("UREA_EE_BULK", "2026-09", 407.5), ("WHEAT_US_HRW", "2025-11", 245.9), ("WHEAT_US_HRW", "2026-09", 347.0),
    ("MAIZE", "2025-08", 185.5), ("MAIZE", "2026-06", 197.1), ("DAP", "2026-01", 619.2), ("COCOA", "2026-03", 3.24),
]


def test_seed_matches_pdf_spot_checks_and_drops_unconfirmed_series():
    sys.path.insert(0, str(ROOT / "scripts"))
    from seed_from_pdf import load_seed

    ds = load_seed()[0]
    by = {s["id"]: s for s in ds["series"]}
    for sid, month, want in PDF_SPOT_CHECKS:
        assert A.value_at(by[sid], month) == want, (sid, month)
    # Japan LNG: latest months are estimates the World Bank revises; not confirmable from the PDFs.
    assert "NGAS_JP" not in by and len(by) == 38


def test_seed_matches_printed_quarterly_averages():
    sys.path.insert(0, str(ROOT / "scripts"))
    from seed_from_pdf import load_seed

    by = {s["id"]: s["values"] for s in load_seed()[0]["series"]}
    printed = {"CRUDE_BRENT": [69.0, 63.7, 80.5, 104.4, 97.1], "NGAS_EUR": [11.29, 10.26, 13.63, 15.58, 21.53],
               "GOLD": [3459, 4152, 4876, 4512, 4268], "UREA_EE_BULK": [488.3, 398.7, 537.7, 693.5, 399.2],
               "MAIZE": [191.6, 201.9, 208.9, 209.1, 225.7], "SILVER": [39.6, 54.1, 84.0, 73.5, 62.9]}
    for sid, qs in printed.items():
        step = 1.0 if isinstance(qs[0], int) else (0.01 if sid == "NGAS_EUR" else 0.1)
        for q, want in enumerate(qs):
            got = (by[sid][3 * q] + by[sid][3 * q + 1] + by[sid][3 * q + 2]) / 3
            assert abs(got - want) <= step + 1e-9, (sid, q, got, want)
