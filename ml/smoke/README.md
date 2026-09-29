# Smoke-signal model handoff

Selected compact CatBoost candidate for `smoke_signal_24_48h` (future registered smoke signal, not confirmed fire).

- Model: `data_handoff/fire_ml/models/candidate_history_compact_20260929/smoke_catboost_20260929T163234Z.cbm`
- Metadata: `data_handoff/fire_ml/models/candidate_history_compact_20260929/smoke_catboost_20260929T163234Z.json`
- Detailed validation and final test report: [`HANDOFF.md`](data_handoff/fire_ml/models/candidate_history_compact_20260929/HANDOFF.md)
- Russian file guide, run instructions, team role and challenges: [`MODEL_GUIDE_RU.md`](data_handoff/fire_ml/models/candidate_history_compact_20260929/MODEL_GUIDE_RU.md)
- Final test AP: 0.01624; precision: 1.71%; recall: 14.36%; threshold: 0.034009546.

The final test was evaluated once after model and threshold selection. Do not tune on those results. Training data and final prediction Parquet files are intentionally excluded from this repository; see `.gitignore`.
