# Sum Beach Trivia Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A lightweight self-hosted bar-trivia web app where friends pre-load questions, teams submit handwritten-answer photos, a vision model grades them with host confirmation, and a live leaderboard tracks scores — all on one persistent sprite.

**Architecture:** Single Python FastAPI process backed by a SQLite file. Server-rendered/static HTML + vanilla JS for four views (contribute, host, play, display), no build step. Live updates via short-interval polling of small JSON endpoints (no WebSockets). Handwriting grading is one Claude vision call per submitted sheet. All authoritative state lives in SQLite; scores are always derived from stored marks, never frozen.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLite (stdlib `sqlite3`), `anthropic` SDK (vision + `messages.parse`), Pydantic, pytest + httpx for tests. Deployed to a sprite (sprites.dev).

## Global Constraints

- Python 3.11+ (uses `match`/`case` and modern typing).
- SQLite via stdlib `sqlite3` only — no ORM, no Postgres. One DB file at `$TRIVIA_DB` (default `trivia.db`).
- Grading uses the official `anthropic` Python SDK. Model id from `GRADING_MODEL` env var, default `claude-opus-4-8` (vision-capable; `claude-haiku-4-5` is the cheap alternative). Requires `ANTHROPIC_API_KEY` in env. Never hardcode the key.
- Vision images are sent as base64 `image` content blocks; grading output is constrained with `messages.parse()` + a Pydantic schema (no prefill).
- **Scores are always derived from `mark` rows — never store a mutable team total.**
- **Role-filtered responses: the `answer` and `answer_items` fields are NEVER serialized to non-host roles.**
- Live updates use polling (2–3s); do not add WebSockets.
- Host-only routes require a secret host key (from `game.host_key`), supplied as a query param/cookie.
- One active game at a time is acceptable for v1.
- Ponytail bias: prefer stdlib and the simplest thing that works; no speculative abstraction.
- Spec: `docs/superpowers/specs/2026-06-19-sum-beach-trivia-design.md`.

---

### Task 1: Project scaffold, dependencies, and database schema

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py` (empty)
- Create: `app/db.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `app/db.py`: `connect(path: str) -> sqlite3.Connection` (row_factory = `sqlite3.Row`, foreign keys ON), `init_db(conn) -> None` (creates all tables idempotently and seeds categories), `STANDARD_CATEGORIES: list[str]`.
  - `tests/conftest.py`: pytest fixture `db` yielding an initialized in-memory connection.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi
uvicorn[standard]
anthropic
pydantic
pytest
httpx
```

- [ ] **Step 2: Write the failing test** `tests/test_db.py`

```python
from app.db import connect, init_db, STANDARD_CATEGORIES


def test_init_db_creates_tables_and_seeds_categories(tmp_path):
    conn = connect(":memory:")
    init_db(conn)
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "game", "category", "question", "round",
        "team", "submission", "wager", "mark",
    } <= tables
    cats = [r["name"] for r in conn.execute(
        "SELECT name FROM category ORDER BY display_order")]
    assert cats == STANDARD_CATEGORIES


def test_init_db_is_idempotent():
    conn = connect(":memory:")
    init_db(conn)
    init_db(conn)  # must not raise or duplicate categories
    (count,) = conn.execute("SELECT COUNT(*) FROM category").fetchone()
    assert count == len(STANDARD_CATEGORIES)


def test_foreign_keys_enforced():
    conn = connect(":memory:")
    init_db(conn)
    import sqlite3
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO question (author_name, category_id, text, answer, display_order) "
            "VALUES ('x', 9999, 'q', 'a', 0)"
        )
        conn.commit()
```

- [ ] **Step 3: Run it to verify failure**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.db'`).

- [ ] **Step 4: Implement `app/db.py`**

```python
from __future__ import annotations

import sqlite3

STANDARD_CATEGORIES = [
    "History",
    "Geography",
    "Science & Nature",
    "Sports",
    "Film & TV",
    "Music",
    "Art & Literature",
    "Food & Drink",
    "General Knowledge",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS game (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    code TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT 'draft',
    current_round_id INTEGER,
    paused INTEGER NOT NULL DEFAULT 0,
    host_key TEXT NOT NULL,
    tiebreak_question TEXT,
    tiebreak_value REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS category (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS round (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category_id INTEGER REFERENCES category(id),
    display_order INTEGER NOT NULL,
    bonus_multiplier REAL NOT NULL DEFAULT 1,
    is_final INTEGER NOT NULL DEFAULT 0,
    wager_cap INTEGER,
    phase_locked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS question (
    id INTEGER PRIMARY KEY,
    author_name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category(id),
    text TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    acceptable_answers TEXT NOT NULL DEFAULT '[]',  -- JSON list
    answer_items TEXT,                              -- JSON list or NULL
    ordered INTEGER NOT NULL DEFAULT 0,
    point_value REAL NOT NULL DEFAULT 1,
    round_id INTEGER REFERENCES round(id),
    display_order INTEGER NOT NULL DEFAULT 0,
    media_url TEXT
);

CREATE TABLE IF NOT EXISTS team (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL UNIQUE,
    recovery_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS submission (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES team(id),
    round_id INTEGER NOT NULL REFERENCES round(id),
    photo_path TEXT NOT NULL,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (team_id, round_id)
);

CREATE TABLE IF NOT EXISTS wager (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES team(id),
    round_id INTEGER NOT NULL REFERENCES round(id),
    amount INTEGER NOT NULL,
    committed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (team_id, round_id)
);

CREATE TABLE IF NOT EXISTS mark (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES team(id),
    question_id INTEGER NOT NULL REFERENCES question(id),
    transcription TEXT NOT NULL DEFAULT '',
    is_correct INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    items_correct INTEGER,   -- for multi-item questions
    confidence REAL,
    flagged INTEGER NOT NULL DEFAULT 0,
    manually_corrected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (team_id, question_id)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for order, name in enumerate(STANDARD_CATEGORIES):
        conn.execute(
            "INSERT OR IGNORE INTO category (name, display_order) VALUES (?, ?)",
            (name, order),
        )
    conn.commit()
```

- [ ] **Step 5: Write `tests/conftest.py`**

```python
import pytest

from app.db import connect, init_db


@pytest.fixture
def db():
    conn = connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt app/__init__.py app/db.py tests/__init__.py tests/conftest.py tests/test_db.py
git commit -m "feat: SQLite schema and DB init with seeded categories"
```

---

### Task 2: Scoring — derive totals from marks (incl. bonus, partial credit, final wager)

**Files:**
- Create: `app/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: a `sqlite3.Connection` with the Task 1 schema.
- Produces:
  - `final_round_delta(amount: int, items_correct: int, total_items: int) -> int` — proportional wager math, `round(amount * (2*f - 1))`, where `f = items_correct/total_items` (f=0 when total_items==0).
  - `team_totals(conn) -> list[dict]` — returns `[{"team_id", "name", "total"}]` sorted by total desc then name asc. Non-final rounds: sum of `mark.score * round.bonus_multiplier` for that round's questions. Final round: the wager delta. Missing marks count as 0.

- [ ] **Step 1: Write the failing test** `tests/test_scoring.py`

```python
import pytest

from app.scoring import final_round_delta, team_totals


@pytest.mark.parametrize("amount,correct,total,expected", [
    (10, 5, 5, 10),     # all right -> +full
    (10, 4, 5, 6),      # 2*0.8-1 = 0.6 -> 6
    (10, 3, 5, 2),      # 2*0.6-1 = 0.2 -> 2
    (10, 2, 5, -2),     # 2*0.4-1 = -0.2 -> -2
    (10, 0, 5, -10),    # all wrong -> -full
    (10, 0, 0, -10),    # no items defined -> treat as f=0
    (0, 3, 5, 0),       # zero wager -> 0
])
def test_final_round_delta(amount, correct, total, expected):
    assert final_round_delta(amount, correct, total) == expected


def _seed_basic_game(db):
    db.execute("INSERT INTO game (id, code, host_key) VALUES (1, 'ABCD', 'k')")
    db.execute("INSERT INTO round (id, title, category_id, display_order, bonus_multiplier) "
               "VALUES (1, 'History', 1, 0, 1)")
    db.execute("INSERT INTO round (id, title, category_id, display_order, bonus_multiplier) "
               "VALUES (2, 'Double Sports', 4, 1, 2)")
    db.execute("INSERT INTO question (id, author_name, category_id, text, answer, round_id, display_order) "
               "VALUES (1, 'me', 1, 'q1', 'a', 1, 0)")
    db.execute("INSERT INTO question (id, author_name, category_id, text, answer, round_id, display_order) "
               "VALUES (2, 'me', 4, 'q2', 'a', 2, 0)")
    db.execute("INSERT INTO team (id, name, name_lower, recovery_code) VALUES (1, 'Aces', 'aces', 'r1')")
    db.execute("INSERT INTO team (id, name, name_lower, recovery_code) VALUES (2, 'Bees', 'bees', 'r2')")
    db.commit()


