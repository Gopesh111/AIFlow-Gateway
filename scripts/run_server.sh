#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "          AIFLOW-GATEWAY PRODUCTION RUNNER                "
echo "=========================================================="

HOST=${HOST:-"0.0.0.0"}
PORT=${PORT:-"8000"}
WORKERS=${WORKERS:-4}

echo "Applying latest database migrations via Alembic..."
alembic upgrade head || {
    echo "Warning: Alembic migration failed or DB not ready. Proceeding with caution..."
}

echo "Seeding initial default keys..."
python scripts/seed_data.py || true

echo "Starting Uvicorn async ASGI server on ${HOST}:${PORT} with ${WORKERS} workers..."
exec uvicorn app.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --loop uvloop \
    --http httptools \
    --timeout-keep-alive 65 \
    --limit-concurrency 1000 \
    --backlog 2048
