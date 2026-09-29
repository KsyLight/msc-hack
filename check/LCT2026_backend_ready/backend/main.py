from contextlib import asynccontextmanager
from datetime import datetime, timezone
import csv
import io
import json
import re
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from backend.config import Settings
from backend.schemas import (Direction, TicketCreate, TicketUpdate, PredictBatch, PredictionPage,
                             BatchResult, TicketRecord, TicketDetail, Collector)
from backend.service import RiskService
from backend.ml.contracts import SENSOR_PATTERN, INFRASTRUCTURE_PATTERN


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = RiskService(settings)
        yield

    app = FastAPI(title="Контур · Предиктивный мониторинг", version="0.1.0", lifespan=lifespan,
                  description="Два направления. Горизонт берётся из метаданных модели в /api/models. Балл модели относится к сигналу «Неисправен», не к подтверждённому физическому отказу.")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

    def service():
        return app.state.service

    @app.get("/api/health", tags=["System"])
    def health():
        return {"status": "ok", "mode": settings.mode, "models": list(service().models)}

    @app.get("/api/models", tags=["Models"])
    def models():
        return [m["metadata"] for m in service().models.values()]

    @app.get("/api/data-quality", tags=["System"])
    def quality():
        data = service().data
        return {**service().dataset, "snapshot_time": data.prediction_time.max().isoformat(),
                "scoring_rows": len(data), "eligible_rows": int(data.eligible.sum()),
                "unavailable_rows": int((~data.eligible).sum()),
                "limitations": ["Сообщение «Неисправен» не подтверждает физическую поломку или износ.",
                                "Ложные сработки не размечены; тревожные сообщения не считаются ложными автоматически.",
                                "Нет привязанной истории ремонтов, обследований и возраста оборудования.",
                                "Связь каналов с объектами взята из текущего справочника."]}

    @app.get("/api/predictions", tags=["Predictions"], response_model=PredictionPage)
    def predictions(direction: Direction | None = None, risk: str | None = Query(None, pattern="^(high|medium|low|unavailable)$"),
                    object_id: str | None = None, search: str = "", latest: bool = True,
                    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return service().prediction_page(latest, direction, risk, object_id, search, limit, offset)

    @app.get("/api/dashboard", tags=["Dashboard"])
    def dashboard():
        rows = service().predictions()
        with service().store.connect() as conn:
            tickets = conn.execute("SELECT count(*) FROM tickets WHERE status IN ('new','in_progress')").fetchone()[0]
        return {"mode": settings.mode, "as_of": service().data.prediction_time.max().isoformat(),
                "objects": len(service().objects), "channels": len(rows),
                "high_risk": sum(r["risk"] == "high" for r in rows),
                "unavailable": sum(r["risk"] == "unavailable" for r in rows), "open_tickets": tickets,
                "directions": {d: {"total": sum(r["direction"] == d for r in rows), "high": sum(r["direction"] == d and r["risk"] == "high" for r in rows)} for d in service().models},
                "trend": service().trend(),
                "observations": service().observation_history(),
                "top_predictions": rows[:6]}

    @app.get("/api/observations", tags=["Dashboard"])
    def observations(days: int = Query(366, ge=1, le=3660)):
        return {"kind": "observed_messages", "description": "Суточные сообщения журналов; повторные сообщения не являются отдельными поломками",
                "items": service().observation_history(days)}

    @app.get("/api/objects", tags=["Objects"], response_model=list[Collector])
    def objects():
        predictions = service().predictions()
        return [{**o, "channels": sum(p["object_id"] == o["id"] for p in predictions),
                 "high_risk": sum(p["object_id"] == o["id"] and p["risk"] == "high" for p in predictions),
                 "max_score": max((p["score"] for p in predictions if p["object_id"] == o["id"] and p["score"] is not None), default=None)} for o in service().objects]

    @app.post("/api/predictions/run", tags=["Predictions"])
    def run():
        return service().run()

    @app.post("/api/predict/{direction}", tags=["Models"], response_model=BatchResult)
    def predict(direction: Direction, payload: PredictBatch):
        expected = set(service().models[direction]["metadata"]["features"])
        rows = []
        for row in payload.rows:
            pattern = SENSOR_PATTERN if direction == "sensor" else INFRASTRUCTURE_PATTERN
            if not re.search(pattern, row.sensor_type.casefold()):
                raise HTTPException(422, "Тип канала не соответствует направлению модели")
            if set(row.features) != expected:
                raise HTTPException(422, {"message": "Feature contract mismatch", "required": sorted(expected)})
            if row.prediction_time.tzinfo is not None:
                raise HTTPException(422, "Notebook timestamps use source-local time without timezone; send the same convention")
            if service().models[direction]["metadata"]["target"] == "target_monthly" and row.prediction_time != row.prediction_time.replace(hour=0, minute=0, second=0, microsecond=0):
                raise HTTPException(422, "Месячная модель принимает срез на полночь времени источника")
            if row.eligible and row.last_explicit_state.casefold() != "норма":
                raise HTTPException(422, "Eligible forecasts require last_explicit_state=норма")
            rows.append({**row.model_dump(exclude={"features"}), **row.features})
        return {"items": service().score(direction, pd.DataFrame(rows)), "persisted": False}

    @app.get("/api/predictions/export.csv", tags=["Predictions"])
    def export():
        output = io.StringIO()
        fields = ["id", "direction", "entity_id", "object_name", "sensor_type", "system_type", "sensor_name", "system_tag", "prediction_time", "target_start", "target_end", "score", "risk", "model_version", "mode"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in service().predictions():
            # Escape formula prefixes for spreadsheet applications.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
        return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="predictions.csv"'})

    @app.get("/api/tickets", tags=["Maintenance"], response_model=list[TicketDetail])
    def tickets():
        with service().store.connect() as conn:
            rows = conn.execute("SELECT t.*,p.payload FROM tickets t JOIN predictions p ON p.id=t.prediction_id ORDER BY t.id DESC").fetchall()
        return [{**{k: r[k] for k in r.keys() if k != "payload"}, "prediction": json.loads(r["payload"])} for r in rows]

    @app.post("/api/tickets", tags=["Maintenance"], response_model=TicketRecord)
    def create_ticket(payload: TicketCreate):
        try:
            return service().create_ticket(payload.prediction_id, payload.comment)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/tickets/generate", tags=["Maintenance"])
    def generate():
        high = [p for p in service().predictions() if p["risk"] == "high"]
        return {"items": [service().create_ticket(p["id"], "Автоматическая заявка по прогнозу повышенного риска", True) for p in high]}

    @app.patch("/api/tickets/{ticket_id}", tags=["Maintenance"], response_model=TicketRecord)
    def update_ticket(ticket_id: int, payload: TicketUpdate):
        allowed = {"new": {"in_progress", "dismissed"}, "in_progress": {"done", "dismissed"}, "done": set(), "dismissed": set()}
        with service().store.connect() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Заявка не найдена")
            if payload.status != row["status"] and payload.status not in allowed[row["status"]]:
                raise HTTPException(409, "Недопустимый переход статуса")
            conn.execute("UPDATE tickets SET status=?,comment=?,updated_at=? WHERE id=?", (payload.status, payload.comment, datetime.now(timezone.utc).isoformat(), ticket_id))
            return dict(conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone())

    if settings.frontend.exists():
        app.mount("/", StaticFiles(directory=settings.frontend, html=True), name="dashboard")
    return app


app = create_app()
