# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Dark factory — you own merge and triage

This repo runs as a **dark factory**: Travis reviews outcomes on the live sprite, not diffs. Agents operate end-to-end on their own authority (his explicit standing instruction — it overrides the global never-push-to-main/always-PR rule for this repo only).

- **No PRs, no review gates.** Work on a short-lived branch, get tests green, merge it to `main` yourself, push, deploy. Don't open a PR or wait for approval.
- **Clean principles still apply.** Focused branches, passing tests before merge, conventional commit messages, full-tree sprite deploys, no drive-by scope creep.
- **Triage is yours too.** When something's reported broken, diagnose → fix → merge → deploy → verify on the sprite, without stopping to ask.
- **GitHub identity:** pushes need Travis's personal `tarvy` account — `gh auth switch --user tarvy`, do the git work, then `gh auth switch --user travclarity` back (approved, standing).

## Overview

Self-hosted bar-trivia web app for a game night with friends. Friends contribute questions ahead of time; on game night teams write answers on paper, snap one photo of the sheet per round, and a Claude vision model transcribes + grades them while the host confirms. **One process, one URL, four screens** (`/contribute`, `/host`, `/play`, `/display`) — FastAPI + SQLite, vanilla HTML/JS with no build step, polling for live updates.

## Architecture & Patterns

- **One FastAPI app, four static screens.** `app/main.py::create_app()` mounts a JSON API and serves the `static/*.html` screens. Each role opens its own screen; there is no SPA, router, or bundler. Live updates are plain `fetch` polling of `/api/state` and friends.
- **Single-game model.** The `game` table is constrained to exactly one row (`CHECK (id = 1)`). `create_app()` auto-creates it on first boot with a random join `code` + `host_key` and prints the host key to the log.
- **Phase state machine is the source of truth.** `game.phase` drives every screen: `draft → lobby → round_open → round_closed → marking → reveal → final_wager → final_open → tiebreak → done`, with `paused` orthogonal. Endpoints gate on phase (e.g. `SUBMIT_PHASES = {round_open, round_closed, final_open}` guards photo submission — `round_closed` is "pens down", teams can still hand in their sheet until `marking`). Add new phases to `VALID_PHASES` in `main.py`.
- **Two MC modes** (`game.mc_mode`, host-switchable any time via `POST /api/host/mc-mode`, exposed in `/api/state`): **`gladys`** (default, "Gladys the AI MILF") — photo submissions are AI-graded into `mark` rows; **`lacey`** ("Lacey in Charge") — photos are stored but never AI-graded, a human MC enters every mark via `POST /api/host/mark` (which works with or without a submission). In gladys mode a grading exception still returns `{ok: true, graded: false}` — the submission is never lost; the MC marks it by hand.
- **Per-thread SQLite connections.** FastAPI runs sync handlers on a thread pool; a SQLite connection must never cross threads. `db()` is a thread-local factory — **always use it in routes.** `app.state.conn` is a test-only back-compat alias (main thread); never use it in production routes. `:memory:` DBs share one connection (tests run sequentially).
- **Leaderboard is always recomputed, never stored.** `scoring.team_totals()` sums from the `mark` rows on every request, so any correction (even after a round "ends") retroactively fixes all scores. Don't cache or persist totals.
- **Serializers enforce the answer-privacy boundary.** `serializers.public_question` omits the answer; `host_question` includes it. Choose deliberately per endpoint (see Anti-Patterns).
- **Round building is idempotent + rebuildable.** `rounds.build_rounds()` detaches/deletes non-final rounds, then regroups unassigned questions by category into ~5-question rounds. Safe to re-run.
- **Grading is injectable.** `app.state.grading_client` (if set) is used instead of the real Anthropic call — tests inject a fake so no API key is needed. Real path: `grading.grade_sheet()` uses `client.messages.parse()` with a JSON-schema-typed `SheetGrade`.

## Stack Best Practices

- **DB access:** stdlib `sqlite3` only, `row_factory = sqlite3.Row`, parameterized queries. Reusable queries that aren't trivial belong in `app/models.py`; keep route handlers thin.
- **Frontend:** vanilla JS in the `static/*.html` files, shared styling via CSS variables in `static/app.css`. No framework, no build, no external CDN. Persist client identity in `localStorage`.
- **Request bodies:** Pydantic models (see `*In` classes in `main.py`).
- **Tests:** `create_app(db_path=":memory:")` + `httpx` `ASGITransport` (see `tests/test_api_*.py`). Inject `app.state.grading_client` to avoid real vision calls.
- **Schema changes:** edit `SCHEMA` in `app/db.py` for fresh DBs **and** add an idempotent migration in `init_db()` (PRAGMA `table_info` check + `ALTER TABLE`) so existing `trivia.db` files upgrade in place.

## Anti-Patterns

- **Never share a SQLite connection across threads** — it corrupts memory and crashes the process. The per-thread `db()` factory exists precisely for this; don't cache a connection at module/app scope for route use.
- **Keep answers off the public display path.** `serializers.public_question` omits answers; only host views (`host_key`) and the owner-facing `GET /api/questions/mine?contributor_id=` (so a contributor can review/edit their own) include them. Don't widen answer exposure into the player/display surface.
- **Don't store/cache the leaderboard** — recompute from `mark` rows.
- **Don't add a build step, frontend framework, or external asset host.** Plain HTML/JS, one process, one URL is intentional.
- **Don't create a second game row** (`CHECK (id = 1)`), and don't bypass `just` with ad-hoc `uvicorn`/ports.

