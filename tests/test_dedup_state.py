"""Cross-day deduplication via dedup-state.json.

Tests are organized by the plan's Group letters (A, B, C, D, E, F, G, K, L).
Group A here covers the canonical_url() refactor extracted from dedupe().
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import content_finder as cf


# --------------------------------------------------------------------------- #
# Group A — canonical_url()
# --------------------------------------------------------------------------- #

def test_A1_plain_url_unchanged():
    assert cf.canonical_url("https://example.com/post") == "https://example.com/post"


def test_A2_query_string_stripped():
    assert (
        cf.canonical_url("https://example.com/post?utm_source=twitter")
        == "https://example.com/post"
    )


def test_A3_trailing_slash_stripped():
    assert cf.canonical_url("https://example.com/post/") == "https://example.com/post"


def test_A4_query_and_trailing_slash_both_stripped():
    assert (
        cf.canonical_url("https://example.com/post/?utm_source=x")
        == "https://example.com/post"
    )


def test_A5_idempotent():
    samples = [
        "https://example.com/post",
        "https://example.com/post/",
        "https://example.com/post?x=1",
        "https://example.com/post/?x=1",
        "https://news.ycombinator.com/item?id=42",
    ]
    for u in samples:
        once = cf.canonical_url(u)
        twice = cf.canonical_url(once)
        assert once == twice, f"not idempotent: {u!r} -> {once!r} -> {twice!r}"


def test_A6_hn_discussion_url_preserves_item_id():
    # HN discussion URLs use the query string as their stable item identity.
    # Preserve `id` there while still stripping tracker params elsewhere.
    a = cf.canonical_url("https://news.ycombinator.com/item?id=1")
    b = cf.canonical_url("https://news.ycombinator.com/item?id=2")
    assert a == "https://news.ycombinator.com/item?id=1"
    assert b == "https://news.ycombinator.com/item?id=2"


def test_A6b_hn_discussion_url_strips_non_id_params():
    assert (
        cf.canonical_url("https://news.ycombinator.com/item?id=42&utm_source=x")
        == "https://news.ycombinator.com/item?id=42"
    )


def _item(url: str, title: str, score: float = 5.0) -> cf.Item:
    it = cf.Item(
        title=title,
        url=url,
        source="Test",
        published=datetime.now(timezone.utc),
        summary="agentic",
    )
    it.score = score
    return it


# --------------------------------------------------------------------------- #
# Group B — load/save dedup-state.json
# --------------------------------------------------------------------------- #

def test_B1_load_missing_file_returns_empty(tmp_path: Path):
    state = cf.load_dedup_state(tmp_path / "does-not-exist.json")
    assert state == {}


def test_B2_load_valid_v1_file(tmp_path: Path):
    p = tmp_path / "dedup-state.json"
    p.write_text(json.dumps({
        "version": 1,
        "entries": {
            "https://example.com/a": "2026-05-01",
            "https://example.com/b": "2026-05-02",
        },
    }))
    state = cf.load_dedup_state(p)
    assert state == {
        "https://example.com/a": "2026-05-01",
        "https://example.com/b": "2026-05-02",
    }


def test_B3_load_malformed_json_returns_empty(tmp_path: Path, capsys):
    p = tmp_path / "dedup-state.json"
    p.write_text("not valid json {{{")
    state = cf.load_dedup_state(p)
    assert state == {}
    err = capsys.readouterr().err
    assert "dedup-state" in err.lower() or "warn" in err.lower()


def test_B4_load_unknown_version_returns_empty(tmp_path: Path):
    p = tmp_path / "dedup-state.json"
    p.write_text(json.dumps({"version": 99, "entries": {"x": "2026-01-01"}}))
    assert cf.load_dedup_state(p) == {}


def test_B5_load_missing_entries_key_returns_empty(tmp_path: Path):
    p = tmp_path / "dedup-state.json"
    p.write_text(json.dumps({"version": 1}))
    assert cf.load_dedup_state(p) == {}


def test_B6_save_then_load_roundtrip(tmp_path: Path):
    p = tmp_path / "dedup-state.json"
    state = {
        "https://example.com/a": "2026-05-01",
        "https://example.com/b": "2026-05-02",
    }
    cf.save_dedup_state(p, state)
    assert cf.load_dedup_state(p) == state


def test_B7_save_is_atomic(tmp_path: Path):
    """save_dedup_state writes to a temp file and renames, so an existing
    file is never left half-written. We verify the file is always valid JSON
    by writing twice and checking the result parses.
    """
    p = tmp_path / "dedup-state.json"
    cf.save_dedup_state(p, {"https://a": "2026-05-01"})
    cf.save_dedup_state(p, {"https://b": "2026-05-02"})
    # No leftover temp files
    leftovers = [f for f in tmp_path.iterdir() if f.name != "dedup-state.json"]
    assert leftovers == []
    # File parses cleanly
    data = json.loads(p.read_text())
    assert data["version"] == 1
    assert data["entries"] == {"https://b": "2026-05-02"}


def test_B8_save_creates_parent_dir(tmp_path: Path):
    p = tmp_path / "nested" / "dir" / "dedup-state.json"
    cf.save_dedup_state(p, {"https://x": "2026-05-01"})
    assert p.exists()


def test_B9_unicode_urls_roundtrip(tmp_path: Path):
    p = tmp_path / "dedup-state.json"
    state = {"https://例え.com/记事": "2026-05-01"}
    cf.save_dedup_state(p, state)
    assert cf.load_dedup_state(p) == state


# --------------------------------------------------------------------------- #
# Group C — annotate_first_seen() and filter_unseen()
# --------------------------------------------------------------------------- #

TODAY = date(2026, 5, 7)


def _ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def test_C0_annotate_sets_first_seen_for_state_match():
    items = [_item("https://example.com/a", "Alpha"), _item("https://example.com/b", "Beta")]
    state = {"https://example.com/a": "2026-05-01"}
    cf.annotate_first_seen(items, state)
    assert items[0].first_seen == date(2026, 5, 1)
    assert items[1].first_seen is None


def test_C0b_annotate_canonicalizes_url():
    """Item URL with tracker matches state's bare URL via canonical_url."""
    items = [_item("https://example.com/a?utm_source=tw", "Alpha")]
    state = {"https://example.com/a": "2026-05-01"}
    cf.annotate_first_seen(items, state)
    assert items[0].first_seen == date(2026, 5, 1)


