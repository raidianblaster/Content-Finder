"""Tests for the judge-ledger rollup (judge_stats.py).

The judge writes one docs/review/<date>.judge.json per run:

    {"date": "...", "judge_prompt_version": "v1",
     "suspect_drops": [{"url": ..., "stage": ..., "reason": ...}],
     "suspect_keeps": [{"url": ..., "reason": ...}]}

`suspect_keeps` entries carry no `stage` -- by definition they survived to the
final digest. Only drops are bucketed by stage.

These are pure-function tests: every fixture is written to tmp_path, so the
suite never depends on the real docs/review/ contents.
"""
from __future__ import annotations

import json

import judge_stats as js


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write(directory, date, drops=(), keeps=(), *, name=None):
    """Write one judge report; `name` overrides the filename stem."""
    payload = {
        "date": date,
        "judge_prompt_version": "v1",
        "suspect_drops": [
            {"url": u, "stage": s, "reason": "because"} for (u, s) in drops
        ],
        "suspect_keeps": [{"url": u, "reason": "because"} for u in keeps],
    }
    p = directory / f"{name or date}.judge.json"
    p.write_text(json.dumps(payload))
    return p


def _basic(directory):
    """Two days of reports with a known stage/source distribution."""
    _write(
        directory, "2026-08-01",
        drops=[
            ("https://arxiv.org/abs/1", "dropped_source_cap"),
            ("https://arxiv.org/abs/2", "dropped_source_cap"),
            ("https://www.anthropic.com/news/x", "dropped_ttl"),
        ],
        keeps=["https://example.com/fluff"],
    )
    _write(
        directory, "2026-08-02",
        drops=[
            ("https://arxiv.org/abs/3", "dropped_source_cap"),
            ("https://simonwillison.net/a", "dropped_keyword"),
        ],
        keeps=[],
    )
    return directory


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_load_reads_all_dated_reports_ascending(tmp_path):
    _basic(tmp_path)
    reports = js.load_judge_reports(tmp_path)
    assert [r["date"] for r in reports] == ["2026-08-01", "2026-08-02"]


def test_load_excludes_the_latest_alias(tmp_path):
    """docs/review/latest.judge.json is a copy of the newest day.

    Counting it would silently double every number for the most recent date,
    which is exactly the day you look at most.
    """
    _basic(tmp_path)
    # latest.judge.json duplicates 2026-08-02
    _write(tmp_path, "2026-08-02",
           drops=[("https://arxiv.org/abs/3", "dropped_source_cap"),
                  ("https://simonwillison.net/a", "dropped_keyword")],
           name="latest")
    reports = js.load_judge_reports(tmp_path)
    assert len(reports) == 2
    assert js.rollup(reports)["suspect_drops"] == 5


def test_load_skips_malformed_json_without_raising(tmp_path):
    """A truncated report must never take the rollup down."""
    _basic(tmp_path)
    (tmp_path / "2026-08-03.judge.json").write_text('{"date": "2026-08-03", "sus')
    reports = js.load_judge_reports(tmp_path)
    assert [r["date"] for r in reports] == ["2026-08-01", "2026-08-02"]


def test_load_ignores_unrelated_files(tmp_path):
    _basic(tmp_path)
    (tmp_path / "2026-08-02.html").write_text("<html></html>")
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "notes.json").write_text("{}")
    assert len(js.load_judge_reports(tmp_path)) == 2


def test_load_since_filters_inclusively(tmp_path):
    _basic(tmp_path)
    reports = js.load_judge_reports(tmp_path, since="2026-08-02")
    assert [r["date"] for r in reports] == ["2026-08-02"]
    # Boundary date is included, not excluded.
    assert len(js.load_judge_reports(tmp_path, since="2026-08-01")) == 2


def test_load_days_keeps_only_the_most_recent_n(tmp_path):
    _basic(tmp_path)
    _write(tmp_path, "2026-08-03", drops=[("https://arxiv.org/abs/9", "final")])
    reports = js.load_judge_reports(tmp_path, days=2)
    assert [r["date"] for r in reports] == ["2026-08-02", "2026-08-03"]


