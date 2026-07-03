"""Round builder v2 (2026-07 rebuild, feedback item B).

Old tests encoded the v1 semantics (every thin category became its own round;
12 questions split 5+5+2 by striding) and were deliberately rewritten:
- selection now keeps the FIRST game.questions_per_person questions per
  contributor (id = submission order); bank/host questions are filler only
- rounds target exactly 5; oversized categories split as evenly as possible
  (7 -> 4+3); undersized ones top up from same-category bank or pool into
  "Mixed Bag" round(s) at the end
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app import models
from app.main import create_app
from app.rounds import build_rounds, imbalance_warnings


@pytest.fixture
def gdb(db):
    """conftest's :memory: db plus the single game row (questions_per_person=5)."""
    models.create_game(db, code="TEST", host_key="hk")
    return db


def _contributor(db, name):
    return models.resolve_contributor(db, token=f"tok-{name}", name=name)["contributor_id"]


def _q(db, category, contributor_id=None, source="contributor"):
    cat = db.execute("SELECT id FROM category WHERE name = ?", (category,)).fetchone()["id"]
    cur = db.execute(
        "INSERT INTO question (author_name, category_id, text, answer, contributor_id, source) "
        "VALUES ('me', ?, 'q', 'a', ?, ?)", (cat, contributor_id, source))
    db.commit()
    return cur.lastrowid


def _assigned(db):
    return {r["id"] for r in db.execute("SELECT id FROM question WHERE round_id IS NOT NULL")}


def _round_qids(db, title):
    return [r["id"] for r in db.execute(
        "SELECT q.id FROM question q JOIN round r ON r.id = q.round_id "
        "WHERE r.title = ? ORDER BY q.display_order", (title,))]


# --- selection: guarantee + keep-first-N ---

def test_every_contributor_guaranteed_at_least_first_question(gdb):
    firsts = []
    for name, count in [("A", 1), ("B", 3), ("C", 5)]:
        cid = _contributor(gdb, name)
        ids = [_q(gdb, "History", cid) for _ in range(count)]
        firsts.append(ids[0])
    models.set_questions_per_person(gdb, 1)
    build_rounds(gdb)
    assert set(firsts) <= _assigned(gdb)
    assert not any("Contributor" in w for w in imbalance_warnings(gdb))


def test_n1_keeps_exactly_each_contributors_first(gdb):
    firsts, rest = [], []
    for name in ["A", "B", "C"]:
        cid = _contributor(gdb, name)
        ids = [_q(gdb, "History", cid) for _ in range(5)]
        firsts.append(ids[0])
        rest += ids[1:]
    models.set_questions_per_person(gdb, 1)
    build_rounds(gdb)
    assert _assigned(gdb) == set(firsts)
    # non-selected questions stay stored, untouched (round_id NULL)
    for qid in rest:
        assert gdb.execute(
            "SELECT round_id FROM question WHERE id = ?", (qid,)).fetchone()["round_id"] is None


def test_n5_keeps_all_in_submission_order(gdb):
    cid = _contributor(gdb, "A")
    ids = [_q(gdb, "History", cid) for _ in range(5)]
    build_rounds(gdb)  # default N=5
    assert _round_qids(gdb, "History") == ids


def test_rebuild_after_changing_n_changes_selection(gdb):
    cid = _contributor(gdb, "A")
    ids = [_q(gdb, "History", cid) for _ in range(5)]
    models.set_questions_per_person(gdb, 1)
    build_rounds(gdb)
    assert _assigned(gdb) == {ids[0]}
    models.set_questions_per_person(gdb, 3)
    build_rounds(gdb)
    assert _assigned(gdb) == set(ids[:3])


def test_double_build_is_idempotent(gdb):
    cid = _contributor(gdb, "A")
    for _ in range(5):
        _q(gdb, "History", cid)
    first = build_rounds(gdb)
    second = build_rounds(gdb)
    assert [(r["title"], r["question_count"]) for r in first] == \
        [(r["title"], r["question_count"]) for r in second]
    (n_rounds,) = gdb.execute("SELECT COUNT(*) FROM round WHERE is_final = 0").fetchone()
    assert n_rounds == 1


def test_rebuild_never_touches_final_rounds(gdb):
    cid = _contributor(gdb, "A")
    for _ in range(5):
        _q(gdb, "History", cid)
    fid = gdb.execute(
        "INSERT INTO round (title, display_order, is_final) VALUES ('Final Round', 99, 1)"
    ).lastrowid
    fq = _q(gdb, "General Knowledge")
    gdb.execute("UPDATE question SET round_id = ? WHERE id = ?", (fid, fq))
    gdb.commit()
    build_rounds(gdb)
    build_rounds(gdb)
    assert gdb.execute(
        "SELECT round_id FROM question WHERE id = ?", (fq,)).fetchone()["round_id"] == fid
    (finals,) = gdb.execute("SELECT COUNT(*) FROM round WHERE is_final = 1").fetchone()
    assert finals == 1


# --- shaping: 5-cap, even split, bank fill, Mixed Bag ---

def test_seven_in_category_splits_4_3(gdb):
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    ids = [_q(gdb, "History", a) for _ in range(5)] + [_q(gdb, "History", b) for _ in range(2)]
    build_rounds(gdb)
    assert _round_qids(gdb, "History") == ids[:4]
    assert _round_qids(gdb, "History II") == ids[4:]


