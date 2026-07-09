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
    game_cols = {r["name"] for r in conn.execute("PRAGMA table_info(game)")}
    submission_cols = {r["name"] for r in conn.execute("PRAGMA table_info(submission)")}
    assert "gladys_level" in game_cols
    assert "gladys_quip" in submission_cols


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