def test_C0c_annotate_skips_corrupt_dates():
    items = [_item("https://example.com/a", "Alpha")]
    state = {"https://example.com/a": "not-a-date"}
    cf.annotate_first_seen(items, state)
    assert items[0].first_seen is None


def _annotated(url: str, days_ago: "int | None") -> cf.Item:
    it = _item(url, f"item-{days_ago}")
    if days_ago is not None:
        it.first_seen = TODAY - timedelta(days=days_ago)
    return it


def test_C1_empty_state_passes_all_items():
    items = [_item(f"https://example.com/{i}", f"x{i}") for i in range(3)]
    out = cf.filter_unseen(items, today=TODAY, ttl_days=5)
    assert out == items


def test_C2_seen_1_day_ago_ttl_5_filtered():
    items = [_annotated("https://example.com/a", 1)]
    assert cf.filter_unseen(items, today=TODAY, ttl_days=5) == []


def test_C3_seen_4_days_ago_ttl_5_filtered():
    items = [_annotated("https://example.com/a", 4)]
    assert cf.filter_unseen(items, today=TODAY, ttl_days=5) == []


def test_C4_seen_exactly_ttl_days_ago_filtered_inclusive():
    items = [_annotated("https://example.com/a", 5)]
    assert cf.filter_unseen(items, today=TODAY, ttl_days=5) == []


