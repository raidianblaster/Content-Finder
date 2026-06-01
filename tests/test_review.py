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


# --------------------------------------------------------------------------- #
# 8. Judge data inlined when .judge.json is present
# --------------------------------------------------------------------------- #

def test_build_inlines_judge_data_when_present(log_root):
    import review
    judge_data = {
        "date": SAMPLE_LOG["date"],
        "judge_prompt_version": "v1",
        "suspect_drops": [
            {"url": "https://ex.com/finance", "stage": "dropped_keyword",
             "reason": "relevant despite keyword miss"},
        ],
        "suspect_keeps": [
            {"url": "https://ex.com/agent-sdk", "reason": "vendor hype"},
        ],
    }
    review_dir = log_root / "docs" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / f"{SAMPLE_LOG['date']}.judge.json").write_text(json.dumps(judge_data))

    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    assert "const JUDGE" in html
    assert '"suspect_drops"' in html


# --------------------------------------------------------------------------- #
# 9. Suspect cards get CSS class emitted server-side
# --------------------------------------------------------------------------- #

def test_judge_suspect_drop_card_gets_css_class(log_root):
    import review
    judge_data = {
        "date": SAMPLE_LOG["date"],
        "judge_prompt_version": "v1",
        "suspect_drops": [
            {"url": "https://ex.com/finance", "stage": "dropped_keyword",
             "reason": "relevant"},
        ],
        "suspect_keeps": [],
    }
    review_dir = log_root / "docs" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / f"{SAMPLE_LOG['date']}.judge.json").write_text(json.dumps(judge_data))

    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    # The finance card div should carry the suspect-drop class
    finance_idx = html.find("ex.com/finance")
    assert finance_idx > 0
    window = html[max(0, finance_idx - 200):finance_idx + 200]
    assert "judge-suspect" in window


# --------------------------------------------------------------------------- #
# 10. When no judge file, JUDGE constant is null
# --------------------------------------------------------------------------- #

def test_build_judge_null_when_no_judge_file(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert "const JUDGE = null" in html


# --------------------------------------------------------------------------- #
# 11. Suspect-first layout — top section appears before "Final"
# --------------------------------------------------------------------------- #

def _write_judge(log_root, judge_dict):
    review_dir = log_root / "docs" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / f"{SAMPLE_LOG['date']}.judge.json").write_text(json.dumps(judge_dict))


def test_needs_review_section_appears_before_final(log_root):
    import review
    _write_judge(log_root, {
        "date": SAMPLE_LOG["date"], "judge_prompt_version": "v1",
        "suspect_drops": [{"url": "https://ex.com/finance", "stage": "dropped_keyword", "reason": "relevant"}],
        "suspect_keeps": [{"url": "https://ex.com/agent-sdk", "reason": "hype"}],
    })
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    needs_idx = html.find('id="needs-review"')
    final_idx = html.find("Final — kept")
    assert needs_idx > 0, "expected a section with id='needs-review'"
    assert final_idx > 0
    assert needs_idx < final_idx, (
        "needs-review section must come before the Final section heading"
    )


def test_suspect_cards_carry_from_stage_chip(log_root):
    import review
    _write_judge(log_root, {
        "date": SAMPLE_LOG["date"], "judge_prompt_version": "v1",
        "suspect_drops": [{"url": "https://ex.com/finance", "stage": "dropped_keyword", "reason": "relevant"}],
        "suspect_keeps": [],
    })
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()

    # Inside the needs-review section, the finance card should declare its origin.
    needs_idx = html.find('id="needs-review"')
    next_section_idx = html.find("<section", needs_idx + 1)
    block = html[needs_idx:next_section_idx]
    assert "was:" in block, "suspect cards should show a 'was: <stage>' chip"
    assert "ex.com/finance" in block


