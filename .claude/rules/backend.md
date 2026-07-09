---
paths:
  - "app/**/*.py"
---

# Backend (app/)

CLAUDE.md's Anti-Patterns are canonical. These are the failure stories behind
them and the checks that keep them fixed.

## Connection hygiene — the worst outage class

Both production lockups were connection bugs: a shared connection crossing
threads (SIGBUS, process crash — `370c779`), and a failed duplicate-INSERT
whose transaction was never rolled back, wedging SQLite's write lock so every
host action 500'd "database is locked" mid-game (`54f4571`). Every
write-failure path — duplicate key, stale FK, unknown id — must roll back
before returning its 4xx. `tests/test_connection_hygiene.py` asserts the
connection is clean after failures; extend it when adding a write path.

## Phase boundaries span screens

Phase gating lives in `main.py`'s sets (e.g. `SUBMIT_PHASES`) AND in what each
screen chooses to show. Three separate bugs came from touching one side only:
pens-down locked unsubmitted teams out of handing in their sheet (`bd61091`),
the submit prompt appeared while pens were still up (`517776f`), and filler
questions counted as "submitted" in the setup header (`f07fb3f`). When you
move a phase boundary, walk /play, /host, and /display's view of that phase
before calling it done.

## Public-payload privacy gets a regression test

Any field added to `/api/state` or a round payload goes through
`serializers.public_question` vs `host_question` deliberately. When exposing
something new at a phase, add the test asserting it is ABSENT everywhere
else — that's how the tiebreak-value and author-name boundaries stay honest.

## Grading must never lose a submission

The photo is saved before grading; a grading exception returns
`{ok: true, graded: false}` so Lacey can mark by hand — keep that shape. Use
`client.messages.parse(output_format=SheetGrade)`: hand-feeding a raw
`model_json_schema()` omits `additionalProperties: false` and the API 400s
every call (`6376187`) — invisible to tests because grading is mocked. After
touching grading, verify one real photo submission on the sprite.

## Schema

- Change `SCHEMA` in `db.py` AND add the idempotent `init_db()` migration —
  the sprite's `/data/trivia.db` upgrades in place on boot.
- `team_member` and team `recovery_code` are vestigial: the roster/rejoin
  features were removed (`6b01d7f`), the columns kept. Don't build on them.
  (Contributor `recovery_code` IS still live.)
