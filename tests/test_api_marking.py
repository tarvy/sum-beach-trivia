import pytest
from httpx import ASGITransport, AsyncClient

from app.grading import QuestionGrade, SheetGrade
from app.main import create_app


class FakeGrader:
    """Returns a fixed grade for whatever questions it is asked about."""
    def __init__(self, mapping):  # mapping: question_id -> (correct, items_correct)
        self.mapping = mapping

    def grade(self, image_bytes, media_type, questions):
        grades = []
        for q in questions:
            correct, items = self.mapping.get(q["id"], (False, None))
            grades.append(QuestionGrade(
                question_id=q["id"], transcription="x", is_correct=correct,
                confidence=0.9, items_correct=items))
        return SheetGrade(grades=grades)


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


async def _setup_open_round(app, c, hk):
    for i in range(2):
        await c.post("/api/questions", json={
            "author": "me", "category": "History", "text": f"q{i}", "answer": "a"})
    rounds = (await c.post("/api/host/build-rounds", params={"host_key": hk})).json()["rounds"]
    rid = rounds[0]["id"]
    t = (await c.post("/api/teams", json={"name": "Aces"})).json()
    await c.post("/api/host/phase", params={"host_key": hk},
                 json={"phase": "round_open", "round_id": rid})
    return rid, t["team_id"]


@pytest.mark.anyio
async def test_submit_grades_and_scores(app_client):
    app, c = app_client
    hk = _hk(app)
    rid, team_id = await _setup_open_round(app, c, hk)
    qids = [q["id"] for q in (await c.get("/api/state")).json()["current_round"]["questions"]]
    app.state.grading_client = FakeGrader({qids[0]: (True, None), qids[1]: (False, None)})

    r = await c.post("/api/submit",
                     data={"team_id": str(team_id), "round_id": str(rid)},
                     files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 200
    # leaderboard reflects 1 correct answer (1 point)
    lb = (await c.get("/api/leaderboard")).json()["teams"]
    assert lb[0]["total"] == 1


@pytest.mark.anyio
async def test_submit_rejected_once_marking_starts(app_client):
    # round_closed ("pens down") still accepts sheet hand-ins; the window
    # truly shuts when the host moves to marking.
    app, c = app_client
    hk = _hk(app)
    rid, team_id = await _setup_open_round(app, c, hk)
    await c.post("/api/host/phase", params={"host_key": hk}, json={"phase": "marking"})
    r = await c.post("/api/submit",
                     data={"team_id": str(team_id), "round_id": str(rid)},
                     files={"photo": ("s.png", b"x", "image/png")})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_host_override_recomputes_total(app_client):
    app, c = app_client
    hk = _hk(app)
    rid, team_id = await _setup_open_round(app, c, hk)
    qids = [q["id"] for q in (await c.get("/api/state")).json()["current_round"]["questions"]]
    app.state.grading_client = FakeGrader({qids[0]: (False, None), qids[1]: (False, None)})
    await c.post("/api/submit", data={"team_id": str(team_id), "round_id": str(rid)},
                 files={"photo": ("s.png", b"x", "image/png")})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 0
    # host flips q0 to correct
    await c.post("/api/host/mark", params={"host_key": hk},
                 json={"team_id": team_id, "question_id": qids[0], "is_correct": True, "score": 1})
    assert (await c.get("/api/leaderboard")).json()["teams"][0]["total"] == 1