def test_C5_seen_ttl_plus_one_kept():
    items = [_annotated("https://example.com/a", 6)]
    assert cf.filter_unseen(items, today=TODAY, ttl_days=5) == items


def test_C8_unannotated_item_kept():
    items = [_annotated("https://example.com/a", None)]
    assert cf.filter_unseen(items, today=TODAY, ttl_days=5) == items


def test_C9_ttl_zero_disables_filter():
    items = [_annotated("https://example.com/a", 1)]
    assert cf.filter_unseen(items, today=TODAY, ttl_days=0) == items


def test_C10_partial_filter_preserves_order():
    items = [
        _annotated("https://example.com/keep1", None),
        _annotated("https://example.com/drop", 1),
        _annotated("https://example.com/keep2", 10),  # TTL expired
        _annotated("https://example.com/keep3", None),
    ]
    out = cf.filter_unseen(items, today=TODAY, ttl_days=5)
    urls = [it.url for it in out]
    assert urls == [
        "https://example.com/keep1",
        "https://example.com/keep2",
        "https://example.com/keep3",
    ]


# --------------------------------------------------------------------------- #
# Group D — update_seen_state(): add today's URLs, prune old entries
# --------------------------------------------------------------------------- #

def test_D1_empty_state_adds_today_for_each_item():
    items = [
        _item("https://example.com/a", "Alpha"),
        _item("https://example.com/b", "Beta"),
    ]
    out = cf.update_seen_state({}, items, today=TODAY, max_age_days=30)
    assert out == {
        "https://example.com/a": TODAY.isoformat(),
        "https://example.com/b": TODAY.isoformat(),
    }


def test_D2_existing_url_keeps_earlier_first_seen():
    state = {"https://example.com/a": _ago(3)}
    items = [_item("https://example.com/a", "Alpha")]
    out = cf.update_seen_state(state, items, today=TODAY, max_age_days=30)
    assert out["https://example.com/a"] == _ago(3)


def test_D3_canonicalized_url_does_not_create_duplicate_entry():
    state = {"https://example.com/a": _ago(2)}
    items = [_item("https://example.com/a?utm_source=x", "Alpha")]
    out = cf.update_seen_state(state, items, today=TODAY, max_age_days=30)
    assert out == {"https://example.com/a": _ago(2)}


def test_D4_pruning_drops_older_than_max_age():
    state = {
        "https://example.com/old": _ago(31),
        "https://example.com/keep": _ago(10),
    }
    out = cf.update_seen_state(state, [], today=TODAY, max_age_days=30)
    assert "https://example.com/old" not in out
    assert "https://example.com/keep" in out


def test_D5_pruning_boundary_inclusive_keeps_max_age_day():
    """Entry exactly max_age_days old is kept (inclusive boundary)."""
    state = {"https://example.com/edge": _ago(30)}
    out = cf.update_seen_state(state, [], today=TODAY, max_age_days=30)
    assert "https://example.com/edge" in out


def test_D6_pruning_with_new_items_combines_correctly():
    state = {
        "https://example.com/old": _ago(40),
        "https://example.com/recent": _ago(20),
    }
    items = [_item("https://example.com/new", "New")]
    out = cf.update_seen_state(state, items, today=TODAY, max_age_days=30)
    assert "https://example.com/old" not in out
    assert "https://example.com/recent" in out
    assert out["https://example.com/new"] == TODAY.isoformat()


def test_D7_empty_items_still_prunes_no_crash():
    state = {"https://example.com/old": _ago(99)}
    out = cf.update_seen_state(state, [], today=TODAY, max_age_days=30)
    assert out == {}


def test_D8_corrupt_date_in_state_is_pruned():
    """Defensive: a malformed date is treated as ancient and dropped."""
    state = {"https://example.com/bad": "not-a-date"}
    out = cf.update_seen_state(state, [], today=TODAY, max_age_days=30)
    assert "https://example.com/bad" not in out


# --------------------------------------------------------------------------- #
# Group K — top-up fallback to MIN_RENDERED_ITEMS
# --------------------------------------------------------------------------- #

