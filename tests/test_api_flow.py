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
async def test_build_rounds_and_open(app_client):
    app, c = app_client
    hk = _hk(app)
    for i in range(3):
        await c.post("/api/questions", json={
            "author": "me", "category": "History", "text": f"q{i}", "answer": "a"})
    r = await c.post("/api/host/build-rounds", params={"host_key": hk})
    assert r.status_code == 200
    rounds = r.json()["rounds"]
    assert rounds and rounds[0]["title"] == "History"
    rid = rounds[0]["id"]

    # open the round
    p = await c.post("/api/host/phase", params={"host_key": hk},
                     json={"phase": "round_open", "round_id": rid})
    assert p.status_code == 200

    state = (await c.get("/api/state")).json()
    assert state["phase"] == "round_open"
    assert state["current_round"]["id"] == rid
    # questions exposed to players must NOT include answers
    qs = state["current_round"]["questions"]
    assert len(qs) == 3
    assert all("answer" not in q for q in qs)


@pytest.mark.anyio
async def test_phase_requires_host_key(app_client):
    app, c = app_client
    r = await c.post("/api/host/phase", params={"host_key": "x"}, json={"phase": "lobby"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_invalid_phase_rejected(app_client):
    app, c = app_client
    hk = _hk(app)
    r = await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "banana"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_pause_reflected_in_state(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/host/pause", params={"host_key": hk}, json={"paused": True})
    assert (await c.get("/api/state")).json()["paused"] is True


@pytest.mark.anyio
async def test_tiebreak_question_public_value_never(app_client):
    """The tiebreak QUESTION appears in /api/state only during the tiebreak
    phase; the tiebreak VALUE (the answer) must never reach the public payload."""
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/host/tiebreak", params={"host_key": hk},
                 json={"question": "How many gumballs in the jar?", "value": 1237.0})

    # Before the tiebreak phase: question hidden (it's a spoiler until then).
    s = (await c.get("/api/state")).json()
    assert s["tiebreak_question"] is None

    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "tiebreak"})
    r = await c.get("/api/state")
    s = r.json()
    assert s["tiebreak_question"] == "How many gumballs in the jar?"
    assert "tiebreak_value" not in s
    assert "1237" not in r.text  # the answer value must not leak anywhere in the payload


@pytest.mark.anyio
async def test_host_rounds_listing(app_client):
    """GET /api/host/rounds returns rounds with required keys; 403 without valid key."""
    app, c = app_client
    hk = _hk(app)

    # 403 without host key
    r = await c.get("/api/host/rounds")
    assert r.status_code == 422  # missing required param

    # 403 with wrong key
    r = await c.get("/api/host/rounds", params={"host_key": "wrong"})
    assert r.status_code == 403

    # No rounds yet — empty list
    r = await c.get("/api/host/rounds", params={"host_key": hk})
    assert r.status_code == 200
    assert r.json()["rounds"] == []

    # Build some rounds
    for i in range(3):
        await c.post("/api/questions", json={
            "author": "me", "category": "Geography", "text": f"q{i}", "answer": "a"})
    build_r = await c.post("/api/host/build-rounds", params={"host_key": hk})
    assert build_r.status_code == 200

    # Now listing should return them with the required keys
    r = await c.get("/api/host/rounds", params={"host_key": hk})
    assert r.status_code == 200
    data = r.json()
    assert "rounds" in data
    assert len(data["rounds"]) >= 1
    for rnd in data["rounds"]:
        assert "id" in rnd
        assert "title" in rnd
        assert "is_final" in rnd
        assert "wager_cap" in rnd
        assert "question_count" in rnd
    # The Geography round should be present with 3 questions
    geo = next((rnd for rnd in data["rounds"] if rnd["title"] == "Geography"), None)
    assert geo is not None
    assert geo["question_count"] == 3
    assert geo["is_final"] is False
