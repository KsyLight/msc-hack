# Smoke-signal compact candidate

## Model

- Model file: `smoke_catboost_20260929T163234Z.cbm`
- Metadata: `smoke_catboost_20260929T163234Z.json`
- Target: `smoke_signal_24_48h`, a registered future smoke signal; it is not a confirmed fire.
- Features: `smoke_messages_1d`, `smoke_messages_7d`, `smoke_messages_30d`, `events_7d`, `channel_history_count`, `channel_history_rate`.
- Training: full pre-test population with `prediction_time >= 2022-01-01` and `target_end <= 2026-01-01`; 10,561,145 rows, 33,596 positives, no negative undersampling.
- CatBoost: depth 7, 343 iterations, learning rate 0.04, L2 8, seed 42, one thread.
- Decision threshold: 0.034009546, selected using OOF folds 2023-2024.

## Validation

Strict expanding windows, with the training start fixed at 2022-01-01 and `target_end` purged at each validation boundary.

| Validation fold | Four numeric features AP | Numeric + channel history AP |
| --- | ---: | ---: |
| 2023 | 0.00689 | 0.03157 |
| 2024 | 0.00355 | 0.02742 |
| 2025 | 0.00485 | 0.01595 |
| Pooled OOF | 0.00473 | 0.02132 |

Mean fold AP gain was 0.01988; sample standard deviation of fold gains was 0.00762. All three fold gains were positive.

At the threshold selected on 2023-2024, the 2025 validation fold produced precision 1.37%, recall 11.63%, F2 0.0466, and about 25 alerts per 1,000 rows. The higher AP and precision come with substantially lower recall; alert policy is a product decision.

## Final test evaluation

The selected compact candidate was evaluated once on the final test set after the model and threshold were fixed. Do not use these test results for further model or threshold tuning.

- Rows: 1,415,514
- Prevalence: 0.444%
- Average precision: 0.01624
- Threshold: 0.034009546
- Precision: 1.71%
- Recall: 14.36%
- F2: 0.05782
- Confusion counts: TN 1,357,197; FP 52,027; FN 5,387; TP 903
- Alerts: about 37.4 per 1,000 rows

Test AP is below pooled OOF AP (0.02132); prevalence is also higher than OOF prevalence (0.313%), consistent with temporal shift. This is the only candidate evaluated on test. The full 68-feature baseline has strict pooled OOF AP 0.01942, but no test score.

## Reproduce training

The training and validation parquet files are intentionally not included in this handoff. They must be available locally under `data_handoff/fire_ml/ml/` before running:

```powershell
.\.venv\Scripts\python.exe train.py `
  --feature-subset smoke_messages_1d smoke_messages_7d smoke_messages_30d events_7d `
  --channel-history `
  --threshold 0.034009546 `
  --negative-rate 1.0 `
  --threads 1 `
  --memory-limit 1GB `
  --output-dir data_handoff/fire_ml/models
```

`predict.py --evaluate-test` was run once for this candidate. Do not repeat it against the same test set for tuning or model selection.

## Sharing notes

- Commit the model `.cbm`, this metadata JSON, this handoff, source scripts, and `requirements.txt`.
- Do not commit raw datasets, source CSVs, notebook outputs, OOF prediction files, or final test predictions. The root `.gitignore` enforces these exclusions while allowing this selected model bundle.
- Current model is the compact candidate, not the full 68-feature model.
