# Round fairness: random selection, one-per-category, team balancing

Date: 2026-07-06
Branch: `feat/gladys-ai-relabel` (follow-on to the Gladys relabel)

## Done in this pass

1. **Random selection (was first-N).** `rounds.build_rounds()` now keeps a
   RANDOM `game.questions_per_person` of each contributor's questions instead of
   their first N (submission order). Contributors who submitted ≤N keep all of
   theirs; everyone is still guaranteed ≥1 in. A `rng` param (seeded in tests)
   keeps it deterministic where needed. Consequence: a rebuild reshuffles which
   of an over-cap contributor's questions are used (shaping stays deterministic
   given the selected set).

2. **One question per category per contributor.** Enforced server-side in
   `models._assert_category_unused` (add / edit / set paths; no-op for bank/host
   questions). `contribute.html` now drops already-used categories from the
   picker (an in-progress edit keeps its own category selectable).

Tests: full suite green (135). Round tests assert count/subset invariants with a
seeded rng; contribute tests use distinct categories + explicit rejection cases.

Not yet shipped — push + `just deploy` are blocked by the harness permission
guard (pending Travis's authorization; see the session report).

## Open — needs Travis's decision (team fairness)

### The core tension
Rounds build at **setup** (`Start the game`, draft→lobby) — BEFORE teams exist.
Teams form at **game night** when phones tap the team list (`POST /api/teams`).
Contributors (browser tokens, days earlier) are a separate identity; the
`team_member.contributor_id` link exists in the schema but nothing populates it
today (no wired-up team-builder). So there is currently **no mapping from
"who authored a question" to "which team they're on."** Per-team fairness needs
that mapping, which means either binding contributors→teams up front OR moving
the round build to after teams are set.

### Decisions required
1. **Approach / build timing** — roster + rebuild at lobby (host assigns each
   contributor to a team during team-building, rounds rebuild once teams are
   set) vs. auto-link at join + rebuild vs. skip per-team balancing (only
   guarantee even-per-person, already done).
2. **Lopsided teams (4 vs 3 contributors)** — cap every team's authored count to
   the smallest team's total and randomly bench the surplus vs. warn the host
   only vs. don't equalize.
3. **Even-per-person** — cap effective N to the smallest submitter so everyone
   contributes the same number, vs. keep N and warn if someone submitted fewer.

### Protocol answer (concentrated categories — Travis's question)
Current v2: rounds are per-category, target 5. If everyone piles into a few
categories, those become big rounds that split evenly ("History", "History II");
other categories get none. Thin categories (<5) top up from same-category bank,
else pool into "Mixed Bag" (padded from any bank if still <3). Every contributor
is still guaranteed ≥1. So concentration → a few large category rounds + a Mixed
Bag, and "even per person" is guaranteed by the per-person cap, independent of
the 5-per-round shaping target.
