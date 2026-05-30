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

# Short labels used in the "was: <stage>" chip on cards lifted into the
# Needs-review section.
STAGE_SHORT_LABELS = {
    "final": "final",
    "dropped_source_cap": "source cap",
    "dropped_ttl": "TTL",
    "dropped_dedupe": "dedupe",
    "dropped_keyword": "keyword filter",
}


# GitHub target for the browser-side auto-save path. A fine-grained PAT
# scoped to this single public repo with Contents: write is the lowest
# blast-radius option for the single-user labelling workflow — see
# CLAUDE.md "First-run setup".
REPO_OWNER = "raidianblaster"
REPO_NAME = "Content-Finder"
BRANCH = "main"


CSS = """
:root {
  --bg-0: #0a0a0d; --bg-1: #111116; --bg-2: #1a1a22;
  --border: #2a2a35; --fg: #e8e8f0; --fg-mid: #a0a0b0; --fg-dim: #6a6a80;
  --purple: hsl(292 60% 65%); --green: #6ee7b7; --amber: #fcd34d; --red: #fca5a5;
  --keep-bg: rgba(110, 231, 183, 0.15); --drop-bg: rgba(252, 165, 165, 0.18);
  --unsure-bg: rgba(252, 211, 77, 0.18);
  --judge-drop-accent: hsl(45 90% 55%); --judge-keep-accent: hsl(0 80% 65%);
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
.card.judge-suspect-drop { border-left: 3px solid var(--judge-drop-accent); }
.card.judge-suspect-keep { border-left: 3px solid var(--judge-keep-accent); }
.judge-flag {
  display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px;
  margin-left: 6px; vertical-align: middle; font-family: 'DM Mono', ui-monospace, monospace;
}
.judge-flag-drop { background: hsla(45,90%,55%,0.2); color: var(--judge-drop-accent); }
.judge-flag-keep { background: hsla(0,80%,65%,0.2); color: var(--judge-keep-accent); }
.from-stage {
  display: inline-block; font-family: 'DM Mono', ui-monospace, monospace;
  font-size: 10px; color: var(--fg-dim); margin-left: 8px;
  padding: 1px 6px; border: 1px solid var(--border); border-radius: 3px;
  vertical-align: middle;
}
.judge-reason {
  font-size: 12px; color: var(--fg-mid); font-style: italic;
  margin: 4px 0 8px; padding-left: 8px; border-left: 2px solid var(--border);
}
.judge-reason::before { content: "Haiku: "; color: var(--fg-dim); font-style: normal; }
#needs-review h2 { color: var(--judge-drop-accent); }
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
footer .save-status {
  font-size: 11px; padding: 3px 8px; border-radius: 10px;
  background: var(--bg-2); color: var(--fg-dim);
  border: 1px solid var(--border);
}
footer .save-status.dirty { color: var(--amber); border-color: var(--amber); }
footer .save-status.saving { color: var(--purple); border-color: var(--purple); }
footer .save-status.saved { color: var(--green); border-color: var(--green); }
footer .save-status.error { color: var(--red); border-color: var(--red); }
footer button.icon {
  background: var(--bg-2); color: var(--fg-mid); font-size: 14px;
  padding: 4px 8px; border: 1px solid var(--border);
}
#settings-panel {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: none; align-items: center; justify-content: center;
  z-index: 50;
}
#settings-panel.open { display: flex; }
#settings-panel .card-inner {
  background: var(--bg-1); border: 1px solid var(--border); border-radius: 10px;
  padding: 20px; width: min(420px, calc(100% - 32px));
  font-family: 'DM Sans', -apple-system, sans-serif;
}
#settings-panel h3 { margin: 0 0 8px; font-size: 16px; color: var(--fg); }
#settings-panel p { margin: 0 0 14px; font-size: 13px; color: var(--fg-mid); }
#settings-panel a { color: var(--purple); }
#settings-panel input {
  width: 100%; background: var(--bg-2); border: 1px solid var(--border);
  color: var(--fg); padding: 8px 10px; border-radius: 4px;
  font-family: 'DM Mono', ui-monospace, monospace; font-size: 12px;
  margin-bottom: 12px;
}
#settings-panel .row { display: flex; gap: 8px; justify-content: flex-end; }
#settings-panel button {
  background: var(--bg-2); color: var(--fg); border: 1px solid var(--border);
  padding: 6px 14px; border-radius: 4px; cursor: pointer;
  font-family: inherit; font-size: 13px;
}
#settings-panel button.primary {
  background: var(--purple); color: var(--bg-0); border-color: var(--purple);
  font-weight: 500;
}
#settings-panel .test-result {
  font-family: 'DM Mono', ui-monospace, monospace; font-size: 11px;
  color: var(--fg-dim); min-height: 16px; margin-bottom: 8px;
}
#settings-panel .test-result.ok { color: var(--green); }
#settings-panel .test-result.fail { color: var(--red); }
"""


