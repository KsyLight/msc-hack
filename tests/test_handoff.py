import json
import pandas as pd
import duckdb
import pytest
from backend.ml.demo import make_demo
from backend.ml.contracts import SENSOR_FEATURES
from backend.config import Settings
from backend.service import RiskService
from scripts.train import prepare, read_split


def test_notebook_contract_can_train_and_serve_without_demo_fallback(tmp_path):
    """Generated fixture of the notebook schema; this is NOT a real-data evaluation."""
    panel, objects = make_demo(seed=19)
    # Small but temporally complete schema fixture for both type groups.
    panel = panel[panel.entity_id.isin(['S-0001','S-0002','S-0003','S-0004','E-0001','E-0002','E-0003','E-0004'])].copy()
    panel = panel.rename(columns={"entity_id": "channel_id", "object_id": "object_id_current", "sensor_type": "sensor_type_current", "eligible": "at_risk_with_history"})
    handoff = tmp_path / "handoff"
    ml = handoff / "ml_ready"
    ml.mkdir(parents=True)
    for name, selection in {
        "train_compact": panel.prediction_time.lt("2026-04-19"),
        "validation": panel.prediction_time.ge("2026-04-21") & panel.prediction_time.lt("2026-05-19"),
        "test": panel.prediction_time.ge("2026-05-21"),
        "scoring_latest": panel.prediction_time.eq(panel.prediction_time.max()),
    }.items():
        panel.loc[selection].to_parquet(ml / f"{name}.parquet", index=False)
    (handoff / "feature_list.json").write_text(json.dumps({"features": SENSOR_FEATURES, "target": "target_fault_24_48h", "target_window": "[t+24h,t+48h)"}))
    pd.DataFrame({"ид_объект": [o["id"] for o in objects], "диспетчерское_название_объекта": [o["name"] for o in objects]}).to_parquet(handoff / "objects_current.parquet")
    settings = Settings(runtime=tmp_path / "runtime", mode="real")
    prepare(handoff, settings.runtime, max_train_rows=10000)
    service = RiskService(settings)
    predictions = service.predictions()
    assert len(predictions) == 8
    assert all(p["mode"] == "real" for p in predictions)
    assert all(o["latitude"] is None for o in service.objects)
    assert len(service.models) == 2
    assert service.dataset["validation_test_sampling"] == "none"


def test_compact_train_requires_sampling_weights(tmp_path):
    path = tmp_path / "train_compact.parquet"
    pd.DataFrame({"channel_id": ['1'], "prediction_time": [pd.Timestamp("2020-01-01")], "sensor_type_current": ['Контактный'], "y": [1], "events_1d": [3]}).to_parquet(path)
    with duckdb.connect() as con, pytest.raises(ValueError, match="sample_weight"):
        read_split(con, path, ["events_1d"], "контакт", "y")
