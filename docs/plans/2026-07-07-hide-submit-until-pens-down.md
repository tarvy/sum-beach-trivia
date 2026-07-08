# Hide the submit prompt until pens-down

## Requirement

On the player screen (`play.html`), while a normal round is **open**
(`round_open`) teams are still writing on paper — the "Snap your answer sheet /
Submit answers" prompt should NOT be visible. It should appear only once the
host calls **pens down** (`round_closed`), matching the big-screen display which
says "write your answers on paper" while open and "PENS DOWN — hand in your
sheets!" when closed.

The final round (`final_open`) has no separate closed phase — the host goes
`final_open → marking` directly — so the submit prompt must stay available
during `final_open`, otherwise teams could never hand in the final sheet.

## Rule

The `round` panel is shown for `round_open`, `round_closed`, and `final_open`.
Hide `#submit-panel` **only when `phase === 'round_open'`**. Show it in
`round_closed` and `final_open`.

## Files to touch

- `static/play.html` — in `renderRound(round, phase)`, toggle `#submit-panel`
  hidden based on phase. No backend change (`SUBMIT_PHASES` still guards the
  API; this is purely what the player sees).

## Implementation steps

1. In `renderRound`, after computing `closed`, hide/show `#submit-panel`:
   `submitPanel.classList.toggle('hidden', phase === 'round_open')`.

## Test plan

- Full suite green (`.venv/bin/python -m pytest -q`) — no backend change, but
  confirm nothing regressed.

## Visual surfaces

`play.html` @ **390x844** (phone), team joined, in each phase the round panel
renders:
- `round_open` — questions list visible, **no** submit card. "Round open"
  eyebrow, rank card below. Looks right = clean list, no orphaned spacing where
  the card was.
- `round_closed` — "Pens down!" eyebrow, submit card visible with the
  "Pens down — get your photo in!" heading + file input + Submit button.
- `final_open` — submit card visible (final round handed in live).
- Awkward state: longest realistic question text wraps cleanly in the list.
