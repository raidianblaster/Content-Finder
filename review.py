#!/usr/bin/env python3
"""Build a labelable HTML review page from a per-run filter log.

Reads `<root>/docs/logs/<date>.json` (written by content_finder.py) and
emits `<root>/docs/review/<date>.html`. The page groups every item the
pipeline saw by which filter stage decided its fate, and lets the reader
record a keep/drop/unsure verdict per item. Verdicts persist in
localStorage; a Download JSONL button exports them as
`feedback/<date>.jsonl` for committing to the repo.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import sys
from pathlib import Path


STAGES = [
    ("final", "Final — kept in today's digest",
     "Items that survived every filter. Mark drop if you'd have cut them."),
    ("dropped_source_cap", "Dropped: Source cap",
     "Cut because the source already had its quota for the day."),
    ("dropped_ttl", "Dropped: TTL (cross-day)",
     "Cut because we already showed this story on a prior day."),
    ("dropped_dedupe", "Dropped: Dedupe",
     "Cut as a duplicate of another item in the same run."),
    ("dropped_keyword", "Dropped: Keyword filter",
     "Cut because the title + summary contained no scored keywords. "
     "Voluminous — skim, don't read every one."),
]


CSS = """
:root {
  --bg-0: #0a0a0d; --bg-1: #111116; --bg-2: #1a1a22;
  --border: #2a2a35; --fg: #e8e8f0; --fg-mid: #a0a0b0; --fg-dim: #6a6a80;
  --purple: hsl(292 60% 65%); --green: #6ee7b7; --amber: #fcd34d; --red: #fca5a5;
  --keep-bg: rgba(110, 231, 183, 0.15); --drop-bg: rgba(252, 165, 165, 0.18);
  --unsure-bg: rgba(252, 211, 77, 0.18);
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 16px 96px; background: var(--bg-0); color: var(--fg);
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px; line-height: 1.5;
}
header {
  padding: 24px 0 16px; border-bottom: 1px solid var(--border);
  margin-bottom: 24px;
}
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: var(--fg-mid); font-size: 13px; }
.pipeline {
  font-family: 'DM Mono', ui-monospace, monospace; font-size: 12px;
  color: var(--fg-mid); margin-top: 8px;
}
section { margin-bottom: 32px; }
section h2 {
  font-size: 16px; margin: 0 0 4px; color: var(--purple);
}
section .blurb { color: var(--fg-mid); font-size: 13px; margin-bottom: 12px; }
.card {
  background: var(--bg-1); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 14px; margin-bottom: 10px;
}
.card.verdict-keep { background: var(--keep-bg); border-color: var(--green); }
.card.verdict-drop { background: var(--drop-bg); border-color: var(--red); }
.card.verdict-unsure { background: var(--unsure-bg); border-color: var(--amber); }
.card .title {
  font-weight: 500; margin-bottom: 4px; display: block;
  color: var(--fg); text-decoration: none;
}
.card .title:hover { color: var(--purple); text-decoration: underline; }
.card .meta {
  font-family: 'DM Mono', ui-monospace, monospace; font-size: 11px;
  color: var(--fg-dim); margin-bottom: 8px;
}
.card .meta .sep { margin: 0 6px; opacity: 0.5; }
.verdicts { display: flex; gap: 6px; }
.verdicts button {
  background: var(--bg-2); border: 1px solid var(--border); color: var(--fg-mid);
  font-family: inherit; font-size: 12px; padding: 4px 10px; border-radius: 4px;
  cursor: pointer;
}
.verdicts button:hover { color: var(--fg); border-color: var(--fg-dim); }
.verdicts button.active[data-verdict="keep"] {
  background: var(--green); color: var(--bg-0); border-color: var(--green);
}
.verdicts button.active[data-verdict="drop"] {
  background: var(--red); color: var(--bg-0); border-color: var(--red);
}
.verdicts button.active[data-verdict="unsure"] {
  background: var(--amber); color: var(--bg-0); border-color: var(--amber);
}
.note-input {
  display: none; margin-top: 8px; width: 100%; background: var(--bg-2);
  border: 1px solid var(--border); color: var(--fg); padding: 6px 8px;
  border-radius: 4px; font-family: inherit; font-size: 13px;
}
.card.has-verdict .note-input { display: block; }
footer {
  position: fixed; bottom: 0; left: 0; right: 0; background: var(--bg-1);
  border-top: 1px solid var(--border); padding: 12px 16px;
  display: flex; align-items: center; gap: 12px;
  font-family: 'DM Mono', ui-monospace, monospace; font-size: 12px;
}
footer .count { color: var(--fg-mid); flex: 1; }
footer button {
  background: var(--purple); border: 0; color: var(--bg-0); font-weight: 500;
  padding: 6px 14px; border-radius: 4px; cursor: pointer; font-family: inherit;
  font-size: 12px;
}
footer button.secondary { background: var(--bg-2); color: var(--fg); }
footer .hint { color: var(--fg-dim); font-size: 11px; }
"""


def _esc(s: str) -> str:
    return html_mod.escape(s or "", quote=True)


def _render_card(item: dict, stage: str) -> str:
    title = _esc(item.get("title", "(untitled)"))
    url = _esc(item.get("url", ""))
    source = _esc(item.get("source", ""))
    score = item.get("score", 0)
    age = item.get("age_days", 0)
    first_seen = item.get("first_seen", "")

    meta_parts = [
        f'<span class="src">{source}</span>',
        f'<span class="sep">·</span><span>score {score}</span>',
        f'<span class="sep">·</span><span>{age}d old</span>',
    ]
    if first_seen:
        meta_parts.append(f'<span class="sep">·</span><span>first seen {first_seen}</span>')

    return f'''  <div class="card" data-url="{url}" data-stage="{stage}">
    <a class="title" href="{url}" target="_blank" rel="noopener">{title}</a>
    <div class="meta">{"".join(meta_parts)}</div>
    <div class="verdicts">
      <button data-verdict="keep" data-url="{url}">keep ✓</button>
      <button data-verdict="drop" data-url="{url}">drop ✗</button>
      <button data-verdict="unsure" data-url="{url}">unsure ?</button>
    </div>
    <input class="note-input" placeholder="note (optional)" data-url="{url}">
  </div>'''


def _render_section(stage_key: str, heading: str, blurb: str, items: list[dict]) -> str:
    if not items:
        return ""
    cards = "\n".join(_render_card(it, stage_key) for it in items)
    return f'''<section>
  <h2>{_esc(heading)} <span style="color:var(--fg-dim);font-weight:400">({len(items)})</span></h2>
  <div class="blurb">{_esc(blurb)}</div>
{cards}
</section>'''


JS_TEMPLATE = """
<script>
const REVIEW_DATE = %(date_json)s;
const TOTAL_ITEMS = %(total)d;
const ITEM_INDEX = %(index_json)s;
const STORAGE_PREFIX = "cf-review::" + REVIEW_DATE + "::";

