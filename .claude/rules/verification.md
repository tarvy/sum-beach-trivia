# Verifying Work

Every check here proves one layer and vouches for nothing else. Most bugs that
shipped in this repo passed the layer *below* the one that would have caught
them. Pick checks by what the change actually touches — then run all that apply.

## The ladder — what each check proves

**`just test` (pytest)** proves API logic: phase gating, scoring, serializers,
round building. Grading is ALWAYS mocked (`app.state.grading_client`), so a
green suite says nothing about the real Anthropic call — the structured-output
schema bug (`6376187`) 400'd every real grading call while all tests passed.

**curl** proves endpoint behavior and is the right tool for *seeding* state
(create questions, build rounds, flip phases). It cannot see the DOM. The join
flow that stored the literal string `"undefined"` in localStorage (`6b01d7f`)
and the pens-down panel overlap that shipped "never visually checked"
(`614d62f`) were both invisible to curl and pytest. Passing curl checks on a
change that includes JS/HTML/CSS is NOT verification of that change.

**agent-browser** proves rendering and client JS — the only check that catches
wrapping labels, misalignment, dead buttons, console errors, and localStorage
rehydration. Any change touching `static/` gets the feature-delivery skill's
visual round: screenshot every affected screen at its real viewport
(play/contribute 390x844, host/bank 1280x800, display 1920x1080) and actually
read the screenshots. Interact, don't just render: click the primary action,
reload the page, confirm identity survives the reload.

**The live sprite** proves deploy integration and HTTPS-only flows: QR join,
phone camera capture, real grading calls, migrations against the real
`/data/trivia.db`. Localhost cannot exercise any of these.

## Definition of done

1. Full suite green (`just test`).
2. UI-touching change → visual round done, screenshots read, defects fixed
   (or the sandbox caveat stated explicitly — never silently skipped).
3. After `just deploy`: `curl -s <sprite>/api/state` returns healthy JSON
   (the gateway can 502 for ~30-60s after restart — retry before digging),
   then spot-check the changed surface on the sprite itself. Both post-deploy
   display bugs — the TV rendering the old UI (`aca0e8c`) and the QR encoding
   a LAN IP (`0dab29e`) — would have been caught by one screenshot of the
   live display page.
4. Touched grading? Verify one real photo submission on the sprite; mocks
   can't catch API-contract violations.

## Rules

- Local verification runs on a scratch DB (`TRIVIA_DB=/tmp/...`), never the
  repo's `trivia.db`. Never seed junk data into the live sprite while a real
  contribution window is open — check `submissions_open` first.
- Verified means observed: report what you actually saw (screenshot, JSON,
  test count), not what the diff was supposed to do.
