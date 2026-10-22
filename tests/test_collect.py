import datetime as dt
import json

import pytest

from commodity_pulse import collect as C
from commodity_pulse.cli import main

from synthetic_workbook import CODES, NAMES, build_rows, build_xlsx, synthetic_value


def test_find_workbook_url_absolute_and_relative():
    html = ('<a href="https://thedocs.worldbank.org/en/doc/abc-0050012026/related/'
            'CMO-Historical-Data-Monthly.xlsx">October 2026 (XLS)</a>')
    assert C.find_workbook_url(html).endswith("abc-0050012026/related/CMO-Historical-Data-Monthly.xlsx")
    rel = "<a href='/en/doc/x/related/CMO-Historical-Data-Monthly.xlsx'>x</a>"
    assert C.find_workbook_url(rel) == "https://www.worldbank.org/en/doc/x/related/CMO-Historical-Data-Monthly.xlsx"


def test_find_workbook_url_missing_and_foreign_host():
    with pytest.raises(C.CollectError) as e:
        C.find_workbook_url("<a href='/other.xlsx'>no</a>")
    assert e.value.code == "no_link"
    with pytest.raises(C.CollectError) as e:
        C.find_workbook_url("<a href='https://evil.example/CMO-Historical-Data-Monthly.xlsx'>x</a>")
    assert e.value.code == "bad_url"
    with pytest.raises(C.CollectError):
        C.check_url("http://thedocs.worldbank.org/x.xlsx")
    with pytest.raises(C.CollectError):
        C.check_url("https://worldbank.org.evil.example/x.xlsx")
    C.check_url("https://thedocs.worldbank.org/x.xlsx")


@pytest.mark.parametrize("cell,want", [
    ("1960M01", "1960-01"), ("2026M9", "2026-09"), (" 1999m12 ", "1999-12"),
    (dt.datetime(2001, 3, 1), "2001-03"), ("1960M13", None), ("1960-01", None), (None, None), ("Title", None),
])
def test_parse_date_cell(cell, want):
    assert C.parse_date_cell(cell) == want


@pytest.mark.parametrize("cell,want", [
    (1.5, 1.5), (3, 3.0), ("2,345.5", 2345.5), ("..", None), ("…", None), ("", None), (None, None),
    (True, None), (float("nan"), None), ("n/a", None),
])
def test_parse_number(cell, want):
    assert C.parse_number(cell) == want


def test_parse_release():
    assert C.parse_release("Updated on October 02, 2026") == "2026-10-02"
    assert C.parse_release("updated on Jan 5 2026") == "2026-01-05"
    assert C.parse_release("no date here") is None


def test_parse_synthetic_workbook_with_codes():
    data = build_xlsx(build_rows(months=30))
    parsed = C.parse_workbook(data)
    assert parsed["release"] == "2026-10-02"
    rows = parsed["rows"]
    ids = {r["series_id"] for r in rows}
    assert ids == set(CODES)
    brent = [r for r in rows if r["series_id"] == "CRUDE_BRENT"]
    assert len(brent) == 30
    assert brent[0] == {"series_id": "CRUDE_BRENT", "name": "Crude oil, Brent", "unit": "$/bbl",
                        "date": "1960-01", "value": synthetic_value(1, 0)}
    assert brent[-1]["date"] == "1962-06"
    eur = [r for r in rows if r["series_id"] == "NGAS_EUR"]
    assert eur[0]["date"] == "1960-06" and len(eur) == 25
    maize = [r for r in rows if r["series_id"] == "MAIZE"]
    assert len(maize) == 29 and "1960-08" not in {r["date"] for r in maize}
    urea = [r for r in rows if r["series_id"] == "UREA_EE_BULK"][0]
    assert urea["name"] == "Urea"


def test_parse_without_code_row_uses_known_names():
    parsed = C.parse_workbook(build_xlsx(build_rows(months=3, with_codes=False)))
    ids = [r["series_id"] for r in parsed["rows"] if r["date"] == "1960-01"]
    assert ids[:3] == ["CRUDE_PETRO", "CRUDE_BRENT", "CRUDE_WTI"]
    assert "NGAS_US" in ids and "GOLD" in ids and "MAIZE" in ids


def test_unknown_name_without_code_gets_slug_and_dedup():
    rows = [["Title"], [None, "Widget price", "Widget price"], [None, "($/kg)", "($/kg)"], ["2000M01", 1, 2]]
    parsed = C.parse_rows(rows)
    assert [r["series_id"] for r in parsed["rows"]] == ["WIDGET_PRICE", "WIDGET_PRICE_2"]
    assert parsed["rows"][0]["unit"] == "$/kg"


def test_sheet_lookup_and_errors():
    with pytest.raises(C.CollectError) as e:
        C.parse_workbook(build_xlsx(build_rows(months=3), sheet="Annual Prices"))
    assert e.value.code == "no_sheet"
    with pytest.raises(C.CollectError) as e:
        C.parse_workbook(b"not a zip file")
    assert e.value.code == "bad_workbook"
    with pytest.raises(C.CollectError) as e:
        C.parse_rows([["Title"], [None, "a"]])
    assert e.value.code == "no_data"
    with pytest.raises(C.CollectError) as e:
        C.parse_rows([["Title"], [None, "A"], [None, "($/t)"], ["2000M01", ".."]])
    assert e.value.code == "no_data"
    with pytest.raises(C.CollectError) as e:
        C.parse_rows([[None, "A"], [None, "($/t)"], ["2000M01", 1], ["2000M01", 2]])
    assert e.value.code == "dup_date"


