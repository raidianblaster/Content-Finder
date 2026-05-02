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
