"""Text-to-speech for Gladys, the AI MC.

Gladys's on-screen personality (the line banks) lives client-side in
`static/gladys.js`; this module is the *voice* — it turns a line of her patter
into spoken audio via ElevenLabs so she can sound like the brassy, nasal
New-York cougar she is, instead of the browser's stock robot voices.

Design mirrors grading (`app/grading.py`): a tiny REST client plus a factory,
injectable at `app.state.tts_client` so tests use a fake and no key/network is
touched. Configuration is env-driven and entirely optional — with no key the
factory returns None, the endpoint 503s, and the display falls back to the
browser Web Speech voice. The app boots fine without any of this set.
"""

from __future__ import annotations

import os
from typing import Optional

# Expressive multilingual voice by default; override for cheaper/faster nights.
DEFAULT_MODEL = "eleven_multilingual_v2"
_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_VOICE_SETTINGS_VERSION = "jersey-cougar-v3"
_VOICE_SETTINGS = {
    "stability": 0.28,
    "similarity_boost": 0.9,
    "style": 0.75,
    "use_speaker_boost": True,
    "speed": 1.07,
}


class ElevenLabsTTS:
    """Synthesizes speech for one configured voice via the ElevenLabs REST API."""

    def __init__(self, api_key: str, voice_id: str, model: Optional[str] = None):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model or os.environ.get("ELEVENLABS_MODEL", DEFAULT_MODEL)

    # The cache key must change whenever the *sound* would change, so callers
    # that persist audio can key on this and never serve a stale voice/model.
    @property
    def fingerprint(self) -> str:
        return f"{self.voice_id}:{self.model}:{_VOICE_SETTINGS_VERSION}"

    def synthesize(self, text: str) -> bytes:
        """Return MP3 bytes for `text`. Raises on any transport/API error."""
        import httpx

        resp = httpx.post(
            _TTS_URL.format(voice_id=self.voice_id),
            headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": self.model,
                # Push the premade voice toward Gladys: throaty, brassy,
                # expressive, and quick enough for Jersey shore patter.
                "voice_settings": _VOICE_SETTINGS,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


def make_tts_client() -> Optional[ElevenLabsTTS]:
    """Build a client from the environment, or None if voice isn't configured.

    Both an API key AND a designed voice id are required — a key alone can't
    speak as Gladys. Absence is normal (dev, no-key nights): callers treat None
    as "fall back to the browser voice."
    """
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.environ.get("GLADYS_VOICE_ID", "").strip()
    if not key or not voice_id:
        return None
    return ElevenLabsTTS(key, voice_id)
