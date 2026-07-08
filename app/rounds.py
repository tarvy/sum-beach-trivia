from __future__ import annotations

import math
import random
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


_UNSET = object()  # "read the setting from the game row" vs an explicit None


def _game_settings(conn: sqlite3.Connection, target_size, max_rounds):
    """Resolve target_size / max_rounds from args, falling back to the game row."""
    game = conn.execute(
        "SELECT questions_per_person, questions_per_round, max_rounds "
        "FROM game WHERE id = 1").fetchone()
    n_keep = game["questions_per_person"] if game else 5
    if target_size is None:
        target_size = game["questions_per_round"] if game else 5
    if max_rounds is _UNSET:
        max_rounds = game["max_rounds"] if game else None
    return n_keep, target_size, max_rounds


def _consolidate(buckets: list[dict], max_rounds: int) -> list[dict]:
    """Meet a round cap by repeatedly merging the two smallest buckets. Every
    question stays in play (nothing benched); merged buckets lose their single
    category (→ Mixed Bag) and may exceed target_size — that is the honest cost
    of forcing fewer rounds than the categories naturally make."""
    buckets = [dict(b) for b in buckets]
    while len(buckets) > max_rounds:
        buckets.sort(key=lambda b: len(b["qids"]))
        a, b = buckets.pop(0), buckets.pop(0)
        cat = a["category_id"] if a["category_id"] == b["category_id"] else None
        buckets.append({"category_id": cat, "qids": sorted(a["qids"] + b["qids"])})
    return buckets


def _number_titles(buckets: list[dict], cat_names: dict[int, str],
                   cat_rank: dict[int, int]) -> list[dict]:
    """Order buckets (named categories by display_order, Mixed Bag last) and
    assign display titles with roman numerals for repeats."""
    named = sorted((b for b in buckets if b["category_id"] is not None),
                   key=lambda b: cat_rank.get(b["category_id"], 999))
    mixed = [b for b in buckets if b["category_id"] is None]
    groups: list[dict] = []
    seen: dict[int, int] = {}
    for b in named:
        cid = b["category_id"]
        idx = seen.get(cid, 0)
        seen[cid] = idx + 1
        groups.append({"title": _title(cat_names[cid], idx),
                       "category_id": cid, "qids": b["qids"]})
    for i, b in enumerate(mixed):
        groups.append({"title": _title("Mixed Bag", i),
                       "category_id": None, "qids": b["qids"]})
    return groups


