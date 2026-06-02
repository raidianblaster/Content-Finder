"""Tests for the SYSTEM_PROMPT structure (feature 2)."""
from __future__ import annotations

import content_finder as cf


def test_prompt_requires_key_takeaways_block():
    p = cf.SYSTEM_PROMPT
    assert "Key takeaways" in p
    # Instruction that the takeaways block has 3 bullets and sits at the top
    assert "3" in p  # "3 bullets" or similar
    # Must instruct that takeaways come before any other section
    lower = p.lower()
    assert "key takeaways" in lower
    assert lower.index("key takeaways") < lower.index("top story")


def test_prompt_takeaways_require_bold_headline():
    """Each Key-takeaway bullet must lead with a short bold hook headline so the
    UI can render headline-on-top + supporting-line-below."""
    p = cf.SYSTEM_PROMPT
    kta_block = p.split("Key takeaways")[1].split("Top story")[0].lower()
    assert "bold" in kta_block and "headline" in kta_block, (
        "takeaways spec must instruct a leading bold headline"
    )


def test_prompt_requires_so_what_per_story():
    p = cf.SYSTEM_PROMPT
    assert "So what" in p


def test_prompt_lists_fixed_tag_taxonomy():
    p = cf.SYSTEM_PROMPT
    for tag in ["Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research"]:
        assert tag in p, f"taxonomy missing: {tag}"
    # Must instruct the {tags: ...} suffix syntax
    assert "{tags:" in p


def test_prompt_forbids_preamble_and_closing():
    p = cf.SYSTEM_PROMPT
    assert "No preamble" in p


def test_prompt_requires_link_per_story_bullet():
    """2026-05-23 prod regression: last bullet in 'Worth a deeper read' had no
    link because the prompt didn't explicitly mandate one.  The prompt must now
    contain language that (a) mandates a link for every story bullet and (b)
    calls out that omitting the link is forbidden."""
    p = cf.SYSTEM_PROMPT
    lower = p.lower()
    # Must explicitly state that the link must never be omitted.
    assert "never omit the link" in lower, (
        "prompt must explicitly say 'never omit the link' so the LLM can't "
        "silently drop the source URL for the last bullet"
    )


def test_prompt_forbids_literal_source_as_link_label():
    """2026-05-06 prod regression: the prompt's `[Source](url)` placeholder
    was copied verbatim into every card. The prompt must explicitly forbid
    the literal word "Source" (and similar generic labels) as the link text,
    and give a concrete example of the expected substitution.
    """
    p = cf.SYSTEM_PROMPT
    lower = p.lower()
    # Must explicitly call out that "Source" is NOT the literal label to use.
    # Either by forbidding it or by showing a concrete substitute example.
    assert (
        "not the literal word" in lower
        or "must be the publication" in lower
        or "must be the source name" in lower
    ), "prompt should explicitly forbid using 'Source' as the literal link label"
    # And there must be at least one concrete example link with a real
    # publication name (not the word 'Source').
    import re as _re
    examples = _re.findall(r'\[([^\]]+)\]\(https?://[^)]+\)', p)
    real_publication_examples = [
        e for e in examples
        if e.strip().lower() not in {
            "source", "read more", "read", "link", "article", "here", "more",
        }
    ]
    assert real_publication_examples, (
        "prompt must include at least one concrete `[Publication name](url)` "
        "example so the model has a real pattern to copy"
    )
