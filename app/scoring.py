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
