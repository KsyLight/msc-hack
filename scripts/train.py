"""Adapter for the exact data_handoff contract exported by LCT2026_final_EDA."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import duckdb
import pandas as pd
from backend.ml.contracts import SENSOR_FEATURES, SENSOR_PATTERN, INFRASTRUCTURE_PATTERN, TARGETS, validate_features
from backend.ml.training import train_model


def quote(path):
    return "'" + str(path).replace("\\", "/").replace("'", "''") + "'"


def read_split(con, path, features, pattern, target, max_train_rows=None):
    schema = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({quote(path)})").fetchall()}
    required = {"channel_id", "prediction_time", "sensor_type_current", target, *features}
    if required - schema:
        raise ValueError(f"{path}: missing {sorted(required - schema)}")
    if path.stem == "train_compact" and "sample_weight" not in schema:
        raise ValueError("train_compact requires sample_weight to undo negative downsampling")
    columns = ["CAST(channel_id AS VARCHAR) AS entity_id", "prediction_time", target, *features]
    if "sample_weight" in schema:
        columns.append("sample_weight")
    query = f"SELECT {','.join(columns)} FROM read_parquet({quote(path)}) WHERE regexp_matches(lower(sensor_type_current), ?)"
    if max_train_rows:
        query = f"SELECT * FROM ({query}) USING SAMPLE reservoir({int(max_train_rows)} ROWS) REPEATABLE(42)"
    return con.execute(query, [pattern]).fetchdf()


def prepare(handoff: Path, runtime: Path, max_train_rows=400000):
    spec = json.loads((handoff / "feature_list.json").read_text(encoding="utf-8"))
    validate_features(spec["features"])
    if spec["target"] != "target_fault_24_48h" or spec.get("target_window") != "[t+24h,t+48h)":
        raise ValueError("Expected notebook target with at least 24h lead")
    # Count-only baseline: no mixed numeric units and no current metadata in X.
    features = [f for f in SENSOR_FEATURES if f in spec["features"]]
    validate_features(features)
    runtime.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET threads=4")
    patterns = {"sensor": SENSOR_PATTERN, "infrastructure": INFRASTRUCTURE_PATTERN}
    try:
        for direction, pattern in patterns.items():
            splits = {}
            for split in ("train", "validation", "test"):
                name = "train_compact" if split == "train" and (handoff / "ml_ready/train_compact.parquet").exists() else split
                splits[split] = read_split(con, handoff / "ml_ready" / f"{name}.parquet", features, pattern, spec["target"], max_train_rows if split == "train" else None)
                print(f"{direction} {split}: {len(splits[split]):,} rows", flush=True)
            train_model(splits, features, spec["target"], direction, runtime / "models", "notebook_handoff")
        latest_file = handoff / "ml_ready/scoring_latest.parquet"
        schema = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({quote(latest_file)})").fetchall()}
        required = {"channel_id", "object_id_current", "sensor_type_current", "prediction_time", "at_risk_with_history", "last_explicit_state", *features}
        if required - schema:
            raise ValueError(f"scoring_latest missing {required-schema}")
        panels = sorted((handoff / "ml").glob("panel_*.parquet"))
        # Do not load all years just to create a dashboard history.
        if panels:
            latest = con.execute(f"SELECT max(prediction_time) FROM read_parquet({quote(latest_file)})").fetchone()[0]
            start = pd.Timestamp(latest) - pd.Timedelta(days=29)
            paths = [p for p in panels if int(p.stem.rsplit('_', 1)[1]) >= start.year]
            source = "[" + ",".join(quote(p) for p in paths) + "]"
            time_filter = f"prediction_time >= TIMESTAMP '{start.isoformat()}'"
        else:
            source = quote(latest_file)
            time_filter = "true"
        scoring = []
        for direction, pattern in patterns.items():
            frame = con.execute(f"""SELECT CAST(channel_id AS VARCHAR) AS entity_id,
                coalesce(CAST(object_id_current AS VARCHAR),'unknown') AS object_id,
                sensor_type_current AS sensor_type,prediction_time,
                coalesce(at_risk_with_history,false) AS eligible,last_explicit_state,{','.join(features)}
                FROM read_parquet({source}) WHERE {time_filter} AND regexp_matches(lower(sensor_type_current), ?)""", [pattern]).fetchdf()
            frame["direction"] = direction
            scoring.append(frame)
        data = pd.concat(scoring, ignore_index=True)
        if data.empty:
            raise ValueError("No matching channels in latest scoring snapshot")
        data.to_parquet(runtime / "scoring.parquet", index=False)
        objects_file = handoff / "objects_current.parquet"
        names = {}
        if objects_file.exists():
            objects = pd.read_parquet(objects_file)
            names = dict(zip(objects["ид_объект"].astype(str), objects["диспетчерское_название_объекта"]))
        objects = [{"id": oid, "name": str(names.get(oid, f"Объект {oid}")), "district": "Не указан",
                    "latitude": None, "longitude": None, "coordinate_source": "unavailable"} for oid in sorted(data.object_id.unique())]
        (runtime / "objects.json").write_text(json.dumps(objects, ensure_ascii=False), encoding="utf-8")
        metadata = {"mode": "real", "provenance": "notebook_handoff", "source": str(handoff.resolve()),
                    "pipeline_version": spec.get("pipeline_version"), "features": features, "max_train_rows": max_train_rows,
                    "validation_test_sampling": "none", "rows": len(data),
                    "notice": "Исторический срез журналов. Цель — сообщение «Неисправен» через 24–48 ч. Координаты не предоставлены."}
        (runtime / "dataset.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    parser.add_argument("--max-train-rows", type=int, default=400000)
    args = parser.parse_args()
    if args.max_train_rows < 1:
        parser.error("--max-train-rows must be positive")
    destination = args.runtime / "real"
    args.runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="training-", dir=args.runtime) as tmp:
        staging = Path(tmp)
        prepare(args.handoff, staging, args.max_train_rows)
        # Publish only a complete pair. Operational SQLite is never replaced.
        destination.mkdir(exist_ok=True)
        for path in staging.iterdir():
            if path.is_dir():
                shutil.copytree(path, destination / path.name, dirs_exist_ok=True)
            else:
                shutil.copy2(path, destination / path.name)
    print("Training completed. Restart API with APP_MODE=real.")


if __name__ == "__main__":
    main()
