## Why

This is a once-a-year game: questions are collected from friends over a few
weeks, then the game is run in one sitting at the beach. Contributors need to
come back over those weeks to finish or change their questions, and none of
that data can be lost. The host needs a clear moment to say "submissions are
closed" before game night. The whole thing only ever serves one game at a time,
for one host (Travis) — there is no need for multi-game or multi-host support,
and we explicitly prefer a confident single-purpose system over a flexible one.

## What Changes

- Affirm a **single persistent game** model: all contributions map to the one
  game; data survives weeks of collection and server sleeps with no loss.
- Contributors can **return and edit** their own questions/answers any time
  while submissions are open (persistence of who-they-are is covered by
  `one-submission-per-contributor`).
- The host panel gets a **submission-window control**: open vs closed.
- When submissions are **closed**, contributors can no longer add or edit, but
  all existing data is preserved and used for the game.

Open questions for the research phase (intentionally not decided yet):
- Is the window strictly one-way (open → closed), or can the host reopen it?
- What exactly does a contributor see when they arrive after close (read-only
  view of their questions, or a simple "submissions are closed" message)?
- Should closing submissions be what unlocks round-building on the host side?

## Capabilities

### New Capabilities
- `submission-window`: the open/closed lifecycle of contribution, the host
  control for it, and the single-game persistence guarantees that make weeks-long
  collection safe.

## Impact

- Host panel (new control), contribute screen (respects open/closed), data model
  (single-game persistence — already largely true today). Related:
  `one-submission-per-contributor`, `question-contribution-form`.
