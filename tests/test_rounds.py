"""Round builder v2 (2026-07 rebuild, feedback item B).

Old tests encoded the v1 semantics (every thin category became its own round;
12 questions split 5+5+2 by striding) and were deliberately rewritten:
- selection keeps a RANDOM game.questions_per_person questions per contributor
  (everyone gets >= 1 in; <= N kept whole); bank/host questions are filler only.
  Tests pass a seeded rng and assert count/subset invariants, not which ids.
- rounds target exactly 5; oversized categories split as evenly as possible
  (7 -> 4+3); undersized ones top up from same-category bank or pool into
  "Mixed Bag" round(s) at the end
"""
import random

import pytest
from httpx import ASGITransport, AsyncClient

from app import models
from app.main import create_app
from app.rounds import build_rounds, imbalance_warnings, plan_preview


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


# --- selection: guarantee + random-keep-N ---

def test_every_contributor_guaranteed_at_least_one(gdb):
    contribs = {}
    for name, count in [("A", 1), ("B", 3), ("C", 5)]:
        cid = _contributor(gdb, name)
        contribs[cid] = [_q(gdb, "History", cid) for _ in range(count)]
    models.set_questions_per_person(gdb, 1)
    build_rounds(gdb, rng=random.Random(0))
    assigned = _assigned(gdb)
    for ids in contribs.values():
        assert len(set(ids) & assigned) == 1  # exactly one of theirs, guaranteed
    assert not any("Contributor" in w for w in imbalance_warnings(gdb))


def test_n1_keeps_one_random_per_contributor(gdb):
    contribs = {}
    for name in ["A", "B", "C"]:
        cid = _contributor(gdb, name)
        contribs[cid] = [_q(gdb, "History", cid) for _ in range(5)]
    models.set_questions_per_person(gdb, 1)
    build_rounds(gdb, rng=random.Random(1))
    assigned = _assigned(gdb)
    assert len(assigned) == 3  # one per contributor
    for ids in contribs.values():
        assert len(set(ids) & assigned) == 1  # a random one of theirs
    # the other 12 stay stored, untouched (round_id NULL)
    unassigned = gdb.execute(
        "SELECT COUNT(*) FROM question WHERE round_id IS NULL AND source = 'contributor'"
    ).fetchone()[0]
    assert unassigned == 12


def test_n5_keeps_all_in_submission_order(gdb):
    cid = _contributor(gdb, "A")
    ids = [_q(gdb, "History", cid) for _ in range(5)]
    build_rounds(gdb)  # default N=5: <= N kept whole, sorted by id
    assert _round_qids(gdb, "History") == ids


def test_rebuild_after_changing_n_changes_count(gdb):
    cid = _contributor(gdb, "A")
    ids = [_q(gdb, "History", cid) for _ in range(5)]
    models.set_questions_per_person(gdb, 1)
    build_rounds(gdb, rng=random.Random(2))
    a1 = _assigned(gdb)
    assert len(a1) == 1 and a1 <= set(ids)
    models.set_questions_per_person(gdb, 3)
    build_rounds(gdb, rng=random.Random(3))
    a3 = _assigned(gdb)
    assert len(a3) == 3 and a3 <= set(ids)


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


# --- questions_per_round (target size) drives the split ---

def test_target_size_10_makes_one_big_round(gdb):
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    for _ in range(5):
        _q(gdb, "History", a)
        _q(gdb, "History", b)
    rounds = build_rounds(gdb, target_size=10)
    assert [(r["title"], r["question_count"]) for r in rounds] == [("History", 10)]


def test_target_size_3_splits_ten_into_four_rounds(gdb):
    a, b = _contributor(gdb, "A"), _contributor(gdb, "B")
    for _ in range(5):
        _q(gdb, "History", a)
        _q(gdb, "History", b)
    rounds = build_rounds(gdb, target_size=3)  # ceil(10/3)=4 → 3+3+2+2
    assert [r["question_count"] for r in rounds] == [3, 3, 2, 2]


# --- max_rounds cap: consolidate smallest into Mixed Bag, keep everything ---

def test_max_rounds_consolidates_smallest(gdb):
    # three full single-category rounds → cap to 2: two smallest merge to Mixed Bag
    for cat in ["History", "Geography", "Sports"]:
        cid = _contributor(gdb, cat)
        for _ in range(5):
            _q(gdb, cat, cid)
    rounds = build_rounds(gdb, max_rounds=2)
    assert len(rounds) == 2
    counts = sorted(r["question_count"] for r in rounds)
    assert counts == [5, 10]  # one category survives, two merged
    assert any(r["title"] == "Mixed Bag" for r in rounds)
    # nothing benched: all 15 contributor questions are in play
    assert len(_assigned(gdb)) == 15


