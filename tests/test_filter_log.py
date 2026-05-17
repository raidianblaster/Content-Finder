"""Tests for FilterLog — per-run structured log of pipeline filtering decisions."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import content_finder as cf


def _item(title: str, url: str, source: str = "Test Source", summary: str = "agentic llm") -> cf.Item:
    return cf.Item(
        title=title,
        url=url,
        source=source,
        published=datetime.now(timezone.utc),
        summary=summary,
    )


def _bypass_fetchers(monkeypatch, items_to_inject):
    """Stub out network fetchers; inject items via dedupe patch."""
    monkeypatch.setattr(cf, "RSS_SOURCES", [])
    monkeypatch.setattr(cf, "HN_QUERIES", [])

    def fake_dedupe(_items):
        return sorted(items_to_inject, key=lambda x: x.score, reverse=True)

    monkeypatch.setattr(cf, "dedupe", fake_dedupe)


def test_gather_returns_tuple(monkeypatch):
    """gather() must return a (list[Item], FilterLog) tuple."""
    _bypass_fetchers(monkeypatch, [])
    result = cf.gather(days=1, hn_min_points=50)
    assert isinstance(result, tuple), "gather() must return a tuple"
    assert len(result) == 2
    items, log = result
    assert isinstance(items, list)
    assert isinstance(log, cf.FilterLog)


def test_dropped_keyword_items_are_logged(monkeypatch):
    """Items with zero keyword signal must appear in log.dropped_keyword."""
    no_signal = _item("Corporate earnings fell 3%", "https://example.com/finance", summary="quarterly report")
    has_signal = _item("New LLM agent released", "https://example.com/ai", summary="agentic llm model")

    # Use one fake RSS source so the ThreadPoolExecutor calls fetch_rss once.
    monkeypatch.setattr(cf, "RSS_SOURCES", [("fake", "https://fake.com/rss")])
    monkeypatch.setattr(cf, "HN_QUERIES", [])
    monkeypatch.setattr(cf, "fetch_rss", lambda src, url, since: [no_signal, has_signal])
    monkeypatch.setattr(cf, "fetch_hn", lambda *a, **kw: [])

    def fake_dedupe(_items):
        return sorted(_items, key=lambda x: x.score, reverse=True)

    monkeypatch.setattr(cf, "dedupe", fake_dedupe)

    _, log = cf.gather(days=1, hn_min_points=50)

    dropped_urls = {d["url"] for d in log.dropped_keyword}
    assert no_signal.url in dropped_urls, (
        f"no-signal item should be in dropped_keyword, got: {log.dropped_keyword}"
    )
    assert has_signal.url not in dropped_urls, (
        "keyword-matching item must not appear in dropped_keyword"
    )


def test_kept_items_appear_in_log_final(monkeypatch):
    """Items that survive all filters must appear in log.final."""
    item = _item("LLM agent benchmark published", "https://example.com/bench", summary="agentic llm")
    _bypass_fetchers(monkeypatch, [item])

    items_out, log = cf.gather(days=1, hn_min_points=50, max_per_source=10)

    final_urls = {d["url"] for d in log.final}
    assert item.url in final_urls, f"kept item should be in log.final, got: {log.final}"


def test_source_cap_drops_are_logged(monkeypatch):
    """Items cut by the per-source cap must appear in log.dropped_source_cap."""
    source = "ArXiv AI"
    items = [
        _item(f"LLM paper {i}", f"https://arxiv.org/{i}", source=source, summary="agentic llm model")
        for i in range(5)
    ]
    _bypass_fetchers(monkeypatch, items)

    _, log = cf.gather(days=1, hn_min_points=50, max_per_source=2)

    assert len(log.dropped_source_cap) >= 3, (
        f"Expected at least 3 source-capped items, got {len(log.dropped_source_cap)}"
    )
    capped_urls = {d["url"] for d in log.dropped_source_cap}
    # All capped items should be from the same source
    for item in items:
        if item.url in capped_urls:
            assert log.dropped_source_cap[0]["source"] == source


def test_filter_log_json_serializable(monkeypatch):
    """FilterLog.to_dict() must be JSON-serialisable without error."""
    _bypass_fetchers(monkeypatch, [])
    _, log = cf.gather(days=1, hn_min_points=50)

    d = log.to_dict()
    # Must not raise
    encoded = json.dumps(d)
    decoded = json.loads(encoded)

    assert "date" in decoded
    assert "pipeline" in decoded
    assert "dropped_keyword" in decoded
    assert "final" in decoded


def test_write_filter_log_creates_file(monkeypatch, tmp_path):
    """write_filter_log() must write a valid JSON file to <out_dir>/logs/YYYY-MM-DD.json."""
    _bypass_fetchers(monkeypatch, [])
    _, log = cf.gather(days=1, hn_min_points=50)

    cf.write_filter_log(log, tmp_path)

    log_dir = tmp_path / "logs"
    assert log_dir.exists(), "logs/ subdirectory should be created"
    files = list(log_dir.glob("*.json"))
    assert len(files) == 1, f"expected 1 log file, got {files}"
    data = json.loads(files[0].read_text())
    assert "date" in data
    assert "pipeline" in data