def test_to_dataset_roundtrip_and_gaps():
    parsed = C.parse_rows(build_rows(months=14))
    ds = C.to_dataset(parsed["rows"])
    by = {s["id"]: s for s in ds["series"]}
    assert by["NGAS_EUR"]["start"] == "1960-06" and len(by["NGAS_EUR"]["values"]) == 9
    assert by["MAIZE"]["values"][7] is None
    assert by["GOLD"]["group"] == "metals" and by["UREA_EE_BULK"]["group"] == "fertilizers"
    assert by["MAIZE"]["group"] == "agriculture" and by["NGAS_US"]["group"] == "energy"
    back = C.from_dataset(ds)
    key = lambda r: (r["series_id"], r["date"])  # noqa: E731
    assert sorted(back, key=key) == sorted(parsed["rows"], key=key)


def test_write_outputs_only_on_change(tmp_path):
    ds = C.to_dataset(C.parse_rows(build_rows(months=6))["rows"])
    assert C.write_outputs(ds, tmp_path, "https://thedocs.worldbank.org/x.xlsx", "2026-10-02", "2026-10-05T00:00:00+00:00")
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["release"] == "2026-10-02" and meta["latest_month"] == "1960-06"
    assert meta["license"]["name"].startswith("Creative Commons Attribution 4.0")
    first = (tmp_path / "monthly.json").read_text()
    assert not C.write_outputs(ds, tmp_path, "https://thedocs.worldbank.org/x.xlsx", "2026-10-02", "2026-10-12T00:00:00+00:00")
    assert json.loads((tmp_path / "meta.json").read_text())["fetched_at"] == "2026-10-05T00:00:00+00:00"
    assert C.write_outputs(ds, tmp_path, "https://thedocs.worldbank.org/x.xlsx", "2026-11-03")
    ds2 = C.to_dataset(C.parse_rows(build_rows(months=7))["rows"])
    assert C.write_outputs(ds2, tmp_path, "u", "2026-11-03")
    assert (tmp_path / "monthly.json").read_text() != first


def test_collect_from_local_xlsx_and_cli(tmp_path, capsys):
    x = tmp_path / "CMO-Historical-Data-Monthly.xlsx"
    x.write_bytes(build_xlsx(build_rows(months=26)))
    out = tmp_path / "data"
    assert main(["collect", "--out", str(out), "--xlsx", str(x)]) == 0
    assert "data changed" in capsys.readouterr().out
    assert main(["collect", "--out", str(out), "--xlsx", str(x)]) == 0
    assert "no change" in capsys.readouterr().out
    assert main(["parse", str(x)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "series_id,name,unit,date,value"
    assert lines[1].startswith("CRUDE_PETRO,") and len(lines) > 200
    assert main(["movers", "--data", str(out / "monthly.json"), "--by", "yoy", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 9 and rows[0]["yoy"] is not None
    assert main(["spreads", "--data", str(out / "monthly.json")]) == 0
    text = capsys.readouterr().out
    assert "Brent minus WTI" in text and "Gold / silver" in text


def test_cli_bad_inputs(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SystemExit):
        main(["movers", "--data", str(bad)])
    with pytest.raises(SystemExit):
        main(["movers", "--data", str(tmp_path / "missing.json")])
    bad.write_text(json.dumps({"series": []}))
    with pytest.raises(SystemExit):
        main(["spreads", "--data", str(bad)])
    assert main(["parse", str(tmp_path / "nope.xlsx")]) == 2
    junk = tmp_path / "junk.xlsx"
    junk.write_bytes(b"PK\x03\x04 nope")
    assert main(["parse", str(junk)]) == 2
    assert main(["collect", "--out", str(tmp_path / "o"), "--xlsx", str(junk)]) == 2


def test_names_constant_matches_codes():
    assert len(NAMES) == len(CODES)


# ------------------------------------------------------------ review fixes

def test_redirect_to_foreign_host_refused_before_following():
    import urllib.request
    h = C._CheckedRedirects()
    req = urllib.request.Request("https://www.worldbank.org/x")
    for bad in ("https://evil.example/CMO-Historical-Data-Monthly.xlsx", "http://thedocs.worldbank.org/x.xlsx"):
        with pytest.raises(C.CollectError) as e:
            h.redirect_request(req, None, 302, "Found", {}, bad)
        assert e.value.code == "bad_url"
    assert h.redirect_request(req, None, 302, "Found", {}, "https://thedocs.worldbank.org/x.xlsx") is not None


def test_collect_refuses_layout_without_core_series_and_writes_nothing(tmp_path):
    rows = build_rows(months=14)
    for r in rows:
        if r and r[0] is None and len(r) > 2 and r[2] == "CRUDE_BRENT":
            r[2] = "SOMETHING_ELSE"
    xlsx = tmp_path / "w.xlsx"
    xlsx.write_bytes(build_xlsx(rows))
    out = tmp_path / "data"
    with pytest.raises(C.CollectError) as e:
        C.collect(out, xlsx_path=xlsx)
    assert e.value.code == "unexpected_layout" and "CRUDE_BRENT" in str(e.value)
    assert not (out / "monthly.json").exists() and not (out / "meta.json").exists()


def test_cli_parse_neutralizes_formula_cells(tmp_path, capsys):
    rows = build_rows(months=3)
    for r in rows:
        if r and r[0] is None and len(r) > 2 and r[2] == "Crude oil, Brent":
            r[2] = "@SUM(A1)"
    xlsx = tmp_path / "w.xlsx"
    xlsx.write_bytes(build_xlsx(rows))
    assert main(["parse", str(xlsx)]) == 0
    out = capsys.readouterr().out
    assert ",'@SUM(A1)," in out and ",@SUM" not in out
