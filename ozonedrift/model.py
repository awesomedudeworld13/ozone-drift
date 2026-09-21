"""Model training and threshold freezing.

A trained artifact carries its operating points with it. The thresholds are
part of the deployed model, not something the evaluation gets to choose later:
picking a threshold on the data you are about to score is the single most common
way an evaluation becomes optimistic, and it is a bug the sibling solar project
shipped and had to fix.

Two operating points are frozen on the validation partition:

``f1``   maximises F1. This is the field default, and because F1 is dragged
         toward the base rate of the data it was tuned on, the pre-registered
         hypothesis (O5) is that it degrades more than the alternative when the
         operational base rate differs.
``tss``  maximises Youden's J, which is invariant to base rate.

Both come from validation only. On the chronological split that validation
period is strictly older than the test period, so the operating point never
sees the future.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from benchgap import evaluate
from .splits import Split

MODEL_VERSION = 1


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except Exception:
        return "unknown"


@dataclass
class TrainedModel:
    """A classifier plus the operating points frozen at training time."""

    estimator: object
    feature_names: tuple[str, ...]
    thresholds: dict[str, float]
    metadata: dict = field(default_factory=dict)

    def predict_proba(self, frame) -> np.ndarray:
        """P(exceedance tomorrow) for a feature frame."""
        X = frame[list(self.feature_names)].to_numpy(dtype=np.float64)
        return self.estimator.predict_proba(X)[:, 1]

    def save(self, path: Path) -> Path:
        import joblib

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)
        path.with_suffix(".meta.json").write_text(
            json.dumps(self.metadata, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def load(path: Path) -> "TrainedModel":
        import joblib

        return joblib.load(Path(path))


def train(split: Split, feature_names, label: str = "", n_estimators: int = 400,
          seed: int = 20260920, n_jobs: int = -1) -> TrainedModel:
    """Fit on ``split.train`` and freeze both operating points on ``split.val``."""
    feature_names = tuple(feature_names)
    X = split.train[list(feature_names)].to_numpy(dtype=np.float64)
    y = split.train.y.to_numpy()

    estimator = RandomForestClassifier(
        n_estimators=n_estimators,
        min_samples_leaf=3,
        # Exceedance days are ~4% of the sample. Without rebalancing the forest
        # optimises toward the majority class and the probability surface is too
        # flat near the decision boundary for a threshold to be meaningful.
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=n_jobs,
    )
    estimator.fit(X, y)

    X_val = split.val[list(feature_names)].to_numpy(dtype=np.float64)
    y_val = split.val.y.to_numpy()
    prob_val = estimator.predict_proba(X_val)[:, 1]

    thresholds = {
        "f1": evaluate.select_threshold(y_val, prob_val, objective="f1"),
        "tss": evaluate.select_threshold(y_val, prob_val, objective="tss"),
    }

    importances = sorted(zip(feature_names, estimator.feature_importances_),
                         key=lambda kv: kv[1], reverse=True)

    metadata = {
        "model_version": MODEL_VERSION,
        "label": label,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "split_name": split.name,
        "split_sizes": split.sizes(),
        "estimator": "RandomForestClassifier",
        "hyperparameters": {
            "n_estimators": n_estimators, "min_samples_leaf": 3,
            "class_weight": "balanced_subsample", "random_state": seed,
        },
        "feature_names": list(feature_names),
        "thresholds": {k: round(v, 6) for k, v in thresholds.items()},
        "top_features": [{"name": n, "importance": round(float(i), 6)}
                         for n, i in importances[:12]],
        "train_span": [str(split.train.date.min().date()), str(split.train.date.max().date())],
        "val_span": [str(split.val.date.min().date()), str(split.val.date.max().date())],
    }

    return TrainedModel(estimator=estimator, feature_names=feature_names,
                        thresholds=thresholds, metadata=metadata)


class PersistenceBaseline:
    """"Tomorrow looks like today" -- the forecaster's null hypothesis.

    Exposed through the same ``predict_proba`` interface so it runs the
    identical evaluation path. It returns today's ozone scaled to [0, 1] by the
    NAAQS threshold, so a higher reading is a higher probability.

    Every operational forecasting domain has a trivial baseline that is
    embarrassingly hard to beat, and persistence is ozone's. A machine-learning
    model that does not clear it has demonstrated nothing, exactly as a phishing
    model that loses to a regex has demonstrated nothing. Reporting it is the
    same discipline in a different domain.
    """

    thresholds = {"f1": 0.5, "tss": 0.5}
    metadata = {"estimator": "PersistenceBaseline", "parameters": 0}
    feature_names = ("o3_max8h",)

    @staticmethod
    def predict_proba(frame) -> np.ndarray:
        from .aqs import NAAQS_8H_OZONE_PPM

        return np.clip(frame["o3_max8h"].to_numpy(dtype=float) / (2 * NAAQS_8H_OZONE_PPM), 0, 1)
