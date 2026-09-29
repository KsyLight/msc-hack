"""Загрузка месячной LightGBM-модели через контракт predict_proba."""
import numpy as np
import lightgbm as lgb


class MonthlyModel:
    classes_ = np.array([0, 1])

    def __init__(self, model_text, features):
        self.model_text = model_text
        self.features = list(features)
        self._booster = None

    def __getstate__(self):
        return {"model_text": self.model_text, "features": self.features, "_booster": None}

    def predict_proba(self, frame):
        if list(frame.columns) != self.features:
            raise ValueError("Не совпадает порядок признаков месячной модели")
        if self._booster is None:
            self._booster = lgb.Booster(model_str=self.model_text)
        x = frame.replace([np.inf, -np.inf], np.nan).astype('float32')
        p = np.asarray(self._booster.predict(x, num_threads=4))
        return np.column_stack([1 - p, p])
