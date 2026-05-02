"""Synthesis-card robustness — fixes the "every card below Top Story is broken"
regression where Python markdown wraps loose-list LIs in ``<p>`` and the
parser silently fell through to a raw-markdown dump.

Each test pins down one user-visible failure mode so it can never come back
without the suite shouting.
"""
from __future__ import annotations

import re
from datetime import date

import content_finder as cf


# Loose lists (blank lines between bullets) — markdown wraps each <li> in <p>.
# This is the shape that broke production today.
LOOSE_FIXTURE = """## Models & capability releases

- **xAI launches Grok 4.3 with 1M context** — Body sentence about pricing and reasoning. **So what:** Strategic implication for PMs in regulated environments. [VentureBeat](https://venturebeat.example/grok-43) {tags: Models, Enterprise}

- **OpenAI restricts GPT-5.5 Cyber access** — Second body sentence describing the change. **So what:** Another point about enterprise procurement. [TechCrunch](https://techcrunch.example/gpt55) {tags: Models, Regulation}

- **Codex CLI 0.128.0 ships /goal** — Third body. **So what:** Third implication. [Simon Willison](https://simonwillison.example/codex) {tags: Agents, Tooling}
"""


# --- Bug 1: loose-list LIs must parse into structured cards ---------------- #

def test_synthesis_card_handles_loose_list_with_p_wrapper():
    """Markdown wraps blank-separated LIs in <p>; parser must still build a card."""
    out = cf.wrap_synthesis_html(LOOSE_FIXTURE, page_date=date(2026, 5, 2))
    # No raw markdown leakage anywhere
    assert "**" not in out, "raw bold markers leaked into HTML"
    assert "{tags:" not in out, "{tags:} literal leaked"
    assert "[VentureBeat]" not in out, "raw markdown link leaked"
    assert "[TechCrunch]" not in out
    assert "[Simon Willison]" not in out
    # Source URLs render as real anchors
    assert 'href="https://venturebeat.example/grok-43"' in out
    assert 'href="https://techcrunch.example/gpt55"' in out
    assert 'href="https://simonwillison.example/codex"' in out
    # data-tags carried through for the chip filter
    assert 'data-tags="Models Enterprise"' in out


# --- Bug 2: title button holds ONLY the headline --------------------------- #

def test_synthesis_card_title_button_contains_only_headline():
    """The .item-title must hold the headline — never the full bullet dump."""
    out = cf.wrap_synthesis_html(LOOSE_FIXTURE, page_date=date(2026, 5, 2))
    titles = re.findall(
        r'<button[^>]*class="item-title"[^>]*>(.*?)</button>',
        out, re.DOTALL,
    )
    assert len(titles) == 3, f"expected 3 title buttons, got {len(titles)}"
    expected_headlines = [
        "xAI launches Grok 4.3",
        "OpenAI restricts GPT-5.5 Cyber",
        "Codex CLI 0.128.0 ships /goal",
    ]
    for title, expected in zip(titles, expected_headlines):
        # Strip any chevron / icon markup so we compare just the text.
        title_text = re.sub(r'<[^>]+>', '', title).strip()
        assert expected in title_text, f"missing headline: {expected}"
        # And the title must NOT include body/so-what/source/markdown noise.
        assert "So what" not in title_text
        assert "{tags:" not in title_text
        assert "VentureBeat" not in title_text
        assert "TechCrunch" not in title_text
        assert "[" not in title_text
        assert "**" not in title_text


# --- Bug 3: source visible in collapsed (default) state -------------------- #

def test_synthesis_card_source_visible_without_expanding():
    """Source must appear in .meta OUTSIDE .item-body (visible when collapsed)."""
    out = cf.wrap_synthesis_html(LOOSE_FIXTURE, page_date=date(2026, 5, 2))
    articles = re.findall(
        r'<article class="item"[^>]*>(.*?)</article>', out, re.DOTALL,
    )
    assert len(articles) == 3
    expected_sources = ["VentureBeat", "TechCrunch", "Simon Willison"]
    for art, expected in zip(articles, expected_sources):
        # The .item-body must close before the .meta div.
        body_m = re.search(r'<div class="item-body">.*?</div>', art, re.DOTALL)
        assert body_m, "no .item-body in card"
        after_body = art[body_m.end():]
        assert 'class="meta"' in after_body, "meta row missing or inside body"
        assert expected in after_body, f"source {expected} missing from meta"


# --- Bug 4: read-article is a real <a>, not literal markdown -------------- #

def test_synthesis_card_read_article_is_real_anchor():
    """Source URL must render as <a class='read-article' href='...'>."""
    out = cf.wrap_synthesis_html(LOOSE_FIXTURE, page_date=date(2026, 5, 2))
    for url in [
        "https://venturebeat.example/grok-43",
        "https://techcrunch.example/gpt55",
        "https://simonwillison.example/codex",
    ]:
        assert re.search(
            r'<a[^>]*class="read-article"[^>]*href="' + re.escape(url) + r'"',
            out,
        ), f"no read-article anchor for {url}"


# --- Bug 5: every bullet gets a full structured card ----------------------- #

def test_multiple_synthesis_items_all_get_structured_cards():
    """Every bullet must produce .item-body + .so-what + .read-article + .source."""
    out = cf.wrap_synthesis_html(LOOSE_FIXTURE, page_date=date(2026, 5, 2))
    articles = re.findall(
        r'<article class="item"[^>]*>(.*?)</article>', out, re.DOTALL,
    )
    assert len(articles) == 3
    for i, art in enumerate(articles, 1):
        assert 'class="item-body"' in art, f"card {i} missing item-body"
        assert 'class="so-what"' in art, f"card {i} missing so-what callout"
        assert 'class="read-article"' in art, f"card {i} missing read-article CTA"
        assert 'class="source"' in art, f"card {i} missing source meta"


# --- Bug 6: nothing — and I mean nothing — leaks raw markdown -------------- #

def test_no_raw_markdown_leaks_anywhere_in_output():
    """Sweep the full page for raw markdown noise that breaks the visual."""
    out = cf.wrap_synthesis_html(LOOSE_FIXTURE, page_date=date(2026, 5, 2))
    assert "**" not in out, "raw bold markers in output"
    assert "{tags:" not in out, "raw {tags:} literal in output"
    # No raw markdown links: pattern "](http" only appears in literal markdown.
    assert "](http" not in out, "raw markdown link syntax in output"


# --- Bug 7: fallback path is sane when bullet shape is unrecognised ------- #

def test_fallback_card_does_not_dump_raw_markdown():
    """If a bullet doesn't match the structured shape, fallback must still be clean."""
    md = """## Top story

- This bullet has no bold headline and no So what clause but has a [Source](https://example.com/x) {tags: Models}
"""
    out = cf.wrap_synthesis_html(md, page_date=date(2026, 5, 2))
    # The {tags: ...} literal must always be stripped, even in fallback.
    assert "{tags:" not in out
    # Markdown link syntax must not leak in fallback either.
    assert "](http" not in out
    # The URL should still be reachable as an <a href>.
    assert 'href="https://example.com/x"' in out
