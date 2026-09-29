"""Validate prepared notebook exports without loading the full journal into RAM."""
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from backend.ml.contracts import HANDOFF_FEATURES, SENSOR_FEATURES, validate_features


def quote(path):
    return "'" + str(path).replace("\\", "/").replace("'", "''") + "'"


def columns(con, path):
    return {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({quote(path)})").fetchall()}


def contract(handoff):
    ml = handoff / "ml_ready" if (handoff / "ml_ready").is_dir() else handoff
    spec_file = handoff / "feature_list.json"
    if spec_file.exists():
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        validate_features(spec["features"])
        if spec["target"] != "target_fault_24_48h" or spec.get("target_window") != "[t+24h,t+48h)":
            raise ValueError("Expected notebook target with at least 24h lead")
        features = [f for f in SENSOR_FEATURES if f in spec["features"]]
        spec["contract_source"] = "feature_list.json"
    else:
        # Never discover features by excluding just the known target columns.
        # A fixed whitelist prevents diagnostics/future availability from entering X.
        features = HANDOFF_FEATURES.copy()
        spec = {"target": "target_fault_24_48h", "target_window": "[t+24h,t+48h)",
                "pipeline_version": "prepared-parquet-v1", "contract_source": "audited_fixed_whitelist"}
    validate_features(features)
    spec["model_features"] = features
    return ml, spec, features


def audit(con, ml, spec, features):
    report = {"contract": spec, "splits": {}, "files": []}
    strict = spec["contract_source"] == "audited_fixed_whitelist"
    checks = {
        "future_features": "feature_max_ts IS NULL OR feature_max_ts >= prediction_time",
        "wrong_target_window": "target_start IS NULL OR target_end IS NULL OR target_start != prediction_time + INTERVAL '24 hours' OR target_end != prediction_time + INTERVAL '48 hours'",
        "ineligible": "at_risk_with_history IS DISTINCT FROM true",
        "incomplete_followup": "channel_followup_48h IS DISTINCT FROM true OR global_complete_24_48h IS DISTINCT FROM true",
    }
    diagnostic = {"feature_max_ts", "target_start", "target_end", "at_risk_with_history", "channel_followup_48h", "global_complete_24_48h"}
    for split in ("train", "validation", "test", "scoring_latest"):
        name = "train_compact" if split == "train" and (ml / "train_compact.parquet").exists() else split
        path = ml / f"{name}.parquet"
        schema = columns(con, path)
        required = {"channel_id", "prediction_time", "sensor_type_current", *features}
        if strict:
            required |= {"feature_max_ts", "at_risk_with_history", "last_explicit_state"}
        if split != "scoring_latest":
            required.add(spec["target"])
            if strict:
                required |= diagnostic
        if required - schema:
            raise ValueError(f"{path.name}: missing {sorted(required - schema)}")
        base = f"FROM read_parquet({quote(path)})"
        query = "count(*) AS row_count, min(prediction_time) AS first_time, max(prediction_time) AS last_time, count(distinct channel_id) AS channels, count(*) - count(distinct (channel_id,prediction_time)) AS duplicate_keys, count(*) filter(where channel_id IS NULL OR prediction_time IS NULL) AS missing_keys"
        if split != "scoring_latest":
            query += f", sum({spec['target']}) AS positives, count(*) filter(where {spec['target']} IS NULL OR {spec['target']} NOT IN (0,1)) AS invalid_labels"
            if diagnostic <= schema:
                query += ", " + ", ".join(f"count(*) filter(where {condition}) AS {key}" for key, condition in checks.items())
        elif "feature_max_ts" in schema:
            query += f", count(*) filter(where {checks['future_features']}) AS future_features"
        if strict:
            query += ", count(*) filter(where at_risk_with_history AND last_explicit_state IS DISTINCT FROM 'норма') AS invalid_eligible_state"
        row = con.execute(f"SELECT {query} {base}").fetchdf().iloc[0].to_dict()
        for key in ["duplicate_keys", "missing_keys", "invalid_labels", "invalid_eligible_state", *checks]:
            if row.get(key, 0):
                raise ValueError(f"{path.name}: {key}={row[key]}")
        if name == "train_compact":
            if not {"sample_weight", "sampling_probability"} <= schema and strict:
                raise ValueError("train_compact requires sample_weight and sampling_probability")
            if "sampling_probability" in schema:
                invalid = con.execute(f"SELECT count(*) {base} WHERE sampling_probability IS NULL OR sampling_probability <= 0 OR sampling_probability > 1 OR sample_weight IS NULL OR NOT isfinite(sample_weight::double) OR abs(sample_weight * sampling_probability - 1) > 0.00001").fetchone()[0]
                if invalid:
                    raise ValueError("Invalid inverse sampling weights")
        report["splits"][split] = {"file": path.name, **row}
        print(f"Audited {path.name}: {row['row_count']:,} rows; no invalid keys/labels or temporal leakage", flush=True)
    for left, right in [("train", "validation"), ("validation", "test")]:
        if report["splits"][left]["last_time"] + pd.Timedelta(hours=48) > report["splits"][right]["first_time"]:
            raise ValueError(f"{left}/{right}: target windows overlap")
    # Small manifest also accounts for deliberately unused full/excluded files.
    for path in sorted(ml.glob("*.parquet")):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        report["files"].append({"name": path.name, "rows": pq.ParquetFile(path).metadata.num_rows,
                                "bytes": path.stat().st_size, "sha256": digest})
    return json.loads(json.dumps(report, default=str, ensure_ascii=False))


def export_daily(con, handoff: Path, runtime: Path, patterns, snapshot):
    paths = sorted(handoff.glob("daily_*.parquet"))
    if not paths:
        return None
    channels = handoff / "channels_current.parquet"
    if not channels.exists():
        return None
    source = "[" + ",".join(quote(p) for p in paths) + "]"
    con.execute(f"CREATE OR REPLACE TEMP VIEW daily AS SELECT * FROM read_parquet({source})")
    if con.execute("SELECT count(*) - count(distinct (channel_id,day)) FROM daily").fetchone()[0]:
        raise ValueError("Duplicate channel/day keys in daily files")
    join = f"FROM daily d LEFT JOIN read_parquet({quote(channels)}) c ON d.channel_id=c.ид_канала_данных WHERE d.day < ?"
    start, end, events, alarms, faults, unknown = con.execute(f"SELECT min(day),max(day),sum(events),sum(alarms),sum(fault_messages),count(*) filter(where c.ид_канала_данных IS NULL) {join}", [snapshot]).fetchone()
    frame = con.execute(f"""SELECT day AS date, sum(events) AS events, sum(alarms) AS alarms,
        sum(fault_messages) AS fault_messages, count(distinct d.channel_id) AS active_channels,
        sum(CASE WHEN regexp_matches(lower(c.тип_датчика), ?) THEN fault_messages ELSE 0 END) AS sensor,
        sum(CASE WHEN regexp_matches(lower(c.тип_датчика), ?) THEN fault_messages ELSE 0 END) AS infrastructure
        {join} GROUP BY day ORDER BY day""", [patterns["sensor"], patterns["infrastructure"], snapshot]).fetchdf()
    frame.to_parquet(runtime / "observations.parquet", index=False)
    missing_days = pd.date_range(start, end).difference(pd.DatetimeIndex(frame.date)) if start else []
    return {"source_files": [p.name for p in paths], "start": str(start), "end": str(end),
            "days": len(frame), "events": int(events or 0), "alarms": int(alarms or 0),
            "fault_messages": int(faults or 0), "unmapped_channel_days": int(unknown),
            "missing_days": [str(day.date()) for day in missing_days]}
