# Руководство по модели

## Что лежит рядом

- `smoke_catboost_20260929T163234Z.cbm` — бинарная модель CatBoost.
- `smoke_catboost_20260929T163234Z.json` — контракт модели: target, порядок и имена features, параметры, training window, threshold.
- `HANDOFF.md` — OOF/test метрики и ограничения.
- `MODEL_GUIDE_RU.md` — это руководство.

## Как читать metadata

- `target`: `smoke_signal_24_48h`, зарегистрированный будущий сигнал дыма; это не подтверждённый пожар.
- `features`: 4 числовых признака и 2 causal channel-history признака в порядке подачи в модель.
- `threshold`: `0.034009546`, выбран по OOF folds 2023-2024. Применять этот threshold только к модели, перечисленной в metadata.
- `training_start` / `training_end`: границы fit; строки до 2022 не использовались как supervised training rows.
- `negative_sampling_rate: 1.0`: отрицательные примеры не undersample-ились.
- `test_read: false` относится к fit metadata. Финальная оценка test была выполнена отдельным однократным запуском после фиксации модели и threshold.

## Запуск из клона

Нужны Python 3.13 и приватно переданные локальные данные `data_handoff/fire_ml/ml/train.parquet` и `validation.parquet`. Сырые данные намеренно не включены в Git.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Чтобы воспроизвести финальный compact fit (это создаст новую версию модели, не переписывая переданную):

```powershell
.\.venv\Scripts\python.exe train.py `
  --data-dir data_handoff/fire_ml/ml `
  --output-dir data_handoff/fire_ml/models `
  --feature-subset smoke_messages_1d smoke_messages_7d smoke_messages_30d events_7d `
  --channel-history `
  --negative-rate 1.0 `
  --threshold 0.034009546 `
  --iterations 343 --depth 7 --learning-rate 0.04 --l2-leaf-reg 8 `
  --threads 1 --memory-limit 1GB
```

Полный OOF можно повторить через `validate.py`. Запускайте каждый год отдельным процессом, чтобы ОС освобождала память между folds:

```powershell
.\.venv\Scripts\python.exe validate.py `
  --models catboost --fold-years 2023 `
  --feature-subset smoke_messages_1d smoke_messages_7d smoke_messages_30d events_7d `
  --channel-history --negative-rate 1.0 --catboost-iterations 343 `
  --output-dir data_handoff/fire_ml/experiments/recheck_2023
```

Повторите с `--fold-years 2024` и `2025`, задав для каждого отдельный `--output-dir`.

## Test и inference

`predict.py --evaluate-test` читает test labels, считает метрики и сохраняет predictions. Для этой версии его уже запускали один раз; **не запускайте повторно на том же test для подбора модели или threshold**. Результаты и predictions сохранены в handoff/workspace, но parquet исключён из Git.

Текущий `predict.py` — gated evaluation runner для label-bearing test, а не общий сервис инференса на новых данных без target. Для production scoring на неизвестном будущем потоке потребуется отдельная команда/обёртка, которая принимает features, строит channel-history из уже созревших train/validation labels и сохраняет probabilities без чтения target.

Channel-history в каждом моменте прогноза использует только labels с `target_end <= prediction_time`; будущие labels не должны попадать в признаки. `feature_list.json` — схема исходного набора features для full-feature экспериментов; для этого compact model авторитетный список находится в её JSON metadata.

## Результаты

- Compact OOF pooled AP: `0.02132`; folds 2023/2024/2025: `0.03157 / 0.02742 / 0.01595`.
- Однократный test: AP `0.01624`, precision `1.71%`, recall `14.36%`, F2 `0.05782` при threshold `0.034009546`.
- AP test ниже OOF; качество алертинга ограничено низким precision и temporal shift.

## Моя роль в команде

> Я отвечала за ML-контур задачи: формализацию target, временную схему train/validation и purge, построение baseline на полной выборке, leakage-аудит признаков, разработку и проверку causal channel-history, OOF/threshold-оценку и подготовку воспроизводимого CatBoost candidate. Бизнес-эффект и внедрение в диспетчерский процесс не заявляю: они не измерялись этим экспериментом.

## Основные сложности и решения

- **Редкий положительный класс.** OOF prevalence около `0.313%`. Сравнение ведётся через pooled/per-fold Average Precision и Dummy baseline; undersampling не применялся.
- **Временная утечка и сдвиг.** Использованы expanding temporal folds и purge по `target_end`; channel-history рассчитывается as-of `prediction_time`. AP заметно различается по годам.
- **Ограничение памяти.** Полный feature set и disk-backed Pool всё равно создают высокую пиковую нагрузку. Компактный кандидат обучался отдельно, по одному process/fold; test evaluation был потоковым.
- **Precision/recall trade-off.** На test AP `0.01624`, precision `1.71%`, recall `14.36%`; допустимая нагрузка алертов — отдельное продуктовое решение.
