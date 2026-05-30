"""Tests for score_components() — the logged breakdown behind score_item (#9).

score_item stays the public scalar API; score_components exposes the same math
as a per-term dict so feedback rows can carry the features the scorer saw.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

import content_finder as cf


def _item(title="New LLM agent", summary="agentic llm", source="Test Source",
          age_hours=0.0, points=None):
    published = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    extra = {"points": points} if points is not None else {}
    return cf.Item(title=title, url="https://ex.com/x", source=source,
                   published=published, summary=summary, extra=extra)


def test_components_total_equals_score_item():
    """The invariant: components["total"] is score_item(item).

    For items older than 7 days the recency term is clamped to 0, so the two
    calls are exactly equal. For a fresh item the only difference between the
    two calls is sub-millisecond clock drift in `age_hours`, so compare with a
    tiny tolerance.
    """
    clock_stable = [
        _item(age_hours=24 * 8),                                            # keyword only
        _item(source="Hacker News", points=900, age_hours=24 * 8),          # hn cap
        _item(title="unrelated", summary="quarterly earnings",
              source="Nobody", age_hours=24 * 9),                           # nothing
        _item(source="Anthropic", age_hours=24 * 10),                       # source trust
    ]
    for it in clock_stable:
        assert cf.score_components(it)["total"] == cf.score_item(it)

    fresh = _item(age_hours=0)  # exercises the recency term
    assert cf.score_components(fresh)["total"] == pytest.approx(
        cf.score_item(fresh), abs=1e-3
    )


def test_components_keys():
    comp = cf.score_components(_item())
    assert set(comp) == {
        "keyword", "recency", "recency_term", "src_bonus", "hn_bonus", "total"
    }


def test_hn_bonus_capped_and_recency_floor():
    hot = _item(source="Hacker News", points=10_000, age_hours=0)
    assert cf.score_components(hot)["hn_bonus"] == 4.0
    stale = _item(age_hours=24 * 30)
    assert cf.score_components(stale)["recency"] == 0.0


def test_recency_term_is_double_recency():
    comp = cf.score_components(_item(age_hours=0))
    assert comp["recency"] == 1.0
    assert comp["recency_term"] == 2.0
