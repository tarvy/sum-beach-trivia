"""MC mode ('lacey' human MC vs 'gladys' AI grading) + submit-window tolerance."""
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


async def _open_round(app, c, hk):
    """Contribute 3 questions, build rounds, open the first one; return (round_id, team_id)."""
    for i in range(3):
        await c.post("/api/questions", json={
            "author": "me", "category": "History", "text": f"q{i}", "answer": "a"})
    r = await c.post("/api/host/build-rounds", params={"host_key": hk})
    rid = r.json()["rounds"][0]["id"]
    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "round_open", "round_id": rid})
    t = await c.post("/api/teams", json={"name": "The Regulars"})
    return rid, t.json()["team_id"]


class GraderCalled(Exception):
    pass


class TrippingGrader:
    """Injected grader that records/raises if the AI path is exercised."""
    def __init__(self, raise_on_call=True):
        self.calls = 0
        self.raise_on_call = raise_on_call

    def grade(self, image_bytes, media_type, questions):
        self.calls += 1
        raise GraderCalled("AI grading should not run" if self.raise_on_call
                           else "simulated grading outage")


@pytest.mark.anyio
async def test_default_mode_is_gladys_in_state(app_client):
    app, c = app_client
    state = (await c.get("/api/state")).json()
    assert state["mc_mode"] == "gladys"


@pytest.mark.anyio
async def test_set_mc_mode_requires_host_key(app_client):
    app, c = app_client
    r = await c.post("/api/host/mc-mode", params={"host_key": "nope"},
                     json={"mode": "lacey"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_set_mc_mode_rejects_unknown_mode(app_client):
    app, c = app_client
    r = await c.post("/api/host/mc-mode", params={"host_key": _hk(app)},
                     json={"mode": "karen"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_set_mc_mode_round_trips_through_state(app_client):
    app, c = app_client
    r = await c.post("/api/host/mc-mode", params={"host_key": _hk(app)},
                     json={"mode": "lacey"})
    assert r.status_code == 200
    assert (await c.get("/api/state")).json()["mc_mode"] == "lacey"


@pytest.mark.anyio
async def test_lacey_mode_saves_photo_without_ai_or_marks(app_client):
    app, c = app_client
    hk = _hk(app)
    grader = TrippingGrader(raise_on_call=True)
    app.state.grading_client = grader
    await c.post("/api/host/mc-mode", params={"host_key": hk}, json={"mode": "lacey"})
    rid, tid = await _open_round(app, c, hk)

    r = await c.post("/api/submit", data={"team_id": tid, "round_id": rid},
                     files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "graded": False}
    assert grader.calls == 0  # the AI was never consulted
    sub = app.state.conn.execute(
        "SELECT * FROM submission WHERE team_id=? AND round_id=?", (tid, rid)).fetchone()
    assert sub is not None
    marks = app.state.conn.execute(
        "SELECT COUNT(*) AS n FROM mark WHERE team_id=?", (tid,)).fetchone()["n"]
    assert marks == 0  # Lacey enters marks herself via /api/host/mark


@pytest.mark.anyio
async def test_lacey_marks_by_hand_and_leaderboard_counts_them(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/host/mc-mode", params={"host_key": hk}, json={"mode": "lacey"})
    rid, tid = await _open_round(app, c, hk)
    qid = app.state.conn.execute(
        "SELECT id FROM question WHERE round_id=? ORDER BY display_order", (rid,)).fetchone()["id"]

    # no photo submitted at all — paper handed straight to the MC
    r = await c.post("/api/host/mark", params={"host_key": hk},
                     json={"team_id": tid, "question_id": qid, "is_correct": True, "score": 1})
    assert r.status_code == 200
    lb = (await c.get("/api/leaderboard")).json()["teams"]
    assert lb[0]["team_id"] == tid and lb[0]["total"] == 1


@pytest.mark.anyio
async def test_gladys_grading_failure_never_loses_the_submission(app_client):
    app, c = app_client
    hk = _hk(app)
    app.state.grading_client = TrippingGrader(raise_on_call=False)  # simulated outage
    rid, tid = await _open_round(app, c, hk)

    r = await c.post("/api/submit", data={"team_id": tid, "round_id": rid},
                     files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "graded": False}
    sub = app.state.conn.execute(
        "SELECT * FROM submission WHERE team_id=? AND round_id=?", (tid, rid)).fetchone()
    assert sub is not None  # photo kept — MC can mark it by hand


@pytest.mark.anyio
async def test_submit_still_allowed_after_pens_down(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/host/mc-mode", params={"host_key": hk}, json={"mode": "lacey"})
    rid, tid = await _open_round(app, c, hk)
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "round_closed"})

    r = await c.post("/api/submit", data={"team_id": tid, "round_id": rid},
                     files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 200  # pens down ≠ locked out


@pytest.mark.anyio
async def test_submit_rejected_once_marking_starts(app_client):
    app, c = app_client
    hk = _hk(app)
    await c.post("/api/host/mc-mode", params={"host_key": hk}, json={"mode": "lacey"})
    rid, tid = await _open_round(app, c, hk)
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "marking"})

    r = await c.post("/api/submit", data={"team_id": tid, "round_id": rid},
                     files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 409  # window truly shuts at marking
