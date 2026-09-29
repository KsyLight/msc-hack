"""Temporal model selection. Test is evaluated once, after choosing on validation."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, precision_score, recall_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from backend.ml.contracts import validate_features


def matrix(frame, features):
    missing = set(features) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required features: {sorted(missing)}")
    return frame[features].apply(pd.to_numeric, errors="raise").replace([np.inf, -np.inf], np.nan)


def select_threshold(y, probabilities, weights=None):
    p, r, t = precision_recall_curve(y, probabilities, sample_weight=weights)
    eligible = np.flatnonzero((p[:-1] > .7) & (r[:-1] > .5))
    if len(eligible):
        index = eligible[np.argmax(r[eligible])]
    else:
        f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
        index = int(np.argmax(f1))
    return float(t[index])


def metrics(y, p, threshold, weights=None):
    pred = p >= threshold
    return {"rows": len(y), "positives": int(np.sum(y)),
            "prevalence": float(np.average(y, weights=weights)),
            "pr_auc": float(average_precision_score(y, p, sample_weight=weights)),
            "precision": float(precision_score(y, pred, sample_weight=weights, zero_division=0)),
            "recall": float(recall_score(y, pred, sample_weight=weights, zero_division=0)),
            "brier": float(brier_score_loss(y, p, sample_weight=weights)),
            "false_positives": int(np.sum(pred & (np.asarray(y) == 0))),
            "alerts": int(np.sum(pred))}


def validate_splits(splits, target):
    for name, frame in splits.items():
        if frame.empty or frame[target].isna().any() or set(frame[target].unique()) != {0, 1}:
            raise ValueError(f"{name}: both observed target classes are required; censored labels cannot become zero")
        if frame.duplicated(["entity_id", "prediction_time"]).any():
            raise ValueError(f"{name}: duplicate entity/time keys")
    for left, right in [("train", "validation"), ("validation", "test")]:
        if pd.to_datetime(splits[left].prediction_time).max() + pd.Timedelta(hours=48) > pd.to_datetime(splits[right].prediction_time).min():
            raise ValueError(f"{left}/{right}: target windows overlap; require 48h purge")


def train_model(splits: dict, features: list[str], target: str, direction: str, out: Path, provenance: str):
    validate_features(features)
    validate_splits(splits, target)
    started = time.perf_counter()
    train, val, test = (splits[k] for k in ("train", "validation", "test"))
    x, vx = matrix(train, features), matrix(val, features)
    weights = train.get("sample_weight", pd.Series(np.ones(len(train)))).to_numpy()
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("sample_weight must be positive and finite")
    candidates = {
        "LogisticRegression": make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), LogisticRegression(max_iter=700, random_state=42)),
        "HistGradientBoosting": HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=15, l2_regularization=3, learning_rate=.07, early_stopping=False, random_state=42),
    }
    results, fitted = [], {}
    for name, model in candidates.items():
        kwargs = {"logisticregression__sample_weight": weights} if name == "LogisticRegression" else {"sample_weight": weights}
        model.fit(x, train[target], **kwargs)
        vp = model.predict_proba(vx)[:, 1]
        threshold = select_threshold(val[target], vp, val.get("sample_weight"))
        results.append({"algorithm": name, "threshold": threshold, **metrics(val[target], vp, threshold, val.get("sample_weight"))})
        fitted[name] = model
    best = max(results, key=lambda m: m["pr_auc"])
    model = fitted[best["algorithm"]]
    tp = model.predict_proba(matrix(test, features))[:, 1]
    test_metrics = metrics(test[target], tp, best["threshold"], test.get("sample_weight"))
    signature = hashlib.sha256(json.dumps([features, target, provenance, results], sort_keys=True).encode()).hexdigest()[:10]
    metadata = {"direction": direction, "algorithm": best["algorithm"], "version": signature,
                "provenance": provenance, "features": features, "target": target, "threshold": best["threshold"],
                "horizon": {"min_hours": 24, "max_hours": 48}, "trained_at": datetime.now(timezone.utc).isoformat(),
                "validation_candidates": results, "test": test_metrics,
                "meets_case_metrics": test_metrics["precision"] > .7 and test_metrics["recall"] > .5,
                "training_seconds": round(time.perf_counter() - started, 3),
                "split_ranges": {k: {"rows": len(v), "start": str(v.prediction_time.min()), "end": str(v.prediction_time.max())} for k, v in splits.items()},
                "limitations": ["Synthetic demonstration; metrics do not measure real-world quality"] if provenance == "synthetic_demo" else ["Proxy target, not a confirmed physical failure or fire", "Current object/type mapping is not historically verified", "Scores are not calibrated incident probabilities"]}
    out.mkdir(parents=True, exist_ok=True)
    bundle = {"model": model, "metadata": metadata}
    temp = out / f"{direction}.partial.joblib"
    joblib.dump(bundle, temp)
    temp.replace(out / f"{direction}.joblib")
    (out / f"{direction}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle
