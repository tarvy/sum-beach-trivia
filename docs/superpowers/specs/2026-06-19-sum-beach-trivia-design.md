# Sum Beach Trivia — Design Spec

**Date:** 2026-06-19
**Status:** Approved design, pre-implementation
**Author:** Travis Glass (with Claude)

## 1. What we're building

A lightweight, self-hosted bar-trivia web app for a small group of friends. Friends
contribute their own questions in the days before game night; on game night everyone
is in the same room, teams write answers by hand on a per-round sheet, snap one photo
of the sheet, and submit it. A vision model reads the handwriting and proposes a grade;
the host confirms or overrides; a live leaderboard updates.

The whole thing runs on a single persistent **sprite** (sprites.dev) at one public URL
that everyone hits from their phones.

### Why build (not reuse)

Research confirmed no free off-the-shelf system does this full flow, and **zero** trivia
projects do handwritten-photo grading. The closest pub-quiz apps are either too minimal
(`voax/quizzer`, MIT), unlicensed and unusable (`thtm88/pubquiz`), or GPL Kahoot-style
speed quizzes with the wrong scoring model (`surajcm/darkhold`, `Ralex91/Razzia`). We
build fresh in Python and borrow their hard-won **ideas and edge cases**, not their code.

The part that sounds hardest — reading handwriting — is now the easiest: a single Claude
vision call transcribes the photo *and* judges each answer against the expected answer
(knows "JFK" = "John F. Kennedy", tolerates spelling). Cost is ~$0.10–0.30 for a whole
trivia night.

## 2. Guiding principles

These are non-negotiable; they came from studying where mature apps went wrong.

1. **Scores are always *derived* from stored marks, never a frozen total.** Any host
   correction — even after a round "ends" — recomputes every total automatically. Never
   store a team's total as an authoritative mutable number.
2. **All authoritative state lives in SQLite, not in memory.** Combined with polling
   (below), this gives reconnect/resume nearly for free: a refreshed phone, a rejoining
   team, or the sprite sleeping and waking just reads current state on the next poll.
3. **Role-filtered responses: the `answer` field is NEVER sent to non-host views.**
   Friends contribute questions on the same URL they later play on — no peeking.
4. **Polling, not WebSockets.** Simple, robust, sidesteps the entire class of reconnect
   bugs the WebSocket apps fought. A 2–3s poll interval is plenty for this scale.
5. **The AI proposes; the host is always final.** Every mark has a one-click override and
   a free-form score, and the host can add an accepted alternate answer mid-game.
6. **Laziest thing that works (ponytail bias).** This is a fun side project for ~5 friends
   and a handful of teams. Prefer stdlib over dependencies, one file over five, a button
   the host clicks over an automated state machine. No speculative scale.

## 3. Architecture

- **Platform:** one persistent sprite. Auto-sleeps when idle (free between now and game
  night), wakes on the next HTTP request. Public URL = the only thing anyone needs.
- **Stack:** Python **FastAPI** + **SQLite** (a single file on the sprite's persistent
  disk). Plain server-rendered HTML + a little vanilla JS — **no build step**. One Python
  process that also makes the Claude vision calls via the Anthropic SDK.
- **Live updates:** client-side polling of small JSON endpoints (current phase, leaderboard).
- **Photos:** uploaded as files to the sprite's persistent disk; path stored in SQLite.
- **Grading:** server sends photo + that round's questions/expected answers to Claude
  vision, gets back structured per-question `{transcription, is_correct, confidence}`.
- **Source vs. state:** code lives in the git repo and is deployed to the sprite. The
  SQLite DB and uploaded photos live on the sprite (gitignored) — they're game data.

### Repo layout

```
~/Dev/sum-beach-trivia/
├── docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md
├── app/
│   ├── main.py          # FastAPI app, routes
│   ├── db.py            # SQLite connection + schema/migrations
│   ├── models.py        # data access helpers
│   ├── scoring.py       # derive scores from marks
│   ├── grading.py       # Claude vision call + response parsing
│   └── rounds.py        # balanced-round builder
├── static/              # contribute / host / play / display views (HTML+JS+CSS)
├── tests/
├── deploy/              # sprite deploy + run script
├── .gitignore           # *.db, uploads/, .env
└── README.md
```

