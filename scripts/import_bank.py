#!/usr/bin/env python3
"""Import bank questions into trivia.db from The Trivia API (the-trivia-api.com).

Fetches N text-choice questions per category (or loads a local JSON snapshot),
maps source categories onto our 9 standard categories, skips anything that
isn't gradeable as a short answer, de-dupes against what's already in the DB,
and INSERTs with source='bank'. Idempotent — re-runs insert nothing new.

Stdlib only. Usage:
    python scripts/import_bank.py --per-category 20 --db trivia.db
    python scripts/import_bank.py --from-file data/bank-starter.json --db trivia.db
    python scripts/import_bank.py --per-category 25 --save-snapshot data/bank-starter.json --db /tmp/bank-test.db
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.request

API_URL = "https://the-trivia-api.com/v2/questions?limit={limit}&categories={category}&types=text_choice"

# The Trivia API category slug -> our standard category. society_and_culture is
# intentionally unmapped (no clean home in our 9); unmapped questions are skipped.
CATEGORY_MAP = {
    "history": "History",
    "geography": "Geography",
    "science": "Science & Nature",
    "sport_and_leisure": "Sports",
    "film_and_tv": "Film & TV",
    "music": "Music",
    "arts_and_literature": "Art & Literature",
    "food_and_drink": "Food & Drink",
    "general_knowledge": "General Knowledge",
}

# Multiple-choice phrasings that are unanswerable without seeing the choices.
_NEEDS_CHOICES = re.compile(r"\bof (these|the following)\b", re.IGNORECASE)


def normalize(text: str) -> str:
    """Dedupe key: lowercase, punctuation stripped, whitespace collapsed."""
    return " ".join(re.sub(r"[^a-z0-9\s]", "", (text or "").lower()).split())


def map_question(raw: dict) -> dict | None:
    """Convert one source question to our shape, or None if it can't be used."""
    if raw.get("type") != "text_choice":  # skips true/false etc.
        return None
    category = CATEGORY_MAP.get(raw.get("category"))
    if category is None:
        return None
    text = ((raw.get("question") or {}).get("text") or "").strip()
    answer = (raw.get("correctAnswer") or "").strip()
    if not text or not answer or _NEEDS_CHOICES.search(text):
        return None
    # Correct answer becomes the answer; distractors are wrong by construction,
    # so acceptable stays empty.
    return {"category": category, "text": text, "answer": answer, "acceptable": []}


def import_questions(conn: sqlite3.Connection, raws: list[dict]) -> dict:
    """Map, dedupe (against the DB and within the batch), and insert as bank
    questions. Returns counts: inserted / duplicate / unmappable."""
    cat_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM category")}
    seen = {normalize(r["text"]) for r in conn.execute("SELECT text FROM question")}
    counts = {"inserted": 0, "duplicate": 0, "unmappable": 0}
    for raw in raws:
        q = map_question(raw)
        if q is None:
            counts["unmappable"] += 1
            continue
        key = normalize(q["text"])
        if key in seen:
            counts["duplicate"] += 1
            continue
        try:
            conn.execute(
                "INSERT INTO question (author_name, category_id, text, answer, "
                "acceptable_answers, contributor_id, round_id, source) "
                "VALUES ('bank', ?, ?, ?, ?, NULL, NULL, 'bank')",
                (cat_ids[q["category"]], q["text"], q["answer"], json.dumps(q["acceptable"])),
            )
        except sqlite3.Error:
            conn.rollback()  # a failed write must never poison the connection
            raise
        seen.add(key)
        counts["inserted"] += 1
    conn.commit()
    return counts


def fetch_all(per_category: int) -> list[dict]:
    """One request per source category (API caps limit at 50)."""
    raws = []
    for slug in CATEGORY_MAP:
        url = API_URL.format(limit=min(per_category, 50), category=slug)
        req = urllib.request.Request(url, headers={"User-Agent": "sum-beach-trivia"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raws.extend(json.load(resp))
        time.sleep(0.5)  # be polite
    return raws


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--per-category", type=int, default=20)
    p.add_argument("--db", default="trivia.db")
    p.add_argument("--from-file", help="load a local JSON snapshot instead of the network")
    p.add_argument("--save-snapshot", help="write the fetched raw questions to this JSON file")
    args = p.parse_args()

    if args.from_file:
        with open(args.from_file) as f:
            raws = json.load(f)
    else:
        raws = fetch_all(args.per_category)
    if args.save_snapshot:
        with open(args.save_snapshot, "w") as f:
            json.dump(raws, f, indent=1, ensure_ascii=False)
        print(f"snapshot: {len(raws)} raw questions -> {args.save_snapshot}")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    if conn.execute("SELECT name FROM sqlite_master WHERE name='question'").fetchone() is None:
        # fresh DB (e.g. right after a game-reset wipe, before the app booted):
        # create the schema ourselves instead of racing the app's first boot
        import pathlib
        import sys
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from app.db import init_db
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
    counts = import_questions(conn, raws)
    conn.close()
    print(f"inserted={counts['inserted']} duplicate={counts['duplicate']} "
          f"unmappable={counts['unmappable']} (of {len(raws)} fetched)")


if __name__ == "__main__":
    main()
