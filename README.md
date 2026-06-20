# Sum Beach Trivia

A lightweight, self-hosted bar-trivia web app for game night with friends. Friends
contribute questions ahead of time; on game night teams write answers by hand, snap one
photo of the sheet per round, and a vision model reads + grades them while the host
confirms. Runs on a single persistent [sprite](https://sprites.dev) at one public URL.

See the design spec: [`docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md`](docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md)

## Status

Implemented. Backend + four web views complete; 47 tests passing. Ready for a game-night dry run.

## Stack

FastAPI + SQLite, plain HTML/JS (no build step), polling for live updates, Claude vision
for handwriting grading. Deployed to a sprite; the SQLite DB and uploaded photos live on
the sprite's persistent disk.

## Quickstart (just)

Requires [`just`](https://github.com/casey/just) (`brew install just`).

```bash
just install              # one-time: create .venv and install deps
cp .env.example .env      # then put your ANTHROPIC_API_KEY in .env
just run                  # start the app on http://localhost:8000
just keys                 # print the game's join code + HOST KEY
```

Other commands: `just test` (no API key needed), `just dev` (autoreload),
`just reset` (wipe game data for a fresh game), `just` (list all).
Set a port with `just run 9000`. Cheaper grading: add `GRADING_MODEL=claude-haiku-4-5` to `.env`.

## Run locally

```bash
pip install -r requirements.txt
ANTHROPIC_API_KEY=your-key-here uvicorn app.main:app --port 8000
```

The game code and HOST KEY are printed to stdout on first start. Open `http://localhost:8000`.

## Deploy

See [`deploy/deploy.md`](deploy/deploy.md) for step-by-step sprite deployment instructions.
