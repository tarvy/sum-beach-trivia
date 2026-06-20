## Why

The contribution form is the main thing friends interact with for weeks before
the trip, so it should be simple and unambiguous: a clear "write your questions"
flow that guarantees we get enough good, well-formed questions. We also want to
record who wrote each question — partly for data, and partly because revealing
the author after each round's answers are in is a fun payoff during the game.

## What Changes

- The form requires **3 questions** and allows up to **2 more optional**
  (5 maximum), presented as one consistent sub-form per question.
- Each question sub-form asks **Question**, **Answer**, and **Category** (chosen
  from the existing standard category list). For every question the contributor
  provides, all three fields are **required** for the form to validate.
- Each question records its **author**.
- After a round's answers have been given/graded, the **author of each question
  in that round is revealed** — it's more fun that way.

Open questions for the research phase (intentionally not decided yet):
- Where the author reveal surfaces: big-screen display, host panel, players'
  phones, or several of these.
- Whether categories can repeat across a contributor's own questions (assume yes
  unless decided otherwise).
- Exact validation messaging/UX (per-field vs per-form).

## Capabilities

### New Capabilities
- `question-contribution`: the structure and validation of the contribute form
  (3 required + 2 optional; Question/Answer/Category each required) and author
  attribution, including revealing the author after each round.

## Impact

- Contribute screen (form), data model (author per question), and gameplay
  reveal (host/display during the reveal phase). Builds on
  `one-submission-per-contributor`; author data feeds `team-builder-from-authors`.
