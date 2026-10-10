"""Entities must be escaped exactly once on the synthesis page.

Regression: text and URLs lifted out of the markdown-rendered HTML were still
entity-encoded ("M&amp;A") and then escaped a second time by the renderers,
so readers saw a literal "M&amp;A" and query-string links broke
("?x=1&amp;amp;y=2").
"""
from __future__ import annotations

import re
from datetime import date

import content_finder as cf


FIXTURE = """## Key takeaways

- **Agentic M&A signals urgency** — AT&T is doubling R&D spend. [Deal & terms](https://example.com/deal?x=1&y=2)

## Models & capability releases

- **Who&When Pro benchmark lands** — Body about R&D budgets. **So what:** M&A matters here. [Johnson & Johnson](https://example.com/deal?x=1&y=2) {tags: Models}
"""


def _render() -> str:
    return cf.wrap_synthesis_html(FIXTURE, page_date=date(2026, 10, 10))


def test_no_double_escaped_entities_anywhere():
    assert "&amp;amp;" not in _render()


def test_takeaway_headline_and_body_escape_ampersand_once():
    out = _render()
    head = re.search(r'<div class="take-head">(.*?)</div>', out, re.DOTALL)
    body = re.search(r'<div class="take-body">(.*?)</div>', out, re.DOTALL)
    assert head and head.group(1) == "Agentic M&amp;A signals urgency"
    assert body and body.group(1) == "AT&amp;T is doubling R&amp;D spend"


def test_takeaway_link_label_and_href_escape_ampersand_once():
    out = _render()
    link = re.search(r'<a class="take-link"[^>]*>.*?</a>', out, re.DOTALL)
    assert link
    assert 'href="https://example.com/deal?x=1&amp;y=2"' in link.group(0)
    assert 'data-item-url="https://example.com/deal?x=1&amp;y=2"' in link.group(0)
    assert "Deal &amp; terms" in link.group(0)


def test_story_card_href_and_source_escape_ampersand_once():
    out = _render()
    card = re.search(r'<article class="story".*?</article>', out, re.DOTALL)
    assert card
    assert 'href="https://example.com/deal?x=1&amp;y=2"' in card.group(0)
    assert '<span class="src">Johnson &amp; Johnson</span>' in card.group(0)
    assert '<span class="src-full">Johnson &amp; Johnson</span>' in card.group(0)


def test_takeaway_text_stays_inert_after_entity_decoding():
    """Decoding entities must not let encoded markup through as live HTML."""
    md = (
        "## Key takeaways\n\n"
        "- **Hook &lt;script&gt;alert(1)&lt;/script&gt;** — Body &lt;img src=x&gt; text. "
        "[Label &lt;b&gt;](https://example.com/a)\n"
    )
    out = cf.wrap_synthesis_html(md, page_date=date(2026, 10, 10))
    takes = re.search(r'<section class="block" id="takeaways">.*?</section>', out, re.DOTALL)
    assert takes
    assert "<script>" not in takes.group(0)
    assert "<img" not in takes.group(0)
    assert "&lt;script&gt;" in takes.group(0)
