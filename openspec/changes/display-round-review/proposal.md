## Why

On the big screen (the read-only display for the room/TV), navigation behaves
oddly when the game is in the "questions being written" state — there's no clean
way to move/"nav back," and it feels off. The display is meant to passively
follow the game, so any navigation that lets a viewer get to a wrong or stuck
screen is a bug in feel, even if it's not breaking the game.

## What Changes

- Define the **intended big-screen behavior** during the writing phase: the
  display shows the active round's questions and a clear "writing in progress"
  cue, and it follows the host's game state automatically.
- Remove or correct the **odd "nav back" behavior** so a viewer can't land on a
  confusing/stuck state on the display.

Open questions for the research phase (intentionally not decided yet) — this
ticket is partly an investigation:
- What "nav back" concretely refers to here: browser back button behavior, an
  in-app control, or the wish to review a *previous* round's questions on the
  big screen.
- Whether the display should ever support intentional review (e.g. host-driven
  "show last round" recap) versus being strictly auto-follow.
- Reproduction details of the odd behavior in the `round_open` (writing) state.

## Capabilities

### New Capabilities
- `display-screen`: the big-screen read-only experience and its navigation
  behavior across game phases, especially while questions are being written.

## Impact

- Display screen only (read-only). No change to scoring or game data. Likely
  small once the desired behavior is pinned down in research.
