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
