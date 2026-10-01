import csv, io, json, zipfile
from collections import defaultdict
from datetime import datetime
from statistics import median
import requests
import unittest

HIST_URL = "https://raw.githubusercontent.com/thiagosfsilva/ENSO-Monitor/main/data/levels/raw/cotasEstacao_14990000_CSV_2026-06-30T15_45_29.149Z.zip"
CUR_URL = "https://raw.githubusercontent.com/thiagosfsilva/ENSO-Monitor/main/data/levels/curData_14990000.csv"

def number(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text or text.lower() in {"na", "nan", "null", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None

def quantile_inc(values, p):
    a = sorted(values)
    h = (len(a) - 1) * p
    lo = int(h)
    hi = min(lo + 1, len(a) - 1)
    frac = h - lo
    return a[lo] + (a[hi] - a[lo]) * frac

def load_series():
    response = requests.get(HIST_URL, timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        member = next(n for n in archive.namelist() if n.endswith("14990000_Cotas.csv"))
        text = archive.read(member).decode("latin-1")
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if "Data;" in line and "Cota01" in line)
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[header:])), delimiter=";"))
    best = {}
    for row in rows:
        if number(row.get("MediaDiaria")) != 1:
            continue
        raw_date = str(row.get("Data", "")).strip()
        try:
            month_date = datetime.strptime(raw_date[:10], "%d/%m/%Y")
        except ValueError:
            continue
        consistency = int(number(row.get("NivelConsistencia")) or 0)
        key = (month_date.year, month_date.month)
        if key not in best or consistency > best[key][0]:
            best[key] = (consistency, row)

    series = {}
    for (year, month), (_, row) in best.items():
        for day in range(1, 32):
            try:
                dt = datetime(year, month, day)
            except ValueError:
                continue
            value = number(row.get(f"Cota{day:02d}"))
            if value is not None and value > 500:
                series[dt.date().isoformat()] = value / 100.0

    cur = requests.get(CUR_URL, timeout=60)
    cur.raise_for_status()
    for row in csv.DictReader(io.StringIO(cur.text)):
        dt = row.get("Dt", "")
        if not ("2015-01-01" <= dt < "2026-01-01"):
            continue
        try:
            value = float(row.get("Nivel", "nan"))
        except ValueError:
            continue
        if value > 500:
            series[dt] = value / 100.0
    return {d: v for d, v in series.items() if "1903-01-01" <= d < "2026-01-01"}

def summarize(series):
    out = {}
    by_year_month = defaultdict(list)
    for d, level in series.items():
        by_year_month[(int(d[:4]), int(d[5:7]))].append(level)
    for month in (8, 9, 10, 11, 12):
        pooled = [v for d, v in series.items() if int(d[5:7]) == month]
        monthly_means = [sum(vals)/len(vals) for (y,m), vals in by_year_month.items() if m == month]
        monthly_medians = [median(vals) for (y,m), vals in by_year_month.items() if m == month]
        out[f"{month:02d}"] = {
            "pooled_n": len(pooled),
            "pooled_q1": round(quantile_inc(pooled, .25), 4),
            "pooled_median": round(quantile_inc(pooled, .5), 4),
            "year_mean_q1": round(quantile_inc(monthly_means, .25), 4),
            "year_mean_median": round(quantile_inc(monthly_means, .5), 4),
            "year_median_q1": round(quantile_inc(monthly_medians, .25), 4),
            "year_median_median": round(quantile_inc(monthly_medians, .5), 4),
        }
    return out

class OctoberReferenceProbe(unittest.TestCase):
    def test_print_reference_candidates(self):
        series = load_series()
        result = summarize(series)
        print("MPHI_SERIES_RANGE=" + min(series) + ".." + max(series) + f" n={len(series)}")
        print("MPHI_SEASONAL_PROBE=" + json.dumps(result, sort_keys=True))
        for end_year in (2022, 2023, 2024, 2025):
            subset = {d: v for d, v in series.items() if int(d[:4]) <= end_year}
            s = summarize(subset)
            compact = {m: {"q1": s[m]["pooled_q1"], "median": s[m]["pooled_median"], "n": s[m]["pooled_n"]} for m in ("08", "09", "10")}
            print(f"MPHI_CUTOFF_{end_year}=" + json.dumps(compact, sort_keys=True))
        self.assertGreater(result["10"]["pooled_n"], 1000)

if __name__ == "__main__":
    unittest.main()