## Data Models

SQLite (`app/db.py`). Key tables and non-obvious columns:

- **game** — single row (`id=1`): `phase`, `current_round_id`, `paused`, `host_key`, `submissions_open` (host-controlled contribution window), `mc_mode` (`lacey`|`gladys`), tiebreak fields.
- **category** — the 9 `STANDARD_CATEGORIES`, seeded on init.
- **contributor** — a person who contributes questions: `token` (random, stored in their browser localStorage — this IS their identity), editable `name`, `recovery_code`. Created/updated via `POST /api/contributor`.
- **question** — `author_name` (display label) + `contributor_id` FK → contributor. `answer` + `acceptable_answers` (JSON list) for normal questions; `answer_items` (JSON list) + `ordered` for multi-item/final questions. `round_id` is NULL until assigned by round-building.
- **team** / **team_member** — `team.name_lower` UNIQUE, `recovery_code` to rejoin; `team_member` rows (optionally linked to a `contributor_id`) form the roster the team-builder manages.
- **submission** — one photo per `(team_id, round_id)` (UNIQUE); `photo_path` points at a file in `uploads/`.
- **wager** / **tiebreak_guess** — final-round bet (0..`wager_cap`) and tiebreak number.
- **mark** — per `(team_id, question_id)` grading result: `transcription`, `is_correct`, `score`, `items_correct` (multi-item), `confidence`, `flagged`, `manually_corrected`. This is the sole input to scoring.

Scoring note: final-round delta is proportional and can go **negative** — `scoring.final_round_delta = round(amount * (2*fraction_correct - 1))`.

## Security & Configuration

- **Identity mechanisms:** host `host_key` (gates all `/api/host/*` via `require_host`); team `recovery_code` (rejoin); contributor identity = a random browser `token` (localStorage) upserted to a `contributor` row via `POST /api/contributor`, which returns a `contributor_id` (used to attribute/list/edit questions) + a `recovery_code`. Edits go through `PUT /api/questions/{id}` and are allowed only for the owning `contributor_id` while `submissions_open` is true.
- **Environment** (`.env` auto-loaded by `just` via dotenv-load; see `.env.example`):
  - `ANTHROPIC_API_KEY` — only needed for photo grading, not to boot the app.
  - `GRADING_MODEL` — defaults to `claude-opus-4-8`; set `claude-haiku-4-5` for cheap nights.
  - `TRIVIA_DB` (default `trivia.db`), `TRIVIA_UPLOADS` (default `uploads`).
- **Storage:** state in SQLite (WAL mode + `busy_timeout` for concurrent readers/one writer); uploaded answer-sheet photos on disk under `uploads/`.
- **Gating:** submissions require the right phase **and** matching `current_round_id`; host routes require the host key.

## Commands & Scripts

**Always use the `just` recipes** (turnkey; default port **8000**). Run `just` to list them.

| Command | What it does |
|---------|--------------|
| `just install` | One-time: create `.venv`, install deps. |
| `just dev` | Run with autoreload (development). |
| `just run` / `just run 9000` | Run without reload (override port). |
| `just test` | Full test suite (no API key — grading is mocked). |
| `just keys` | Print the current game's join code + HOST KEY. |
| `just reset` | Wipe local game data (questions, teams, scores, photos). |
| `just deploy` | Push `app/` + `static/` + `requirements.txt` to the sprite, restart it, print the URL. |
| `just deploy-reset` | Wipe the **sprite's** game data (regenerates the host key). |
| `just sprite-keys` | Print the **sprite** game's join code + HOST KEY. |

- **Single test file / case:** `.venv/bin/python -m pytest tests/test_api_contribute.py -q` or `.venv/bin/python -m pytest -k contributor -q`.

### Deploy / the real environment (sprite)

The game is meant to run on **one public sprite** at an HTTPS URL — that is the
game-night and the integration-test environment, not localhost. See
`deploy/deploy.md` for first-time setup (`deploy/run.sh` loads the API key from
`/data/secrets.env`).

- **Iterate loop:** edit locally → `just deploy` → open the sprite display on a laptop/TV → scan with a real phone. Don't bother testing the QR or photo flow locally (below).
- **Sprite:** name `sum-beach-trivia`, URL `https://sum-beach-trivia-btt6i.sprites.app`. The `SPRITE` var at the top of the `justfile` is the single place that name lives.
- **Why test on the sprite, not localhost:** the lobby QR encodes whatever origin the **display page was loaded from** (its `window.location.origin`, passed to `GET /api/qr?origin=…`). On localhost that's `localhost:8000`, which a phone can't reach. Phone camera capture also needs HTTPS, which the sprite has and local dev doesn't. So localhost can't exercise the join-by-QR or photo-grading paths end-to-end.
- **Deploy the FULL tree, never a partial push.** `just deploy` ships all of `app/` and `static/` because `main.py` is versioned together with `models.py`/`db.py`/serializers and the `static/*.html`. Pushing only one changed file onto an older tree causes a schema/API mismatch → 500s. (`init_db()` migrations run on boot, so the on-disk `/data/trivia.db` upgrades in place.)
- The sprite **auto-sleeps when idle** and wakes on the next request (first request after a sleep is slow). The DB + uploaded photos live on `/data` and survive sleeps.
- No linter/formatter is configured; don't assume one.
