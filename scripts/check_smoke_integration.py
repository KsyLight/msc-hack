"""Проверка smoke CatBoost-модели через API в отдельной временной базе."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


def check() -> dict:
    root = Path(__file__).resolve().parents[1]
    smoke_joblib = root / "runtime/real/models/smoke.joblib"
    if not smoke_joblib.exists():
        raise FileNotFoundError("Сначала выполните: python -m scripts.export_smoke")

    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        shutil.copytree(
            root / "runtime/real",
            runtime / "real",
            ignore=shutil.ignore_patterns("*.sqlite3*"),
        )
        with TestClient(create_app(Settings(runtime=runtime, mode="real"))) as client:
            health = client.get("/api/health").json()
            assert health["mode"] == "real"
            assert "smoke" in health["models"]
            models = {m["direction"]: m for m in client.get("/api/models").json()}
            smoke = models["smoke"]
            assert smoke["target"] == "smoke_signal_24_48h"
            assert smoke["horizon"] == {"min_hours": 24, "max_hours": 48}

            service = client.app.state.service
            smoke_rows = service.data.loc[service.data.direction.eq("smoke")]
            assert not smoke_rows.empty
            predictions = [p for p in service.predictions() if p["direction"] == "smoke"]
            assert len(predictions) == len(smoke_rows)

            meta = service.models["smoke"]["metadata"]
            sample = smoke_rows.loc[smoke_rows.eligible].head(3)
            assert not sample.empty
            payload_rows = []
            for _, row in sample.iterrows():
                payload_rows.append(
                    {
                        "entity_id": str(row.entity_id),
                        "object_id": str(row.object_id),
                        "sensor_type": str(row.sensor_type),
                        "prediction_time": pd.Timestamp(row.prediction_time).isoformat(),
                        "eligible": True,
                        "last_explicit_state": str(row.last_explicit_state),
                        "features": {
                            f: None if pd.isna(row[f]) else float(row[f]) for f in meta["features"]
                        },
                    }
                )
            response = client.post("/api/predict/smoke", json={"rows": payload_rows})
            assert response.status_code == 200, response.text
            items = response.json()["items"]
            assert len(items) == len(payload_rows)
            assert all(item["score"] is None or 0 <= item["score"] <= 1 for item in items)

            # Direct model contract check
            matrix = sample[meta["features"]].replace([np.inf, -np.inf], np.nan)
            probs = np.asarray(service.models["smoke"]["model"].predict_proba(matrix))
            assert probs.shape == (len(sample), 2)
            assert np.isfinite(probs).all()
            assert np.allclose(probs.sum(axis=1), 1, atol=1e-5)

            result = {
                "api_passed": True,
                "smoke_rows": int(len(smoke_rows)),
                "smoke_eligible": int(smoke_rows.eligible.sum()),
                "version": smoke["version"],
                "threshold": smoke["threshold"],
                "batch_scores": [item["score"] for item in items],
            }
    (root / "reports").mkdir(exist_ok=True)
    out = root / "reports/smoke_integration_check.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
    return result


if __name__ == "__main__":
    check()
