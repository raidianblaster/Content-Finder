"""Best-effort tracing of LLM calls → docs/logs/traces.jsonl (roadmap M0.1).

One JSONL row per Claude call: tokens, cost, latency, model, prompt_version.
Used by content_finder.synthesize_with_claude and judge.run_judge. A tracing
failure must NEVER break the pipeline — logging errors are swallowed, and a
failed LLM call still records ok=false and re-raises.

Read it back with `python traces.py` (see traces.py / rollup()).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

# USD per 1M tokens. Placeholder rates — confirm against the Anthropic pricing
# page; only the ledger's cost column depends on these.
PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":         {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5":          {"in": 1.00, "out": 5.00},
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
}
DEFAULT_TRACE_PATH = Path("docs/logs/traces.jsonl")


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost for a call. Unknown models cost 0.0 (and are still logged)."""
    p = PRICES.get(model)
    if p is None and "-" in model:
        # Tolerate dated snapshots, e.g. claude-haiku-4-5-20251001.
        p = PRICES.get(model.rsplit("-", 1)[0])
    p = p or {"in": 0.0, "out": 0.0}
    return round(input_tokens / 1e6 * p["in"] + output_tokens / 1e6 * p["out"], 6)


def traced_message(client, *, call_site: str, prompt_version: str = "",
                   trace_path: "Path | str" = DEFAULT_TRACE_PATH, **create_kwargs):
    """Call ``client.messages.create(**create_kwargs)``, append one trace row,
    and return the response unchanged.

    Best-effort: any error writing the trace is swallowed; an error from the LLM
    call records ok=false then re-raises so callers see the real failure.
    """
    t0 = time.perf_counter()
    ok = True
    msg = None
    try:
        msg = client.messages.create(**create_kwargs)
        return msg
    except Exception:
        ok = False
        raise
    finally:
        _append_row(
            trace_path,
            call_site=call_site,
            prompt_version=prompt_version,
            model=create_kwargs.get("model", ""),
            msg=msg,
            ok=ok,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )


def _append_row(trace_path, *, call_site, prompt_version, model, msg, ok, latency_ms):
    try:
        usage = getattr(msg, "usage", None)
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "call_site": call_site,
            "model": model,
            "prompt_version": prompt_version,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": estimate_cost(model, in_tok, out_tok),
            "latency_ms": round(latency_ms, 1),
            # Surfaces truncation: "max_tokens" here means the response was cut
            # off and a trailing card may have lost its source link.
            "stop_reason": getattr(msg, "stop_reason", None),
            "ok": ok,
        }
        path = Path(trace_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass  # tracing must never break the run


def load_traces(trace_path: "Path | str" = DEFAULT_TRACE_PATH) -> list[dict]:
    """Read a trace ledger; tolerate a missing file and malformed lines."""
    path = Path(trace_path)
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def rollup(rows: list[dict], since: "str | None" = None) -> dict:
    """Aggregate trace rows into totals + a per-call_site breakdown.

    `since` is an ISO date/datetime string compared lexicographically against
    each row's `ts` (ISO-8601 sorts correctly as text).
    """
    if since:
        rows = [r for r in rows if (r.get("ts", "") >= since)]
    by_site: dict[str, dict] = {}
    total_cost = 0.0
    total_in = total_out = 0
    latencies: list[float] = []
    for r in rows:
        site = r.get("call_site", "?")
        s = by_site.setdefault(site, {"calls": 0, "cost_usd": 0.0,
                                      "input_tokens": 0, "output_tokens": 0,
                                      "errors": 0})
        s["calls"] += 1
        s["cost_usd"] += r.get("cost_usd", 0.0) or 0.0
        s["input_tokens"] += r.get("input_tokens", 0) or 0
        s["output_tokens"] += r.get("output_tokens", 0) or 0
        if not r.get("ok", True):
            s["errors"] += 1
        total_cost += r.get("cost_usd", 0.0) or 0.0
        total_in += r.get("input_tokens", 0) or 0
        total_out += r.get("output_tokens", 0) or 0
        lat = r.get("latency_ms")
        if isinstance(lat, (int, float)):
            latencies.append(lat)
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    return {
        "calls": len(rows),
        "cost_usd": round(total_cost, 6),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "p50_latency_ms": p50,
        "by_call_site": {
            k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_site.items()
        },
    }