def _scored(url: str, score: float, days_ago: "int | None" = None) -> cf.Item:
    it = _item(url, url.rsplit("/", 1)[-1], score=score)
    if days_ago is not None:
        it.first_seen = TODAY - timedelta(days=days_ago)
    return it


def test_K1_above_threshold_no_topup():
    fresh = [_scored(f"https://x/{i}", 10.0 - i) for i in range(12)]
    out = cf.topup_to_minimum(fresh=fresh, filtered_out=[], minimum=10)
    assert out == fresh


def test_K2_at_threshold_no_topup_boundary():
    fresh = [_scored(f"https://x/{i}", 10.0 - i) for i in range(10)]
    out = cf.topup_to_minimum(fresh=fresh, filtered_out=[], minimum=10)
    assert out == fresh


def test_K3_below_by_one_takes_highest_filtered():
    fresh = [_scored(f"https://x/{i}", 10.0 - i) for i in range(9)]
    filtered = [
        _scored("https://y/low", 1.0, days_ago=1),
        _scored("https://y/high", 7.5, days_ago=1),
        _scored("https://y/mid", 4.0, days_ago=2),
    ]
    out = cf.topup_to_minimum(fresh=fresh, filtered_out=filtered, minimum=10)
    assert len(out) == 10
    # The highest-scored filtered item is the topup
    assert any(it.url == "https://y/high" for it in out)
    assert not any(it.url == "https://y/low" for it in out)


def test_K4_zero_fresh_topup_to_minimum():
    filtered = [_scored(f"https://y/{i}", 30 - i, days_ago=1) for i in range(30)]
    out = cf.topup_to_minimum(fresh=[], filtered_out=filtered, minimum=10)
    assert len(out) == 10
    # All topup items still carry their resurfacing flag
    assert all(it.first_seen is not None for it in out)


def test_K6_topup_picks_by_score():
    fresh = []
    filtered = [
        _scored("https://y/a", 5.0, days_ago=1),
        _scored("https://y/b", 9.0, days_ago=4),  # higher score, older
        _scored("https://y/c", 3.0, days_ago=1),
    ]
    out = cf.topup_to_minimum(fresh=fresh, filtered_out=filtered, minimum=2)
    urls = {it.url for it in out}
    assert urls == {"https://y/a", "https://y/b"}  # top-2 by score


def test_K7_empty_pools_returns_empty_no_crash():
    out = cf.topup_to_minimum(fresh=[], filtered_out=[], minimum=10)
    assert out == []


# --------------------------------------------------------------------------- #
# Group L — resurfacing badge in rendered HTML
# --------------------------------------------------------------------------- #

def test_L3_card_without_first_seen_has_no_badge():
    it = _item("https://example.com/a", "Alpha")
    it.score = 5.0
    html = cf._render_ranked_card(it, item_id=1)
    assert "resurfacing" not in html
    assert "↻" not in html


def test_L1_card_with_first_seen_renders_badge():
    it = _item("https://example.com/a", "Alpha")
    it.score = 5.0
    it.first_seen = date(2026, 5, 1)
    html = cf._render_ranked_card(it, item_id=1)
    assert "resurfacing" in html
    assert "↻" in html
    assert 'title="First seen 2026-05-01"' in html


def test_L6_badge_lives_in_meta_row_not_body():
    """V2: resurfacing badge belongs in the always-visible .story-head meta row,
    never inside the collapsible .story-body. Keeps the recurrence signal
    legible without forcing an expand."""
    it = _item("https://example.com/a", "Alpha")
    it.score = 5.0
    it.first_seen = date(2026, 5, 1)
    html_str = cf._render_ranked_card(it, item_id=1)
    head_match = re.search(
        r'<div class="story-head"[^>]*>(.*?)</div>\s*<div class="story-body"',
        html_str, re.DOTALL,
    )
    assert head_match, "no story-head in card"
    head_segment = head_match.group(1)
    body_match = re.search(
        r'<div class="story-body"[^>]*>(.*?)</article>', html_str, re.DOTALL,
    )
    assert body_match, "no story-body in card"
    body_segment = body_match.group(1)
    assert "resurfacing" in head_segment, "badge missing from story-head"
    assert "resurfacing" not in body_segment, "badge leaked into expandable body"


