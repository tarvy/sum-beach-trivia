# Marking console: duplicate question nav below the team rows

## Requirement

On a phone, the MC marks 4+ teams top-to-bottom and then has to scroll back
up to find "Next →" (Travis screenshot, 2026-07-07, beta sprite). Add a
second Prev / Q-counter / Next row directly under the last team's
right/wrong row so the thumb never leaves the bottom of the list.

## Files

- `static/host.html` — `renderConsole()` markup + the `mk-console` click
  handler + `paintQuestionChip()`.

## Implementation

1. Switch nav matching from ids to classes: buttons get `mk-prev`/`mk-next`
   as classes; the delegated click handler matches `.closest('.mk-prev')` /
   `.closest('.mk-next')`.
2. Render the same cluster row (Prev / "Q x of y" / marked-chip / Next)
   twice: once above the question, once between `#mk-teams` and the reload
   button. Chips get class `mk-qmarked`; `paintQuestionChip()` updates all
   via `querySelectorAll`.
3. No backend change; no schema change.

## Test plan

- Full pytest suite (no API change — must stay green).
- Existing behavior via visual round; there are no JS unit tests in repo.

## Visual surfaces

- `host.html` marking console, phase=marking, 4 teams, mid-round question:
  verify at **390x844** (Travis is driving this from a phone even though
  host.html's canonical viewport is laptop) AND **1280x800**.
- "Looks right": bottom nav row identical in style to the top row; sits
  below the last team row with normal stack spacing; both counters/chips
  stay in sync after tapping bottom-Next; Prev disabled on Q1, Next disabled
  on last Q in both rows; touch targets ≥44px; no horizontal scroll at 390px.
- Awkward states: first question (Prev disabled), last question (Next
  disabled), multi-item question (number inputs instead of buttons).
