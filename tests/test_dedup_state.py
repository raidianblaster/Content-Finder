"""Tests for canonical_url() — extracted from dedupe() as the safety net
for the upcoming cross-day dedup feature.
"""
from __future__ import annotations

from datetime import datetime, timezone

import content_finder as cf


def _item(url: str, title: str, score: float = 5.0) -> cf.Item:
    it = cf.Item(
        title=title,
        url=url,
        source="Test",
        published=datetime.now(timezone.utc),
        summary="agentic",
    )
    it.score = score
    return it


# --------------------------------------------------------------------------- #
# Group A — canonical_url()
# --------------------------------------------------------------------------- #

def test_A1_plain_url_unchanged():
    assert cf.canonical_url("https://example.com/post") == "https://example.com/post"


def test_A2_query_string_stripped():
    assert (
        cf.canonical_url("https://example.com/post?utm_source=twitter")
        == "https://example.com/post"
    )


def test_A3_trailing_slash_stripped():
    assert cf.canonical_url("https://example.com/post/") == "https://example.com/post"


def test_A4_query_and_trailing_slash_both_stripped():
    assert (
        cf.canonical_url("https://example.com/post/?utm_source=x")
        == "https://example.com/post"
    )


def test_A5_idempotent():
    samples = [
        "https://example.com/post",
        "https://example.com/post/",
        "https://example.com/post?x=1",
        "https://example.com/post/?x=1",
        "https://news.ycombinator.com/item?id=42",
    ]
    for u in samples:
        once = cf.canonical_url(u)
        twice = cf.canonical_url(once)
        assert once == twice, f"not idempotent: {u!r} -> {once!r} -> {twice!r}"


def test_A6_hn_discussion_url_collapses_documents_existing_behavior():
    # Pre-existing behavior: dedupe() strips ?id=, so all bare HN discussion
    # URLs canonicalize to the same string. This test exists to flag the
    # collapse if canonical_url is later changed without considering HN.
    a = cf.canonical_url("https://news.ycombinator.com/item?id=1")
    b = cf.canonical_url("https://news.ycombinator.com/item?id=2")
    assert a == b == "https://news.ycombinator.com/item"


def test_A7_dedupe_url_collapse_behavior_unchanged_after_refactor():
    """Regression: URL canonicalization in dedupe() must be unchanged.

    Three URL variants of the same article (bare, trailing slash, tracker)
    should collapse to one entry. Highest score wins.
    """
    items = [
        _item("https://example.com/a", "Alpha one", score=10),
        _item("https://example.com/a/", "Beta two", score=8),
        _item("https://example.com/a?utm_source=tw", "Gamma three", score=9),
        _item("https://example.com/b", "Delta four", score=7),
    ]
    out = cf.dedupe(items)
    urls = [it.url for it in out]
    # The bare URL (highest score in the canonical-collapsed group) wins.
    assert urls == ["https://example.com/a", "https://example.com/b"]
