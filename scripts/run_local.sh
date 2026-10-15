#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Create the Python environment and install requirements first. See README."
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  echo "Build the React frontend first: cd frontend && npm ci && npm run build"
  exit 1
fi
.venv/bin/python scripts/check_readiness.py
exec .venv/bin/python -m uvicorn greenhome.api:app \
  --host 127.0.0.1 --port "${PORT:-8000}" --no-access-log \
  --workers "${WEB_CONCURRENCY:-1}" --limit-concurrency 256 \
  --no-proxy-headers --timeout-keep-alive 5
