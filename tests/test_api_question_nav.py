"""One-question-at-a-time: cursor, loose timer, anti-spoiler slicing."""
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


async def _open_round(c, hk, n=4):
    for i in range(n):
        await c.post("/api/questions", json={
            "author": "me", "category": "History", "text": f"q{i}", "answer": "a"})
    r = await c.post("/api/host/build-rounds", params={"host_key": hk})
    rid = r.json()["rounds"][0]["id"]
    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "round_open", "round_id": rid})
    return rid


@pytest.mark.anyio
async def test_round_open_starts_at_question_one_with_timer(app_client):
    app, c = app_client
    await _open_round(c, _hk(app))
    s = (await c.get("/api/state")).json()
    assert s["question_idx"] == 0
    assert s["question_seconds"] == 60
    assert isinstance(s["question_elapsed"], int) and s["question_elapsed"] >= 0
    # anti-spoiler: only the live question is exposed; count says how many exist
    assert len(s["current_round"]["questions"]) == 1
    assert s["current_round"]["question_count"] == 4
    assert s["current_round"]["round_number"] == 1


@pytest.mark.anyio
async def test_nav_next_prev_clamped_and_gated(app_client):
    app, c = app_client
    hk = _hk(app)
    await _open_round(c, hk)

    assert (await c.post("/api/host/question", params={"host_key": "nope"},
                         json={"action": "next"})).status_code == 403
    assert (await c.post("/api/host/question", params={"host_key": hk},
                         json={"action": "sideways"})).status_code == 400

    r = await c.post("/api/host/question", params={"host_key": hk}, json={"action": "next"})
    assert r.json()["question_idx"] == 1
    s = (await c.get("/api/state")).json()
    assert [q["text"] for q in s["current_round"]["questions"]] == ["q0", "q1"]

    # clamp at both ends
    for _ in range(10):
        await c.post("/api/host/question", params={"host_key": hk}, json={"action": "next"})
    assert (await c.get("/api/state")).json()["question_idx"] == 3
    for _ in range(10):
        await c.post("/api/host/question", params={"host_key": hk}, json={"action": "prev"})
    assert (await c.get("/api/state")).json()["question_idx"] == 0

    # gated outside a live round
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "round_closed"})
    assert (await c.post("/api/host/question", params={"host_key": hk},
                         json={"action": "next"})).status_code == 409


@pytest.mark.anyio
async def test_reveal_shows_all_questions(app_client):
    app, c = app_client
    hk = _hk(app)
    await _open_round(c, hk)
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "reveal"})
    s = (await c.get("/api/state")).json()
    assert len(s["current_round"]["questions"]) == 4  # full list at reveal


@pytest.mark.anyio
async def test_pens_down_freezes_at_current_question(app_client):
    app, c = app_client
    hk = _hk(app)
    await _open_round(c, hk)
    await c.post("/api/host/question", params={"host_key": hk}, json={"action": "next"})
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "round_closed"})
    s = (await c.get("/api/state")).json()
    assert len(s["current_round"]["questions"]) == 2  # still only what was shown


@pytest.mark.anyio
async def test_question_seconds_setting(app_client):
    app, c = app_client
    hk = _hk(app)
    assert (await c.post("/api/host/settings", params={"host_key": hk},
                         json={"question_seconds": 5})).status_code == 400
    assert (await c.post("/api/host/settings", params={"host_key": hk},
                         json={"question_seconds": 90})).status_code == 200
    assert (await c.get("/api/state")).json()["question_seconds"] == 90
    # both settings in one call still works
    r = await c.post("/api/host/settings", params={"host_key": hk},
                     json={"question_seconds": 45, "questions_per_person": 3})
    assert r.status_code == 200
    s = (await c.get("/api/state")).json()
    assert s["question_seconds"] == 45 and s["questions_per_person"] == 3


@pytest.mark.anyio
async def test_answers_readback_exposes_answers_cursor_paced(app_client):
    """Answers go public ONLY during phase=answers, sliced by the cursor."""
    app, c = app_client
    hk = _hk(app)
    await _open_round(c, hk)

    # never during the live round
    s = (await c.get("/api/state")).json()
    assert all("answer" not in q for q in s["current_round"]["questions"])

    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "answers"})
    s = (await c.get("/api/state")).json()
    qs = s["current_round"]["questions"]
    assert s["question_idx"] == 0 and len(qs) == 1  # read-back restarts at item 1
    assert qs[0]["answer"] == "a" and qs[0]["author_name"] == "me"

    # cursor nav works during the read-back
    r = await c.post("/api/host/question", params={"host_key": hk}, json={"action": "next"})
    assert r.json()["question_idx"] == 1
    s = (await c.get("/api/state")).json()
    assert len(s["current_round"]["questions"]) == 2
    assert all(q["answer"] == "a" for q in s["current_round"]["questions"])

    # ...and answers vanish again once scores are released
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "reveal"})
    s = (await c.get("/api/state")).json()
    assert all("answer" not in q for q in s["current_round"]["questions"])
    assert len(s["current_round"]["questions"]) == 4  # full list at reveal
