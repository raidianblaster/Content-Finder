"""Tests for the expanded source list (feature 3)."""
from __future__ import annotations

from urllib.parse import urlparse

import content_finder as cf


NEW_RSS_SOURCE_NAMES = [
    "arXiv cs.AI",
    "Stratechery",
    "Last Week in AI",
    "Dwarkesh Podcast",
    "NIST News",
    "EU AI Office",
]

NEW_HN_QUERIES = ["RAG", "eval", "fine-tuning"]


def test_new_rss_sources_present():
    names = {name for name, _ in cf.RSS_SOURCES}
    for new_name in NEW_RSS_SOURCE_NAMES:
        assert new_name in names, f"missing source: {new_name}"


def test_all_rss_urls_are_well_formed_https():
    for name, url in cf.RSS_SOURCES:
        parsed = urlparse(url)
        assert parsed.scheme == "https", f"{name} url not https: {url}"
        assert parsed.netloc, f"{name} url has no host: {url}"


def test_new_hn_queries_present():
    for q in NEW_HN_QUERIES:
        assert q in cf.HN_QUERIES, f"missing HN query: {q}"


def test_every_source_has_trusted_weight_or_default():
    # Ensures the trusted-weight lookup never explodes for any registered source.
    from datetime import datetime, timezone

    for name, _ in cf.RSS_SOURCES:
        item = cf.Item(
            title="probe",
            url="https://example.com/x",
            source=name,
            published=datetime.now(timezone.utc),
            summary="agentic llm",
        )
        score = cf.score_item(item)
        assert isinstance(score, (int, float))
        assert score >= 0
