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


# --- Bug 8: stray ** in titles is scrubbed, never rendered literally ------ #

def test_synthesis_card_strips_unmatched_bold_marker_from_title():
    """Unclosed **bold leaks `**` into title text; the renderer must scrub it.

    Reproduces the item-12 case in the live 2026-05-06 digest, where a
    Simon Willison newsletter bullet rendered as ``**Simon Willison …`` in
    the title text.
    """
    md = """## Top story

- **Real bullet** — Body sentence. **So what:** Implication. [Source](https://x.example) {tags: Models}

- **Truncated headline that lost its closer — Body sentence. {tags: Tooling}
"""
    out = cf.wrap_synthesis_html(md, page_date=date(2026, 5, 6))
    titles = re.findall(
        r'<span class="item-title-text">(.*?)</span>',
        out, re.DOTALL,
    )
    assert titles, "no titles rendered at all"
    for title in titles:
        assert "**" not in title, f"raw `**` leaked into title: {title!r}"


def test_build_card_html_strips_asterisks_from_title_directly():
    """Unit-level guarantee: _build_card_html scrubs `**` regardless of caller."""
    out = cf._build_card_html(
        item_id=1,
        data_tags="Models",
        title="**Simon Willison newsletter: Opus 4",
        snippet="Body text.",
        so_what="Implication.",
        url="https://example.com/x",
        source_name="Simon Willison",
    )
    assert "**" not in out, "raw `**` leaked from _build_card_html title"
    assert "Simon Willison newsletter: Opus 4" in out


# --- Bug 9: cards with no body, no so-what, no url AND no source are skipped — #

def test_empty_synthesis_card_is_skipped_entirely():
    """A bullet that produces no snippet, so-what, url, or source is render-noise."""
    md = """## Top story

- **Good bullet** — Real body. **So what:** Real implication. [Source](https://x.example) {tags: Models}
"""
    # Build a deliberately-empty card directly to confirm the skip rule.
    empty = cf._build_card_html(
        item_id=99,
        data_tags="",
        title="Title with no body",
        snippet="",
        so_what="",
        url="",
        source_name="",
    )
    assert empty == "", f"empty card should render to '', got: {empty!r}"

    # And a normal card still renders.
    out = cf.wrap_synthesis_html(md, page_date=date(2026, 5, 6))
    articles = re.findall(r'<article class="item"[^>]*>', out)
    assert len(articles) == 1


def test_card_with_only_source_or_url_still_renders():
    """A card with a usable source link is still meaningful — don't over-skip."""
    out = cf._build_card_html(
        item_id=1, data_tags="Models", title="Title",
        snippet="", so_what="",
        url="https://example.com/x", source_name="Example",
    )
    assert out, "card with url+source got skipped"
    assert 'href="https://example.com/x"' in out


def test_synthesis_html_escapes_untrusted_card_text():
    """Feed/LLM text is untrusted; rendered cards must not preserve raw HTML."""
    md = """## Top story

- **<img src=x onerror=alert(1)>** — body <script>alert(2)</script>. **So what:** <img src=x onerror=alert(3)> [Source](https://x.example) {tags: Models}
"""
    out = cf.wrap_synthesis_html(md, page_date=date(2026, 5, 16))
    assert "<img src=x onerror=alert(1)>" not in out
    assert "<img src=x onerror=alert(3)>" not in out
    assert "<script>alert(2)</script>" not in out
    assert "&lt;img src=x onerror=alert(1)&gt;" in out
    assert "&lt;script&gt;alert(2)&lt;/script&gt;" in out
    assert "&lt;img src=x onerror=alert(3)&gt;" in out


def test_synthesis_card_drops_non_http_source_links():
    """Only http(s) source URLs should become clickable article links."""
    out = cf._build_card_html(
        item_id=1,
        data_tags="Models",
        title="Title",
        snippet="Body",
        so_what="Implication",
        url="javascript:alert(1)",
        source_name="Source",
    )
    assert "javascript:" not in out
    assert 'class="read-article"' not in out
    assert 'class="source"' in out


# --- Bug 10: generic LLM link labels get a useful source, not literal "Source" — #
#
# 2026-05-06 prod regression: every card on the live page rendered with the
# literal source name "Source" because Claude copied the prompt placeholder
# `[Source](url)` verbatim. Cover the case so the fallback can't silently
# break again. Pair with the prompt fix in SYSTEM_PROMPT.

GENERIC_LABEL_FIXTURE = """## Top story

- **Stratechery on AI earnings** — Body sentence about earnings divergence. **So what:** Strategic implication. [Source](https://stratechery.com/2026/google-earnings-meta-earnings/) {tags: Enterprise}

- **arXiv paper on agent benchmarks** — Body about benchmarks. **So what:** Implication. [Read more](https://arxiv.org/abs/2605.00334) {tags: Research}

- **Cloudflare on agents** — Body. **So what:** Implication. [Link](https://blog.cloudflare.com/agents-stripe-projects/) {tags: Tooling}

- **Anthropic news** — Body. **So what:** Implication. [Article](https://www.anthropic.com/news/some-update) {tags: Models}
"""


def test_generic_link_label_falls_back_to_useful_source_name():
    """If the LLM emits `[Source]`, `[Read more]`, etc., the renderer must
    derive a real source name from the URL — never display the literal
    placeholder word."""
    out = cf.wrap_synthesis_html(GENERIC_LABEL_FIXTURE, page_date=date(2026, 5, 6))
    articles = re.findall(
        r'<article class="item"[^>]*>(.*?)</article>', out, re.DOTALL,
    )
    assert len(articles) == 4

    sources_in_meta = []
    for art in articles:
        m = re.search(r'<span class="source">([^<]+)</span>', art)
        sources_in_meta.append(m.group(1) if m else None)

    # Literal placeholder words must never reach the rendered .source span.
    for src in sources_in_meta:
        assert src, "card missing .source meta entirely"
        assert src.strip().lower() not in {
            "source", "read more", "read", "link", "article", "here", "more",
        }, f"generic placeholder leaked into source: {src!r}"

    # And the derived names should be recognisable for these well-known domains.
    assert sources_in_meta[0] == "Stratechery"
    assert sources_in_meta[1] == "arXiv 2605.00334"
    # Cloudflare blog isn't in RSS_SOURCES — domain fallback is acceptable.
    assert "cloudflare" in sources_in_meta[2].lower()
    assert sources_in_meta[3] == "Anthropic News"


def test_real_source_names_are_preserved_unchanged():
    """The fallback must NOT clobber a perfectly-good source name the LLM
    already provided. Regression guard for over-eager replacement."""
    md = """## Top story

- **Headline** — Body. **So what:** Implication. [Stratechery](https://stratechery.com/2026/x/) {tags: Enterprise}
"""
    out = cf.wrap_synthesis_html(md, page_date=date(2026, 5, 6))
    m = re.search(r'<span class="source">([^<]+)</span>', out)
    assert m and m.group(1) == "Stratechery"


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