def test_max_rounds_above_natural_is_noop(gdb):
    for cat in ["History", "Geography"]:
        cid = _contributor(gdb, cat)
        for _ in range(5):
            _q(gdb, cat, cid)
    rounds = build_rounds(gdb, max_rounds=10)
    assert [(r["title"], r["question_count"]) for r in rounds] == \
        [("History", 5), ("Geography", 5)]


# --- plan_preview parity + summary ---

def test_plan_preview_matches_build(gdb):
    # a benching case (keep 2 of 4) so the random pick matters; same seed both paths
    for name in ["A", "B", "C"]:
        cid = _contributor(gdb, name)
        for cat in ["History", "Geography", "Sports"]:
            _q(gdb, cat, cid)
    models.set_questions_per_person(gdb, 2)
    plan = plan_preview(gdb)  # seeds Random(0) internally
    built = build_rounds(gdb, rng=random.Random(0))
    assert [(t["title"], t["count"]) for t in plan["round_titles"]] == \
        [(r["title"], r["question_count"]) for r in built]
    assert plan["rounds"] == len(built)


def test_plan_preview_counts_and_flags(gdb):
    a = _contributor(gdb, "A")
    for _ in range(5):
        _q(gdb, "History", a)  # full round
    b = _contributor(gdb, "B")
    _q(gdb, "Sports", b)       # thin → Mixed Bag flag
    plan = plan_preview(gdb)
    assert plan["contributors"] == 2
    assert plan["submitted"] == 6
    assert plan["rounds"] == 2  # History + Mixed Bag
    cats = {c["name"]: c for c in plan["by_category"]}
    assert cats["History"]["own_round"] is True
    assert cats["Sports"]["own_round"] is False
    assert any("Sports" in f["msg"] for f in plan["flags"])


def test_plan_preview_benched_flag(gdb):
    a = _contributor(gdb, "A")
    for cat in ["History", "Geography", "Sports", "Music", "Film & TV"]:
        _q(gdb, cat, a)  # 5 categories, one each
    models.set_questions_per_person(gdb, 2)  # keeps 2, benches 3
    plan = plan_preview(gdb)
    assert plan["submitted"] == 5
    assert plan["benched"] == 3
    assert any("benches" in f["msg"] for f in plan["flags"])


def test_plan_preview_cap_flag(gdb):
    for cat in ["History", "Geography", "Sports"]:
        cid = _contributor(gdb, cat)
        for _ in range(5):
            _q(gdb, cat, cid)
    models.set_max_rounds(gdb, 2)
    plan = plan_preview(gdb)
    assert plan["rounds"] == 2
    assert plan["natural_rounds"] == 3
    assert any("Capped" in f["msg"] for f in plan["flags"])


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


@pytest.mark.anyio
async def test_round_settings_round_trip(app_client):
    app, c = app_client
    hk = _hk(app)
    st = (await c.get("/api/state")).json()
    assert st["questions_per_round"] == 5 and st["max_rounds"] is None  # defaults
    r = await c.post("/api/host/settings", params={"host_key": hk},
                     json={"questions_per_round": 8, "max_rounds": 6})
    assert r.status_code == 200
    st = (await c.get("/api/state")).json()
    assert st["questions_per_round"] == 8 and st["max_rounds"] == 6
    # max_rounds=0 clears the cap → auto (null)
    await c.post("/api/host/settings", params={"host_key": hk}, json={"max_rounds": 0})
    assert (await c.get("/api/state")).json()["max_rounds"] is None


@pytest.mark.anyio
async def test_round_settings_reject_out_of_range(app_client):
    app, c = app_client
    hk = _hk(app)
    for bad in (2, 13):
        r = await c.post("/api/host/settings", params={"host_key": hk},
                         json={"questions_per_round": bad})
        assert r.status_code == 400
    r = await c.post("/api/host/settings", params={"host_key": hk},
                     json={"max_rounds": 21})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_round_plan_endpoint(app_client):
    app, c = app_client
    hk = _hk(app)
    assert (await c.get("/api/host/round-plan", params={"host_key": "nope"})).status_code == 403
    r = await c.get("/api/host/round-plan", params={"host_key": hk})
    assert r.status_code == 200
    body = r.json()
    for key in ("contributors", "submitted", "rounds", "by_category", "flags"):
        assert key in body
