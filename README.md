# Контур · ЛЦТ 2026, кейс 08

Локальный веб-сервис прогнозирования сигналов неисправности инженерных коллекторов: **FastAPI + React/TypeScript + scikit-learn + SQLite + Docker**.

Два направления: датчики и инфраструктура (насосы/вентиляторы). Второе выбрано по доступной разметке ноутбука. Цель обоих — новое сообщение «Неисправен» через **24–48 часов**, а не подтверждённая физическая поломка или износ. [Подробнее о данных и моделях](docs/DATA_AND_MODELS.md).

## Быстрый запуск через Docker

Из корня проекта, при запущенном Docker Desktop:

```powershell
docker compose up --build -d
```

* Дашборд: **http://localhost:8000**
* Swagger / REST API: **http://localhost:8000/docs**
* Состояние: **http://localhost:8000/api/health**

Первый запуск загружает зависимости и обучает две небольшие демонстрационные модели. Последующие используют сохранённые артефакты. После первой сборки дашборд и API работают без сети; интерактивный Swagger использует CDN, а его схема доступна локально в `docs/openapi.json`. Порт можно изменить в `.env` (`APP_PORT=8001`). Скопировать образец: `Copy-Item .env.example .env`.

```powershell
docker compose logs -f app
docker compose ps
docker compose down
```

`runtime/` хранит модели, срезы данных, прогнозы и заявки и сохраняется после `down`.

Если загрузки Python-пакетов внутри Docker прерываются, подготовьте их через окружение хоста: `conda run -n msc-hack python -m scripts.download_docker_wheels`, затем повторите `docker compose up --build -d`. Сборка автоматически использует `docker/wheels/` без скачивания из контейнера. Этот дополнительный вариант рассчитан на Linux x86_64 внутри Docker Desktop; wheel-файлы не попадают в Git или финальный образ.

**По умолчанию включён явно обозначенный DEMO:** синтетические каналы, координаты и метрики. Ноутбук требует внешние журналы и справочники, не включённые в репозиторий. Отсутствующие реальные данные не подменяются демоданными при `APP_MODE=real`.

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

`start.cmd` работает при стандартном запрете PowerShell-скриптов. Альтернатива — `start.ps1` (параметры `-Mode` и `-Port`) либо команды вручную:

```powershell
conda activate msc-hack
cd frontend
npm ci
npm run build
cd ..
$env:OMP_NUM_THREADS = '4'
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

Если команда уже рассчитала `data_handoff`, повторное выполнение EDA не требуется:

```powershell
conda activate msc-hack
python -m scripts.train --handoff D:/lct-data/data_handoff
.\start.cmd real
```

Для Docker после обучения измените `.env`: `APP_MODE=real`, затем `docker compose up -d --force-recreate`.

Нужны `feature_list.json`, `ml_ready/train_compact.parquet` (либо `train.parquet`), `validation.parquet`, `test.parquet`, `scoring_latest.parquet`. `objects_current.parquet` добавляет названия объектов; `ml/panel_*.parquet` — историю графика за 30 дней. Без панели показывается один доступный срез, без координат — реестр объектов. Нет выдуманного геокодирования.

CLI сравнивает LogisticRegression и HistGradientBoosting отдельно для двух направлений; сохраняет победителя, метрики и контракт признаков. Выбор делается по validation; тест и порог не смешиваются. При недостатке классов или несовместимой схеме обучение прекращается с ошибкой. Перезапустите сервис после публикации новых артефактов.

## Возможности

* Сводка, направления риска, интерактивная схема, динамика предупреждений.
* Журнал: поиск, фильтры, пагинация, исторические прогнозы, CSV текущего среза.
* Карточка: целевой интервал, известное состояние, наблюдения и заявка на диагностику.
* Ручные и автоматические заявки; статусы «Новая → В работе → Завершена» / «Отклонена».
* Карточки моделей: метрики, кандидаты, признаки, происхождение данных.
* Пакетное применение моделей: `POST /api/predict/sensor`, `POST /api/predict/infrastructure`; строгий контракт признаков из `GET /api/models`.

## Разработка и проверки

```powershell
conda activate msc-hack
python -m pytest
cd frontend
npm run build
npm run dev
```

Браузерная проверка на Windows с установленным Edge: при работающем API выполните из `frontend` команду `npm run test:e2e`. Тест создаёт и завершает явно помеченную заявку `E2E` в текущем деморежиме. Снимки desktop/mobile сохраняются в `reports/`.

Для frontend dev сервер API запускается отдельно на 8000; Vite на 5173 проксирует `/api`. Стили и компоненты отделены от API. [Архитектура и инструкция для фронтендера/ML-команды](docs/ARCHITECTURE.md).

Основные API: `GET /api/dashboard`, `/api/objects`, `/api/predictions`, `/api/models`, `/api/data-quality`, `/api/tickets`; `POST /api/predictions/run`, `/api/tickets`, `/api/tickets/generate`; `PATCH /api/tickets/{id}`. OpenAPI: `/openapi.json`.

Рекомендации по используемым механизмам: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [FastAPI в Docker](https://fastapi.tiangolo.com/deployment/docker/), [HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html).
