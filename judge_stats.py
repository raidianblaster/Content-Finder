#!/usr/bin/env python3
"""CLI rollup of the judge ledger (docs/review/<date>.judge.json).

Companion to `traces.py`, which rolls up LLM cost/latency. This one rolls up
what the judge actually *said*: which pipeline stage it disputes most, and
which outlets that stage costs you.

`judge.py run <date>` writes one report per day:

    {"date": ..., "judge_prompt_version": ...,
     "suspect_drops": [{"url", "stage", "reason"}],
     "suspect_keeps": [{"url", "reason"}]}

Drops carry the stage that killed the item; keeps don't (they survived to the
final digest), so only drops are bucketed by stage.

Usage:
    python judge_stats.py                              # whole ledger
    python judge_stats.py --days 30                    # last 30 reports
    python judge_stats.py --since 2026-07-01           # on/after a date
    python judge_stats.py --stage dropped_source_cap   # drill into one stage
    python judge_stats.py --dir docs/review --top 15

Read-only: it never writes, and a malformed report is skipped rather than
raised, so this can be pointed at a live ledger safely.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_REVIEW_DIR = Path(__file__).resolve().parent / "docs" / "review"

# Only YYYY-MM-DD.judge.json. This is deliberately strict: it excludes
# `latest.judge.json`, which is a copy of the newest day and would otherwise
# double-count the most recent date.
_REPORT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.judge\.json$")

UNKNOWN = "unknown"


def source_of(url: str | None) -> str:
    """Host for a judged URL, normalised to the outlet ('www.' stripped).

    Returns "unknown" for a missing or unparseable URL -- the ledger is
    LLM-written, so no field is guaranteed.
    """
    if not url or not isinstance(url, str):
        return UNKNOWN
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return UNKNOWN
    if host.startswith("www."):
        host = host[4:]
    return host or UNKNOWN


def load_judge_reports(
    directory: "str | Path | None" = None,
    *,
    since: str | None = None,
    days: int | None = None,
) -> list[dict]:
    """Load judge reports from `directory`, oldest first.

    `since` is an inclusive ISO date lower bound; `days` keeps only the N most
    recent reports (applied after `since`). Malformed JSON is skipped.
    """
    d = Path(directory) if directory is not None else DEFAULT_REVIEW_DIR
    if not d.is_dir():
        return []

    reports: list[tuple[str, dict]] = []
    for path in d.iterdir():
        m = _REPORT_RE.match(path.name)
        if not m:
            continue
        stamp = m.group(1)
        if since and stamp < since:
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue  # truncated or unreadable report must not break the rollup
        if not isinstance(payload, dict):
            continue
        payload.setdefault("date", stamp)
        reports.append((stamp, payload))

    reports.sort(key=lambda pair: pair[0])
    ordered = [payload for _, payload in reports]
    if days is not None and days >= 0:
        ordered = ordered[-days:] if days else []
    return ordered


def _entries(report: dict, key: str) -> list[dict]:
    value = report.get(key) or []
    if not isinstance(value, list):
        return []
    return [e for e in value if isinstance(e, dict)]


def rollup(reports: list[dict]) -> dict:
    """Aggregate loaded reports into counts by stage and by source."""
    by_stage: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_stage_source: dict[str, Counter[str]] = defaultdict(Counter)

    drops = keeps = 0
    for report in reports:
        for entry in _entries(report, "suspect_drops"):
            drops += 1
            stage = entry.get("stage") or UNKNOWN
            source = source_of(entry.get("url"))
            by_stage[stage] += 1
            by_source[source] += 1
            by_stage_source[stage][source] += 1
        keeps += len(_entries(report, "suspect_keeps"))

    days = len(reports)
    dates = [r.get("date") for r in reports if r.get("date")]
    return {
        "days": days,
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "suspect_drops": drops,
        "suspect_keeps": keeps,
        "drops_per_day": round(drops / days, 2) if days else 0.0,
        "keeps_per_day": round(keeps / days, 2) if days else 0.0,
        "by_stage": dict(by_stage),
        "by_source": dict(by_source),
        "by_stage_source": {k: dict(v) for k, v in by_stage_source.items()},
    }


def _ranked(counts: dict[str, int], top: int | None) -> list[tuple[str, int]]:
    """Counts sorted by size desc, then name asc so output is deterministic."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return items[:top] if top else items


def _table(title: str, counts: dict[str, int], days: int, top: int | None,
           *, per_day: bool) -> list[str]:
    rows = _ranked(counts, top)
    if not rows:
        return []
    width = max([len(title)] + [len(name) for name, _ in rows])
    head = f"{title.upper():<{width}}  {'DROPS':>6}"
    if per_day:
        head += f"  {'/DAY':>6}"
    lines = [head, "-" * len(head)]
    for name, count in rows:
        line = f"{name:<{width}}  {count:>6}"
        if per_day:
            rate = round(count / days, 2) if days else 0.0
            line += f"  {rate:>6}"
        lines.append(line)
    return lines


def format_report(data: dict, *, top: int | None = 10,
                  stage: str | None = None) -> str:
    """Render a rollup as plain ASCII text (repo convention: no emojis)."""
    if not data or not data.get("days"):
        return "No judge reports found."

    days = data["days"]
    span = f"{data['first_date']} to {data['last_date']}"
    out = [
        f"JUDGE DISPUTES  ({days} day{'s' if days != 1 else ''}, {span})",
        "",
    ]

    if stage:
        count = data["by_stage"].get(stage, 0)
        rate = round(count / days, 2) if days else 0.0
        out.append(f"Stage filter: {stage}  ({count} drops, {rate}/day)")
        out.append("")
        sources = data["by_stage_source"].get(stage, {})
        block = _table(f"top sources ({stage})", sources, days, top, per_day=False)
        out.extend(block or ["  (no drops recorded at this stage)"])
        return "\n".join(out)

    out.append(
        f"  suspect drops: {data['suspect_drops']:>5}  "
        f"({data['drops_per_day']}/day)"
    )
    out.append(
        f"  suspect keeps: {data['suspect_keeps']:>5}  "
        f"({data['keeps_per_day']}/day)"
    )
    out.append("")
    out.extend(_table("stage", data["by_stage"], days, None, per_day=True))
    out.append("")
    out.extend(_table("top sources (all stages)", data["by_source"], days, top,
                      per_day=False))
    return "\n".join(out)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        description="Summarise the judge ledger (docs/review/*.judge.json)."
    )
    ap.add_argument("--dir", default=None,
                    help="Review directory (default: docs/review).")
    ap.add_argument("--since", default=None,
                    help="Only include reports dated on/after this ISO date.")
    ap.add_argument("--days", type=int, default=None,
                    help="Only the N most recent reports.")
    ap.add_argument("--stage", default=None,
                    help="Drill into one stage, e.g. dropped_source_cap.")
    ap.add_argument("--top", type=int, default=10,
                    help="Max source rows to show (default: 10).")
    ap.add_argument("--json", action="store_true",
                    help="Emit the raw rollup as JSON instead of a table.")
    args = ap.parse_args(argv)

    reports = load_judge_reports(args.dir, since=args.since, days=args.days)
    data = rollup(reports)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(format_report(data, top=args.top, stage=args.stage))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
