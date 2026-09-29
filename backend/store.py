from contextlib import contextmanager
import sqlite3


class Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS predictions (
                    id TEXT PRIMARY KEY, direction TEXT NOT NULL, entity_id TEXT NOT NULL,
                    object_id TEXT NOT NULL, prediction_time TEXT NOT NULL,
                    model_version TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS predictions_time ON predictions(prediction_time);
                CREATE INDEX IF NOT EXISTS predictions_active ON predictions(direction,model_version,prediction_time);
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id TEXT NOT NULL REFERENCES predictions(id),
                    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','in_progress','done','dismissed')),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    automatic INTEGER NOT NULL DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS active_ticket ON tickets(prediction_id) WHERE status IN ('new','in_progress');
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
