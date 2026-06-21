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


def test_fetch_status_logged_per_source(monkeypatch):
    """Each source's fetch outcome (ok + item count, or the error) must be
    recorded so a quiet day can be told apart from silently-broken feeds.
    Regression for 2026-06-21, where ~all feeds returned nothing and stderr
    was the only (lost) signal."""
    monkeypatch.setattr(cf, "RSS_SOURCES", [
        ("Good Feed", "https://good.example/rss"),
        ("Empty Feed", "https://empty.example/rss"),
        ("Bad Feed", "https://bad.example/rss"),
    ])
    monkeypatch.setattr(cf, "HN_QUERIES", [])

    def fake_fetch_rss(src, url, since):
        if src == "Bad Feed":
            raise RuntimeError("HTTP 503 Service Unavailable")
        if src == "Empty Feed":
            return []
        return [_item("LLM agent shipped", "https://good.example/1",
                      source=src, summary="agentic llm model")]

    monkeypatch.setattr(cf, "fetch_rss", fake_fetch_rss)
    monkeypatch.setattr(cf, "fetch_hn", lambda *a, **kw: [])

    _, log = cf.gather(days=1, hn_min_points=50)

    by_source = {s["source"]: s for s in log.fetch_status}
    assert by_source["Good Feed"]["ok"] is True
    assert by_source["Good Feed"]["items"] == 1
    assert by_source["Empty Feed"]["ok"] is True
    assert by_source["Empty Feed"]["items"] == 0
    assert by_source["Bad Feed"]["ok"] is False
    assert by_source["Bad Feed"]["items"] == 0
    assert "503" in by_source["Bad Feed"]["error"]


def test_fetch_status_serialized_in_to_dict(monkeypatch):
    """fetch_status must round-trip through to_dict()/JSON for the review tools."""
    monkeypatch.setattr(cf, "RSS_SOURCES", [("Good Feed", "https://good.example/rss")])
    monkeypatch.setattr(cf, "HN_QUERIES", [])
    monkeypatch.setattr(cf, "fetch_rss", lambda src, url, since: [])
    monkeypatch.setattr(cf, "fetch_hn", lambda *a, **kw: [])

    _, log = cf.gather(days=1, hn_min_points=50)
    decoded = json.loads(json.dumps(log.to_dict()))

    assert "fetch_status" in decoded
    assert decoded["fetch_status"][0]["source"] == "Good Feed"


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
    # write_filter_log writes both a dated file and a `latest.json` pointer.
    files = sorted(log_dir.glob("*.json"))
    names = {f.name for f in files}
    assert "latest.json" in names, f"expected latest.json, got {names}"
    dated = [f for f in files if f.name != "latest.json"]
    assert len(dated) == 1, f"expected exactly one dated log file, got {dated}"
    data = json.loads(dated[0].read_text())
    assert "date" in data
    assert "pipeline" in data
