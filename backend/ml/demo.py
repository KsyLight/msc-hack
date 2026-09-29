"""Explicitly synthetic fixtures, never mixed with notebook data."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from backend.ml.contracts import SENSOR_FEATURES, TARGETS
from backend.ml.training import train_model


def make_demo(seed=42):
    rng = np.random.default_rng(seed)
    objects = [{"id": f"DEMO-{i+1:02}", "name": name, "district": district, "coordinate_source": "synthetic", "latitude": lat, "longitude": lon}
               for i, (name, district, lat, lon) in enumerate([
                   ("Пресня", "Центральный", 55.762, 37.554), ("Таганский", "Центральный", 55.738, 37.668),
                   ("Сокольники", "Восточный", 55.795, 37.681), ("Лефортово", "Юго-Восточный", 55.767, 37.707),
                   ("Замоскворечье", "Центральный", 55.726, 37.625), ("Хамовники", "Центральный", 55.728, 37.574),
                   ("Аэропорт", "Северный", 55.8, 37.533), ("Марьина Роща", "Северо-Восточный", 55.8, 37.615),
                   ("Даниловский", "Южный", 55.703, 37.642), ("Дорогомилово", "Западный", 55.744, 37.54),
                   ("Басманный", "Центральный", 55.771, 37.659), ("Раменки", "Западный", 55.699, 37.5)])]
    rows = []
    for direction in TARGETS:
        types = ["Контактный", "Объёмный", "Температурный", "Дымовой", "Газовый"] if direction == "sensor" else ["Состояние насоса", "Состояние вентилятора"]
        for i in range(72 if direction == "sensor" else 36):
            base = rng.uniform(.2, 2)
            for day, t in enumerate(pd.date_range("2026-01-01", periods=180)):
                latent = base + 1.8 * np.sin(day / 13 + i) + rng.normal(0, .45)
                fault = rng.poisson(max(.1, latent * 2))
                alarms = rng.poisson(max(.2, latent * 3 + 2))
                events7 = alarms + rng.poisson(45)
                events1 = rng.poisson(max(1, latent * 2 + 7))
                row = {"entity_id": f"{'S' if direction == 'sensor' else 'E'}-{i+1:04}", "object_id": objects[i % len(objects)]["id"],
                       "sensor_type": types[i % len(types)], "prediction_time": t, "direction": direction,
                       "events_1d": events1, "events_7d": events7, "events_30d": events7 * 4 + rng.poisson(15),
                       "alarms_7d": alarms, "fault_messages_30d": fault, "undefined_messages_7d": rng.poisson(max(.1, latent)),
                       "disabled_messages_7d": rng.poisson(.4), "hours_since_last_event": rng.exponential(4),
                       "alarm_rate_7d": alarms / events7, "event_ratio_1d_7d": events1 / (events7 / 7),
                       "active_days_30d": int(rng.integers(25, 31)), "history_complete_days": 30,
                       "eligible": True, "last_explicit_state": "норма", "sample_weight": 1.0}
                # Synthetic future outcome with noise, not a deterministic copy of a feature.
                logit = -5 + .5 * fault + .18 * alarms + .35 * row["undefined_messages_7d"]
                row[TARGETS[direction]] = int(rng.random() < 1 / (1 + np.exp(-logit)))
                rows.append(row)
    return pd.DataFrame(rows), objects


def bootstrap_demo(runtime: Path):
    runtime.mkdir(parents=True, exist_ok=True)
    panel, objects = make_demo()
    for direction, target in TARGETS.items():
        frame = panel.loc[panel.direction.eq(direction)]
        splits = {"train": frame.loc[frame.prediction_time.lt("2026-04-19")],
                  "validation": frame.loc[frame.prediction_time.ge("2026-04-21") & frame.prediction_time.lt("2026-05-19")],
                  "test": frame.loc[frame.prediction_time.ge("2026-05-21")]}
        train_model(splits, SENSOR_FEATURES, target, direction, runtime / "models", "synthetic_demo")
    panel.loc[panel.prediction_time.ge(panel.prediction_time.max() - pd.Timedelta(days=29))].drop(columns=[TARGETS["sensor"], "sample_weight"]).to_parquet(runtime / "scoring.parquet", index=False)
    (runtime / "objects.json").write_text(json.dumps(objects, ensure_ascii=False), encoding="utf-8")
    (runtime / "dataset.json").write_text(json.dumps({"mode": "demo", "provenance": "synthetic_demo", "rows": len(panel), "notice": "Синтетические данные. Все объекты, координаты и показатели демонстрационные."}, ensure_ascii=False), encoding="utf-8")
