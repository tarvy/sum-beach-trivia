# Sum Beach Trivia

A lightweight, self-hosted bar-trivia web app for game night with friends. Friends
contribute questions ahead of time; on game night teams write answers by hand, snap one
photo of the sheet per round, and a vision model reads + grades them while the host
confirms. Runs on a single persistent [sprite](https://sprites.dev) at one public URL.

See the design spec: [`docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md`](docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md)

## Status

Pre-implementation. Spec approved; implementation plan next.

## Stack

FastAPI + SQLite, plain HTML/JS (no build step), polling for live updates, Claude vision
for handwriting grading. Deployed to a sprite; the SQLite DB and uploaded photos live on
the sprite's persistent disk.
