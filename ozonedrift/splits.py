"""Partitioning schemes, and the era gate.

The contrast between the two splits IS cell 1 vs cell 2 of the study.

``random_split`` is the protocol most published air-quality ML uses: shuffle
rows, take 70/15/15. On a pooled time series that leaks twice over. First,
consecutive days are strongly autocorrelated, so a model can interpolate
tomorrow from a training row two days either side rather than forecast it.
Second -- and this one is specific to pooling an airshed -- an ozone episode is
regional, so the *same day* appears at up to twenty sites; a random split puts
some of those sites in training and the rest in test, and the model is scored on
a weather event it has already seen.

``chronological_split`` is the honest protocol: earlier days train, later days
test, and a date is never divided across partitions. The difference between the
two is the quantity cell 2 exists to measure.

Neither split is "the right answer" on its own -- the study needs both, because
the claim is about how much the naive one overstates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Split:
    """A train/validation/test partition and how it was produced."""

    name: str
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    def sizes(self) -> dict:
        def part(frame):
            return {
                "rows": len(frame),
                "days": int(frame.date.nunique()),
                "positives": int(frame.y.sum()),
                "base_rate": round(float(frame.y.mean()), 6) if len(frame) else None,
            }
        return {"train": part(self.train), "val": part(self.val), "test": part(self.test)}


def random_split(frame: pd.DataFrame, seed: int = 20260920,
                 fractions=(0.70, 0.15, 0.15)) -> Split:
    """Stratified i.i.d. row split -- the naive protocol, leakage included.

    Deliberately NOT date-aware. This cell exists to show what the common
    protocol reports, so repairing its leakage here would erase the finding.
    """
    rng = np.random.default_rng(seed)
    parts = {"train": [], "val": [], "test": []}
    for _, group in frame.groupby("y"):
        idx = rng.permutation(group.index.to_numpy())
        n_train = int(len(idx) * fractions[0])
        n_val = int(len(idx) * fractions[1])
        parts["train"].append(idx[:n_train])
        parts["val"].append(idx[n_train:n_train + n_val])
        parts["test"].append(idx[n_train + n_val:])
    return Split(
        name="random",
        train=frame.loc[np.concatenate(parts["train"])].copy(),
        val=frame.loc[np.concatenate(parts["val"])].copy(),
        test=frame.loc[np.concatenate(parts["test"])].copy(),
    )


def chronological_split(frame: pd.DataFrame,
                        fractions=(0.70, 0.15, 0.15)) -> Split:
    """Earliest days train, latest days test; no date split across partitions.

    The validation slice is taken from the END of the training period rather
    than at random, so the operating point is never chosen using data newer
    than the test set. Selecting a threshold on scattered days would leak future
    information into the very number the deployment freezes.

    No seed: this partition is fully determined by the calendar, which is the
    point -- there is nothing to resample.
    """
    days = np.array(sorted(frame.date.unique()))
    n_train = int(len(days) * fractions[0])
    n_val = int(len(days) * fractions[1])

    train_days = set(days[:n_train])
    val_days = set(days[n_train:n_train + n_val])
    test_days = set(days[n_train + n_val:])

    split = Split(
        name="chronological",
        train=frame[frame.date.isin(train_days)].copy(),
        val=frame[frame.date.isin(val_days)].copy(),
        test=frame[frame.date.isin(test_days)].copy(),
    )

    # Fail closed: the guarantee this split exists to provide is that no day is
    # shared, so verify it rather than trusting the construction.
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        overlap = set(getattr(split, a).date) & set(getattr(split, b).date)
        if overlap:
            raise AssertionError(
                f"chronological_split shared {len(overlap)} date(s) between {a} and {b}"
            )
    if len(split.train) and len(split.test):
        if split.train.date.max() >= split.test.date.min():
            raise AssertionError("chronological_split: train is not strictly before test")
    return split


def era_split(frame: pd.DataFrame, benchmark_years, operational_years) -> tuple:
    """Partition by era for the training-source x test-set 2x2."""
    b = frame[frame.date.dt.year.isin(benchmark_years)].copy()
    o = frame[frame.date.dt.year.isin(operational_years)].copy()
    return b, o


def era_gate(frame: pd.DataFrame, years) -> dict:
    """Check no year in an era has zero pooled exceedances.

    A year with no positives makes TSS undefined and contributes nothing but
    noise to a pooled estimate. This is a property of the data, checkable before
    any model exists, so applying it is not a result-dependent choice -- the
    same reasoning as phish-drift's fail-closed label gate.
    """
    rows = []
    ok = True
    for year in sorted(years):
        sub = frame[frame.date.dt.year == year]
        positives = int(sub.y.sum())
        if len(sub) == 0 or positives == 0:
            ok = False
        rows.append({
            "year": int(year),
            "rows": len(sub),
            "days": int(sub.date.nunique()),
            "positives": positives,
            "base_rate": round(float(sub.y.mean()), 6) if len(sub) else None,
        })
    return {"passed": ok, "years": rows}
