#!/usr/bin/env python3
"""CLI rollup of the LLM trace ledger (docs/logs/traces.jsonl).

Usage:
    python traces.py                      # rollup of the whole ledger
    python traces.py --since 2026-05-30   # only rows on/after a date
    python traces.py --path /tmp/t.jsonl  # a different ledger
"""
from __future__ import annotations

import argparse

from tracing import DEFAULT_TRACE_PATH, load_traces, rollup


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Summarise the LLM trace ledger.")
    ap.add_argument("--path", default=str(DEFAULT_TRACE_PATH),
                    help="Trace JSONL path (default: docs/logs/traces.jsonl).")
    ap.add_argument("--since", default=None,
                    help="Only include rows with ts >= this ISO date/datetime.")
    args = ap.parse_args(argv)

    data = rollup(load_traces(args.path), since=args.since)
    print(
        f"calls={data['calls']}  cost=${data['cost_usd']:.4f}  "
        f"in={data['input_tokens']}  out={data['output_tokens']}  "
        f"p50={data['p50_latency_ms']}ms"
    )
    for site, s in sorted(data["by_call_site"].items()):
        print(
            f"  {site:12} calls={s['calls']:>4}  cost=${s['cost_usd']:.4f}  "
            f"in={s['input_tokens']}  out={s['output_tokens']}  errors={s['errors']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