def _esc(s: str) -> str:
    return html_mod.escape(s or "", quote=True)


def _render_card(
    item: dict,
    stage: str,
    suspect: str | None = None,
    from_stage_label: str | None = None,
    judge_reason: str | None = None,
) -> str:
    """Render one item card.

    suspect: None | "drop" (judge thinks this was a wrong drop) |
             "keep" (judge thinks this shouldn't have made the final cut).
    from_stage_label: short label shown as a `was: <label>` chip when this card
        is rendered in the Needs-review section instead of its original stage.
    judge_reason: Haiku's one-line rationale, shown inline below the meta line.
    """
    title = _esc(item.get("title", "(untitled)"))
    url = _esc(item.get("url", ""))
    source = _esc(item.get("source", ""))
    score = item.get("score", 0)
    age = item.get("age_days", 0)
    first_seen = item.get("first_seen", "")

    extra_classes = ""
    judge_badge = ""
    if suspect == "drop":
        extra_classes = " judge-suspect-drop"
        judge_badge = '<span class="judge-flag judge-flag-drop" title="Haiku: possible wrong drop">⚑ suspect drop</span>'
    elif suspect == "keep":
        extra_classes = " judge-suspect-keep"
        judge_badge = '<span class="judge-flag judge-flag-keep" title="Haiku: possible wrong keep">⚑ suspect keep</span>'

    from_chip = ""
    if from_stage_label:
        from_chip = f'<span class="from-stage">was: {_esc(from_stage_label)}</span>'

    reason_html = ""
    if judge_reason:
        reason_html = f'\n    <div class="judge-reason">{_esc(judge_reason)}</div>'

    meta_parts = [
        f'<span class="src">{source}</span>',
        f'<span class="sep">·</span><span>score {score}</span>',
        f'<span class="sep">·</span><span>{age}d old</span>',
    ]
    if first_seen:
        meta_parts.append(f'<span class="sep">·</span><span>first seen {first_seen}</span>')

    return f'''  <div class="card{extra_classes}" data-url="{url}" data-stage="{stage}">
    <a class="title" href="{url}" target="_blank" rel="noopener">{title}</a>{judge_badge}{from_chip}
    <div class="meta">{"".join(meta_parts)}</div>{reason_html}
    <div class="verdicts">
      <button data-verdict="keep" data-url="{url}">keep ✓</button>
      <button data-verdict="drop" data-url="{url}">drop ✗</button>
      <button data-verdict="unsure" data-url="{url}">unsure ?</button>
    </div>
    <input class="note-input" placeholder="note (optional)" data-url="{url}">
  </div>'''


def _render_section(
    stage_key: str,
    heading: str,
    blurb: str,
    items: list[dict],
    suspect_drops: set[str] | None = None,
    suspect_keeps: set[str] | None = None,
) -> str:
    if not items:
        return ""
    cards_html = []
    for it in items:
        url = it.get("url", "")
        suspect = None
        if suspect_drops and url in suspect_drops:
            suspect = "drop"
        elif suspect_keeps and url in suspect_keeps:
            suspect = "keep"
        cards_html.append(_render_card(it, stage_key, suspect=suspect))
    return f'''<section>
  <h2>{_esc(heading)} <span style="color:var(--fg-dim);font-weight:400">({len(items)})</span></h2>
  <div class="blurb">{_esc(blurb)}</div>
{chr(10).join(cards_html)}
</section>'''


