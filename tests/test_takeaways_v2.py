"""V2 takeaways grid tests.

The V2 redesign replaces the old collapsible <section class="takeaways"> +
takeaways-toggle button with a static 3-column card grid:

  <section class="block" id="takeaways">
    <div class="sec-head">
      <h2 class="sec-title">Key takeaways</h2>
      <span class="sec-meta">03 · The shortlist</span>
    </div>
    <div class="takes">
      <article class="take">
        <div class="take-num">01</div>
        <div class="take-body">…body text…</div>
        <div class="take-foot">
          <a class="take-link" href="#story-N" data-item-url="…">Label →</a>
        </div>
      </article>
      …
    </div>
  </section>
"""
from __future__ import annotations

import re
from datetime import date

import content_finder as cf


FIXTURE_MD = """## Key takeaways
- One: enterprises are being asked to ship agent guardrails. [Five Eyes guidance](https://example.com/five-eyes)
- Two: model launches keep accelerating, with mid-tier the new battleground. [Mistral Medium](https://mistral.ai)
- Three: regulation is now arriving from joint multi-country bodies.

## Top story
- **Five Eyes guidance on agentic AI** — Joint guidance warns over-privileged agents are already inside critical infrastructure. **So what:** least-privilege architecture is moving from best practice to compliance. [Five Eyes](https://example.com/five-eyes) {tags: Regulation, Agents}

## Models & capability releases
- **Mistral Medium 3.5 lands** — New mid-tier model with remote-agent support. **So what:** raises pricing pressure on the Sonnet/Haiku tier. [Mistral](https://mistral.ai) {tags: Models}
"""


# ---------------------------------------------------------------------------
# Section wrapper + heading
# ---------------------------------------------------------------------------

def test_takeaways_section_uses_v2_block_with_anchor():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # V2 section uses <section class="block" id="takeaways"> so the topnav
    # "Takeaways" link (href="#takeaways") jumps here.
    assert '<section class="block" id="takeaways">' in out


def test_takeaways_sec_head_shows_title_and_count_meta():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    head_m = re.search(r'<section class="block" id="takeaways">\s*<div class="sec-head">(.*?)</div>', out, re.DOTALL)
    assert head_m, "missing .sec-head"
    head = head_m.group(1)
    assert '<h2 class="sec-title">Key takeaways</h2>' in head
    # The mono sec-meta shows the count ("03 · The shortlist" or similar)
    assert 'class="sec-meta"' in head
    assert "03" in head


# ---------------------------------------------------------------------------
# Takes grid + per-card markup
# ---------------------------------------------------------------------------

def test_takeaways_grid_renders_three_take_cards():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    grid_m = re.search(r'<div class="takes">(.*?)</div>\s*</section>', out, re.DOTALL)
    assert grid_m, "missing .takes grid"
    cards = re.findall(r'<article class="take">(.*?)</article>', grid_m.group(1), re.DOTALL)
    assert len(cards) == 3


def test_takeaways_cards_have_mono_numbers_01_02_03():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    nums = re.findall(r'<div class="take-num">([^<]+)</div>', out)
    # 3 takeaways → 01, 02, 03 with zero padding
    assert nums == ["01", "02", "03"]


def test_takeaways_cards_have_body_with_text():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    bodies = re.findall(r'<div class="take-body">(.*?)</div>', out, re.DOTALL)
    assert len(bodies) == 3
    assert "enterprises are being asked" in bodies[0]
    assert "model launches keep accelerating" in bodies[1]
    assert "regulation is now arriving" in bodies[2]


# ---------------------------------------------------------------------------
# Jump links — V2 spec wants real <a> anchors with the article URL
# ---------------------------------------------------------------------------

def test_takeaway_links_render_as_take_link_anchors():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # Per V2: <a class="take-link" href="..." data-item-url="...">label</a>
    assert re.search(
        r'<a class="take-link"[^>]*href="https://example\.com/five-eyes"[^>]*>',
        out,
    )
    assert re.search(
        r'<a class="take-link"[^>]*href="https://mistral\.ai"[^>]*>',
        out,
    )


def test_takeaway_links_keep_data_item_url_hook():
    """data-item-url preserved so navigateToItem can intercept clicks and
    expand the matching story card in-page (with browser-default fallback)."""
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    assert 'data-item-url="https://example.com/five-eyes"' in out


def test_takeaway_link_label_includes_arrow():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    # The V2 take-link spec ends each label with an arrow → for affordance
    assert "→" in out


# ---------------------------------------------------------------------------
# Old collapsible markup is fully gone
# ---------------------------------------------------------------------------

def test_legacy_takeaways_toggle_markup_is_removed():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=date(2026, 5, 26))
    assert "takeaways-toggle" not in out
    assert "takeaways-body" not in out
    assert "takeaways-chevron" not in out
    # The legacy <section class="takeaways"> outer wrapper is replaced by
    # <section class="block" id="takeaways">
    assert 'class="takeaways"' not in out