def test_L5_badge_includes_correct_iso_date_in_title_attr():
    it = _item("https://example.com/a", "Alpha")
    it.score = 5.0
    it.first_seen = date(2025, 12, 31)
    html_str = cf._render_ranked_card(it, item_id=1)
    assert 'title="First seen 2025-12-31"' in html_str


def test_L8_chip_counts_unaffected_by_badge():
    """The badge must not introduce a tag-like element that gets counted
    by _count_tags_in_body."""
    it = _item("https://example.com/a", "Alpha")
    it.score = 5.0
    it.first_seen = date(2026, 5, 1)
    card_html = cf._render_ranked_card(it, item_id=1)
    counts = cf._count_tags_in_body(card_html)
    assert all(v == 0 for v in counts.values())


# --------------------------------------------------------------------------- #
# Group E — HKT timezone correctness
# --------------------------------------------------------------------------- #

def test_E1_today_hkt_at_cron_time_returns_next_day():
    """22:07 UTC on 2026-05-07 → 06:07 HKT on 2026-05-08."""
    cron_utc = datetime(2026, 5, 7, 22, 7, 0, tzinfo=timezone.utc)
    assert cf.today_hkt(cron_utc) == date(2026, 5, 8)


def test_E2_ttl_arithmetic_uses_hkt_today():
    """Item first_seen = HKT 2026-05-07; today_hkt = 2026-05-08; TTL=5
    → 1 day old → filtered."""
    cron_utc = datetime(2026, 5, 7, 22, 7, 0, tzinfo=timezone.utc)
    today = cf.today_hkt(cron_utc)
    assert today == date(2026, 5, 8)
    items = [_annotated("https://example.com/a", None)]
    items[0].first_seen = date(2026, 5, 7)
    out = cf.filter_unseen(items, today=today, ttl_days=5)
    assert out == []


def test_E3_state_written_today_hkt_not_utc():
    """update_seen_state stamps with whatever 'today' caller passes,
    which main() takes from today_hkt(), not date.today()."""
    cron_utc = datetime(2026, 5, 7, 22, 7, 0, tzinfo=timezone.utc)
    today = cf.today_hkt(cron_utc)
    items = [_item("https://example.com/a", "Alpha")]
    out = cf.update_seen_state({}, items, today=today, max_age_days=30)
    assert out == {"https://example.com/a": "2026-05-08"}


# --------------------------------------------------------------------------- #
# Group F — gather() integration with dedup_state
# --------------------------------------------------------------------------- #

def _bypass_fetchers(monkeypatch, items_to_return):
    """Make gather() think the fetchers returned `items_to_return`."""
    monkeypatch.setattr(cf, "RSS_SOURCES", [])
    monkeypatch.setattr(cf, "HN_QUERIES", [])

    # Patch the keyword filter so test items always pass through; their
    # summaries don't necessarily contain real keywords.
    monkeypatch.setattr(cf, "keyword_score", lambda text: 1)

    # Inject items via a dummy ThreadPoolExecutor would be heavier than
    # patching gather() to splice them in. Cleanest: patch
    # ThreadPoolExecutor's `as_completed` flow by replacing fetchers.
    # Here we just stash the items and re-route gather() to use them.

    # Instead of running the executor, reach into gather()'s pipeline by
    # patching the fetcher functions to no-ops and pre-loading items.
    # gather() builds items from fetchers — easier route: monkeypatch a
    # post-fetch hook by replacing dedupe to return our items unchanged
    # AFTER intercepting via score_item. Simplest: patch fetch_rss and
    # fetch_hn to no-ops and rebuild via a custom helper.
    # The cleanest change is to call gather() with empty source lists and
    # then exercise the filter/topup/cap logic directly via the helpers
    # — which we already test in groups C/D/K. Group F here verifies the
    # wiring through gather(), so we patch dedupe to return our items.

    def fake_dedupe(_items):
        # Items already deduped by caller; return as-is, sorted by score.
        return sorted(items_to_return, key=lambda x: x.score, reverse=True)

    monkeypatch.setattr(cf, "dedupe", fake_dedupe)


