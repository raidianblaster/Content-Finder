"""Pin the cron schedule off GitHub Actions' peak minutes.

GH Actions queues scheduled workflows behind paid traffic, and the queue is
heaviest at :00 and :30. We were running at 22:30 UTC and seeing 30–60 min
delays (digest landing ~07:27 HKT instead of the intended ~06:30 HKT).
Moving to an off-peak minute typically drops delay to <15 min.

If you ever feel tempted to "tidy up" the cron back to :30 or :00, this
test exists to remind you why it's wrong.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml"


def test_workflow_is_valid_yaml():
    """GitHub rejects the whole file (0s failure, no digest) if daily.yml is not
    valid YAML. A `run: |` literal block needs every script line indented at
    least as far as the block start; a flush-left line continuation silently
    dedents out of the block and breaks parsing. Guard against that regressing.
    """
    yaml.safe_load(WORKFLOW.read_text())


def _cron_minute() -> int:
    text = WORKFLOW.read_text()
    m = re.search(r'cron:\s*"(\d+)\s+(\d+)\s+\*\s+\*\s+\*"', text)
    assert m, f"could not find cron schedule in {WORKFLOW}"
    return int(m.group(1))


def test_cron_minute_avoids_peak_congestion():
    minute = _cron_minute()
    assert minute not in (0, 30), (
        f"cron minute is {minute}; :00 and :30 are GH Actions peak congestion "
        "windows and queue-delay scheduled jobs by 30–60 min on the free tier."
    )


def test_cron_minute_targets_morning_hkt_delivery():
    """22:00–23:00 UTC = 06:00–07:00 HKT. Anything outside that window means
    the digest stops arriving when the user wakes up."""
    text = WORKFLOW.read_text()
    m = re.search(r'cron:\s*"\d+\s+(\d+)\s+\*\s+\*\s+\*"', text)
    assert m, "missing cron"
    hour_utc = int(m.group(1))
    assert hour_utc == 22, (
        f"cron hour is {hour_utc} UTC; digest target is 06:xx HKT (= 22:xx UTC)."
    )


def test_workflow_commits_dedup_state_alongside_digest():
    """Cross-day dedup is only useful if the state file persists across runs.
    The workflow must include dedup-state.json in its `git add` step."""
    text = WORKFLOW.read_text()
    assert "dedup-state.json" in text, (
        "daily.yml must `git add dedup-state.json` so cross-day dedup state "
        "survives between runs"
    )


def test_dedup_state_not_in_gitignore():
    """If the state file is gitignored, `git add` silently skips it and the
    cross-day dedup state never gets committed."""
    gitignore = WORKFLOW.parent.parent.parent / ".gitignore"
    if not gitignore.exists():
        return
    lines = [ln.strip() for ln in gitignore.read_text().splitlines()]
    assert "dedup-state.json" not in lines, (
        ".gitignore must not exclude dedup-state.json — it has to be committed."
    )


def test_workflow_builds_review_page():
    """Daily cron must build the review page so mobile labelling works without
    a laptop. See issue #11."""
    text = WORKFLOW.read_text()
    assert "review.py build" in text, (
        "daily.yml must invoke `review.py build` so docs/review/<date>.html is "
        "generated and published via Pages each day"
    )


def test_workflow_runs_judge_triage():
    """Daily cron should run Haiku judge so mobile review pages have suspect
    highlights without manual laptop work. See issue #12."""
    text = WORKFLOW.read_text()
    assert "judge.py run" in text, (
        "daily.yml must invoke `judge.py run` so docs/review/<date>.judge.json "
        "is generated and inlined into the review page"
    )


def test_workflow_builds_review_index():
    """A review/index.html browsable list of past review pages must be
    regenerated daily so historical pages stay discoverable."""
    text = WORKFLOW.read_text()
    assert "review.py build-index" in text or "build_index" in text, (
        "daily.yml must invoke `review.py build-index` so the listing of "
        "past review pages is kept current"
    )


def test_workflow_writes_latest_review_alias():
    """`docs/review/latest.html` is the stable bookmark URL — must be
    overwritten by the cron each day so mobile users don't have to type
    today's date into the URL."""
    text = WORKFLOW.read_text()
    assert "review/latest.html" in text, (
        "daily.yml must copy today's review page to `docs/review/latest.html` "
        "so a bookmark of /review/latest.html always shows the newest digest"
    )


def test_workflow_judge_step_tolerates_failure():
    """Judge step is best-effort — API errors must NOT break the digest
    workflow. `continue-on-error: true` is the required guardrail."""
    text = WORKFLOW.read_text()
    # Find the judge step block and assert continue-on-error is set within it.
    judge_block = re.search(
        r"name:\s*[\"']?[^\n]*[Jj]udge[^\n]*[\"']?\n.*?(?=\n\s*-\s+name:|\Z)",
        text, re.DOTALL,
    )
    assert judge_block, "could not locate a judge step in daily.yml"
    assert "continue-on-error: true" in judge_block.group(0), (
        "judge step must set `continue-on-error: true` so an Anthropic API "
        "failure does not break the daily digest"
    )
