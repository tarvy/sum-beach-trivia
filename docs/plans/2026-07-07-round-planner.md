# Round planner: game-size controls + live "quick math" + flags

Date: 2026-07-07
Branch: `feat/round-planner`

## The reported pain

Host left "questions kept per person" at 5, lots of people contributed, and the
builder made **way too many rounds** (used every question). The `5` reads like a
game-size cap but it's per-person, so with N contributors it silently balloons.
The host had **no direct lever for game size** (how many rounds, how big) and
**no preview** — Start was a blind one-way door.

## What shipped (this pass)

Direct, legible control over game shape at setup, with live math:

1. **Questions per round** (new persisted setting, default 5, range 3–12). Was a
   hardcoded `target_size=5`; now threaded through `build_rounds`. Bigger rounds
   → fewer rounds.
2. **Max rounds** (new persisted setting, nullable/0 = auto, range 1–20). A soft
   cap: when the natural per-category rounds exceed it, the smallest rounds are
   consolidated (merged into "Mixed Bag") until the count fits. Never benches
   questions (keeps the every-contributor-guaranteed invariant); merged rounds
   may exceed the target size — surfaced as an honest flag.
3. **Live "quick math" preview** (`GET /api/host/round-plan`, read-only) — a
   projection of the round structure from current questions + settings without
   building: per-category breakdown (own-round vs → Mixed Bag), projected round
   count, questions in play vs. benched, contributor count, round-by-round list.
4. **Flags** — banners for the mismatch cases: nothing contributed; a category
   too thin for its own round; per-person cap benching; max-rounds consolidation
   (and its oversized-round consequence).

## How it's built

- `app/db.py` — game table gains `questions_per_round` (default 5) and
  `max_rounds` (nullable); idempotent `init_db()` migrations for both.
- `app/models.py` — `set_questions_per_round` (3–12), `set_max_rounds` (1–20,
  0/null clears).
- `app/rounds.py` — read-only `_assemble()` computes the round groups (selection
  + shaping + max-rounds `_consolidate`) without writing; `build_rounds` calls it
  then persists; `plan_preview()` calls it and summarizes. Shared core → the
  preview and the real build can't drift (guarded by a parity test).
- `app/main.py` — `SettingsIn` + `set_settings` wire the two new settings;
  `GET /api/host/round-plan`; `/api/state` exposes both.
- `static/host.html` — setup card 1 reworked into a **Game shape** planner
  (three inputs + live preview panel + flags); run-stage settings block mirrors
  the new inputs. Saves on change, then re-fetches the plan.

## Tests / verification

Full suite green (147). New round tests: per-round size drives the split;
max-rounds consolidation; preview-vs-build parity (anti-divergence guard);
settings validation + state round-trip for both new fields; the round-plan
endpoint. Visual round: setup card verified via an isolated harness at 1280px
across empty / healthy / benched / capped / 8-category states — inputs align in
a row, labels sit above their fields, chips wrap without overflow, flags are
color-coded. (agent-browser can't reach loopback in this session; the render was
verified against the real markup + `renderPlan()` in a network-free harness.)

## Deferred: team-wide author distribution (needs decision)

Unchanged from `2026-07-06-round-fairness.md`: rounds build before teams exist
and nothing maps contributor→team today. Fair per-team author counts require
either binding contributors to teams up front or moving the build to after teams
form — a product-direction call. Not built this pass, which delivers the
game-size control + math + flags Travis called "more important."
