from __future__ import annotations

import argparse
import json
import gc
import tempfile
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from duckdb import DuckDBPyConnection
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, fbeta_score, precision_recall_curve, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from features import CATEGORICAL_FEATURES, CHANNEL_HISTORY_FEATURES, TARGET, cast_feature_frame, connect, create_labeled_view, feature_names, labeled_paths


def sql_column(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_sampled_training(
    con: DuckDBPyConnection,
    features: list[str],
    valid_year: int,
    negative_rate: float,
    seed: int,
    categorical_features: list[str] | None = None,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, dict[str, int]]:
    categorical_features = categorical_features or []
    start = f"{valid_year}-01-01"
    if not 0 < negative_rate <= 1:
        raise ValueError("negative_rate must be in (0, 1]")
    columns = ",".join([sql_column(name) for name in features + categorical_features] + [TARGET])
    sample_mod = max(1, round(1 / negative_rate))
    query = f"""
        SELECT {columns}
        FROM labeled
                WHERE prediction_time >= TIMESTAMP '2022-01-01'
                    AND prediction_time < TIMESTAMP '{start}'
          AND target_end <= TIMESTAMP '{start}'
          AND ({TARGET}=1 OR hash(channel_id,prediction_time,{seed})%{sample_mod}=0)
    """
    train = con.execute(query).fetch_df()
    y = train.pop(TARGET).to_numpy(dtype=np.int8)
    train = cast_feature_frame(train, categorical_features)
    weights = np.where(y == 1, 1.0, 1.0 / negative_rate).astype(np.float32)
    full_counts = con.execute(
        f"""SELECT count(*),sum({TARGET}) FROM labeled
                        WHERE prediction_time >= TIMESTAMP '2022-01-01'
                            AND prediction_time < TIMESTAMP '{start}'
                            AND target_end <= TIMESTAMP '{start}'"""
    ).fetchone()
    return train, y, weights, {
        "sampled_rows": len(y),
        "sampled_positives": int(y.sum()),
        "population_rows": int(full_counts[0]),
        "population_positives": int(full_counts[1]),
    }


def make_catboost_training_pool(
    con: DuckDBPyConnection,
    features: list[str],
    valid_year: int,
    directory: Path,
    negative_rate: float,
    categorical_features: list[str] | None = None,
) -> tuple[Any, dict[str, int]]:
    from catboost import Pool

    categorical_features = categorical_features or []
    if negative_rate != 1.0:
        raise ValueError("CatBoost OOF currently requires the full negative population")
    start = f"{valid_year}-01-01"
    data_path = directory / "train.tsv"
    description_path = directory / "train.cd"
    feature_columns = []
    for name in features:
        column = sql_column(name)
        if name in categorical_features:
            feature_columns.append(f"coalesce(CAST({column} AS VARCHAR), '__MISSING__') AS {column}")
        else:
            feature_columns.append(f"CAST({column} AS FLOAT) AS {column}")
    columns = ",".join([sql_column(TARGET)] + feature_columns)
    where = f"""prediction_time >= TIMESTAMP '2022-01-01'
        AND prediction_time < TIMESTAMP '{start}'
        AND target_end <= TIMESTAMP '{start}'"""
    destination = str(data_path).replace("'", "''")
    con.execute(
        f"COPY (SELECT {columns} FROM labeled WHERE {where}) "
        f"TO '{destination}' (FORMAT CSV, DELIMITER '\\t', HEADER FALSE, NULL 'NaN')"
    )
    description_path.write_text(
        "0\tLabel\n" + "".join(
            f"{index}\t{'Categ' if name in categorical_features else 'Num'}\n"
            for index, name in enumerate(features, start=1)
        ),
        encoding="ascii",
    )
    counts = con.execute(
        f"SELECT count(*),sum({TARGET}) FROM labeled WHERE {where}"
    ).fetchone()
    pool = Pool(
        str(data_path),
        column_description=str(description_path),
        delimiter="\t",
        has_header=False,
        thread_count=2,
    )
    return pool, {
        "sampled_rows": int(counts[0]),
        "sampled_positives": int(counts[1]),
        "population_rows": int(counts[0]),
        "population_positives": int(counts[1]),
    }


def make_model(name: str, seed: int, iterations: int) -> Any:
    if name == "dummy":
        return DummyClassifier(strategy="prior")
    if name == "logistic":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(
                C=0.5,
                max_iter=300,
                solver="lbfgs",
                random_state=seed,
                tol=1e-3,
            )),
        ])
    if name in {"catboost", "catboost_cat"}:
        from catboost import CatBoostClassifier

        return CatBoostClassifier(
            loss_function="Logloss",
            eval_metric="PRAUC",
            iterations=iterations,
            depth=7,
            learning_rate=0.04,
            l2_leaf_reg=8,
            random_seed=seed,
            thread_count=4,
            allow_writing_files=False,
            verbose=False,
        )
    if name == "lightgbm":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            objective="binary",
            n_estimators=iterations,
            learning_rate=0.04,
            num_leaves=31,
            max_depth=-1,
            random_state=seed,
            n_jobs=4,
            verbosity=-1,
        )
    if name == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(
            objective="binary:logistic",
            eval_metric="aucpr",
            n_estimators=iterations,
            max_depth=7,
            learning_rate=0.04,
            subsample=0.8,
            colsample_bytree=0.8,
            tree_method="hist",
            random_state=seed,
            n_jobs=4,
        )
    raise ValueError(f"Unsupported model: {name}")


