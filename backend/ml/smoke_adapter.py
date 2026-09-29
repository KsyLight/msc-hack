"""CatBoost smoke-signal model behind the shared predict_proba contract."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier


class SmokeModel:
    classes_ = np.array([0, 1])

    def __init__(self, model_path: str | Path, features: list[str], categorical_features: list[str] | None = None):
        self.model_path = str(model_path)
        self.features = list(features)
        self.categorical_features = list(categorical_features or [])
        self._model: CatBoostClassifier | None = None

    def __getstate__(self):
        return {
            "model_path": self.model_path,
            "features": self.features,
            "categorical_features": self.categorical_features,
            "_model": None,
        }

    def _booster(self) -> CatBoostClassifier:
        if self._model is None:
            model = CatBoostClassifier()
            model.load_model(self.model_path)
            self._model = model
        return self._model

    def predict_proba(self, frame):
        if list(frame.columns) != self.features:
            raise ValueError("Не совпадает порядок признаков smoke-модели")
        data = frame.copy()
        categorical = set(self.categorical_features)
        numeric = [name for name in self.features if name not in categorical]
        if numeric:
            data[numeric] = data[numeric].replace([np.inf, -np.inf], np.nan).astype("float32")
        for name in self.categorical_features:
            data[name] = data[name].fillna("__MISSING__").astype(str)
        return np.asarray(self._booster().predict_proba(data[self.features]))