function key(url) { return STORAGE_PREFIX + url; }

function loadVerdict(url) {
  const raw = localStorage.getItem(key(url));
  return raw ? JSON.parse(raw) : null;
}

function saveVerdict(url, patch) {
  const cur = loadVerdict(url) || {};
  const next = Object.assign({}, cur, patch, {
    labelled_at: new Date().toISOString(),
  });
  localStorage.setItem(key(url), JSON.stringify(next));
  updateCount();
}

function updateCard(card) {
  const url = card.dataset.url;
  const v = loadVerdict(url);
  card.classList.remove("verdict-keep", "verdict-drop", "verdict-unsure", "has-verdict");
  card.querySelectorAll(".verdicts button").forEach(b => b.classList.remove("active"));
  if (v && v.verdict) {
    card.classList.add("verdict-" + v.verdict, "has-verdict");
    const btn = card.querySelector(`.verdicts button[data-verdict="${v.verdict}"]`);
    if (btn) btn.classList.add("active");
    const note = card.querySelector(".note-input");
    if (note) note.value = v.note || "";
  }
}

function updateCount() {
  let n = 0;
  for (const url of ITEM_INDEX) {
    if (loadVerdict(url)) n++;
  }
  const el = document.getElementById("count");
  if (el) el.textContent = n + " / " + TOTAL_ITEMS + " labelled";
}

function buildJSONL() {
  const lines = [];
  for (const url of ITEM_INDEX) {
    const v = loadVerdict(url);
    if (!v || !v.verdict) continue;
    const meta = ITEM_META[url] || {};
    lines.push(JSON.stringify({
      date: REVIEW_DATE,
      url: url,
      title: meta.title || "",
      source: meta.source || "",
      stage: meta.stage || "",
      score: meta.score,
      age_days: meta.age_days,
      verdict: v.verdict,
      note: v.note || "",
      labelled_at: v.labelled_at,
    }));
  }
  return lines.join("\\n") + (lines.length ? "\\n" : "");
}

