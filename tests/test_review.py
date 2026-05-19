"""Tests for the review-harness HTML generator.

`review.build(date, root)` reads `<root>/docs/logs/<date>.json` and writes
`<root>/docs/review/<date>.html` — a labelable view of every filtering
decision for that day. Verdicts are persisted via localStorage and exported
as JSONL.
"""
from __future__ import annotations

import json
import re

import pytest


SAMPLE_LOG = {
    "date": "2026-05-17",
    "prompt_version": "v1",
    "pipeline": {
        "fetched": 5,
        "after_keyword_filter": 4,
        "after_dedupe": 4,
        "after_ttl_filter": 3,
        "after_source_cap": 2,
    },
    "dropped_keyword": [
        {"title": "Quarterly earnings rise 3%", "url": "https://ex.com/finance",
         "source": "Techmeme", "score": 0.0, "age_days": 0.5},
    ],
    "dropped_dedupe": [
        {"title": "Old story rerun", "url": "https://ex.com/dup",
         "source": "Hacker News", "score": 4.2, "age_days": 1.1},
    ],
    "dropped_ttl": [
        {"title": "Yesterday's MCP write-up", "url": "https://ex.com/mcp-yesterday",
         "source": "Simon Willison", "score": 6.8, "age_days": 1.3,
         "first_seen": "2026-05-16"},
    ],
    "dropped_source_cap": [
        {"title": "Fourth MindStudio post today",
         "url": "https://ex.com/mindstudio-overflow",
         "source": "MindStudio", "score": 4.5, "age_days": 0.8},
    ],
    "final": [
        {"title": "New Claude agent SDK release", "url": "https://ex.com/agent-sdk",
         "source": "Anthropic", "score": 9.1, "age_days": 0.4},
        {"title": "MCP adoption analysis", "url": "https://ex.com/mcp-analysis",
         "source": "Simon Willison", "score": 8.3, "age_days": 0.6},
    ],
}


@pytest.fixture
def log_root(tmp_path):
    """Write SAMPLE_LOG into <tmp>/docs/logs/<date>.json and return tmp_path."""
    logs_dir = tmp_path / "docs" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / f"{SAMPLE_LOG['date']}.json").write_text(json.dumps(SAMPLE_LOG))
    return tmp_path


# --------------------------------------------------------------------------- #
# 1. build() reads the log and writes a non-empty HTML file
# --------------------------------------------------------------------------- #

def test_build_reads_log_and_writes_html(log_root):
    import review
    out_path = review.build(SAMPLE_LOG["date"], root=log_root)
    expected = log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html"
    assert out_path == expected
    assert expected.exists()
    html = expected.read_text()
    assert len(html) > 500
    assert "<html" in html


# --------------------------------------------------------------------------- #
# 2. Page groups items by stage in the expected order
# --------------------------------------------------------------------------- #

def test_html_groups_items_by_stage(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    sections = [
        ("Final", "agent-sdk"),
        ("Source", "mindstudio-overflow"),    # "Dropped: source-cap"
        ("TTL", "mcp-yesterday"),
        ("Dedupe", "dup"),
        ("Keyword", "finance"),
    ]
    for heading_substr, url_substr in sections:
        assert heading_substr in html, f"missing section heading containing {heading_substr!r}"
        assert url_substr in html, f"missing item URL substring {url_substr!r}"

    # Order: final (kept) first, raw keyword drops last.
    final_pos = html.find("agent-sdk")
    cap_pos = html.find("mindstudio-overflow")
    ttl_pos = html.find("mcp-yesterday")
    dedupe_pos = html.find("ex.com/dup")
    keyword_pos = html.find("ex.com/finance")
    positions = [final_pos, cap_pos, ttl_pos, dedupe_pos, keyword_pos]
    assert all(p > 0 for p in positions)
    assert positions == sorted(positions), (
        f"expected final < source-cap < ttl < dedupe < keyword order, got {positions}"
    )


# --------------------------------------------------------------------------- #
# 3. Each item card has three verdict buttons with data-verdict/data-url
# --------------------------------------------------------------------------- #

def test_each_item_has_three_verdict_buttons(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    # For the SDK release in final, three buttons should appear in its card.
    sdk_url = "https://ex.com/agent-sdk"
    # All three verdicts present somewhere in the page
    for verdict in ("keep", "drop", "unsure"):
        assert f'data-verdict="{verdict}"' in html, f"missing data-verdict={verdict!r}"

    # The card for the SDK URL contains all three verdict buttons.
    # Find the card block by anchoring on its URL, then look for verdict buttons
    # within ~2KB of the anchor.
    idx = html.find(sdk_url)
    assert idx > 0
    window = html[idx:idx + 2000]
    for verdict in ("keep", "drop", "unsure"):
        assert f'data-verdict="{verdict}"' in window, (
            f"card for {sdk_url} missing data-verdict={verdict!r}"
        )
    # data-url attribute on at least one button in the card matches the item URL
    assert f'data-url="{sdk_url}"' in window


# --------------------------------------------------------------------------- #
# 4. localStorage key encodes both date and url
# --------------------------------------------------------------------------- #

def test_localstorage_key_includes_date_and_url(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    # The JS builds a key as `${date}::${url}` (or equivalent template).
    assert "::" in html, "expected '::' separator in localStorage key template"
    # The page date must be present as a JS constant.
    assert SAMPLE_LOG["date"] in html


# --------------------------------------------------------------------------- #
# 5. Download JSONL button + serialiser fields
# --------------------------------------------------------------------------- #

def test_download_jsonl_button_and_fields_present(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    assert re.search(r'id="download-jsonl"', html), "expected download-jsonl button id"
    assert re.search(r'id="copy-jsonl"', html), "expected copy-jsonl button id"

    # Every required JSONL field must appear in the JS that builds the lines.
    for field in ("date", "url", "title", "source", "stage", "score",
                  "age_days", "verdict", "note", "labelled_at"):
        assert field in html, f"JSONL serialiser missing field {field!r}"

    # Filename hint for the user-facing save.
    assert "feedback/" in html
    assert f"{SAMPLE_LOG['date']}.jsonl" in html


# --------------------------------------------------------------------------- #
# 6. build_all walks the logs directory
# --------------------------------------------------------------------------- #

def test_build_all_writes_page_per_log(tmp_path):
    import review
    logs_dir = tmp_path / "docs" / "logs"
    logs_dir.mkdir(parents=True)
    for d in ("2026-05-17", "2026-05-18", "2026-05-19"):
        log = {**SAMPLE_LOG, "date": d}
        (logs_dir / f"{d}.json").write_text(json.dumps(log))

    written = review.build_all(root=tmp_path)
    assert len(written) == 3
    review_dir = tmp_path / "docs" / "review"
    for d in ("2026-05-17", "2026-05-18", "2026-05-19"):
        assert (review_dir / f"{d}.html").exists()


# --------------------------------------------------------------------------- #
# 7. Missing log → helpful FileNotFoundError
# --------------------------------------------------------------------------- #

def test_missing_log_raises(tmp_path):
    import review
    (tmp_path / "docs" / "logs").mkdir(parents=True)
    with pytest.raises(FileNotFoundError) as exc:
        review.build("2099-01-01", root=tmp_path)
    assert "2099-01-01" in str(exc.value)
