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
