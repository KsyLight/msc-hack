from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Any

import duckdb

TARGET = "smoke_signal_24_48h"
IDENTIFIERS = ["channel_id", "prediction_time"]
CATEGORICAL_FEATURES = ["sensor_type_current", "system_type_current"]
METADATA = [
    "target_start",
    "target_end",
    "sensor_type_current",
    "object_id_current",
    "system_type_current",
    "feature_max_ts",
    "last_explicit_state",
    "last_state_ts",
    "at_risk_with_history",
    "channel_followup_48h",
    "global_complete_24_48h",
    "first_seen",
    "last_seen",
]


def sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''").replace("\\", "/") + "'"


def parquet_list(paths: list[Path]) -> str:
    return "[" + ",".join(sql_literal(path) for path in paths) + "]"


def connect(data_dir: Path, memory_limit: str = "2GB") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit={sql_literal(memory_limit)}")
    con.execute("SET threads=2")
    temp_dir = data_dir.parent / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory={sql_literal(temp_dir)}")
    return con


def labeled_paths(data_dir: Path) -> list[Path]:
    paths = [data_dir / "train.parquet", data_dir / "validation.parquet"]
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing pre-test labeled files: " + ", ".join(map(str, missing)))
    return paths


def feature_names(data_dir: Path) -> list[str]:
    spec_path = data_dir.parent / "feature_list.json"
    if spec_path.exists():
        return json.loads(spec_path.read_text(encoding="utf-8"))["features"]
    con = connect(data_dir)
    try:
        names = [row[0] for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({parquet_list(labeled_paths(data_dir))}, union_by_name=true)"
        ).fetchall()]
    finally:
        con.close()
    excluded = set(IDENTIFIERS + METADATA + [TARGET])
    return [name for name in names if name not in excluded]


def cast_feature_frame(frame: Any, categorical_features: list[str] | None = None) -> Any:
    categorical = set(categorical_features or [])
    numeric = [name for name in frame.columns if name not in categorical]
    if numeric:
        frame[numeric] = frame[numeric].astype("float32")
    for name in categorical:
        frame[name] = frame[name].fillna("__MISSING__").astype(str)
    return frame


CHANNEL_HISTORY_FEATURES = ["channel_history_count", "channel_history_rate"]


def create_labeled_view(
    con: duckdb.DuckDBPyConnection,
    data_dir: Path,
    with_channel_history: bool = False,
    channel_history_alpha: float = 100.0,
) -> None:
    paths = labeled_paths(data_dir)
    base_sql = f"SELECT * FROM read_parquet({parquet_list(paths)}, union_by_name=true)"
    con.execute(f"CREATE OR REPLACE VIEW labeled_base AS {base_sql}")
    if with_channel_history:
        create_channel_history_view(
            con, "labeled_base", "labeled_base", "labeled", channel_history_alpha
        )
    else:
        con.execute("CREATE OR REPLACE VIEW labeled AS SELECT * FROM labeled_base")


def create_channel_history_view(
    con: duckdb.DuckDBPyConnection,
    rows_view: str,
    history_view: str,
    output_view: str,
    alpha: float = 100.0,
) -> None:
    view_names = (rows_view, history_view, output_view)
    if any(not name.replace("_", "").isalnum() or name[0].isdigit() for name in view_names):
        raise ValueError("View names must be simple SQL identifiers")
    if alpha < 0:
        raise ValueError("channel_history_alpha must be non-negative")
    con.execute(f"""
        CREATE OR REPLACE VIEW {output_view} AS
        WITH by_end AS (
            SELECT channel_id, target_end, sum({TARGET})::DOUBLE AS pos, count(*)::DOUBLE AS n
            FROM {history_view}
            GROUP BY channel_id, target_end
        ), channel_cum AS (
            -- ASOF joins below restrict both histories to target_end <= prediction_time
            SELECT channel_id, target_end,
                sum(pos) OVER (PARTITION BY channel_id ORDER BY target_end
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_pos,
                sum(n) OVER (PARTITION BY channel_id ORDER BY target_end
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_n
            FROM by_end
        ), global_by_end AS (
            SELECT target_end, sum({TARGET})::DOUBLE AS g_pos, count(*)::DOUBLE AS g_n
            FROM {history_view}
            GROUP BY target_end
        ), global_cum AS (
            SELECT target_end,
                sum(g_pos) OVER (ORDER BY target_end
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_pos,
                sum(g_n) OVER (ORDER BY target_end
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_n
            FROM global_by_end
        )
        SELECT r.*,
            coalesce(c.cum_pos, 0)::FLOAT AS channel_history_count,
            (
                (coalesce(c.cum_pos, 0) + {alpha} *
                    coalesce(g.cum_pos / NULLIF(g.cum_n, 0), 0.0))
                / (coalesce(c.cum_n, 0) + {alpha})
            )::FLOAT AS channel_history_rate
        FROM {rows_view} r
        ASOF LEFT JOIN channel_cum c
            ON r.channel_id = c.channel_id AND r.prediction_time >= c.target_end
        ASOF LEFT JOIN global_cum g
            ON r.prediction_time >= g.target_end
    """)


