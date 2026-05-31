"""Tests for the trace rollup + traces.py CLI (roadmap M0.1)."""
from __future__ import annotations

import json

import tracing
import traces


def _write(tp, rows):
    tp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_rollup_aggregates_by_call_site(tmp_path):
    tp = tmp_path / "traces.jsonl"
    _write(tp, [
        {"ts": "2026-05-30T01:00:00+00:00", "call_site": "synthesis",
         "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0010,
         "latency_ms": 1200.0, "ok": True},
        {"ts": "2026-05-30T02:00:00+00:00", "call_site": "judge",
         "input_tokens": 2000, "output_tokens": 100, "cost_usd": 0.0025,
         "latency_ms": 800.0, "ok": True},
        {"ts": "2026-05-30T03:00:00+00:00", "call_site": "judge",
         "input_tokens": 1000, "output_tokens": 50, "cost_usd": 0.0015,
         "latency_ms": 400.0, "ok": False},
    ])
    data = tracing.rollup(tracing.load_traces(tp))
    assert data["calls"] == 3
    assert data["cost_usd"] == round(0.0010 + 0.0025 + 0.0015, 6)
    assert data["by_call_site"]["judge"]["calls"] == 2
    assert data["by_call_site"]["judge"]["errors"] == 1
    assert data["p50_latency_ms"] == 800.0


def test_rollup_since_filter(tmp_path):
    tp = tmp_path / "traces.jsonl"
    _write(tp, [
        {"ts": "2026-05-29T10:00:00+00:00", "call_site": "synthesis",
         "cost_usd": 0.01, "input_tokens": 1, "output_tokens": 1,
         "latency_ms": 1, "ok": True},
        {"ts": "2026-05-30T10:00:00+00:00", "call_site": "synthesis",
         "cost_usd": 0.02, "input_tokens": 1, "output_tokens": 1,
         "latency_ms": 1, "ok": True},
    ])
    data = tracing.rollup(tracing.load_traces(tp), since="2026-05-30")
    assert data["calls"] == 1
    assert data["cost_usd"] == 0.02


def test_load_traces_missing_file_is_empty(tmp_path):
    assert tracing.load_traces(tmp_path / "nope.jsonl") == []


def test_cli_main_prints_summary(tmp_path, capsys):
    tp = tmp_path / "traces.jsonl"
    _write(tp, [{"ts": "2026-05-30T01:00:00+00:00", "call_site": "synthesis",
                 "model": "m", "input_tokens": 10, "output_tokens": 5,
                 "cost_usd": 0.0, "latency_ms": 1.0, "ok": True}])
    rc = traces.main(["--path", str(tp)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "calls=1" in out
    assert "synthesis" in out