def test_F1_no_state_passes_all_items(monkeypatch):
    items = [_scored(f"https://x/{i}", 10.0 - i) for i in range(5)]
    _bypass_fetchers(monkeypatch, items)
    out, _ = cf.gather(days=2, hn_min_points=50, max_per_source=10, dedup_state=None)
    assert len(out) == 5
    assert all(it.first_seen is None for it in out)


def test_F2_state_filters_seen_items(monkeypatch):
    items = [_scored(f"https://x/{i}", 10.0 - i) for i in range(15)]
    _bypass_fetchers(monkeypatch, items)
    state = {
        "https://x/0": (TODAY - timedelta(days=1)).isoformat(),
        "https://x/1": (TODAY - timedelta(days=1)).isoformat(),
    }
    out, _ = cf.gather(
        days=2, hn_min_points=50, max_per_source=10,
        dedup_state=state, today=TODAY, ttl_days=5,
        minimum_items=10,
    )
    urls = {it.url for it in out}
    assert "https://x/0" not in urls
    assert "https://x/1" not in urls


def test_F3_topup_kicks_in_when_pool_below_minimum(monkeypatch):
    """Only 5 fresh items remain after filter, but minimum=10 → top up
    with the highest-scored seen items, badged as resurfacing."""
    items = [_scored(f"https://x/{i}", 20.0 - i) for i in range(15)]
    _bypass_fetchers(monkeypatch, items)
    # Mark 10 of them as recently seen
    state = {
        f"https://x/{i}": (TODAY - timedelta(days=1)).isoformat()
        for i in range(10)
    }
    out, _ = cf.gather(
        days=2, hn_min_points=50, max_per_source=10,
        dedup_state=state, today=TODAY, ttl_days=5,
        minimum_items=10,
    )
    # 5 fresh + 5 topup = 10
    assert len(out) == 10
    resurfacing = [it for it in out if it.first_seen is not None]
    assert len(resurfacing) == 5
    # Topup picks highest-scored seen items: x/0 (score 20) ranks higher
    # than x/9 (score 11), so x/0 should be in the topup.
    topup_urls = {it.url for it in resurfacing}
    assert "https://x/0" in topup_urls


def test_F4_filter_runs_before_source_cap(monkeypatch):
    """Source A has 5 items; 3 are seen-and-filtered. Cap=3 should let
    the remaining 2 fresh items through (not be capped to 3 of 5
    pre-filter)."""
    items = []
    for i in range(5):
        it = _item(f"https://a/{i}", f"a{i}", score=10 - i)
        it.source = "Source A"
        items.append(it)
    for i in range(3):
        it = _item(f"https://b/{i}", f"b{i}", score=5 - i)
        it.source = "Source B"
        items.append(it)
    _bypass_fetchers(monkeypatch, items)
    state = {f"https://a/{i}": (TODAY - timedelta(days=1)).isoformat()
             for i in range(3)}
    out, _ = cf.gather(
        days=2, hn_min_points=50, max_per_source=3,
        dedup_state=state, today=TODAY, ttl_days=5,
        minimum_items=0,  # disable topup so we see the post-cap effect
    )
    a_count = sum(1 for it in out if it.source == "Source A")
    assert a_count == 2  # 5 fetched - 3 filtered = 2 fresh, all under cap


# --------------------------------------------------------------------------- #
# Group G — main() integration: state lifecycle around render failures
# --------------------------------------------------------------------------- #