def test_team_totals_basic_and_bonus(db):
    _seed_basic_game(db)
    # Aces: 1 pt in round 1, 1 pt in round 2 (x2 bonus) = 1 + 2 = 3
    db.execute("INSERT INTO mark (team_id, question_id, score) VALUES (1, 1, 1)")
    db.execute("INSERT INTO mark (team_id, question_id, score) VALUES (1, 2, 1)")
    # Bees: nothing scored
    db.commit()
    totals = team_totals(db)
    by_name = {t["name"]: t["total"] for t in totals}
    assert by_name == {"Aces": 3, "Bees": 0}
    assert totals[0]["name"] == "Aces"  # sorted desc


def test_team_totals_corrections_cascade(db):
    _seed_basic_game(db)
    db.execute("INSERT INTO mark (team_id, question_id, score) VALUES (1, 1, 1)")
    db.commit()
    assert {t["name"]: t["total"] for t in team_totals(db)}["Aces"] == 1
    # host fixes the mark down to 0 -> total recomputes
    db.execute("UPDATE mark SET score = 0 WHERE team_id = 1 AND question_id = 1")
    db.commit()
    assert {t["name"]: t["total"] for t in team_totals(db)}["Aces"] == 0


def test_team_totals_final_round_wager(db):
    _seed_basic_game(db)
    db.execute("UPDATE round SET is_final = 1, wager_cap = 10 WHERE id = 2")
    db.execute("UPDATE question SET answer_items = '[\"a\",\"b\",\"c\",\"d\",\"e\"]', ordered = 1 WHERE id = 2")
    db.execute("INSERT INTO wager (team_id, round_id, amount) VALUES (1, 2, 10)")
    db.execute("INSERT INTO mark (team_id, question_id, items_correct, score) VALUES (1, 2, 4, 0)")
    db.commit()
    # final delta for Aces: amount 10, 4/5 -> +6 ; no points from round 1
    assert {t["name"]: t["total"] for t in team_totals(db)}["Aces"] == 6
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.scoring'`).

- [ ] **Step 3: Implement `app/scoring.py`**

```python
from __future__ import annotations

import json
import sqlite3


def final_round_delta(amount: int, items_correct: int, total_items: int) -> int:
    f = (items_correct / total_items) if total_items else 0.0
    return round(amount * (2 * f - 1))


def team_totals(conn: sqlite3.Connection) -> list[dict]:
    teams = conn.execute("SELECT id, name FROM team").fetchall()
    rounds = conn.execute(
        "SELECT id, bonus_multiplier, is_final, wager_cap FROM round"
    ).fetchall()
    results = []
    for team in teams:
        total = 0.0
        for rnd in rounds:
            if rnd["is_final"]:
                total += _final_total(conn, team["id"], rnd["id"])
            else:
                row = conn.execute(
                    "SELECT COALESCE(SUM(m.score), 0) AS s "
                    "FROM mark m JOIN question q ON q.id = m.question_id "
                    "WHERE m.team_id = ? AND q.round_id = ?",
                    (team["id"], rnd["id"]),
                ).fetchone()
                total += row["s"] * rnd["bonus_multiplier"]
        # totals are whole numbers in practice; keep int when clean
        total = int(total) if float(total).is_integer() else total
        results.append({"team_id": team["id"], "name": team["name"], "total": total})
    results.sort(key=lambda t: (-t["total"], t["name"].lower()))
    return results


def _final_total(conn: sqlite3.Connection, team_id: int, round_id: int) -> int:
    from app.scoring import final_round_delta  # self-ref kept explicit
    w = conn.execute(
        "SELECT amount FROM wager WHERE team_id = ? AND round_id = ?",
        (team_id, round_id),
    ).fetchone()
    if w is None:
        return 0
    q = conn.execute(
        "SELECT id, answer_items FROM question WHERE round_id = ? LIMIT 1",
        (round_id,),
    ).fetchone()
    if q is None:
        return 0
    items = json.loads(q["answer_items"] or "[]")
    mark = conn.execute(
        "SELECT items_correct FROM mark WHERE team_id = ? AND question_id = ?",
        (team_id, q["id"]),
    ).fetchone()
    correct = (mark["items_correct"] or 0) if mark else 0
    return final_round_delta(w["amount"], correct, len(items))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: PASS (all parametrized + 3 DB tests).

- [ ] **Step 5: Commit**

```bash
git add app/scoring.py tests/test_scoring.py
git commit -m "feat: derived scoring with bonus rounds and proportional final wager"
```

---

### Task 3: Balanced round builder

**Files:**
- Create: `app/rounds.py`
- Test: `tests/test_rounds.py`

**Interfaces:**
- Consumes: `sqlite3.Connection`.
- Produces:
  - `build_rounds(conn, target_size: int = 5) -> list[dict]` — clears existing non-final rounds, groups unassigned questions by category into rounds aiming for `target_size`, assigns `question.round_id` and `display_order`, returns the created rounds as `[{"id","title","category","question_count"}]` in display order. Does NOT touch a round with `is_final = 1`.
  - `imbalance_warnings(conn, target_size: int = 5) -> list[str]` — human-readable warnings (e.g. categories with very few questions, total below a sensible minimum).

- [ ] **Step 1: Write the failing test** `tests/test_rounds.py`

```python
from app.rounds import build_rounds, imbalance_warnings


def _add_questions(db, category_name, n):
    cat = db.execute("SELECT id FROM category WHERE name = ?", (category_name,)).fetchone()["id"]
    for i in range(n):
        db.execute(
            "INSERT INTO question (author_name, category_id, text, answer, display_order) "
            "VALUES (?, ?, ?, ?, ?)",
            ("me", cat, f"{category_name} q{i}", "a", i),
        )
    db.commit()


def test_build_rounds_groups_by_category(db):
    _add_questions(db, "History", 3)
    _add_questions(db, "Sports", 2)
    rounds = build_rounds(db, target_size=5)
    titles = {r["title"] for r in rounds}
    assert titles == {"History", "Sports"}
    counts = {r["title"]: r["question_count"] for r in rounds}
    assert counts == {"History": 3, "Sports": 2}
    # every question is now assigned to a round
    (unassigned,) = db.execute(
        "SELECT COUNT(*) FROM question WHERE round_id IS NULL"
    ).fetchone()
    assert unassigned == 0


def test_build_rounds_splits_large_category(db):
    _add_questions(db, "History", 12)
    rounds = build_rounds(db, target_size=5)
    history = [r for r in rounds if r["title"].startswith("History")]
    assert len(history) == 3  # 5 + 5 + 2
    assert sum(r["question_count"] for r in history) == 12


def test_build_rounds_rerun_is_clean(db):
    _add_questions(db, "History", 3)
    build_rounds(db)
    build_rounds(db)  # rerun must not duplicate rounds or orphan questions
    (rounds,) = db.execute("SELECT COUNT(*) FROM round WHERE is_final = 0").fetchone()
    assert rounds == 1


def test_imbalance_warning_for_thin_category(db):
    _add_questions(db, "History", 1)
    warnings = imbalance_warnings(db)
    assert any("History" in w for w in warnings)
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_rounds.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `app/rounds.py`**

