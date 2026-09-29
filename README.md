# Контур: предиктивный мониторинг

Локальный сервис для раннего предупреждения о новых сообщениях «Неисправен» в инженерных коллекторах. Проект состоит из FastAPI backend, React/TypeScript frontend, моделей scikit-learn, SQLite-журнала и Docker-конфигурации.

Сервис работает по направлениям:

- `sensor` / `infrastructure` — общая месячная LightGBM-модель (окно `[t+24ч, t+31д)`), фильтр по типу оборудования;
- `smoke` — опциональная CatBoost-модель сигнала дыма (окно `[t+24ч, t+48ч)`), подключается при наличии `runtime/real/models/smoke.joblib`.

Балл модели не подтверждает физическую поломку, износ или пожар. Подробности: [docs/DATA_AND_MODELS.md](docs/DATA_AND_MODELS.md), [docs/MONTHLY_INTEGRATION.md](docs/MONTHLY_INTEGRATION.md).

## Структура проекта

```text
backend/                  FastAPI API и сервис прогнозирования
backend/ml/               контракты, обучение и demo-генератор
frontend/                 React/TypeScript приложение
data/                     входные Parquet-файлы для обучения
runtime/real/             реальные модели, срез для scoring и справочники
runtime/demo/             синтетический комплект для demo-режима
scripts/                  обучение, handoff и работа с notebook
tests/                    backend-тесты
docs/                     архитектура и описание данных
```

## Быстрый запуск в режиме real

### 1. Проверьте реальные артефакты

Перед запуском в корне проекта должен существовать каталог `runtime/real` со следующими файлами:

```text
runtime/real/
  dataset.json
  objects.json
  scoring.parquet
  observations.parquet       # нужен для истории наблюдений; может отсутствовать
  models/
    sensor.joblib / sensor.json
    infrastructure.joblib / infrastructure.json
    smoke.joblib / smoke.json / smoke_catboost_*.cbm   # опционально
```

| Направление | Рабочая модель | Цель / горизонт |
|---|---|---|
| Датчики | `runtime/real/models/sensor.joblib` | `target_monthly`, 24–744 ч |
| Насосы и вентиляторы | `runtime/real/models/infrastructure.joblib` | `target_monthly`, 24–744 ч |
| Сигнал дыма | `runtime/real/models/smoke.joblib` | `smoke_signal_24_48h`, 24–48 ч |

Файл `.joblib` содержит словарь `{"model": ..., "metadata": ...}`. Backend загружает `sensor` и `infrastructure` при старте; `smoke` — если артефакт есть. Для переупаковки CatBoost: `python -m scripts.export_smoke`. Если реальных артефактов нет, режим `real` завершается ошибкой и не подменяется demo-данными. Не запускайте `scripts.train` для установки месячного комплекта — он вернёт суточный baseline.

### 2. Запуск через Docker

Нужен Docker Desktop. Выполните из корня проекта:

```powershell
$env:APP_MODE = "real"
docker compose up --build -d
```

После запуска:

- dashboard: http://localhost:8000
- API: http://localhost:8000/docs
- health check: http://localhost:8000/api/health

