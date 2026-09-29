FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 APP_RUNTIME_DIR=/app/runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip --mount=type=bind,source=docker/wheels,target=/wheels \
    if ls /wheels/*.whl >/dev/null 2>&1; then \
      pip install --find-links=/wheels --timeout 120 --retries 5 -r requirements.txt; \
    else \
      pip install --timeout 120 --retries 5 -r requirements.txt; \
    fi
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY --from=frontend /frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 app && mkdir -p /app/runtime && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