```python
from __future__ import annotations

import math
import sqlite3


def build_rounds(conn: sqlite3.Connection, target_size: int = 5) -> list[dict]:
    # Detach questions from non-final rounds, then delete those rounds.
    conn.execute(
        "UPDATE question SET round_id = NULL WHERE round_id IN "
        "(SELECT id FROM round WHERE is_final = 0)"
    )
    conn.execute("DELETE FROM round WHERE is_final = 0")

    cats = conn.execute(
        "SELECT c.id, c.name, c.display_order "
        "FROM category c "
        "WHERE EXISTS (SELECT 1 FROM question q WHERE q.category_id = c.id AND q.round_id IS NULL) "
        "ORDER BY c.display_order"
    ).fetchall()

    order = 0
    for cat in cats:
        qs = conn.execute(
            "SELECT id FROM question WHERE category_id = ? AND round_id IS NULL ORDER BY id",
            (cat["id"],),
        ).fetchall()
        n_rounds = max(1, math.ceil(len(qs) / target_size))
        chunks = [qs[i::n_rounds] for i in range(n_rounds)]  # even-ish split
        for idx, chunk in enumerate(chunks):
            if not chunk:
                continue
            title = cat["name"] if n_rounds == 1 else f"{cat['name']} {idx + 1}"
            cur = conn.execute(
                "INSERT INTO round (title, category_id, display_order, bonus_multiplier) "
                "VALUES (?, ?, ?, 1)",
                (title, cat["id"], order),
            )
            round_id = cur.lastrowid
            for d, q in enumerate(chunk):
                conn.execute(
                    "UPDATE question SET round_id = ?, display_order = ? WHERE id = ?",
                    (round_id, d, q["id"]),
                )
            order += 1
    conn.commit()
    return _round_summaries(conn)


def _round_summaries(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT r.id, r.title, c.name AS category, "
        "(SELECT COUNT(*) FROM question q WHERE q.round_id = r.id) AS question_count "
        "FROM round r LEFT JOIN category c ON c.id = r.category_id "
        "WHERE r.is_final = 0 ORDER BY r.display_order"
    ).fetchall()
    return [dict(r) for r in rows]


def imbalance_warnings(conn: sqlite3.Connection, target_size: int = 5) -> list[str]:
    warnings: list[str] = []
    rows = conn.execute(
        "SELECT c.name, COUNT(q.id) AS n FROM category c "
        "JOIN question q ON q.category_id = c.id GROUP BY c.id ORDER BY c.display_order"
    ).fetchall()
    for r in rows:
        if r["n"] < 2:
            warnings.append(f"Category '{r['name']}' has only {r['n']} question(s).")
    (total,) = conn.execute("SELECT COUNT(*) FROM question").fetchone()
    if total < target_size:
        warnings.append(f"Only {total} questions total — fewer than one full round.")
    return warnings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rounds.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/rounds.py tests/test_rounds.py
git commit -m "feat: balanced round builder grouped by category with imbalance warnings"
```

---

### Task 4: Models / data-access helpers

**Files:**
- Create: `app/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `sqlite3.Connection`.
- Produces (all take `conn` first):
  - `add_question(conn, author_name, category_name, text, answer, acceptable=None) -> int`
  - `create_game(conn, code, host_key) -> None` (upserts the single `id=1` row, phase `draft`).
  - `get_game(conn) -> sqlite3.Row | None`
  - `set_phase(conn, phase) -> None`; `set_current_round(conn, round_id)`; `set_paused(conn, bool)`
  - `join_team(conn, name) -> dict` — returns `{"team_id","name","recovery_code"}`; raises `ValueError` on case-insensitive duplicate.
  - `team_by_recovery(conn, recovery_code) -> sqlite3.Row | None`
  - `gen_code(n=4) -> str` and `gen_recovery() -> str` — short random tokens (use `secrets`).

- [ ] **Step 1: Write the failing test** `tests/test_models.py`

```python
import pytest

from app import models


def test_add_question_resolves_category(db):
    qid = models.add_question(db, "Travis", "Science & Nature", "Sky color?", "blue",
                              acceptable=["azure"])
    row = db.execute("SELECT * FROM question WHERE id = ?", (qid,)).fetchone()
    assert row["author_name"] == "Travis"
    assert row["answer"] == "blue"
    import json
    assert json.loads(row["acceptable_answers"]) == ["azure"]


def test_add_question_unknown_category_raises(db):
    with pytest.raises(ValueError):
        models.add_question(db, "x", "Nope", "q", "a")


def test_create_and_get_game(db):
    models.create_game(db, code="WAVE", host_key="secret")
    g = models.get_game(db)
    assert g["code"] == "WAVE"
    assert g["phase"] == "draft"
    assert g["host_key"] == "secret"


def test_join_team_unique_case_insensitive(db):
    t = models.join_team(db, "Beach Bums")
    assert t["team_id"] > 0 and t["recovery_code"]
    with pytest.raises(ValueError):
        models.join_team(db, "beach bums")


def test_team_by_recovery(db):
    t = models.join_team(db, "Sandy")
    row = models.team_by_recovery(db, t["recovery_code"])
    assert row["id"] == t["team_id"]
    assert models.team_by_recovery(db, "nope") is None
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `app/models.py`**

```python
from __future__ import annotations

import json
import secrets
import sqlite3

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars


def gen_code(n: int = 4) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def gen_recovery() -> str:
    return secrets.token_hex(4)


def _category_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM category WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown category: {name}")
    return row["id"]


def add_question(conn, author_name, category_name, text, answer, acceptable=None) -> int:
    cat_id = _category_id(conn, category_name)
    cur = conn.execute(
        "INSERT INTO question (author_name, category_id, text, answer, acceptable_answers) "
        "VALUES (?, ?, ?, ?, ?)",
        (author_name, cat_id, text, answer, json.dumps(acceptable or [])),
    )
    conn.commit()
    return cur.lastrowid


def create_game(conn, code: str, host_key: str) -> None:
    conn.execute(
        "INSERT INTO game (id, code, host_key, phase) VALUES (1, ?, ?, 'draft') "
        "ON CONFLICT(id) DO UPDATE SET code = excluded.code, host_key = excluded.host_key",
        (code, host_key),
    )
    conn.commit()


def get_game(conn) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM game WHERE id = 1").fetchone()


def set_phase(conn, phase: str) -> None:
    conn.execute("UPDATE game SET phase = ? WHERE id = 1", (phase,))
    conn.commit()


def set_current_round(conn, round_id: int | None) -> None:
    conn.execute("UPDATE game SET current_round_id = ? WHERE id = 1", (round_id,))
    conn.commit()


def set_paused(conn, paused: bool) -> None:
    conn.execute("UPDATE game SET paused = ? WHERE id = 1", (1 if paused else 0,))
    conn.commit()


def join_team(conn, name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("Team name required")
    recovery = gen_recovery()
    try:
        cur = conn.execute(
            "INSERT INTO team (name, name_lower, recovery_code) VALUES (?, ?, ?)",
            (name, name.lower(), recovery),
        )
    except sqlite3.IntegrityError:
        raise ValueError("Team name already taken")
    conn.commit()
    return {"team_id": cur.lastrowid, "name": name, "recovery_code": recovery}


def team_by_recovery(conn, recovery_code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM team WHERE recovery_code = ?", (recovery_code,)
    ).fetchone()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: data-access helpers for questions, game, and teams"
```

---

### Task 5: Grading — Claude vision call and response parsing

**Files:**
- Create: `app/grading.py`
- Test: `tests/test_grading.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure helper); reads `GRADING_MODEL` / `ANTHROPIC_API_KEY` from env at call time.
- Produces:
  - Pydantic models `QuestionGrade` (`question_id: int`, `transcription: str`, `is_correct: bool`, `confidence: float`, `items_correct: int | None = None`) and `SheetGrade` (`grades: list[QuestionGrade]`).
  - `build_prompt(questions: list[dict]) -> str` — questions are `[{"id","text","answer","acceptable","answer_items","ordered"}]`; produces the grading instruction text. Pure/testable.
  - `grade_sheet(image_bytes: bytes, media_type: str, questions: list[dict], client=None) -> SheetGrade` — sends one vision request via `messages.parse`; `client` injectable for tests.

- [ ] **Step 1: Write the failing test** `tests/test_grading.py`

```python
from app.grading import QuestionGrade, SheetGrade, build_prompt, grade_sheet


def test_build_prompt_includes_questions_and_answers():
    qs = [
        {"id": 1, "text": "Capital of France?", "answer": "Paris",
         "acceptable": [], "answer_items": None, "ordered": False},
        {"id": 2, "text": "Order these by year", "answer": "",
         "acceptable": [], "answer_items": ["A", "B", "C"], "ordered": True},
    ]
    prompt = build_prompt(qs)
    assert "Capital of France?" in prompt
    assert "Paris" in prompt
    assert "1" in prompt and "2" in prompt
    # multi-item guidance present
    assert "items_correct" in prompt.lower() or "in order" in prompt.lower()


class _FakeClient:
    """Mimics anthropic client: .messages.parse(...) -> object with .parsed_output."""
    def __init__(self, payload):
        self._payload = payload
        self.messages = self

    def parse(self, **kwargs):
        # capture for assertions
        self.last_kwargs = kwargs
        class R:  # noqa: N801
            parsed_output = self_payload = self._payload
        return R

    @property
    def _payload_obj(self):
        return self._payload


