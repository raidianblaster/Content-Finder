"""Unit tests for derived masthead fields: issue number, distinct sources, read time.

Per the V2 design handoff, the masthead surfaces:
- "AI Digest · Issue N"      → count of files in docs/archive/
- "10 items · 7 sources"     → distinct count of `Item.source`
- "~6 min read"              → ~250 wpm over total rendered text
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import content_finder as cf


# ---------------------------------------------------------------------------
# count_archived_issues
# ---------------------------------------------------------------------------

def test_count_archived_issues_empty_dir(tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    assert cf.count_archived_issues(archive) == 0


def test_count_archived_issues_counts_only_dated_html(tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    # Three valid issue files
    (archive / "2026-05-24.html").write_text("x")
    (archive / "2026-05-25.html").write_text("x")
    (archive / "2026-05-26.html").write_text("x")
    # Distractors that must not be counted
    (archive / "index.html").write_text("x")
    (archive / "README.md").write_text("x")
    (archive / "2026-05-26.html.bak").write_text("x")
    assert cf.count_archived_issues(archive) == 3


def test_count_archived_issues_missing_dir_returns_zero(tmp_path: Path):
    # If the archive directory does not exist, callers shouldn't crash —
    # rendering should degrade to "Issue 0" rather than blow up.
    assert cf.count_archived_issues(tmp_path / "nope") == 0


# ---------------------------------------------------------------------------
# distinct_sources
# ---------------------------------------------------------------------------

def _mk_item(title: str, source: str) -> cf.Item:
    return cf.Item(
        title=title,
        url=f"https://example.com/{title}",
        source=source,
        published=datetime(2026, 5, 26, tzinfo=timezone.utc),
        summary="x",
    )


def test_distinct_sources_dedupes():
    items = [
        _mk_item("a", "NYT"),
        _mk_item("b", "NYT"),
        _mk_item("c", "Techmeme"),
        _mk_item("d", "Simon Willison"),
    ]
    assert cf.distinct_sources(items) == 3


def test_distinct_sources_empty_list():
    assert cf.distinct_sources([]) == 0


# ---------------------------------------------------------------------------
# estimated_read_minutes
# ---------------------------------------------------------------------------

def test_estimated_read_minutes_basic():
    # 500 total words at 250 wpm → 2 minutes
    items = [_mk_item("t1", "S"), _mk_item("t2", "S")]
    items[0].summary = "word " * 250
    items[1].summary = "word " * 250
    assert cf.estimated_read_minutes(items) == 2


def test_estimated_read_minutes_minimum_one():
    # Very short content rounds up to at least 1 minute
    items = [_mk_item("short", "S")]
    items[0].summary = "tiny"
    assert cf.estimated_read_minutes(items) == 1


def test_estimated_read_minutes_empty_list():
    assert cf.estimated_read_minutes([]) == 1