def test_ten_in_category_splits_5_5(gdb):
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    for _ in range(5):
        _q(gdb, "History", a)
        _q(gdb, "History", b)
    rounds = build_rounds(gdb)
    assert [(r["title"], r["question_count"]) for r in rounds] == \
        [("History", 5), ("History II", 5)]


def test_twelve_splits_as_evenly_as_possible(gdb):
    # v1 split 12 into 5+5+2; v2 splits as evenly as possible: 4+4+4.
    for name in ["A", "B", "C"]:
        cid = _contributor(gdb, name)
        for _ in range(4):
            _q(gdb, "History", cid)
    rounds = build_rounds(gdb)
    assert [(r["title"], r["question_count"]) for r in rounds] == \
        [("History", 4), ("History II", 4), ("History III", 4)]


def test_thin_category_tops_up_from_same_category_bank_oldest_first(gdb):
    cid = _contributor(gdb, "A")
    mine = [_q(gdb, "History", cid) for _ in range(3)]
    bank = [_q(gdb, "History", source="bank") for _ in range(4)]
    _q(gdb, "Sports", source="bank")  # bank-only category: must NOT become a round
    rounds = build_rounds(gdb)
    assert [(r["title"], r["question_count"]) for r in rounds] == [("History", 5)]
    assert _round_qids(gdb, "History") == mine + bank[:2]  # oldest bank first
    assert _assigned(gdb) == set(mine + bank[:2])


def test_thin_categories_pool_into_mixed_bag(gdb):
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    hist = [_q(gdb, "History", a) for _ in range(2)]
    sport = [_q(gdb, "Sports", b) for _ in range(2)]
    rounds = build_rounds(gdb)
    assert [(r["title"], r["question_count"]) for r in rounds] == [("Mixed Bag", 4)]
    assert _round_qids(gdb, "Mixed Bag") == sorted(hist + sport)
    warnings = imbalance_warnings(gdb)
    assert any("History" in w for w in warnings)
    assert any("Sports" in w for w in warnings)


def test_mixed_bag_ordered_last(gdb):
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    for _ in range(5):
        _q(gdb, "Sports", a)  # full round
    for _ in range(2):
        _q(gdb, "History", b)  # pools into Mixed Bag
    rounds = build_rounds(gdb)
    assert [r["title"] for r in rounds] == ["Sports", "Mixed Bag"]


def test_small_mixed_bag_tops_up_from_any_category_bank(gdb):
    cid = _contributor(gdb, "A")
    mine = [_q(gdb, "History", cid) for _ in range(2)]
    bank = [_q(gdb, "Music", source="bank") for _ in range(5)]
    rounds = build_rounds(gdb)
    # 2 pooled questions < 3 → top up toward 5 from ANY bank, oldest first
    assert [(r["title"], r["question_count"]) for r in rounds] == [("Mixed Bag", 5)]
    assert _round_qids(gdb, "Mixed Bag") == sorted(mine + bank[:3])


def test_small_mixed_bag_rides_small_without_bank(gdb):
    cid = _contributor(gdb, "A")
    _q(gdb, "History", cid)
    rounds = build_rounds(gdb)
    assert [(r["title"], r["question_count"]) for r in rounds] == [("Mixed Bag", 1)]
    assert any("Mixed Bag" in w for w in imbalance_warnings(gdb))


def test_bank_never_displaces_contributor_questions(gdb):
    bank = [_q(gdb, "History", source="bank") for _ in range(3)]  # older ids than contributors'
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    mine = [_q(gdb, "History", a) for _ in range(5)] + [_q(gdb, "History", b) for _ in range(2)]
    build_rounds(gdb)
    assert _assigned(gdb) == set(mine)  # 4+3 split; bank untouched despite older ids
    assert bank[0] not in _assigned(gdb)


def test_bank_and_host_alone_build_nothing(gdb):
    _q(gdb, "History", source="host")
    _q(gdb, "History", source="bank")
    assert build_rounds(gdb) == []


def test_contributor_zero_selected_warning_fires(gdb):
    cid = _contributor(gdb, "A")
    _q(gdb, "History", cid)
    # no build ran, nothing assigned — the safety-net warning must fire
    assert any("'A'" in w for w in imbalance_warnings(gdb))


# --- settings endpoint + state round-trip ---

@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


@pytest.mark.anyio
async def test_settings_requires_host_key(app_client):
    app, c = app_client
    r = await c.post("/api/host/settings", params={"host_key": "nope"},
                     json={"questions_per_person": 3})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_settings_rejects_out_of_range(app_client):
    app, c = app_client
    hk = _hk(app)
    for bad in (0, 6):
        r = await c.post("/api/host/settings", params={"host_key": hk},
                         json={"questions_per_person": bad})
        assert r.status_code == 400


@pytest.mark.anyio
async def test_settings_round_trips_through_state(app_client):
    app, c = app_client
    hk = _hk(app)
    assert (await c.get("/api/state")).json()["questions_per_person"] == 5  # default
    r = await c.post("/api/host/settings", params={"host_key": hk},
                     json={"questions_per_person": 2})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert (await c.get("/api/state")).json()["questions_per_person"] == 2