def test_grade_sheet_returns_parsed_grades():
    payload = SheetGrade(grades=[
        QuestionGrade(question_id=1, transcription="Paris", is_correct=True, confidence=0.95),
    ])

    class Resp:
        parsed_output = payload

    class Msgs:
        def parse(self, **kwargs):
            Msgs.captured = kwargs
            return Resp

    class Client:
        messages = Msgs()

    result = grade_sheet(
        image_bytes=b"\x89PNG fake",
        media_type="image/png",
        questions=[{"id": 1, "text": "Capital of France?", "answer": "Paris",
                    "acceptable": [], "answer_items": None, "ordered": False}],
        client=Client(),
    )
    assert isinstance(result, SheetGrade)
    assert result.grades[0].is_correct is True
    # image was attached as a base64 block
    content = Msgs.captured["messages"][0]["content"]
    assert any(b.get("type") == "image" for b in content)
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_grading.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `app/grading.py`**

```python
from __future__ import annotations

import base64
import json
import os

from pydantic import BaseModel


class QuestionGrade(BaseModel):
    question_id: int
    transcription: str
    is_correct: bool
    confidence: float
    items_correct: int | None = None


class SheetGrade(BaseModel):
    grades: list[QuestionGrade]


def build_prompt(questions: list[dict]) -> str:
    lines = [
        "You are grading a photo of a team's handwritten trivia answer sheet.",
        "For EACH numbered question below, find the team's handwritten answer in the image,",
        "transcribe it, and decide if it is correct. Be generous about spelling, abbreviations,",
        "and well-known equivalents (e.g. 'JFK' = 'John F. Kennedy'). Set a confidence 0..1;",
        "use low confidence when the handwriting is unclear or no answer is found.",
        "For multi-item questions (a list, or 'put these in order'), set items_correct to the",
        "number of items the team got right (for ordered questions, count correct positions).",
        "",
        "Questions:",
    ]
    for q in questions:
        if q.get("answer_items"):
            expected = ", ".join(q["answer_items"])
            kind = "ORDERED list" if q.get("ordered") else "set of items"
            lines.append(
                f'#{q["id"]} ({kind}): {q["text"]}  Expected items: [{expected}]'
            )
        else:
            acc = q.get("acceptable") or []
            extra = f" (also accept: {', '.join(acc)})" if acc else ""
            lines.append(f'#{q["id"]}: {q["text"]}  Correct answer: {q["answer"]}{extra}')
    return "\n".join(lines)


def _client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def grade_sheet(image_bytes: bytes, media_type: str, questions: list[dict], client=None) -> SheetGrade:
    client = client or _client()
    model = os.environ.get("GRADING_MODEL", "claude-opus-4-8")
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    resp = client.messages.parse(
        model=model,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": build_prompt(questions)},
            ],
        }],
        output_config={"format": _schema_format()},
    )
    parsed = resp.parsed_output
    if isinstance(parsed, SheetGrade):
        return parsed
    if isinstance(parsed, dict):
        return SheetGrade(**parsed)
    # parsed_output may already be the typed object; fall back to text JSON
    return SheetGrade(**json.loads(parsed))


def _schema_format():
    return {"type": "json_schema", "schema": SheetGrade.model_json_schema()}
```

> Note for the implementer: `messages.parse(output_format=SheetGrade)` is the SDK's typed convenience and is preferred if the installed SDK supports it (returns a `SheetGrade` directly). The explicit `output_config.format` above is the canonical API form and keeps the test's `parsed_output` contract simple. Pick whichever the installed `anthropic` version supports; both satisfy the test. Do not add assistant prefill.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_grading.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/grading.py tests/test_grading.py
git commit -m "feat: Claude vision grading of handwritten answer sheets"
```

---

### Task 6: FastAPI app — contribute flow and role-filtered serialization

**Files:**
- Create: `app/main.py`
- Create: `app/serializers.py`
- Test: `tests/test_api_contribute.py`

**Interfaces:**
- Consumes: `app.db`, `app.models`, `app.rounds`.
- Produces:
  - `app/main.py`: `create_app(db_path: str | None = None) -> FastAPI`. App holds one connection on `app.state.conn` (SQLite with `check_same_thread=False`). On startup: `init_db`, and if no game exists, `create_game` with random code + host key (printed to stdout). Routes:
    - `GET /api/categories` -> `{"categories": [...]}`
    - `POST /api/questions` body `{author, category, text, answer, acceptable?}` -> `{"id": ...}` (only allowed while phase is `draft`).
    - `GET /api/questions?host_key=...` -> full questions **including** answers, host only (403 otherwise).
    - `GET /api/questions/mine?author=...` -> the author's own questions WITHOUT answers (count + texts), for the contribute confirmation view.
  - `app/serializers.py`: `public_question(row) -> dict` (NO `answer`/`answer_items`), `host_question(row) -> dict` (full). Used everywhere a question is returned.

- [ ] **Step 1: Write the failing test** `tests/test_api_contribute.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c._app = app
        yield c


def _host_key(client):
    return client._app.state.conn.execute(
        "SELECT host_key FROM game WHERE id = 1"
    ).fetchone()["host_key"]


@pytest.mark.anyio
async def test_categories(client):
    r = await client.get("/api/categories")
    assert r.status_code == 200
    assert "History" in r.json()["categories"]


@pytest.mark.anyio
async def test_submit_question_then_host_sees_answer(client):
    r = await client.post("/api/questions", json={
        "author": "Travis", "category": "History", "text": "Year WWII ended?",
        "answer": "1945",
    })
    assert r.status_code == 200
    qid = r.json()["id"]

    # public listing of mine must NOT leak the answer
    mine = await client.get("/api/questions/mine", params={"author": "Travis"})
    body = mine.json()
    assert any(q["id"] == qid for q in body["questions"])
    assert all("answer" not in q for q in body["questions"])

    # host listing (with key) DOES include the answer
    hk = _host_key(client)
    h = await client.get("/api/questions", params={"host_key": hk})
    assert h.status_code == 200
    assert any(q["answer"] == "1945" for q in h.json()["questions"])


@pytest.mark.anyio
async def test_host_listing_requires_key(client):
    r = await client.get("/api/questions", params={"host_key": "wrong"})
    assert r.status_code == 403
```

> Add a `tests/conftest.py` fixture for anyio backend: `@pytest.fixture\ndef anyio_backend(): return "asyncio"`. Add `anyio` to `requirements.txt` (pulled in by httpx/starlette already, but pin it).

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_api_contribute.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.main'`).

- [ ] **Step 3: Implement `app/serializers.py`**

```python
from __future__ import annotations

import json
import sqlite3


def public_question(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "text": row["text"],
        "category_id": row["category_id"],
        "display_order": row["display_order"],
        "ordered": bool(row["ordered"]),
        "item_count": len(json.loads(row["answer_items"])) if row["answer_items"] else None,
        "point_value": row["point_value"],
    }


def host_question(row: sqlite3.Row) -> dict:
    d = public_question(row)
    d.update({
        "author_name": row["author_name"],
        "answer": row["answer"],
        "acceptable_answers": json.loads(row["acceptable_answers"]),
        "answer_items": json.loads(row["answer_items"]) if row["answer_items"] else None,
    })
    return d
```

- [ ] **Step 4: Implement `app/main.py`**

