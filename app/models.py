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


def _require_complete(text, answer):
    # Trust boundary: a provided question needs Question + Answer (category is
    # validated by _category_id, which raises on anything off the standard list).
    if not (text or "").strip():
        raise ValueError("Question text required")
    if not (answer or "").strip():
        raise ValueError("Answer required")


def add_question(conn, author_name, category_name, text, answer, acceptable=None,
                 contributor_id=None) -> int:
    _require_complete(text, answer)
    cat_id = _category_id(conn, category_name)
    cur = conn.execute(
        "INSERT INTO question (author_name, category_id, text, answer, acceptable_answers, "
        "contributor_id) VALUES (?, ?, ?, ?, ?, ?)",
        (author_name, cat_id, text, answer, json.dumps(acceptable or []), contributor_id),
    )
    conn.commit()
    return cur.lastrowid


def update_question(conn, question_id, contributor_id, category_name, text, answer,
                    acceptable=None) -> bool:
    """Replace an existing question in place. Returns False if it isn't owned by
    this contributor (so the route can 404/403). Edits the set, never grows it."""
    row = conn.execute(
        "SELECT contributor_id FROM question WHERE id = ?", (question_id,)
    ).fetchone()
    if row is None or row["contributor_id"] != contributor_id:
        return False
    _require_complete(text, answer)
    cat_id = _category_id(conn, category_name)
    conn.execute(
        "UPDATE question SET category_id=?, text=?, answer=?, acceptable_answers=? WHERE id=?",
        (cat_id, text, answer, json.dumps(acceptable or []), question_id),
    )
    conn.commit()
    return True


def submit_question_set(conn, contributor_id, author_name, questions) -> list[int]:
    """Atomic set submission: 3 required, 5 max, each complete with a valid
    category. Replaces the contributor's existing set. Raises ValueError on any
    rule violation so the route returns 400 (the form's HTML5 rules mirror this,
    but the server is the trust boundary)."""
    if not (3 <= len(questions) <= 5):
        raise ValueError("Provide between 3 and 5 questions")
    for q in questions:  # validate all before writing anything
        _require_complete(q.get("text"), q.get("answer"))
        _category_id(conn, q.get("category"))
    conn.execute("DELETE FROM question WHERE contributor_id = ?", (contributor_id,))
    ids = []
    for q in questions:
        cat_id = _category_id(conn, q["category"])
        cur = conn.execute(
            "INSERT INTO question (author_name, category_id, text, answer, "
            "acceptable_answers, contributor_id) VALUES (?, ?, ?, ?, ?, ?)",
            (author_name, cat_id, q["text"], q["answer"],
             json.dumps(q.get("acceptable") or []), contributor_id),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def set_submissions_open(conn, is_open: bool) -> None:
    conn.execute("UPDATE game SET submissions_open = ? WHERE id = 1", (1 if is_open else 0,))
    conn.commit()


def resolve_contributor(conn, token: str, name: str) -> dict:
    """Identity = browser token. Upsert by token; name is an editable label."""
    token = (token or "").strip()
    name = (name or "").strip()
    if not token:
        raise ValueError("Token required")
    if not name:
        raise ValueError("Name required")
    row = conn.execute("SELECT * FROM contributor WHERE token = ?", (token,)).fetchone()
    if row is None:
        recovery = gen_recovery()
        cur = conn.execute(
            "INSERT INTO contributor (token, name, recovery_code) VALUES (?, ?, ?)",
            (token, name, recovery),
        )
        conn.commit()
        return {"contributor_id": cur.lastrowid, "name": name, "recovery_code": recovery}
    if name != row["name"]:
        conn.execute("UPDATE contributor SET name = ? WHERE id = ?", (name, row["id"]))
        conn.commit()
    return {"contributor_id": row["id"], "name": name, "recovery_code": row["recovery_code"]}


def contributor_by_recovery(conn, recovery_code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM contributor WHERE recovery_code = ?", (recovery_code,)
    ).fetchone()


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
