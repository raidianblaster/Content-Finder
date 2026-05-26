"""Design-handoff tests for the V2 layout (warm amber accent, Hanken Grotesk body).

Targets `HTML_CSS`, `render_chip_bar`, `wrap_synthesis_html`, `render_html`.
The class names `.chip`, `.is-active`, `.is-hidden` are preserved per the
original design handoff README. V2 introduces amber accent + masthead.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import content_finder as cf


# ---------------------------------------------------------------------------
# Design tokens / fonts / colours — V2
# ---------------------------------------------------------------------------

def test_html_css_includes_v2_design_tokens():
    css = cf.HTML_CSS
    for token in ["--bg", "--surface", "--surface-2", "--line", "--line-strong",
                  "--fg", "--fg-2", "--fg-3", "--accent", "--accent-soft"]:
        assert token in css, f"missing V2 token: {token}"
    # V2 spec colour values
    assert "#0a0a0e" in css
    assert "#14141c" in css


def test_css_uses_warm_amber_accent():
    """V2 spec replaces the purple accent with warm amber #e8b765.

    Per-tag chip rules + .tag-* pills still reference the old --purple/--green
    backward-compat aliases (cleaned up in PR2/PR3); the load-bearing assertion
    is that the primary --accent token resolves to amber, not purple.
    """
    css = cf.HTML_CSS
    assert "#e8b765" in css, "amber accent hex missing from CSS"
    assert re.search(r"--accent:\s*#e8b765", css), \
        "--accent should be bound to the amber hex"


def test_hanken_grotesk_and_jetbrains_mono_loaded_via_google_fonts():
    out = cf.wrap_synthesis_html("## Key takeaways\n- a\n- b\n- c\n", page_date=date(2026, 5, 2))
    assert "fonts.googleapis.com" in out
    assert "Hanken+Grotesk" in out
    assert "JetBrains+Mono" in out


def test_html_css_defines_per_tag_color_rules():
    """V2 per-tag tints are keyed by data-cat (not tag-X class names)."""
    css = cf.HTML_CSS
    for tag in ["Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research"]:
        assert f'data-cat="{tag}"' in css, f"missing per-cat rule: {tag}"


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
    # Each story bullet becomes an <article class="story" data-tags="...">
    assert re.search(r'<article class="story"[^>]*data-tags="[A-Z][^"]*"', out)
    # The card's head is the click/keyboard target (role=button on div)
    assert re.search(r'<div class="story-head"\s+role="button"', out)
    # The card has a "So what" callout
    assert 'class="sowhat"' in out
    # The card has a "Read the article" CTA pill
    assert "Read the article" in out


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
    # V2 card structure (no-summarize path renders through the same builder)
    assert re.search(r'<article class="story"', out)
    # Score pill (with optional threshold class)
    assert re.search(r'class="score-pill[^"]*"', out)
    # Score value rendered
    assert "9.4" in out
    # Source surfaced
    assert "Simon Willison" in out


# ---------------------------------------------------------------------------
# Interaction JS (expand/collapse on story-head click)
# ---------------------------------------------------------------------------

def test_expand_collapse_js_present():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    # V2 toggles a .open class on the .story article
    assert "story-head" in out
    assert "'open'" in out or '"open"' in out


# ---------------------------------------------------------------------------
# Route A spec — takeaway → article link rows (the piece previously missing)
# ---------------------------------------------------------------------------

FIXTURE_LINKS = """## Key takeaways
- Agentic infra is converging across vendors. [Claude 4 native MCP](https://anthropic.com/blog) [MCP hits 50k](https://latent.space/)
- EU Act deadline is most actionable. [EU AI Act update](https://importai.com/)
- Open models closing the gap on coding. [Llama 4 Scout](https://simonwillison.net/)

## Top story
- **Five Eyes guidance** — detail. **So what:** implication. [Five Eyes](https://example.com/five-eyes) {tags: Regulation, Agents}

## Models & capability releases
- **Llama 4 Scout drops** — 17B MoE model. **So what:** open coding gap narrows. [Simon Willison](https://simonwillison.net/) {tags: Models, Tooling}
"""


def test_system_prompt_instructs_source_links_in_takeaways():
    """SYSTEM_PROMPT must tell Claude to ground each takeaway with [label](url) links."""
    prompt = cf.SYSTEM_PROMPT
    kta_block = prompt.split("Key takeaways")[1].split("Top story")[0].lower()
    # The block describing takeaway format must mention links/url syntax.
    assert "link" in kta_block or "[" in kta_block


def test_takeaway_links_render_multiple_per_takeaway():
    """All [label](url) links in a takeaway bullet must surface in the output."""
    out = cf.wrap_synthesis_html(FIXTURE_LINKS, page_date=date(2026, 5, 2))
    # Both links from takeaway 1
    assert "Claude 4 native MCP" in out
    assert "MCP hits 50k" in out
    # Single link from takeaway 2
    assert "EU AI Act update" in out
    # Spec arrow indicator (link rows end with "↓")
    assert "↓" in out
    # No leftover {tags: literal anywhere
    assert "{tags:" not in out


def test_takeaway_links_have_navigation_hooks():
    """Each takeaway link must carry a hook (data-item-url) so JS can scroll/expand."""
    out = cf.wrap_synthesis_html(FIXTURE_LINKS, page_date=date(2026, 5, 2))
    # Link rows expose the source URL so navigateToItem() can find the matching card.
    assert "data-item-url" in out
    # The matching ranked/synthesis card carries the same URL on its read-article link.
    assert "https://simonwillison.net/" in out


def test_navigate_to_item_js_present():
    """navigateToItem must be in the page script — collapses takeaways, scrolls, expands."""
    out = cf.wrap_synthesis_html(FIXTURE_LINKS, page_date=date(2026, 5, 2))
    assert "navigateToItem" in out


def test_takeaway_count_badge_in_toggle():
    """Toggle button must show the count of takeaways (Route A spec section 3)."""
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 2))
    toggle = re.search(
        r'<button[^>]*class="takeaways-toggle"[^>]*>.*?</button>', out, re.DOTALL,
    )
    assert toggle is not None
    # FIXTURE_MD has 3 takeaway bullets
    assert "3" in toggle.group(0)


# ---------------------------------------------------------------------------
# _page_shell archive_href parameter (2026-05-23 bugfix)
# ---------------------------------------------------------------------------

def test_page_shell_default_archive_href():
    """Homepage uses href="archive.html" (relative, same directory)."""
    html = cf._page_shell(date(2026, 1, 1), 5)
    assert 'href="archive.html"' in html


def test_page_shell_custom_archive_href():
    """Archived copies need href="../archive.html" to resolve one level up."""
    html = cf._page_shell(date(2026, 1, 1), 5, archive_href="../archive.html")
    assert 'href="../archive.html"' in html
    assert 'href="archive.html"' not in html
