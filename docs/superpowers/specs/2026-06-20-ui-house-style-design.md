# UI House Style via Visual Kit Token Pipeline

## Goal

Reskin all 5 trivia screens (index, play, host, display, contribute) to the
house style — the Visual Kit / Gumroad system (hot pink + yellow, hard black
borders, hard offset shadows, bold display type on cream/white) — and wire it
to the visual-kit token pipeline so future palette swaps propagate with no
markup edits.

## Context

- 5 static HTML pages share one `static/app.css`.
- Page JS keys off element IDs and `.hidden` only — never off styling classes.
  So a CSS-level reskin needs zero JS or markup-structure changes.
- House style source: `~/Dev/visual-kit/` (tokens + `build_tokens.py`), surfaced
  through the `visual-artifact` skill at `~/.claude/skills/visual-artifact/`.
- A first-pass var-remap reskin already landed (hardcoded Gumroad hexes in
  `app.css`). This spec upgrades it to the token pipeline and verifies the
  data-heavy views the first pass never rendered.

## Approach

Token source of truth lives in `theme.css`; `app.css` is a thin adapter that
references those tokens. No markup migration to `.visual-kit-*` classes — the
app keeps its own component vocabulary (`.btn`, `.card`, `.phase-strip`,
`.lb-table`, `.mark-panel`, `.display-*`).

### 1. theme.css as token source

- Copy visual-kit's generated `theme.css` (`--visual-kit-*` custom properties)
  to `static/theme.css`.
- Link it **before** `app.css` in all 5 pages: `<link rel="stylesheet" href="/theme.css">`.
- Reskin path: edit `~/Dev/visual-kit/tokens/theme.config.json` (swap preset or
  override roles) → `python3 ~/Dev/visual-kit/tokens/build_tokens.py` → recopy
  the regenerated `theme.css` to `static/`. Never hand-edit `static/theme.css`.

### 2. app.css adapter

- `:root` aliases the app's legacy var names to tokens instead of hardcoding:
  `--brand: var(--visual-kit-brand)`, `--accent: var(--visual-kit-accent)`,
  `--accent-2: var(--visual-kit-success)`, `--ground: var(--visual-kit-surface-subtle)`,
  `--ground-2: var(--visual-kit-surface)`, `--ground-3: var(--visual-kit-surface-inset)`,
  `--ink: var(--visual-kit-ink)`, `--ink-soft: var(--visual-kit-ink-soft)`,
  `--text-dim: var(--visual-kit-muted)`, `--border-subtle: var(--visual-kit-border-subtle)`,
  `--danger: var(--visual-kit-danger)`, `--success: var(--visual-kit-success)`,
  shadows → `var(--visual-kit-shadow*)`, radii → `var(--visual-kit-radius*)`,
  fonts → `var(--visual-kit-font-*)`.
- Component rules (`.btn`, `.card`, `.eyebrow`, `.nav`, inputs, `.lb-table`,
  `.mark-panel`, `.hero*`, `.display-*`, `.steps`, etc.) already read the legacy
  aliases — unchanged.
- The inline `<style>` patches in `display.html`/`host.html` reference legacy
  vars too — unchanged.

### 3. Fonts

- Keep the Google Fonts `@import` in `app.css` (Space Grotesk / Inter /
  JetBrains Mono). The kit's `--visual-kit-font-display` is `Mabry Pro`
  (commercial, no webfont) with `Space Grotesk` as its declared fallback, so
  landing on Space Grotesk is faithful to the system.

### 4. Display screen

- Light, same single token set as every other page. No dark preset. Already
  verified high-contrast and projector-readable.

## Verification

Empty/initial states already verified for all 5 pages. The gap is data-heavy
views. Seed a game and screenshot with real content:

- **play**: open round (question list `.q-item`), wager slider `.wager-display`,
  tiebreak input, own-rank panel.
- **host**: marking panel `.mark-panel` / `.mark-row` with a submission, phase
  controls, `.section-title`.
- **display**: lobby team chips, round question list `.display-q-item`,
  leaderboard `.lb-display-row` with teams.

Fix any contrast/border/legibility issues the seeded states expose (e.g. accent
fills used as text on light surfaces). Re-screenshot after fixes.

## Out of scope

- Migrating markup to `.visual-kit-*` component classes.
- Any JS / API / game-logic change.
- Self-hosting `Mabry Pro` or other commercial fonts.

## Files

- `static/theme.css` — new, copied from visual-kit (regenerated, not hand-edited).
- `static/app.css` — `:root` rewritten to reference tokens; component rules unchanged.
- `static/{index,play,host,display,contribute}.html` — one `<link>` line each.
- Plus any fixes surfaced by seeded-state verification.
