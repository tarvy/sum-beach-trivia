# Question Bank

Filler questions for round-building come from an external source, imported into
the `question` table with `source='bank'`. The host (MC) can also add her own
via `POST /api/host/bank-question` (`source='host'`) or the `/bank.html` page.

## Source: The Trivia API (the-trivia-api.com)

**The pick.** Evaluated 2026-07-03 against C-1's bar: bar-trivia style, active
maintenance, license compatible with a private friends' game.

Why it won:

- **Only candidate whose categories map 1:1 onto all 9 of our standard
  categories** — including Food & Drink, which OpenTDB and the GitHub dumps
  simply don't have. Mapping: `history→History`, `geography→Geography`,
  `science→Science & Nature`, `sport_and_leisure→Sports`, `film_and_tv→Film &
  TV`, `music→Music`, `arts_and_literature→Art & Literature`,
  `food_and_drink→Food & Drink`, `general_knowledge→General Knowledge`
  (`society_and_culture` is deliberately unmapped/skipped).
- **Curated, vetted questions** (~14,400) in clean plain-text JSON — no HTML
  entities to unescape, tags + difficulty + `isNiche` metadata. Sampled quality
  is genuinely bar-trivia ("What did Herb Peterson invent? — Egg McMuffin").
- **No API key, no signup** for the free tier; `types=text_choice` filters
  true/false at the source.

**License:** free tier is **CC BY-NC 4.0** — "free for noncommercial use",
attribution requested "somewhere discreet" (per the-trivia-api.com/pricing).
A private, self-hosted friends' game is squarely non-commercial, so importing
and storing questions locally is permitted. (This credit in the repo + this doc
is the attribution.)

**Maintenance evidence:** the service is a commercially operated API
(free + paid tiers, account dashboard) and was **verified live on 2026-07-03**
— it served all nine category fetches for our starter snapshot that day. The
site states the API "is under active development with new questions and
features being added regularly." Honest caveat: decoding the Mongo ObjectId
timestamps of a 150-question random sample puts the newest sampled *question
creation* at ~Sep 2023 — the operation is current, but content growth has
likely slowed. For our use (one-time snapshot, hand-pruned, committed to the
repo) that's fine.

## Runner-up and also-rans

- **Open Trivia Database (opentdb.com)** — runner-up. CC BY-SA 4.0,
  community-maintained with demonstrably fresh activity (moderation/forum
  activity June 2026; third-party scrapes updated May 2026; 21k+ questions).
  Lost on fit: **no Food & Drink category** (verified against
  `api_category.php` — 24 categories, none food), splintered
  entertainment/science categories, HTML-entity-encoded text, true/false noise,
  and a 1-request-per-5-seconds rate limit. If The Trivia API ever dies,
  `CATEGORY_MAP` + the fetcher in `scripts/import_bank.py` are the only things
  to swap; Food & Drink would need another source.
- **uberspot/OpenTriviaQA (GitHub)** — CC BY-SA 4.0, last commit 2026-05-21
  (within 3 months), but a static text-file dump with its own odd category set
  (no food/drink either), mixed quality, multiple-choice-dependent phrasing
  throughout.
- **el-cms/Open-trivia-database (GitHub)** — dead: last push Jan 2022, no
  license file. Eliminated.
- **r/trivia** surfaced no maintained machine-readable source beyond the above
  (it's mostly people sharing quiz packs); OpenTDB is the community default.

## Importing

```
# from the committed snapshot (no network — game night default)
python scripts/import_bank.py --from-file data/bank-starter.json --db trivia.db

# fresh from the API
python scripts/import_bank.py --per-category 20 --db trivia.db
```

- Maps categories via `CATEGORY_MAP`; skips unmappable categories, true/false,
  and choice-dependent phrasings ("which of these…") that can't be graded as a
  short answer. Correct answer → `answer`; distractors are wrong by
  construction so `acceptable_answers` stays empty.
- De-dupes by normalized text (lowercase, punctuation stripped) against the DB
  and within the batch — **re-runs are idempotent**.
- Inserts with `source='bank'`, `author_name='bank'`, `contributor_id NULL`,
  `round_id NULL`.

## Starter snapshot (`data/bank-starter.json`)

Fetched live 2026-07-03 (25/category), then hand-pruned from 203 to **186
questions**: dropped broken grammar, contested facts ("only boxer to knock out
Ali"), ungradeable short answers ("approximate radius of the Earth"), a name
typo, video/board-game questions the source files under sport_and_leisure, and
one too-niche pick. Per category: Music 25, General Knowledge 25, Art &
Literature 23, Science & Nature 21, History 20, Film & TV 20, Food & Drink 18,
Geography 17, Sports 17. Kept in the source's raw JSON shape so `--from-file`
exercises the exact same mapping path as a live fetch.

## Management

`/bank.html` — host-key-gated table of every question (id, source, author,
category, text, answer, round assignment) with category/source filters, inline
delete (server refuses with 409 while a question is assigned to a round), and
an add-question form for the host. **Note for the integrator: `host.html`
(Lane A) should link to `/bank.html`.**