def temporal_folds() -> list[tuple[int, str]]:
    return [(year, f"expanding_to_{year - 1}") for year in range(2022, 2026)]


def audit_training_data(data_dir: Path) -> dict[str, Any]:
    con = connect(data_dir)
    create_labeled_view(con, data_dir)
    features = feature_names(data_dir)
    outputs: dict[str, Any] = {"target": TARGET, "positive_class": 1, "features": len(features), "splits": {}}
    try:
        for split in ("train", "validation"):
            path = data_dir / f"{split}.parquet"
            source = f"read_parquet({sql_literal(path)})"
            count, positive, min_year, max_year, duplicate_keys, duplicate_rows = con.execute(
                f"""SELECT count(*), sum({TARGET}), min(year(prediction_time)), max(year(prediction_time)),
                    count(*)-count(DISTINCT (channel_id,prediction_time)),
                    count(*)-count(DISTINCT hash(channel_id,prediction_time,{TARGET}))
                    FROM {source}"""
            ).fetchone()
            future_feature_rows = con.execute(
                f"SELECT count(*) FROM {source} WHERE feature_max_ts>prediction_time"
            ).fetchone()[0]
            if future_feature_rows:
                raise ValueError(f"{split} has {future_feature_rows} rows with features after prediction_time")
            expressions: list[str] = []
            for name in features:
                escaped = '"' + name.replace('"', '""') + '"'
                expressions.extend([f"count({escaped})", f"approx_count_distinct({escaped})"])
            values = con.execute(f"SELECT {','.join(expressions)} FROM {source}").fetchone()
            null_features = [
                name for index, name in enumerate(features) if values[index * 2] < count
            ]
            constant_features = [
                name for index, name in enumerate(features) if values[index * 2 + 1] <= 1
            ]
            years = con.execute(
                f"SELECT year(prediction_time), count(*), sum({TARGET}) FROM {source} "
                "GROUP BY 1 ORDER BY 1"
            ).fetchall()
            outputs["splits"][split] = {
                "rows": count,
                "positives": positive,
                "prevalence": positive / count,
                "min_year": min_year,
                "max_year": max_year,
                "duplicate_channel_time_keys": duplicate_keys,
                "duplicate_target_rows": duplicate_rows,
                "future_feature_rows": future_feature_rows,
                "features_with_nulls": null_features,
                "constant_features": constant_features,
                "year_counts": years,
            }
        overlap = con.execute(
            f"""SELECT count(*) FROM (
                SELECT t.channel_id,t.prediction_time
                FROM read_parquet({sql_literal(data_dir / 'train.parquet')}) t
                INNER JOIN read_parquet({sql_literal(data_dir / 'validation.parquet')}) v
                USING(channel_id,prediction_time)
            )"""
        ).fetchone()[0]
        outputs["train_validation_key_overlap"] = overlap
        outputs["test_read"] = False
    finally:
        con.close()
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit only pre-test train and validation parquet files.")
    parser.add_argument("--data-dir", default="data_handoff/fire_ml/ml")
    parser.add_argument("--output", default="data_handoff/fire_ml/audit/data_audit_train_validation.json")
    args = parser.parse_args()
    report = audit_training_data(Path(args.data_dir).resolve())
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))