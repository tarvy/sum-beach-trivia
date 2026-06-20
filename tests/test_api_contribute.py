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


@pytest.mark.anyio
async def test_contributor_resolve_is_stable_by_token(client):
    # First visit: create a contributor with a fresh token.
    r = await client.post("/api/contributor", json={"token": "tok-abc", "name": "Sandy"})
    assert r.status_code == 200
    c = r.json()
    assert c["name"] == "Sandy"
    assert c["recovery_code"]
    cid = c["contributor_id"]

    # Return visit on same browser (same token) resolves to the same person,
    # even with an edited display name.
    r2 = await client.post("/api/contributor", json={"token": "tok-abc", "name": "Sandy B"})
    assert r2.json()["contributor_id"] == cid
    assert r2.json()["name"] == "Sandy B"


@pytest.mark.anyio
async def test_questions_attributed_to_contributor_and_loaded_back(client):
    cid = (await client.post("/api/contributor", json={"token": "t1", "name": "Pat"})).json()["contributor_id"]
    for txt in ("Q1?", "Q2?"):
        r = await client.post("/api/questions", json={
            "author": "Pat", "category": "History", "text": txt, "answer": "x",
            "contributor_id": cid,
        })
        assert r.status_code == 200
    mine = await client.get("/api/questions/mine", params={"contributor_id": cid})
    assert len(mine.json()["questions"]) == 2


@pytest.mark.anyio
async def test_authors_listed_once_per_person(client):
    cid = (await client.post("/api/contributor", json={"token": "t2", "name": "Lee"})).json()["contributor_id"]
    for txt in ("A?", "B?", "C?"):
        await client.post("/api/questions", json={
            "author": "Lee", "category": "History", "text": txt, "answer": "x",
            "contributor_id": cid,
        })
    authors = (await client.get("/api/authors")).json()["authors"]
    lees = [a for a in authors if a["name"] == "Lee"]
    assert len(lees) == 1


@pytest.mark.anyio
async def test_recover_contributor_by_code(client):
    c = (await client.post("/api/contributor", json={"token": "t3", "name": "Mo"})).json()
    r = await client.get("/api/contributor/recover", params={"recovery_code": c["recovery_code"]})
    assert r.status_code == 200
    assert r.json()["contributor_id"] == c["contributor_id"]
    bad = await client.get("/api/contributor/recover", params={"recovery_code": "nope"})
    assert bad.status_code == 404
