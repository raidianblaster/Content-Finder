"""Tests for judge.py — Haiku triage of per-run filter logs."""
from __future__ import annotations

import json
import pytest


SAMPLE_LOG = {
    "date": "2026-05-17",
    "prompt_version": "v1",
    "pipeline": {
        "fetched": 10, "after_keyword_filter": 6,
        "after_dedupe": 5, "after_ttl_filter": 4, "after_source_cap": 2,
    },
    "dropped_keyword": [
        # score 0.0 — should be excluded from prompt
        {"title": "Quarterly earnings rise", "url": "https://ex.com/finance",
         "source": "Techmeme", "score": 0.0, "age_days": 0.5},
        # score 4.5 — should be included
        {"title": "Anthropic raises Series D", "url": "https://ex.com/fundraise",
         "source": "TechCrunch", "score": 4.5, "age_days": 0.3},
        # score 7.0 — should be included
        {"title": "Claude beats GPT-4 on bench", "url": "https://ex.com/benchmark",
         "source": "Anthropic", "score": 7.0, "age_days": 0.2},
    ],
    "dropped_dedupe": [
        {"title": "Old story rerun", "url": "https://ex.com/dup",
         "source": "HN", "score": 3.0, "age_days": 1.1},
    ],
    "dropped_ttl": [
        {"title": "MCP write-up", "url": "https://ex.com/mcp-old",
         "source": "Simon Willison", "score": 6.8, "age_days": 1.3},
    ],
    "dropped_source_cap": [
        {"title": "Fourth MindStudio post", "url": "https://ex.com/ms-4",
         "source": "MindStudio", "score": 4.5, "age_days": 0.8},
    ],
    "final": [
        {"title": "Claude SDK release", "url": "https://ex.com/sdk",
         "source": "Anthropic", "score": 9.1, "age_days": 0.4},
        {"title": "MCP analysis", "url": "https://ex.com/mcp",
         "source": "Simon Willison", "score": 8.3, "age_days": 0.6},
    ],
}


# --------------------------------------------------------------------------- #
# 1. build_judge_prompt — item selection logic
# --------------------------------------------------------------------------- #

def test_build_judge_prompt_excludes_low_score_keyword_drops():
    import judge
    prompt = judge.build_judge_prompt(SAMPLE_LOG)
    assert "ex.com/finance" not in prompt      # score 0.0 → excluded
    assert "ex.com/fundraise" in prompt        # score 4.5 → included
    assert "ex.com/benchmark" in prompt        # score 7.0 → included


def test_build_judge_prompt_includes_all_other_stage_drops():
    import judge
    prompt = judge.build_judge_prompt(SAMPLE_LOG)
    assert "ex.com/dup" in prompt
    assert "ex.com/mcp-old" in prompt
    assert "ex.com/ms-4" in prompt


def test_build_judge_prompt_caps_total_items():
    import judge
    big_log = {
        **SAMPLE_LOG,
        "dropped_keyword": [
            {"title": f"Story {i}", "url": f"https://ex.com/k{i}",
             "source": "X", "score": 5.0, "age_days": 0.5}
            for i in range(80)
        ],
    }
    prompt = judge.build_judge_prompt(big_log, max_items=60)
    count = sum(1 for i in range(80) if f"ex.com/k{i}" in prompt)
    assert count <= 60


# --------------------------------------------------------------------------- #
# 2. parse_judge_response
# --------------------------------------------------------------------------- #

def test_parse_judge_response_valid():
    import judge
    resp = json.dumps({
        "suspect_drops": [
            {"url": "https://ex.com/fundraise", "stage": "dropped_keyword",
             "reason": "relevant AI funding news"},
        ],
        "suspect_keeps": [],
    })
    result = judge.parse_judge_response(resp)
    assert len(result["suspect_drops"]) == 1
    assert result["suspect_drops"][0]["url"] == "https://ex.com/fundraise"
    assert result["suspect_keeps"] == []


def test_parse_judge_response_malformed_returns_empty():
    import judge
    assert judge.parse_judge_response("not json") == {"suspect_drops": [], "suspect_keeps": []}
    assert judge.parse_judge_response('{"missing_keys": true}') == {
        "suspect_drops": [], "suspect_keeps": []
    }


# --------------------------------------------------------------------------- #
# 3. run_judge — writes judge JSON with correct shape
# --------------------------------------------------------------------------- #

def test_run_judge_writes_judge_json(tmp_path):
    import judge
    logs_dir = tmp_path / "docs" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "2026-05-17.json").write_text(json.dumps(SAMPLE_LOG))

    class _Content:
        text = json.dumps({
            "suspect_drops": [
                {"url": "https://ex.com/fundraise", "stage": "dropped_keyword",
                 "reason": "AI funding news"},
            ],
            "suspect_keeps": [
                {"url": "https://ex.com/sdk", "reason": "too speculative"},
            ],
        })

    class _Msg:
        content = [_Content()]

    class _Messages:
        def create(self, **kwargs):
            return _Msg()

    class _Client:
        messages = _Messages()

    out = judge.run_judge("2026-05-17", root=tmp_path, client=_Client())
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["date"] == "2026-05-17"
    assert "judge_prompt_version" in data
    assert isinstance(data["suspect_drops"], list)
    assert isinstance(data["suspect_keeps"], list)
    assert data["suspect_drops"][0]["url"] == "https://ex.com/fundraise"


def test_run_judge_missing_log_raises(tmp_path):
    import judge
    (tmp_path / "docs" / "logs").mkdir(parents=True)
    with pytest.raises(FileNotFoundError) as exc:
        judge.run_judge("2099-01-01", root=tmp_path, client=object())
    assert "2099-01-01" in str(exc.value)