```python
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app import models
from app.db import connect, init_db
from app.serializers import host_question, public_question


class QuestionIn(BaseModel):
    author: str
    category: str
    text: str
    answer: str = ""
    acceptable: list[str] | None = None


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("TRIVIA_DB", "trivia.db")
    app = FastAPI(title="Sum Beach Trivia")
    conn = connect(db_path) if db_path == ":memory:" else connect(db_path)
    # allow cross-thread use by uvicorn workers
    conn = connect(db_path) if db_path != ":memory:" else conn
    app.state.conn = conn

    init_db(conn)
    if models.get_game(conn) is None:
        code = models.gen_code()
        host_key = models.gen_recovery()
        models.create_game(conn, code=code, host_key=host_key)
        print(f"[sum-beach-trivia] game code={code}  HOST KEY={host_key}")

    def db():
        return app.state.conn

    def require_host(host_key: str):
        g = models.get_game(db())
        if g is None or host_key != g["host_key"]:
            raise HTTPException(status_code=403, detail="bad host key")
        return g

    @app.get("/api/categories")
    def categories():
        rows = db().execute("SELECT name FROM category ORDER BY display_order")
        return {"categories": [r["name"] for r in rows]}

    @app.post("/api/questions")
    def add_question(q: QuestionIn):
        g = models.get_game(db())
        if g["phase"] != "draft":
            raise HTTPException(status_code=409, detail="game already started")
        try:
            qid = models.add_question(db(), q.author, q.category, q.text, q.answer, q.acceptable)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"id": qid}

    @app.get("/api/questions/mine")
    def my_questions(author: str):
        rows = db().execute(
            "SELECT * FROM question WHERE author_name = ? ORDER BY id", (author,)
        ).fetchall()
        return {"questions": [public_question(r) for r in rows]}

    @app.get("/api/questions")
    def all_questions(host_key: str, _=Depends(lambda: None)):
        require_host(host_key)
        rows = db().execute("SELECT * FROM question ORDER BY id").fetchall()
        return {"questions": [host_question(r) for r in rows]}

    return app


app = create_app()
```

