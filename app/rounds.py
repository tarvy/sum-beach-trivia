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
