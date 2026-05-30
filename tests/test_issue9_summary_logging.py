"""Issue #9 — log the article summary + score-component breakdown.

Feedback rows must carry the text and features the scorer saw, otherwise the
self-tuning scorer (roadmap M2.1) has nothing to learn from.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import content_finder as cf


def _item(summary="agentic llm tooling"):
    return cf.Item(
        title="New Claude agent SDK release",
        url="https://ex.com/agent-sdk",
        source="Anthropic",
        published=datetime.now(timezone.utc),
        summary=summary,
    )


def test_item_log_dict_includes_summary_and_components():
    it = _item("UNIQUE_SUMMARY_TOKEN agentic sdk")
    it.score = cf.score_item(it)
    d = cf._item_log_dict(it)
    assert d["summary"] == "UNIQUE_SUMMARY_TOKEN agentic sdk"
    assert "score_components" in d
    # total is the same arithmetic as score_item (modulo sub-ms recency drift).
    assert d["score_components"]["total"] == pytest.approx(cf.score_item(it), abs=1e-3)


def test_summary_flows_into_review_item_meta_and_jsonl():
    import review
    log = {
        "date": "2026-05-17", "prompt_version": "v1",
        "pipeline": {"fetched": 1, "after_keyword_filter": 1, "after_dedupe": 1,
                     "after_ttl_filter": 1, "after_source_cap": 1},
        "dropped_keyword": [], "dropped_dedupe": [], "dropped_ttl": [],
        "dropped_source_cap": [],
        "final": [{
            "title": "New Claude agent SDK release", "url": "https://ex.com/agent-sdk",
            "source": "Anthropic", "score": 9.1, "age_days": 0.4,
            "summary": "UNIQUE_SUMMARY_TOKEN agentic sdk",
        }],
    }
    html = review.render(log)
    assert "UNIQUE_SUMMARY_TOKEN" in html, "summary should be injected into ITEM_META"
    assert "summary: meta.summary" in html, "buildJSONL should export the summary field"