Проверьте, что API действительно работает в real:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod http://localhost:8000/api/models
```

В ответе `/api/health` должно быть `"mode": "real"`, а `/api/models` должен вернуть две модели с непустыми версиями.

Полезные команды:

```powershell
docker compose ps
docker compose logs -f app
docker compose down
```

Compose монтирует локальный `runtime` в контейнер. SQLite-журнал прогнозов и заявок сохраняется между перезапусками.

Если нужен постоянный режим без установки переменной в каждой консоли, создайте локальный `.env` в корне проекта:

```dotenv
APP_MODE=real
APP_PORT=8000
```

`.env` не следует добавлять в Git.

### 3. Локальный запуск в Windows

Нужны Python 3.12 в conda-окружении `msc-hack` и Node.js 22+:

```powershell
conda activate msc-hack
python -m pip install -r requirements-dev.txt
.\start.cmd real
```

Если frontend ещё не собран, `start.cmd` установит npm-зависимости из `frontend/package-lock.json` и выполнит `npm run build`. API и собранный frontend будут доступны на http://127.0.0.1:8000.

Альтернативный запуск через PowerShell:

```powershell
.\start.ps1 -Mode real -Port 8000
```

Не запускайте Docker и локальный процесс одновременно на одном порту и с одним каталогом `runtime`.

## Demo-режим

Demo нужен только для проверки интерфейса без реальных артефактов:

```powershell
docker compose down
$env:APP_MODE = "demo"
docker compose up --build -d
```

Demo-данные создаются в `runtime/demo` и явно помечаются в интерфейсе как демонстрационные. Для рабочей проверки данных всегда используйте `real`.

## Что показывает frontend и откуда берутся данные

Frontend не содержит копию прогнозов. Он получает данные через относительные запросы `/api`:

| Экран | Endpoint | Источник backend |
|---|---|---|
| Обзор | `GET /api/dashboard` | scoring-срез, модели и SQLite |
| Объекты | `GET /api/objects` | `objects.json` и текущие прогнозы |
| Журнал прогнозов | `GET /api/predictions` | SQLite, заполненная при старте из scoring-среза |
| Качество данных | `GET /api/data-quality` | `dataset.json`, scoring-срез и observations |
| Заявки | `GET /api/tickets` | SQLite |
| Модели | `GET /api/models` | метаданные внутри `.joblib` |

При старте backend читает `runtime/<APP_MODE>`, загружает модели и пересчитывает текущий срез. Кнопка «Обновить прогнозы» повторяет scoring уже загруженными моделями; после замены файлов моделей требуется перезапуск сервиса.

## Обучение на реальных данных

Готовый real-комплект уже можно запускать. Повторное выполнение исходного EDA требуется только при подготовке нового handoff.

Для обучения на подготовленных файлах `data/`:

```powershell
conda activate msc-hack
python -m scripts.train --handoff data --runtime runtime/candidate
```

Нужны `train_compact.parquet` или `train.parquet`, `validation.parquet`, `test.parquet`, `scoring_latest.parquet`. Дополнительные файлы `channels_current.parquet`, `objects_current.parquet` и `daily_*.parquet` обогащают справочники и историю.

Результат появится в `runtime/candidate/real`. Перед публикацией замените рабочий комплект только после проверки моделей:

```powershell
python -m pytest
```

После публикации перезапустите Docker или `start.cmd real`. Версию модели можно проверить через `GET /api/models`.

Исходный notebook и подготовка handoff описаны в [docs/DATA_AND_MODELS.md](docs/DATA_AND_MODELS.md). Исходные журналы `ext-journal-*.csv` в репозиторий не добавляются.

## API

Основные endpoints:

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/objects`
- `GET /api/predictions`
- `GET /api/predictions/export.csv`
- `GET /api/models`
- `GET /api/data-quality`
- `GET /api/tickets`
- `POST /api/predictions/run`
- `POST /api/predict/sensor`
- `POST /api/predict/infrastructure`
- `POST /api/tickets`
- `POST /api/tickets/generate`
- `PATCH /api/tickets/{id}`

Полная схема доступна в Swagger по адресу `/docs` и в [docs/openapi.json](docs/openapi.json).

## Разработка и проверки

Backend:

```powershell
conda activate msc-hack
python -m pytest
```

Frontend:

```powershell
cd frontend
npm ci
npm run build
npm run dev
```

Vite dev server работает на порту 5173 и проксирует `/api` на backend на порту 8000. E2E-проверка запускается из каталога `frontend` при работающем API:

```powershell
npm run test:e2e
```

Архитектурные границы описаны в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Метрики текущих baseline-моделей и ограничения реальных данных находятся в [reports/REAL_DATA.md](reports/REAL_DATA.md).
