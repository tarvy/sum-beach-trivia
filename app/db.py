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
