# Sum Beach Trivia — task runner.
# Put your key in a .env file (cp .env.example .env) or export ANTHROPIC_API_KEY.
# `set dotenv-load` makes recipes read .env automatically.

set dotenv-load := true

# the deploy target (see deploy/deploy.md)
SPRITE := "sum-beach-trivia"

# list available commands
default:
    @just --list

# one-time setup: create a virtualenv and install dependencies
install:
    python3 -m venv .venv
    .venv/bin/pip install --quiet -r requirements.txt
    @echo "Installed. Next: cp .env.example .env, add your ANTHROPIC_API_KEY, then run 'just run'."

# run the app (reads ANTHROPIC_API_KEY + optional GRADING_MODEL from .env/env)
run port="8000":
    .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port {{port}}

# run with autoreload while developing
dev port="8000":
    .venv/bin/uvicorn app.main:app --reload --port {{port}}

# run the test suite (no API key needed — grading is mocked)
test:
    .venv/bin/python -m pytest -q

# print the current game's join code and HOST KEY from the database
keys:
    @.venv/bin/python -c "import app.db, os; c=app.db.connect(os.environ.get('TRIVIA_DB','trivia.db')); r=c.execute('SELECT code, host_key FROM game WHERE id=1').fetchone(); print(f'join code: {r[\"code\"]}   HOST KEY: {r[\"host_key\"]}') if r else print('no game yet — start the app once with: just run')"

# wipe local game data (questions, teams, scores, photos) for a fresh game
reset:
    rm -f trivia.db trivia.db-wal trivia.db-shm
    rm -rf uploads && mkdir -p uploads
    @echo "Game data wiped. A fresh game is created next time you run: just run"

# push code to the sprite and restart it (run after editing app/ or static/)
deploy:
    sprite file push -r -s {{SPRITE}} ./app             /app/app
    sprite file push -r -s {{SPRITE}} ./static          /app/static
    sprite file push    -s {{SPRITE}} ./requirements.txt /app/requirements.txt
    sprite exec -s {{SPRITE}} -- sprite-env services restart web
    @sprite info -s {{SPRITE}} | grep -i '^URL'

# wipe the sprite's game data for a fresh game (also regenerates the host key)
deploy-reset:
    sprite exec -s {{SPRITE}} -- rm -f /data/trivia.db /data/trivia.db-wal /data/trivia.db-shm
    sprite exec -s {{SPRITE}} -- sprite-env services restart web
    @echo "Sprite game data wiped. New host key: run 'just sprite-keys'"

# print the sprite game's join code + HOST KEY
sprite-keys:
    @sprite exec -s {{SPRITE}} -- python3 -c "import sqlite3; r=sqlite3.connect('/data/trivia.db').execute('select code,host_key from game where id=1').fetchone(); print('join code',r[0],' HOST KEY',r[1])"
