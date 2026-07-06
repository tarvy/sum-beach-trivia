# Gladys (AI) relabel + de-emphasize Lacey default

Date: 2026-07-06
Branch: `feat/gladys-ai-relabel`

## Context / why

Travis is spinning up a second sprite to do more testing on the **AI (Gladys)**
MC mode — that mode is the current focus. This change walks back the UI's
"Lacey is recommended" framing and standardizes the AI's name to **Gladys**.

## Requirements

1. Remove the `recommended` badge from the "Lacey in Charge" MC card.
2. Rename the AI MC card from **"Gladys the AI MILF"** to **"Gladys (AI)"**.
3. Everywhere in the app, when Gladys mode is on, refer to the AI as **"Gladys"**
   (not "the AI", not "Gladys the AI MILF").

## Files to touch

- `static/host.html`
  - L155: delete `<span class="badge badge--amber">recommended</span>` (Lacey card).
  - L160: `Gladys the AI MILF` → `Gladys (AI)`.
  - L161: card description "…the AI transcribes and proposes marks…" →
    "…Gladys transcribes and proposes marks…".
  - L~1311: remove the first-load auto-default that forces `mc_mode` to `lacey`.
    Rationale: it's per-origin localStorage, so on the brand-new AI-testing
    sprite it would fire and select Lacey on the host's first load — the exact
    opposite of the stated goal. Removing it lets the **DB default (`gladys`)**
    stand, which CLAUDE.md already documents as the default. Easy to revert if
    Travis wants Lacey-first back.
- `CLAUDE.md`
  - L24: update the "Gladys the AI MILF" label reference to "Gladys (AI)" so the
    doc matches the UI.

## Scope notes / non-goals

- Player-facing screens (`play.html`, `display.html`, `contribute.html`) do NOT
  name the AI — verified by grep. `play.html`'s gladys-mode submit copy says
  "Snap your answer sheet" with no "AI" mention. Nothing to change there.
- The in-game mini MC toggle already labels the button just "Gladys" — fine.
- The mode toast already says "Gladys has the con" — fine.
- No schema/API changes. `game.mc_mode` values (`lacey`/`gladys`) are internal
  identifiers, unchanged. This is copy + one client-default removal only.

## Test plan

- `.venv/bin/python -m pytest -q` — full suite must stay green. No server
  behavior changes; `test_api_mc_mode.py::test_default_mode_is_gladys_in_state`
  already asserts the server default is `gladys` (unaffected). The removed
  auto-default is client-side JS, not covered by pytest.

## Visual surfaces

- **host.html @ 1280x800**, `draft`/setup phase — the "2 · Who's your MC?" card:
  - Lacey card: NO badge; "Lacey in Charge" title now sits at the card top,
    baseline-aligned with the Gladys title (previously the badge pushed Lacey's
    title down — removing it should improve alignment, watch for the opposite).
  - Gladys card: title reads "Gladys (AI)"; description reads
    "Teams snap a photo, Gladys transcribes and proposes marks, the MC just
    confirms." — check it doesn't over-wrap or overflow the pink card.
  - Both cards equal height, consistent gap/padding (grid `1fr 1fr`).
  - On a FRESH scratch game (mc_mode=gladys), confirm the Gladys card renders
    **selected** (pink) on load and is NOT auto-flipped to Lacey.
- "Looks right" = two tidy top-aligned cards, no badge on Lacey, correct titles,
  description fully contained, Gladys selected by default.
