"""testing-new: dose-response, more history, learner/regional feature (Z1-Z5).

    python -m ozonedrift.dose          # -> testing_new/dose_results.json, testing_new/models/

Pre-registered in testing_new/PREREGISTRATION.md: every arm is trained on its
own days, picks thresholds on the SAME validation window, and is scored on the
SAME test window, so arms differ only in training data.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from benchgap import evaluate
from .aqs import build_features, load_ozone
from .gap import evaluate_cell
from .model import PersistenceBaseline, TrainedModel, train as train_rf
from .splits import Split, chronological_split

SEED = 20260920
CACHE = Path("data/cache")
OUT = Path("testing_new")
YEARS = tuple(range(2005, 2020)) + (2022, 2023, 2024, 2025, 2026)
VAL = ("2024-10-18", "2025-05-24")
TEST = ("2025-05-25", "2025-12-30")
OP28 = [("2022-01-01", "2024-10-17")]
BM5 = [("2015-01-01", "2019-12-31")]
HIST = [("2005-01-01", "2019-12-31")]
ARMS = {
    "op1": [("2023-10-18", "2024-10-17")],
    "op2": [("2022-10-18", "2024-10-17")],
    "op28": OP28,
    "bm3": [("2017-01-01", "2019-12-31")],
    "bm5": BM5,
    "bm_op": BM5 + OP28,
    "hist_bm": HIST,
    "hist_bm_op": HIST + OP28,
}
FINAL_TRAIN = HIST + [("2022-01-01", "2026-03-31")]
REGIONAL = "airshed_o3_max"


def _within(frame, spans):
    m = np.zeros(len(frame), dtype=bool)
    for a, b in spans:
        m |= ((frame.date >= a) & (frame.date <= b)).to_numpy()
    return frame[m]


def airshed_max(years) -> pd.Series:
    """Highest o3_max8h across every HGB site reporting on each date."""
    oz = pd.concat([load_ozone(y, CACHE) for y in years], ignore_index=True)
    return oz.groupby("date").o3_max8h.max()


def frame_for(tier: str) -> tuple[pd.DataFrame, tuple]:
    f = build_features(YEARS, CACHE, tier)
    names = f.attrs["feature_names"]
    f[REGIONAL] = f.date.map(airshed_max(YEARS))
    return f.reset_index(drop=True), names


def split(frame, spans) -> Split:
    return Split(name="arm", train=_within(frame, spans), val=_within(frame, [VAL]), test=_within(frame, [TEST]))


def train_hgb(sp: Split, names) -> TrainedModel:
    est = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, class_weight="balanced",
                                         random_state=SEED)
    est.fit(sp.train[list(names)].to_numpy(float), sp.train.y.to_numpy())
    pv = est.predict_proba(sp.val[list(names)].to_numpy(float))[:, 1]
    thr = {o: evaluate.select_threshold(sp.val.y.to_numpy(), pv, o) for o in ("f1", "tss")}
    return TrainedModel(estimator=est, feature_names=tuple(names), thresholds=thr,
                        metadata={"estimator": "HistGradientBoostingClassifier"})


def cell(model, frame) -> dict:
    return evaluate_cell("x", "", model, frame, {"tss": model.thresholds["tss"]}).to_dict()


def diff(a, b, test) -> dict:
    g = test.date.dt.strftime("%Y-%m-%d").to_numpy()
    y = test.y.to_numpy()
    pt, lo, hi = evaluate.paired_difference_ci(y, a.predict_proba(test), a.thresholds["tss"],
                                               y, b.predict_proba(test), b.thresholds["tss"],
                                               groups_a=g, groups_b=g)
    return {"value": round(pt, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "direction": "a>b" if lo > 0 else "a<b" if hi < 0 else "inconclusive"}


def tss_of(c):
    return c["operating_points"]["tss"]["tss"] if "operating_points" in c else c["scores"]["tss"]["tss"]


def run_tier(tier: str) -> dict:
    frame, names = frame_for(tier)
    test = _within(frame, [TEST])
    out = {"tier": tier, "n_test": int(len(test)), "test_exceedances": int(test.y.sum()), "arms": {}}
    models = {}
    for arm, spans in ARMS.items():
        sp = split(frame, spans)
        models[arm] = train_rf(sp, names, label=f"{tier}/{arm}")
        out["arms"][arm] = {"n_train": int(len(sp.train)), "train_exceedances": int(sp.train.y.sum()),
                            "test": cell(models[arm], test)}
        print(f"  [{tier}] {arm}: n_train={len(sp.train)}", flush=True)
    out["Z1_op28_minus_bm3"] = diff(models["op28"], models["bm3"], test)
    out["Z2_op28_minus_op1"] = diff(models["op28"], models["op1"], test)
    out["Z3_bm_op_minus_bm5"] = diff(models["bm_op"], models["bm5"], test)
    out["Z4_hist_bm_op_minus_bm_op"] = diff(models["hist_bm_op"], models["bm_op"], test)

    sp = split(frame, ARMS["hist_bm_op"])
    val = sp.val
    variants = {}
    for learner in ("rf", "hgb"):
        for feats in ("base", "regional"):
            use = tuple(names) + ((REGIONAL,) if feats == "regional" else ())
            m = train_rf(sp, use, label=f"{tier}/{learner}/{feats}") if learner == "rf" else train_hgb(sp, use)
            vt = evaluate.score_at(val.y.to_numpy(), m.predict_proba(val), m.thresholds["tss"]).to_dict()["tss"]
            variants[f"{learner}_{feats}"] = (m, use, round(vt, 4))
    winner = max(variants, key=lambda k: variants[k][2])
    out["variants"] = {k: {"val_tss": v[2], "test": cell(v[0], test)} for k, v in variants.items()}
    out["dev_winner"] = winner

    pers = PersistenceBaseline()
    p_thr = evaluate.select_threshold(val.y.to_numpy(), pers.predict_proba(val), "tss")
    pers.thresholds = {"f1": p_thr, "tss": p_thr}
    out["Z5_winner_minus_persistence"] = diff(variants[winner][0], pers, test)
    out["persistence_test"] = cell(pers, test)
    out["_winner"] = variants[winner]
    return out


def main():
    OUT.mkdir(exist_ok=True)
    res = {"preregistration": "testing_new/PREREGISTRATION.md"}
    for tier in ("core", "extended"):
        print(f"tier {tier} ...", flush=True)
        res[tier] = run_tier(tier)
    # Final model F (core tier: the live tier), winner recipe refit on everything published.
    m, use, _ = res["core"].pop("_winner")
    res["extended"].pop("_winner")
    frame, names = frame_for("core")
    full = Split(name="final", train=_within(frame, FINAL_TRAIN), val=_within(frame, [VAL]),
                 test=_within(frame, [TEST]))
    kind = res["core"]["dev_winner"].split("_")[0]
    F = train_rf(full, use, label="core/F") if kind == "rf" else train_hgb(full, use)
    F.thresholds = dict(m.thresholds)                     # frozen from the dev winner
    F.metadata = {**getattr(F, "metadata", {}), "recipe": res["core"]["dev_winner"],
                  "features": list(use), "trained_on": FINAL_TRAIN, "thresholds_from": "dev winner"}
    bench = train_rf(chronological_split(_within(frame, BM5)), names, label="core/main-benchmark")
    (OUT / "models").mkdir(exist_ok=True)
    joblib.dump(F, OUT / "models" / "F_core.joblib", compress=3)
    joblib.dump(bench, OUT / "models" / "main_benchmark_core.joblib", compress=3)
    res["final_model"] = {"recipe": res["core"]["dev_winner"], "features": list(use),
                          "thresholds": F.thresholds, "n_train": int(len(full.train))}
    (OUT / "dose_results.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps({t: {k: v for k, v in res[t].items() if k.startswith("Z") or k == "dev_winner"}
                      for t in ("core", "extended")}, indent=2))


if __name__ == "__main__":
    main()
