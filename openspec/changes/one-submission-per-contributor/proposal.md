## Why

Questions are contributed by individual people, and teams aren't known until
right before game night. So contribution must be anchored to a **person**, not a
team. Each person should own exactly one set of questions for the game — not be
able to accidentally create a second set on a return visit, and not have their
work split across duplicate identities. This keeps the question bank clean and
makes the later "pick your teammates from the list of authors" flow reliable.

## What Changes

- Contribution is keyed to an **individual contributor identity**, established by
  the name they enter plus a persisted browser identity so return visits resolve
  to the same person.
- Each contributor has **exactly one submission set**; returning edits that set
  rather than creating a new one.
- The system avoids duplicate author records for the same person.

Open questions for the research phase (intentionally not decided yet):
- How to handle a name collision in a small known friend group (block the second
  use? warn? this is ~a dozen people who know each other).
- Recovery if someone clears their browser / switches devices — e.g. a personal
  recovery link/code, or re-claim by name. (Pairs with editable-submissions.)
- Whether the host can view/merge/reassign contributors if a duplicate slips in.

## Capabilities

### New Capabilities
- `contributor-identity`: how an individual contributor is identified, made
  persistent across visits, and constrained to a single submission set.

## Impact

- Contribute screen, data model (contributor identity). Tightly related to
  `editable-submissions-and-close` (return-to-edit) and
  `question-contribution-form` (the set they own); feeds
  `team-builder-from-authors` (author list) and author reveal.
