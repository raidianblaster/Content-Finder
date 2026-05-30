#!/usr/bin/env python3
"""Haiku triage of per-run filter logs.

Reads `<root>/docs/logs/<date>.json`, sends a curated subset of filtering
decisions to Claude Haiku, and writes `<root>/docs/review/<date>.judge.json`.
That file is read by `review.py build` and inlined into the review HTML so
suspect cards are highlighted at load time — no runtime fetch needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

JUDGE_PROMPT_VERSION = "v1"

# Keyword drops below this score are too noisy to send to Haiku.
_KEYWORD_SCORE_THRESHOLD = 3.0
# Hard cap on how many keyword drops we include (take highest-scoring first).
_MAX_KEYWORD_DROPS = 20

JUDGE_SYSTEM = """You review filtering decisions made by an AI news pipeline for an AI Product Manager in a regulated corporate environment. The pipeline filters content in stages: keyword filter → dedupe → TTL (cross-day) → source cap → final.

You receive a JSON array of items. Each has: url, title, source, score, age_days, stage (where it was dropped, or "final").

Identify up to the requested number of HIGH-SIGNAL mistakes only:
- suspect_drop: a dropped item that likely deserved to be kept — e.g. substantive AI/ML/agents content from trusted sources (Anthropic, Simon Willison, Latent Space, Hugging Face, ArXiv) that was cut despite clear relevance
- suspect_keep: a final item that probably shouldn't have made it — e.g. vendor marketing, earnings reports, unrelated tech, or low-substance hype

Respond with ONLY valid JSON, no commentary:
{"suspect_drops": [{"url": "...", "stage": "...", "reason": "one concise sentence"}], "suspect_keeps": [{"url": "...", "reason": "one concise sentence"}]}"""


def build_judge_prompt(log: dict, max_items: int = 60) -> str:
    """Return the user-turn prompt text for Haiku, selecting items from log.

    Selection strategy:
    - Include all non-keyword drops (source_cap, ttl, dedupe) — small set, all interesting.
    - Include keyword drops with score >= threshold, sorted by score desc, up to _MAX_KEYWORD_DROPS.
    - Include all final items.
    - Hard-cap the total at max_items (trimming keyword drops first if needed).
    """
    other_drops: list[dict] = []
    for stage in ("dropped_source_cap", "dropped_ttl", "dropped_dedupe"):
        for item in log.get(stage, []):
            other_drops.append({**item, "stage": stage})

    kw_candidates = sorted(
        [it for it in log.get("dropped_keyword", [])
         if (it.get("score") or 0) >= _KEYWORD_SCORE_THRESHOLD],
        key=lambda x: x.get("score", 0),
        reverse=True,
    )[:_MAX_KEYWORD_DROPS]
    kw_drops = [{**it, "stage": "dropped_keyword"} for it in kw_candidates]

    final_items = [{**it, "stage": "final"} for it in log.get("final", [])]

    combined = other_drops + final_items + kw_drops
    if len(combined) > max_items:
        # Trim from kw_drops (lowest priority) first.
        trim = len(combined) - max_items
        kw_drops = kw_drops[:-trim] if trim < len(kw_drops) else []
        combined = other_drops + final_items + kw_drops

    fields = ["url", "title", "source", "score", "age_days", "stage"]
    items_json = json.dumps(
        [{k: it.get(k) for k in fields} for it in combined],
        ensure_ascii=False, indent=2,
    )
    return (
        f"Date: {log.get('date', 'unknown')}\n"
        f"Items to review ({len(combined)} total):\n{items_json}"
    )


def parse_judge_response(text: str) -> dict:
    """Parse Haiku's JSON response into {suspect_drops, suspect_keeps}.

    Returns empty lists on any parse failure — graceful degradation is
    preferable to a hard error that breaks the build step.
    """
    empty = {"suspect_drops": [], "suspect_keeps": []}
    try:
        # Haiku sometimes wraps the JSON in ```json … ``` fences. Strip them.
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(stripped)
        if "suspect_drops" not in data or "suspect_keeps" not in data:
            return empty
        return {
            "suspect_drops": list(data["suspect_drops"]),
            "suspect_keeps": list(data["suspect_keeps"]),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return empty


def run_judge(
    date: str,
    root: Path | str = ".",
    client=None,
    k: int = 10,
) -> Path:
    """Run Haiku triage for one day's log and write the judge JSON.

    Parameters
    ----------
    client:
        An Anthropic client instance (or mock for tests). If None, imports
        anthropic and creates a default client.
    k:
        Maximum suspect items to request in each direction.

    Returns the path of the written judge JSON file.
    """
    root = Path(root)
    log_path = root / "docs" / "logs" / f"{date}.json"
    if not log_path.exists():
        raise FileNotFoundError(
            f"No filter log for {date} at {log_path}. "
            f"Run `python content_finder.py` first."
        )

    log = json.loads(log_path.read_text())

    if client is None:
        import anthropic  # lazy import — not installed in all envs
        client = anthropic.Anthropic()

    prompt = build_judge_prompt(log)
    user_content = (
        f"Return at most {k} suspect_drops and {k} suspect_keeps.\n\n{prompt}"
    )

    from tracing import traced_message
    msg = traced_message(
        client,
        call_site="judge",
        prompt_version=JUDGE_PROMPT_VERSION,
        trace_path=root / "docs" / "logs" / "traces.jsonl",
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = msg.content[0].text
    result = parse_judge_response(raw)
    print(
        f"[judge] {len(result['suspect_drops'])} suspect_drops, "
        f"{len(result['suspect_keeps'])} suspect_keeps",
        file=sys.stderr,
    )

    out_dir = root / "docs" / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "date": date,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "suspect_drops": result["suspect_drops"],
            "suspect_keeps": result["suspect_keeps"],
        },
        ensure_ascii=False, indent=2,
    )
    out_path = out_dir / f"{date}.judge.json"
    out_path.write_text(payload)
    # Stable handoff for the Hermes Discovery Queue skill; pairs with
    # docs/logs/latest.json.
    (out_dir / "latest.judge.json").write_text(payload)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Haiku triage on a filter log."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="Judge one day's log.")
    p_run.add_argument("date", help="Date in YYYY-MM-DD form.")
    p_run.add_argument("--root", default=".", help="Repo root (default: cwd).")
    p_run.add_argument("--k", type=int, default=10,
                       help="Max suspect items per direction (default: 10).")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        out = run_judge(args.date, root=args.root, k=args.k)
        print(out)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
