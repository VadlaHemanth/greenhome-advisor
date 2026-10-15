#!/usr/bin/env bash
# Local-only demonstration, even if .env contains an older public tunnel config.
set -euo pipefail
cd "$(dirname "$0")/.."
export GREENHOME_PUBLIC_MODE=false
export GREENHOME_GATEWAY_TOKEN=
export GREENHOME_ALLOWED_HOSTS=localhost,127.0.0.1
export GREENHOME_ALLOWED_ORIGINS="http://localhost:${PORT:-8000},http://127.0.0.1:${PORT:-8000}"
exec bash scripts/run_local.sh
