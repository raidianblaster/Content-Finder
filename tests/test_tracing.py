"""Tests for the LLM tracing wrapper + cost estimation (roadmap M0.1).

Mocks the Anthropic client at the boundary (per CLAUDE.md) — no network.
"""
from __future__ import annotations

import json

import pytest

import tracing


class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class _Resp:
    def __init__(self, text="ok", i=100, o=50, stop_reason="end_turn"):
        self.content = [type("C", (), {"text": text})()]
        self.usage = _Usage(i, o)
        self.stop_reason = stop_reason


class _FakeClient:
    """Mimics anthropic.Anthropic(): client.messages.create(**kwargs)."""
    def __init__(self, resp=None, raise_exc=None):
        self._resp = resp if resp is not None else _Resp()
        self._raise = raise_exc
        self.messages = self

    def create(self, **kwargs):
        if self._raise:
            raise self._raise
        return self._resp


def test_estimate_cost_known_and_unknown():
    # sonnet = $3/$15 per 1M in/out → 1M+1M = 18.0
    assert tracing.estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)
    # dated haiku snapshot resolves via the family fallback
    assert tracing.estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0) == pytest.approx(1.0)
    assert tracing.estimate_cost("totally-unknown", 1_000_000, 1_000_000) == 0.0


def test_traced_message_writes_row_and_returns_response(tmp_path):
    tp = tmp_path / "traces.jsonl"
    client = _FakeClient(_Resp(text="hi", i=200, o=80))
    resp = tracing.traced_message(
        client, call_site="synthesis", prompt_version="v1", trace_path=tp,
        model="claude-sonnet-4-6", max_tokens=10,
        messages=[{"role": "user", "content": "x"}],
    )
    assert resp.content[0].text == "hi"  # response passed through untouched
    rows = [json.loads(l) for l in tp.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    r = rows[0]
    assert r["call_site"] == "synthesis"
    assert r["model"] == "claude-sonnet-4-6"
    assert r["prompt_version"] == "v1"
    assert r["input_tokens"] == 200 and r["output_tokens"] == 80
    assert r["ok"] is True
    assert r["cost_usd"] == pytest.approx(tracing.estimate_cost("claude-sonnet-4-6", 200, 80))
    assert isinstance(r["latency_ms"], (int, float))


def test_traced_message_records_stop_reason(tmp_path):
    """A truncated synthesis (stop_reason='max_tokens') must be visible in the
    ledger — that's the only signal that a card shipped without its link."""
    tp = tmp_path / "traces.jsonl"
    client = _FakeClient(_Resp(text="cut off…", stop_reason="max_tokens"))
    tracing.traced_message(
        client, call_site="synthesis", trace_path=tp,
        model="claude-sonnet-4-6", max_tokens=10,
        messages=[{"role": "user", "content": "x"}],
    )
    r = [json.loads(l) for l in tp.read_text().splitlines() if l.strip()][0]
    assert r["stop_reason"] == "max_tokens"


def test_traced_message_records_failure_and_reraises(tmp_path):
    tp = tmp_path / "traces.jsonl"
    client = _FakeClient(raise_exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        tracing.traced_message(
            client, call_site="judge", trace_path=tp,
            model="claude-haiku-4-5", messages=[],
        )
    rows = [json.loads(l) for l in tp.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["ok"] is False
    assert rows[0]["input_tokens"] == 0


def test_logging_failure_never_breaks_the_call(tmp_path):
    # Make trace_path's parent a FILE so mkdir/open fails inside the writer.
    afile = tmp_path / "afile"
    afile.write_text("x")
    tp = afile / "traces.jsonl"
    client = _FakeClient(_Resp(text="still works"))
    resp = tracing.traced_message(
        client, call_site="synthesis", trace_path=tp,
        model="claude-sonnet-4-6", messages=[],
    )
    assert resp.content[0].text == "still works"  # did not raise
