from __future__ import annotations

import math
import sqlite3

_MIN_MIXED = 3  # a Mixed Bag round smaller than this pulls any-category bank fill


def _roman(n: int) -> str:
    out = ""
    for v, s in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


def _title(name: str, idx: int) -> str:
    return name if idx == 0 else f"{name} {_roman(idx + 1)}"


def build_rounds(conn: sqlite3.Connection, target_size: int = 5) -> list[dict]:
    """Rebuild all non-final rounds from scratch. Idempotent; never touches
    is_final rounds or their questions.

    Selection: keep the FIRST game.questions_per_person questions of each
    contributor (by id = submission order) — so everyone who submitted gets at
    least their first question in. Non-selected questions stay stored with
    round_id NULL. source in ('bank','host') questions are filler only, never
    guaranteed.

    Shaping: every category is a round of exactly target_size; oversized
    categories split as evenly as possible ("History" / "History II");
    undersized ones top up from same-category bank/host (oldest first) or,
    still short, pool into "Mixed Bag" round(s) at the end.
    """
    try:
        # Detach questions from non-final rounds, then delete those rounds.
        conn.execute(
            "UPDATE question SET round_id = NULL WHERE round_id IN "
            "(SELECT id FROM round WHERE is_final = 0)"
        )
        conn.execute("DELETE FROM round WHERE is_final = 0")

        game = conn.execute("SELECT questions_per_person FROM game WHERE id = 1").fetchone()
        n_keep = game["questions_per_person"] if game else 5

        # Keep the first n_keep per contributor. Legacy questions with no
        # contributor link can't be capped per-person, so they're always kept.
        selected_by_cat: dict[int, list[int]] = {}
        kept: dict[int, int] = {}
        for q in conn.execute(
            "SELECT id, category_id, contributor_id FROM question "
            "WHERE round_id IS NULL AND source = 'contributor' ORDER BY id"
        ):
            cid = q["contributor_id"]
            if cid is not None:
                kept[cid] = kept.get(cid, 0) + 1
                if kept[cid] > n_keep:
                    continue  # non-destructive: stays stored, just unselected
            selected_by_cat.setdefault(q["category_id"], []).append(q["id"])

        def bank_fill(n: int, category_id: int | None = None, exclude=()) -> list[int]:
            """Oldest unassigned bank/host questions, optionally same-category."""
            sql = ("SELECT id FROM question WHERE round_id IS NULL "
                   "AND source IN ('bank', 'host')")
            args: list = []
            if category_id is not None:
                sql += " AND category_id = ?"
                args.append(category_id)
            rows = conn.execute(sql + " ORDER BY id", args).fetchall()
            return [r["id"] for r in rows if r["id"] not in exclude][:n]

        order = 0

        def make_round(title: str, category_id: int | None, qids: list[int]) -> None:
            nonlocal order
            cur = conn.execute(
                "INSERT INTO round (title, category_id, display_order, bonus_multiplier) "
                "VALUES (?, ?, ?, 1)", (title, category_id, order))
            for d, qid in enumerate(sorted(qids)):  # within a round: id order
                conn.execute(
                    "UPDATE question SET round_id = ?, display_order = ? WHERE id = ?",
                    (cur.lastrowid, d, qid))
            order += 1

        mixed_pool: list[int] = []
        for cat in conn.execute("SELECT id, name FROM category ORDER BY display_order"):
            qids = selected_by_cat.get(cat["id"], [])
            if not qids:
                continue  # bank-only categories don't become rounds
            if len(qids) < target_size:
                qids += bank_fill(target_size - len(qids), cat["id"])
                if len(qids) < target_size:  # still short → pool into Mixed Bag
                    mixed_pool += qids
                    continue
            # split as evenly as possible, each chunk <= target_size (7 → 4+3)
            n_rounds = math.ceil(len(qids) / target_size)
            base, rem = divmod(len(qids), n_rounds)
            start = 0
            for i in range(n_rounds):
                size = base + (i < rem)
                make_round(_title(cat["name"], i), cat["id"], qids[start:start + size])
                start += size

        # Mixed Bag round(s) of up to target_size; only the last may be small,
        # and if it would have < _MIN_MIXED questions, top it up from ANY bank.
        mixed_pool.sort()
        for i, start in enumerate(range(0, len(mixed_pool), target_size)):
            chunk = mixed_pool[start:start + target_size]
            if len(chunk) < _MIN_MIXED:
                chunk += bank_fill(target_size - len(chunk), exclude=chunk)
            make_round(_title("Mixed Bag", i), None, chunk)

        conn.commit()
    except Exception:
        conn.rollback()  # a failed build must not hold the write lock
        raise
    return _round_summaries(conn)


def _round_summaries(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT r.id, r.title, c.name AS category, "
        "(SELECT COUNT(*) FROM question q WHERE q.round_id = r.id) AS question_count "
        "FROM round r LEFT JOIN category c ON c.id = r.category_id "
        "WHERE r.is_final = 0 ORDER BY r.display_order"
    ).fetchall()
    return [dict(r) for r in rows]


def imbalance_warnings(conn: sqlite3.Connection) -> list[str]:
    """Post-build sanity warnings (call after build_rounds).

    Non-final rounds with category_id NULL are the Mixed Bag rounds.
    """
    warnings: list[str] = []
    # Safety net: every contributor with a question is guaranteed a slot.
    for r in conn.execute(
        "SELECT c.name FROM contributor c WHERE "
        "EXISTS (SELECT 1 FROM question q WHERE q.contributor_id = c.id) AND NOT EXISTS "
        "(SELECT 1 FROM question q WHERE q.contributor_id = c.id AND q.round_id IS NOT NULL) "
        "ORDER BY c.id"
    ):
        warnings.append(f"Contributor '{r['name']}' has no questions in the game.")
    # Categories that couldn't fill a round (not enough bank) → went to Mixed Bag.
    for r in conn.execute(
        "SELECT c.name FROM question q JOIN category c ON c.id = q.category_id "
        "JOIN round r ON r.id = q.round_id "
        "WHERE r.is_final = 0 AND r.category_id IS NULL AND q.source = 'contributor' "
        "GROUP BY c.id ORDER BY c.display_order"
    ):
        warnings.append(
            f"Category '{r['name']}' didn't have enough questions for its own round "
            "— moved to Mixed Bag.")
    # A Mixed Bag round that stayed small means the bank ran dry too.
    for r in conn.execute(
        "SELECT r.title, COUNT(q.id) AS n FROM round r "
        "LEFT JOIN question q ON q.round_id = r.id "
        "WHERE r.is_final = 0 AND r.category_id IS NULL "
        "GROUP BY r.id HAVING n < ?", (_MIN_MIXED,)
    ):
        warnings.append(
            f"Round '{r['title']}' has only {r['n']} question(s) and no bank "
            "questions were left to fill it.")
    return warnings
