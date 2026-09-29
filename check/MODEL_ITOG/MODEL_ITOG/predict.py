from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score, confusion_matrix, fbeta_score, precision_score, recall_score

from features import (
    CHANNEL_HISTORY_FEATURES,
    TARGET,
    cast_feature_frame,
    connect,
    create_channel_history_view,
    create_labeled_view,
    sql_literal,
)


def score_test(args: argparse.Namespace) -> dict[str, float | int | str]:
    if not args.evaluate_test:
        raise ValueError("Pass --evaluate-test only for the final, pre-registered test evaluation.")
    model_path = Path(args.model).resolve()
    test_path = Path(args.test_file).resolve()
    prediction_path = Path(args.predictions).resolve()
    if not test_path.exists():
        raise FileNotFoundError(test_path)
    model_meta = json.loads(Path(args.model_metadata).read_text(encoding="utf-8")) if args.model_metadata else {}
    feature_list = model_meta.get("features")
    categorical_features = model_meta.get("categorical_features", [])
    if not feature_list:
        feature_list = json.loads(Path(args.feature_spec).read_text(encoding="utf-8"))["features"]
    threshold = args.threshold
    if threshold is None:
        threshold = model_meta.get("threshold")
    if threshold is None:
        raise ValueError("A threshold selected from OOF predictions is required.")
    model = CatBoostClassifier()
    model.load_model(str(model_path))
    data_dir = test_path.parent
    con = connect(data_dir, args.memory_limit)
    if set(CHANNEL_HISTORY_FEATURES).issubset(feature_list):
        create_labeled_view(con, data_dir, with_channel_history=True)
        con.execute(
            f"CREATE OR REPLACE VIEW test_base AS "
            f"SELECT * FROM read_parquet({sql_literal(test_path)})"
        )
        create_channel_history_view(
            con, "test_base", "labeled_base", "test_features"
        )
        test_source = "test_features"
    else:
        test_source = f"read_parquet({sql_literal(test_path)})"
    selection = ",".join(
        ["channel_id", "prediction_time", TARGET]
        + ['"' + name.replace('"', '""') + '"' for name in feature_list]
    )
    result = con.execute(f"SELECT {selection} FROM {test_source}")
    reader = result.to_arrow_reader(args.batch_size)
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    labels: list[np.ndarray] = []
    probabilities: list[np.ndarray] = []
    rows = 0
    try:
        for batch in reader:
            frame = batch.to_pandas()
            y = frame.pop(TARGET).to_numpy(dtype=np.int8)
            channel = frame.pop("channel_id").astype(str).to_numpy()
            timestamp = pd.to_datetime(frame.pop("prediction_time")).to_numpy()
            probability = model.predict_proba(cast_feature_frame(frame, categorical_features))[:, 1].astype(np.float32)
            predictions = probability >= threshold
            table = pa.table({
                "channel_id": channel,
                "prediction_time": timestamp,
                "y_true": y,
                "probability": probability,
                "prediction": predictions.astype(np.int8),
                "threshold": np.full(len(y), threshold, dtype=np.float32),
            })
            if writer is None:
                writer = pq.ParquetWriter(prediction_path, table.schema, compression="zstd")
            writer.write_table(table)
            labels.append(y)
            probabilities.append(probability)
            rows += len(y)
    finally:
        if writer is not None:
            writer.close()
        con.close()
    y_true = np.concatenate(labels)
    probability = np.concatenate(probabilities)
    predicted = probability >= threshold
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    metrics = {
        "rows": int(rows),
        "prevalence": float(y_true.mean()),
        "average_precision": float(average_precision_score(y_true, probability)),
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "f2": float(fbeta_score(y_true, predicted, beta=2, zero_division=0)),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "predictions": str(prediction_path),
    }
    print(json.dumps(metrics, indent=2))
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream the registered final test once after model selection is frozen.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-metadata")
    parser.add_argument("--feature-spec", default="data_handoff/fire_ml/feature_list.json")
    parser.add_argument("--test-file", default="data_handoff/fire_ml/ml/test.parquet")
    parser.add_argument("--predictions", default="data_handoff/fire_ml/final_test_predictions.parquet")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--evaluate-test", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--memory-limit", default="2GB")
    return parser.parse_args()


if __name__ == "__main__":
    score_test(parse_args())