JS_TEMPLATE = """
<script>
const REVIEW_DATE = %(date_json)s;
const TOTAL_ITEMS = %(total)d;
const ITEM_INDEX = %(index_json)s;
const STORAGE_PREFIX = "cf-review::" + REVIEW_DATE + "::";
const JUDGE = %(judge_json)s;

const REPO_OWNER = "raidianblaster";
const REPO_NAME = "Content-Finder";
const BRANCH = "main";
const PAT_KEY = "cf-review::__pat__";
const SAVE_DEBOUNCE_MS = 10000;

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
      summary: meta.summary || "",
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

// -- Auto-save to GitHub ---------------------------------------------------

function loadPat() { return localStorage.getItem(PAT_KEY) || ""; }
function savePat(t) {
  if (t) localStorage.setItem(PAT_KEY, t);
  else localStorage.removeItem(PAT_KEY);
}

function setStatus(state, text) {
  const el = document.getElementById("save-status");
  if (!el) return;
  el.className = "save-status " + state;
  el.textContent = text;
}

function refreshStatusIdle() {
  if (!loadPat()) {
    // If there are unsaved labels in localStorage already, surface that so the
    // user knows connecting will rescue them.
    const pending = buildJSONL();
    if (pending) setStatus("dirty", "unsaved · connect to save");
    else setStatus("idle", "not connected");
    return;
  }
  setStatus("idle", "ready");
}

function utf8ToBase64(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function ghHeaders(pat) {
  return {
    "Authorization": "Bearer " + pat,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

function feedbackPath() { return "feedback/" + REVIEW_DATE + ".jsonl"; }

function contentsUrl() {
  return "https://api.github.com/repos/" + REPO_OWNER + "/" + REPO_NAME
       + "/contents/" + feedbackPath();
}

async function fetchSha(pat) {
  const r = await fetch(contentsUrl() + "?ref=" + BRANCH,
    { headers: ghHeaders(pat) });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("get sha: " + r.status);
  const j = await r.json();
  return j.sha || null;
}

async function putContents(pat, body) {
  const r = await fetch(contentsUrl(), {
    method: "PUT",
    headers: Object.assign({"Content-Type": "application/json"}, ghHeaders(pat)),
    body: JSON.stringify(body),
  });
  return r;
}

async function commitJsonl() {
  const pat = loadPat();
  if (!pat) { setStatus("idle", "not connected"); return; }
  const jsonl = buildJSONL();
  if (!jsonl) { setStatus("idle", "nothing to save"); return; }

  setStatus("saving", "saving…");
  try {
    let sha = await fetchSha(pat);
    const body = {
      message: "review: update " + feedbackPath(),
      content: utf8ToBase64(jsonl),
      branch: BRANCH,
    };
    if (sha) body.sha = sha;
    let r = await putContents(pat, body);
    if (r.status === 409) {
      sha = await fetchSha(pat);
      if (sha) body.sha = sha; else delete body.sha;
      r = await putContents(pat, body);
    }
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(r.status + " " + (j.message || ""));
    }
    const now = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    setStatus("saved", "saved " + now);
  } catch (e) {
    setStatus("error", "error: " + e.message + " · click to retry");
  }
}

let saveTimer = null;
function scheduleSave() {
  if (!loadPat()) { setStatus("dirty", "unsaved (connect repo)"); return; }
  setStatus("dirty", "unsaved · saving in " + (SAVE_DEBOUNCE_MS / 1000) + "s");
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { saveTimer = null; commitJsonl(); }, SAVE_DEBOUNCE_MS);
}

async function testPat() {
  const input = document.getElementById("pat-input");
  const out = document.getElementById("pat-test-result");
  const pat = input.value.trim();
  if (!pat) { out.className = "test-result fail"; out.textContent = "paste a token first"; return; }
  out.className = "test-result"; out.textContent = "testing…";
  try {
    const r = await fetch("https://api.github.com/repos/" + REPO_OWNER + "/" + REPO_NAME,
      { headers: ghHeaders(pat) });
    if (!r.ok) throw new Error(r.status + "");
    out.className = "test-result ok"; out.textContent = "connection ok";
  } catch (e) {
    out.className = "test-result fail"; out.textContent = "failed: " + e.message;
  }
}

function openSettings() {
  document.getElementById("pat-input").value = loadPat();
  document.getElementById("pat-test-result").textContent = "";
  document.getElementById("settings-panel").classList.add("open");
}
function closeSettings() {
  document.getElementById("settings-panel").classList.remove("open");
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
        scheduleSave();
      });
    });
    const note = card.querySelector(".note-input");
    if (note) {
      note.addEventListener("input", () => {
        if (loadVerdict(note.dataset.url)) {
          saveVerdict(note.dataset.url, {note: note.value});
          scheduleSave();
        }
      });
    }
  });
  document.getElementById("download-jsonl").addEventListener("click", downloadJSONL);
  document.getElementById("copy-jsonl").addEventListener("click", copyJSONL);
  document.getElementById("settings-toggle").addEventListener("click", openSettings);
  document.getElementById("settings-close").addEventListener("click", closeSettings);
  document.getElementById("pat-test").addEventListener("click", testPat);
  document.getElementById("pat-save").addEventListener("click", () => {
    const v = document.getElementById("pat-input").value.trim();
    savePat(v);
    closeSettings();
    // Flush any labels already in localStorage (e.g. labelled before the PAT
    // was connected) the moment a token lands.
    if (v && buildJSONL()) commitJsonl(); else refreshStatusIdle();
  });
  document.getElementById("save-status").addEventListener("click", (e) => {
    if (e.currentTarget.classList.contains("error")) commitJsonl();
  });
  updateCount();
  refreshStatusIdle();
});
</script>
"""


