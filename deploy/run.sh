#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Load secrets (e.g. ANTHROPIC_API_KEY, GRADING_MODEL) from a file if present.
# Keeps the key out of process args and service logs. On a sprite this file
# lives on the persistent disk (/data/secrets.env); locally it falls back to .env.
for envfile in /data/secrets.env "$(pwd)/.env"; do
  if [ -f "$envfile" ]; then set -a; . "$envfile"; set +a; break; fi
done

export TRIVIA_DB="${TRIVIA_DB:-/data/trivia.db}"
export TRIVIA_UPLOADS="${TRIVIA_UPLOADS:-/data/uploads}"
mkdir -p "$(dirname "$TRIVIA_DB")" "$TRIVIA_UPLOADS"

# python3 -m uvicorn (not bare `uvicorn`) so it works regardless of PATH.
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000
