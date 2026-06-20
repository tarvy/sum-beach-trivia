import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c._app = app
        yield c


def _host_key(client):
    return client._app.state.conn.execute(
        "SELECT host_key FROM game WHERE id = 1"
    ).fetchone()["host_key"]


@pytest.mark.anyio
async def test_categories(client):
    r = await client.get("/api/categories")
    assert r.status_code == 200
    assert "History" in r.json()["categories"]


@pytest.mark.anyio
async def test_submit_question_then_host_sees_answer(client):
    r = await client.post("/api/questions", json={
        "author": "Travis", "category": "History", "text": "Year WWII ended?",
        "answer": "1945",
    })
    assert r.status_code == 200
    qid = r.json()["id"]

    # public listing of mine must NOT leak the answer
    mine = await client.get("/api/questions/mine", params={"author": "Travis"})
    body = mine.json()
    assert any(q["id"] == qid for q in body["questions"])
    assert all("answer" not in q for q in body["questions"])

    # host listing (with key) DOES include the answer
    hk = _host_key(client)
    h = await client.get("/api/questions", params={"host_key": hk})
    assert h.status_code == 200
    assert any(q["answer"] == "1945" for q in h.json()["questions"])


@pytest.mark.anyio
async def test_host_listing_requires_key(client):
    r = await client.get("/api/questions", params={"host_key": "wrong"})
    assert r.status_code == 403