def fit_model(model: Any, name: str, X: pd.DataFrame, y: np.ndarray, weights: np.ndarray) -> None:
    if name == "dummy":
        model.fit(np.zeros((len(y), 1), dtype=np.float32), y, sample_weight=weights)
    elif name == "logistic":
        model.fit(X, y, model__sample_weight=weights)
    elif name == "catboost_cat":
        model.fit(X, y, sample_weight=weights, cat_features=CATEGORICAL_FEATURES)
    else:
        model.fit(X, y, sample_weight=weights)


def predict_batches(
    con: DuckDBPyConnection,
    model: Any,
    model_name: str,
    features: list[str],
    valid_year: int,
    batch_size: int,
    writer: pq.ParquetWriter,
) -> tuple[np.ndarray, np.ndarray, int]:
    start, end = f"{valid_year}-01-01", f"{valid_year + 1}-01-01"
    categorical_features = CATEGORICAL_FEATURES if model_name == "catboost_cat" else []
    selected_features = [] if model_name == "dummy" else features + categorical_features
    selection = ",".join(
        ["channel_id", "prediction_time", TARGET] + [sql_column(name) for name in selected_features]
    )
    result = con.execute(
        f"""SELECT {selection} FROM labeled
            WHERE prediction_time >= TIMESTAMP '{start}' AND prediction_time < TIMESTAMP '{end}'"""
    )
    reader = result.fetch_record_batch(rows_per_batch=batch_size)
    labels: list[np.ndarray] = []
    probabilities: list[np.ndarray] = []
    row_count = 0
    for batch in reader:
        frame = batch.to_pandas()
        y = frame.pop(TARGET).to_numpy(dtype=np.int8)
        channel = frame.pop("channel_id").astype(str).to_numpy()
        timestamp = pd.to_datetime(frame.pop("prediction_time")).to_numpy()
        X = cast_feature_frame(frame, categorical_features)
        if model_name == "dummy":
            probability = model.predict_proba(np.zeros((len(y), 1), dtype=np.float32))[:, 1]
        else:
            probability = model.predict_proba(X)[:, 1]
        table = pa.table({
            "fold_year": np.full(len(y), valid_year, dtype=np.int16),
            "channel_id": channel,
            "prediction_time": timestamp,
            "y_true": y,
            "probability": probability.astype(np.float32),
        })
        writer.write_table(table)
        labels.append(y)
        probabilities.append(probability.astype(np.float32))
        row_count += len(y)
    if not labels:
        raise ValueError(f"No labeled validation rows for year {valid_year}")
    return np.concatenate(labels), np.concatenate(probabilities), row_count


