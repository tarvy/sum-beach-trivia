# Sum Beach Trivia

A lightweight, self-hosted bar-trivia web app for game night with friends. Friends
contribute questions ahead of time; on game night teams write answers by hand, snap one
photo of the sheet per round, and a Claude vision model reads + grades them while the host
confirms. One process, one URL, four screens.

**Status:** Implemented and tested (47 tests passing). Ready for a game-night dry run.

## Running it

### 1. Prerequisites

- Python 3.9+ (3.11+ in production)
- [`just`](https://github.com/casey/just) — `brew install just` (optional but recommended; a no-`just` path is below)
- An Anthropic API key (only needed for grading photos): https://console.anthropic.com

### 2. Start it

```bash
just install            # one-time: create .venv and install dependencies
cp .env.example .env    # then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
just run                # serves on http://localhost:8000
```

Then open **http://localhost:8000** — it links to all four screens.

Get the host password anytime:

```bash
just keys               # prints the game's join code + HOST KEY
```

> The HOST KEY also prints to the server log on first start, but it can be buffered —
> `just keys` reads it straight from the database and is the reliable way to fetch it.

The API key can live in `.env` (auto-loaded) **or** be exported in your shell
(`export ANTHROPIC_API_KEY=...`) — either works.

#### Without `just`

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... .venv/bin/uvicorn app.main:app --port 8000
```

### 3. All commands

| command | what it does |
|---|---|
| `just install` | create `.venv`, install dependencies |
| `just run` / `just run 9000` | start the server (default port 8000) |
| `just dev` | start with autoreload (development) |
| `just keys` | print the current game's join code + HOST KEY |
| `just test` | run the 47-test suite (no API key needed — grading is mocked) |
| `just reset` | wipe game data (questions, teams, scores, photos) for a fresh game |
| `just` | list all commands |

Cheaper grading (pennies a night vs. the Opus default): add `GRADING_MODEL=claude-haiku-4-5` to `.env`.

## The four screens

Everything is served from the one URL. Each person opens the screen for their role:

| Screen | URL | Who / when |
|---|---|---|
| **Landing** | `/` | links to the others |
| **Contribute** | `/contribute.html` | each friend, in the days before — submit your 3 questions |
| **Host** | `/host.html` | you, on a laptop — run the game (needs the HOST KEY) |
| **Play** | `/play.html` | each team, on a phone — join, then snap + submit answer photos |
| **Display** | `/display.html` | the room TV/projector — read-only join code + questions + leaderboard |

## A game, start to finish

**Days before — collect questions.** Share the URL; everyone opens **Contribute**,
enters their name, picks a category, and submits their 3 questions (question + answer +
optional accepted alternates). These persist in the database.

**Game night — on the Host screen** (`/host.html`, paste the HOST KEY):

1. **Build rounds** — groups the contributed questions into balanced rounds by category.
   Tweak/open from the round list.
2. **Open the game** (lobby) — teams open **Play** on their phones, enter a team name, and
   get a recovery code (so a refreshed phone can rejoin).
3. **Run each round:** open a round → teams see the questions and write answers on paper →
   "pens down" closes submissions → each team snaps **one photo of their sheet** and submits.
4. **Mark** — the vision model transcribes and proposes correct/incorrect per answer; you
   confirm, override a score, or add an accepted alternate. Reveal and move to the next round.
5. **Final round** — create it with a multi-item question (e.g. "put these 5 in order") and a
   wager cap. Teams place a wager (0–cap) before seeing it; scoring is proportional to how
   many items they get right.
6. **Tiebreak** (only if needed) — pose a nearest-wins number; closest guess wins.
7. **Done** — final standings; download a CSV of the results from the host screen.

Pause/resume anytime (for the bar run). The leaderboard is always recomputed from the
recorded marks, so any correction — even after a round "ends" — updates every score.

## Stack

FastAPI + SQLite, plain HTML/JS (no build step), polling for live updates, Claude vision
for handwriting grading. State (game/questions/teams/scores) lives in SQLite; uploaded
photos live on disk. Deploy to a [sprite](https://sprites.dev) for a public URL — see
[`deploy/deploy.md`](deploy/deploy.md).

Design details: [`docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md`](docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md).
