#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export TRIVIA_DB="${TRIVIA_DB:-/data/trivia.db}"
export TRIVIA_UPLOADS="${TRIVIA_UPLOADS:-/data/uploads}"
mkdir -p "$(dirname "$TRIVIA_DB")" "$TRIVIA_UPLOADS"
exec uvicorn app.main:app --host 0.0.0.0 --port 3000
