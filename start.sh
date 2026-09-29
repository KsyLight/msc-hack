#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ -z "${APP_MODE:-}" ]; then
  if [ -f runtime/real/dataset.json ]; then APP_MODE=real; else APP_MODE=demo; fi
fi
export APP_MODE
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci --no-audit --no-fund)
fi
(cd frontend && npm run build)
exec conda run --no-capture-output -n msc-hack python -m uvicorn backend.main:app --host 127.0.0.1 --port "${APP_PORT:-8000}"