function downloadJSONL() {
  const blob = new Blob([buildJSONL()], {type: "application/x-ndjson"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "feedback/" + REVIEW_DATE + ".jsonl";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

async function copyJSONL() {
  await navigator.clipboard.writeText(buildJSONL());
  const btn = document.getElementById("copy-jsonl");
  const orig = btn.textContent;
  btn.textContent = "copied!";
  setTimeout(() => { btn.textContent = orig; }, 1200);
}

const ITEM_META = %(meta_json)s;

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".card").forEach(card => {
    updateCard(card);
    card.querySelectorAll(".verdicts button").forEach(btn => {
      btn.addEventListener("click", () => {
        const url = btn.dataset.url;
        const cur = loadVerdict(url);
        if (cur && cur.verdict === btn.dataset.verdict) {
          localStorage.removeItem(key(url));
        } else {
          saveVerdict(url, {verdict: btn.dataset.verdict});
        }
        updateCard(card);
      });
    });
    const note = card.querySelector(".note-input");
    if (note) {
      note.addEventListener("input", () => {
        if (loadVerdict(note.dataset.url)) {
          saveVerdict(note.dataset.url, {note: note.value});
        }
      });
    }
  });
  document.getElementById("download-jsonl").addEventListener("click", downloadJSONL);
  document.getElementById("copy-jsonl").addEventListener("click", copyJSONL);
  updateCount();
});
</script>
"""


def render(log: dict) -> str:
    """Render a full HTML review page from a parsed log dict."""
    date = log["date"]
    pipeline = log.get("pipeline", {})
    prompt_version = log.get("prompt_version", "?")

    sections_html = []
    item_index = []
    item_meta = {}
    for stage_key, heading, blurb in STAGES:
        items = log.get(stage_key, [])
        if stage_key == "final":
            items = log.get("final", [])
        for it in items:
            url = it.get("url", "")
            if url:
                item_index.append(url)
                item_meta[url] = {
                    "title": it.get("title", ""),
                    "source": it.get("source", ""),
                    "stage": stage_key,
                    "score": it.get("score"),
                    "age_days": it.get("age_days"),
                }
        sections_html.append(_render_section(stage_key, heading, blurb, items))

    sections_html = [s for s in sections_html if s]

    pipeline_line = " · ".join(f"{k}: {v}" for k, v in pipeline.items())

    js = JS_TEMPLATE % {
        "date_json": json.dumps(date),
        "total": len(item_index),
        "index_json": json.dumps(item_index),
        "meta_json": json.dumps(item_meta),
    }

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Review — {_esc(date)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Filter-log review — {_esc(date)}</h1>
  <div class="sub">prompt version <code>{_esc(prompt_version)}</code> · label each item <code>keep / drop / unsure</code>, then download as <code>feedback/{_esc(date)}.jsonl</code>.</div>
  <div class="pipeline">{_esc(pipeline_line)}</div>
</header>
{chr(10).join(sections_html)}
<footer>
  <span class="count" id="count">0 / 0 labelled</span>
  <span class="hint">verdicts saved to localStorage automatically</span>
  <button id="copy-jsonl" class="secondary">copy JSONL</button>
  <button id="download-jsonl">download JSONL</button>
</footer>
{js}
</body>
</html>'''


def build(date: str, root: Path | str = ".") -> Path:
    """Read `<root>/docs/logs/<date>.json` and write the review HTML.

    Returns the path of the written HTML file.
    """
    root = Path(root)
    log_path = root / "docs" / "logs" / f"{date}.json"
    if not log_path.exists():
        raise FileNotFoundError(
            f"No filter log for {date} at {log_path}. "
            f"Run `python content_finder.py --out docs/index.html` first."
        )

    log = json.loads(log_path.read_text())
    out_dir = root / "docs" / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date}.html"
    out_path.write_text(render(log))
    return out_path


def build_all(root: Path | str = ".") -> list[Path]:
    """Rebuild a review page for every log file under `<root>/docs/logs/`."""
    root = Path(root)
    logs_dir = root / "docs" / "logs"
    written: list[Path] = []
    for log_path in sorted(logs_dir.glob("*.json")):
        date = log_path.stem
        written.append(build(date, root=root))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate review HTML from a filter log."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="Build review page(s).")
    p_build.add_argument("date", nargs="?", help="Date in YYYY-MM-DD form.")
    p_build.add_argument("--all", action="store_true",
                         help="Rebuild every log under docs/logs/.")
    p_build.add_argument("--root", default=".", help="Repo root (default: cwd).")

    args = parser.parse_args(argv)
    if args.cmd == "build":
        if args.all:
            written = build_all(root=args.root)
            for p in written:
                print(p)
            print(f"[info] wrote {len(written)} review pages", file=sys.stderr)
            return 0
        if not args.date:
            parser.error("provide a date or pass --all")
        out = build(args.date, root=args.root)
        print(out)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