def choose_f2_threshold(y: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    precision, recall, thresholds = precision_recall_curve(y, probability)
    f2 = 5 * precision[:-1] * recall[:-1] / (4 * precision[:-1] + recall[:-1] + 1e-12)
    if len(thresholds) == 0:
        return 0.5, 0.0
    index = int(np.nanargmax(f2))
    return float(thresholds[index]), float(f2[index])


def run(args: argparse.Namespace) -> pd.DataFrame:
    if not args.fold_years or any(year < 2023 for year in args.fold_years):
        raise ValueError("fold_years must contain only years 2023 and later")
    if not 0 < args.negative_rate <= 1:
        raise ValueError("negative_rate must be in (0, 1]")
    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in labeled_paths(data_dir):
        if not path.exists():
            raise FileNotFoundError(path)
    available_features = feature_names(data_dir)
    if args.feature_subset:
        unknown_features = sorted(set(args.feature_subset) - set(available_features))
        if unknown_features:
            raise ValueError(f"Unknown feature_subset values: {unknown_features}")
        features = list(dict.fromkeys(args.feature_subset))
    else:
        features = available_features
    if args.channel_history:
        features = features + CHANNEL_HISTORY_FEATURES
    con = connect(data_dir, args.memory_limit)
    create_labeled_view(con, data_dir, with_channel_history=args.channel_history)
    result_rows: list[dict[str, Any]] = []
    try:
        for model_name in args.models.split(","):
            model_name = model_name.strip().lower()
            oof_path = output_dir / f"oof_{model_name}.parquet"
            if oof_path.exists():
                oof_path.unlink()
            writer: pq.ParquetWriter | None = None
            all_y: list[np.ndarray] = []
            all_probability: list[np.ndarray] = []
            fold_scores: list[float] = []
            params: dict[str, Any] = {
                "train_start": "2022-01-01",
                "negative_rate": args.negative_rate,
                "fold_years": args.fold_years,
                "seed": args.seed,
                "channel_history": args.channel_history,
                "feature_subset": args.feature_subset or "all",
            }
            if model_name == "logistic":
                params.update({"C": 0.5, "max_iter": 300, "imputer": "median+indicator", "scaler": "standard"})
            elif model_name == "catboost":
                params.update({"iterations": args.catboost_iterations, "depth": 7, "learning_rate": 0.04, "l2_leaf_reg": 8})
            elif model_name == "catboost_cat":
                params.update({"iterations": args.catboost_iterations, "depth": 7, "learning_rate": 0.04, "l2_leaf_reg": 8, "categorical_features": CATEGORICAL_FEATURES})
            elif model_name == "lightgbm":
                params.update({"iterations": args.catboost_iterations, "num_leaves": 31, "learning_rate": 0.04})
            elif model_name == "xgboost":
                params.update({"iterations": args.catboost_iterations, "max_depth": 7, "learning_rate": 0.04, "subsample": 0.8, "colsample_bytree": 0.8})
            try:
                for valid_year in args.fold_years:
                    model = make_model(model_name, args.seed, args.catboost_iterations)
                    if model_name == "catboost":
                        with tempfile.TemporaryDirectory(
                            prefix=f"catboost_{valid_year}_", dir=output_dir
                        ) as training_dir:
                            train_pool, counts = make_catboost_training_pool(
                                con, features, valid_year, Path(training_dir), args.negative_rate
                            )
                            model.fit(train_pool)
                            del train_pool
                            gc.collect()
                    else:
                        train, y_train, weights, counts = get_sampled_training(
                            con, [] if model_name == "dummy" else features,
                            valid_year, args.negative_rate, args.seed,
                            CATEGORICAL_FEATURES if model_name == "catboost_cat" else [],
                        )
                        fit_model(model, model_name, train, y_train, weights)
                    schema = pa.schema([
                        ("fold_year", pa.int16()),
                        ("channel_id", pa.string()),
                        ("prediction_time", pa.timestamp("us")),
                        ("y_true", pa.int8()),
                        ("probability", pa.float32()),
                    ])
                    if writer is None:
                        writer = pq.ParquetWriter(oof_path, schema, compression="zstd")
                    y_valid, probability, valid_rows = predict_batches(
                        con, model, model_name, features, valid_year, args.batch_size, writer
                    )
                    score = float(average_precision_score(y_valid, probability))
                    fold_scores.append(score)
                    all_y.append(y_valid)
                    all_probability.append(probability)
                    print(json.dumps({
                        "model": model_name,
                        "fold_year": valid_year,
                        "train_sample_rows": counts["sampled_rows"],
                        "train_population_rows": counts["population_rows"],
                        "validation_rows": valid_rows,
                        "validation_prevalence": float(y_valid.mean()),
                        "pr_auc": score,
                    }))
                    del model
                    if model_name != "catboost":
                        del train, y_train, weights
                    gc.collect()
            finally:
                if writer is not None:
                    writer.close()
            oof_y = np.concatenate(all_y)
            oof_probability = np.concatenate(all_probability)
            if model_name == "dummy":
                threshold = 0.5
                f2 = float(fbeta_score(oof_y, oof_probability >= threshold, beta=2, zero_division=0))
            else:
                threshold, f2 = choose_f2_threshold(oof_y, oof_probability)
            precision = float(precision_score(oof_y, oof_probability >= threshold, zero_division=0))
            recall = float(recall_score(oof_y, oof_probability >= threshold, zero_division=0))
            threshold_rows = []
            candidate_thresholds = sorted(set([threshold, 0.0025, 0.005, 0.01, 0.02, 0.05]))
            for candidate in candidate_thresholds:
                predicted = oof_probability >= candidate
                tn, fp, fn, tp = confusion_matrix(oof_y, predicted, labels=[0, 1]).ravel()
                threshold_rows.append({
                    "model": model_name,
                    "threshold": candidate,
                    "is_oof_f2_optimum": candidate == threshold,
                    "precision": precision_score(oof_y, predicted, zero_division=0),
                    "recall": recall_score(oof_y, predicted, zero_division=0),
                    "f2": fbeta_score(oof_y, predicted, beta=2, zero_division=0),
                    "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
                })
            pd.DataFrame(threshold_rows).to_csv(output_dir / f"thresholds_{model_name}.csv", index=False)
            tn, fp, fn, tp = confusion_matrix(oof_y, oof_probability >= threshold, labels=[0, 1]).ravel()
            row = {
                "model": model_name,
                "params": json.dumps(params, sort_keys=True),
                "cv_pr_auc_mean": float(np.mean(fold_scores)),
                "cv_pr_auc_std": float(np.std(fold_scores, ddof=1)) if len(fold_scores) > 1 else 0.0,
                "oof_pr_auc": float(average_precision_score(oof_y, oof_probability)),
                "f2": f2,
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
                "oof_rows": int(len(oof_y)),
                "oof_positives": int(oof_y.sum()),
                "oof_file": str(oof_path),
            }
            result_rows.append(row)
            print(json.dumps(row))
    finally:
        con.close()
    results = pd.DataFrame(result_rows)
    log_path = output_dir / "experiments.csv"
    if log_path.exists():
        old = pd.read_csv(log_path)
        results = pd.concat([old, results], ignore_index=True)
    results.to_csv(log_path, index=False)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expanding-window OOF validation without reading the final test set.")
    parser.add_argument("--data-dir", default="data_handoff/fire_ml/ml")
    parser.add_argument("--output-dir", default="data_handoff/fire_ml/experiments")
    parser.add_argument("--models", default="dummy,logistic")
    parser.add_argument("--fold-years", nargs="+", type=int, default=[2023, 2024, 2025])
    parser.add_argument("--negative-rate", type=float, default=1.0)
    parser.add_argument(
        "--channel-history", action="store_true",
        help="Add leakage-safe expanding channel_history_count/rate features (fit causally, target_end-ordered).",
    )
    parser.add_argument(
        "--feature-subset", nargs="+", default=None,
        help="Optional numeric feature subset; channel-history features are appended when requested.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--catboost-iterations", type=int, default=343)
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--memory-limit", default="2GB")
    return parser.parse_args()


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning)
    run(parse_args())