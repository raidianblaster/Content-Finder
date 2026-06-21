"""Blank-page guard: synthesis must never erase items that survived the pipeline.

Regression for the 2026-06-21 empty homepage. On a low-diversity day only a
handful of thin items reached synthesis; Claude returned a short "quiet day"
note that carried none of the structured story bullets the parser expects, so
``wrap_synthesis_html`` produced an empty ``<div class="article-list"></div>``
and a "0 items" masthead -- silently dropping items the pipeline had approved.
The render path must fall back to the ranked list whenever synthesis yields no
cards while items exist.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import content_finder as cf

# A thin reply with no headings/bullets -- parses to zero synthesis cards,
# exactly like the 280-token "quiet day" output observed on 2026-06-21.
THIN_REPLY = (
    "It was a quiet day for agentic-AI news. Only a handful of academic "
    "preprints crossed the wire, with no major model or product releases "
    "worth a full brief."
)


def _item(source: str, title: str) -> cf.Item:
    return cf.Item(
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}",
        source=source,
        published=datetime.now(timezone.utc),
        summary="agentic llm research",
    )


def test_thin_synthesis_falls_back_to_ranked_list():
    items = [_item("arXiv cs.AI", f"Paper {i}") for i in range(5)]

    out = cf.render_digest_html(
        THIN_REPLY, items, page_date=date(2026, 6, 21), top_n=25,
    )

    # The page must not be empty when items exist.
    assert '<div class="article-list"></div>' not in out
    # Items the pipeline approved must appear on the page.
    assert "Paper 0" in out
    assert "Paper 4" in out
    # Masthead must reflect the real count, not the synthesis "0 items".
    assert ">0 items<" not in out


def test_good_synthesis_still_uses_synthesis_render():
    md = (
        "## Models & capability releases\n\n"
        "- **A big model ships** with new capabilities. "
        "[Read the article](https://example.com/model)\n"
    )
    items = [_item("arXiv cs.AI", "Paper 0")]

    out = cf.render_digest_html(
        md, items, page_date=date(2026, 6, 21), top_n=25,
    )

    # Synthesis produced cards, so the brief is used (not the ranked fallback).
    assert "A big model ships" in out


def test_thin_synthesis_with_no_items_does_not_crash():
    # Degenerate but possible: nothing survived the pipeline. No fallback
    # source exists, so we still return a valid (empty) synthesis page.
    out = cf.render_digest_html(
        THIN_REPLY, [], page_date=date(2026, 6, 21), top_n=25,
    )
    assert "<!doctype html>" in out
