"""Tests for per-item tags + chip filter bar (feature 4, option b)."""
from __future__ import annotations

import re

import content_finder as cf


# --- post-processor: strip {tags: …}, attach data-tags to <li>/<p> --------- #

def test_strip_tags_returns_plain_li_and_tag_list():
    src = "<li>Headline — body. {tags: Models, Tooling}</li>"
    out, tags = cf.transform_tag_element(src)
    assert out == '<li data-tags="Models Tooling">Headline — body.</li>'
    assert tags == {"Models", "Tooling"}


def test_strip_tags_handles_missing_tags_gracefully():
    src = "<li>Headline — no tags here</li>"
    out, tags = cf.transform_tag_element(src)
    assert out == '<li data-tags="">Headline — no tags here</li>'
    assert tags == set()


def test_strip_tags_normalises_whitespace_and_case():
    src = "<li>Body. {tags:  models ,  tooling}</li>"
    out, tags = cf.transform_tag_element(src)
    assert 'data-tags="Models Tooling"' in out
    assert tags == {"Models", "Tooling"}


# --- chip bar -------------------------------------------------------------- #

def test_render_chip_bar_emits_one_chip_per_taxonomy_tag():
    bar = cf.render_chip_bar()
    # Expect 1 'All' chip + 6 taxonomy chips
    chip_attrs = re.findall(r'data-tag="([^"]+)"', bar)
    assert chip_attrs[0] == "all"
    assert set(chip_attrs[1:]) == {
        "Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research",
    }
    assert len(chip_attrs) == 7


def test_chip_bar_includes_inline_filter_script():
    out = cf.wrap_synthesis_html(
        "## Key takeaways\n- one\n- two\n- three\n", page_date=None
    )
    assert "<script>" in out
    # script should reference the data-tag attribute and toggle visibility
    assert "data-tag" in out
    assert "data-tags" in out


def test_filter_keeps_untagged_items_visible():
    """Untagged <li> (Key takeaways) shouldn't be hidden when filtering by tag."""
    out = cf.wrap_synthesis_html(
        "## Key takeaways\n- one\n- two\n- three\n", page_date=None
    )
    # The script must short-circuit on empty tag lists so synthesis bullets
    # stay pinned across every filter, not just 'All'.
    assert "tags.length === 0" in out


# --- per-tag counts on chip bar (QoL feature 1) --------------------------- #

def test_render_chip_bar_with_counts_shows_count_per_tag():
    counts = {
        "Models": 3, "Agents": 5, "Tooling": 2,
        "Regulation": 0, "Enterprise": 1, "Research": 0,
    }
    bar = cf.render_chip_bar(counts=counts)
    assert ">Models (3)<" in bar
    assert ">Agents (5)<" in bar
    assert ">Tooling (2)<" in bar
    assert ">Regulation (0)<" in bar
    assert ">Enterprise (1)<" in bar
    assert ">Research (0)<" in bar


def test_render_chip_bar_with_counts_keeps_all_chip_plain():
    """Total is in the topbar already; 'All (N)' would be redundant + multi-tag items make sum-of-counts misleading."""
    counts = {"Models": 3, "Agents": 5}
    bar = cf.render_chip_bar(counts=counts)
    assert ">All<" in bar
    assert ">All (" not in bar


def test_render_chip_bar_without_counts_unchanged():
    """Backward compat: existing callers that don't pass counts get plain chips."""
    bar = cf.render_chip_bar()
    assert ">Models<" in bar
    assert "(0)" not in bar
    assert "(3)" not in bar


def test_render_chip_bar_missing_tag_in_counts_renders_zero():
    """If a tag is omitted from the counts dict, treat it as 0."""
    bar = cf.render_chip_bar(counts={"Models": 2})
    assert ">Models (2)<" in bar
    assert ">Agents (0)<" in bar
    assert ">Research (0)<" in bar


# --- end-to-end pipeline --------------------------------------------------- #

FIXTURE_MD = """## Key takeaways
- One: enterprises are being asked to ship agent guardrails.
- Two: model launches keep accelerating, with mid-tier the new battleground.
- Three: regulation is now arriving from joint multi-country bodies.

## Top story
- **Five Eyes guidance on agentic AI** — Joint guidance warns over-privileged agents are already inside critical infra. **So what:** least-privilege architecture is moving from best practice to compliance. {tags: Regulation, Agents}

## Models & capability releases
- **Mistral Medium 3.5 lands** — New mid-tier model with remote agent support. **So what:** raises pricing pressure on the Sonnet/Haiku tier. [Mistral](https://mistral.ai) {tags: Models}

## Agentic engineering & tooling
- **Codex CLI 0.128.0 adds /goal** — OpenAI's coding agent gains a Ralph-style goal loop. **So what:** agent harnesses are converging on similar primitives. {tags: Agents, Tooling}

## Enterprise, regulation & governance
- **GitHub buckles under AI load** — Pragmatic Engineer breaks down the recent GitHub outage. **So what:** vendor concentration risk is now visible. {tags: Enterprise}
"""


def test_full_synthesis_pipeline_with_fixture():
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=None)

    # (a) chip bar present
    assert 'class="chips"' in out
    assert out.count("data-tag=") >= 7

    # (b) at least one rendered element with data-tags (post-redesign this is
    # the <article> card; pre-redesign it was the <li>).
    assert re.search(r'data-tags="[A-Z][^"]*"', out)

    # (c) Key Takeaways block comes before the Top Story section in the page
    # (design relabels sections to title-case display labels).
    assert out.index("Key Takeaways") < out.index("Top Story")

    # (d) no leftover {tags: literal anywhere in the output
    assert "{tags:" not in out


def test_no_summarize_path_renders_chips_without_zero_counts():
    """The no-summarize ``render_html`` path doesn't tag items, so per-tag
    counts would all be ``(0)``. Suppress counts in that case — a chip bar
    full of ``(0)`` is worse than no counts at all.
    """
    from datetime import datetime, timezone

    items = [
        cf.Item(
            title="Example item",
            url="https://example.com/x",
            source="Example",
            published=datetime.now(timezone.utc),
            summary="Body text.",
            score=10.0,
        ),
    ]
    out = cf.render_html(items, top_n=5)
    assert ">Models<" in out
    assert ">Models (0)<" not in out
    assert "(0)" not in out


def test_full_pipeline_renders_real_per_tag_counts_on_chips():
    """Counts on chips must reflect what actually rendered.

    Fixture has: Top story (Regulation, Agents) · Models · Agents+Tooling · Enterprise.
    """
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=None)
    # Models: 1 (Mistral). Agents: 2 (Five Eyes + Codex). Tooling: 1 (Codex).
    # Regulation: 1 (Five Eyes). Enterprise: 1 (GitHub). Research: 0.
    assert ">Models (1)<" in out
    assert ">Agents (2)<" in out
    assert ">Tooling (1)<" in out
    assert ">Regulation (1)<" in out
    assert ">Enterprise (1)<" in out
    assert ">Research (0)<" in out
