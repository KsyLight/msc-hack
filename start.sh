#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
export APP_MODE="${APP_MODE:-demo}"
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi
exec conda run --no-capture-output -n msc-hack python -m uvicorn backend.main:app --host 127.0.0.1 --port "${APP_PORT:-8000}"
