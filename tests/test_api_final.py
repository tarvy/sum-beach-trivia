import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


@pytest.mark.anyio
async def test_final_wager_flow(app_client):
    app, c = app_client
    hk = _hk(app)
    t = (await c.post("/api/teams", json={"name": "Aces"})).json()
    f = await c.post("/api/host/final", params={"host_key": hk}, json={
        "text": "Order these films by release year",
        "items": ["A", "B", "C", "D", "E"], "ordered": True, "wager_cap": 10})
    rid = f.json()["round_id"]

    # wagers only accepted in final_wager phase
    early = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 10})
    assert early.status_code == 409

    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "final_wager", "round_id": rid})
    # no cap: any amount sticks (negative clamps to 0)
    w = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 99})
    assert w.status_code == 200
    amt = app.state.conn.execute("SELECT amount FROM wager WHERE team_id=?",
                                 (t["team_id"],)).fetchone()["amount"]
    assert amt == 99
    neg = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": -5})
    assert neg.status_code == 200 and neg.json()["amount"] == 0
    # settle on 10 so the scoring math below stays legible
    await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 10})

    # host marks 4/5 correct on the final question -> +6
    qid = app.state.conn.execute("SELECT id FROM question WHERE round_id=?",
                                 (rid,)).fetchone()["id"]
    await c.post("/api/host/mark", params={"host_key": hk},
                 json={"team_id": t["team_id"], "question_id": qid,
                       "is_correct": True, "score": 0, "items_correct": 4})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 6


@pytest.mark.anyio
async def test_tiebreak_db_persistence(tmp_path):
    """Tiebreak guesses are stored in SQLite; result survives a new app instance on the same file."""
    import os
    db_file = str(tmp_path / "tiebreak_test.db")

    # First app instance: set tiebreak and submit two guesses
    app1 = create_app(db_path=db_file)
    hk = app1.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]

    async with AsyncClient(transport=ASGITransport(app=app1), base_url="http://t") as c1:
        t1 = (await c1.post("/api/teams", json={"name": "TeamA"})).json()
        t2 = (await c1.post("/api/teams", json={"name": "TeamB"})).json()

        r = await c1.post("/api/host/tiebreak", params={"host_key": hk},
                          json={"question": "How many?", "value": 100.0})
        assert r.status_code == 200

        # TeamA guesses closer (95), TeamB guesses farther (200)
        g1 = await c1.post("/api/tiebreak", params={"team_id": t1["team_id"], "value": 95.0})
        assert g1.status_code == 200
        g2 = await c1.post("/api/tiebreak", params={"team_id": t2["team_id"], "value": 200.0})
        assert g2.status_code == 200

    # Verify no app.state dict used: tiebreak_guesses attr should not exist
    assert not hasattr(app1.state, "tiebreak_guesses")

    # Second app instance on same file: guesses must survive
    app2 = create_app(db_path=db_file)
    hk2 = app2.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]

    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://t") as c2:
        res = await c2.get("/api/host/tiebreak-result", params={"host_key": hk2})
        assert res.status_code == 200
        data = res.json()
        assert data["target"] == 100.0
        ranked = data["ranked"]
        assert len(ranked) == 2
        # TeamA (delta=5) should rank first, TeamB (delta=100) second
        assert ranked[0]["name"] == "TeamA"
        assert ranked[0]["delta"] == pytest.approx(5.0)
        assert ranked[1]["name"] == "TeamB"
        assert ranked[1]["delta"] == pytest.approx(100.0)


@pytest.mark.anyio
async def test_wager_bad_round_id(app_client):
    """POST /api/wager with a nonexistent round_id returns 404."""
    app, c = app_client
    hk = _hk(app)
    t = (await c.post("/api/teams", json={"name": "Aces"})).json()
    # Set phase to final_wager so the phase check passes
    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "final_wager"})
    r = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": 9999, "amount": 5})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_csv_export(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/teams", json={"name": "Aces"})
    r = await c.get("/api/host/export.csv", params={"host_key": hk})
    assert r.status_code == 200
    assert "team" in r.text.lower()
    assert "Aces" in r.text


@pytest.mark.anyio
async def test_final_can_be_changed_until_in_play(app_client):
    """Nothing is set in stone until wagers/marks exist: delete + re-create works."""
    app, c = app_client
    hk = _hk(app)
    # nothing to delete yet
    assert (await c.delete("/api/host/final", params={"host_key": hk})).status_code == 404
    assert (await c.delete("/api/host/final", params={"host_key": "nope"})).status_code == 403

    r1 = await c.post("/api/host/final", params={"host_key": hk}, json={
        "text": "First idea", "items": ["A", "B", "C"], "ordered": False})
    rid1 = r1.json()["round_id"]
    d = await c.delete("/api/host/final", params={"host_key": hk})
    assert d.status_code == 200
    # round and its question are gone
    assert app.state.conn.execute("SELECT 1 FROM round WHERE id=?", (rid1,)).fetchone() is None
    assert app.state.conn.execute(
        "SELECT 1 FROM question WHERE round_id=?", (rid1,)).fetchone() is None

    # re-create freely
    r2 = await c.post("/api/host/final", params={"host_key": hk}, json={
        "text": "Better idea", "items": ["X", "Y", "Z", "W"], "ordered": True})
    assert r2.status_code == 200


@pytest.mark.anyio
async def test_final_change_allowed_mid_play_and_clears_dependents(app_client):
    """Nothing is locked: the host can swap the final even after wagers exist;
    the old final's wagers/marks go with it and current_round is cleared."""
    app, c = app_client
    hk = _hk(app)
    t = (await c.post("/api/teams", json={"name": "Locks"})).json()
    rid = (await c.post("/api/host/final", params={"host_key": hk}, json={
        "text": "Q", "items": ["A", "B"], "ordered": False})).json()["round_id"]
    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "final_wager", "round_id": rid})
    await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 5})

    d = await c.delete("/api/host/final", params={"host_key": hk})
    assert d.status_code == 200  # in play, but still changeable
    conn = app.state.conn
    assert conn.execute("SELECT 1 FROM round WHERE id=?", (rid,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM wager WHERE round_id=?", (rid,)).fetchone() is None
    assert conn.execute("SELECT current_round_id FROM game").fetchone()["current_round_id"] is None
