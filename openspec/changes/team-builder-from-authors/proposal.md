## Why

Teams aren't known until game night. When teams form at the beach, it's natural
to build a team from the people who actually contributed questions — so the play
screen should let a team name itself and pick its members from the list of
question authors. It also has to handle real life: someone who didn't contribute
still plays, and people swap teams as the night shakes out, so membership must be
editable at any time.

## What Changes

- On the play screen, forming a team means: enter a **team name**, then **select
  members from the list of question-bank authors**.
- A team can always **manually add a teammate** who isn't in the author list.
- Team membership is **editable at any point during play**.

Open questions for the research phase (intentionally not decided yet):
- Whether one author can be on multiple teams or is exclusive once picked (and
  whether the UI should show who's already taken).
- How this interacts with the existing team join/recovery flow.
- Whether the host can also adjust team membership from the host panel.

## Capabilities

### New Capabilities
- `team-management`: building a team by name + members chosen from authors, with
  manual additions and editable membership during play.

## Impact

- Play screen (team builder), data model (team membership, link to contributors),
  possibly host panel. Depends on author data from
  `question-contribution-form` / `one-submission-per-contributor`.