def test_suspect_cards_show_judge_reason(log_root):
    """Reason must appear in the visible card UI, not only inside the
    embedded JUDGE JS constant."""
    import review
    _write_judge(log_root, {
        "date": SAMPLE_LOG["date"], "judge_prompt_version": "v1",
        "suspect_drops": [{
            "url": "https://ex.com/finance", "stage": "dropped_keyword",
            "reason": "this is a UNIQUE_REASON_STRING_42",
        }],
        "suspect_keeps": [],
    })
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    # Reason must appear in the needs-review section block (i.e. before the
    # <script> tag where const JUDGE is defined).
    script_idx = html.find("<script")
    body_section = html[:script_idx]
    assert "UNIQUE_REASON_STRING_42" in body_section, (
        "judge reason should be rendered in the card UI, not only embedded "
        "in the const JUDGE script"
    )


def test_suspect_items_removed_from_original_stage_section(log_root):
    """When a card is in needs-review, it should NOT also appear in its stage section."""
    import review
    _write_judge(log_root, {
        "date": SAMPLE_LOG["date"], "judge_prompt_version": "v1",
        "suspect_drops": [{"url": "https://ex.com/finance", "stage": "dropped_keyword", "reason": "x"}],
        "suspect_keeps": [],
    })
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    # The finance URL should appear exactly once as a card data-url attribute.
    card_occurrences = html.count('data-url="https://ex.com/finance"')
    # 3 buttons + 1 card div + 1 note input = 5 per card. If it's duplicated we'd see 10.
    assert card_occurrences <= 5, (
        f"finance URL appears {card_occurrences} times; suspect items should be "
        "moved to needs-review, not duplicated into stage sections."
    )


def test_no_needs_review_section_when_judge_null(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert 'id="needs-review"' not in html


# --------------------------------------------------------------------------- #
# 12. build_index — listing all review pages
# --------------------------------------------------------------------------- #

def test_build_index_lists_review_pages(tmp_path):
    import review
    logs_dir = tmp_path / "docs" / "logs"
    logs_dir.mkdir(parents=True)
    for d in ("2026-05-17", "2026-05-18", "2026-05-19"):
        log = {**SAMPLE_LOG, "date": d}
        (logs_dir / f"{d}.json").write_text(json.dumps(log))
    review.build_all(root=tmp_path)

    out = review.build_index(root=tmp_path)
    assert out == tmp_path / "docs" / "review" / "index.html"
    html = out.read_text()
    for d in ("2026-05-17", "2026-05-18", "2026-05-19"):
        assert d in html, f"index should reference review page for {d}"


def test_build_index_excludes_aliases(tmp_path):
    """index.html must not list itself or latest.html as review entries."""
    import review
    logs_dir = tmp_path / "docs" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "2026-05-19.json").write_text(json.dumps({**SAMPLE_LOG, "date": "2026-05-19"}))
    review.build_all(root=tmp_path)
    # Pretend a previous run dropped these aliases in:
    review_dir = tmp_path / "docs" / "review"
    (review_dir / "latest.html").write_text("dummy")
    out = review.build_index(root=tmp_path)
    html = out.read_text()
    # No <a href="latest.html"> or <a href="index.html"> in the listing.
    assert 'href="latest.html"' not in html
    assert 'href="index.html"' not in html


def test_build_index_orders_newest_first(tmp_path):
    import review
    logs_dir = tmp_path / "docs" / "logs"
    logs_dir.mkdir(parents=True)
    for d in ("2026-05-17", "2026-05-18", "2026-05-19"):
        (logs_dir / f"{d}.json").write_text(json.dumps({**SAMPLE_LOG, "date": d}))
    review.build_all(root=tmp_path)
    out = review.build_index(root=tmp_path)
    html = out.read_text()
    i19 = html.find("2026-05-19")
    i18 = html.find("2026-05-18")
    i17 = html.find("2026-05-17")
    assert 0 < i19 < i18 < i17, "index should list newest date first"


