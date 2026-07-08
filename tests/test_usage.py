import json

from app import usage


def test_cost_usd_known_model():
    u = {"input_tokens": 1_000_000, "output_tokens": 100_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    # haiku: $1/M in + $5/M out -> 1.0 + 0.5
    assert usage.cost_usd("claude-haiku-4-5", u) == 1.5


def test_cost_usd_counts_cache_tokens():
    u = {"input_tokens": 0, "output_tokens": 0,
         "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000}
    # opus input $5/M: reads at 0.1x (0.5) + writes at 1.25x (6.25)
    assert usage.cost_usd("claude-opus-4-8", u) == 6.75


def test_cost_usd_unknown_model_is_none():
    assert usage.cost_usd("some-future-model", {"input_tokens": 5}) is None


def test_record_appends_jsonl_and_never_raises(tmp_path, monkeypatch):
    log = tmp_path / "ai-usage.jsonl"
    monkeypatch.setenv("TRIVIA_USAGE_LOG", str(log))
    monkeypatch.delenv("ADMIN_URL", raising=False)  # no forwarding in tests

    usage.record("grading", game_code="ABCD", model="claude-haiku-4-5",
                 usage={"input_tokens": 2000, "output_tokens": 300},
                 duration_ms=1234, team_id=1, round_id=3)
    usage.record("grading", game_code="ABCD", ok=False, error="BadRequestError('boom')",
                 team_id=2, round_id=3)

    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert len(lines) == 2
    ok_ev, err_ev = lines
    assert ok_ev["ok"] is True and ok_ev["cost_usd"] > 0 and ok_ev["team_id"] == 1
    assert ok_ev["game_code"] == "ABCD" and ok_ev["duration_ms"] == 1234
    assert err_ev["ok"] is False and "boom" in err_ev["error"]


def test_record_survives_unwritable_log(monkeypatch):
    monkeypatch.setenv("TRIVIA_USAGE_LOG", "/nonexistent-dir/nope.jsonl")
    monkeypatch.delenv("ADMIN_URL", raising=False)
    ev = usage.record("grading", game_code="X")  # must not raise
    assert ev["kind"] == "grading"
