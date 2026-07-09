---
paths:
  - "static/**"
---

# Frontend (static/*.html)

`host.html` and `display.html` are the two most-fixed files in this repo, and
nearly every fix was a rendering defect one screenshot would have caught. Any
change here gets the feature-delivery skill's visual round — see
`.claude/rules/verification.md` for what agent-browser alone proves.

## Layout traps (each broke production once)

- A wrapping label grows its box and sinks siblings in a center-aligned flex
  row (`330d24e` — bank's "Also accept" input sat below its row). Labels grow
  AWAY from the content they label; verify at the width where wrap happens.
- `position:absolute` collides at phone widths (`892010b` — the back arrow
  landed on the progress stepper). Prefer flow layout.
- `flex-basis:auto` sizes columns to their label text, so centered content
  drifts (`cb7f245`). Give stepper-like columns an explicit basis.
- The app forces light mode (`e0928db`) — mobile auto-dark repainted the cream
  theme. Don't add colors that assume a scheme.

## localStorage identity discipline

- Read the EXACT response key. The join handler once read `d.id` where the API
  returns `team_id`, storing the string `"undefined"` — players could never
  leave the join panel and reloads re-asked for a team (`6b01d7f`).
- Revalidate stored identity against the server on boot (team against
  `GET /api/teams`, host key against a host endpoint). A failed verify is a
  failure: clear the stale value and show the locked/join state. Never treat a
  fetch error as success — that's how "anyone can host" shipped (`c955e6c`).
- Reload-survival is part of any identity change's verification:
  act → reload → still in the same state.

## Display screen

- The TV tab polls data forever but only reloads its own HTML when the boot
  marker in `/api/state` changes (`aca0e8c`). Structural changes to
  display.html are invisible on an already-open TV until that fires — verify
  post-deploy on the sprite, not just locally.
- Everything the display renders is public. Answers, authors, and tiebreak
  values appear only in their exact phase; when in doubt re-read the
  anti-spoiler rules in CLAUDE.md before adding a field to a display payload.
