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


# --- per-tag counts on chip bar (V2 .n badge format) ---------------------- #

def test_render_chip_bar_with_counts_shows_count_per_tag():
    """V2 counts live in <span class="n">N</span> badges, not in chip text."""
    counts = {
        "Models": 3, "Agents": 5, "Tooling": 2,
        "Regulation": 0, "Enterprise": 1, "Research": 0,
    }
    bar = cf.render_chip_bar(counts=counts)
    for tag, n in counts.items():
        assert re.search(
            rf'<button[^>]*data-tag="{tag}"[^>]*>.*?<span class="n">{n}</span>',
            bar, re.DOTALL,
        ), f"missing .n badge for {tag}={n}"


def test_render_chip_bar_total_passed_to_all_chip():
    """When the caller passes `total`, the All chip's .n badge shows it.
    Sum-of-counts is misleading when items can carry multiple tags, so the
    caller computes total from item count and passes it explicitly."""
    counts = {"Models": 3, "Agents": 5}
    bar = cf.render_chip_bar(counts=counts, total=7)
    assert re.search(
        r'<button[^>]*data-tag="all"[^>]*>.*?<span class="n">7</span>',
        bar, re.DOTALL,
    )


def test_render_chip_bar_without_counts_unchanged():
    """No-summarize path: no counts → no .n badges (a row of zeros would be
    worse than no badges at all)."""
    bar = cf.render_chip_bar()
    assert 'data-tag="Models"' in bar
    assert 'class="n"' not in bar


def test_render_chip_bar_missing_tag_in_counts_renders_zero():
    """If a tag is omitted from the counts dict, its .n badge shows 0."""
    bar = cf.render_chip_bar(counts={"Models": 2})
    assert re.search(
        r'<button[^>]*data-tag="Models"[^>]*>.*?<span class="n">2</span>',
        bar, re.DOTALL,
    )
    assert re.search(
        r'<button[^>]*data-tag="Agents"[^>]*>.*?<span class="n">0</span>',
        bar, re.DOTALL,
    )


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

    # (a) V2 filter rail present
    assert '<div class="rail">' in out
    assert out.count("data-tag=") >= 7

    # (b) at least one rendered element with data-tags (post-redesign this is
    # the <article> card; pre-redesign it was the <li>).
    assert re.search(r'data-tags="[A-Z][^"]*"', out)

    # (c) V2 takeaways block comes before the Top Story section in the page.
    # V2 spec uses sentence case for the section title.
    assert out.index("Key takeaways") < out.index("Top Story")

    # (d) no leftover {tags: literal anywhere in the output
    assert "{tags:" not in out


def test_no_summarize_path_renders_chips_without_zero_count_badges():
    """The no-summarize ``render_html`` path doesn't tag items, so per-tag
    counts would all be 0. Suppress the .n badges in that case — a rail of
    zero badges is worse than no badges at all.
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
    # Rail chips still present
    assert 'data-tag="Models"' in out
    # No empty .n badges
    assert 'class="n"' not in out


def test_full_pipeline_renders_real_per_tag_counts_on_chips():
    """V2 .n badges reflect real per-tag counts.

    Fixture has: Top story (Regulation, Agents) · Models · Agents+Tooling · Enterprise.
    """
    out = cf.wrap_synthesis_html(FIXTURE_MD, page_date=None)
    # Models: 1, Agents: 2, Tooling: 1, Regulation: 1, Enterprise: 1, Research: 0
    for tag, n in [("Models", 1), ("Agents", 2), ("Tooling", 1),
                    ("Regulation", 1), ("Enterprise", 1), ("Research", 0)]:
        assert re.search(
            rf'<button[^>]*data-tag="{tag}"[^>]*>.*?<span class="n">{n}</span>',
            out, re.DOTALL,
        ), f"wrong/missing count badge for {tag}={n}"
