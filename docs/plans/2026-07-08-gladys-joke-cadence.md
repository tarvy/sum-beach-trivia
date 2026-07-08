# Gladys Joke Cadence

## Requirements

- Reduce repeated em-dash joke shapes in Gladys's on-screen and spoken lines.
- Keep Gladys original: sharp, warm, showbiz-roast energy without copying or directly imitating any TV show's lines.
- Make the answer read-back lines especially punchier, since they appear under individual questions.
- Preserve the existing stable picker behavior so captions and spoken audio stay in sync.

## Files To Touch

- `static/gladys.js`
- Add focused tests if there is already a lightweight JavaScript test path; otherwise verify with the Python suite and visual check.

## Implementation Steps

1. Rewrite the Gladys personality note to describe original voice traits and cadence constraints.
2. Refresh the line banks with varied sentence shapes, especially `answers`, `answerLeadIn`, and state-transition lines.
3. Add a tiny dev-facing cadence check that can be called manually to catch overuse of long dash constructions.
4. Verify display rendering in the `answers` phase at TV size.

## Test Plan

- Run the full test suite with `just test`.
- Manually inspect the line bank for repeated dash-separated constructions.

## Visual Surfaces

- `display.html` at `1920x1080`, `answers` phase.
- Looks right means the "Gladys says" caption still appears under the answer content, long jokes wrap cleanly, and the voice toggle remains anchored in the top-right.
