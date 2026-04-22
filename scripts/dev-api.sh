#!/usr/bin/env bash
# Dev-only helper: run backend + runner locally without Docker.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${HERE%/scripts}"

export ANVIL_DATABASE_URL="${ANVIL_DATABASE_URL:-postgresql+asyncpg://anvil:anvil@localhost:5432/anvil}"
export ANVIL_BEARER_TOKEN="${ANVIL_BEARER_TOKEN:-dev-token}"
export ANVIL_RUNNER_SOCKET="${ANVIL_RUNNER_SOCKET:-$ROOT/var/run/runner.sock}"

mkdir -p "$(dirname "$ANVIL_RUNNER_SOCKET")"
mkdir -p "$ROOT/var/anvil"

cd "$ROOT/backend"
exec uvicorn anvil.main:app --host 0.0.0.0 --port 8080 --reload
