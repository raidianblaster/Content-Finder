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

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml"


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