def _assemble(conn: sqlite3.Connection, target_size: int, max_rounds,
              rng: random.Random | None) -> tuple[list[dict], dict]:
    """READ-ONLY. Compute the round groups from the current questions + settings
    without writing anything. Returns (groups, meta) where each group is
    {title, category_id, qids} and meta carries {natural_rounds, capped}.

    Selection: keep n_keep RANDOM questions of each contributor (>= 1 each; all
    kept if they submitted <= n_keep). Shaping: per-category rounds of target_size
    (oversized split evenly, undersized topped from same-category bank else pooled
    into Mixed Bag). Then, if max_rounds is set and exceeded, consolidate."""
    rng = rng or random
    n_keep = conn.execute(
        "SELECT questions_per_person FROM game WHERE id = 1").fetchone()
    n_keep = n_keep["questions_per_person"] if n_keep else 5
    # Candidate = contributor questions not tied to a final round (build detaches
    # non-final rounds only after this read, so include their questions here too).
    non_final = ("(round_id IS NULL OR round_id IN "
                 "(SELECT id FROM round WHERE is_final = 0))")

    by_contrib: dict[int, list[tuple[int, int]]] = {}
    selected: list[tuple[int, int]] = []
    for q in conn.execute(
        "SELECT id, category_id, contributor_id FROM question "
        f"WHERE source = 'contributor' AND {non_final} ORDER BY id"
    ):
        if q["contributor_id"] is None:
            selected.append((q["id"], q["category_id"]))  # legacy: always kept
        else:
            by_contrib.setdefault(q["contributor_id"], []).append(
                (q["id"], q["category_id"]))
    for qs in by_contrib.values():
        selected += qs if len(qs) <= n_keep else rng.sample(qs, n_keep)

    selected_by_cat: dict[int, list[int]] = {}
    for qid, cat_id in selected:
        selected_by_cat.setdefault(cat_id, []).append(qid)
    for lst in selected_by_cat.values():
        lst.sort()

    used_bank: set[int] = set()  # track in memory so this stays read-only

    def bank_fill(n: int, category_id: int | None = None) -> list[int]:
        if n <= 0:
            return []
        sql = ("SELECT id FROM question WHERE source IN ('bank', 'host') "
               f"AND {non_final}")
        args: list = []
        if category_id is not None:
            sql += " AND category_id = ?"
            args.append(category_id)
        rows = conn.execute(sql + " ORDER BY id", args).fetchall()
        picked = [r["id"] for r in rows if r["id"] not in used_bank][:n]
        used_bank.update(picked)
        return picked

    cat_names: dict[int, str] = {}
    cat_rank: dict[int, int] = {}
    buckets: list[dict] = []
    mixed_pool: list[int] = []
    for rank, cat in enumerate(
            conn.execute("SELECT id, name FROM category ORDER BY display_order")):
        cat_names[cat["id"]] = cat["name"]
        cat_rank[cat["id"]] = rank
        qids = list(selected_by_cat.get(cat["id"], []))
        if not qids:
            continue  # bank-only categories don't become rounds
        if len(qids) < target_size:
            qids += bank_fill(target_size - len(qids), cat["id"])
            if len(qids) < target_size:  # still short → pool into Mixed Bag
                mixed_pool += qids
                continue
        n_rounds = math.ceil(len(qids) / target_size)
        base, rem = divmod(len(qids), n_rounds)
        start = 0
        for i in range(n_rounds):
            size = base + (i < rem)
            buckets.append({"category_id": cat["id"],
                            "qids": sorted(qids[start:start + size])})
            start += size

    mixed_pool.sort()
    mixed_chunks = [mixed_pool[s:s + target_size]
                    for s in range(0, len(mixed_pool), target_size)]
    if mixed_chunks and len(mixed_chunks[-1]) < _MIN_MIXED:
        mixed_chunks[-1] = mixed_chunks[-1] + bank_fill(
            target_size - len(mixed_chunks[-1]))
    for chunk in mixed_chunks:
        buckets.append({"category_id": None, "qids": sorted(chunk)})

    natural = len(buckets)
    capped = bool(max_rounds) and natural > max_rounds
    if capped:
        buckets = _consolidate(buckets, max_rounds)
    groups = _number_titles(buckets, cat_names, cat_rank)
    return groups, {"natural_rounds": natural, "capped": capped}


def build_rounds(conn: sqlite3.Connection, target_size: int | None = None,
                 max_rounds=_UNSET, rng: random.Random | None = None) -> list[dict]:
    """Rebuild all non-final rounds from scratch. Never touches is_final rounds
    or their questions.

    target_size / max_rounds default to game.questions_per_round /
    game.max_rounds when omitted (tests override them). See `_assemble` for the
    selection + shaping rules; pass rng (a random.Random) for a deterministic
    pick in tests. Non-selected contributor questions stay stored (round_id NULL).
    """
    _, target_size, max_rounds = _game_settings(conn, target_size, max_rounds)
    try:
        # Assemble first (read-only), THEN detach/delete old non-final rounds and
        # write the new ones — so a mid-build failure rolls back cleanly.
        groups, _meta = _assemble(conn, target_size, max_rounds, rng)
        conn.execute(
            "UPDATE question SET round_id = NULL WHERE round_id IN "
            "(SELECT id FROM round WHERE is_final = 0)")
        conn.execute("DELETE FROM round WHERE is_final = 0")
        for order, g in enumerate(groups):
            cur = conn.execute(
                "INSERT INTO round (title, category_id, display_order, bonus_multiplier) "
                "VALUES (?, ?, ?, 1)", (g["title"], g["category_id"], order))
            for d, qid in enumerate(g["qids"]):  # within a round: id order
                conn.execute(
                    "UPDATE question SET round_id = ?, display_order = ? WHERE id = ?",
                    (cur.lastrowid, d, qid))
        conn.commit()
    except Exception:
        conn.rollback()  # a failed build must not hold the write lock
        raise
    return _round_summaries(conn)


