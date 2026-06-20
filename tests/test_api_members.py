import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _team(client, name="Beach Bums"):
    r = await client.post("/api/teams", json={"name": name})
    return r.json()["team_id"]


async def _author(client, token, name):
    r = await client.post("/api/contributor", json={"token": token, "name": name})
    return r.json()["contributor_id"]


@pytest.mark.anyio
async def test_add_author_and_manual_members(client):
    tid = await _team(client)
    cid = await _author(client, "tok-ada", "Ada")
    # author picked from the bank (contributor_id set)
    r1 = await client.post(f"/api/teams/{tid}/members", json={"name": "Ada", "contributor_id": cid})
    assert r1.status_code == 200
    # manual teammate, no contributor_id
    r2 = await client.post(f"/api/teams/{tid}/members", json={"name": "Walk-in Wally"})
    assert r2.status_code == 200

    lst = await client.get(f"/api/teams/{tid}/members")
    members = lst.json()["members"]
    assert {m["name"] for m in members} == {"Ada", "Walk-in Wally"}
    ada = next(m for m in members if m["name"] == "Ada")
    assert ada["contributor_id"] == cid


@pytest.mark.anyio
async def test_remove_member_takes_effect(client):
    tid = await _team(client)
    r = await client.post(f"/api/teams/{tid}/members", json={"name": "Temp"})
    mid = r.json()["id"]
    rm = await client.delete(f"/api/teams/{tid}/members/{mid}")
    assert rm.status_code == 200
    lst = await client.get(f"/api/teams/{tid}/members")
    assert lst.json()["members"] == []


@pytest.mark.anyio
async def test_empty_name_rejected(client):
    tid = await _team(client)
    r = await client.post(f"/api/teams/{tid}/members", json={"name": "  "})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_author_can_be_on_multiple_teams(client):
    a = await _team(client, "Team A")
    b = await _team(client, "Team B")
    cid = await _author(client, "tok-ada", "Ada")
    await client.post(f"/api/teams/{a}/members", json={"name": "Ada", "contributor_id": cid})
    r = await client.post(f"/api/teams/{b}/members", json={"name": "Ada", "contributor_id": cid})
    assert r.status_code == 200  # no exclusivity
