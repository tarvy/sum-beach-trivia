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