### Config / secrets

- `ANTHROPIC_API_KEY` — set in the sprite's env. Only external dependency, only cost.
- `GRADING_MODEL` — defaults to a vision-capable Claude model (decided at plan time per
  the claude-api skill; likely Haiku for cost, with Opus as an override).
- Host access is protected by a simple secret **host key** in the URL/cookie (see §8).

## 4. The four views (one URL)

1. **Contribute** (pre-game): a friend opens the URL, enters their name, and submits
   their 3 questions — pick a category, type the question, the answer, and optional
   accepted alternates. Saved to SQLite immediately; persists for days. Never shows
   anyone else's answers (or their own, after submit, beyond a confirmation).
2. **Host control** (game night, laptop): build/tweak rounds, run the game phase by
   phase, review each team's photo with the AI's transcription + proposed grade, confirm
   or override, advance. Protected by the host key.
3. **Team / play** (game night, phones): join with a team name + get a recovery code,
   see the current round's questions, snap **one photo of the whole sheet** at round
   close, submit. Shows own score/rank on reveal.
4. **Display** (game night, big screen/TV): read-only. Shows join code in lobby, current
   round/questions during play, and the leaderboard on reveal. A distinct `/display`
   route with no controls.

## 5. Game flow (phases)

A single active game moves through these phases. The host advances most transitions with
a button (lazy + flexible beats an over-enforced state machine). Phase is stored in
SQLite; every client polls and renders the right view for its role.

| Phase | Host | Team (phone) | Display (TV) |
|---|---|---|---|
| **draft** | build/tweak rounds from contributed Qs | — | — |
| **lobby** | open game, see/kick teams | join (name + recovery code) | join code + team list |
| **round_open** | reveal round + its questions; submissions open | see questions; write on paper | round title + questions |
| **round_closed** | "pens down"; lock submissions | submit/confirm sheet photo (read-only after) | "pens down" |
| **marking** | review AI grades per team; confirm/override; add alternates | wait | (interstitial) |
| **reveal** | reveal correct answers; push scores | see own result + rank | correct answers + leaderboard |
| → next round | advance to next `round_open` | wait | interstitial |
| **tiebreak** | pose nearest-wins numeric question (only if tied) | submit one number | tiebreak prompt |
| **done** | final standings; export CSV | final standings | podium |
| **paused** | pause/resume at any time (for the bar/break) | "paused" notice | "paused" |

Notes baked in from the harvest:
- A missing photo for a round is a normal **"no submission" = 0**, rendered as a markable
  state in the marking UI — not an error.
- Submissions are rejected server-side once a round is closed (no late writes).
- Reconnect is implicit: any client re-reads phase + its data on the next poll. The sprite
  sleeping/waking mid-game resumes from SQLite with no special handling.

## 6. Data model (SQLite)

Derived from the cleanest parts of the reference apps. Scores are computed from `marks`,
never stored as a mutable total.

- **game** — `id`, `code` (join PIN), `phase`, `current_round_id`, `paused` (bool),
  `host_key`, `created_at`. (One active game at a time is fine for v1.)
- **category** — `id`, `name`, `display_order`. Seeded with the standard set (§7).
- **question** — `id`, `author_name`, `category_id`, `text`, `answer` (canonical),
  `acceptable_answers` (JSON list of alternates), `point_value` (default 1),
  `round_id` (nullable until assigned), `display_order`, `media_url` (nullable; schema
  room for picture/music rounds later — no UI in v1).
- **round** — `id`, `title`, `category_id`, `display_order`, `bonus_multiplier`
  (default 1; set 2 for a double-points round), `phase_locked` (bool).
- **team** — `id`, `name` (case-insensitive unique per game), `recovery_code`,
  `created_at`. No stored total — derived.
- **submission** — `id`, `team_id`, `round_id`, `photo_path`, `submitted_at`.
  One per (team, round); upload replaces if re-submitted before close.