> Implementer note: simplify the duplicated `connect()` lines (they're shown defensively) to a single `conn = connect(db_path)` constructed with `check_same_thread=False` for file DBs — add a `check_same_thread=False` kwarg in `app/db.connect` when running under uvicorn. Keep the in-memory path single-connection for tests. The `_=Depends(...)` placeholder is unnecessary; pass `host_key` as a normal query param.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_contribute.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/serializers.py tests/test_api_contribute.py requirements.txt
git commit -m "feat: FastAPI app with contribute flow and role-filtered question serialization"
```

---

### Task 7: Lobby — team join, recovery, and leaderboard endpoints

**Files:**
- Modify: `app/main.py` (add routes inside `create_app`)
- Test: `tests/test_api_lobby.py`

**Interfaces:**
- Consumes: `app.models`, `app.scoring`.
- Produces routes:
  - `POST /api/teams` body `{name}` -> `{"team_id","name","recovery_code"}`; 409 on duplicate name.
  - `GET /api/teams` -> `{"teams":[{"id","name"}]}` (no recovery codes).
  - `GET /api/teams/recover?recovery_code=...` -> `{"team_id","name"}` or 404.
  - `GET /api/leaderboard` -> `{"teams":[{"team_id","name","total"}]}` (uses `scoring.team_totals`).

- [ ] **Step 1: Write the failing test** `tests/test_api_lobby.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.anyio
async def test_join_and_list_teams(client):
    r = await client.post("/api/teams", json={"name": "Beach Bums"})
    assert r.status_code == 200
    body = r.json()
    assert body["recovery_code"]

    dup = await client.post("/api/teams", json={"name": "beach bums"})
    assert dup.status_code == 409

    teams = await client.get("/api/teams")
    names = [t["name"] for t in teams.json()["teams"]]
    assert names == ["Beach Bums"]
    assert all("recovery_code" not in t for t in teams.json()["teams"])


@pytest.mark.anyio
async def test_recover_team(client):
    r = await client.post("/api/teams", json={"name": "Sandy"})
    rc = r.json()["recovery_code"]
    ok = await client.get("/api/teams/recover", params={"recovery_code": rc})
    assert ok.json()["name"] == "Sandy"
    bad = await client.get("/api/teams/recover", params={"recovery_code": "nope"})
    assert bad.status_code == 404


@pytest.mark.anyio
async def test_empty_leaderboard(client):
    await client.post("/api/teams", json={"name": "Sandy"})
    r = await client.get("/api/leaderboard")
    assert r.json()["teams"] == [{"team_id": 1, "name": "Sandy", "total": 0}]
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_api_lobby.py -v`
Expected: FAIL (404s — routes not defined).

- [ ] **Step 3: Add the routes to `create_app` in `app/main.py`**

```python
    from app import scoring  # add at top of file with other imports

    class TeamIn(BaseModel):
        name: str

    @app.post("/api/teams")
    def create_team(t: TeamIn):
        try:
            return models.join_team(db(), t.name)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.get("/api/teams")
    def list_teams():
        rows = db().execute("SELECT id, name FROM team ORDER BY id").fetchall()
        return {"teams": [{"id": r["id"], "name": r["name"]} for r in rows]}

    @app.get("/api/teams/recover")
    def recover_team(recovery_code: str):
        row = models.team_by_recovery(db(), recovery_code)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown recovery code")
        return {"team_id": row["id"], "name": row["name"]}

    @app.get("/api/leaderboard")
    def leaderboard():
        return {"teams": scoring.team_totals(db())}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_lobby.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api_lobby.py
git commit -m "feat: lobby endpoints — team join, recovery, leaderboard"
```

---

### Task 8: Game flow — round building, phase transitions, and current state

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_api_flow.py`

**Interfaces:**
- Consumes: `app.rounds`, `app.models`.
- Produces routes (all mutating ones host-only via `host_key`):
  - `POST /api/host/build-rounds?host_key=...` -> `{"rounds":[...], "warnings":[...]}` (calls `rounds.build_rounds` + `imbalance_warnings`).
  - `POST /api/host/phase?host_key=...` body `{phase, round_id?}` -> sets phase, and (when entering a round-open phase) `current_round_id`. Allowed phases listed in `VALID_PHASES`.
  - `POST /api/host/pause?host_key=...` body `{paused}` -> toggles pause.
  - `GET /api/state` -> role-appropriate snapshot every client polls: `{"phase","paused","current_round":{...}|null}`; when a round is open, includes that round's **public** questions (no answers). The single source of truth for reconnect.

- [ ] **Step 1: Write the failing test** `tests/test_api_flow.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


@pytest.mark.anyio
async def test_build_rounds_and_open(app_client):
    app, c = app_client
    hk = _hk(app)
    for i in range(3):
        await c.post("/api/questions", json={
            "author": "me", "category": "History", "text": f"q{i}", "answer": "a"})
    r = await c.post("/api/host/build-rounds", params={"host_key": hk})
    assert r.status_code == 200
    rounds = r.json()["rounds"]
    assert rounds and rounds[0]["title"] == "History"
    rid = rounds[0]["id"]

    # open the round
    p = await c.post("/api/host/phase", params={"host_key": hk},
                     json={"phase": "round_open", "round_id": rid})
    assert p.status_code == 200

    state = (await c.get("/api/state")).json()
    assert state["phase"] == "round_open"
    assert state["current_round"]["id"] == rid
    # questions exposed to players must NOT include answers
    qs = state["current_round"]["questions"]
    assert len(qs) == 3
    assert all("answer" not in q for q in qs)


@pytest.mark.anyio
async def test_phase_requires_host_key(app_client):
    app, c = app_client
    r = await c.post("/api/host/phase", params={"host_key": "x"}, json={"phase": "lobby"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_invalid_phase_rejected(app_client):
    app, c = app_client
    hk = _hk(app)
    r = await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "banana"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_pause_reflected_in_state(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/host/pause", params={"host_key": hk}, json={"paused": True})
    assert (await c.get("/api/state")).json()["paused"] is True
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_api_flow.py -v`
Expected: FAIL (routes missing).

- [ ] **Step 3: Add the routes to `app/main.py`**

```python
    from app import rounds as rounds_mod  # top of file

    VALID_PHASES = {
        "draft", "lobby", "round_open", "round_closed", "marking", "reveal",
        "final_wager", "final_open", "tiebreak", "done", "paused",
    }

    class PhaseIn(BaseModel):
        phase: str
        round_id: int | None = None

    class PauseIn(BaseModel):
        paused: bool

    def _round_public(round_id: int) -> dict | None:
        r = db().execute("SELECT * FROM round WHERE id = ?", (round_id,)).fetchone()
        if r is None:
            return None
        qs = db().execute(
            "SELECT * FROM question WHERE round_id = ? ORDER BY display_order", (round_id,)
        ).fetchall()
        return {
            "id": r["id"], "title": r["title"], "is_final": bool(r["is_final"]),
            "wager_cap": r["wager_cap"],
            "questions": [public_question(q) for q in qs],
        }

    @app.post("/api/host/build-rounds")
    def build(host_key: str):
        require_host(host_key)
        rs = rounds_mod.build_rounds(db())
        return {"rounds": rs, "warnings": rounds_mod.imbalance_warnings(db())}

    @app.post("/api/host/phase")
    def set_phase_route(body: PhaseIn, host_key: str):
        require_host(host_key)
        if body.phase not in VALID_PHASES:
            raise HTTPException(status_code=400, detail="unknown phase")
        models.set_phase(db(), body.phase)
        if body.round_id is not None:
            models.set_current_round(db(), body.round_id)
        return {"ok": True}

    @app.post("/api/host/pause")
    def pause_route(body: PauseIn, host_key: str):
        require_host(host_key)
        models.set_paused(db(), body.paused)
        return {"ok": True}

    @app.get("/api/state")
    def state():
        g = models.get_game(db())
        cur = _round_public(g["current_round_id"]) if g["current_round_id"] else None
        return {"phase": g["phase"], "paused": bool(g["paused"]), "current_round": cur}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_flow.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api_flow.py
git commit -m "feat: round building, phase transitions, and polled game state"
```

---

### Task 9: Submission upload, grading trigger, and host marking

**Files:**
- Modify: `app/main.py`
- Create: `uploads/.gitkeep`
- Test: `tests/test_api_marking.py`

**Interfaces:**
- Consumes: `app.grading`, `app.serializers`, `app.scoring`.
- Produces routes:
  - `POST /api/submit` (multipart: `team_id`, `round_id`, file `photo`) -> stores file under `uploads/`, upserts `submission`, runs `grading.grade_sheet` over that round's questions, writes one `mark` per question (score = `point_value` if `is_correct` else 0; `items_correct` passed through). **Rejected (409) unless the game phase allows submissions for that round** (`round_open`/`final_open`) — no late writes. Grading client is taken from `app.state.grading_client` if set (tests inject a fake).
  - `GET /api/host/marks?host_key=...&round_id=...` -> `{"teams":[{team, marks:[{question_id, transcription, is_correct, score, items_correct, flagged, photo_url}]}]}` — host marking view.
  - `POST /api/host/mark?host_key=...` body `{team_id, question_id, is_correct?, score?, items_correct?}` -> updates the mark, sets `manually_corrected=1`. Totals are always re-derived, never stored.
  - `POST /api/host/add-alternate?host_key=...` body `{question_id, alternate}` -> appends to `acceptable_answers`.

- [ ] **Step 1: Write the failing test** `tests/test_api_marking.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.grading import QuestionGrade, SheetGrade
from app.main import create_app


class FakeGrader:
    """Returns a fixed grade for whatever questions it is asked about."""
    def __init__(self, mapping):  # mapping: question_id -> (correct, items_correct)
        self.mapping = mapping

    def grade(self, image_bytes, media_type, questions):
        grades = []
        for q in questions:
            correct, items = self.mapping.get(q["id"], (False, None))
            grades.append(QuestionGrade(
                question_id=q["id"], transcription="x", is_correct=correct,
                confidence=0.9, items_correct=items))
        return SheetGrade(grades=grades)


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


async def _setup_open_round(app, c, hk):
    for i in range(2):
        await c.post("/api/questions", json={
            "author": "me", "category": "History", "text": f"q{i}", "answer": "a"})
    rounds = (await c.post("/api/host/build-rounds", params={"host_key": hk})).json()["rounds"]
    rid = rounds[0]["id"]
    t = (await c.post("/api/teams", json={"name": "Aces"})).json()
    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "round_open", "round_id": rid})
    return rid, t["team_id"]


@pytest.mark.anyio
async def test_submit_grades_and_scores(app_client):
    app, c = app_client
    hk = _hk(app)
    rid, team_id = await _setup_open_round(app, c, hk)
    qids = [q["id"] for q in (await c.get("/api/state")).json()["current_round"]["questions"]]
    app.state.grading_client = FakeGrader({qids[0]: (True, None), qids[1]: (False, None)})

    r = await c.post("/api/submit",
                     data={"team_id": str(team_id), "round_id": str(rid)},
                     files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 200
    # leaderboard reflects 1 correct answer (1 point)
    lb = (await c.get("/api/leaderboard")).json()["teams"]
    assert lb[0]["total"] == 1


@pytest.mark.anyio
async def test_submit_rejected_when_round_closed(app_client):
    app, c = app_client
    hk = _hk(app)
    rid, team_id = await _setup_open_round(app, c, hk)
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "round_closed"})
    r = await c.post("/api/submit",
                     data={"team_id": str(team_id), "round_id": str(rid)},
                     files={"photo": ("s.png", b"x", "image/png")})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_host_override_recomputes_total(app_client):
    app, c = app_client
    hk = _hk(app)
    rid, team_id = await _setup_open_round(app, c, hk)
    qids = [q["id"] for q in (await c.get("/api/state")).json()["current_round"]["questions"]]
    app.state.grading_client = FakeGrader({qids[0]: (False, None), qids[1]: (False, None)})
    await c.post("/api/submit", data={"team_id": str(team_id), "round_id": str(rid)},
                 files={"photo": ("s.png", b"x", "image/png")})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 0
    # host flips q0 to correct
    await c.post("/api/host/mark", params={"host_key": hk},
                 json={"team_id": team_id, "question_id": qids[0], "is_correct": True, "score": 1})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 1
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_api_marking.py -v`
Expected: FAIL (routes missing).

- [ ] **Step 3: Add upload + marking routes to `app/main.py`**

Key implementation points (write the actual code):
- Add `from fastapi import UploadFile, File, Form` and `import json, pathlib, time`.
- `UPLOAD_DIR = pathlib.Path(os.environ.get("TRIVIA_UPLOADS", "uploads"))`; `UPLOAD_DIR.mkdir(exist_ok=True)`.
- A grading shim so tests can inject a fake:

```python
    def _grade(image_bytes, media_type, questions):
        grader = getattr(app.state, "grading_client", None)
        if grader is not None:
            return grader.grade(image_bytes, media_type, questions)
        from app import grading
        return grading.grade_sheet(image_bytes, media_type, questions)

    SUBMIT_PHASES = {"round_open", "final_open"}

    @app.post("/api/submit")
    async def submit(team_id: int = Form(...), round_id: int = Form(...),
                     photo: UploadFile = File(...)):
        g = models.get_game(db())
        if g["phase"] not in SUBMIT_PHASES or g["current_round_id"] != round_id:
            raise HTTPException(status_code=409, detail="submissions closed for this round")
        data = await photo.read()
        ext = (photo.filename or "sheet.png").rsplit(".", 1)[-1]
        fname = f"team{team_id}_round{round_id}.{ext}"
        (UPLOAD_DIR / fname).write_bytes(data)
        db().execute(
            "INSERT INTO submission (team_id, round_id, photo_path) VALUES (?, ?, ?) "
            "ON CONFLICT(team_id, round_id) DO UPDATE SET photo_path=excluded.photo_path, "
            "submitted_at=datetime('now')",
            (team_id, round_id, fname))
        db().commit()

        rows = db().execute(
            "SELECT * FROM question WHERE round_id = ? ORDER BY display_order", (round_id,)
        ).fetchall()
        questions = [host_question(r) for r in rows]
        # grade_sheet expects keys id/text/answer/acceptable/answer_items/ordered
        qpayload = [{"id": q["id"], "text": q["text"], "answer": q["answer"],
                     "acceptable": q["acceptable_answers"], "answer_items": q["answer_items"],
                     "ordered": q["ordered"]} for q in questions]
        result = _grade(data, photo.content_type or "image/png", qpayload)

        by_id = {q["id"]: q for q in questions}
        for gr in result.grades:
            q = by_id.get(gr.question_id)
            if q is None:
                continue
            score = q["point_value"] if gr.is_correct else 0
            db().execute(
                "INSERT INTO mark (team_id, question_id, transcription, is_correct, score, "
                "items_correct, confidence, flagged) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(team_id, question_id) DO UPDATE SET transcription=excluded.transcription, "
                "is_correct=excluded.is_correct, score=excluded.score, items_correct=excluded.items_correct, "
                "confidence=excluded.confidence, flagged=excluded.flagged "
                "WHERE manually_corrected = 0",
                (team_id, gr.question_id, gr.transcription, int(gr.is_correct), score,
                 gr.items_correct, gr.confidence, int(gr.confidence < 0.5)))
        db().commit()
        return {"ok": True}

    @app.get("/api/host/marks")
    def host_marks(host_key: str, round_id: int):
        require_host(host_key)
        teams = db().execute("SELECT id, name FROM team ORDER BY id").fetchall()
        qids = [r["id"] for r in db().execute(
            "SELECT id FROM question WHERE round_id = ?", (round_id,))]
        out = []
        for t in teams:
            sub = db().execute(
                "SELECT photo_path FROM submission WHERE team_id=? AND round_id=?",
                (t["id"], round_id)).fetchone()
            marks = []
            for qid in qids:
                m = db().execute(
                    "SELECT * FROM mark WHERE team_id=? AND question_id=?",
                    (t["id"], qid)).fetchone()
                marks.append({
                    "question_id": qid,
                    "transcription": m["transcription"] if m else "",
                    "is_correct": bool(m["is_correct"]) if m else False,
                    "score": m["score"] if m else 0,
                    "items_correct": m["items_correct"] if m else None,
                    "flagged": bool(m["flagged"]) if m else False,
                    "submitted": sub is not None,
                })
            out.append({"team_id": t["id"], "name": t["name"],
                        "photo_url": f"/uploads/{sub['photo_path']}" if sub else None,
                        "marks": marks})
        return {"teams": out}

    class MarkIn(BaseModel):
        team_id: int
        question_id: int
        is_correct: bool | None = None
        score: float | None = None
        items_correct: int | None = None

    @app.post("/api/host/mark")
    def host_mark(body: MarkIn, host_key: str):
        require_host(host_key)
        existing = db().execute(
            "SELECT * FROM mark WHERE team_id=? AND question_id=?",
            (body.team_id, body.question_id)).fetchone()
        is_correct = body.is_correct if body.is_correct is not None else (
            bool(existing["is_correct"]) if existing else False)
        score = body.score if body.score is not None else (
            existing["score"] if existing else 0)
        db().execute(
            "INSERT INTO mark (team_id, question_id, is_correct, score, items_correct, "
            "manually_corrected) VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(team_id, question_id) DO UPDATE SET is_correct=?, score=?, "
            "items_correct=COALESCE(?, items_correct), manually_corrected=1",
            (body.team_id, body.question_id, int(is_correct), score, body.items_correct,
             int(is_correct), score, body.items_correct))
        db().commit()
        return {"ok": True}

    class AlternateIn(BaseModel):
        question_id: int
        alternate: str

    @app.post("/api/host/add-alternate")
    def add_alternate(body: AlternateIn, host_key: str):
        require_host(host_key)
        row = db().execute("SELECT acceptable_answers FROM question WHERE id=?",
                           (body.question_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such question")
        acc = json.loads(row["acceptable_answers"])
        if body.alternate not in acc:
            acc.append(body.alternate)
        db().execute("UPDATE question SET acceptable_answers=? WHERE id=?",
                     (json.dumps(acc), body.question_id))
        db().commit()
        return {"ok": True}
```

- Also mount static uploads for the host photo view: `from fastapi.staticfiles import StaticFiles; app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_marking.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api_marking.py uploads/.gitkeep
git commit -m "feat: photo submission, AI grading, and host marking with overrides"
```

---

### Task 10: Final round (wager + multi-item), tiebreaker, and CSV export

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_api_final.py`

**Interfaces:**
- Consumes: `app.scoring`.
- Produces routes:
  - `POST /api/host/final?host_key=...` body `{text, items: [str], ordered: bool, wager_cap: int}` -> creates a final round (`is_final=1`) plus its one multi-item question (`answer_items`), placed last in display order.
  - `POST /api/wager` body `{team_id, round_id, amount}` -> records a wager; **only while phase is `final_wager`**; clamps to `0..wager_cap`; upsert.
  - `POST /api/host/tiebreak?host_key=...` body `{question, value}` -> stores numeric tiebreak prompt/answer on the game.
  - `POST /api/tiebreak?team_id=...&value=...` -> records a team's numeric guess (reuses a `mark`-free table? No — store in `submission`-like manner). For v1 store tiebreak guesses in a small in-memory dict on `app.state.tiebreak_guesses` keyed by team_id (ephemeral is fine — tiebreaks are resolved live). `GET /api/host/tiebreak-result?host_key=...` returns guesses sorted by closeness to `game.tiebreak_value`.
  - `GET /api/host/export.csv?host_key=...` -> CSV: one row per team, columns per round + total.

- [ ] **Step 1: Write the failing test** `tests/test_api_final.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


@pytest.mark.anyio
async def test_final_wager_flow(app_client):
    app, c = app_client
    hk = _hk(app)
    t = (await c.post("/api/teams", json={"name": "Aces"})).json()
    f = await c.post("/api/host/final", params={"host_key": hk}, json={
        "text": "Order these films by release year",
        "items": ["A", "B", "C", "D", "E"], "ordered": True, "wager_cap": 10})
    rid = f.json()["round_id"]

    # wagers only accepted in final_wager phase
    early = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 10})
    assert early.status_code == 409

    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "final_wager", "round_id": rid})
    w = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 99})
    assert w.status_code == 200
    # clamped to cap
    amt = app.state.conn.execute("SELECT amount FROM wager WHERE team_id=?",
                                 (t["team_id"],)).fetchone()["amount"]
    assert amt == 10

    # host marks 4/5 correct on the final question -> +6
    qid = app.state.conn.execute("SELECT id FROM question WHERE round_id=?",
                                 (rid,)).fetchone()["id"]
    await c.post("/api/host/mark", params={"host_key": hk},
                 json={"team_id": t["team_id"], "question_id": qid,
                       "is_correct": True, "score": 0, "items_correct": 4})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 6


