"""Accessibility + interaction affordance tests for the homepage (V2).

These are additive contracts: they shouldn't change the look, but they improve
keyboard navigation and reduce-motion support.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import content_finder as cf


def _items(n: int = 2) -> list[cf.Item]:
    out: list[cf.Item] = []
    for i in range(n):
        out.append(
            cf.Item(
                title=f"Story {i}",
                url=f"https://example.com/{i}",
                source="Example",
                published=datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc),
                summary="A short summary.",
            )
        )
    return out


def test_skip_link_present_and_targets_main_content():
    out = cf.render_html(_items(2), top_n=2, page_date=date(2026, 5, 26))
    assert 'class="skip-link"' in out
    assert 'href="#content"' in out
    assert re.search(r"<main[^>]*id=\"content\"[^>]*>", out), "main should be id=content for skip link"


def test_css_supports_prefers_reduced_motion():
    css = cf.HTML_CSS
    assert "prefers-reduced-motion" in css


def test_story_head_wires_aria_controls_to_story_body_id():
    out = cf.render_html(_items(2), top_n=2, page_date=date(2026, 5, 26))
    assert re.search(r'<div class="story-head"[^>]*aria-controls="story-body-1"', out)
    assert re.search(r'<div class="story-body"[^>]*id="story-body-1"', out)
