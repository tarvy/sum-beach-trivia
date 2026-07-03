---
name: feature-delivery
description: Use when building any feature, fix, or UI change in sum-beach-trivia — "add X", "change the host screen", "fix the layout of Y". Walks planning → implementation → a mandatory agent-browser visual feedback round → ship. The visual round exists to catch small rendering defects (misaligned inputs, wrapped labels shoving things around, overflow) BEFORE Travis sees them.
---

# Feature Delivery

Plan → implement → **visually verify with agent-browser** → ship. This repo is a
dark factory (see CLAUDE.md): you own merge and triage; no PRs, no approval
gates. The visual feedback round is NOT optional — a change that passes tests
but renders wrong is not done. Canonical miss this skill exists to prevent:
the bank page's "Also accept" input sat pixels below its row because its
wrapped label grew downward in a center-aligned flex row. A single screenshot
would have caught it.

## Phase 1 — Plan

1. Read CLAUDE.md, the relevant screen(s) in `static/`, and any feedback docs
   in `docs/feedback/` touching this area.
2. Write the plan to `docs/plans/YYYY-MM-DD-<slug>.md`: requirements, files to
   touch, implementation steps, test plan, and — required — a **visual
   surfaces** section: which screens/states change, at which viewport each
   will be verified, and what "looks right" means (alignment, spacing,
   wrapping, empty states).
3. Dark factory: don't wait for approval. Ask Travis only if the request is
   genuinely ambiguous about WHAT to build (never about whether to proceed).

## Phase 2 — Implement

1. Branch: `feat/<slug>` or `fix/<slug>`.
2. House rules (CLAUDE.md is canonical): stdlib sqlite3 via the thread-local
   `db()` factory; rollback on any failed write (see
   `tests/test_connection_hygiene.py`); schema changes go in BOTH `SCHEMA` and
   an idempotent `init_db()` migration; vanilla JS, no build step, style via
   `static/app.css` variables; answers never reach public payloads.
3. Full suite green before Phase 3:
   `.venv/bin/python -m pytest -q`

## Phase 3 — Visual feedback round (mandatory for any UI-touching change)

Run the app on a scratch DB, drive it to the affected states, screenshot, and
**actually look at every screenshot** — then fix and re-shoot until clean.

```bash
# 1. scratch server (never the repo's trivia.db)
(TRIVIA_DB=/tmp/fd-vis.db TRIVIA_UPLOADS=/tmp/fd-up .venv/bin/uvicorn app.main:app --port 8442 &)
sleep 2
KEY=$(.venv/bin/python -c "import sqlite3; print(sqlite3.connect('/tmp/fd-vis.db').execute('select host_key from game').fetchone()[0])")

# 2. seed a representative game (adjust to the feature)
curl -s -XPOST localhost:8442/api/questions -H 'Content-Type: application/json' \
  -d '{"author":"Gladys","category":"History","text":"Sample question long enough to wrap on a phone?","answer":"Yes"}'
# repeat for 2-3 authors/categories; then:
curl -s -XPOST "localhost:8442/api/host/build-rounds?host_key=$KEY"
curl -s -XPOST localhost:8442/api/teams -H 'Content-Type: application/json' -d '{"name":"Sandy Bottoms"}'
# set any phase: curl -s -XPOST "localhost:8442/api/host/phase?host_key=$KEY" -H 'Content-Type: application/json' -d '{"phase":"round_open","round_id":1}'

# 3. host-gated pages: inject the key instead of typing it
agent-browser open --viewport 1280x800 "http://127.0.0.1:8442/bank.html"
agent-browser eval "localStorage.setItem('host_key','$KEY'); location.reload()"

# 4. screenshot every affected screen/state and READ each image
agent-browser screenshot /tmp/fd-bank.png
```

Viewports: `play.html`/`contribute.html` → **390x844** (phone); `host.html`/
`bank.html` → **1280x800** (laptop); `display.html` → **1920x1080** (TV).
Verify every affected screen at its viewport, in every phase/state the change
touches (use the phase endpoint to walk states). Include at least one
"awkward" state: longest realistic text, empty list, 8+ teams.

Defect checklist — hunt for these in each screenshot, don't just confirm the
feature exists:
- Row/baseline alignment: do inputs, buttons, chips in a row share a baseline?
- Wrapping: does a wrapped label/title push siblings around? (Labels should
  grow AWAY from the content they label.)
- Overflow/clipping: long team names, long questions, small widths.
- Spacing rhythm: gaps consistent with neighboring cards (app.css vars).
- Empty/zero states: does the screen make sense with no data?
- Phone: touch targets ≥44px, no horizontal scroll.
- Interact, don't just render: click the primary action per screen; watch for
  console errors (`agent-browser errors` if available) and dead buttons.

Tear down when done: `pkill -f "port 8442"; rm -f /tmp/fd-vis.db*`.

If agent-browser cannot resolve hosts (sandboxed background sessions), say so
explicitly in the report, deploy, and flag the affected screens for Travis to
eyeball — never silently skip the round.

## Phase 4 — Ship

1. Full suite once more, then merge to main and push per dark-factory rules
   (CLAUDE.md: `gh auth switch --user tarvy` → push → switch back).
2. `just deploy` (full tree, never partial). If scripts/ or data/ changed,
   push those too: `sprite file push -r -s sum-beach-trivia ./scripts /app/scripts`.
3. Verify live: `curl -s https://sum-beach-trivia-btt6i.sprites.app/api/state`
   returns healthy JSON; spot-check the changed endpoint/page. The gateway can
   502 for ~30-60s after restart — retry, then restart the service once before
   digging.
4. Report: what shipped, screenshots taken (or the sandbox caveat), test
   count, live-verification results.

## Rules

- No implementation without the plan file; no ship without green tests AND the
  visual round (or its explicit sandbox caveat).
- Never run visual checks against the repo's `trivia.db` or the live sprite's
  data; scratch DBs only.
- QR-scan and phone-camera flows can't be verified locally (need HTTPS) — test
  those on the sprite after deploy.
- Fix what the screenshots show, not just what the diff intended: if you spot
  an unrelated visual defect on an affected screen, fix it in the same branch
  when trivial, or file it in `docs/feedback/` when not.