def render(log: dict, judge: dict | None = None) -> str:
    """Render a full HTML review page from a parsed log dict.

    judge: optional parsed .judge.json dict with suspect_drops / suspect_keeps
    arrays.  When provided the URL sets are converted to dicts and inlined as
    `const JUDGE` in the page script; suspect cards also receive CSS classes
    emitted server-side at build time.
    """
    date = log["date"]
    pipeline = log.get("pipeline", {})
    prompt_version = log.get("prompt_version", "?")

    # Build URL-keyed sets and reason dicts for server-side suspect class
    # emission and inline reason display.
    suspect_drops: set[str] = set()
    suspect_keeps: set[str] = set()
    drop_reasons: dict[str, str] = {}
    keep_reasons: dict[str, str] = {}
    judge_js_value = "null"
    if judge:
        for it in judge.get("suspect_drops", []):
            url = it.get("url")
            if url:
                suspect_drops.add(url)
                drop_reasons[url] = it.get("reason", "") or ""
        for it in judge.get("suspect_keeps", []):
            url = it.get("url")
            if url:
                suspect_keeps.add(url)
                keep_reasons[url] = it.get("reason", "") or ""
        judge_js = {
            "suspect_drops": {
                url: {"stage": it.get("stage"), "reason": drop_reasons.get(url, "")}
                for url, it in zip(
                    [x.get("url") for x in judge.get("suspect_drops", []) if x.get("url")],
                    [x for x in judge.get("suspect_drops", []) if x.get("url")],
                )
            },
            "suspect_keeps": {
                url: {"reason": keep_reasons.get(url, "")}
                for url in suspect_keeps
            },
        }
        judge_js_value = json.dumps(judge_js)

    all_suspects = suspect_drops | suspect_keeps

    # First pass: build item_index / item_meta in display order (suspects first,
    # then remaining items grouped by stage). Also collect suspect items for
    # the Needs-review section, in (drops then keeps) order matching the judge
    # output ordering.
    sections_html: list[str] = []
    item_index: list[str] = []
    item_meta: dict[str, dict] = {}
    items_by_stage: dict[str, list[dict]] = {}
    url_to_stage: dict[str, str] = {}

    for stage_key, _, _ in STAGES:
        stage_items = log.get(stage_key, [])
        items_by_stage[stage_key] = stage_items
        for it in stage_items:
            url = it.get("url", "")
            if url and url not in url_to_stage:
                url_to_stage[url] = stage_key
                item_meta[url] = {
                    "title": it.get("title", ""),
                    "summary": it.get("summary", ""),
                    "source": it.get("source", ""),
                    "stage": stage_key,
                    "score": it.get("score"),
                    "age_days": it.get("age_days"),
                }

    # Needs-review section (only when judge supplied any suspects).
    if all_suspects:
        suspect_cards: list[str] = []
        # Preserve the judge's drop/keep ordering, fall back to set order.
        drop_urls = [it["url"] for it in (judge.get("suspect_drops", []) if judge else [])
                     if it.get("url") and it["url"] in url_to_stage]
        keep_urls = [it["url"] for it in (judge.get("suspect_keeps", []) if judge else [])
                     if it.get("url") and it["url"] in url_to_stage]
        ordered_suspects = drop_urls + keep_urls

        for url in ordered_suspects:
            origin_stage = url_to_stage[url]
            # Find the item dict in its original stage.
            it = next((x for x in items_by_stage[origin_stage] if x.get("url") == url), None)
            if it is None:
                continue
            item_index.append(url)
            if url in suspect_drops:
                kind, reason = "drop", drop_reasons.get(url, "")
            else:
                kind, reason = "keep", keep_reasons.get(url, "")
            suspect_cards.append(_render_card(
                it, origin_stage, suspect=kind,
                from_stage_label=STAGE_SHORT_LABELS.get(origin_stage, origin_stage),
                judge_reason=reason,
            ))

        if suspect_cards:
            blurb = ("Items the judge flagged for your attention. "
                     "Label these first — the rest of the page is for context.")
            sections_html.append(
                f'<section id="needs-review">\n'
                f'  <h2>Needs review <span style="color:var(--fg-dim);font-weight:400">'
                f'({len(suspect_cards)})</span></h2>\n'
                f'  <div class="blurb">{_esc(blurb)}</div>\n'
                + "\n".join(suspect_cards) + "\n</section>"
            )

    # Original stage sections, with suspects removed (they live in needs-review now).
    for stage_key, heading, blurb in STAGES:
        items = [it for it in items_by_stage[stage_key]
                 if it.get("url", "") not in all_suspects]
        for it in items:
            url = it.get("url", "")
            if url:
                item_index.append(url)
        sections_html.append(_render_section(stage_key, heading, blurb, items))

    sections_html = [s for s in sections_html if s]

    pipeline_line = " · ".join(f"{k}: {v}" for k, v in pipeline.items())

    js = JS_TEMPLATE % {
        "date_json": json.dumps(date),
        "total": len(item_index),
        "index_json": json.dumps(item_index),
        "meta_json": json.dumps(item_meta),
        "judge_json": judge_js_value,
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
  <span id="save-status" class="save-status" title="auto-save status (click on error to retry)">not connected</span>
  <button id="settings-toggle" class="icon" title="connect to GitHub">⚙</button>
  <button id="copy-jsonl" class="secondary">copy</button>
  <button id="download-jsonl" class="secondary">download</button>
</footer>
<div id="settings-panel">
  <div class="card-inner">
    <h3>Connect to GitHub</h3>
    <p>Paste a fine-grained Personal Access Token scoped to <code>{_esc(REPO_OWNER)}/{_esc(REPO_NAME)}</code> with <code>Contents: Read and write</code>. After this, your labels auto-save to <code>feedback/{_esc(date)}.jsonl</code>.</p>
    <input id="pat-input" type="password" autocomplete="off" spellcheck="false" placeholder="github_pat_…">
    <div id="pat-test-result" class="test-result"></div>
    <div class="row">
      <button id="settings-close">cancel</button>
      <button id="pat-test">test connection</button>
      <button id="pat-save" class="primary">save</button>
    </div>
  </div>
</div>
{js}
</body>
</html>'''


def build(date: str, root: Path | str = ".") -> Path:
    """Read `<root>/docs/logs/<date>.json` and write the review HTML.

    Also reads `<root>/docs/review/<date>.judge.json` if it exists and inlines
    the judge triage data so suspect cards are highlighted at page load.

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

    judge: dict | None = None
    judge_path = root / "docs" / "review" / f"{date}.judge.json"
    if judge_path.exists():
        judge = json.loads(judge_path.read_text())

    out_dir = root / "docs" / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date}.html"
    out_path.write_text(render(log, judge=judge))
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


_INDEX_CSS = """
body {
  margin: 0; padding: 24px 16px 48px; background: #0a0a0d; color: #e8e8f0;
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px; line-height: 1.5;
}
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: #a0a0b0; font-size: 13px; margin-bottom: 24px; }
ul.entries { list-style: none; padding: 0; margin: 0; }
ul.entries li {
  background: #111116; border: 1px solid #2a2a35; border-radius: 8px;
  padding: 12px 14px; margin-bottom: 10px;
}
ul.entries a {
  color: hsl(292 60% 65%); text-decoration: none; font-weight: 500; font-size: 16px;
}
ul.entries a:hover { text-decoration: underline; }
.meta {
  font-family: 'DM Mono', ui-monospace, monospace; font-size: 11px;
  color: #6a6a80; margin-top: 4px;
}
.meta .suspects { color: hsl(45 90% 55%); margin-left: 8px; }
"""


def _index_entry(date: str, root: Path) -> str:
    """Build one <li> for the review index for a given date."""
    log_path = root / "docs" / "logs" / f"{date}.json"
    pipeline_summary = ""
    if log_path.exists():
        try:
            log = json.loads(log_path.read_text())
            p = log.get("pipeline", {})
            fetched = p.get("fetched", "?")
            final = p.get("after_source_cap", "?")
            pipeline_summary = f"{fetched} fetched → {final} final"
        except Exception:
            pass

    suspects_html = ""
    judge_path = root / "docs" / "review" / f"{date}.judge.json"
    if judge_path.exists():
        try:
            jd = json.loads(judge_path.read_text())
            n = len(jd.get("suspect_drops", [])) + len(jd.get("suspect_keeps", []))
            if n:
                suspects_html = f'<span class="suspects">⚑ {n} suspects flagged</span>'
        except Exception:
            pass

    return (
        f'  <li>\n'
        f'    <a href="{_esc(date)}.html">{_esc(date)}</a>\n'
        f'    <div class="meta">{_esc(pipeline_summary)}{suspects_html}</div>\n'
        f'  </li>'
    )


def build_index(root: Path | str = ".") -> Path:
    """Write `<root>/docs/review/index.html` — a listing of past review pages.

    Globs `<root>/docs/review/*.html`, excludes `latest.html` and `index.html`,
    and emits a newest-first list. Each entry shows date (linked), pipeline
    summary from the log, and judge suspect count if a `.judge.json` exists.
    """
    root = Path(root)
    review_dir = root / "docs" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    dates: list[str] = []
    for html_path in review_dir.glob("*.html"):
        stem = html_path.stem
        if stem in ("latest", "index"):
            continue
        dates.append(stem)
    dates.sort(reverse=True)

    entries = "\n".join(_index_entry(d, root) for d in dates) if dates else \
              '  <li class="meta">no review pages yet</li>'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Review index</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap">
<style>{_INDEX_CSS}</style>
</head>
<body>
<h1>Filter-log review</h1>
<div class="sub">Daily review pages. Newest first. Bookmark <code>latest.html</code> for the freshest one.</div>
<ul class="entries">
{entries}
</ul>
</body>
</html>'''

    out_path = review_dir / "index.html"
    out_path.write_text(html)
    return out_path


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

    p_index = sub.add_parser(
        "build-index", help="Build the review/index.html listing.")
    p_index.add_argument("--root", default=".", help="Repo root (default: cwd).")

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
    if args.cmd == "build-index":
        out = build_index(root=args.root)
        print(out)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
