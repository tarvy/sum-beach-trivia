# Host screen — quick screen launcher

## Requirement

On the host screen, give the host quick controls to open the other screens
(Display, Play, Contribute, Bank) in new browser tabs. Motivated by game night:
once the game starts the host wants to pop open the TV Display and preview the
player Play view without hunting for URLs.

## Approach

Add a compact **"Open a screen"** card to the run-stage right column, directly
below the MC-mode mini card. Four anchors styled as small buttons, each with
`target="_blank" rel="noopener"`:

- 📺 **Display** — TV / big screen
- 📸 **Play** — player phone view
- ✏️ **Contribute** — question submission
- 🗂️ **Bank** — question-bank manager

Plain anchors — no JS, no state, no host key needed (Display/Play/Contribute are
public; Bank self-gates on its own stored host key). This is a pure static addition.

Setup stage already links to the bank inline; the launcher is a run-stage
convenience so it lives in the run stage only (matches the "when the host starts
a game" ask).

## Files to touch

- `static/host.html` — add the card markup in the right column (`.stack--lg`
  after `#mc-mini`) and a small `.screens-grid` style block.

## Test plan

No backend change → no new pytest needed. Run the full suite to confirm nothing
regressed. Visual round is the real check.

## Visual surfaces

- `host.html` @ **1280x800** (laptop), run stage (e.g. phase=`round_open`):
  the new "Open a screen" card sits below MC mode in the right column; four
  buttons align in a tidy 2-col grid, emoji + label share a baseline, no
  overflow, spacing matches neighboring cards. Confirm each link opens the
  right page in a new tab.
- Narrow width (~700px) where the grid collapses to one column: buttons stay
  full-width and readable, no horizontal scroll.