# --------------------------------------------------------------------------- #
# 13. Auto-save: settings panel + status pill + GitHub Contents API wiring
# --------------------------------------------------------------------------- #
#
# Labels live only in localStorage today; the user has to manually export and
# commit a feedback JSONL per labelling session. These tests pin down the
# auto-save surface: a settings gear opens a panel for the PAT, a status pill
# in the footer reflects save state, and the embedded JS targets the
# `Content-Finder` repo's Contents API for `feedback/<date>.jsonl`.

def test_settings_gear_button_rendered(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert re.search(r'id="settings-toggle"', html), (
        "expected a settings gear button with id='settings-toggle' in the footer"
    )


def test_save_status_pill_rendered(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert re.search(r'id="save-status"', html), (
        "expected a status pill <span id='save-status'> in the footer"
    )


def test_settings_panel_has_pat_input(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert re.search(r'id="settings-panel"', html), (
        "expected a hidden settings panel with id='settings-panel'"
    )
    assert re.search(r'id="pat-input"', html), (
        "settings panel must contain a PAT input field with id='pat-input'"
    )
    assert re.search(r'id="pat-test"', html), (
        "settings panel must contain a 'Test connection' button with id='pat-test'"
    )
    assert re.search(r'id="pat-save"', html), (
        "settings panel must contain a 'Save' button with id='pat-save'"
    )


def test_repo_constants_embedded_in_js(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert 'const REPO_OWNER = "raidianblaster"' in html, (
        "expected REPO_OWNER constant in embedded JS"
    )
    assert 'const REPO_NAME = "Content-Finder"' in html, (
        "expected REPO_NAME constant in embedded JS"
    )
    assert 'const BRANCH = "main"' in html, (
        "expected BRANCH constant in embedded JS"
    )


def test_github_contents_api_url_in_js(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    # The Contents API URL is built per-request from REPO_OWNER/REPO_NAME/date;
    # assert the host + path prefix appear in JS. Exact composition is tested
    # by the manual end-to-end run, not here.
    assert "api.github.com/repos/" in html, (
        "expected GitHub Contents API host in embedded JS"
    )
    # Path is composed at runtime from pieces; assert both fragments are present
    # in the JS source, even if not adjacent.
    assert "/contents/" in html, "expected /contents/ API path fragment in JS"
    assert "feedback/" in html, "expected feedback/ path fragment in JS"


def test_auto_save_debounce_wired(log_root):
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    # Function name we'll use for the debounced commit trigger.
    assert "scheduleSave" in html, (
        "expected scheduleSave() debounce function in embedded JS"
    )
    # The commit function itself.
    assert "commitJsonl" in html, (
        "expected commitJsonl() function in embedded JS"
    )


def test_existing_download_and_copy_buttons_preserved(log_root):
    """Regression guard: Download/Copy JSONL fallback path must survive."""
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert re.search(r'id="download-jsonl"', html)
    assert re.search(r'id="copy-jsonl"', html)


def test_save_caches_put_response_sha(log_root):
    """Consecutive saves must not trip GitHub's 409 'does not match' on a stale
    sha. After a successful PUT, the new blob sha is in the response body
    (`content.sha`); the next save must reuse that instead of re-reading via a
    GET that can lag (replica) or be HTTP-cached (browser). Regression for the
    two-cycle 409 bug.
    """
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    # A module-level cache for the last-written sha.
    assert "lastKnownSha" in html, (
        "expected a cached sha variable so save #2 skips the stale GET"
    )
    # The cache is populated from the PUT response body's blob sha.
    assert "content.sha" in html, (
        "expected the PUT response's content.sha to be captured for reuse"
    )


def test_fetch_sha_bypasses_http_cache(log_root):
    """The sha GET must be uncached, or the 409 fallback re-fetch returns the
    same browser-cached stale sha and the retry fails identically.
    """
    import review
    review.build(SAMPLE_LOG["date"], root=log_root)
    html = (log_root / "docs" / "review" / f"{SAMPLE_LOG['date']}.html").read_text()
    assert "no-store" in html, (
        "expected cache: 'no-store' on the sha fetch so the retry can recover"
    )
