"""Admin-summary endpoint for the home-base sprite."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


@pytest.mark.anyio
async def test_admin_summary_absent_without_env_token(app_client, monkeypatch):
    _, c = app_client
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = await c.get("/api/admin-summary", params={"admin_token": "anything"})
    assert r.status_code == 404  # endpoint effectively doesn't exist


@pytest.mark.anyio
async def test_admin_summary_gated_and_complete(app_client, monkeypatch):
    app, c = app_client
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    assert (await c.get("/api/admin-summary", params={"admin_token": "wrong"})).status_code == 403
    r = await c.get("/api/admin-summary", params={"admin_token": "s3cret"})
    assert r.status_code == 200
    d = r.json()
    row = app.state.conn.execute("SELECT code, host_key FROM game").fetchone()
    assert d["code"] == row["code"] and d["host_key"] == row["host_key"]
    assert set(d) == {"code", "host_key", "phase", "mc_mode", "teams", "questions"}