def test_load_missing_directory_returns_empty(tmp_path):
    assert js.load_judge_reports(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# Rollup
# ---------------------------------------------------------------------------

def test_rollup_counts_totals_and_date_span(tmp_path):
    data = js.rollup(js.load_judge_reports(_basic(tmp_path)))
    assert data["days"] == 2
    assert data["first_date"] == "2026-08-01"
    assert data["last_date"] == "2026-08-02"
    assert data["suspect_drops"] == 5
    assert data["suspect_keeps"] == 1


def test_rollup_buckets_drops_by_stage(tmp_path):
    data = js.rollup(js.load_judge_reports(_basic(tmp_path)))
    assert data["by_stage"] == {
        "dropped_source_cap": 3,
        "dropped_ttl": 1,
        "dropped_keyword": 1,
    }


def test_rollup_buckets_drops_by_source_host(tmp_path):
    """Host, not full URL -- the actionable unit is the outlet."""
    data = js.rollup(js.load_judge_reports(_basic(tmp_path)))
    assert data["by_source"]["arxiv.org"] == 3
    # www. is stripped so anthropic.com and www.anthropic.com are one bucket.
    assert data["by_source"]["anthropic.com"] == 1
    assert data["by_source"]["simonwillison.net"] == 1


def test_rollup_cross_tabs_stage_by_source(tmp_path):
    """Answers 'which outlets does a given stage hurt most?'."""
    data = js.rollup(js.load_judge_reports(_basic(tmp_path)))
    assert data["by_stage_source"]["dropped_source_cap"] == {"arxiv.org": 3}
    assert data["by_stage_source"]["dropped_ttl"] == {"anthropic.com": 1}


def test_rollup_reports_drops_per_day(tmp_path):
    data = js.rollup(js.load_judge_reports(_basic(tmp_path)))
    assert data["drops_per_day"] == 2.5


def test_rollup_keeps_are_not_bucketed_by_stage(tmp_path):
    """suspect_keeps have no stage; they must not pollute by_stage."""
    _write(tmp_path, "2026-08-01", drops=[], keeps=["https://a.com/x"])
    data = js.rollup(js.load_judge_reports(tmp_path))
    assert data["suspect_keeps"] == 1
    assert data["by_stage"] == {}


def test_rollup_of_nothing_is_safe(tmp_path):
    data = js.rollup([])
    assert data["days"] == 0
    assert data["suspect_drops"] == 0
    assert data["by_stage"] == {}
    assert data["drops_per_day"] == 0.0
    assert data["first_date"] is None


# ---------------------------------------------------------------------------
# Malformed entries -- the ledger is LLM-written, so assume nothing
# ---------------------------------------------------------------------------

def test_rollup_handles_drop_missing_stage(tmp_path):
    p = tmp_path / "2026-08-01.judge.json"
    p.write_text(json.dumps({
        "date": "2026-08-01",
        "suspect_drops": [{"url": "https://arxiv.org/abs/1", "reason": "r"}],
    }))
    data = js.rollup(js.load_judge_reports(tmp_path))
    assert data["by_stage"] == {"unknown": 1}
    assert data["by_source"] == {"arxiv.org": 1}


def test_rollup_handles_drop_missing_or_unparseable_url(tmp_path):
    p = tmp_path / "2026-08-01.judge.json"
    p.write_text(json.dumps({
        "date": "2026-08-01",
        "suspect_drops": [
            {"stage": "final", "reason": "r"},
            {"url": "not a url", "stage": "final", "reason": "r"},
        ],
    }))
    data = js.rollup(js.load_judge_reports(tmp_path))
    assert data["by_source"] == {"unknown": 2}
    assert data["by_stage"] == {"final": 2}


def test_rollup_handles_absent_drop_and_keep_keys(tmp_path):
    p = tmp_path / "2026-08-01.judge.json"
    p.write_text(json.dumps({"date": "2026-08-01"}))
    data = js.rollup(js.load_judge_reports(tmp_path))
    assert data["days"] == 1
    assert data["suspect_drops"] == 0
    assert data["suspect_keeps"] == 0


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def test_format_report_shows_span_stages_and_sources(tmp_path):
    out = js.format_report(js.rollup(js.load_judge_reports(_basic(tmp_path))))
    assert "2026-08-01" in out and "2026-08-02" in out
    assert "dropped_source_cap" in out
    assert "arxiv.org" in out
    assert "3" in out


def test_format_report_orders_stages_by_count_desc(tmp_path):
    out = js.format_report(js.rollup(js.load_judge_reports(_basic(tmp_path))))
    assert out.index("dropped_source_cap") < out.index("dropped_ttl")


def test_format_report_stage_filter_narrows_sources(tmp_path):
    data = js.rollup(js.load_judge_reports(_basic(tmp_path)))
    out = js.format_report(data, stage="dropped_source_cap")
    assert "arxiv.org" in out
    # anthropic.com only appears under dropped_ttl, so it must be filtered out
    assert "anthropic.com" not in out


def test_format_report_empty_ledger_is_graceful(tmp_path):
    out = js.format_report(js.rollup([]))
    assert "no judge reports" in out.lower()


def test_format_report_has_no_emoji(tmp_path):
    """Repo convention: no emojis in generated output."""
    out = js.format_report(js.rollup(js.load_judge_reports(_basic(tmp_path))))
    assert all(ord(ch) < 0x2190 for ch in out), "non-ASCII glyph in report"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_main_prints_report_and_exits_zero(tmp_path, capsys):
    _basic(tmp_path)
    rc = js.main(["--dir", str(tmp_path)])
    assert rc == 0
    assert "dropped_source_cap" in capsys.readouterr().out


def test_main_on_empty_dir_exits_zero(tmp_path, capsys):
    rc = js.main(["--dir", str(tmp_path)])
    assert rc == 0
    assert "no judge reports" in capsys.readouterr().out.lower()
