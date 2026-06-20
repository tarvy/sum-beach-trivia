import pytest

from app.scoring import final_round_delta, team_totals


@pytest.mark.parametrize("amount,correct,total,expected", [
    (10, 5, 5, 10),     # all right -> +full
    (10, 4, 5, 6),      # 2*0.8-1 = 0.6 -> 6
    (10, 3, 5, 2),      # 2*0.6-1 = 0.2 -> 2
    (10, 2, 5, -2),     # 2*0.4-1 = -0.2 -> -2
    (10, 0, 5, -10),    # all wrong -> -full
    (10, 0, 0, -10),    # no items defined -> treat as f=0
    (0, 3, 5, 0),       # zero wager -> 0
])
def test_final_round_delta(amount, correct, total, expected):
    assert final_round_delta(amount, correct, total) == expected


def _seed_basic_game(db):
    db.execute("INSERT INTO game (id, code, host_key) VALUES (1, 'ABCD', 'k')")
    db.execute("INSERT INTO round (id, title, category_id, display_order, bonus_multiplier) "
               "VALUES (1, 'History', 1, 0, 1)")
    db.execute("INSERT INTO round (id, title, category_id, display_order, bonus_multiplier) "
               "VALUES (2, 'Double Sports', 4, 1, 2)")
    db.execute("INSERT INTO question (id, author_name, category_id, text, answer, round_id, display_order) "
               "VALUES (1, 'me', 1, 'q1', 'a', 1, 0)")
    db.execute("INSERT INTO question (id, author_name, category_id, text, answer, round_id, display_order) "
               "VALUES (2, 'me', 4, 'q2', 'a', 2, 0)")
    db.execute("INSERT INTO team (id, name, name_lower, recovery_code) VALUES (1, 'Aces', 'aces', 'r1')")
    db.execute("INSERT INTO team (id, name, name_lower, recovery_code) VALUES (2, 'Bees', 'bees', 'r2')")
    db.commit()


def test_team_totals_basic_and_bonus(db):
    _seed_basic_game(db)
    # Aces: 1 pt in round 1, 1 pt in round 2 (x2 bonus) = 1 + 2 = 3
    db.execute("INSERT INTO mark (team_id, question_id, score) VALUES (1, 1, 1)")
    db.execute("INSERT INTO mark (team_id, question_id, score) VALUES (1, 2, 1)")
    # Bees: nothing scored
    db.commit()
    totals = team_totals(db)
    by_name = {t["name"]: t["total"] for t in totals}
    assert by_name == {"Aces": 3, "Bees": 0}
    assert totals[0]["name"] == "Aces"  # sorted desc


def test_team_totals_corrections_cascade(db):
    _seed_basic_game(db)
    db.execute("INSERT INTO mark (team_id, question_id, score) VALUES (1, 1, 1)")
    db.commit()
    assert {t["name"]: t["total"] for t in team_totals(db)}["Aces"] == 1
    # host fixes the mark down to 0 -> total recomputes
    db.execute("UPDATE mark SET score = 0 WHERE team_id = 1 AND question_id = 1")
    db.commit()
    assert {t["name"]: t["total"] for t in team_totals(db)}["Aces"] == 0


def test_team_totals_final_round_wager(db):
    _seed_basic_game(db)
    db.execute("UPDATE round SET is_final = 1, wager_cap = 10 WHERE id = 2")
    db.execute("UPDATE question SET answer_items = '[\"a\",\"b\",\"c\",\"d\",\"e\"]', ordered = 1 WHERE id = 2")
    db.execute("INSERT INTO wager (team_id, round_id, amount) VALUES (1, 2, 10)")
    db.execute("INSERT INTO mark (team_id, question_id, items_correct, score) VALUES (1, 2, 4, 0)")
    db.commit()
    # final delta for Aces: amount 10, 4/5 -> +6 ; no points from round 1
    assert {t["name"]: t["total"] for t in team_totals(db)}["Aces"] == 6
