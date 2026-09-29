import json
import pandas as pd
import duckdb
import pytest
from backend.ml.demo import make_demo
from backend.ml.contracts import SENSOR_FEATURES, HANDOFF_FEATURES
from backend.config import Settings
from backend.service import RiskService
from scripts.train import prepare, read_split
from scripts.handoff import contract, audit


@pytest.mark.parametrize("flat", [False, True])
def test_notebook_contract_can_train_and_serve_without_demo_fallback(tmp_path, flat):
    """Generated fixture of the notebook schema; this is NOT a real-data evaluation."""
    panel, objects = make_demo(seed=19)
    # Small but temporally complete schema fixture for both type groups.
    panel = panel[panel.entity_id.isin(['S-0001','S-0002','S-0003','S-0004','E-0001','E-0002','E-0003','E-0004'])].copy()
    panel = panel.rename(columns={"entity_id": "channel_id", "object_id": "object_id_current", "sensor_type": "sensor_type_current", "eligible": "at_risk_with_history"})
    handoff = tmp_path / "handoff"
    ml = handoff if flat else handoff / "ml_ready"
    ml.mkdir(parents=True)
    if flat:
        for feature in HANDOFF_FEATURES:
            if feature not in panel:
                panel[feature] = 0.0
        panel.loc[panel.channel_id.str.startswith("S-"), "sensor_type_current"] = "КД Дверь"
        panel["feature_max_ts"] = panel.prediction_time - pd.Timedelta(hours=1)
        panel["target_start"] = panel.prediction_time + pd.Timedelta(hours=24)
        panel["target_end"] = panel.prediction_time + pd.Timedelta(hours=48)
        panel["channel_followup_48h"] = True
        panel["global_complete_24_48h"] = True
        panel["sampling_probability"] = 1 / panel.sample_weight
    for name, selection in {
        "train_compact": panel.prediction_time.lt("2026-04-19"),
        "validation": panel.prediction_time.ge("2026-04-21") & panel.prediction_time.lt("2026-05-19"),
        "test": panel.prediction_time.ge("2026-05-21"),
        "scoring_latest": panel.prediction_time.eq(panel.prediction_time.max()),
    }.items():
        if flat and name != "scoring_latest":
            selection &= panel.at_risk_with_history
        panel.loc[selection].to_parquet(ml / f"{name}.parquet", index=False)
    if not flat:
        (handoff / "feature_list.json").write_text(json.dumps({"features": SENSOR_FEATURES, "target": "target_fault_24_48h", "target_window": "[t+24h,t+48h)"}))
    channels = panel[["channel_id"]].drop_duplicates().rename(columns={"channel_id": "ид_канала_данных"})
    channels["тип_инж_системы"] = "Тестовая система"
    channels["название_датчика"] = "Датчик у входа"
    channels["тег_инженерной_системы"] = "test-tag"
    channels.to_parquet(handoff / "channels_current.parquet", index=False)
    pd.DataFrame({"ид_объект": [o["id"] for o in objects], "диспетчерское_название_объекта": [o["name"] for o in objects]}).to_parquet(handoff / "objects_current.parquet")
    settings = Settings(runtime=tmp_path / "runtime", mode="real")
    prepare(handoff, settings.runtime, max_train_rows=10000)
    service = RiskService(settings)
    predictions = service.predictions()
    assert len(predictions) == 8
    assert all(p["mode"] == "real" for p in predictions)
    assert all(p["system_type"] == "Тестовая система" and p["sensor_name"] == "Датчик у входа" for p in predictions)
    assert all(o["latitude"] is None for o in service.objects)
    assert len(service.models) == 2
    assert service.dataset["validation_test_sampling"] == "none"
    found = service.prediction_page(True, None, None, None, "ТЕСТОВАЯ СИСТЕМА", 100, 0)
    assert found["total"] == 8
    if flat:
        assert service.dataset["contract_source"] == "audited_fixed_whitelist"
        assert all(p["sensor_type"] == "КД Дверь" for p in predictions if p["direction"] == "sensor")


def test_compact_train_requires_sampling_weights(tmp_path):
    path = tmp_path / "train_compact.parquet"
    pd.DataFrame({"channel_id": ['1'], "prediction_time": [pd.Timestamp("2020-01-01")], "sensor_type_current": ['Контактный'], "y": [1], "events_1d": [3]}).to_parquet(path)
    with duckdb.connect() as con, pytest.raises(ValueError, match="sample_weight"):
        read_split(con, path, ["events_1d"], "контакт", "y")


@pytest.mark.parametrize("corruption", ["feature_max_ts", "target_start", "sample_weight"])
def test_flat_handoff_rejects_leakage_and_bad_weights(tmp_path, corruption):
    for split, year in [("train_compact", 2020), ("validation", 2021), ("test", 2022), ("scoring_latest", 2023)]:
        t = pd.Timestamp(f"{year}-02-01")
        frame = pd.DataFrame({"channel_id": [1, 2], "prediction_time": t, "sensor_type_current": "Датчик дыма",
                              "target_fault_24_48h": [0, 1], "sample_weight": 1.0, "sampling_probability": 1.0,
                              "feature_max_ts": t - pd.Timedelta(hours=1), "target_start": t + pd.Timedelta(hours=24),
                              "target_end": t + pd.Timedelta(hours=48), "at_risk_with_history": True,
                              "last_explicit_state": "норма", "channel_followup_48h": True, "global_complete_24_48h": True,
                              **{feature: 1.0 for feature in HANDOFF_FEATURES}})
        if split == "train_compact":
            frame.loc[0, corruption] = 20.0 if corruption == "sample_weight" else t
        frame.to_parquet(tmp_path / f"{split}.parquet")
    ml, spec, features = contract(tmp_path)
    with duckdb.connect() as con, pytest.raises(ValueError, match="future_features|wrong_target_window|sampling weights"):
        audit(con, ml, spec, features)