- **mark** — `id`, `team_id`, `question_id`, `transcription` (what the AI read),
  `is_correct` (bool), `score` (numeric; free-form, supports partial credit),
  `confidence` (AI 0–1), `flagged` (AI unsure → host attention), `manually_corrected`
  (host override beats AI), `created_at`. The unit scores are summed (× round bonus)
  to derive team totals.
- **tiebreak** *(only if needed)* — `team_id`, `value` (the numeric guess), plus the
  question/correct value stored on the round/game.

## 7. Categories

Seeded standard set, editable: History, Geography, Science & Nature, Sports, Film & TV,
Music, Art & Literature, Food & Drink, General Knowledge.

## 8. Scoring, marking & grading details

- **Default scoring:** 1 point per question. `point_value` allows exceptions; round
  `bonus_multiplier` allows a double-points round. Partial credit is possible because
  `mark.score` is free-form, not binary.
- **Grading call:** for each submitted sheet, one Claude vision call receives the image +
  the round's questions and expected/alternate answers, and returns structured JSON per
  question: `{question_id, transcription, is_correct, confidence}`. Low confidence →
  `flagged` for host attention. Implementation uses the Anthropic SDK; model + exact
  request shape decided at plan time via the **claude-api** skill.
- **Host marking UI:** per team per question — shows the photo, the transcription, and the
  proposed correct/incorrect. Host can toggle correct/incorrect, set a custom score, and
  **add an accepted alternate** to the question (which can re-grade matching answers).
  `manually_corrected` always wins over the AI.
- **Tiebreaker:** nearest-wins numeric question, used only when the top teams are tied at
  `done`. Closest guess wins (over or under); tied teams answer simultaneously.
- **Export:** at `done`, download results as CSV (teams × rounds, totals).

## 9. Edge cases explicitly handled

- Duplicate team names → rejected (case-insensitive, per game).
- Team joins mid-game → allowed; starts at 0, missed rounds score 0.
- No photo / blurry / two answers for one question → host marks manually via the override
  (free-form score); AI flags low confidence.
- Host fixes a mark after scores "locked" → totals recompute (derived scoring).
- Phone refresh / backgrounding / rejoin → recovery code + polling re-reads state.
- Late submission after close → rejected server-side.
- Author on their own team → questions tagged `author_name`; `answer` never served to
  non-host roles regardless.
- Category imbalance / question shortage → round builder warns the host at draft time.

## 10. Explicitly out of scope (v1)

YAGNI for a fun night with ~5 friends. Schema leaves room where cheap; no UI:

- Picture/music rounds (media field exists; no upload/playback UI yet).
- Jeopardy-style wagers / final-question betting.
- Answer-distribution histograms, animated rank-change leaderboard.
- Swap-marking / self-marking modes (we use AI-proposes-host-confirms only).
- Profanity/duplicate-question filtering.
- Multi-device-per-team concurrent editing (assume one device per team; last-write-wins).
- PWA/offline shell, internationalization, multiple simultaneous games.

## 11. Testing approach

- **Unit:** scoring derivation (incl. corrections cascading, bonus multiplier, partial
  credit), balanced-round builder, grading-response parser (against canned model JSON),
  role-filtered serialization (assert `answer` never leaks to non-host).
- **Integration:** phase transitions, submission accept/reject by phase, team-name
  uniqueness, recovery-code rejoin, missing-submission = 0.
- **Grading:** mock the Anthropic call in tests; one optional live smoke test behind a
  flag. Keep a couple of real handwritten sample photos as fixtures.
- **Manual:** a game-night dry run on the sprite from two phones + the laptop + the TV
  view before the real night.

## 12. Open implementation-time decisions (not blockers)

- Exact Claude model id + request/response schema → resolve via **claude-api** skill.
- Deploy mechanism to the sprite (push files vs. git clone + run script) → pick the
  simpler in the plan.
- Whether a per-round countdown timer is worth it for v1 (leaning no — host closes
  manually) — revisit during ponytail review.
