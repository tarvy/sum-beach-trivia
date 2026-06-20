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
    w = await c.post("/api/wager", json={"team_id": t["team_id"], "round_id": rid, "amount": 99})
    assert w.status_code == 200
    # clamped to cap
    amt = app.state.conn.execute("SELECT amount FROM wager WHERE team_id=?",
                                 (t["team_id"],)).fetchone()["amount"]
    assert amt == 10

    # host marks 4/5 correct on the final question -> +6
    qid = app.state.conn.execute("SELECT id FROM question WHERE round_id=?",
                                 (rid,)).fetchone()["id"]
    await c.post("/api/host/mark", params={"host_key": hk},
                 json={"team_id": t["team_id"], "question_id": qid,
                       "is_correct": True, "score": 0, "items_correct": 4})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 6


@pytest.mark.anyio
async def test_csv_export(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/teams", json={"name": "Aces"})
    r = await c.get("/api/host/export.csv", params={"host_key": hk})
    assert r.status_code == 200
    assert "team" in r.text.lower()
    assert "Aces" in r.text
