"""Checks on the invariants this study depends on.

Run: `python tests/test_protocol.py` (or `python -m pytest tests/ -q`).

Each guards a specific way the experiment could become invalid with no visible
error:

* a chronological split that leaks a date would erase the very leakage cell 2
  measures;
* a random split that happened NOT to leak would make the cell 1 vs 2 contrast
  vacuous;
* a label built by shifting rows rather than days would turn record gaps into
  easier multi-day forecasts;
* an i.i.d. bootstrap over pooled site-days would report intervals several times
  too narrow, because a regional ozone episode is one event, not twenty;
* a local copy of the scoring code reappearing would shadow the shared
  `benchgap` package and silently stop the cross-domain comparison from being
  a comparison.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchgap import evaluate                                    # noqa: E402
from ozonedrift.splits import (                                    # noqa: E402
    chronological_split, era_gate, random_split,
)

def _frame(n_days=200, n_sites=8, seed=0):
    """Synthetic pooled airshed: many sites per day, regional episodes."""
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2020-01-01")
    for d in range(n_days):
        # One regional driver per day -- this is what makes site-days dependent.
        episode = rng.random() < 0.15
        for s in range(n_sites):
            rows.append({
                "site": f"48-201-{s:04d}",
                "date": start + pd.Timedelta(days=d),
                "o3_max8h": 0.05 + (0.03 if episode else 0.0) + rng.normal(0, 0.003),
                "y": int(episode and rng.random() < 0.9),
            })
    return pd.DataFrame(rows)


def test_chronological_split_shares_no_date():
    f = _frame()
    s = chronological_split(f)
    assert not (set(s.train.date) & set(s.val.date))
    assert not (set(s.train.date) & set(s.test.date))
    assert not (set(s.val.date) & set(s.test.date))
    assert s.train.date.max() < s.test.date.min(), "train must precede test"
    assert len(s.train) + len(s.val) + len(s.test) == len(f)


def test_validation_period_precedes_test_period():
    """Thresholds must never be chosen using data newer than the test set."""
    s = chronological_split(_frame())
    assert s.val.date.max() < s.test.date.min(), (
        "validation extends past the start of test; the frozen operating point "
        "would be chosen with knowledge of the future"
    )


def test_random_split_does_leak_dates():
    """The cell 1 vs cell 2 contrast is only meaningful if random really leaks."""
    f = _frame()
    s = random_split(f, seed=1)
    shared = set(s.train.date) & set(s.test.date)
    assert shared, "random split shared no dates; the leakage contrast is vacuous"
    # Most days should straddle the partition, not a rare few.
    assert len(shared) > 0.5 * f.date.nunique()


def test_date_clustered_bootstrap_is_wider_than_iid():
    """Pooled site-days are not independent; the interval must reflect that."""
    rng = np.random.default_rng(3)
    y, prob, groups = [], [], []
    for d in range(40):
        label = d % 2
        correct = (d % 4) != 3          # a quarter of DAYS are wrong together
        centre = (0.65 if label else 0.35) if correct else (0.35 if label else 0.65)
        for _ in range(20):             # 20 sites share that day's outcome
            y.append(label)
            prob.append(np.clip(centre + rng.normal(0, 0.02), 0, 1))
            groups.append(f"2020-01-{d+1:02d}")
    y, prob, groups = np.array(y), np.array(prob), np.array(groups)

    lo_c, hi_c = evaluate.cluster_bootstrap_ci(y, prob, 0.5, groups=groups, n_resamples=300)
    lo_i, hi_i = evaluate.cluster_bootstrap_ci(y, prob, 0.5, groups=None, n_resamples=300)
    assert (hi_c - lo_c) > (hi_i - lo_i), (
        "date-clustered interval was not wider than i.i.d.; pooling 20 sites per "
        "day would be reported as 20 independent observations"
    )


def test_era_gate_rejects_a_year_with_no_exceedances():
    f = _frame()
    f.loc[f.date.dt.year == 2020, "y"] = 0
    gate = era_gate(f, [2020])
    assert gate["passed"] is False
    assert gate["years"][0]["positives"] == 0


def test_era_gate_passes_a_year_with_exceedances():
    f = _frame()
    assert f.y.sum() > 0
    assert era_gate(f, [2020])["passed"] is True


def test_label_is_next_day_not_same_day():
    """The forecast-time contract, checked on the real pipeline if data is cached.

    Skipped when the AQS cache is absent, so the suite still runs on a clean
    checkout; the assertion is the one that matters most when it does run.
    """
    cache = Path(__file__).resolve().parent.parent / "data" / "cache"
    if not (cache / "daily_44201_2023.zip").exists():
        print("    (skipped: no cached AQS data)")
        return
    from ozonedrift.aqs import NAAQS_8H_OZONE_PPM, build_features

    f = build_features([2023], cache, tier="core")
    # y must equal exceedance of the NEXT day's ozone, never the current row's.
    assert (f.y == (f.next_o3 > NAAQS_8H_OZONE_PPM).astype(int)).all()
    same_day = (f.o3_max8h > NAAQS_8H_OZONE_PPM).astype(int)
    assert not (f.y == same_day).all(), "label appears to be same-day, not next-day"
    # Every retained row's successor must be exactly one day later.
    assert ((f.next_date - f.date).dt.days == 1).all()


def test_scoring_comes_from_the_shared_package():
    """The cross-domain comparison depends on this, so assert it rather than assume.

    Every domain in the study must compute TSS with the SAME code. That used to
    be enforced by hashing a local copy; now it is enforced structurally, by
    there being only one copy. This checks the import actually resolves to the
    installed package and that no local shadow has reappeared.
    """
    import benchgap

    assert evaluate.__name__.startswith("benchgap"), (
        f"evaluate resolved to {evaluate.__name__!r}, not the shared package"
    )
    shadow = Path(__file__).resolve().parent.parent / "ozonedrift" / "evaluate.py"
    assert not shadow.exists(), (
        "a local ozonedrift/evaluate.py has reappeared; it would shadow the "
        "shared package and silently break cross-domain comparability"
    )
    # The functions the study depends on must all be present.
    for fn in ("score_at", "select_threshold", "peak_tss", "cluster_bootstrap_ci",
               "paired_difference_ci", "brier_skill"):
        assert hasattr(evaluate, fn), f"benchgap.evaluate is missing {fn}"
    print(f"    (benchgap {benchgap.__version__})")


def _run_all():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  PASS  {name}")
            except AssertionError as exc:
                failures += 1; print(f"  FAIL  {name}: {exc}")
    print(f"\n{'all checks passed' if not failures else f'{failures} FAILED'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(_run_all())
