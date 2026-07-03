"""Final-round and tiebreak pick-list endpoints (app/final_options.py).

The list payloads must hide the answers (items/values) — the person setting
up the game may also be playing, so they pick blind. ?id=N returns the full
option for the actual POST /api/host/final or /api/host/tiebreak.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.final_options import FINAL_OPTIONS, TIEBREAK_OPTIONS
from app.main import create_app


@pytest.fixture
async def app_client():
    app = create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


def _hk(app):
    return app.state.conn.execute("SELECT host_key FROM game WHERE id=1").fetchone()["host_key"]


def test_curated_content_shape():
    assert len(FINAL_OPTIONS) >= 15
    for o in FINAL_OPTIONS:
        assert o["text"].strip()
        assert 3 <= len(o["items"]) <= 8
        assert all(isinstance(i, str) and i.strip() for i in o["items"])
        assert isinstance(o["ordered"], bool)
    assert len(TIEBREAK_OPTIONS) >= 20
    for o in TIEBREAK_OPTIONS:
        assert o["question"].strip()
        assert isinstance(o["value"], (int, float))


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/host/final-options", "/api/host/tiebreak-options"])
async def test_options_require_host_key(app_client, path):
    _, c = app_client
    assert (await c.get(path, params={"host_key": "nope"})).status_code == 403
    assert (await c.get(path, params={"host_key": "nope", "id": 0})).status_code == 403


@pytest.mark.anyio
async def test_final_options_list_hides_items(app_client):
    app, c = app_client
    r = await c.get("/api/host/final-options", params={"host_key": _hk(app)})
    assert r.status_code == 200
    opts = r.json()["options"]
    assert len(opts) == len(FINAL_OPTIONS)
    for i, o in enumerate(opts):
        # exactly the blind-pick fields — no items/answers leak
        assert set(o) == {"id", "text", "ordered", "item_count"}
        assert o["id"] == i
        assert o["item_count"] == len(FINAL_OPTIONS[i]["items"])


@pytest.mark.anyio
async def test_final_option_by_id_returns_items(app_client):
    app, c = app_client
    r = await c.get("/api/host/final-options", params={"host_key": _hk(app), "id": 0})
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == 0
    assert d["items"] == FINAL_OPTIONS[0]["items"]
    assert d["text"] == FINAL_OPTIONS[0]["text"]
    assert d["ordered"] == FINAL_OPTIONS[0]["ordered"]


@pytest.mark.anyio
async def test_tiebreak_options_list_hides_values(app_client):
    app, c = app_client
    r = await c.get("/api/host/tiebreak-options", params={"host_key": _hk(app)})
    assert r.status_code == 200
    opts = r.json()["options"]
    assert len(opts) == len(TIEBREAK_OPTIONS)
    for i, o in enumerate(opts):
        assert set(o) == {"id", "question"}
        assert o["id"] == i


@pytest.mark.anyio
async def test_tiebreak_option_by_id_returns_value(app_client):
    app, c = app_client
    last = len(TIEBREAK_OPTIONS) - 1
    r = await c.get("/api/host/tiebreak-options", params={"host_key": _hk(app), "id": last})
    assert r.status_code == 200
    d = r.json()
    assert d["question"] == TIEBREAK_OPTIONS[last]["question"]
    assert d["value"] == TIEBREAK_OPTIONS[last]["value"]


@pytest.mark.anyio
@pytest.mark.parametrize("path,n", [
    ("/api/host/final-options", len(FINAL_OPTIONS)),
    ("/api/host/tiebreak-options", len(TIEBREAK_OPTIONS)),
])
async def test_options_out_of_range_404(app_client, path, n):
    app, c = app_client
    hk = _hk(app)
    assert (await c.get(path, params={"host_key": hk, "id": n})).status_code == 404
    assert (await c.get(path, params={"host_key": hk, "id": -1})).status_code == 404


@pytest.mark.anyio
async def test_picked_final_option_round_trips(app_client):
    """Fetch a full option and POST it to /api/host/final — the intended flow."""
    app, c = app_client
    hk = _hk(app)
    d = (await c.get("/api/host/final-options", params={"host_key": hk, "id": 1})).json()
    r = await c.post("/api/host/final", params={"host_key": hk}, json={
        "text": d["text"], "items": d["items"], "ordered": d["ordered"]})
    assert r.status_code == 200
    rid = r.json()["round_id"]
    rounds = (await c.get("/api/host/rounds", params={"host_key": hk})).json()["rounds"]
    fin = next(x for x in rounds if x["id"] == rid)
    assert fin["is_final"] and fin["wager_cap"] is None  # wagers are uncapped