def plan_preview(conn: sqlite3.Connection, target_size: int | None = None,
                 max_rounds=_UNSET) -> dict:
    """READ-ONLY "quick math" for the host setup screen: what the game would look
    like if built right now with the given (or current) settings. Never writes.

    The selection is seeded for a stable preview across polls; the real build
    reshuffles, so the round count is an estimate when the per-person cap benches
    questions across categories."""
    n_keep, target_size, max_rounds = _game_settings(conn, target_size, max_rounds)
    groups, meta = _assemble(conn, target_size, max_rounds, random.Random(0))

    # Contributor tallies (deterministic — counts only, not which questions).
    by_contrib: dict[int, int] = {}
    by_cat_submitted: dict[int, int] = {}
    for q in conn.execute(
        "SELECT category_id, contributor_id FROM question WHERE source = 'contributor'"
    ):
        by_cat_submitted[q["category_id"]] = by_cat_submitted.get(q["category_id"], 0) + 1
        if q["contributor_id"] is not None:
            by_contrib[q["contributor_id"]] = by_contrib.get(q["contributor_id"], 0) + 1
    submitted = sum(by_cat_submitted.values())
    legacy = conn.execute(
        "SELECT COUNT(*) FROM question WHERE source = 'contributor' "
        "AND contributor_id IS NULL").fetchone()[0]
    # kept = per-person cap applied to each contributor, plus always-kept legacy
    selected = sum(min(k, n_keep) for k in by_contrib.values()) + legacy
    benched = submitted - selected
    in_play = sum(len(g["qids"]) for g in groups)
    own_round_cats = {g["category_id"] for g in groups if g["category_id"] is not None}

    cats = {r["id"]: r["name"]
            for r in conn.execute("SELECT id, name FROM category")}
    by_category = [
        {"name": cats.get(cid, "?"), "submitted": n,
         "own_round": cid in own_round_cats}
        for cid, n in sorted(by_cat_submitted.items(),
                             key=lambda kv: -kv[1]) if n]

    flags: list[dict] = []
    if submitted == 0:
        flags.append({"level": "warn", "msg": "No questions submitted yet."})
    for c in by_category:
        if not c["own_round"]:
            flags.append({"level": "warn",
                          "msg": f"“{c['name']}” is too thin for its own round "
                                 "— it goes in the Mixed Bag."})
    if benched > 0:
        flags.append({"level": "info",
                      "msg": f"Keeping {n_keep} per person benches {benched} "
                             f"extra question{'s' if benched != 1 else ''}."})
    if meta["capped"]:
        flags.append({"level": "info",
                      "msg": f"Capped at {max_rounds} rounds — smaller categories "
                             "merged into the Mixed Bag."})
        if any(len(g["qids"]) > target_size for g in groups):
            flags.append({"level": "warn",
                          "msg": f"Some rounds are larger than {target_size} "
                                 "questions to meet the round cap."})

    return {
        "contributors": len(by_contrib),
        "submitted": submitted,
        "in_play": in_play,
        "benched": benched,
        "rounds": len(groups),
        "target_size": target_size,
        "max_rounds": max_rounds,
        "natural_rounds": meta["natural_rounds"],
        "by_category": by_category,
        "round_titles": [{"title": g["title"], "count": len(g["qids"])} for g in groups],
        "flags": flags,
    }


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
