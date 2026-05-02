"""Tests for the HKT-aware date logic (feature 1)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import content_finder as cf


def test_today_hkt_returns_hk_date_when_utc_is_previous_day():
    # 23:30 UTC May 1 == 07:30 HKT May 2
    now = datetime(2026, 5, 1, 23, 30, tzinfo=timezone.utc)
    assert cf.today_hkt(now=now) == date(2026, 5, 2)


def test_today_hkt_returns_hk_date_when_utc_is_same_day():
    # 06:00 UTC May 2 == 14:00 HKT May 2
    now = datetime(2026, 5, 2, 6, 0, tzinfo=timezone.utc)
    assert cf.today_hkt(now=now) == date(2026, 5, 2)


def test_wrap_synthesis_html_uses_passed_page_date():
    out = cf.wrap_synthesis_html("# hello", page_date=date(2026, 5, 2))
    # 2026-05-02 is a Saturday
    assert "Sat 02 May 2026" in out
    # Both <title> and <h1> should carry the date
    assert out.count("Sat 02 May 2026") >= 2


def test_render_html_uses_passed_page_date():
    out = cf.render_html(items=[], top_n=0, page_date=date(2026, 5, 2))
    assert "Sat 02 May 2026" in out


def test_main_passes_hkt_date_to_renderers(tmp_path, monkeypatch):
    # Stub out the network/LLM layers
    fake_item = cf.Item(
        title="Stub",
        url="https://example.com/x",
        source="Simon Willison",
        published=datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc),
        summary="agentic",
    )
    fake_item.score = 5.0

    monkeypatch.setattr(cf, "gather", lambda *a, **kw: [fake_item])
    monkeypatch.setattr(cf, "today_hkt", lambda now=None: date(2026, 5, 2))
    monkeypatch.setattr(
        cf, "synthesize_with_claude", lambda items, model: "## Key takeaways\n- a\n- b\n- c\n"
    )

    out_path: Path = tmp_path / "out.html"
    monkeypatch.setattr(
        "sys.argv",
        ["content_finder.py", "--days", "1", "--format", "html", "--out", str(out_path)],
    )

    rc = cf.main()
    assert rc == 0
    body = out_path.read_text()
    assert "Sat 02 May 2026" in body
