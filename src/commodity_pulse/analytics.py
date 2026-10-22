"""Pure analytics on monthly price series. No I/O.

A series is a dict with at least ``start`` ("YYYY-MM") and ``values`` (a list of
floats or None, one per consecutive calendar month from ``start``). A dataset is
``{"series": [series, ...]}``. The JavaScript core in web/app.html mirrors every
function here; web/parity.test.mjs checks them against tests/vectors.json.

All loops are written out by hand (no ``sum()``) so float results match the
JavaScript core operation for operation. Python 3.12 ``sum()`` uses compensated
summation and would drift from JavaScript in the last bits.
"""

from __future__ import annotations

import math
import re

MONTH_RE = re.compile(r"([0-9]{4})-([0-9]{2})")

GROUPS = ("energy", "metals", "agriculture", "fertilizers", "other")
GROUP_LABELS = {
    "energy": "Energy",
    "metals": "Metals",
    "agriculture": "Agriculture",
    "fertilizers": "Fertilizers",
    "other": "Other",
}

# World Bank Pink Sheet series codes by group. Codes not listed fall back to
# name keywords (see classify).
CODE_GROUPS = {
    "energy": [
        "CRUDE_PETRO", "CRUDE_BRENT", "CRUDE_DUBAI", "CRUDE_WTI", "COAL_AUS", "COAL_SAFRICA",
        "NGAS_US", "NGAS_EUR", "NGAS_JP", "INATGAS",
    ],
    "fertilizers": ["PHOSROCK", "DAP", "TSP", "UREA_EE_BULK", "POTASH"],
    "metals": [
        "ALUMINUM", "IRON_ORE", "COPPER", "LEAD", "TIN", "NICKEL", "ZINC", "GOLD", "PLATINUM", "SILVER",
    ],
    "agriculture": [
        "COCOA", "COFFEE_ARABIC", "COFFEE_ROBUS", "TEA_AVG", "TEA_COLOMBO", "TEA_KOLKATA", "TEA_MOMBASA",
        "COCONUT_OIL", "GRNUT", "FISH_MEAL", "GRNUT_OIL", "PALM_OIL", "PLMKRNL_OIL", "SOYBEANS",
        "SOYBEAN_OIL", "SOYBEAN_MEAL", "RAPESEED_OIL", "SUNFLOWER_OIL", "BARLEY", "MAIZE", "SORGHUM",
        "RICE_05", "RICE_25", "RICE_A1", "RICE_05_VNM", "WHEAT_US_SRW", "WHEAT_US_HRW", "BANANA_EU",
        "BANANA_US", "ORANGE", "BEEF", "CHICKEN", "LAMB", "SHRIMP_MEX", "SUGAR_EU", "SUGAR_US",
        "SUGAR_WLD", "TOBAC_US", "LOGS_CMR", "LOGS_MYS", "SAWNWD_CMR", "SAWNWD_MYS", "PLYWOOD",
        "COTTON_A_INDX", "RUBBER_TSR20", "RUBBER1_MYSG",
    ],
}

# Name keywords, checked in this order. Agriculture terms that contain an energy
# word ("palm oil") are caught because energy only matches "crude", not "oil".
NAME_KEYWORDS = [
    ("fertilizers", ["urea", "dap", "tsp", "phosphate", "potassium", "potash", "fertili"]),
    ("energy", ["crude", "coal", "natural gas", "lng", "liquefied"]),
    ("metals", ["aluminum", "aluminium", "copper", "iron ore", "lead", "nickel", "tin", "zinc",
                "gold", "silver", "platinum"]),
    ("agriculture", ["cocoa", "coffee", "tea", "oil", "meal", "soybean", "barley", "maize", "corn",
                     "sorghum", "rice", "wheat", "banana", "orange", "beef", "chicken", "lamb",
                     "shrimp", "sugar", "tobacco", "logs", "sawnwood", "plywood", "cotton", "rubber",
                     "groundnut"]),
]

_CODE_TO_GROUP = {}
for _g, _codes in CODE_GROUPS.items():
    for _c in _codes:
        _CODE_TO_GROUP[_c] = _g

WORD_RE = re.compile(r"[a-z]+")

