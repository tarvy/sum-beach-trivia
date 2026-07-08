import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.anyio
@pytest.mark.parametrize("path", [
    "/", "/contribute.html", "/host.html", "/play.html", "/display.html",
])
async def test_static_pages_served(client, path):
    r = await client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


@pytest.mark.anyio
async def test_gladys_script_served(client):
    """Gladys's personality/voice engine ships as a plain static file — no route,
    no build. Lock the wiring so the display can always load /gladys.js."""
    r = await client.get("/gladys.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    body = r.text
    assert "window.Gladys" in body      # the global the display depends on
    assert "bubbeleh" in body           # a known catchphrase — the persona is present
    assert "/api/gladys/tts" in body    # the real (server) voice path is wired
