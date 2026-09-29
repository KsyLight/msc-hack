# Контур · ЛЦТ 2026, кейс 08

> Месячная ML-поставка: в `runtime/real` подключена общая LightGBM-модель через два направления API. Цель: запись «Неисправен» в окне [t+24 часа, t+31 день). Это другой горизонт, чем у исходного baseline ниже. Пошаговый запуск, метрики и ограничения: [docs/MONTHLY_INTEGRATION.md](docs/MONTHLY_INTEGRATION.md). Повторный `scripts.train` вернёт исходные суточные baseline-модели; для этого комплекта переобучение не требуется.

Локальный веб-сервис прогнозирования сигналов неисправности инженерных коллекторов: **FastAPI + React/TypeScript + scikit-learn + SQLite + Docker**.

Два направления: датчики и инфраструктура (насосы/вентиляторы). Второе выбрано по доступной разметке ноутбука. Цель обоих — новое сообщение «Неисправен» через **24–48 часов**, а не подтверждённая физическая поломка или износ. [Подробнее о данных и моделях](docs/DATA_AND_MODELS.md).

**Данные из `data/` подключены:** обучены две реальные baseline-модели, срез на 01.07.2026 содержит 6 145 каналов, график строится по журналам января–июня. Локальный `.env` настроен на `APP_MODE=real`. Метрики пока ниже требований кейса; результаты и назначение каждого файла — в [отчёте интеграции](reports/REAL_DATA.md).

## Быстрый запуск через Docker

Из корня проекта, при запущенном Docker Desktop:

```powershell
docker compose up --build -d
```

* Дашборд: **http://localhost:8000**
* Swagger / REST API: **http://localhost:8000/docs**
* Состояние: **http://localhost:8000/api/health**

Первый запуск на новом компьютере загружает зависимости. В режиме `real` предварительно обучите модели командой ниже; текущий компьютер уже содержит артефакты в `runtime/real`. После первой сборки дашборд и API работают без сети; интерактивный Swagger использует CDN, а его схема доступна локально в `docs/openapi.json`. Порт можно изменить в `.env` (`APP_PORT=8001`).

```powershell
docker compose logs -f app
docker compose ps
docker compose down
```

`runtime/` хранит модели, срезы данных, прогнозы и заявки и сохраняется после `down`.

Если загрузки Python-пакетов внутри Docker прерываются, подготовьте их через окружение хоста: `conda run -n msc-hack python -m scripts.download_docker_wheels`, затем повторите `docker compose up --build -d`. Сборка автоматически использует `docker/wheels/` без скачивания из контейнера. Этот дополнительный вариант рассчитан на Linux x86_64 внутри Docker Desktop; wheel-файлы не попадают в Git или финальный образ.

На чистом клоне без `.env` Docker запускает явно обозначенный DEMO. Для переданных реальных данных выполните обучение и установите `APP_MODE=real` в `.env`. Данные, модели и `.env` не входят в Git. Отсутствующие реальные артефакты не подменяются демоданными при `APP_MODE=real`.

## Локально в окружении msc-hack

Если окружение ещё не содержит Python:

```powershell
conda install -n msc-hack python=3.12 pip -y
conda activate msc-hack
python -m pip install -r requirements-dev.txt
```

Запуск (Node.js 22+ нужен для сборки фронтенда):

```powershell
.\start.cmd
```

`start.cmd` работает при стандартном запрете PowerShell-скриптов и выбирает реальные артефакты, если они подготовлены. Режим можно задать явно: `start.cmd real` или `start.cmd demo`. Альтернатива — `start.ps1` (параметры `-Mode` и `-Port`) либо команды вручную:

```powershell
conda activate msc-hack
cd frontend
npm ci
npm run build
cd ..
$env:OMP_NUM_THREADS = '4'
$env:APP_MODE = 'real'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS: `conda env create -f environment.yml`, затем `sh start.sh`. Не запускайте Docker и локальный процесс одновременно на одном порту и одном `runtime`.

## Выполнение исходного ноутбука

Положите в одну папку 8 годовых CSV и 3 справочника:

```text
D:/lct-data/
  ext-journal-2019.csv ... ext-journal-2026.csv
  справочник_каналов_датчиков.csv
  справочник_объектов_диспетчер.csv
  справочник_состояний.csv
  processed/                       # необязательно, готовые Parquet
