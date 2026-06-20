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

    # owner listing of mine shows the author their OWN answer (for review/edit)
    mine = await client.get("/api/questions/mine", params={"author": "Travis"})
    body = mine.json()
    assert any(q["id"] == qid for q in body["questions"])
    assert any(q.get("answer") == "1945" for q in body["questions"])

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
async def test_state_exposes_submissions_open_default(client):
    s = (await client.get("/api/state")).json()
    assert s["submissions_open"] is True


@pytest.mark.anyio
async def test_host_can_close_and_reopen_submissions(client):
    hk = _host_key(client)
    r = await client.post("/api/host/submissions", params={"host_key": hk}, json={"open": False})
    assert r.status_code == 200
    assert (await client.get("/api/state")).json()["submissions_open"] is False
    # reopenable: flip back
    await client.post("/api/host/submissions", params={"host_key": hk}, json={"open": True})
    assert (await client.get("/api/state")).json()["submissions_open"] is True


@pytest.mark.anyio
async def test_close_requires_host_key(client):
    r = await client.post("/api/host/submissions", params={"host_key": "wrong"}, json={"open": False})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_closed_window_blocks_add_but_preserves_data(client):
    hk = _host_key(client)
    cid = (await client.post("/api/contributor", json={"token": "tc", "name": "Cee"})).json()["contributor_id"]
    qid = (await client.post("/api/questions", json={
        "author": "Cee", "category": "History", "text": "Open Q?", "answer": "x",
        "contributor_id": cid,
    })).json()["id"]
    # close
    await client.post("/api/host/submissions", params={"host_key": hk}, json={"open": False})
    # cannot add
    blocked = await client.post("/api/questions", json={
        "author": "Cee", "category": "History", "text": "Late Q?", "answer": "y",
        "contributor_id": cid,
    })
    assert blocked.status_code == 409
    # existing data preserved
    mine = await client.get("/api/questions/mine", params={"contributor_id": cid})
    qs = mine.json()["questions"]
    assert len(qs) == 1 and qs[0]["id"] == qid


@pytest.mark.anyio
async def test_contributor_edits_own_question_while_open(client):
    cid = (await client.post("/api/contributor", json={"token": "te", "name": "Ed"})).json()["contributor_id"]
    qid = (await client.post("/api/questions", json={
        "author": "Ed", "category": "History", "text": "Old text?", "answer": "old",
        "contributor_id": cid,
    })).json()["id"]
    r = await client.put(f"/api/questions/{qid}", json={
        "contributor_id": cid, "category": "Science & Nature",
        "text": "New text?", "answer": "new", "acceptable": ["n"],
    })
    assert r.status_code == 200
    # still one question (replaced in place, no second set)
    mine = (await client.get("/api/questions/mine", params={"contributor_id": cid})).json()["questions"]
    assert len(mine) == 1 and mine[0]["text"] == "New text?"


@pytest.mark.anyio
async def test_edit_blocked_when_closed(client):
    hk = _host_key(client)
    cid = (await client.post("/api/contributor", json={"token": "tx", "name": "Ex"})).json()["contributor_id"]
    qid = (await client.post("/api/questions", json={
        "author": "Ex", "category": "History", "text": "T?", "answer": "a",
        "contributor_id": cid,
    })).json()["id"]
    await client.post("/api/host/submissions", params={"host_key": hk}, json={"open": False})
    r = await client.put(f"/api/questions/{qid}", json={
        "contributor_id": cid, "category": "History", "text": "Edited?", "answer": "b",
    })
    assert r.status_code == 409


@pytest.mark.anyio
async def test_cannot_edit_someone_elses_question(client):
    a = (await client.post("/api/contributor", json={"token": "ta", "name": "A"})).json()["contributor_id"]
    b = (await client.post("/api/contributor", json={"token": "tb", "name": "B"})).json()["contributor_id"]
    qid = (await client.post("/api/questions", json={
        "author": "A", "category": "History", "text": "Mine?", "answer": "a",
        "contributor_id": a,
    })).json()["id"]
    r = await client.put(f"/api/questions/{qid}", json={
        "contributor_id": b, "category": "History", "text": "Stolen?", "answer": "x",
    })
    assert r.status_code in (403, 404)


@pytest.mark.anyio
async def test_recover_contributor_by_code(client):
    c = (await client.post("/api/contributor", json={"token": "t3", "name": "Mo"})).json()
    r = await client.get("/api/contributor/recover", params={"recovery_code": c["recovery_code"]})
    assert r.status_code == 200
    assert r.json()["contributor_id"] == c["contributor_id"]
    bad = await client.get("/api/contributor/recover", params={"recovery_code": "nope"})
    assert bad.status_code == 404
