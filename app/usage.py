"""AI spend tracking — cost per grading call, persisted locally and forwarded
to the tarvy-admin sprite for historical collection.

Every Anthropic call gets one JSONL event: tokens, computed cost, duration,
and ok/error (the debugger half — grading failures used to vanish inside
/api/submit's try/except; now they at least leave a record).

Two sinks, both best-effort and never allowed to break a submit:
- local append to ai-usage.jsonl beside the DB (survives game resets, which
  only wipe trivia.db and uploads/)
- POST to the admin sprite's /api/ai-usage (ADMIN_URL + ADMIN_TOKEN env,
  same token that already gates /api/admin-summary); skipped when unset
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.request
from datetime import datetime, timezone

# $/MTok (input, output). Cache reads bill at 0.1x input, cache writes at
# 1.25x input (5-minute TTL, the default — grading never sets a longer one).
PRICES = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def cost_usd(model: str, usage: dict) -> float | None:
    """Estimated cost of one call from its usage block; None for unknown models."""
    prices = PRICES.get(model)
    if not prices:
        return None
    price_in, price_out = prices
    cost = (
        (usage.get("input_tokens") or 0) * price_in
        + (usage.get("cache_read_input_tokens") or 0) * price_in * 0.1
        + (usage.get("cache_creation_input_tokens") or 0) * price_in * 1.25
        + (usage.get("output_tokens") or 0) * price_out
    ) / 1_000_000
    return round(cost, 6)


def _log_path() -> pathlib.Path:
    explicit = os.environ.get("TRIVIA_USAGE_LOG")
    if explicit:
        return pathlib.Path(explicit)
    return pathlib.Path(os.environ.get("TRIVIA_DB", "trivia.db")).with_name("ai-usage.jsonl")


def _forward(event: dict) -> None:
    admin_url = os.environ.get("ADMIN_URL", "").rstrip("/")
    token = os.environ.get("ADMIN_TOKEN", "")
    if not admin_url or not token:
        return
    req = urllib.request.Request(
        f"{admin_url}/api/ai-usage?token={token}",
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=3).read()


def record(kind: str, *, game_code: str = "", model: str = "", usage: dict | None = None,
           duration_ms: int | None = None, ok: bool = True, error: str = "",
           **context) -> dict:
    """Record one AI call. Never raises — a broken tracker must not break the game."""
    usage = usage or {}
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app": os.environ.get("USAGE_APP", "sum-beach-trivia"),
        "kind": kind,
        "game_code": game_code,
        "model": model,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cost_usd": cost_usd(model, usage) if usage else None,
        "duration_ms": duration_ms,
        "ok": ok,
        "error": error or None,
        **context,
    }
    try:
        with _log_path().open("a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass
    try:
        _forward(event)
    except Exception:
        pass
    return event
