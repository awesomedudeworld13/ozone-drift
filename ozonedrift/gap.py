"""The experiment: three cells, then the question of whether live training helps.

Two questions, as in every domain of this study:

1. **How far does benchmark performance fall on operational data?**

       cell 1  benchmark era, random i.i.d. split     <- the common protocol
                 |  change: partition by date instead of by row
       cell 2   benchmark era, chronological split    <- removes temporal leakage
                 |  change: score the frozen cell-2 model on a later era
       cell 3   operational era                       <- deployment reality

   Each step changes exactly one thing, so the drop is attributed rather than
   merely observed:

       temporal leakage  = cell 1 - cell 2
       operational drift = cell 2 - cell 3

2. **Does training on operational data close that gap?** -- the training-source
   x test-set 2x2 against a model fitted on the operational era alone.

Ozone can answer question 2 immediately, which is the one respect in which it
is easier than the sibling phishing domain: EPA observations are archived and
retrievable for any past period, so an "operational-era-trained" model can be
fitted today. The phishing project must wait for a daily feed to accumulate.

Uncertainty clusters on DATE throughout. An ozone episode is regional, so on an
exceedance day many of the pooled sites exceed together; resampling site-days
i.i.d. would count one weather event as twenty observations and make every
interval several times too narrow. This is the same dependency the solar project
handles by clustering on active region and phish-drift by registrable domain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from benchgap import evaluate
from .model import PersistenceBaseline, TrainedModel, train
from .splits import Split, chronological_split, era_gate, random_split

BOOTSTRAP_RESAMPLES = 1000


@dataclass
class Cell:
    name: str
    description: str
    n: int
    days: int
    base_rate: float
    scores: dict = field(default_factory=dict)
    peak_tss: float = float("nan")

    def tss(self, point: str = "tss") -> float:
        return self.scores[point]["tss"]

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "n": self.n, "days": self.days,
            "base_rate": round(self.base_rate, 6),
            "peak_tss": round(self.peak_tss, 6),
            "operating_points": self.scores,
        }


def evaluate_cell(name: str, description: str, model, frame: pd.DataFrame,
                  thresholds: dict, n_resamples: int = BOOTSTRAP_RESAMPLES) -> Cell:
    """Score ``model`` on ``frame`` at each frozen threshold, clustered on date."""
    y = frame.y.to_numpy()
    prob = model.predict_proba(frame)
    # The cluster key. Dates are datetime64; cast to a stable string so the
    # grouping in evaluate.cluster_bootstrap_ci sorts deterministically.
    groups = frame.date.dt.strftime("%Y-%m-%d").to_numpy()

    peak, _ = evaluate.peak_tss(y, prob)
    cell = Cell(name=name, description=description, n=len(frame),
                days=int(frame.date.nunique()), base_rate=float(y.mean()),
                peak_tss=peak)

    for point, thr in thresholds.items():
        s = evaluate.score_at(y, prob, thr).to_dict()
        lo, hi = evaluate.cluster_bootstrap_ci(y, prob, thr, groups=groups,
                                               n_resamples=n_resamples)
        s["tss_ci95"] = [round(lo, 6), round(hi, 6)]
        cell.scores[point] = s
    return cell


def run(frame: pd.DataFrame, feature_names, benchmark_years, operational_years,
        tier: str, n_estimators: int = 400, n_resamples: int = BOOTSTRAP_RESAMPLES,
        seed: int = 20260920) -> dict:
    """Execute the three cells and the 2x2 for one feature tier."""
    results: dict = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": tier,
        "bootstrap_resamples": n_resamples,
        "cluster_key": "date",
        "benchmark_years": list(benchmark_years),
        "operational_years": list(operational_years),
        "n_features": len(feature_names),
    }

    bench = frame[frame.date.dt.year.isin(benchmark_years)].copy()
    oper = frame[frame.date.dt.year.isin(operational_years)].copy()

    # Data-quality gate, applied before any model exists.
    results["era_gate"] = {
        "benchmark": era_gate(bench, benchmark_years),
        "operational": era_gate(oper, operational_years),
    }
    if not (results["era_gate"]["benchmark"]["passed"]
            and results["era_gate"]["operational"]["passed"]):
        results["aborted"] = (
            "An era contains a year with zero pooled exceedances; TSS is "
            "undefined there. Choose eras that pass the gate."
        )
        return results

    # -- cells 1 and 2: same era, two partitions ---------------------------
    split_rand = random_split(bench, seed=seed)
    split_chron = chronological_split(bench)

    model_rand = train(split_rand, feature_names, label=f"{tier}/benchmark/random",
                       n_estimators=n_estimators, seed=seed)
    model_chron = train(split_chron, feature_names, label=f"{tier}/benchmark/chronological",
                        n_estimators=n_estimators, seed=seed)

    cells: dict[str, Cell] = {
        "cell1_benchmark_random": evaluate_cell(
            "cell1_benchmark_random",
            "Benchmark era, random i.i.d. split — the protocol most published "
            "air-quality ML uses.",
            model_rand, split_rand.test, model_rand.thresholds, n_resamples),
        "cell2_benchmark_chronological": evaluate_cell(
            "cell2_benchmark_chronological",
            "Benchmark era, chronological split — earlier days train, later "
            "days test, no date shared.",
            model_chron, split_chron.test, model_chron.thresholds, n_resamples),
        "cell3_operational": evaluate_cell(
            "cell3_operational",
            "Operational era, cell-2 model frozen — deployment reality.",
            model_chron, oper, model_chron.thresholds, n_resamples),
    }
    results["cells"] = {k: v.to_dict() for k, v in cells.items()}

    # -- attribution --------------------------------------------------------
    attribution = {}
    for point in ("f1", "tss"):
        attribution[point] = {
            "temporal_leakage": round(
                cells["cell1_benchmark_random"].tss(point)
                - cells["cell2_benchmark_chronological"].tss(point), 6),
            "operational_drift": round(
                cells["cell2_benchmark_chronological"].tss(point)
                - cells["cell3_operational"].tss(point), 6),
            "total": round(
                cells["cell1_benchmark_random"].tss(point)
                - cells["cell3_operational"].tss(point), 6),
        }
    results["attribution_tss"] = attribution
    results["attribution_steps"] = [
        {"step": "temporal_leakage", "from": "cell1_benchmark_random",
         "to": "cell2_benchmark_chronological",
         "meaning": "Same era and same data; only the partitioning changes. Skill "
                    "lost here came from interpolating between autocorrelated days "
                    "and from seeing the same regional episode at other sites."},
        {"step": "operational_drift", "from": "cell2_benchmark_chronological",
         "to": "cell3_operational",
         "meaning": "Same honest protocol, a later era. Skill lost here is genuine "
                    "drift — the seasonal and physical shift this domain exists to "
                    "measure."},
    ]

    # -- question 2: does operational training close the gap? ---------------
    # Unlike the phishing domain, the data for this exists already.
    split_oper = chronological_split(oper)
    model_oper = train(split_oper, feature_names, label=f"{tier}/operational/chronological",
                       n_estimators=n_estimators, seed=seed)

    twobytwo = {
        "A_benchmark_trained_on_benchmark": evaluate_cell(
            "A", "Benchmark-trained on its own chronological test.",
            model_chron, split_chron.test, {"tss": model_chron.thresholds["tss"]}, n_resamples),
        "B_benchmark_trained_on_operational": evaluate_cell(
            "B", "Benchmark-trained on the operational era — the gap.",
            model_chron, split_oper.test, {"tss": model_chron.thresholds["tss"]}, n_resamples),
        "C_operational_trained_on_benchmark": evaluate_cell(
            "C", "Operational-trained on the benchmark test — does it generalise "
                 "backwards, or only fit its own era?",
            model_oper, split_chron.test, {"tss": model_oper.thresholds["tss"]}, n_resamples),
        "D_operational_trained_on_operational": evaluate_cell(
            "D", "Operational-trained on the operational test — the best "
                 "achievable with deployment-era data.",
            model_oper, split_oper.test, {"tss": model_oper.thresholds["tss"]}, n_resamples),
    }

    gap = twobytwo["A_benchmark_trained_on_benchmark"].tss() - twobytwo["B_benchmark_trained_on_operational"].tss()
    recovery = twobytwo["D_operational_trained_on_operational"].tss() - twobytwo["B_benchmark_trained_on_operational"].tss()

    test_o = split_oper.test
    point, lo, hi = evaluate.paired_difference_ci(
        test_o.y.to_numpy(), model_oper.predict_proba(test_o), model_oper.thresholds["tss"],
        test_o.y.to_numpy(), model_chron.predict_proba(test_o), model_chron.thresholds["tss"],
        groups_a=test_o.date.dt.strftime("%Y-%m-%d").to_numpy(),
        groups_b=test_o.date.dt.strftime("%Y-%m-%d").to_numpy(),
        n_resamples=n_resamples,
    )

    # The interval can exclude zero in EITHER direction, and the negative case
    # is a real finding rather than a null: it means training on the newer era
    # measurably hurt. Testing only `lo > 0` would report that as "not
    # significant" and quietly discard the result.
    if lo > 0:
        direction, significant = "improves", True
    elif hi < 0:
        direction, significant = "harms", True
    else:
        direction, significant = "inconclusive", False

    results["live_training"] = {
        "question": "Does training on operational data close the gap?",
        "cells": {k: v.to_dict() for k, v in twobytwo.items()},
        "gap_A_minus_B": round(gap, 6),
        "recovery_D_minus_B": round(recovery, 6),
        "recovery_ci95": [round(lo, 6), round(hi, 6)],
        "recovery_significant": significant,
        "recovery_direction": direction,
        "recovery_fraction_of_gap": round(recovery / gap, 6) if gap else None,
        "answer": (
            f"Operational training changes TSS by {recovery:+.3f} on the same "
            f"operational test rows (95% CI {lo:.3f}..{hi:.3f}). "
            + {
                "improves": "The interval excludes zero above, so it measurably helps.",
                "harms": "The interval excludes zero BELOW, so training on the newer "
                         "era measurably HURT — the benchmark-era model generalises to "
                         "deployment better than a model fitted on deployment-era data. "
                         "The loss is not a training-data problem, and collecting more "
                         "recent data would not fix it.",
                "inconclusive": "The interval includes zero, so on this much data no "
                                "effect can be claimed either way.",
            }[direction]
        ),
        "operational_model": model_oper.metadata,
    }

    # -- the forecaster's null hypothesis -----------------------------------
    results["persistence_baseline"] = {
        k: evaluate_cell(k, "Persistence: tomorrow looks like today.",
                         PersistenceBaseline, f, PersistenceBaseline.thresholds,
                         n_resamples).to_dict()
        for k, f in (("benchmark_test", split_chron.test), ("operational", oper))
    }

    results["models"] = {"random": model_rand.metadata, "chronological": model_chron.metadata}
    return results


def _fmt(x) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"


def render_markdown(by_tier: dict) -> str:
    """RESULTS.md. Generated, never hand-edited."""
    out: list[str] = []
    a = out.append
    a("# ozone-drift — Results\n")
    a("> Auto-generated by `python -m ozonedrift.cli report`. Do not hand-edit.\n")

    first = next(iter(by_tier.values()))
    a(f"Generated {first['generated_at_utc']} · "
      f"{first['bootstrap_resamples']} date-clustered bootstrap resamples.\n")
    a(f"Benchmark era {first['benchmark_years'][0]}–{first['benchmark_years'][-1]} · "
      f"operational era {first['operational_years'][0]}–{first['operational_years'][-1]}.\n")
    a("*Both feature tiers are reported. Choosing one after seeing which gave a "
      "larger gap would be the selection effect this project exists to criticise.*\n")

    for tier, r in by_tier.items():
        a(f"\n---\n\n## Tier: {tier}\n")
        if r.get("aborted"):
            a(f"**Aborted.** {r['aborted']}\n"); continue

        a("### The three cells\n")
        a("| cell | n | days | base rate | TSS @ F1 pt | TSS @ TSS pt | 95% CI (TSS pt) |")
        a("|---|---|---|---|---|---|---|")
        for key, c in r["cells"].items():
            f1 = c["operating_points"].get("f1", {})
            ts = c["operating_points"].get("tss", {})
            ci = ts.get("tss_ci95")
            a(f"| {key} | {c['n']:,} | {c['days']:,} | {c['base_rate']:.4f} | "
              f"{_fmt(f1.get('tss'))} | **{_fmt(ts.get('tss'))}** | "
              f"{ci[0]:.3f}..{ci[1]:.3f} |")
        a("")
        for key, c in r["cells"].items():
            a(f"- **{key}** — {c['description']}")
        a("")

        a("### Where the skill went\n")
        at = r["attribution_tss"]
        a("| step | ΔTSS @ F1 pt | ΔTSS @ TSS pt |")
        a("|---|---|---|")
        for step in r["attribution_steps"]:
            k = step["step"]
            a(f"| {k.replace('_',' ')} | {_fmt(at['f1'].get(k))} | {_fmt(at['tss'].get(k))} |")
        a(f"| **total** | **{_fmt(at['f1']['total'])}** | **{_fmt(at['tss']['total'])}** |")
        a("")
        for step in r["attribution_steps"]:
            a(f"- **{step['step'].replace('_',' ')}**: {step['meaning']}")
        a("")

        lt = r["live_training"]
        a("### Does training on operational data close the gap?\n")
        c = lt["cells"]
        a("| training source | benchmark test | operational test |")
        a("|---|---|---|")
        a(f"| benchmark-trained | {_fmt(c['A_benchmark_trained_on_benchmark']['operating_points']['tss']['tss'])} "
          f"| {_fmt(c['B_benchmark_trained_on_operational']['operating_points']['tss']['tss'])} |")
        a(f"| operational-trained | {_fmt(c['C_operational_trained_on_benchmark']['operating_points']['tss']['tss'])} "
          f"| **{_fmt(c['D_operational_trained_on_operational']['operating_points']['tss']['tss'])}** |")
        a("")
        a(f"- Gap (A − B): **{_fmt(lt['gap_A_minus_B'])}**")
        a(f"- Recovery from operational training (D − B): **{lt['recovery_D_minus_B']:+.3f}** "
          f"(95% CI {lt['recovery_ci95'][0]:.3f}..{lt['recovery_ci95'][1]:.3f}) — "
          f"**{lt['recovery_direction']}**")
        a("")
        a(f"> {lt['answer']}")
        if lt.get("recovery_fraction_of_gap") is not None:
            a(f"- That is {lt['recovery_fraction_of_gap']:.1%} of the gap.")
        a("")

        a("### Persistence baseline\n")
        a("*\"Tomorrow looks like today.\" A model that does not clear this has "
          "demonstrated nothing about forecasting.*\n")
        a("| evaluated on | n | TSS | peak TSS |")
        a("|---|---|---|---|")
        for key, p in r["persistence_baseline"].items():
            a(f"| {key} | {p['n']:,} | {_fmt(p['operating_points']['tss']['tss'])} "
              f"| {_fmt(p['peak_tss'])} |")
        a("")

        a("### Era gate\n")
        a("| era | year | rows | days | exceedances | base rate |")
        a("|---|---|---|---|---|---|")
        for era in ("benchmark", "operational"):
            for row in r["era_gate"][era]["years"]:
                a(f"| {era} | {row['year']} | {row['rows']:,} | {row['days']} | "
                  f"{row['positives']} | {_fmt(row['base_rate'])} |")
        a("")
    return "\n".join(out) + "\n"


def write(by_tier: dict, json_dir: Path, markdown_path: Path) -> None:
    json_dir = Path(json_dir); json_dir.mkdir(parents=True, exist_ok=True)
    for tier, r in by_tier.items():
        (json_dir / f"{tier}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    Path(markdown_path).write_text(render_markdown(by_tier), encoding="utf-8")
