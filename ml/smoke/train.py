from __future__ import annotations

import argparse
import gc
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier

from features import CHANNEL_HISTORY_FEATURES, CATEGORICAL_FEATURES, TARGET, connect, create_labeled_view, feature_names
from validate import make_catboost_training_pool


def train(args: argparse.Namespace) -> Path:
    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    available_features = feature_names(data_dir)
    if args.feature_subset:
        unknown_features = sorted(set(args.feature_subset) - set(available_features))
        if unknown_features:
            raise ValueError(f"Unknown feature_subset values: {unknown_features}")
        features = list(dict.fromkeys(args.feature_subset))
    else:
        features = available_features
    if args.channel_history:
        features.extend(CHANNEL_HISTORY_FEATURES)
    categorical_features = CATEGORICAL_FEATURES if args.use_categoricals else []
    model_features = list(dict.fromkeys(features + categorical_features))
    if not 0 < args.negative_rate <= 1:
        raise ValueError("negative_rate must be in (0, 1]")
    if args.negative_rate != 1.0:
        raise ValueError("Final CatBoost training currently requires the full negative population")
    con = connect(data_dir, args.memory_limit)
    create_labeled_view(con, data_dir, with_channel_history=args.channel_history)
    parameters = {
        "loss_function": "Logloss",
        "eval_metric": "PRAUC",
        "iterations": args.iterations,
        "depth": args.depth,
        "learning_rate": args.learning_rate,
        "l2_leaf_reg": args.l2_leaf_reg,
        "random_seed": args.seed,
        "thread_count": args.threads,
        "allow_writing_files": False,
        "verbose": args.verbose,
    }
    model = CatBoostClassifier(**parameters)
    with tempfile.TemporaryDirectory(prefix="final_train_", dir=output_dir) as training_dir:
        pool, counts = make_catboost_training_pool(
            con, model_features, 2026, Path(training_dir), args.negative_rate, categorical_features
        )
        con.close()
        if args.positive_weight != 1.0:
            labels = pool.get_label()
            pool.set_weight(np.where(labels == 1, args.positive_weight, 1.0).astype(np.float32))
            del labels
        model.fit(pool)
        del pool
        gc.collect()
    version = f"smoke_catboost_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    model_path = output_dir / f"{version}.cbm"
    model.save_model(model_path)
    metadata = {
        "model_version": version,
        "target": TARGET,
        "features": model_features,
        "categorical_features": categorical_features,
        "channel_history": args.channel_history,
        "feature_subset": args.feature_subset or "all",
        "params": parameters,
        "training_files": ["train.parquet", "validation.parquet"],
        "training_start": "2022-01-01",
        "training_end": "2025-12-31",
        "negative_sampling_rate": args.negative_rate,
        "positive_weight": args.positive_weight,
        "threshold": args.threshold,
        "rows_sampled": counts["sampled_rows"],
        "positives_sampled": counts["sampled_positives"],
        "test_read": False,
    }
    (output_dir / f"{version}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"model": str(model_path), **metadata}, ensure_ascii=False))
    return model_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit the final model using only pre-test labeled data.")
    parser.add_argument("--data-dir", default="data_handoff/fire_ml/ml")
    parser.add_argument("--output-dir", default="data_handoff/fire_ml/models")
    parser.add_argument("--negative-rate", type=float, default=1.0)
    parser.add_argument("--positive-weight", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=343)
    parser.add_argument("--depth", type=int, default=7)
    parser.add_argument("--learning-rate", type=float, default=0.04)
    parser.add_argument("--l2-leaf-reg", type=float, default=8.0)
    parser.add_argument("--use-categoricals", action="store_true")
    parser.add_argument("--channel-history", action="store_true")
    parser.add_argument("--feature-subset", nargs="+", default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="2GB")
    parser.add_argument("--verbose", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())