def test_G6_render_failure_does_not_update_state(monkeypatch, tmp_path):
    """If synthesize_with_claude raises, the dedup-state file must remain
    untouched — an item must be visible to the user before it can be banned.
    Without this guarantee, a transient API failure would silently ban every
    fetched URL for the next 5 days.
    """
    state_path = tmp_path / "dedup-state.json"
    initial_state = {
        "https://example.com/seen-yesterday": (TODAY - timedelta(days=1)).isoformat(),
    }
    cf.save_dedup_state(state_path, initial_state)
    initial_bytes = state_path.read_bytes()
    initial_mtime = state_path.stat().st_mtime_ns

    items = [_scored(f"https://fresh/{i}", 20.0 - i) for i in range(15)]
    _bypass_fetchers(monkeypatch, items)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated synthesis failure")

    monkeypatch.setattr(cf, "synthesize_with_claude", boom)
    monkeypatch.setattr(sys, "argv", [
        "content_finder.py",
        "--days", "2",
        "--top", "25",
        "--format", "html",
        "--out", str(tmp_path / "out.html"),
        "--dedup-state-path", str(state_path),
        "--max-per-source", "10",
    ])

    with pytest.raises(RuntimeError, match="simulated synthesis failure"):
        cf.main()

    assert state_path.read_bytes() == initial_bytes, (
        "dedup-state.json was modified despite render failure — "
        "items would be banned without ever being visible"
    )
    assert state_path.stat().st_mtime_ns == initial_mtime, (
        "dedup-state.json was rewritten (even with identical content) — "
        "the save path ran when it should not have"
    )


def test_G6b_successful_render_does_update_state(monkeypatch, tmp_path):
    """Sibling regression: confirm that without the failure, the state IS
    written. Otherwise G6 could pass trivially because the save path is
    never reachable in this monkeypatched setup."""
    state_path = tmp_path / "dedup-state.json"
    items = [_scored(f"https://fresh/{i}", 20.0 - i) for i in range(15)]
    _bypass_fetchers(monkeypatch, items)
    monkeypatch.setattr(cf, "today_hkt", lambda now=None: TODAY)

    monkeypatch.setattr(sys, "argv", [
        "content_finder.py",
        "--days", "2",
        "--top", "25",
        "--no-summarize",  # skip synthesis, render plain HTML
        "--format", "html",
        "--out", str(tmp_path / "out.html"),
        "--dedup-state-path", str(state_path),
        "--max-per-source", "10",
    ])

    rc = cf.main()
    assert rc == 0
    assert state_path.exists()
    saved = cf.load_dedup_state(state_path)
    # All synthetic items share source "Test"; --max-per-source 10 caps the
    # render to 10. State should reflect the rendered set.
    assert len(saved) == 10
    assert all(d == TODAY.isoformat() for d in saved.values())


def test_A7_dedupe_url_collapse_behavior_unchanged_after_refactor():
    """Regression: URL canonicalization in dedupe() must be unchanged.

    Three URL variants of the same article (bare, trailing slash, tracker)
    should collapse to one entry. Highest score wins.
    """
    items = [
        _item("https://example.com/a", "Alpha one", score=10),
        _item("https://example.com/a/", "Beta two", score=8),
        _item("https://example.com/a?utm_source=tw", "Gamma three", score=9),
        _item("https://example.com/b", "Delta four", score=7),
    ]
    out = cf.dedupe(items)
    urls = [it.url for it in out]
    # The bare URL (highest score in the canonical-collapsed group) wins.
    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_A8_dedupe_keeps_distinct_hn_discussion_urls():
    items = [
        _item("https://news.ycombinator.com/item?id=1", "HN one", score=10),
        _item("https://news.ycombinator.com/item?id=2", "HN two", score=9),
    ]
    out = cf.dedupe(items)
    assert [it.url for it in out] == [
        "https://news.ycombinator.com/item?id=1",
        "https://news.ycombinator.com/item?id=2",
    ]
