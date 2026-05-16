"""Fetcher behavior tests."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import content_finder as cf


def test_fetch_rss_uses_httpx_timeout_and_parses_response_bytes(monkeypatch):
    calls: dict[str, object] = {}

    class Response:
        content = b"<rss><channel></channel></rss>"

        def raise_for_status(self) -> None:
            calls["raise_for_status"] = True

    def fake_get(url, *, headers, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["timeout"] = timeout
        return Response()

    def fake_parse(payload):
        calls["payload"] = payload
        return SimpleNamespace(
            bozo=False,
            entries=[
                SimpleNamespace(
                    title="Agentic update",
                    link="https://example.com/agentic",
                    summary="<p>agentic llm</p>",
                    published_parsed=time.gmtime(),
                )
            ],
        )

    monkeypatch.setattr(cf.httpx, "get", fake_get)
    monkeypatch.setattr(cf.feedparser, "parse", fake_parse)

    since = datetime.now(timezone.utc) - timedelta(days=1)
    items = cf.fetch_rss("Example", "https://example.com/feed.xml", since)

    assert calls["url"] == "https://example.com/feed.xml"
    assert calls["headers"] == {"User-Agent": "ContentFinder/1.0"}
    assert calls["timeout"] == 15
    assert calls["payload"] == Response.content
    assert calls["raise_for_status"] is True
    assert len(items) == 1
    assert items[0].title == "Agentic update"