@pytest.mark.anyio
async def test_csv_export(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/teams", json={"name": "Aces"})
    r = await c.get("/api/host/export.csv", params={"host_key": hk})
    assert r.status_code == 200
    assert "team" in r.text.lower()
    assert "Aces" in r.text
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_api_final.py -v`
Expected: FAIL (routes missing).

- [ ] **Step 3: Add final-round, wager, tiebreak, and export routes to `app/main.py`**

```python
    import csv
    import io

    class FinalIn(BaseModel):
        text: str
        items: list[str]
        ordered: bool = False
        wager_cap: int = 10

    @app.post("/api/host/final")
    def create_final(body: FinalIn, host_key: str):
        require_host(host_key)
        (max_order,) = db().execute(
            "SELECT COALESCE(MAX(display_order), -1) FROM round").fetchone()
        cur = db().execute(
            "INSERT INTO round (title, display_order, is_final, wager_cap, bonus_multiplier) "
            "VALUES ('Final Round', ?, 1, ?, 1)", (max_order + 1, body.wager_cap))
        rid = cur.lastrowid
        db().execute(
            "INSERT INTO question (author_name, category_id, text, answer_items, ordered, "
            "round_id, point_value, display_order) "
            "VALUES ('host', (SELECT id FROM category ORDER BY display_order LIMIT 1), "
            "?, ?, ?, ?, 0, 0)",
            (body.text, json.dumps(body.items), int(body.ordered), rid))
        db().commit()
        return {"round_id": rid}

    class WagerIn(BaseModel):
        team_id: int
        round_id: int
        amount: int

    @app.post("/api/wager")
    def place_wager(body: WagerIn):
        g = models.get_game(db())
        if g["phase"] != "final_wager":
            raise HTTPException(status_code=409, detail="wagering closed")
        cap = db().execute("SELECT wager_cap FROM round WHERE id=?",
                           (body.round_id,)).fetchone()["wager_cap"] or 0
        amount = max(0, min(body.amount, cap))
        db().execute(
            "INSERT INTO wager (team_id, round_id, amount) VALUES (?, ?, ?) "
            "ON CONFLICT(team_id, round_id) DO UPDATE SET amount=excluded.amount",
            (body.team_id, body.round_id, amount))
        db().commit()
        return {"amount": amount}

    class TiebreakIn(BaseModel):
        question: str
        value: float

    @app.post("/api/host/tiebreak")
    def set_tiebreak(body: TiebreakIn, host_key: str):
        require_host(host_key)
        db().execute("UPDATE game SET tiebreak_question=?, tiebreak_value=? WHERE id=1",
                     (body.question, body.value))
        db().commit()
        app.state.tiebreak_guesses = {}
        return {"ok": True}

    @app.post("/api/tiebreak")
    def guess_tiebreak(team_id: int, value: float):
        guesses = getattr(app.state, "tiebreak_guesses", None)
        if guesses is None:
            guesses = app.state.tiebreak_guesses = {}
        guesses[team_id] = value
        return {"ok": True}

    @app.get("/api/host/tiebreak-result")
    def tiebreak_result(host_key: str):
        require_host(host_key)
        g = models.get_game(db())
        target = g["tiebreak_value"]
        guesses = getattr(app.state, "tiebreak_guesses", {})
        names = {t["id"]: t["name"] for t in db().execute("SELECT id, name FROM team")}
        ranked = sorted(
            ({"team_id": tid, "name": names.get(tid, "?"), "guess": v,
              "delta": abs(v - target)} for tid, v in guesses.items()),
            key=lambda x: x["delta"])
        return {"target": target, "ranked": ranked}

    @app.get("/api/host/export.csv")
    def export_csv(host_key: str):
        from fastapi.responses import PlainTextResponse
        require_host(host_key)
        rounds = db().execute(
            "SELECT id, title FROM round ORDER BY display_order").fetchall()
        totals = {t["team_id"]: t for t in scoring.team_totals(db())}
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["team"] + [r["title"] for r in rounds] + ["total"])
        for t in db().execute("SELECT id, name FROM team ORDER BY name").fetchall():
            row = [t["name"]]
            for r in rounds:
                if db().execute("SELECT is_final FROM round WHERE id=?",
                                (r["id"],)).fetchone()["is_final"]:
                    row.append(scoring._final_total(db(), t["id"], r["id"]))
                else:
                    s = db().execute(
                        "SELECT COALESCE(SUM(m.score),0) AS s FROM mark m "
                        "JOIN question q ON q.id=m.question_id "
                        "WHERE m.team_id=? AND q.round_id=?", (t["id"], r["id"])).fetchone()["s"]
                    bonus = db().execute("SELECT bonus_multiplier FROM round WHERE id=?",
                                         (r["id"],)).fetchone()["bonus_multiplier"]
                    row.append(s * bonus)
            row.append(totals.get(t["id"], {}).get("total", 0))
            w.writerow(row)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_final.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tasks 1–10).

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_api_final.py
git commit -m "feat: final round wager, tiebreaker, and CSV export"
```

---

### Task 11: Frontend — four views (contribute, host, play, display)

**Files:**
- Create: `static/index.html` (landing: links to the four views)
- Create: `static/contribute.html`
- Create: `static/host.html`
- Create: `static/play.html`
- Create: `static/display.html`
- Create: `static/app.css`
- Modify: `app/main.py` (mount `static/` at `/`)
- Test: `tests/test_static.py`

**Interfaces:**
- Consumes: every `/api/*` route from Tasks 6–10.
- Produces: four self-contained HTML pages using vanilla `fetch` + `setInterval` polling (2.5s) of `/api/state` and `/api/leaderboard`. No build step, no external CDNs (per the house design constraints — inline CSS in `app.css`, no remote assets).

**Design:** Apply the **artifact-design** house style for the visual treatment (color tokens, type, spacing) — this is the one place to invoke it. Keep it a beach/summer trivia theme. Keep all four pages skimmable on a phone.

Page responsibilities:
- **contribute.html**: enter name → pick category (from `/api/categories`) → type question + answer + optional alternates → submit (`POST /api/questions`) ×3. Shows a running list of *your* submitted question texts (`/api/questions/mine`) — never answers.
- **play.html**: join (`POST /api/teams`, store `recovery_code` + `team_id` in `localStorage`); a "rejoin" box using `/api/teams/recover`. Polls `/api/state`; in `round_open`/`final_open` shows the question list and a camera file input (`<input type="file" accept="image/*" capture="environment">`) → `POST /api/submit`. In `final_wager` shows a wager slider (0..cap) → `POST /api/wager`. Shows own rank from `/api/leaderboard`.
- **host.html**: host key field (stored in `localStorage`). Buttons: build rounds, advance phase (per the phase list), open a chosen round, pause/resume, create final round (text + items + cap), set tiebreak. Marking panel: `/api/host/marks?round_id=` showing each team's photo + per-question transcription with correct/incorrect toggle, score box, items-correct box (for the final), and add-alternate. Live leaderboard.
- **display.html**: read-only, big text. Polls `/api/state` + `/api/leaderboard`. Lobby → join code + team list; round_open → round title + questions; reveal/done → leaderboard.

- [ ] **Step 1: Write the failing test** `tests/test_static.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.anyio
@pytest.mark.parametrize("path", [
    "/", "/contribute.html", "/host.html", "/play.html", "/display.html",
])
async def test_static_pages_served(client, path):
    r = await client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_static.py -v`
Expected: FAIL (404 — static not mounted).

- [ ] **Step 3: Build the pages and mount static**

- Write the five HTML files + `app.css` per the responsibilities above. Use the artifact-design skill for the visual layer. Each page is plain HTML with a `<script>` block doing `fetch`/poll. Store `host_key`, `team_id`, `recovery_code` in `localStorage`.
- In `app/main.py`, after all API routes (so `/api/*` wins) and after the `/uploads` mount, add:

```python
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

- [ ] **Step 4: Run the static test to verify it passes**

Run: `python -m pytest tests/test_static.py -v`
Expected: PASS (5 parametrized).

- [ ] **Step 5: Manual smoke check (local)**

Run: `ANTHROPIC_API_KEY=dummy GRADING_MODEL=claude-haiku-4-5 uvicorn app.main:app --port 8000`
Then open `http://localhost:8000/` and click through each view; note the printed game code + host key from stdout. (Real grading needs a valid key; UI/flow can be exercised without one until a photo is submitted.)

- [ ] **Step 6: Commit**

```bash
git add static/ app/main.py tests/test_static.py
git commit -m "feat: contribute, host, play, and display web views"
```

---

### Task 12: Deploy to a sprite + run docs

**Files:**
- Create: `deploy/run.sh` (start the server: `uvicorn app.main:app --host 0.0.0.0 --port 3000`)
- Create: `deploy/deploy.md` (the exact sprite steps)
- Modify: `README.md` (local-run + deploy quickstart)
- Modify: `app/db.py` (add `check_same_thread=False` for file-backed connections)

**Interfaces:**
- Consumes: the whole app.
- Produces: a documented path to run on a sprite, listening on `:3000` (the sprite's web-service port), with `ANTHROPIC_API_KEY` set in the sprite env and the SQLite file + `uploads/` on the sprite's persistent disk.

- [ ] **Step 1: Make file DB connections thread-safe**

In `app/db.connect`, when `path != ":memory:"`, pass `check_same_thread=False` to `sqlite3.connect`. Re-run `python -m pytest -v` — Expected: still PASS (in-memory tests unaffected).

- [ ] **Step 2: Write `deploy/run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export TRIVIA_DB="${TRIVIA_DB:-/data/trivia.db}"
export TRIVIA_UPLOADS="${TRIVIA_UPLOADS:-/data/uploads}"
mkdir -p "$(dirname "$TRIVIA_DB")" "$TRIVIA_UPLOADS"
exec uvicorn app.main:app --host 0.0.0.0 --port 3000
```

- [ ] **Step 3: Write `deploy/deploy.md`** with the verified sprite steps

```markdown
# Deploy to a sprite

1. Create the sprite:        `sprite create sum-beach-trivia`
2. Push the code:            `sprite file ./ sum-beach-trivia:/app` (or git clone inside via `sprite console`)
3. In `sprite console`:
   - `cd /app && pip install -r requirements.txt`
   - Set the key: add `ANTHROPIC_API_KEY=...` (and optional `GRADING_MODEL=claude-haiku-4-5`) to the sprite env.
   - `bash deploy/run.sh` (persistent disk at /data keeps the DB + photos across sleeps)
4. Register the web service on port 3000 and make it public: `sprite url` to get the public URL.
5. Open the public URL; the server prints the game code + HOST KEY on first start (read it from the console/log).
```

> Implementer: verify exact `sprite` subcommands against `sprite --help` at deploy time; the CLI is installed. Adjust file-push vs git-clone to whichever is simpler on the day.

- [ ] **Step 4: Update `README.md`** with local-run and the deploy pointer

Add a "Run locally" block (`pip install -r requirements.txt`; `ANTHROPIC_API_KEY=... uvicorn app.main:app --port 8000`) and a "Deploy" section pointing at `deploy/deploy.md`. Note the game code + host key are printed to stdout on first start.

- [ ] **Step 5: Final full-suite run**

Run: `python -m pytest -v`
Expected: PASS (entire suite).

- [ ] **Step 6: Commit**

```bash
git add deploy/ README.md app/db.py
git commit -m "feat: sprite deploy script, run docs, and thread-safe DB connection"
```

---

## Post-implementation

- Run `ponytail-review` over the diff to strip any over-engineering before finishing the branch.
- Manual game-night dry run on the sprite (two phones + laptop + TV view) before the real night.
