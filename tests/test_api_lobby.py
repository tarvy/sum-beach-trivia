import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.anyio
async def test_join_and_list_teams(client):
    r = await client.post("/api/teams", json={"name": "Beach Bums"})
    assert r.status_code == 200
    body = r.json()
    assert body["team_id"] == 1 and body["name"] == "Beach Bums"
    assert "recovery_code" not in body  # no codes: joining is open, tap-to-join

    dup = await client.post("/api/teams", json={"name": "beach bums"})
    assert dup.status_code == 409

    teams = await client.get("/api/teams")
    names = [t["name"] for t in teams.json()["teams"]]
    assert names == ["Beach Bums"]
    assert all("recovery_code" not in t for t in teams.json()["teams"])


@pytest.mark.anyio
async def test_removed_team_endpoints_are_gone(client):
    t = (await client.post("/api/teams", json={"name": "Sandy"})).json()
    assert (await client.get("/api/teams/recover", params={"recovery_code": "x"})).status_code == 404
    assert (await client.get(f"/api/teams/{t['team_id']}/members")).status_code == 404


@pytest.mark.anyio
async def test_empty_leaderboard(client):
    await client.post("/api/teams", json={"name": "Sandy"})
    r = await client.get("/api/leaderboard")
    assert r.json()["teams"] == [{"team_id": 1, "name": "Sandy", "total": 0}]
