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
        "source": row["source"],
        "round_id": row["round_id"],
    })
    return d
