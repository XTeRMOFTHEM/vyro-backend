#!/usr/bin/env bash
# VYRO — quick start script (no Docker)
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[vyro] creating venv..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

echo "[vyro] applying migrations..."
alembic upgrade head

if [ "$1" == "--seed" ]; then
  echo "[vyro] seeding demo data..."
  python scripts/seed.py
fi

echo "[vyro] starting server on http://0.0.0.0:8000 (docs: /docs, playground: /playground)"
uvicorn app.main:app --host 0.0.0.0 --port 8000
