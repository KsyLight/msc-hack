from datetime import datetime, timezone
import hashlib
import json
import threading
import time
import joblib
import numpy as np
import pandas as pd
from backend.ml.contracts import TARGETS, validate_features
from backend.ml.demo import bootstrap_demo
from backend.ml.training import matrix
from backend.store import Store


class RiskService:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()
        root = settings.runtime
        required = [root / "scoring.parquet", root / "objects.json", root / "dataset.json", *[root / "models" / f"{d}.joblib" for d in TARGETS]]
        if not all(p.exists() for p in required):
            if settings.mode != "demo":
                raise RuntimeError("Real artifacts missing. Run python -m scripts.train --handoff PATH first; demo is never substituted.")
            bootstrap_demo(root)
        self.models = {d: joblib.load(root / "models" / f"{d}.joblib") for d in TARGETS}
        for bundle in self.models.values():
            validate_features(bundle["metadata"]["features"])
            if settings.mode == "real" and bundle["metadata"]["provenance"] == "synthetic_demo":
                raise RuntimeError("Synthetic model cannot be served in real mode")
        self.data = pd.read_parquet(root / "scoring.parquet")
        self.data.prediction_time = pd.to_datetime(self.data.prediction_time)
        self.objects = json.loads((root / "objects.json").read_text(encoding="utf-8"))
        self.dataset = json.loads((root / "dataset.json").read_text(encoding="utf-8"))
        self.store = Store(settings.database)
        self.run()

    def factors(self, row):
        # Observed context, deliberately not called SHAP or causal explanation.
        labels = [("fault_messages_30d", "Сообщений «Неисправен» за 30 дней"),
                  ("undefined_messages_7d", "Неопределённых состояний за 7 дней"),
                  ("alarms_7d", "Тревожных сообщений за 7 дней"),
                  ("event_ratio_1d_7d", "Активность относительно средней за неделю")]
        return [{"feature": key, "label": label, "value": round(float(row[key]), 2)} for key, label in labels if key in row and pd.notna(row[key])]

    def score(self, direction, frame):
        bundle = self.models[direction]
        meta = bundle["metadata"]
        eligible = frame.eligible.fillna(False).astype(bool)
        scores = np.full(len(frame), np.nan)
        if eligible.any():
            scores[eligible.to_numpy()] = bundle["model"].predict_proba(matrix(frame.loc[eligible], meta["features"]))[:, 1]
        names = {o["id"]: o["name"] for o in self.objects}
        results = []
        for (_, row), score in zip(frame.iterrows(), scores):
            t = pd.Timestamp(row.prediction_time)
            key = f"{direction}|{row.entity_id}|{t.isoformat()}|{meta['version']}"
            risk = "unavailable" if np.isnan(score) else "high" if score >= meta["threshold"] else "medium" if score >= meta["threshold"] * .5 else "low"
            results.append({"id": hashlib.sha256(key.encode()).hexdigest()[:24], "direction": direction,
                            "entity_id": str(row.entity_id), "object_id": str(row.object_id),
                            "object_name": names.get(str(row.object_id), str(row.object_id)), "sensor_type": str(row.sensor_type),
                            "prediction_time": t.isoformat(), "target_start": (t + pd.Timedelta(hours=24)).isoformat(),
                            "target_end": (t + pd.Timedelta(hours=48)).isoformat(),
                            "score": None if np.isnan(score) else round(float(score), 6), "risk": risk,
                            "threshold": meta["threshold"], "model_version": meta["version"],
                            "state": str(row.get("last_explicit_state", "unknown")), "factors": self.factors(row),
                            "recommendation": "Проверить журнал и запланировать диагностику" if risk == "high" else "Продолжить наблюдение" if risk != "unavailable" else "Проверить состояние и полноту данных",
                            "mode": self.settings.mode})
        return results

    def run(self):
        with self.lock:
            started = time.perf_counter()
            rows = []
            for direction in TARGETS:
                rows.extend(self.score(direction, self.data.loc[self.data.direction.eq(direction)]))
            with self.store.connect() as conn:
                conn.executemany("INSERT OR IGNORE INTO predictions VALUES (?,?,?,?,?,?,?)", [
                    (r["id"], r["direction"], r["entity_id"], r["object_id"], r["prediction_time"], r["model_version"], json.dumps(r, ensure_ascii=False)) for r in rows])
            return {"scored": len(rows), "duration_seconds": round(time.perf_counter() - started, 3), "as_of": self.data.prediction_time.max().isoformat()}

    def predictions(self, latest=True):
        # Active model versions only; previous predictions remain in the journal/database.
        where, params = self._prediction_filter(latest)
        with self.store.connect() as conn:
            data = [json.loads(r["payload"]) for r in conn.execute(f"SELECT payload FROM predictions WHERE {where}", params)]
        return sorted(data, key=lambda r: r["score"] if r["score"] is not None else -1, reverse=True)

    def _prediction_filter(self, latest):
        where = "(" + " OR ".join("(direction=? AND model_version=?)" for _ in self.models) + ")"
        params = [value for direction, model in self.models.items() for value in (direction, model["metadata"]["version"])]
        if latest:
            where += " AND prediction_time=?"
            params.append(self.data.prediction_time.max().isoformat())
        return where, params

    def prediction_page(self, latest, direction, risk, object_id, search, limit, offset):
        where, params = self._prediction_filter(latest)
        for column, value in [("direction", direction), ("object_id", object_id), ("json_extract(payload,'$.risk')", risk)]:
            if value:
                where += f" AND {column}=?"
                params.append(value)
        if search:
            where += " AND instr(casefold(json_extract(payload,'$.object_name') || ' ' || entity_id || ' ' || json_extract(payload,'$.sensor_type')),?) > 0"
            params.append(search.casefold())
        with self.store.connect() as conn:
            conn.create_function("casefold", 1, lambda s: s.casefold() if s else "")
            total = conn.execute(f"SELECT count(*) FROM predictions WHERE {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT payload FROM predictions WHERE {where} ORDER BY json_extract(payload,'$.score') DESC, prediction_time DESC, id LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"total": total, "items": [json.loads(r["payload"]) for r in rows]}

    def trend(self):
        where, params = self._prediction_filter(False)
        where += " AND prediction_time>=?"
        params.append((self.data.prediction_time.max() - pd.Timedelta(days=29)).isoformat())
        with self.store.connect() as conn:
            rows = conn.execute(f"""SELECT substr(prediction_time,1,10) AS date,count(*) AS total,
                sum(direction='sensor' AND json_extract(payload,'$.risk')='high') AS sensor,
                sum(direction='infrastructure' AND json_extract(payload,'$.risk')='high') AS infrastructure
                FROM predictions WHERE {where} GROUP BY date ORDER BY date""", params).fetchall()
        return [dict(row) for row in rows]

    def create_ticket(self, prediction_id, comment="", automatic=False):
        now = datetime.now(timezone.utc).isoformat()
        with self.store.connect() as conn:
            prediction = conn.execute("SELECT payload FROM predictions WHERE id=?", (prediction_id,)).fetchone()
            if not prediction:
                raise KeyError("Прогноз не найден")
            if json.loads(prediction["payload"])["score"] is None:
                raise ValueError("Нет прогноза: сначала проверьте качество данных")
            conn.execute("INSERT OR IGNORE INTO tickets (prediction_id,created_at,updated_at,comment,automatic) VALUES (?,?,?,?,?)", (prediction_id, now, now, comment, int(automatic)))
            return dict(conn.execute("SELECT * FROM tickets WHERE prediction_id=? AND status IN ('new','in_progress')", (prediction_id,)).fetchone())
