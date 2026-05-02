"""Design-handoff tests for Variant A (dark, mobile-first card layout).

Targets `HTML_CSS`, `render_chip_bar`, `wrap_synthesis_html`, `render_html`.
The class names `.chip`, `.is-active`, `.is-hidden` are preserved per the
design handoff README.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import content_finder as cf


# ---------------------------------------------------------------------------
# Design tokens / fonts / colours
# ---------------------------------------------------------------------------

def test_html_css_includes_dark_design_tokens():
    css = cf.HTML_CSS
    for token in ["--bg-0", "--bg-1", "--bg-2", "--border", "--fg", "--fg-mid",
                  "--fg-dim", "--accent", "--green", "--amber"]:
        assert token in css, f"missing token: {token}"
    assert "#0d0d0f" in css
    assert "#131316" in css


def test_dm_sans_dm_mono_loaded_via_google_fonts():
    out = cf.wrap_synthesis_html("## Key takeaways\n- a\n- b\n- c\n", page_date=date(2026, 5, 2))
    assert "fonts.googleapis.com" in out
    assert "DM+Sans" in out
    assert "DM+Mono" in out


def test_html_css_defines_per_tag_color_rules():
    css = cf.HTML_CSS
    for tag in ["Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research"]:
        assert f'tag-{tag}' in css, f"missing per-tag class: tag-{tag}"


# ---------------------------------------------------------------------------
# Chip bar redesign
# ---------------------------------------------------------------------------

def test_chip_bar_emits_pill_chips_with_data_tag():
    bar = cf.render_chip_bar()
    # Still 7 chips (All + 6 taxonomy) — preserved class names
    chips = re.findall(r'<button[^>]*class="chip[^"]*"[^>]*data-tag="([^"]+)"', bar)
    assert chips[0] == "all"
    assert set(chips[1:]) == {"Models", "Agents", "Tooling", "Regulation",
                              "Enterprise", "Research"}


def test_active_chip_styling_per_tag_in_css():
    css = cf.HTML_CSS
    # Active state must exist and be tag-aware (selector that combines chip with the tag)
    assert ".chip.is-active" in css
    assert 'data-tag="Models"' in css or '[data-tag="Models"]' in css


# ---------------------------------------------------------------------------
# Header bar
# ---------------------------------------------------------------------------

def test_header_bar_shows_date_and_title():
    out = cf.wrap_synthesis_html(
        "## Key takeaways\n- a\n- b\n- c\n",
        page_date=date(2026, 5, 2),
    )
    assert 'class="topbar"' in out
    assert "AI Digest" in out
    assert "Sat 2 May 2026" in out or "Sat 02 May 2026" in out


# ---------------------------------------------------------------------------
# Takeaways extraction + collapsible block
# ---------------------------------------------------------------------------

FIXTURE_MD = """## Key takeaways
- One: enterprises are being asked to ship agent guardrails.
- Two: model launches keep accelerating, with cost the new battleground.
- Three: regulation is now arriving from joint multi-country bodies.

## Top story
- **Five Eyes guidance on agentic AI** — Joint guidance warns over-privileged agents are already inside critical infrastructure. **So what:** least-privilege architecture is moving from best practice to compliance. [Five Eyes](https://example.com/five-eyes) {tags: Regulation, Agents}

## Models & capability releases
- **Mistral Medium 3.5 lands** — New mid-tier model with remote-agent support. **So what:** raises pricing pressure on the Sonnet/Haiku tier. [Mistral](https://mistral.ai) {tags: Models}

## Agentic engineering & tooling
- **Codex CLI 0.128.0 adds /goal** — OpenAI's coding agent gains a Ralph-style goal loop. **So what:** agent harnesses are converging on similar primitives. [Simon Willison](https://example.com/codex) {tags: Agents, Tooling}

## Enterprise, regulation & governance
- **GitHub buckles under AI load** — Pragmatic Engineer breaks down a recent multi-day GitHub outage. **So what:** vendor concentration risk is now visible in your dev pipeline. [Pragmatic Engineer](https://example.com/github) {tags: Enterprise, Tooling}
"""


def test_takeaways_extracted_into_dedicated_collapsible_section():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    # Dedicated takeaways section exists
    assert 'class="takeaways"' in out
    assert "takeaways-toggle" in out
    assert "takeaways-body" in out
    # The takeaways list does NOT bleed into the main article list
    takeaway_section = re.search(
        r'<section[^>]*class="takeaways"[^>]*>.*?</section>',
        out, re.DOTALL,
    )
    assert takeaway_section is not None
    # The h2 "Key takeaways" should not also appear inside the main list area
    assert out.count("Key takeaways") <= 2  # one in label, maybe one in aria/visible label


def test_takeaways_toggle_js_present():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    # Toggle handler present
    assert "takeaways-toggle" in out
    # JS toggles a class on the body element
    assert "is-collapsed" in out or "is-hidden" in out


# ---------------------------------------------------------------------------
# Card-style item layout
# ---------------------------------------------------------------------------

def test_synthesis_li_renders_as_card_article():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    # Each story bullet becomes an <article class="item ..." data-tags="...">
    assert re.search(r'<article[^>]*class="[^"]*\bitem\b[^"]*"[^>]*data-tags="[A-Z][^"]*"', out)
    # The card has an explicit title button (tap target)
    assert re.search(r'<button[^>]*class="[^"]*\bitem-title\b', out)
    # The card has a So What callout
    assert 'class="so-what"' in out
    # The card has a "Read article" button
    assert "Read article" in out


def test_item_card_carries_data_tags_for_filter():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    # All article cards expose data-tags so the chip filter still works.
    cards = re.findall(r'<article[^>]*data-tags="([^"]*)"', out)
    # Fixture has 4 sectioned items (top story + 3 categories)
    assert len(cards) >= 4
    assert any("Models" in c for c in cards)
    assert any("Regulation" in c for c in cards)


def test_synthesis_no_leftover_tags_literal():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    assert "{tags:" not in out


# ---------------------------------------------------------------------------
# render_html (no-summarize ranked path) gets the card treatment too
# ---------------------------------------------------------------------------

def _stub_item(source: str, score: float, title: str = "T") -> cf.Item:
    it = cf.Item(
        title=title,
        url="https://example.com/x",
        source=source,
        published=datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc),
        summary="agentic llm",
    )
    it.score = score
    return it


def test_render_html_uses_card_layout_with_score_pill():
    items = [
        _stub_item("Simon Willison", 9.4, "High score story"),
        _stub_item("arXiv cs.AI", 6.1, "Mid score paper"),
    ]
    out = cf.render_html(items, top_n=2, page_date=date(2026, 5, 2))
    # Card structure
    assert re.search(r'<article[^>]*class="[^"]*\bitem\b', out)
    # Score pill (with optional threshold class)
    assert re.search(r'class="score-pill[^"]*"', out)
    # Score value rendered
    assert "9.4" in out
    # Source surfaced
    assert "Simon Willison" in out


# ---------------------------------------------------------------------------
# Interaction JS (expand/collapse on item title click)
# ---------------------------------------------------------------------------

def test_expand_collapse_js_present():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    assert "item-title" in out
    # is-expanded class is the trigger for showing the expanded body
    assert "is-expanded" in out
