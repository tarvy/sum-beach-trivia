#!/usr/bin/env python3
"""One-off: design Gladys's voice on ElevenLabs and print her permanent voice_id.

Gladys is a designed *archetype* — a brassy, nasal, New-York-cougar hostess —
NOT a clone of any real person. We describe her to ElevenLabs voice-design,
listen to (well, save) the previews, keep one, and register it as a permanent
voice. Run this ONCE, then set the printed id as GLADYS_VOICE_ID on each sprite.

    ELEVENLABS_API_KEY=... python3 scripts/design_gladys_voice.py

By default it auto-selects the first preview and creates the voice. Pass
--previews-only to just write the preview mp3s to /tmp and stop, so you can
audition them and pick, then re-run with --pick N.

Docs: https://elevenlabs.io/docs/api-reference/text-to-voice/design
"""

from __future__ import annotations

import argparse
import base64
import os
import sys

import httpx

API = "https://api.elevenlabs.io/v1"

# The archetype. Vivid and specific — voice-design leans on adjectives.
DESCRIPTION = (
    "A brassy, nasal, middle-aged woman from Queens, New York — loud, warm, "
    "flirtatious and theatrical, like a campy game-show hostess who's had three "
    "cocktails and loves every person in the room. Fast, honking, big-personality "
    "delivery with a thick working-class New York accent and a laugh in her voice."
)
# A real Gladys line as the sample (100–1000 chars).
SAMPLE = (
    "Well hello, hello, HELLO, sweetie! Sit your gorgeous tuchus down — Gladys is "
    "your hostess tonight, and oh, do we have fun. Pens down, darlings, and don't "
    "be shy, because nobody good ever got anywhere bein' shy. Hah!"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--previews-only", action="store_true",
                    help="write preview mp3s to /tmp and stop (audition, then --pick)")
    ap.add_argument("--pick", type=int, default=0, help="which preview index to keep")
    ap.add_argument("--name", default="Gladys", help="voice name to register")
    args = ap.parse_args()

    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY not set", file=sys.stderr)
        return 2
    headers = {"xi-api-key": key}

    print("Designing previews from the archetype description…", file=sys.stderr)
    r = httpx.post(f"{API}/text-to-voice/design", headers=headers, timeout=120.0, json={
        "voice_description": DESCRIPTION,
        "text": SAMPLE,
        "model_id": "eleven_multilingual_ttv_v2",
    })
    r.raise_for_status()
    previews = r.json().get("previews", [])
    if not previews:
        print("no previews returned", file=sys.stderr)
        return 1

    for i, p in enumerate(previews):
        audio = p.get("audio_base_64") or p.get("audio_base64") or ""
        if audio:
            out = f"/tmp/gladys-preview-{i}.mp3"
            with open(out, "wb") as f:
                f.write(base64.b64decode(audio))
            print(f"  preview {i}: {out}", file=sys.stderr)

    if args.previews_only:
        print("Auditioned. Re-run with --pick N to register one.", file=sys.stderr)
        return 0

    pick = previews[args.pick]
    gid = pick["generated_voice_id"]
    print(f"Registering preview {args.pick} as a permanent voice…", file=sys.stderr)
    r = httpx.post(f"{API}/text-to-voice", headers=headers, timeout=120.0, json={
        "voice_name": args.name,
        "voice_description": DESCRIPTION,
        "generated_voice_id": gid,
    })
    r.raise_for_status()
    voice_id = r.json()["voice_id"]
    # The one line meant for stdout: the id to set as GLADYS_VOICE_ID.
    print(voice_id)
    print(f"\nSet it:  GLADYS_VOICE_ID={voice_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
