import csv
import io
import pandas as pd
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app
import pytest


def test_startup_trains_two_models_with_explicit_provenance(client):
    assert client.get("/api/health").json() == {"status": "ok", "mode": "demo", "models": ["sensor", "infrastructure"]}
    models = client.get("/api/models").json()
    assert len(models) == 2
    assert all(m["provenance"] == "synthetic_demo" for m in models)
    assert all(m["horizon"]["min_hours"] == 24 for m in models)
    assert all(m["test"]["positives"] > 0 for m in models)


def test_filters_pagination_and_target_window(client):
    first = client.get("/api/predictions?direction=sensor&risk=high&limit=2").json()
    assert first["total"] > 2
    second = client.get("/api/predictions?direction=sensor&risk=high&limit=2&offset=2").json()
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    for row in first["items"]:
        assert row["direction"] == "sensor" and row["risk"] == "high"
        assert pd.Timestamp(row["target_start"]) - pd.Timestamp(row["prediction_time"]) == pd.Timedelta(hours=24)
        assert pd.Timestamp(row["target_end"]) - pd.Timestamp(row["prediction_time"]) == pd.Timedelta(hours=48)
    assert client.get("/api/predictions?limit=-1").status_code == 422
    found = client.get("/api/predictions", params={"search": "ПРЕСНЯ"}).json()
    assert found["total"] > 0
    assert all(r["object_name"] == "Пресня" for r in found["items"])


def test_ticket_idempotency_state_machine_and_persistence(client, app):
    prediction = client.get("/api/predictions?limit=1").json()["items"][0]
    payload = {"prediction_id": prediction["id"], "comment": "Проверить соединение"}
    ticket = client.post("/api/tickets", json=payload).json()
    again = client.post("/api/tickets", json=payload).json()
    assert ticket["id"] == again["id"]
    route = f"/api/tickets/{ticket['id']}"
    assert client.patch(route, json={"status": "done"}).status_code == 409
    assert client.patch(route, json={"status": "in_progress", "comment": "Назначена диагностика"}).status_code == 200
    assert client.patch(route, json={"status": "done"}).status_code == 200
    assert client.patch(route, json={"status": "new"}).status_code == 409
    with app.state.service.store.connect() as conn:
        assert conn.execute("SELECT status FROM tickets WHERE id=?", (ticket["id"],)).fetchone()[0] == "done"
    assert client.post("/api/tickets", json={"prediction_id": "missing"}).status_code == 404


def test_prediction_contract_and_unavailable_state(client, app):
    row = app.state.service.data.query("direction == 'sensor'").iloc[0]
    features = app.state.service.models["sensor"]["metadata"]["features"]
    item = {"entity_id": row.entity_id, "object_id": row.object_id, "sensor_type": row.sensor_type,
            "prediction_time": row.prediction_time.isoformat(), "eligible": True, "last_explicit_state": "норма",
            "features": {f: float(row[f]) for f in features}}
    result = client.post("/api/predict/sensor", json={"rows": [item]})
    assert result.status_code == 200
    assert 0 <= result.json()["items"][0]["score"] <= 1
    item["eligible"] = False
    assert client.post("/api/predict/sensor", json={"rows": [item]}).json()["items"][0]["score"] is None
    item["features"]["target_fault_24_48h"] = 1
    assert client.post("/api/predict/sensor", json={"rows": [item]}).status_code == 422


def test_refresh_is_idempotent_and_export_is_consistent(client):
    before = client.get("/api/predictions?latest=false").json()["total"]
    assert client.post("/api/predictions/run").status_code == 200
    assert client.get("/api/predictions?latest=false").json()["total"] == before
    response = client.get("/api/predictions/export.csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == client.get("/api/dashboard").json()["channels"]


def test_real_mode_never_falls_back_to_demo(tmp_path):
    with pytest.raises(RuntimeError, match="Real artifacts missing"):
        with TestClient(create_app(Settings(runtime=tmp_path, mode="real"))):
            pass


def test_generate_tickets_does_not_duplicate_open_requests(client):
    a = client.post("/api/tickets/generate").json()
    b = client.post("/api/tickets/generate").json()
    assert {r["id"] for r in a["items"]} == {r["id"] for r in b["items"]}
