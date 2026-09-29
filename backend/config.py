from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    runtime: Path = Path(os.getenv("APP_RUNTIME_DIR", str(ROOT / "runtime")))
    mode: str = os.getenv("APP_MODE", "demo")
    frontend: Path = ROOT / "frontend" / "dist"

    def __post_init__(self):
        if self.mode not in {"demo", "real"}:
            raise ValueError("APP_MODE must be demo or real")
        self.runtime = self.runtime / self.mode
        self.runtime.mkdir(parents=True, exist_ok=True)

    @property
    def database(self):
        return self.runtime / "operations.sqlite3"
