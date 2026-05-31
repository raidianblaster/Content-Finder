"""Do-no-harm gate (roadmap M0.3).

The key-free digest path must keep working end-to-end with no ANTHROPIC_API_KEY
set — it's the guaranteed-free news utility. This is the network-free companion
to the CI smoke step in .github/workflows/ci.yml.
"""
from __future__ import annotations

from datetime import datetime, timezone

import content_finder as cf


def _items(n):
    return [
        cf.Item(
            title=f"New LLM agent benchmark {i}",
            url=f"https://ex.com/a{i}",
            source=f"Src{i}",
            published=datetime.now(timezone.utc),
            summary="agentic llm model tooling",
        )
        for i in range(n)
    ]


def test_keyfree_pipeline_renders_html_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    items = _items(12)
    monkeypatch.setattr(cf, "RSS_SOURCES", [("fake", "https://fake/rss")])
    monkeypatch.setattr(cf, "HN_QUERIES", [])
    monkeypatch.setattr(cf, "fetch_rss", lambda src, url, since: list(items))
    monkeypatch.setattr(cf, "fetch_hn", lambda *a, **k: [])
    monkeypatch.setattr(cf, "dedupe", lambda lst: sorted(lst, key=lambda x: x.score, reverse=True))

    final_items, _log = cf.gather(days=2, hn_min_points=50, max_per_source=50)
    html = cf.render_html(final_items, top_n=25)

    assert len(final_items) >= cf.MIN_RENDERED_ITEMS
    assert 'class="article-list"' in html
    assert "New LLM agent benchmark 0" in html
    assert len(html) > 500


def test_synthesize_without_key_falls_back_to_plain(monkeypatch):
    """No key → synthesize_with_claude returns the plain ranked list, no network."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = cf.synthesize_with_claude(_items(3), model="claude-sonnet-4-6")
    assert isinstance(out, str) and out.strip()
