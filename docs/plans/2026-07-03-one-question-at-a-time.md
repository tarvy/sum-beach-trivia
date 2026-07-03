# One question at a time (host-driven)

Travis: questions are asked ONE at a time; Lacey advances from the host page.
A "loose" timer per question (default 60s, settable in-game) — visual cue only,
never auto-advances. TV shows the single current question big; previous
questions of the round tuck into the upper-left; after round 1 a stock-style
ticker of standings runs along the bottom.

## State (game table — persisted, refresh/crash-safe)
- `current_question_idx` INT DEFAULT 0 — live question within current round
- `question_seconds` INT DEFAULT 60 — loose timer length
- `question_opened_at` TEXT — server timestamp; elapsed computed in SQL

## API
- `/api/state` += `question_idx`, `question_seconds`, `question_elapsed`;
  `current_round` += `question_count`, `round_number`, `round_count` (position
  among non-final rounds; final → number null)
- **Anti-spoiler**: during round_open/round_closed the public round payload
  only includes questions up to the current idx (future questions never reach
  any client — the play screen was leaking the whole round). Full list at reveal.
- `POST /api/host/question` {action: next|prev} — clamped, restamps opened_at;
  409 outside round_open
- phase → round_open or final_open: idx reset to 0 + opened_at stamped
- `POST /api/host/settings` += optional `question_seconds` (10–600)

## Host (Lacey drives)
- round_open primary action = "Next question →" until the last, then "Pens
  down"; status shows "Q n/M: <text>"; small "← back one" (loose!)
- "Seconds per question" input in the Rounds & questions panel

## Display
- round_open/closed: eyebrow "QUESTION n OF M", current question hero-sized,
  loose countdown under it (amber <10s, TIME! at 0, nothing blocks),
  previous questions small in the upper-left quadrant
- bottom ticker (marquee) with standings when round_number > 1 or final

## Visual surfaces
- display.html at 1920x1080: round_open q1 (no prev list, no ticker on round 1),
  q3 (prev list), round 2 (ticker), pens-down, reveal
- host.html 1280x800: action card during round_open
- play.html 390x844: partial question list numbering
- Caveat: agent-browser is DNS-dead in this sandbox — flag for eyeball pass.
