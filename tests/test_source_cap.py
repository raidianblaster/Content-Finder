"""Per-source diversity cap (feature: balance the digest across sources)."""
from __future__ import annotations

from datetime import datetime, timezone

import content_finder as cf


def _item(source: str, score: float, title: str = "x") -> cf.Item:
    it = cf.Item(
        title=title,
        url=f"https://example.com/{title}",
        source=source,
        published=datetime.now(timezone.utc),
        summary="agentic llm",
    )
    it.score = score
    return it


def test_apply_source_cap_keeps_top_n_per_source():
    items = (
        [_item("arXiv cs.AI", 12 - i, f"arxiv-{i}") for i in range(7)]
        + [_item("Simon Willison", 10 - i, f"sw-{i}") for i in range(5)]
        + [_item("Hacker News", 8 - i, f"hn-{i}") for i in range(4)]
        + [_item("Stratechery", 6, "strat-1")]
    )

    capped = cf.apply_source_cap(items, max_per_source=3)

    by_source: dict[str, int] = {}
    for it in capped:
        by_source[it.source] = by_source.get(it.source, 0) + 1

    assert by_source["arXiv cs.AI"] == 3
    assert by_source["Simon Willison"] == 3
    assert by_source["Hacker News"] == 3
    assert by_source["Stratechery"] == 1


def test_apply_source_cap_prefers_higher_scores():
    items = [
        _item("arXiv cs.AI", 1, "low"),
        _item("arXiv cs.AI", 9, "high"),
        _item("arXiv cs.AI", 5, "mid"),
        _item("arXiv cs.AI", 0.5, "lowest"),
    ]
    capped = cf.apply_source_cap(items, max_per_source=2)
    titles = {it.title for it in capped}
    assert titles == {"high", "mid"}


def test_gather_applies_source_cap(monkeypatch):
    """gather() must run apply_source_cap so the renderers receive a balanced set."""
    fake_items = [_item("arXiv cs.AI", 10 - i, f"a-{i}") for i in range(8)] + [
        _item("Simon Willison", 5, "sw-1"),
    ]
    monkeypatch.setattr(cf, "fetch_rss", lambda *a, **kw: [])
    monkeypatch.setattr(cf, "fetch_hn", lambda *a, **kw: [])
    monkeypatch.setattr(cf, "dedupe", lambda items: fake_items)

    out = cf.gather(days=1, hn_min_points=50)

    assert sum(1 for it in out if it.source == "arXiv cs.AI") <= 3
