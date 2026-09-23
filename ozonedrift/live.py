"""testing-new live forecaster (P-live in testing_new/PREREGISTRATION.md).

Once a day, from AirNow's keyless hourly files, rebuild day D's core features
per HGB site the way EPA's AQS daily summaries do, forecast exceedance on D+1
with the final model F and with main's benchmark-trained model, and verify the
forecasts made for D. Local standard time (UTC-6), like AQS "Date Local".

    python -m ozonedrift.live          # appends to testing_new/live_forecasts.csv
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

from .aqs import HGB_COUNTIES, NAAQS_8H_OZONE_PPM, TEXAS

URL = "https://files.airnowtech.org/airnow/{y}/{ymd}/HourlyData_{ymdh}.dat"
LST = timedelta(hours=-6)
OUT = Path("testing_new")
FORECASTS = OUT / "live_forecasts.csv"
FEATURES = OUT / "live_features.csv"
COLS = ["issued_utc", "feature_date", "target_date", "site", "o3_max8h_today", "p_F", "p_main",
        "thr_F", "thr_main", "status", "actual_o3_max8h", "y"]
PARAMS = {"OZONE", "TEMP", "RWS", "RWD"}


def _hour_file(t_utc: datetime) -> list[list[str]]:
    u = URL.format(y=f"{t_utc:%Y}", ymd=f"{t_utc:%Y%m%d}", ymdh=f"{t_utc:%Y%m%d%H}")
    for attempt in range(3):
        try:
            r = requests.get(u, timeout=60)
            if r.status_code == 200:
                return [ln.split("|") for ln in r.text.splitlines()]
            if r.status_code == 404:
                return []
        except requests.RequestException:
            pass
    return []


def hourly(day: date) -> dict:
    """{site: {param: {lst_hour_index: value}}} for LST hours of `day` 00..23 plus the next 7
    (8-hour averages starting late in the day run into the following morning)."""
    out: dict = defaultdict(lambda: defaultdict(dict))
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - LST     # 00 LST in UTC
    for h in range(31):
        for row in _hour_file(start + timedelta(hours=h)):
            if len(row) < 8 or row[5] not in PARAMS:
                continue
            aqsid = row[2]
            if not (aqsid.startswith(TEXAS) and aqsid[2:5] in HGB_COUNTIES and len(aqsid) == 9):
                continue
            try:
                v = float(row[7])
            except ValueError:
                continue
            out[f"{aqsid[:2]}-{aqsid[2:5]}-{aqsid[5:]}"][row[5]][h] = v
    return out


def o3_max8h(o3: dict) -> float | None:
    """Daily max of 8-hour running averages starting 00-23 LST, >= 6 of 8 hours present (ppm, truncated)."""
    best = None
    for s in range(24):
        vals = [o3[h] for h in range(s, s + 8) if h in o3]
        if len(vals) >= 6:
            avg = sum(vals) / len(vals)
            best = avg if best is None else max(best, avg)
    return None if best is None else math.floor(best) / 1000.0      # ppb -> ppm, EPA truncation


def day_features(day: date) -> pd.DataFrame:
    rows = []
    hrs = hourly(day)
    for site, p in hrs.items():
        today = {k: {h: v for h, v in p[k].items() if h < 24} for k in ("TEMP", "RWS", "RWD")}
        row = {"site": site, "date": pd.Timestamp(day), "o3_max8h": o3_max8h(p.get("OZONE", {}))}
        for key, name, conv in (("TEMP", "outdoor_temperature", lambda c: c * 9 / 5 + 32),
                                ("RWS", "wind_speed_resultant", lambda x: x),
                                ("RWD", "wind_direction_resultant", lambda x: x)):
            vals = [conv(v) for v in today[key].values()]
            row[f"{name}_mean"] = float(np.mean(vals)) if vals else np.nan
            row[f"{name}_max"] = float(np.max(vals)) if vals else np.nan
        rows.append(row)
    f = pd.DataFrame(rows)
    if f.empty:
        return f
    doy = f.date.dt.dayofyear
    f["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    f["day_of_week"] = f.date.dt.dayofweek
    f["airshed_o3_max"] = f.o3_max8h.max()
    return f


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day = (now + LST).date() - timedelta(days=1)          # the last complete LST day
    feats = day_features(day)
    rows = _read(FORECASTS)
    done_days = {r["feature_date"] for r in rows}
    summary = {"feature_date": str(day), "sites_with_data": int(len(feats))}

    # 1) verify forecasts that targeted `day`
    actual = dict(zip(feats.site, feats.o3_max8h)) if len(feats) else {}
    verified = 0
    for r in rows:
        if r["status"] == "pending" and r["target_date"] == str(day) and actual.get(r["site"]) is not None:
            a = actual[r["site"]]
            r.update(status="verified", actual_o3_max8h=f"{a:.3f}", y=str(int(a > NAAQS_8H_OZONE_PPM)))
            verified += 1
    summary["verified"] = verified

    # 2) forecast day+1 from day's features (once per feature day)
    issued = 0
    if str(day) not in done_days and len(feats):
        F = joblib.load(OUT / "models" / "F_core.joblib")
        M = joblib.load(OUT / "models" / "main_benchmark_core.joblib")
        need = sorted(set(F.feature_names) | set(M.feature_names))
        ok = feats.dropna(subset=need)
        if len(ok):
            pF, pM = F.predict_proba(ok), M.predict_proba(ok)
            for (_, r), a, b in zip(ok.iterrows(), pF, pM):
                rows.append({"issued_utc": now.isoformat(timespec="seconds"), "feature_date": str(day),
                             "target_date": str(day + timedelta(days=1)), "site": r.site,
                             "o3_max8h_today": f"{r.o3_max8h:.3f}", "p_F": f"{a:.4f}", "p_main": f"{b:.4f}",
                             "thr_F": f"{F.thresholds['tss']:.4f}", "thr_main": f"{M.thresholds['tss']:.4f}",
                             "status": "pending", "actual_o3_max8h": "", "y": ""})
                issued += 1
        summary["dropped_incomplete_sites"] = int(len(feats) - len(ok))
    summary["issued"] = issued

    OUT.mkdir(exist_ok=True)
    with open(FORECASTS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    if len(feats):                                        # keep AirNow-derived features for AQS drift checks
        old = pd.read_csv(FEATURES) if FEATURES.exists() else pd.DataFrame()
        new = feats.assign(date=feats.date.dt.strftime("%Y-%m-%d"))
        both = pd.concat([old, new], ignore_index=True).drop_duplicates(["site", "date"], keep="first")
        both.to_csv(FEATURES, index=False)
    print(summary)
    return summary


def score() -> dict:
    """L1: F vs main's benchmark model on verified live forecasts (Brier + TSS, date-clustered)."""
    from benchgap import evaluate
    rows = [r for r in _read(FORECASTS) if r["status"] == "verified"]
    if not rows:
        out = {"ready": False, "reason": "no verified forecasts yet"}
        OUT.mkdir(exist_ok=True)
        (OUT / "live_score.json").write_text(__import__("json").dumps(out, indent=2), encoding="utf-8")
        return out
    y = np.array([int(r["y"]) for r in rows])
    g = np.array([r["target_date"] for r in rows])
    pF, pM = (np.array([float(r[k]) for r in rows]) for k in ("p_F", "p_main"))
    tF, tM = float(rows[0]["thr_F"]), float(rows[0]["thr_main"])
    out = {"n": len(rows), "days": len(set(g)), "exceedances": int(y.sum()),
           "brier": {"F": round(float(((pF - y) ** 2).mean()), 5), "main": round(float(((pM - y) ** 2).mean()), 5)}}
    if 0 < y.sum() < len(y):
        pt, lo, hi = evaluate.paired_difference_ci(y, pF, tF, y, pM, tM, groups_a=g, groups_b=g)
        out["tss_F_minus_main"] = {"value": round(pt, 4), "ci95": [round(lo, 4), round(hi, 4)]}
    else:
        out["tss_F_minus_main"] = "undefined: no exceedances (or no non-exceedances) verified yet"
    (OUT / "live_score.json").write_text(__import__("json").dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        assert o3_max8h({h: 60.0 for h in range(31)}) == 0.060
        assert o3_max8h({h: 80.9 for h in range(6)}) == 0.080          # 6 of 8 present, truncated
        assert o3_max8h({0: 50.0}) is None
        print("live self-check OK")
    elif "--score" in sys.argv:
        print(score())
    else:
        run()
        score()
