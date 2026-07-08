# Gladys: a real (Fran-esque) voice via ElevenLabs

## Problem

The shipped Gladys voice is the browser Web Speech API driving the OS's stock
voices (Samantha/Victoria) pitched up. It does not, and cannot, sound like Fran
Drescher — Web Speech has no access to a brassy/nasal NY voice. Travis wants her
to actually *sound* the part.

## Requirements

- A genuinely brassy, nasal, New-York-cougar voice on the `/display` screen.
- Use ElevenLabs (Travis has an account) with a **designed archetype** voice
  (voice-design from a text prompt) — NOT a clone of the real Fran Drescher.
- Server-side synthesis; the display plays real audio.
- **Web Speech stays as a graceful fallback** when ElevenLabs isn't configured
  or a synth call fails — the app must still boot and run with no key.
- Boot must NOT require an ElevenLabs key (mirrors `ANTHROPIC_API_KEY`: only
  needed for the feature, not to run).
- No build step, one process, one URL (CLAUDE.md invariants hold).

## Design

**Live endpoint + disk cache** (chosen over pre-generating clips):
- `GET /api/gladys/tts?text=...` → `audio/mpeg`.
- Cache key = `sha1(voice_id + model + text)`; cached file under
  `<uploads>/../gladys-tts/<hash>.mp3` (→ `/data/gladys-tts` on the sprite,
  survives sleeps). First utterance of a line synthesizes + caches; every
  repeat (all the static catchphrases) is an instant file read. The dynamic
  answer read-back synthesizes once per distinct answer string.
- Fully dynamic (handles the answer read-back), gets cheaper each game, no
  build/pre-gen step, no line-bank↔Python duplication.

**Injectable client** (mirrors `app.state.grading_client`):
- `app/tts.py`: `ElevenLabsTTS.synthesize(text) -> bytes` via `httpx` REST
  (`POST /v1/text-to-speech/{voice_id}`, `xi-api-key` header). `make_tts_client()`
  returns an instance iff `ELEVENLABS_API_KEY` + `GLADYS_VOICE_ID` are set, else
  `None`. Tests inject a fake so no key/network is needed.
- `create_app()` sets `app.state.tts_client = make_tts_client()`.

**State flag:** `/api/state` gains `gladys_tts: bool` (client configured?). The
display uses it to choose server-audio vs Web Speech.

**Voice design (one-off):** `scripts/design_gladys_voice.py` calls
`POST /v1/text-to-voice/design` (Fran-archetype `voice_description`, a Gladys
line as sample `text`), then `POST /v1/text-to-voice` with the chosen
`generated_voice_id` → prints the permanent `voice_id`. Run once; set
`GLADYS_VOICE_ID` on the sprite. Not part of the request path.

**Frontend (`gladys.js` + `display.html`):**
- `Gladys.Voice` gains a server-audio path. `serverTTS` flag set from
  `state.gladys_tts` in `driveGladys`. `speak(text)`: if `serverTTS`, play
  `new Audio('/api/gladys/tts?text=' + encodeURIComponent(text))`; on error or
  when off, fall back to Web Speech. One `current` Audio, stopped before the
  next (parity with `speechSynthesis.cancel()`).
- `canSpeak` becomes true when EITHER server TTS or Web Speech is available.
- Toggle button unchanged (the click still unlocks browser autoplay for both
  `Audio.play()` and Web Speech).

## Files

- `app/tts.py` (new) — client + factory.
- `app/main.py` — import, `app.state.tts_client`, `gladys_tts` in `/api/state`,
  `GET /api/gladys/tts` (before the `/` static mount).
- `static/gladys.js` — server-audio path + fallback in `Voice`.
- `static/display.html` — pass `state.gladys_tts` into `driveGladys`.
- `scripts/design_gladys_voice.py` (new) — one-off voice designer.
- `.env.example` — document `ELEVENLABS_API_KEY`, `GLADYS_VOICE_ID`,
  `ELEVENLABS_MODEL`.
- `requirements.txt` — `httpx` already present (test dep); reuse it.
- `tests/test_api_gladys_tts.py` (new) — endpoint behavior with a fake client;
  503 when unconfigured; cache hit skips a second synth; `gladys_tts` flag.

## Test plan

- Unconfigured (no client): `/api/gladys/tts` → 503; `state.gladys_tts` false.
- Configured (fake client): first call synthesizes (client called once) and
  returns `audio/mpeg`; second identical call is served from cache (client NOT
  called again); `state.gladys_tts` true.
- Empty/overlong `text` → 400.
- Full suite stays green with no key (fake injection only).

## Visual/behavior surfaces

`display.html` @ 1920x1080. The change is mostly audio, but verify the toggle
still renders/hides correctly in gladys vs lacey mode and the `💋 Gladys says`
caption still appears (no regressions to the existing UI). Real audio can only
be exercised on the sprite once `GLADYS_VOICE_ID` is set — flagged for Travis to
hear. Local visual round confirms no UI regression + the `<audio>` path fires
(console has no errors, network requests `/api/gladys/tts`).

## Ship

Merge to main (dark factory), `just deploy` to the **main** sprite AND push the
tree to `sum-beach-trivia-ai` (Travis is testing there). `scripts/` changed →
push `scripts/` too. Set `ELEVENLABS_API_KEY` + `GLADYS_VOICE_ID` in each
sprite's `/data/secrets.env`. Verify `state.gladys_tts` true live and one
`/api/gladys/tts` call returns audio.
