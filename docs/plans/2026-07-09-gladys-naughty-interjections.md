# Gladys Naughty Interjections

## Requirements

- Give the host clean, naughty, and uncensored Gladys humor levels.
- Keep the cougar/showbiz-roast persona while adding sharper profanity and participant-name jokes.
- Interject sparingly while question timers run and when teams hand in sheets.
- Let vision grading produce one photo-specific joke, but hold it until answers/reveal so it cannot spoil written answers.
- Never let joke generation block or invalidate a submission or grade.

## Files

- `app/db.py`, `app/models.py`, `app/main.py`, `app/grading.py`
- `static/host.html`, `static/display.html`, `static/gladys.js`
- Focused API and grading tests

## Implementation

1. Persist and expose `gladys_level` (`clean`, `naughty`, `uncensored`).
2. Add the host selector in setup and the live MC controls.
3. Add level-aware timer and sheet-submission line banks with name substitution.
4. Expose public-safe submission event metadata; announce an immediate static team roast once.
5. Extend the existing vision result with an optional photo quip, persist it on the submission, and expose it only during `answers`, `reveal`, or later.
6. Queue display announcements with cooldowns and per-question milestone de-duplication.

## Test Plan

- Validate setting authorization, enum rejection, migration/state round-trip, and Lacey behavior.
- Verify photo quips persist without exposing answers or marks.
- Verify photo quips are withheld before `answers` and released afterward.
- Run `just test`.

## Visual Surfaces

- Host at `1280x800`: humor selector is legible in setup and live controls.
- Display at `1920x1080`: timer and submission captions fit without covering the question or ticker.
- Check a long uncensored line, a team-name roast, and a released photo joke.
