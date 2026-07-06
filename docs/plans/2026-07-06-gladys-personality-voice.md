# Gladys gets a personality (+ a voice)

Branch: `feat/gladys-personality`

## Requirement

Give **Gladys**, the AI MC, a late-middle-aged "cougar" comedic persona built on
comedy-movie / sketch / sitcom tropes — specifically **Fran Fine from *The
Nanny*** (Fran Drescher): brassy Queens/Flushing nasal delivery, honking "Hah!"
laugh, Yiddish sprinkles (*bubbeleh, oy, tuchus, meshugganah*), boy-crazy/flirty
warmth, name-drops (Barbra, Bob Barker), vain-but-lovable, calls everyone
"sweetie / doll / darlin'." Blend with campy SNL-cougar forwardness — playful
and PG-13, never creepy or mean. It's a friends' game night.

Then, **if feasible, give her a voice that sounds like Fran the Nanny.**

## Voice feasibility — the honest answer

The repo forbids a build step, a frontend framework, and any external asset
host (CLAUDE.md Anti-Patterns), and the app must boot with no API key. That
leaves exactly one in-constraint option: the **browser Web Speech API**
(`speechSynthesis`), which runs on the display laptop and speaks through the TV.

- It uses the **operating system's** voices — you cannot load "Fran Drescher."
  We can shape a female voice toward nasal/brassy with `pitch`/`rate`, but the
  **timbre is generic**. The Fran personality lands through the **words and
  cadence**, which we control fully, not the voice engine.
- A closer nasal-NY-cougar timbre would need an external paid TTS (ElevenLabs
  et al.) proxied through our own server + audio caching — a new paid API
  dependency, and still not legally "Fran Drescher." That's out of scope for v1
  (noted as an upgrade path in the ship report; the trigger/debounce/toggle
  plumbing built here is the same regardless of TTS backend, so it's not wasted).

**Decision (dark-factory autonomy):** ship Web Speech + killer Fran-cadence
text now; flag the ElevenLabs upgrade path for Travis.

## Design

Personality is **100% client-side** — a line bank + deterministic picker +
a Web Speech controller. **No server, schema, or API changes** (`/api/state`
already exposes `mc_mode`, `phase`, `question_idx`, and — only during
`phase=answers` — `current_round.questions[].answer/answer_items/author_name`,
the one legitimate window answers are client-side; verified via serializers).

Voice + quips live on **`display.html` (the TV) only** — the shared screen.
Not phones (chaos), not the host console (control panel). All Gladys output is
**gated on `state.mc_mode === 'gladys'`**: in Lacey mode a human reads aloud, so
Gladys stays silent and her quips are hidden.

### Files to touch

1. **`static/gladys.js` (new)** — served automatically by the `static/` mount
   (`main.py:838`), zero route changes. Exports a global `Gladys` with:
   - `LINES` — a context-keyed line bank (Fran-cadence), ~8-14 lines each for:
     `lobby`, `round_closed` (pens down), `marking`, `answers` (framing quips),
     `answerLeadIn` (connectives into the spoken answer), `reveal`,
     `final_wager`, `final_open`, `tiebreak`, `done`. (Deliberately **no**
     `round_open` bank — that's silent writing/thinking time.)
   - `pickLine(context, seed)` — hashes `seed` → stable index, so a line is
     **stable across the 2.5s poll repaint** and matches what's spoken
     (same discipline as the existing ticker de-dupe at `display.html:487`).
   - `Voice` — Web Speech controller: async voice-list load
     (`onvoiceschanged`), female-en voice pick, nasal tuning
     (`pitch ≈ 1.5`, `rate ≈ 1.05`), `cancel()` before each `speak()` (fast
     cursor advances don't queue), `enable()/disable()` persisted to
     `localStorage['gladys_voice']`, graceful no-op if unsupported.

2. **`static/display.html`** —
   - `<script src="/gladys.js"></script>`.
   - A fixed **voice toggle** (bottom-right, clear of ticker/prev-qs):
     `🔊 Let Gladys talk` ↔ `🔇 Gladys` — the click both flips the pref and
     satisfies the browser autoplay gesture. Hidden if speech unsupported or
     `mc_mode !== 'gladys'`.
   - A **`#gladys-says` caption** rendered in the relevant per-phase renderers
     (small, tasteful, always shown in gladys mode even with sound off — the
     persona is *present* in text, *audible* on opt-in).
   - Drive speech on **state change only**: a `lastSpokenKey` guard keyed
     `phase:roundId:questionIdx`; **first load primes the key silently** (a
     reload / deploy-reboot doesn't make her re-announce). Speak only when
     `voice enabled && mc_mode==='gladys' && key changed`.
   - `answers`: on-screen caption = framing quip; **spoken** =
     `quip + leadIn + answerText` (answer_items joined; the TV shows the answer
     big for reading, Gladys says it with flair).

3. **`static/host.html`** (light touch, keep the clear `Gladys (AI)` label) —
   - Freshen the Gladys MC-card blurb (`:160`) with a wink of her voice.
   - Freshen the switch-to-Gladys toast (`:766`).

4. **`tests/test_static_gladys.py` (new)** — one guard: `GET /gladys.js` returns
   200 and contains a known catchphrase, locking the wiring. (Line-bank/picker
   logic is vanilla client JS; the repo has no JS runner and won't grow one —
   real verification is the browser round below.)

## Test plan

- `.venv/bin/python -m pytest -q` — full suite green (no server changes, so the
  existing ~N tests are unaffected) + the new served-file guard.
- Browser round exercises `Gladys.pickLine` in the console and confirms the
  voice actually speaks.

## Visual surfaces (mandatory round)

Display = TV, **1920x1080**. Drive a seeded game through phases via the phase
endpoint and screenshot + **read** each:

- **lobby** — Gladys welcome caption present, legible, not colliding with QR /
  team chips / voice button.
- **round_open** — confirm **no** Gladys caption (writing time is quiet).
- **round_closed** (pens down) — pens-down caption under the red banner, no
  overlap.
- **marking** — "hold your horses" caption.
- **answers** — the money state: framing caption under the hero answer, author
  credit intact, prev-qs rail on the left not overlapping the caption; walk the
  cursor (`/api/host/question`) and confirm the caption changes per question and
  is stable across polls (screenshot twice at the same cursor).
- **reveal / final_wager / done** — captions fit around scores/podium.
- **Voice toggle**: default off, both states render, positioned clear of the
  ticker; hidden when `mc_mode=lacey` (flip via `/api/host/mc-mode`).
- **Audio check**: enable the toggle, advance the answers cursor, confirm Gladys
  actually speaks (report whether the sandbox browser can produce audio; if not,
  flag for Travis to hear on the real display).
- Awkward state: longest realistic answer + author name — caption wraps, doesn't
  shove the hero answer or overflow.

## Ship

Full suite → merge to main (dark factory: `gh auth switch --user tarvy` → push →
switch back) → `just deploy` (full tree) → verify `/api/state` healthy and
`/gladys.js` served live. Report screenshots (or sandbox caveat), the audio
result, and the ElevenLabs upgrade path.
