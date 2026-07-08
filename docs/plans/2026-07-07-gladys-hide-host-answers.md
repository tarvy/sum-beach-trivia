# Gladys mode: hide upcoming answers from the host

## Request
Once a game is **started** in **Gladys (AI) mode**, the host should not be able to see:
- the **manage-question answers** (question-bank answer column), or
- the **final round question**.

Additionally, **no tiebreak question** should be visible unless we're in a
**sudden-death scenario**.

## Interpretation / rationale
In Gladys mode the AI owns grading + read-back, so the host is effectively a
player. The things worth hiding are *upcoming* answers (a real cheat vector):
- **Bank answers** — every upcoming round's answers.
- **Final round question + answers** — upcoming.
- **Tiebreak question** — upcoming, and only ever relevant at sudden death.

The **marking console keeps its answers**: it only ever shows the *just-finished*
round (not a cheat vector for the current round) and the host legitimately needs
the answer to hand-mark when Gladys's grading fails (CLAUDE.md: gladys grading
exception → MC marks by hand). Removing it would be a functional regression.

Gate condition (host + bank): `mc_mode === 'gladys' && phase !== 'draft'`.
During `draft` (setup) everything stays visible — that's where the host writes
the final. In **Lacey mode** nothing changes (the human MC needs answers).

The tiebreak rule is stated generally ("no tiebreak question visible unless
sudden death"), so it applies in **all modes**: hide the tiebreak picker fold
unless `phase === 'tiebreak'` OR the top-two teams are currently tied at the
final-reveal moment (the existing sudden-death trigger the "Tiebreak" side
button already uses). This keeps the side-button flow working (when tied at
final reveal, the fold un-hides so it can be opened).

## Files (frontend only — no backend changes)
- `static/host.html`
  - `renderRun()`: hide `#final-details` when Gladys+started.
  - `renderRun()`: hide `#tb-details` unless sudden death (all modes).
- `static/bank.html`
  - When Gladys+started: force answers hidden and hide the "Show answers"
    toggle. Add a light `/api/state` poll so it reacts if the game starts /
    mode flips while the bank page is open.

No backend edits — `mc_mode` + `phase` are already in `/api/state`; this is a
UI-visibility change, consistent with the existing (frontend-only) bank
"hide answers until start" behavior. The host already holds the host key and
full API access; this is not a hard security boundary, just not shoving answers
in the host's face while they play.

## Test plan
- `.venv/bin/python -m pytest -q` — pure frontend change; suite must stay green.

## Visual surfaces (Phase 3, scratch DB, laptop 1280x800)
Seed a game (2–3 authors, a final, teams), then walk phases:
1. **bank.html**, Gladys + `lobby`: answer column shows `•••`, no "Show answers"
   button. Then flip to Lacey → answers + toggle return.
2. **host.html**, Gladys + `lobby`: `#final-details` fold gone; `#tb-details`
   gone. Lacey + `lobby`: both folds present.
3. **host.html**, marking phase (Gladys): marking console still shows the
   correct answer (unchanged).
4. **Sudden death**: at final `reveal` with top-two tied → `#tb-details`
   appears and the "Tiebreak" side button flow still opens it. `phase=tiebreak`
   → `#tb-details` visible.
"Looks right" = folds cleanly absent (no empty gap), no console errors,
leaderboard/stepper unaffected.