```

```powershell
conda activate msc-hack
python -m scripts.run_notebook --data-dir D:/lct-data --output-dir data_handoff
```

Исходный ноутбук сохраняется без изменений. Результат исполнения — `reports/LCT2026_final_EDA.executed.ipynb`, статус и список недостающих файлов — `reports/notebook_execution.json`. Ячейка `!pip install` в исполняемой копии заменена комментарием: зависимости устанавливаются явно в выбранное окружение. Полный расчёт может потребовать десятки GB диска и продолжительное время.

Извлечение встроенных планов без внешних журналов:

```powershell
python -m scripts.inspect_notebook
```

Сохраняет исходные таблицы планов в `runtime/notebook_sources`, отчёт — `reports/notebook_inventory.json`. Планы без подтверждённой связи с объектами не используются как история ремонтов.

## Обучение на реальных данных ноутбука

Для полученной плоской папки `data/` повторное выполнение EDA не требуется:

```powershell
conda activate msc-hack
python -m scripts.train --handoff data
.\start.cmd real
```

Для Docker после обучения измените `.env`: `APP_MODE=real`, затем `docker compose up -d --force-recreate`.

Нужны `train_compact.parquet` (либо `train.parquet`), `validation.parquet`, `test.parquet`, `scoring_latest.parquet`. `channels_current.parquet` добавляет систему, название датчика и тег; `objects_current.parquet` — названия объектов; `daily_*.parquet` — реальные суточные графики. Пропуски оставляются разрывами. `*_excluded_followup.parquet` не используются для обучения.

Поддерживается и прежняя структура `data_handoff/feature_list.json` + `ml_ready/`. Для плоской поставки без `feature_list.json` применяется фиксированный список 27 прошлых признаков и проверяется временной контракт исходных файлов. Аудит и SHA-256 сохраняются в `runtime/real/handoff_audit.json`. Текущая привязка каналов не выдаётся за историческую. Без координат показывается реестр объектов.

CLI сравнивает LogisticRegression и HistGradientBoosting отдельно для двух направлений; сохраняет победителя, метрики и контракт признаков. Выбор делается по validation; тест и порог не смешиваются. При недостатке классов или несовместимой схеме обучение прекращается с ошибкой. Перезапустите сервис после публикации новых артефактов.

## Возможности

* Сводка, направления риска, реестр объектов, график наблюдавшихся сообщений (30/90 дней или весь период). Схема появляется только при наличии координат.
* Журнал: поиск, фильтры, пагинация, исторические прогнозы, CSV текущего среза.
* Карточка: целевой интервал, известное состояние, наблюдения и заявка на диагностику.
* Ручные и автоматические заявки; статусы «Новая → В работе → Завершена» / «Отклонена».
* Состояние данных: дата обновления, доступность прогнозов, история событий и каналы по типам оборудования.
* Пакетное применение моделей: `POST /api/predict/sensor`, `POST /api/predict/infrastructure`; строгий контракт признаков из `GET /api/models`.

## Замена модели — инструкция для ML-команды

Метрики, признаки и подробности обучения доступны в `GET /api/models`, JSON артефактов и отчётах. В рабочем интерфейсе показываются прогнозы, события и заявки.

### Что передавать в сервис

| Направление | Артефакт | Метаданные |
|---|---|---|
| Датчики | `runtime/real/models/sensor.joblib` | `sensor.json` рядом |
| Насосы и вентиляторы | `runtime/real/models/infrastructure.joblib` | `infrastructure.json` рядом |

Можно заменить одно направление: второй артефакт должен оставаться на месте. API требует обе модели. Сервис читает **словарь** `{"model": fitted_pipeline, "metadata": metadata}` внутри `.joblib`; отдельный `.json` нужен для просмотра и проверки. Изменение только JSON не переключает модель или её порог.

Контракт модели:

* `predict_proba(X)` принимает числовой `pandas.DataFrame` со столбцами **в порядке `metadata["features"]`** и возвращает массив `(n, 2)`; `classes_` должны быть `[0, 1]`. API использует второй столбец как балл 0–1. Метод `predict()` без `predict_proba()` не подходит.
* Импутация, масштабирование и другие преобразования сохраняются внутри обученного sklearn Pipeline. На входе могут быть NaN; бесконечные значения заменяются на NaN. Строковые категории текущий адаптер не принимает.
* Цель существующих направлений — `target_fault_24_48h`, окно `[t+24h,t+48h)`. Изменение цели, горизонта или добавление третьего направления требует согласованного изменения backend, а не только нового файла весов.
* `threshold` выбирается на validation. Высокий риск: `score >= threshold`; внимание: `score >= threshold / 2`. Test служит для итоговой оценки. Строки `eligible=false` не передаются модели и получают «Без оценки».
* `features` должны присутствовать в `runtime/real/scoring.parquet`. Запрещены метки, ID, `last_seen`, будущая наблюдаемость и другие поля из `validate_features` в [contracts.py](backend/ml/contracts.py). Веса `sample_weight` из compact учитываются при обучении, но не входят в X.
* `version` обязательно меняется при замене весов, преобразований, признаков или порога. Она входит в ключ прогноза: повторное использование старой версии может оставить старые результаты в журнале.

Версии Python и пакетов для обучения и запуска должны совпадать с [environment.yml](environment.yml) и [requirements.txt](requirements.txt). Пользовательские трансформеры определяйте в импортируемом модуле, например `backend/ml/team_pipeline.py`, а не только в ячейке notebook или `__main__`. Если добавляется библиотека, зафиксируйте её в `requirements.txt` и пересоберите Docker. При использовании офлайн wheels обновите и их через `python -m scripts.download_docker_wheels`.

### Вариант 1: обучить через существующий pipeline

Добавьте estimator в `candidates` функции `train_model` в [backend/ml/training.py](backend/ml/training.py). При необходимости настройте передачу `sample_weight`: обычный estimator принимает этот аргумент напрямую, sklearn Pipeline — через `<имя_шага>__sample_weight`. Затем из корня проекта:

```powershell
conda activate msc-hack
$env:OMP_NUM_THREADS = '4'
$env:OPENBLAS_NUM_THREADS = '4'
python -m scripts.train --handoff data --runtime runtime/candidate
```

Результат появится в **`runtime/candidate/real/`**, отдельно от рабочего сервиса. Команда проверяет данные, обучает оба направления, выбирает лучшего кандидата по validation и сохраняет модели, метрики, `scoring.parquet` и справочники. Новый алгоритм попадёт в сервис только если победит по validation; это видно в `models/*.json`.

При новых признаках обновите `HANDOFF_FEATURES` в `contracts.py` для плоской поставки или рекомендованный список и выбор признаков в `scripts/handoff.py` для структуры с `feature_list.json`. Новые столбцы должны присутствовать во всех train/validation/test/scoring файлах. Повторно выполните команду выше: одного редактирования `features` в метаданных недостаточно.

### Вариант 2: модель уже обучена командой

Сначала скопируйте рабочий комплект в каталог кандидата, чтобы сохранить второе направление и совместимый срез:

```powershell
New-Item -ItemType Directory -Force runtime/candidate | Out-Null
Copy-Item -LiteralPath runtime/real -Destination runtime/candidate -Recurse -Force
```

В конце вашего обучающего notebook сохраните модель по примеру ниже. Здесь `fitted_pipeline`, `features`, `threshold`, `test_metrics`, `validation_candidates`, `split_ranges` и `training_seconds` — **ваши фактические результаты обучения**. Формат метрик и диапазонов можно посмотреть в текущем `runtime/real/models/sensor.json`. Не копируйте метрики baseline для новой модели.

```python
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import joblib
from backend.ml.contracts import validate_features

direction = "sensor"  # либо "infrastructure"
validate_features(features)
metadata = {
    "direction": direction,
    "algorithm": type(fitted_pipeline).__name__,
    "version": f"{direction}-{uuid4().hex[:12]}",
    "provenance": "notebook_handoff",
    "features": list(features),
    "target": "target_fault_24_48h",
    "threshold": float(threshold),
    "horizon": {"min_hours": 24, "max_hours": 48},
    "trained_at": datetime.now(timezone.utc).isoformat(),
    "validation_candidates": validation_candidates,
    "test": test_metrics,
    "meets_case_metrics": (
        test_metrics["precision"] > 0.7 and test_metrics["recall"] > 0.5
    ),
    "split_ranges": split_ranges,
    "training_seconds": float(training_seconds),
    "limitations": [],  # заполните известные ограничения вашей модели
}
destination = Path("runtime/candidate/real/models")  # cwd — корень проекта
destination.mkdir(parents=True, exist_ok=True)
joblib.dump(
    {"model": fitted_pipeline, "metadata": metadata},
    destination / f"{direction}.joblib",
)
(destination / f"{direction}.json").write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
)
```

Если новые признаки отсутствуют в скопированном `scoring.parquet`, подготовьте новый срез с ними либо используйте первый вариант. Служебные поля `direction`, `entity_id`, `object_id`, `sensor_type`, `prediction_time`, `eligible`, `last_explicit_state` и метаданные каналов сохраняются. Не заменяйте подготовленный срез файлом `scoring_latest.parquet` напрямую: у них разные имена служебных столбцов.

### Проверка перед переключением

Следующий код запустите из корня проекта в `msc-hack` (например, отдельной ячейкой notebook). Он проверяет обе модели на всём доступном срезе и поднимает изолированный FastAPI TestClient. Рабочая SQLite не меняется.

```python
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app
from backend.ml.contracts import validate_features
from backend.ml.training import matrix

root = Path("runtime/candidate/real")
frame = pd.read_parquet(root / "scoring.parquet")
for direction in ("sensor", "infrastructure"):
    bundle = joblib.load(root / "models" / f"{direction}.joblib")
    model, metadata = bundle["model"], bundle["metadata"]
    validate_features(metadata["features"])
    assert metadata["direction"] == direction
    assert metadata["target"] == "target_fault_24_48h"
    assert metadata["horizon"] == {"min_hours": 24, "max_hours": 48}
    assert metadata["provenance"] != "synthetic_demo"
    assert metadata["version"] and 0 < metadata["threshold"] <= 1
    assert list(model.classes_) == [0, 1]
    rows = frame.loc[frame.direction.eq(direction) & frame.eligible]
    assert not rows.empty
    probabilities = np.asarray(model.predict_proba(matrix(rows, metadata["features"])))
    assert probabilities.shape == (len(rows), 2)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    assert np.allclose(probabilities.sum(axis=1), 1)

with TestClient(create_app(Settings(runtime=Path("runtime/candidate"), mode="real"))) as client:
    assert client.get("/api/health").json()["mode"] == "real"
    predictions = client.get("/api/predictions?limit=1")
    assert predictions.status_code == 200 and predictions.json()["total"] > 0
    print(client.get("/api/models").json())
```

Сравните метрики с предыдущей версией и сохраните отчёт. Наличие корректного `predict_proba` подтверждает совместимость, но не качество новой модели.

### Переключение и откат

Команды ниже выполняются из корня проекта после проверки кандидата. Они сохраняют рабочие заявки и копируют только подготовленные артефакты; SQLite кандидата переносить не нужно.

```powershell
docker compose stop app
$modelBackup = Join-Path 'runtime/backups' (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Force $modelBackup | Out-Null
$modelArtifacts = @('models', 'scoring.parquet', 'objects.json', 'dataset.json', 'observations.parquet', 'handoff_audit.json')
foreach ($artifact in $modelArtifacts) {
    $activeArtifact = Join-Path 'runtime/real' $artifact
    if (Test-Path -LiteralPath $activeArtifact) {
        Copy-Item -LiteralPath $activeArtifact -Destination $modelBackup -Recurse -Force
    }
}
foreach ($artifact in $modelArtifacts) {
    $candidateArtifact = Join-Path 'runtime/candidate/real' $artifact
    if (Test-Path -LiteralPath $candidateArtifact) {
        Copy-Item -LiteralPath $candidateArtifact -Destination 'runtime/real' -Recurse -Force
    }
}
# В .env должно быть APP_MODE=real
docker compose up -d
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod http://localhost:8000/api/models | Select-Object direction, algorithm, version
```

Если изменились Python-код или зависимости, используйте `docker compose up --build -d`. Дождитесь состояния `healthy` (`docker compose ps`); первые HTTP-запросы во время старта могут потребовать повторения. Без Docker остановите локальный процесс, выполните те же операции с файлами и запустите `start.cmd real`.

Для отката остановите сервис, восстановите артефакты из сохранённого `$modelBackup` в `runtime/real` и снова запустите. Если менялись код или зависимости, верните также их совместимые версии. **`runtime/real/operations.sqlite3` не заменяется и не удаляется**: это рабочий журнал прогнозов и заявок.

Модели загружаются при старте. Кнопка «Обновить прогнозы» и `POST /api/predictions/run` используют уже загруженную модель; для замены обязателен перезапуск. После запуска сверяйте `version` через `/api/models`: новые прогнозы получат новую версию, а предыдущие заявки останутся в журнале.

## Разработка и проверки

```powershell
conda activate msc-hack
python -m pytest
cd frontend
npm run build
npm run dev
```

Браузерная проверка на Windows с установленным Edge: при работающем API выполните из `frontend` команду `npm run test:e2e`. Тест создаёт и завершает явно помеченную заявку `E2E` в текущем режиме. Снимки desktop/mobile сохраняются в `reports/`.

Для frontend dev сервер API запускается отдельно на 8000; Vite на 5173 проксирует `/api`. Стили и компоненты отделены от API. [Архитектура и инструкция для фронтендера/ML-команды](docs/ARCHITECTURE.md).

Основные API: `GET /api/dashboard`, `/api/observations?days=90`, `/api/objects`, `/api/predictions`, `/api/models`, `/api/data-quality`, `/api/tickets`; `POST /api/predictions/run`, `/api/tickets`, `/api/tickets/generate`; `PATCH /api/tickets/{id}`. OpenAPI: `/openapi.json`.

Рекомендации по используемым механизмам: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [FastAPI в Docker](https://fastapi.tiangolo.com/deployment/docker/), [HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html).