# Spreads and ratios shown on the dashboard.
SPREADS = [
    {"id": "brent_wti", "label": "Brent minus WTI", "a": "CRUDE_BRENT", "b": "CRUDE_WTI", "op": "diff", "unit": "$/bbl"},
    {"id": "gas_eu_us", "label": "Europe gas (TTF) minus US gas (Henry Hub)", "a": "NGAS_EUR", "b": "NGAS_US", "op": "diff", "unit": "$/mmbtu"},
    {"id": "gas_eu_us_ratio", "label": "Europe gas / US gas", "a": "NGAS_EUR", "b": "NGAS_US", "op": "ratio", "unit": "ratio"},
    {"id": "urea_gas", "label": "Urea / Europe gas", "a": "UREA_EE_BULK", "b": "NGAS_EUR", "op": "ratio", "unit": "mmbtu/mt"},
    {"id": "gold_silver", "label": "Gold / silver", "a": "GOLD", "b": "SILVER", "op": "ratio", "unit": "ratio"},
]


class AnalyticsError(ValueError):
    """Bad input to an analytics function. ``code`` is stable for tests."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- months

def parse_month(s: str) -> int:
    """'YYYY-MM' to a month index (year * 12 + month - 1)."""
    m = MONTH_RE.fullmatch(s) if isinstance(s, str) else None
    if not m:
        raise AnalyticsError("bad_month", "Month must look like YYYY-MM.")
    y, mo = int(m.group(1)), int(m.group(2))
    if mo < 1 or mo > 12:
        raise AnalyticsError("bad_month", "Month must be 01 to 12.")
    return y * 12 + mo - 1


def format_month(idx: int) -> str:
    y = idx // 12
    mo = idx - y * 12 + 1
    return f"{y:04d}-{mo:02d}"


def month_add(s: str, n: int) -> str:
    return format_month(parse_month(s) + n)


def month_diff(a: str, b: str) -> int:
    """Months from b to a (a - b)."""
    return parse_month(a) - parse_month(b)


def _num(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    return None


def value_at(series: dict, month: str):
    i = month_diff(month, series["start"])
    vals = series["values"]
    if i < 0 or i >= len(vals):
        return None
    return _num(vals[i])


def end_month(series: dict) -> str:
    return month_add(series["start"], len(series["values"]) - 1)


def last_index(series: dict) -> int:
    """Index of the last non-null value, or -1."""
    vals = series["values"]
    i = len(vals) - 1
    while i >= 0 and _num(vals[i]) is None:
        i -= 1
    return i


# ---------------------------------------------------------------- changes

def pct_change(cur, prev):
    """(cur - prev) / |prev| x 100. None if either is missing or prev is 0."""
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev) * 100.0


def abs_change(cur, prev):
    if cur is None or prev is None:
        return None
    return cur - prev


def zscore(series: dict, idx: int, window: int = 12):
    """Z-score of value idx against the window months ending at idx (inclusive).

    z = (x_t - mean) / sd, sample sd (n - 1). Needs every month in the window.
    None if any month is missing or sd is 0.
    """
    if idx < window - 1:
        return None
    vals = series["values"]
    xs = []
    for k in range(idx - window + 1, idx + 1):
        v = _num(vals[k])
        if v is None:
            return None
        xs.append(v)
    total = 0.0
    for v in xs:
        total += v
    mean = total / window
    ss = 0.0
    for v in xs:
        d = v - mean
        ss += d * d
    sd = math.sqrt(ss / (window - 1))
    if sd == 0:
        return None
    return (xs[-1] - mean) / sd


def percentile(series: dict, idx: int):
    """Percentile rank of value idx among all non-null values up to and including idx.

    P = 100 x (count below + 0.5 x count equal) / n. Midrank convention, so the
    highest value of n distinct values scores 100 x (n - 0.5) / n.
    """
    vals = series["values"]
    x = _num(vals[idx]) if 0 <= idx < len(vals) else None
    if x is None:
        return None
    below = 0
    equal = 0
    n = 0
    for k in range(0, idx + 1):
        v = _num(vals[k])
        if v is None:
            continue
        n += 1
        if v < x:
            below += 1
        elif v == x:
            equal += 1
    return 100.0 * (below + 0.5 * equal) / n


def summarize(series: dict, kind: str = "pct") -> dict:
    """Latest value and its statistics.

    kind "pct": MoM and YoY are percent changes (prices).
    kind "abs": MoM and YoY are absolute changes (spreads and ratios, which can be
    zero or negative).
    """
    idx = last_index(series)
    if idx < 0:
        return {"id": series.get("id", ""), "date": None, "value": None, "mom": None, "yoy": None,
                "z12": None, "pct": None, "n": 0}
    vals = series["values"]
    cur = _num(vals[idx])
    prev = _num(vals[idx - 1]) if idx >= 1 else None
    year = _num(vals[idx - 12]) if idx >= 12 else None
    change = pct_change if kind == "pct" else abs_change
    n = 0
    for k in range(0, idx + 1):
        if _num(vals[k]) is not None:
            n += 1
    return {
        "id": series.get("id", ""),
        "date": month_add(series["start"], idx),
        "value": cur,
        "mom": change(cur, prev),
        "yoy": change(cur, year),
        "z12": zscore(series, idx, 12),
        "pct": percentile(series, idx),
        "n": n,
    }


# ---------------------------------------------------------------- transforms

def rebase(series: dict, base_month: str) -> dict:
    """Series scaled so base_month = 100. Values become None if the base is missing or 0."""
    b = value_at(series, base_month)
    out = []
    for v in series["values"]:
        x = _num(v)
        out.append(None if (x is None or b is None or b == 0) else x / b * 100.0)
    return {"id": series.get("id", ""), "start": series["start"], "values": out}


def window(series: dict, first: str, last: str) -> dict:
    """Values for first..last inclusive, None outside the series."""
    n = month_diff(last, first) + 1
    if n < 1:
        raise AnalyticsError("bad_range", "Range end must not be before range start.")
    out = []
    for k in range(n):
        out.append(value_at(series, month_add(first, k)))
    return {"id": series.get("id", ""), "start": first, "values": out}


def combine(a: dict, b: dict, op: str) -> dict:
    """Month-aligned a - b (op 'diff') or a / b (op 'ratio') over the overlap."""
    if op not in ("diff", "ratio"):
        raise AnalyticsError("bad_op", "op must be diff or ratio.")
    first = a["start"] if month_diff(a["start"], b["start"]) >= 0 else b["start"]
    ea, eb = end_month(a), end_month(b)
    last = ea if month_diff(ea, eb) <= 0 else eb
    n = month_diff(last, first) + 1
    out = []
    for k in range(max(n, 0)):
        m = month_add(first, k)
        x, y = value_at(a, m), value_at(b, m)
        if x is None or y is None:
            out.append(None)
        elif op == "diff":
            out.append(x - y)
        else:
            out.append(None if y == 0 else x / y)
    return {"id": a.get("id", "") + ("-" if op == "diff" else "/") + b.get("id", ""), "start": first, "values": out}


def find_series(dataset: dict, sid: str):
    for s in dataset.get("series", []):
        if s.get("id") == sid:
            return s
    return None


def spreads(dataset: dict, defs=None) -> list:
    """Summaries for each spread whose two legs exist in the dataset."""
    out = []
    for d in (SPREADS if defs is None else defs):
        a, b = find_series(dataset, d["a"]), find_series(dataset, d["b"])
        if a is None or b is None:
            continue
        s = combine(a, b, d["op"])
        s["id"] = d["id"]
        summ = summarize(s, "abs")
        out.append({"id": d["id"], "label": d["label"], "unit": d["unit"], "op": d["op"],
                    "a": d["a"], "b": d["b"], "series": s, "summary": summ})
    return out


def movers(dataset: dict, group: str | None = None, by: str = "mom", top: int | None = None) -> list:
    """Summaries for a group, sorted by |MoM| or |YoY| descending. Missing values sort last.

    Ties keep dataset order (stable sort).
    """
    if by not in ("mom", "yoy"):
        raise AnalyticsError("bad_sort", "by must be mom or yoy.")
    rows = []
    for s in dataset.get("series", []):
        if group is not None and s.get("group") != group:
            continue
        r = summarize(s, "pct")
        r["name"] = s.get("name", r["id"])
        r["unit"] = s.get("unit", "")
        r["group"] = s.get("group", "other")
        rows.append(r)

    def key(r):
        v = r[by]
        return (1, 0.0) if v is None else (0, -abs(v))

    rows.sort(key=key)
    return rows if top is None else rows[:top]


# ---------------------------------------------------------------- classify

def classify(code: str, name: str) -> str:
    g = _CODE_TO_GROUP.get((code or "").upper())
    if g:
        return g
    words = " ".join(WORD_RE.findall((name or "").lower()))
    padded = " " + words + " "
    for group, keys in NAME_KEYWORDS:
        for k in keys:
            if " " + k + " " in padded:
                return group
    return "other"


# ---------------------------------------------------------------- formatting

def round_half_away(x: float, decimals: int) -> str:
    """Fixed-point string, halves away from zero, decided on the shortest decimal repr.

    Python repr and JavaScript String() give the same shortest round-trip digits,
    so both sides round the same decimal string and agree exactly.
    """
    if x is None or not math.isfinite(x):
        return ""
    neg = x < 0
    s = _plain_digits(abs(x))
    if "." in s:
        ip, fp = s.split(".")
    else:
        ip, fp = s, ""
    if len(fp) <= decimals:
        fp = fp + "0" * (decimals - len(fp))
        digits = ip + fp
    else:
        digits = ip + fp[:decimals]
        if fp[decimals] >= "5":
            digits = _increment(digits)
    if decimals > 0:
        ip2, fp2 = digits[:-decimals] or "0", digits[-decimals:]
        out = ip2.lstrip("0") or "0"
        out = out + "." + fp2
    else:
        out = digits.lstrip("0") or "0"
    if neg and out.strip("0.") != "":
        out = "-" + out
    return out


def _plain_digits(x: float) -> str:
    r = repr(float(x))
    if "e" not in r and "E" not in r:
        return r
    mant, exp = r.lower().split("e")
    e = int(exp)
    if "." in mant:
        ip, fp = mant.split(".")
    else:
        ip, fp = mant, ""
    digits = ip + fp
    point = len(ip) + e
    if point <= 0:
        return "0." + "0" * (-point) + digits
    if point >= len(digits):
        return digits + "0" * (point - len(digits))
    return digits[:point] + "." + digits[point:]


def _increment(digits: str) -> str:
    ds = list(digits)
    i = len(ds) - 1
    while i >= 0:
        if ds[i] == "9":
            ds[i] = "0"
            i -= 1
        else:
            ds[i] = str(int(ds[i]) + 1)
            return "".join(ds)
    return "1" + "".join(ds)


def _group_thousands(s: str) -> str:
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    ip, _, fp = s.partition(".")
    parts = []
    while len(ip) > 3:
        parts.insert(0, ip[-3:])
        ip = ip[:-3]
    parts.insert(0, ip)
    out = ",".join(parts) + ("." + fp if fp else "")
    return ("-" if neg else "") + out


def value_decimals(x: float) -> int:
    a = abs(x)
    if a >= 1000:
        return 0
    if a >= 100:
        return 1
    return 2


def format_value(x) -> str:
    """Price display: 0 decimals at 1,000 and above, 1 at 100 and above, else 2."""
    if x is None or not math.isfinite(x):
        return "n/a"
    return _group_thousands(round_half_away(x, value_decimals(x)))


def format_pct(x, decimals: int = 1) -> str:
    """Signed percent, e.g. +3.4% or -0.2%. Zero shows as 0.0%."""
    if x is None or not math.isfinite(x):
        return "n/a"
    s = round_half_away(x, decimals)
    if not s.startswith("-") and s.strip("0.") != "":
        s = "+" + s
    return s + "%"


def format_signed(x, decimals: int = 2) -> str:
    if x is None or not math.isfinite(x):
        return "n/a"
    s = _group_thousands(round_half_away(x, decimals))
    if not s.startswith("-") and s.strip("0.,") != "":
        s = "+" + s
    return s


# ---------------------------------------------------------------- validation

ID_RE = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
MAX_SERIES = 500
MAX_POINTS_PER_SERIES = 2400
MAX_POINTS = 1_000_000


def validate_dataset(obj) -> dict:
    """Check a monthly.json-shaped object and return a normalized copy.

    Normalized series carry id, name, unit, group, start, values. Unknown groups
    are replaced by classify(). Numbers must be finite; null marks a missing month.
    """
    if not isinstance(obj, dict) or not isinstance(obj.get("series"), list):
        raise AnalyticsError("bad_shape", "Data must be an object with a series list.")
    raw = obj["series"]
    if len(raw) == 0:
        raise AnalyticsError("empty", "Data has no series.")
    if len(raw) > MAX_SERIES:
        raise AnalyticsError("too_many_series", "Data has more than " + str(MAX_SERIES) + " series.")
    out = []
    seen = set()
    total = 0
    for i, s in enumerate(raw):
        where = "Series " + str(i + 1)
        if not isinstance(s, dict):
            raise AnalyticsError("bad_series", where + " is not an object.")
        sid = s.get("id")
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
            raise AnalyticsError("bad_id", where + " has a missing or invalid id.")
        if sid in seen:
            raise AnalyticsError("dup_id", "Series id " + sid + " appears twice.")
        seen.add(sid)
        name = s.get("name", sid)
        unit = s.get("unit", "")
        if not isinstance(name, str) or len(name) > 200:
            raise AnalyticsError("bad_name", "Series " + sid + " has an invalid name.")
        if not isinstance(unit, str) or len(unit) > 40:
            raise AnalyticsError("bad_unit", "Series " + sid + " has an invalid unit.")
        start = s.get("start")
        try:
            parse_month(start)
        except AnalyticsError:
            raise AnalyticsError("bad_start", "Series " + sid + " has an invalid start month.") from None
        vals = s.get("values")
        if not isinstance(vals, list) or len(vals) == 0:
            raise AnalyticsError("bad_values", "Series " + sid + " has no values list.")
        if len(vals) > MAX_POINTS_PER_SERIES:
            raise AnalyticsError("too_long", "Series " + sid + " has more than " + str(MAX_POINTS_PER_SERIES) + " months.")
        total += len(vals)
        if total > MAX_POINTS:
            raise AnalyticsError("too_many_points", "Data has more than " + str(MAX_POINTS) + " values.")
        clean = []
        for k, v in enumerate(vals):
            if v is None:
                clean.append(None)
                continue
            x = _num(v)
            if x is None:
                raise AnalyticsError("bad_value", "Series " + sid + " value " + str(k + 1) + " is not a finite number.")
            clean.append(x)
        group = s.get("group")
        if group not in GROUPS:
            group = classify(sid, name)
        out.append({"id": sid, "name": name or sid, "unit": unit, "group": group, "start": start, "values": clean})
    return {"series": out}


# ---------------------------------------------------------------- CSV export

FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def csv_text(s) -> str:
    """Text for a CSV export cell, safe to open in a spreadsheet.

    A leading = + - @ tab or carriage return makes Excel, LibreOffice and Sheets
    treat the cell as a formula, so those cells get a leading single quote.
    Apply to text fields only (ids, names, units), never to numbers.
    """
    s = "" if s is None else str(s)
    return "'" + s if s[:1] in FORMULA_LEADS and s else s


# ---------------------------------------------------------------- tidy CSV

MAX_CSV_ROWS = 50000
MISSING_TOKENS = ("", "..", "\u2026", "nan", "na", "n/a", "null", "none", "-")
NUM_RE = re.compile(r"[+-]?([0-9]+[.]?[0-9]*|[.][0-9]+)([eE][+-]?[0-9]+)?")
CSV_DATE_RE = re.compile(r"([0-9]{4})(?:-|M|m)([0-9]{1,2})")
ID_KEYS = ("series_id", "id", "series", "code")


def _split_csv_line(line: str, delim: str, lineno: int) -> list:
    fields = []
    cur = ""
    inq = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if inq:
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    cur += '"'
                    i += 2
                    continue
                inq = False
                i += 1
                continue
            cur += ch
            i += 1
            continue
        if ch == '"' and cur.strip(" \t") == "":
            cur = ""
            inq = True
            i += 1
            continue
        if ch == delim:
            fields.append(cur)
            cur = ""
            i += 1
            continue
        cur += ch
        i += 1
    if inq:
        raise AnalyticsError("bad_csv", "Line " + str(lineno) + " has an unterminated quote.")
    fields.append(cur)
    return [f.strip(" \t") for f in fields]


def parse_tidy_csv(text: str) -> dict:
    """Tidy rows (series_id, name, unit, date, value) to a validated dataset.

    Comma or tab separated (decided by the first non-blank line), optional header,
    double quotes allowed within a line. Without a header: 5 columns
    (series_id, name, unit, date, value) or 3 (series_id, date, value). With a
    header the columns can come in any order and extra columns are ignored.
    Dates: YYYY-MM or YYYYMmm. Missing values ("", "..", NaN, n/a) are skipped.
    """
    if not isinstance(text, str):
        raise AnalyticsError("bad_csv", "Input must be text.")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    delim = None
    cols = None
    rows = 0
    by = {}
    order = []
    for ln, line in enumerate(lines, start=1):
        if line.strip(" \t") == "":
            continue
        if delim is None:
            delim = "\t" if "\t" in line else ","
        f = _split_csv_line(line, delim, ln)
        if all(x == "" for x in f):
            continue
        if cols is None:
            low = [x.lower() for x in f]
            if "date" in low and "value" in low:
                idc = None
                for k in ID_KEYS:
                    if k in low:
                        idc = low.index(k)
                        break
                if idc is None:
                    raise AnalyticsError("bad_header", "Header needs a series_id column.")
                cols = {"id": idc, "date": low.index("date"), "value": low.index("value"),
                        "name": low.index("name") if "name" in low else None,
                        "unit": low.index("unit") if "unit" in low else None}
                continue
            if len(f) == 5:
                cols = {"id": 0, "name": 1, "unit": 2, "date": 3, "value": 4}
            elif len(f) == 3:
                cols = {"id": 0, "name": None, "unit": None, "date": 1, "value": 2}
            else:
                raise AnalyticsError("bad_columns", "Line " + str(ln) +
                                     ": expected 3 or 5 columns (series_id, [name, unit,] date, value).")
        need = -1
        for k in ("id", "name", "unit", "date", "value"):
            if cols[k] is not None and cols[k] > need:
                need = cols[k]
        if len(f) <= need:
            raise AnalyticsError("bad_columns", "Line " + str(ln) + " has too few columns.")
        rows += 1
        if rows > MAX_CSV_ROWS:
            raise AnalyticsError("too_many_rows", "More than 50,000 rows. Load monthly.json for long histories.")
        sid = f[cols["id"]]
        if not ID_RE.fullmatch(sid):
            raise AnalyticsError("bad_id", "Line " + str(ln) + ": series id must be 1 to 64 letters, digits, _ . or -.")
        dm = CSV_DATE_RE.fullmatch(f[cols["date"]])
        mo = int(dm.group(2)) if dm else 0
        if not dm or mo < 1 or mo > 12:
            raise AnalyticsError("bad_date", "Line " + str(ln) + ": date must be YYYY-MM or YYYYMmm.")
        mi = int(dm.group(1)) * 12 + mo - 1
        raw = f[cols["value"]]
        if raw.lower() in MISSING_TOKENS:
            continue
        if not NUM_RE.fullmatch(raw):
            raise AnalyticsError("bad_value", "Line " + str(ln) + ": value is not a number.")
        v = float(raw)
        if not math.isfinite(v):
            raise AnalyticsError("bad_value", "Line " + str(ln) + ": value is not a finite number.")
        if sid not in by:
            name = f[cols["name"]] if cols["name"] is not None else ""
            unit = f[cols["unit"]] if cols["unit"] is not None else ""
            by[sid] = {"name": name or sid, "unit": unit, "points": {}, "lo": mi, "hi": mi}
            order.append(sid)
        rec = by[sid]
        if mi in rec["points"]:
            raise AnalyticsError("dup_month", "Line " + str(ln) + ": a month repeats for series " + sid + ".")
        rec["points"][mi] = v
        if mi < rec["lo"]:
            rec["lo"] = mi
        if mi > rec["hi"]:
            rec["hi"] = mi
    if not order:
        raise AnalyticsError("empty", "No data rows found.")
    series = []
    for sid in order:
        rec = by[sid]
        span = rec["hi"] - rec["lo"] + 1
        if span > MAX_POINTS_PER_SERIES:
            raise AnalyticsError("too_long", "Series " + sid + " has more than " + str(MAX_POINTS_PER_SERIES) + " months.")
        vals = []
        for k in range(rec["lo"], rec["hi"] + 1):
            vals.append(rec["points"].get(k))
        series.append({"id": sid, "name": rec["name"], "unit": rec["unit"], "group": classify(sid, rec["name"]),
                       "start": format_month(rec["lo"]), "values": vals})
    return validate_dataset({"series": series})
