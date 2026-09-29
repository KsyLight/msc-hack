"""Упаковка CatBoost smoke-модели в runtime-совместимый joblib-бандл."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import joblib

from backend.ml.contracts import HORIZONS, validate_features
from backend.ml.smoke_adapter import SmokeModel


def export(source: Path, destination: Path) -> Path:
    source = source.resolve()
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    meta_candidates = sorted(source.glob("smoke_catboost_*.json"))
    if not meta_candidates:
        raise FileNotFoundError(f"Не найден metadata JSON в {source}")
    meta_path = meta_candidates[-1]
    model_path = meta_path.with_suffix(".cbm")
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    handoff = json.loads(meta_path.read_text(encoding="utf-8"))
    features = list(handoff["features"])
    validate_features(features)
    threshold = float(handoff["threshold"])
    target = handoff["target"]
    if target not in HORIZONS:
        raise ValueError(f"Неподдерживаемый target: {target}")

    shutil.copy2(model_path, destination / model_path.name)
    relative_model = model_path.name
    model = SmokeModel(
        model_path=destination / relative_model,
        features=features,
        categorical_features=handoff.get("categorical_features", []),
    )
    # Store relative name so the bundle stays portable inside models/.
    model.model_path = relative_model

    metadata = {
        "direction": "smoke",
        "algorithm": "CatBoostClassifier",
        "version": handoff.get("model_version", model_path.stem),
        "provenance": "notebook_handoff",
        "features": features,
        "categorical_features": handoff.get("categorical_features", []),
        "target": target,
        "threshold": threshold,
        "horizon": HORIZONS[target],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_start": handoff.get("training_start"),
        "training_end": handoff.get("training_end"),
        "params": handoff.get("params", {}),
        "channel_history": bool(handoff.get("channel_history", False)),
        "test": {
            "average_precision": 0.01624,
            "precision": 0.0171,
            "recall": 0.1436,
            "f2": 0.05782,
            "threshold": threshold,
            "rows": 1415514,
            "positives": 6290,
            "source": "HANDOFF.md one-shot final test",
        },
        "meets_case_metrics": False,
        "model_file": relative_model,
        "limitations": [
            "Прогноз зарегистрированного сигнала дыма, не подтверждённый пожар.",
            "Без размеченной channel-history в scoring используются cold-start нули.",
            "Низкий precision на финальном тесте; нагрузка алертов — продуктовое решение.",
            "Обучение на полном потоке до 2026-01-01; test читался один раз.",
        ],
    }
    bundle_path = destination / "smoke.joblib"
    joblib.dump({"model": model, "metadata": metadata}, bundle_path)
    (destination / "smoke.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return bundle_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("ml/smoke/candidate_history_compact_20260929"),
        help="Каталог с .cbm и .json кандидата",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("runtime/real/models"),
        help="Куда положить smoke.joblib/.cbm/.json",
    )
    args = parser.parse_args()
    path = export(args.source, args.destination)
    print(json.dumps({"smoke_joblib": str(path)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
