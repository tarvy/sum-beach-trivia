"""Gladys's server voice endpoint (ElevenLabs), exercised with a fake client so
no API key or network is touched. Mirrors the grading_client injection pattern."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


class FakeTTS:
    """Stand-in for ElevenLabsTTS: counts synth calls, returns dummy mp3 bytes."""

    fingerprint = "voice-test:model-test"

    def __init__(self):
        self.calls = 0

    def synthesize(self, text):
        self.calls += 1
        return b"ID3fake-mp3-for:" + text.encode("utf-8")


@pytest.fixture
async def app_client(tmp_path, monkeypatch):
    # Point the on-disk voice cache at a temp dir so tests never touch real
    # uploads / the sprite's /data. The endpoint reads this module global at
    # call time, so patching it here is enough.
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "TTS_CACHE_DIR", tmp_path / "gladys-tts")
    app = main_mod.create_app(db_path=":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield app, c


@pytest.mark.anyio
async def test_tts_503_when_unconfigured(app_client):
    """No voice configured → endpoint 503s and state advertises no server voice,
    so the display knows to fall back to the browser voice."""
    app, c = app_client
    assert app.state.tts_client is None
    assert (await c.get("/api/state")).json()["gladys_tts"] is False
    r = await c.get("/api/gladys/tts", params={"text": "Hello sweetie"})
    assert r.status_code == 503


@pytest.mark.anyio
async def test_tts_synthesizes_then_caches(app_client):
    app, c = app_client
    fake = FakeTTS()
    app.state.tts_client = fake
    assert (await c.get("/api/state")).json()["gladys_tts"] is True

    r = await c.get("/api/gladys/tts", params={"text": "Pens down, darlings!"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content.startswith(b"ID3")
    assert fake.calls == 1

    # Identical text is served from disk cache — the client is NOT called again.
    r2 = await c.get("/api/gladys/tts", params={"text": "Pens down, darlings!"})
    assert r2.status_code == 200
    assert r2.content == r.content
    assert fake.calls == 1

    # A different line does synthesize.
    await c.get("/api/gladys/tts", params={"text": "Scores are up!"})
    assert fake.calls == 2


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["", "   ", "x" * 501])
async def test_tts_rejects_bad_text(app_client, text):
    app, c = app_client
    app.state.tts_client = FakeTTS()
    r = await c.get("/api/gladys/tts", params={"text": text})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_tts_502_on_synth_failure(app_client):
    """A synth failure surfaces as 5xx (the display then falls back)."""
    app, c = app_client

    class Boom:
        fingerprint = "boom:model"
        def synthesize(self, text):
            raise RuntimeError("elevenlabs down")

    app.state.tts_client = Boom()
    r = await c.get("/api/gladys/tts", params={"text": "this will fail"})
    assert r.status_code == 502
