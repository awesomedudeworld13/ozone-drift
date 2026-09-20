"""Command line entry points.

    python -m ozonedrift.cli fetch     # download the AQS annual files
    python -m ozonedrift.cli survey    # per-year coverage and exceedance counts
    python -m ozonedrift.cli report    # three cells + the 2x2 -> RESULTS.md

Eras are fixed here, not passed as flags, so a run cannot quietly search for
the year split that produces the most interesting gap.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import gap
from .aqs import build_features, summarise
from .splits import era_gate

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
RESULTS_DIR = ROOT / "results"
RESULTS_MD = ROOT / "RESULTS.md"

SEED = 20260920

# Frozen eras. 2020-2021 are deliberately excluded rather than assigned: the
# pandemic changed traffic volumes, and therefore ozone precursor emissions,
# enough that those years belong to neither a "before" nor an "after" regime.
# Excluding them is a decision about the world, made before modelling, not a
# result-dependent choice -- and it is stated here so it cannot be quietly
# revised later.
BENCHMARK_YEARS = (2015, 2016, 2017, 2018, 2019)
OPERATIONAL_YEARS = (2022, 2023, 2024, 2025)
ALL_YEARS = BENCHMARK_YEARS + OPERATIONAL_YEARS

TIERS = ("core", "extended")


def cmd_fetch(args) -> int:
    from .aqs import download

    for year in ALL_YEARS:
        for stem in (f"daily_44201_{year}", f"daily_TEMP_{year}",
                     f"daily_WIND_{year}", f"daily_RH_DP_{year}"):
            try:
                p = download(stem, CACHE)
                print(f"  ok   {stem}  {p.stat().st_size // 1024:,}K", flush=True)
            except Exception as exc:
                print(f"  FAIL {stem}: {str(exc)[:90]}", file=sys.stderr, flush=True)
    return 0


def cmd_survey(args) -> int:
    for tier in TIERS:
        frame = build_features(ALL_YEARS, CACHE, tier=tier)
        print(f"\n=== tier: {tier} ===")
        print(f"  {json.dumps(summarise(frame))}")
        gate = era_gate(frame, ALL_YEARS)
        print(f"  {'year':>6}{'rows':>8}{'days':>7}{'exceed':>8}{'rate':>8}")
        for row in gate["years"]:
            flag = "  <-- ZERO" if row["positives"] == 0 else ""
            rate = row["base_rate"] if row["base_rate"] is not None else float("nan")
            print(f"  {row['year']:>6}{row['rows']:>8,}{row['days']:>7}"
                  f"{row['positives']:>8}{rate:>8.4f}{flag}")
        b = era_gate(frame[frame.date.dt.year.isin(BENCHMARK_YEARS)], BENCHMARK_YEARS)
        o = era_gate(frame[frame.date.dt.year.isin(OPERATIONAL_YEARS)], OPERATIONAL_YEARS)
        print(f"  era gate — benchmark: {'PASS' if b['passed'] else 'FAIL'}, "
              f"operational: {'PASS' if o['passed'] else 'FAIL'}")
    return 0


def cmd_report(args) -> int:
    by_tier = {}
    for tier in TIERS:
        frame = build_features(ALL_YEARS, CACHE, tier=tier)
        feature_names = frame.attrs["feature_names"]
        print(f"[{tier}] {len(frame):,} rows, {frame.site.nunique()} sites, "
              f"{int(frame.y.sum()):,} exceedances, {len(feature_names)} features",
              flush=True)
        r = gap.run(frame, feature_names, BENCHMARK_YEARS, OPERATIONAL_YEARS,
                    tier=tier, n_estimators=args.n_estimators,
                    n_resamples=args.resamples, seed=SEED)
        by_tier[tier] = r
        if r.get("aborted"):
            print(f"[{tier}] ABORTED: {r['aborted']}", file=sys.stderr)
            continue
        for key, c in r["cells"].items():
            print(f"         {key:<32} TSS {c['operating_points']['tss']['tss']:+.3f} "
                  f"(n={c['n']:,})", flush=True)
        lt = r["live_training"]
        print(f"         gap {lt['gap_A_minus_B']:+.3f}  recovery "
              f"{lt['recovery_D_minus_B']:+.3f} (sig={lt['recovery_significant']})",
              flush=True)

    gap.write(by_tier, RESULTS_DIR, RESULTS_MD)
    print(f"\n[report] -> results/*.json, RESULTS.md")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="ozonedrift",
        description="Does a benchmark overstate operational skill when the shift "
                    "is ordinary and physical?")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("fetch", help="download the AQS annual files")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("survey", help="per-year coverage and exceedance counts")
    s.set_defaults(func=cmd_survey)

    s = sub.add_parser("report", help="three cells + the 2x2")
    s.add_argument("--n-estimators", type=int, default=400)
    s.add_argument("--resamples", type=int, default=1000)
    s.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
