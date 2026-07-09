import pytest
from httpx import ASGITransport, AsyncClient

from app.grading import QuestionGrade, SheetGrade
from app.main import create_app


class QuippingGrader:
    def grade(self, image_bytes, media_type, questions):
        return SheetGrade(
            grades=[
                QuestionGrade(
                    question_id=q["id"],
                    transcription="answer",
                    is_correct=False,
                    confidence=0.9,
                )
                for q in questions
            ],
            gladys_quip="That handwriting looks like it left the hotel without paying.",
        )


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield app, client


def _host_key(app):
    return app.state.conn.execute(
        "SELECT host_key FROM game WHERE id = 1"
    ).fetchone()["host_key"]


async def _open_round(app, client):
    for i in range(3):
        await client.post("/api/questions", json={
            "author": f"Author {i}",
            "category": "History",
            "text": f"Question {i}?",
            "answer": "answer",
        })
    host_key = _host_key(app)
    rounds = (await client.post(
        "/api/host/build-rounds", params={"host_key": host_key}
    )).json()["rounds"]
    round_id = rounds[0]["id"]
    team_id = (await client.post("/api/teams", json={"name": "Beach Please"})).json()["team_id"]
    await client.post(
        "/api/host/phase",
        params={"host_key": host_key},
        json={"phase": "round_open", "round_id": round_id},
    )
    return host_key, round_id, team_id


@pytest.mark.anyio
async def test_gladys_level_defaults_and_round_trips(app_client):
    app, client = app_client
    assert (await client.get("/api/state")).json()["gladys_level"] == "uncensored"

    response = await client.post(
        "/api/host/settings",
        params={"host_key": _host_key(app)},
        json={"gladys_level": "clean"},
    )
    assert response.status_code == 200
    assert (await client.get("/api/state")).json()["gladys_level"] == "clean"


@pytest.mark.anyio
async def test_gladys_level_requires_host_and_rejects_unknown_value(app_client):
    app, client = app_client
    denied = await client.post(
        "/api/host/settings",
        params={"host_key": "wrong"},
        json={"gladys_level": "naughty"},
    )
    assert denied.status_code == 403

    invalid = await client.post(
        "/api/host/settings",
        params={"host_key": _host_key(app)},
        json={"gladys_level": "vicious"},
    )
    assert invalid.status_code == 400


@pytest.mark.anyio
async def test_submission_name_is_public_but_photo_quip_waits_for_answers(app_client):
    app, client = app_client
    app.state.grading_client = QuippingGrader()
    host_key, round_id, team_id = await _open_round(app, client)

    response = await client.post(
        "/api/submit",
        data={"team_id": team_id, "round_id": round_id},
        files={"photo": ("sheet.png", b"\x89PNG fake", "image/png")},
    )
    assert response.status_code == 200

    live_event = (await client.get("/api/state")).json()["submission_events"][0]
    assert live_event["team_name"] == "Beach Please"
    assert live_event["photo_quip"] is None

    await client.post(
        "/api/host/phase",
        params={"host_key": host_key},
        json={"phase": "marking"},
    )
    marking_event = (await client.get("/api/state")).json()["submission_events"][0]
    assert marking_event["photo_quip"] is None

    await client.post(
        "/api/host/phase",
        params={"host_key": host_key},
        json={"phase": "answers"},
    )
    answer_event = (await client.get("/api/state")).json()["submission_events"][0]
    assert answer_event["photo_quip"].startswith("That handwriting")
    assert "transcription" not in answer_event
    assert "is_correct" not in answer_event

