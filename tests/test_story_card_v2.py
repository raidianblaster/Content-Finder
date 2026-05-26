"""V2 story card markup + interaction tests.

Pins the V2 redesign's card contract:
- <article class="story" id="story-N" data-tags="...">
- <div class="story-head" role="button" tabindex="0" aria-expanded="false">
- Tags use data-cat (not tag-X classes)
- .chev SVG chevron, rotates on .story.open
- .story-body uses grid-template-rows 0fr/1fr animation
- .sowhat callout only when so_what is truthy
- .read pill button uses target=_blank rel=noopener noreferrer
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import content_finder as cf


FIXTURE_MD = """## Top story

- **Five Eyes guidance on agentic AI** — Joint guidance warns over-privileged agents are already inside critical infrastructure. **So what:** least-privilege architecture is moving from best practice to compliance. [Five Eyes](https://example.com/five-eyes) {tags: Regulation, Agents}

## Models & capabilities

- **Mistral Medium 3.5 lands** — New mid-tier model with remote-agent support. **So what:** raises pricing pressure on the Sonnet/Haiku tier. [Mistral](https://mistral.ai) {tags: Models}
"""


# ---------------------------------------------------------------------------
# Article wrapper + id contract
# ---------------------------------------------------------------------------

def test_v2_story_uses_story_class_and_story_id():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # Card root carries the V2 .story class (not the old .item class)
    arts = re.findall(r'<article class="story"[^>]*id="story-(\d+)"', out)
    assert len(arts) == 2, f"expected 2 V2 story cards, got {len(arts)}"
    assert arts == ["1", "2"]


def test_v2_story_preserves_data_tags_for_chip_filter():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # data-tags stays on the article wrapper so the chip filter JS keeps working
    assert 'data-tags="Regulation Agents"' in out
    assert 'data-tags="Models"' in out


# ---------------------------------------------------------------------------
# Story head — clickable region with ARIA
# ---------------------------------------------------------------------------

def test_v2_story_head_is_aria_button():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    heads = re.findall(
        r'<div class="story-head"\s+role="button"\s+tabindex="0"\s+aria-expanded="false"',
        out,
    )
    assert len(heads) == 2, f"expected 2 story-head buttons, got {len(heads)}"


def test_v2_story_head_contains_title_and_chevron():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # Headlines render as h3.story-title (not the old item-title button)
    titles = re.findall(r'<h3 class="story-title">([^<]+)</h3>', out)
    assert len(titles) == 2
    assert "Five Eyes guidance on agentic AI" in titles[0]
    # Chevron SVG must be present once per card, inside .chev
    chev = re.findall(r'<span class="chev">\s*<svg', out)
    assert len(chev) == 2, f"expected 2 .chev SVGs, got {len(chev)}"


# ---------------------------------------------------------------------------
# Tags — pastel chips with data-cat
# ---------------------------------------------------------------------------

def test_v2_tags_use_data_cat_attribute():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # V2 uses <span class="tag" data-cat="Models">Models</span>
    # (replaces the legacy <span class="tag tag-Models">)
    assert re.search(r'<span class="tag" data-cat="Regulation">Regulation</span>', out)
    assert re.search(r'<span class="tag" data-cat="Models">Models</span>', out)
    # Old class-based naming is gone from the markup. Strip the embedded
    # <style> block first — dead tag-X CSS rules are PR4 cleanup, not a bug.
    markup_only = re.sub(r"<style>.*?</style>", "", out, flags=re.DOTALL)
    assert "tag-Models" not in markup_only
    assert "tag-Regulation" not in markup_only


# ---------------------------------------------------------------------------
# Source visibility — collapsed AND expanded
# ---------------------------------------------------------------------------

def test_v2_source_short_visible_in_head_meta_row():
    """Source label sits inside .story-head's .story-meta-row so it is visible
    while the card is collapsed (its main job)."""
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    arts = re.findall(r'<article class="story"[^>]*>(.*?)</article>', out, re.DOTALL)
    for art in arts:
        head_m = re.search(r'<div class="story-head"[^>]*>(.*?)</div>\s*<div class="story-body"', art, re.DOTALL)
        assert head_m, "no .story-head before .story-body"
        head = head_m.group(1)
        assert 'class="src"' in head, "source missing from story-head meta row"


# ---------------------------------------------------------------------------
# So-what callout
# ---------------------------------------------------------------------------

def test_v2_sowhat_callout_renders_when_so_what_present():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # Both fixture items have So-what text
    assert out.count('class="sowhat"') == 2
    # Label uses the V2 mono uppercase "So what" string
    assert out.count('class="sowhat-label">So what</') == 2


def test_v2_sowhat_callout_omitted_when_so_what_empty():
    """Per CLAUDE.md / V2 spec: hide the amber callout entirely when there's
    no so-what text rather than rendering an empty box."""
    out = cf._build_card_html(
        item_id=1,
        data_tags="Models",
        title="Headline",
        snippet="Body sentence.",
        so_what="",
        url="https://example.com/x",
        source_name="Example",
    )
    assert 'class="sowhat"' not in out, "empty .sowhat block leaked into card"
    # But the card itself still renders
    assert 'class="story"' in out
    assert 'class="read"' in out


# ---------------------------------------------------------------------------
# Read pill — proper anchor with secure rel
# ---------------------------------------------------------------------------

def test_v2_read_pill_uses_secure_target_blank():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # V2 uses .read (not .read-article) with target=_blank rel="noopener noreferrer"
    reads = re.findall(
        r'<a class="read"\s+href="[^"]+"\s+target="_blank"\s+rel="noopener noreferrer"',
        out,
    )
    assert len(reads) == 2, f"expected 2 .read anchors, got {len(reads)}"


def test_v2_read_pill_arrow_span_present():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # Spec: arrow lives in its own .arrow span so :hover can translate it
    assert out.count('<span class="arrow">') >= 2


# ---------------------------------------------------------------------------
# Expand/collapse JS
# ---------------------------------------------------------------------------

def test_v2_expand_collapse_js_present():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # Listener on the story-head element (click + keydown)
    assert ".story-head" in out
    # Class toggle for open state
    assert "'open'" in out or '"open"' in out
    # aria-expanded sync on toggle
    assert "aria-expanded" in out


# ---------------------------------------------------------------------------
# CSS contract — class names exist in the embedded stylesheet
# ---------------------------------------------------------------------------

def test_v2_card_css_classes_present():
    css = cf.HTML_CSS
    for sel in [".story", ".story-head", ".story-body", ".story-title",
                ".story-summary", ".chev", ".sowhat", ".sowhat-label",
                ".read", ".src", ".src-full"]:
        assert sel in css, f"missing V2 card CSS selector: {sel}"
    # Per-cat tag tints
    for cat in ["Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research"]:
        assert f'data-cat="{cat}"' in css, f"missing per-cat tag rule: {cat}"
    # Grid-rows collapse animation
    assert "grid-template-rows: 0fr" in css
    assert ".story.open .story-body" in css
