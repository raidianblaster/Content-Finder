#!/usr/bin/env python3
"""Content Finder — credible agentic-AI news digest for AI product managers.

Pulls from a curated set of RSS feeds plus Hacker News, scores items for
relevance to agentic engineering / LLM industry trends, and prints a digest
to stdout (optionally synthesised by Claude into a themed brief).
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser
import httpx


HK_TZ = ZoneInfo("Asia/Hong_Kong")


def today_hkt(now: datetime | None = None) -> date:
    """Return today's calendar date in Hong Kong (HKT, UTC+8).

    Why: GitHub Actions runs in UTC, so a 23:00-UTC cron lands at 07:00 HKT
    the *next* day. Using `datetime.now()` for the page header puts the wrong
    date on every cron run; we anchor on HKT instead.
    """
    now = now or datetime.now(timezone.utc)
    return now.astimezone(HK_TZ).date()


# Fixed taxonomy used both in the LLM prompt and the chip filter bar.
TAG_TAXONOMY: list[str] = [
    "Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research",
]
_TAG_LOOKUP = {t.lower(): t for t in TAG_TAXONOMY}


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #

# Curated for credibility on agentic AI / LLM industry coverage.
RSS_SOURCES: list[tuple[str, str]] = [
    ("Simon Willison",            "https://simonwillison.net/atom/everything/"),
    ("Anthropic News",            "https://www.anthropic.com/rss.xml"),
    ("Hugging Face Blog",         "https://huggingface.co/blog/feed.xml"),
    ("Latent Space",              "https://www.latent.space/feed"),
    ("Techmeme",                  "https://www.techmeme.com/feed.xml"),
    ("Import AI (Jack Clark)",    "https://importai.substack.com/feed"),
    ("AI Snake Oil",              "https://www.aisnakeoil.com/feed"),
    ("One Useful Thing",          "https://www.oneusefulthing.org/feed"),
    ("Interconnects (Lambert)",   "https://www.interconnects.ai/feed"),
    ("The Pragmatic Engineer",    "https://newsletter.pragmaticengineer.com/feed"),
    ("arXiv cs.AI",               "https://rss.arxiv.org/rss/cs.AI"),
    ("Stratechery",               "https://stratechery.com/feed/"),
    ("Last Week in AI",           "https://lastweekin.ai/feed"),
    ("Dwarkesh Podcast",          "https://www.dwarkesh.com/feed"),
    ("NIST News",                 "https://www.nist.gov/news-events/news/rss.xml"),
    ("EU AI Office",              "https://digital-strategy.ec.europa.eu/en/rss.xml"),
]

# Keyword queries against the HN Algolia API (story tag, last week).
HN_QUERIES: list[str] = [
    "AI agents",
    "agentic",
    "LLM",
    "Claude",
    "Anthropic",
    "MCP",
    "AI regulation",
    "RAG",
    "eval",
    "fine-tuning",
]

# Weighted keywords used to score generic feed items.
KEYWORD_WEIGHTS: dict[int, list[str]] = {
    3: [
        "agentic", "ai agent", "autonomous agent", "tool use", "tool-use",
        "mcp", "model context protocol", "function calling", "computer use",
        "multi-agent",
    ],
    2: [
        "llm", "claude", "gpt-", "gemini", "anthropic", "openai", "deepmind",
        "foundation model", "frontier model", "rag ", "retrieval-augmented",
        "fine-tuning", "ai coding", "copilot", "cursor", "codex",
    ],
    1: [
        "regulation", "eu ai act", "compliance", "governance", "safety",
        "alignment", "enterprise ai", "evaluation", "benchmark", "open source",
        "open-source", "hallucination", "embedding", "vector",
        "product manager", "guardrails",
    ],
}


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #

@dataclass
class Item:
    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""
    score: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc.replace("www.", "")
        except Exception:
            return ""

    @property
    def age_hours(self) -> float:
        return (datetime.now(timezone.utc) - self.published).total_seconds() / 3600


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #

def _to_utc(struct_time) -> datetime:
    if not struct_time:
        return datetime.now(timezone.utc) - timedelta(days=30)
    return datetime.fromtimestamp(time.mktime(struct_time), tz=timezone.utc)


def fetch_rss(source: str, url: str, since: datetime) -> list[Item]:
    items: list[Item] = []
    try:
        parsed = feedparser.parse(url, request_headers={"User-Agent": "ContentFinder/1.0"})
    except Exception as exc:
        print(f"[warn] {source}: {exc}", file=sys.stderr)
        return items

    if parsed.bozo and not parsed.entries:
        print(f"[warn] {source}: feed parse error ({parsed.bozo_exception})", file=sys.stderr)
        return items

    for entry in parsed.entries:
        published = _to_utc(
            getattr(entry, "published_parsed", None)
            or getattr(entry, "updated_parsed", None)
        )
        if published < since:
            continue
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        summary_html = getattr(entry, "summary", "") or ""
        summary = re.sub(r"<[^>]+>", " ", summary_html)
        summary = re.sub(r"\s+", " ", summary).strip()
        items.append(Item(
            title=title,
            url=link,
            source=source,
            published=published,
            summary=summary[:500],
        ))
    return items


def fetch_hn(query: str, since: datetime, min_points: int = 50) -> list[Item]:
    """Hacker News stories matching a query, recent and with traction."""
    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": (
            f"created_at_i>{int(since.timestamp())},"
            f"points>={min_points}"
        ),
        "hitsPerPage": 20,
    }
    items: list[Item] = []
    try:
        r = httpx.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"[warn] HN '{query}': {exc}", file=sys.stderr)
        return items

    for hit in data.get("hits", []):
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        title = hit.get("title") or ""
        if not title:
            continue
        published = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
        items.append(Item(
            title=title,
            url=link,
            source=f"Hacker News",
            published=published,
            summary=f"{hit.get('points', 0)} points · {hit.get('num_comments', 0)} comments · query: {query}",
            extra={"points": hit.get("points", 0), "comments": hit.get("num_comments", 0)},
        ))
    return items


# --------------------------------------------------------------------------- #
# Scoring + dedupe
# --------------------------------------------------------------------------- #

def keyword_score(text: str) -> int:
    text_l = text.lower()
    score = 0
    for weight, terms in KEYWORD_WEIGHTS.items():
        for t in terms:
            if t in text_l:
                score += weight
    return score


def score_item(item: Item) -> float:
    body = f"{item.title} {item.summary}"
    base = keyword_score(body)

    # Recency bonus: fresher = higher.
    age_days = item.age_hours / 24
    recency = max(0.0, 7 - age_days) / 7  # 0..1

    # Source-credibility bonus.
    trusted = {
        "Simon Willison": 3,
        "Anthropic News": 3,
        "Import AI (Jack Clark)": 2,
        "Latent Space": 2,
        "AI Snake Oil": 2,
        "Interconnects (Lambert)": 2,
        "One Useful Thing": 2,
        "Stratechery": 2,
        "arXiv cs.AI": 2,
        "NIST News": 2,
        "EU AI Office": 2,
        "Dwarkesh Podcast": 2,
        "Techmeme": 1,
        "The Pragmatic Engineer": 1,
        "Hugging Face Blog": 1,
        "Last Week in AI": 1,
    }
    src_bonus = trusted.get(item.source, 0)

    # HN points contribute lightly (caps to avoid drowning the rest).
    hn_bonus = 0.0
    if item.source == "Hacker News":
        pts = item.extra.get("points", 0)
        hn_bonus = min(pts / 100.0, 4.0)

    return base + 2 * recency + src_bonus + hn_bonus


def dedupe(items: list[Item]) -> list[Item]:
    """Drop near-duplicate titles / same URLs across sources."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[Item] = []
    for it in sorted(items, key=lambda x: x.score, reverse=True):
        u = it.url.split("?")[0].rstrip("/")
        t_norm = re.sub(r"[^a-z0-9 ]+", "", it.title.lower()).strip()
        t_key = " ".join(t_norm.split()[:8])
        if u in seen_urls or (t_key and t_key in seen_titles):
            continue
        seen_urls.add(u)
        seen_titles.add(t_key)
        out.append(it)
    return out


def apply_source_cap(items: list[Item], max_per_source: int) -> list[Item]:
    """Keep at most `max_per_source` items per source, preferring higher scores.

    Why: a single hot day on arXiv or Simon Willison can otherwise crowd out
    the rest. Balancing per-source preserves diversity for the synthesis
    layer and the no-summarize ranked view alike.
    """
    if max_per_source <= 0:
        return items
    by_source: dict[str, int] = {}
    out: list[Item] = []
    for it in sorted(items, key=lambda x: x.score, reverse=True):
        cnt = by_source.get(it.source, 0)
        if cnt >= max_per_source:
            continue
        by_source[it.source] = cnt + 1
        out.append(it)
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def render_plain(items: list[Item], top_n: int) -> str:
    lines = [
        f"# Agentic AI Digest — {datetime.now().strftime('%Y-%m-%d')}",
        f"_{len(items)} items collected, top {min(top_n, len(items))} shown_",
        "",
    ]
    for it in items[:top_n]:
        age = f"{int(it.age_hours)}h ago" if it.age_hours < 48 else f"{int(it.age_hours / 24)}d ago"
        lines.append(f"## {it.title}")
        lines.append(f"_{it.source} · {it.domain} · {age} · score {it.score:.1f}_")
        if it.summary:
            lines.append("")
            lines.append(it.summary)
        lines.append("")
        lines.append(it.url)
        lines.append("")
    return "\n".join(lines)


HTML_CSS = """
:root {
  /* Backgrounds — Route A spec */
  --bg-0: #0a0a0d;
  --bg-1: #111116;
  --bg-2: #18181f;
  --bg-3: #202028;
  --bg-4: #28282f;
  --border: #22222c;
  --border-2: #2e2e3a;
  --fg: #e2e2ea;
  --fg-mid: #9a9ab0;
  --fg-dim: #606072;
  /* Purple — primary accent (hue 292) */
  --purple: oklch(65% 0.22 292);
  --purple-bright: oklch(72% 0.24 292);
  --purple-soft: oklch(65% 0.22 292 / 0.15);
  --purple-border: oklch(65% 0.22 292 / 0.35);
  --purple-dim: oklch(65% 0.22 292 / 0.08);
  /* Backwards-compat aliases — earlier code referred to --accent. */
  --accent: var(--purple);
  --accent-bg: var(--purple-soft);
  --accent-border: var(--purple-border);
  /* Secondary accents */
  --green: oklch(68% 0.13 145);
  --green-bg: oklch(68% 0.13 145 / 0.1);
  --amber: oklch(72% 0.13 75);
  --amber-bg: oklch(72% 0.13 75 / 0.1);
  --teal: oklch(68% 0.13 210);
  --teal-bg: oklch(68% 0.13 210 / 0.1);
  --slate: oklch(68% 0.12 260);
  --slate-bg: oklch(68% 0.12 260 / 0.1);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: var(--bg-0); color: var(--fg); }
body {
  font: 14px/1.55 "DM Sans", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  min-height: 100vh;
}
.page {
  max-width: 680px;
  margin: 0 auto;
  background: var(--bg-0);
  min-height: 100vh;
}

/* Top bar */
.topbar {
  background: var(--bg-0);
  border-bottom: 1px solid var(--border);
  padding: 16px 20px;
  display: flex; align-items: baseline; gap: 12px;
}
.topbar-left { display: flex; align-items: baseline; gap: 12px; }
.topbar-title { font-size: 16px; font-weight: 600; color: var(--fg); }
.topbar-date  { font-size: 13px; color: var(--fg-dim); }
.topbar-right {
  margin-left: auto; font-size: 12px; color: var(--fg-dim);
}
.topbar-right a { color: var(--fg-dim); text-decoration: none; }
.topbar-right a:hover { color: var(--fg-mid); }

/* Takeaways block */
.takeaways {
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
}
.takeaways-toggle {
  width: 100%; min-height: 44px;
  padding: 12px 20px;
  background: none; border: none; cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  font-family: inherit; text-align: left;
}
.takeaways-label {
  font-size: 11px; font-weight: 600;
  color: var(--purple);
  letter-spacing: 0.07em; text-transform: uppercase;
}
.takeaways-count {
  margin-left: 4px; font-size: 11px; color: var(--purple); opacity: 0.6;
}
.takeaways-chevron {
  margin-left: auto; font-size: 13px; color: var(--fg-dim);
  display: inline-block; transition: transform 0.15s;
}
.takeaways-toggle[aria-expanded="false"] .takeaways-chevron {
  transform: rotate(180deg);
}
.takeaways-body {
  padding: 4px 20px 18px;
  display: flex; flex-direction: column; gap: 16px;
}
.takeaways-body.is-collapsed { display: none; }
.takeaway {
  display: flex; gap: 10px; align-items: flex-start;
}
.takeaway-num {
  font-family: "DM Mono", monospace;
  font-size: 12px; font-weight: 700; color: var(--purple);
  min-width: 20px; padding-top: 3px; flex-shrink: 0;
}
.takeaway-content { flex: 1; min-width: 0; }
.takeaway-content p {
  font-size: 14px; color: var(--fg-mid); line-height: 1.65;
}
.takeaway-links {
  margin-top: 8px; display: flex; flex-direction: column; gap: 4px;
}
.takeaway-link-row {
  display: flex; align-items: center; gap: 6px;
  min-height: 28px;
  background: none; border: none; padding: 2px 6px;
  margin-left: -6px; margin-right: -6px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit; text-align: left;
  text-decoration: none;
  transition: background .12s, color .12s;
  width: 100%;
}
.takeaway-link-row:hover {
  background: var(--purple-dim);
}
.takeaway-link-tick {
  display: inline-block; width: 2px; height: 12px;
  background: var(--purple); border-radius: 1px; flex-shrink: 0;
  transition: background .12s;
}
.takeaway-link-row:hover .takeaway-link-tick {
  background: var(--purple-bright);
}
.takeaway-link-label {
  font-size: 12px; color: var(--purple);
  text-decoration: underline;
  text-decoration-color: var(--purple-border);
  text-underline-offset: 2px;
}
.takeaway-link-row:hover .takeaway-link-label {
  color: var(--purple-bright);
  text-decoration-color: var(--purple);
}
.takeaway-link-source {
  font-size: 11px; color: var(--fg-dim);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.takeaway-link-arrow {
  font-size: 11px; color: var(--fg-dim); margin-left: auto;
  transition: color .12s;
}
.takeaway-link-row:hover .takeaway-link-arrow {
  color: var(--purple-bright);
}

/* Filter chips */
.chips {
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
}
.chip {
  font-family: inherit; font-size: 12px; font-weight: 500;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: transparent;
  color: var(--fg-dim);
  cursor: pointer;
  white-space: nowrap;
  transition: color .12s, background .12s, border-color .12s;
}
.chip:hover { color: var(--fg); }
.chip.is-active { color: var(--fg); background: var(--bg-3); border-color: var(--border-2); }
.chip[data-tag="Models"].is-active     { color: var(--green);  background: var(--green-bg);  border-color: oklch(68% 0.13 145 / 0.4); }
.chip[data-tag="Agents"].is-active     { color: var(--purple); background: var(--purple-soft); border-color: var(--purple-border); }
.chip[data-tag="Tooling"].is-active    { color: var(--teal);   background: var(--teal-bg);   border-color: oklch(68% 0.13 210 / 0.4); }
.chip[data-tag="Regulation"].is-active { color: var(--amber);  background: var(--amber-bg);  border-color: oklch(72% 0.13 75 / 0.4); }
.chip[data-tag="Enterprise"].is-active { color: var(--purple); background: var(--purple-dim); border-color: var(--purple-border); }
.chip[data-tag="Research"].is-active   { color: var(--slate);  background: var(--slate-bg);  border-color: oklch(68% 0.12 260 / 0.4); }

/* Article list + section labels */
.article-list { padding-bottom: 24px; }
.section-label {
  padding: 14px 20px 6px;
  display: flex; align-items: center; gap: 10px;
  font-size: 11px; font-weight: 600;
  color: var(--purple);
  letter-spacing: 0.06em; text-transform: uppercase;
  border-bottom: 1px solid var(--border);
}
.section-label::after {
  content: ""; flex: 1; height: 1px; background: var(--border);
}

/* Item card */
.item {
  border-bottom: 1px solid var(--border);
  padding: 14px 20px;
  border-left: 3px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.item.is-expanded {
  border-left-color: var(--purple);
  background: var(--purple-dim);
}
.item .tags {
  display: flex; gap: 6px; flex-wrap: wrap;
  margin-bottom: 8px;
}
.tag {
  display: inline-block;
  font-size: 11px; font-weight: 500;
  padding: 2px 7px;
  border-radius: 4px;
  letter-spacing: 0.01em;
  border: 1px solid;
}
.tag-Models     { color: var(--green);  background: var(--green-bg);   border-color: oklch(68% 0.13 145 / 0.3); }
.tag-Agents     { color: var(--purple); background: oklch(65% 0.22 292 / 0.12); border-color: var(--purple-border); }
.tag-Tooling    { color: var(--teal);   background: var(--teal-bg);    border-color: oklch(68% 0.13 210 / 0.3); }
.tag-Regulation { color: var(--amber);  background: var(--amber-bg);   border-color: oklch(72% 0.13 75 / 0.3); }
.tag-Enterprise { color: var(--purple); background: var(--purple-dim); border-color: var(--purple-border); }
.tag-Research   { color: var(--slate);  background: var(--slate-bg);   border-color: oklch(68% 0.12 260 / 0.3); }

.item-title {
  display: block; width: 100%; min-height: 44px;
  background: none; border: none; padding: 0;
  margin-bottom: 8px;
  text-align: left; cursor: pointer;
  font-family: inherit; font-size: 15px; font-weight: 500;
  color: var(--fg); line-height: 1.45; text-wrap: pretty;
}
.item-title:hover { color: var(--purple); }
.item-body { display: none; margin-bottom: 12px; }
.item.is-expanded .item-body { display: block; }
.item-snippet {
  font-size: 14px; color: var(--fg-mid); line-height: 1.7;
  margin-bottom: 10px;
}

.so-what {
  background: var(--purple-soft);
  border: 1px solid var(--purple-border);
  border-radius: 5px;
  padding: 8px 11px;
}
.so-what-label { font-size: 12px; font-weight: 600; color: var(--purple); }
.so-what-body  { font-size: 12px; color: var(--fg-mid); line-height: 1.55; }

.item-actions {
  display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap;
}
.read-article {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; padding: 8px 16px; min-height: 40px;
  background: var(--purple-soft); border: 1px solid var(--purple-border);
  border-radius: 6px;
  color: var(--purple-bright); text-decoration: none;
  font-family: inherit;
}
.read-article:hover { background: var(--purple-dim); border-color: var(--purple-bright); }
.collapse-btn {
  display: inline-flex; align-items: center;
  font-size: 13px; padding: 8px 14px; min-height: 40px;
  background: none; border: 1px solid var(--border-2);
  border-radius: 6px; color: var(--fg-dim);
  cursor: pointer; font-family: inherit;
}
.collapse-btn:hover { color: var(--fg); border-color: var(--fg-mid); }

.item .meta {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  margin-top: 6px;
}
.item.is-expanded .meta { margin-top: 0; }
.item .meta .source { font-size: 13px; color: var(--fg-mid); }
.item .meta .date   { font-size: 13px; color: var(--fg-dim); }
.score-pill {
  font-family: "DM Mono", monospace;
  font-size: 11px;
  border: 1px solid; border-radius: 3px;
  padding: 1px 6px;
}
.score-pill.score-high { color: var(--green);  background: oklch(68% 0.13 145 / 0.18); border-color: oklch(68% 0.13 145 / 0.3); }
.score-pill.score-mid  { color: var(--purple); background: var(--purple-soft);          border-color: var(--purple-border); }
.score-pill.score-low  { color: var(--fg-dim); background: rgba(255,255,255,0.05);     border-color: rgba(255,255,255,0.18); }

footer {
  padding: 24px 20px; text-align: center;
  font-size: 12px; color: var(--fg-dim);
  border-top: 1px solid var(--border);
}
footer a { color: var(--fg-dim); }

.is-hidden { display: none !important; }
"""


# --------------------------------------------------------------------------- #
# Tag post-processing + chip filter
# --------------------------------------------------------------------------- #

_TAG_ELEMENT_RE = re.compile(
    r'^(<li([^>]*)>)(.*?)(</li>)\s*$',
    re.DOTALL,
)
_TAG_SUFFIX_RE = re.compile(r'\s*\{tags:\s*([^}]*)\}\s*$')
_BODY_LI_RE = re.compile(r'<li\b[^>]*>.*?</li>', re.DOTALL)


def _canonicalize_tags(raw: str) -> list[str]:
    """Normalise a comma-separated tag list to canonical taxonomy casing."""
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        key = part.strip().lower()
        if not key:
            continue
        canonical = _TAG_LOOKUP.get(key)
        if canonical and canonical not in seen:
            out.append(canonical)
            seen.add(canonical)
    return out


def transform_tag_element(snippet: str) -> tuple[str, set[str]]:
    """Strip a `{tags: …}` suffix from a single `<li>` and attach `data-tags`.

    Returns the rewritten element and the set of canonical tags found.
    """
    m = _TAG_ELEMENT_RE.match(snippet)
    if not m:
        return snippet, set()
    _open, attrs, content, close = m.groups()
    suffix = _TAG_SUFFIX_RE.search(content)
    if suffix:
        tag_list = _canonicalize_tags(suffix.group(1))
        content = content[: suffix.start()].rstrip()
    else:
        tag_list = []
    new_open = f'<li{attrs} data-tags="{" ".join(tag_list)}">'
    return new_open + content + close, set(tag_list)


def _process_tags_in_body(body_html: str) -> tuple[str, set[str]]:
    seen: set[str] = set()

    def repl(m: re.Match) -> str:
        new, tags = transform_tag_element(m.group(0))
        seen.update(tags)
        return new

    return _BODY_LI_RE.sub(repl, body_html), seen


def render_chip_bar() -> str:
    parts = ['<div class="chips" role="tablist">']
    parts.append(
        '<button type="button" class="chip is-active" data-tag="all">All</button>'
    )
    for tag in TAG_TAXONOMY:
        parts.append(
            f'<button type="button" class="chip" data-tag="{tag}">{tag}</button>'
        )
    parts.append("</div>")
    return "\n".join(parts)


INTERACTIONS_JS = """
<script>
(function () {
  // Topic filter chips
  var chips = document.querySelectorAll('.chip');
  function applyFilter(tag) {
    chips.forEach(function (c) {
      c.classList.toggle('is-active', c.dataset.tag === tag);
    });
    document.querySelectorAll('[data-tags]').forEach(function (el) {
      var tags = (el.dataset.tags || '').split(' ').filter(Boolean);
      // Untagged items (e.g. Key takeaways bullets) stay visible under
      // every filter — they're synthesis, not topic-scoped.
      var show = tag === 'all' || tags.length === 0 || tags.indexOf(tag) !== -1;
      el.classList.toggle('is-hidden', !show);
    });
  }
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      applyFilter(chip.dataset.tag);
    });
  });

  // Item expand/collapse on title click
  document.querySelectorAll('.item-title').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('.item');
      if (item) item.classList.toggle('is-expanded');
    });
  });

  // Item explicit collapse button
  document.querySelectorAll('.collapse-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('.item');
      if (item) item.classList.remove('is-expanded');
    });
  });

  // Takeaways collapsible
  var takeawaysToggle = document.querySelector('.takeaways-toggle');
  var takeawaysBody = document.querySelector('.takeaways-body');
  function setTakeawaysCollapsed(collapsed) {
    if (!takeawaysBody || !takeawaysToggle) return;
    takeawaysBody.classList.toggle('is-collapsed', collapsed);
    takeawaysToggle.setAttribute('aria-expanded', String(!collapsed));
    var chev = takeawaysToggle.querySelector('.takeaways-chevron');
    if (chev) chev.textContent = collapsed ? '▼' : '▲';
  }
  if (takeawaysToggle) {
    takeawaysToggle.addEventListener('click', function () {
      setTakeawaysCollapsed(!takeawaysBody.classList.contains('is-collapsed'));
    });
  }

  // Takeaway → article link navigation (Route A spec §4 + §10).
  // Each link row carries data-item-url; we look up the matching .item by its
  // .read-article href, expand it, clear the filter, collapse takeaways and
  // scroll into view.
  function navigateToItem(itemUrl) {
    if (!itemUrl) return;
    var matchLink = document.querySelector(
      '.item .read-article[href="' + itemUrl.replace(/"/g, '\\\\"') + '"]'
    );
    var item = matchLink ? matchLink.closest('.item') : null;
    if (!item) {
      // Fallback: open the source URL in a new tab if no in-page card matches.
      window.open(itemUrl, '_blank', 'noopener');
      return;
    }
    applyFilter('all');
    document.querySelectorAll('.item.is-expanded').forEach(function (el) {
      if (el !== item) el.classList.remove('is-expanded');
    });
    item.classList.add('is-expanded');
    setTakeawaysCollapsed(true);
    setTimeout(function () {
      item.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  }
  // Expose for inline onclicks if ever needed; primary path is event listener.
  window.navigateToItem = navigateToItem;
  document.querySelectorAll('.takeaway-link-row').forEach(function (btn) {
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      navigateToItem(btn.dataset.itemUrl);
    });
  });
})();
</script>
"""

# Backwards-compat alias for any external imports.
CHIP_FILTER_JS = INTERACTIONS_JS


# --------------------------------------------------------------------------- #
# Card rendering helpers
# --------------------------------------------------------------------------- #

# Display labels for synthesis section headings (per design handoff).
_SECTION_LABELS = {
    "key takeaways": "Key Takeaways",
    "top story": "Top Story",
    "models & capability releases": "Models & Capabilities",
    "agentic engineering & tooling": "Agentic Engineering",
    "enterprise, regulation & governance": "Enterprise & Regulation",
    "worth a deeper read": "Worth a Deeper Read",
}


def _section_display_label(raw: str) -> str:
    # The raw heading text comes from a regex-stripped <h2>, so HTML entities
    # are still entity-encoded (e.g. "Models &amp; capability releases"). The
    # taxonomy map keys on plain text, so decode before lookup.
    decoded = html.unescape(raw).strip()
    return _SECTION_LABELS.get(decoded.lower(), decoded)


def _score_tier(score: float) -> str:
    if score >= 8.5:
        return "high"
    if score >= 7.0:
        return "mid"
    return "low"


def _format_age(age_hours: float) -> str:
    return (
        f"{int(age_hours)}h ago" if age_hours < 48
        else f"{int(age_hours / 24)}d ago"
    )


def _render_tag_chips(data_tags: str) -> str:
    if not data_tags:
        return ""
    chips = "".join(
        f'<span class="tag tag-{html.escape(t)}">{html.escape(t)}</span>'
        for t in data_tags.split() if t
    )
    return f'<div class="tags">{chips}</div>' if chips else ""


_LI_OUTER_RE = re.compile(r'<li([^>]*)>(.*)</li>', re.DOTALL)
_LI_TITLE_RE = re.compile(r'\s*<strong>(.*?)</strong>\s*[—–-]?\s*', re.DOTALL)
_LI_SO_WHAT_RE = re.compile(r'<strong>\s*So what:?\s*</strong>\s*', re.IGNORECASE)
_LI_LINK_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)


def _parse_synthesis_li(li_html: str, item_id: int) -> str:
    """Convert a `<li>` carrying a structured synthesis bullet into a card."""
    outer = _LI_OUTER_RE.match(li_html)
    if not outer:
        return li_html
    attrs, content = outer.group(1), outer.group(2)
    data_tags_match = re.search(r'data-tags="([^"]*)"', attrs)
    data_tags = data_tags_match.group(1) if data_tags_match else ""

    title_m = _LI_TITLE_RE.match(content)
    if not title_m:
        # Bullet doesn't follow the **Headline** — body. shape; render as
        # a minimal card so the filter still works on it.
        body_clean = re.sub(r'<[^>]+>', '', content).strip()
        return (
            f'<article class="item" data-tags="{html.escape(data_tags)}" '
            f'id="item-{item_id}">'
            f'{_render_tag_chips(data_tags)}'
            f'<button type="button" class="item-title">{html.escape(body_clean)}</button>'
            f'</article>'
        )

    title = title_m.group(1).strip()
    rest = content[title_m.end():]

    sw_m = _LI_SO_WHAT_RE.search(rest)
    if sw_m:
        snippet = rest[:sw_m.start()].rstrip(" .").rstrip()
        after_sw = rest[sw_m.end():]
    else:
        snippet = rest.strip()
        after_sw = ""

    link_m = _LI_LINK_RE.search(after_sw)
    if link_m:
        url = link_m.group(1)
        source_name = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
        so_what = after_sw[:link_m.start()].rstrip(" .").rstrip()
    else:
        url = ""
        source_name = ""
        so_what = after_sw.rstrip(" .").rstrip()

    snippet = snippet.strip()
    so_what = so_what.strip()

    parts = [
        f'<article class="item" data-tags="{html.escape(data_tags)}" '
        f'id="item-{item_id}">',
        _render_tag_chips(data_tags),
        f'<button type="button" class="item-title">{title}</button>',
        '<div class="item-body">',
    ]
    if snippet:
        parts.append(f'<p class="item-snippet">{snippet}</p>')
    if so_what:
        parts.append(
            '<div class="so-what">'
            '<span class="so-what-label">So what:</span> '
            f'<span class="so-what-body">{so_what}</span>'
            '</div>'
        )
    parts.append('<div class="item-actions">')
    if url:
        parts.append(
            f'<a class="read-article" href="{html.escape(url)}" '
            f'target="_blank" rel="noopener">Read article →</a>'
        )
    parts.append(
        '<button type="button" class="collapse-btn">Collapse</button>'
    )
    parts.append('</div>')
    parts.append('</div>')
    if source_name:
        parts.append(
            '<div class="meta">'
            f'<span class="source">{html.escape(source_name)}</span>'
            '</div>'
        )
    parts.append('</article>')
    return "".join(parts)


_H2_RE = re.compile(r'<h2[^>]*>(.*?)</h2>', re.DOTALL)
_BODY_LI_OUTER_RE = re.compile(r'<li[^>]*>.*?</li>', re.DOTALL)


def _split_synthesis_sections(body_html: str) -> list[tuple[str, str]]:
    """Slice the body HTML into [(section_title, section_inner_html), …]."""
    matches = list(_H2_RE.finditer(body_html))
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body_html)
        sections.append((title, body_html[start:end]))
    return sections


_LI_LINK_ITER_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)


def _extract_takeaways(
    body_html: str,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Pull the Key Takeaways section out of the body.

    Returns (takeaways, remaining_sections). Each takeaway is::

        {"text": "...", "links": [{"href": ..., "label": ...}, ...]}
    """
    sections = _split_synthesis_sections(body_html)
    takeaways: list[dict] = []
    rest: list[tuple[str, str]] = []
    for title, content in sections:
        if title.strip().lower() == "key takeaways":
            for li in _BODY_LI_OUTER_RE.finditer(content):
                inner = re.sub(r'^<li[^>]*>', '', li.group(0))
                inner = re.sub(r'</li>\s*$', '', inner)
                links: list[dict] = []
                for link_m in _LI_LINK_ITER_RE.finditer(inner):
                    label = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
                    if not label:
                        continue
                    links.append({"href": link_m.group(1), "label": label})
                text_html = _LI_LINK_ITER_RE.sub('', inner)
                text = re.sub(r'<[^>]+>', '', text_html).strip().rstrip(" .")
                takeaways.append({"text": text, "links": links})
        else:
            rest.append((title, content))
    return takeaways, rest


def _build_url_to_source_map(
    rest_sections: list[tuple[str, str]],
) -> dict[str, str]:
    """Pre-scan rendered sections to map source-URLs back to display source names.

    Used so each takeaway link row can show the publication name
    ("Anthropic Blog", "Latent Space") next to the underlined label, per
    Route A spec §4.
    """
    url_to_source: dict[str, str] = {}
    for _title, content in rest_sections:
        for li_m in _BODY_LI_OUTER_RE.finditer(content):
            link_m = _LI_LINK_RE.search(li_m.group(0))
            if not link_m:
                continue
            url = link_m.group(1)
            source = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
            if url and source and url not in url_to_source:
                url_to_source[url] = source
    return url_to_source


def _domain_label(url: str) -> str:
    try:
        host = urlparse(url).netloc.replace("www.", "")
        return host or url
    except Exception:
        return url


def render_takeaways_section(
    takeaways: list[dict],
    url_to_source: dict[str, str] | None = None,
) -> str:
    """Render the collapsible Key Takeaways panel.

    Each takeaway carries a ``links`` list (per ``_extract_takeaways``); for
    backwards compatibility a single ``href``/``label`` pair is also accepted.
    Link rows render as ``<button class="takeaway-link-row" data-item-url>``
    so the page JS can navigate to the matching feed item (Route A spec §4).
    """
    if not takeaways:
        return ""
    url_to_source = url_to_source or {}
    parts = [
        '<section class="takeaways">',
        '<button type="button" class="takeaways-toggle" '
        'aria-expanded="true" aria-controls="takeaways-body">',
        '<span class="takeaways-label">Key Takeaways</span>',
        f'<span class="takeaways-count">{len(takeaways)}</span>',
        '<span class="takeaways-chevron">▲</span>',
        '</button>',
        '<div class="takeaways-body" id="takeaways-body">',
    ]
    for i, t in enumerate(takeaways, 1):
        parts.append('<div class="takeaway">')
        parts.append(f'<span class="takeaway-num">{i}.</span>')
        parts.append('<div class="takeaway-content">')
        parts.append(f'<p>{html.escape(t["text"])}</p>')

        # Normalise: support both new (`links: [...]`) and legacy
        # (`href`/`label`) shapes so callers stay backward-compatible.
        link_items = list(t.get("links") or [])
        if not link_items and t.get("href"):
            link_items = [{"href": t["href"], "label": t.get("label") or "Source"}]

        if link_items:
            parts.append('<div class="takeaway-links">')
            for lnk in link_items:
                href = lnk.get("href") or ""
                label = lnk.get("label") or "Source"
                source = url_to_source.get(href) or _domain_label(href)
                parts.append(
                    '<button type="button" class="takeaway-link-row" '
                    f'data-item-url="{html.escape(href)}">'
                    '<span class="takeaway-link-tick" aria-hidden="true"></span>'
                    f'<span class="takeaway-link-label">{html.escape(label)}</span>'
                    f'<span class="takeaway-link-source">{html.escape(source)}</span>'
                    '<span class="takeaway-link-arrow" aria-hidden="true">↓</span>'
                    '</button>'
                )
            parts.append('</div>')
        parts.append('</div>')
        parts.append('</div>')
    parts.append('</div>')
    parts.append('</section>')
    return "".join(parts)


def _render_synthesis_sections(rest_sections: list[tuple[str, str]]) -> tuple[str, int]:
    parts: list[str] = ['<div class="article-list">']
    item_id = 0
    for title, content in rest_sections:
        label = _section_display_label(title)
        parts.append(f'<div class="section-label">{html.escape(label)}</div>')
        for li_m in _BODY_LI_OUTER_RE.finditer(content):
            item_id += 1
            parts.append(_parse_synthesis_li(li_m.group(0), item_id))
    parts.append('</div>')
    return "".join(parts), item_id


def _render_ranked_card(item: Item, item_id: int) -> str:
    age = _format_age(item.age_hours)
    tier = _score_tier(item.score)
    parts = [
        f'<article class="item" id="item-{item_id}">',
        f'<button type="button" class="item-title">{html.escape(item.title)}</button>',
        '<div class="item-body">',
    ]
    if item.summary:
        parts.append(f'<p class="item-snippet">{html.escape(item.summary)}</p>')
    parts.append('<div class="item-actions">')
    parts.append(
        f'<a class="read-article" href="{html.escape(item.url)}" '
        f'target="_blank" rel="noopener">Read article →</a>'
    )
    parts.append(
        '<button type="button" class="collapse-btn">Collapse</button>'
    )
    parts.append('</div>')
    parts.append('</div>')
    parts.append('<div class="meta">')
    parts.append(f'<span class="source">{html.escape(item.source)}</span>')
    parts.append(f'<span class="date">{age}</span>')
    parts.append(
        f'<span class="score-pill score-{tier}">{item.score:.1f}</span>'
    )
    parts.append('</div>')
    parts.append('</article>')
    return "".join(parts)


def _page_shell(
    page_date: date,
    item_count: int,
    *,
    takeaways_html: str = "",
    body_html: str = "",
    sub_label: str | None = None,
) -> str:
    title = f"AI Digest — {page_date.strftime('%a %d %b %Y')}"
    short_date = page_date.strftime("%a %d %b %Y")
    return "\n".join([
        "<!doctype html>",
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="theme-color" content="#0a0a0d">',
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><text y=\'.9em\' font-size=\'90\'>📡</text></svg>">',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link href="https://fonts.googleapis.com/css2?'
        'family=DM+Sans:wght@300;400;500;600&'
        'family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{HTML_CSS}</style>",
        "</head><body>",
        '<div class="page">',
        '<header class="topbar">',
        '<div class="topbar-left">',
        '<span class="topbar-title">AI Digest</span>',
        f'<span class="topbar-date">{html.escape(short_date)}</span>',
        '</div>',
        f'<div class="topbar-right">{item_count} items '
        '· <a href="archive.html">archive</a></div>',
        "</header>",
        takeaways_html or "",
        render_chip_bar(),
        body_html,
        '<footer>Generated by '
        '<a href="https://github.com/raidianblaster/Content-Finder">'
        "Content Finder</a></footer>",
        "</div>",
        INTERACTIONS_JS,
        "</body></html>",
    ])


def render_html(items: list[Item], top_n: int, *, page_date: date | None = None) -> str:
    """No-summarize ranked list, rendered with the Variant A card layout."""
    page_date = page_date or today_hkt()
    shown = items[:top_n]
    body_parts = ['<div class="article-list">']
    for i, it in enumerate(shown, 1):
        body_parts.append(_render_ranked_card(it, i))
    body_parts.append('</div>')
    return _page_shell(
        page_date,
        item_count=len(shown),
        takeaways_html="",
        body_html="".join(body_parts),
    )


SYSTEM_PROMPT = """You are a research analyst writing a daily news brief for an
AI Product Manager who works in a large, highly regulated corporation. They
have limited access to bleeding-edge models and tools, so they rely on this
brief to track industry trends and decide what to watch.

Given a list of articles (titles, sources, URLs, snippets), produce a concise
markdown brief structured exactly as below:

## Key takeaways

3 bullets at the very top of the brief, before any other section. Each bullet
is 1–2 sentences. Each takeaway should synthesise across multiple stories —
not just summarise a single one — answering "what does today's news mean for
an AI PM?". This block sits ABOVE every other section.

After the synthesis text, EACH takeaway bullet MUST end with one or two inline
markdown links pointing at the source article(s) the synthesis is drawn from.
Use the EXACT same article URL that appears in the bullet below (so the UI
can scroll the reader to that card). The label should be a short 2–5 word
hook, not the full headline. Format:

  - Synthesis text in 1–2 sentences. [Short hook](https://exact-source-url) [Other hook](https://other-url)

Two links per takeaway when the takeaway spans multiple stories; otherwise one.

## Top story
- **Headline** — 2 sentences on what happened today and the context around
  it. **So what:** 1–2 sentences on the strategic implication for an AI PM
  in a regulated environment. [Source](url) {tags: <Tag1>, <Tag2>}

## Models & capability releases
- bullets in the same shape as Top story (model launches, capability changes).

## Agentic engineering & tooling
- bullets in the same shape (agents, frameworks, MCP, dev tools).

## Enterprise, regulation & governance
- bullets in the same shape (adoption, policy, safety, risk).

## Worth a deeper read
- 2–4 longform / analysis pieces, same bullet shape.

Per-bullet rules:
- Every bullet (including Top story) ends with a `{tags: …}` suffix listing
  1–3 tags drawn ONLY from this fixed taxonomy:
  Models, Agents, Tooling, Regulation, Enterprise, Research.
- Every story bullet (every section after Key takeaways) must include a
  bolded **So what:** clause naming the PM-level implication.
- Each bullet shape: "**Headline** — what happened. **So what:** why it
  matters [Source](url) {tags: …}".

Brief-wide rules:
- Skip any section that has no relevant items — do not pad.
- Drop low-signal items (vendor fluff, rumours, duplicates).
- Prefer named primary sources over aggregators when both appear.
- No preamble, no closing remarks. Markdown only.
"""


def synthesize_with_claude(items: list[Item], model: str) -> str:
    try:
        from anthropic import Anthropic
    except ImportError:
        print("[warn] anthropic SDK not installed; falling back to plain output",
              file=sys.stderr)
        return render_plain(items, top_n=25)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[warn] ANTHROPIC_API_KEY not set; falling back to plain output",
              file=sys.stderr)
        return render_plain(items, top_n=25)

    payload_lines = []
    for it in items[:40]:
        age = f"{int(it.age_hours)}h" if it.age_hours < 48 else f"{int(it.age_hours / 24)}d"
        payload_lines.append(
            f"- [{it.source} · {age}] {it.title}\n  {it.url}\n  {it.summary}"
        )
    user_msg = "Articles:\n\n" + "\n".join(payload_lines)

    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.content[0].text


def wrap_synthesis_html(md_text: str, *, page_date: date | None = None) -> str:
    """Render a Claude-synthesised brief in the Variant A card layout."""
    import markdown as md_lib
    page_date = page_date or today_hkt()

    body_html = md_lib.markdown(md_text, extensions=["extra"])
    body_html, _seen_tags = _process_tags_in_body(body_html)

    takeaways, rest = _extract_takeaways(body_html)
    url_to_source = _build_url_to_source_map(rest)
    takeaways_html = render_takeaways_section(takeaways, url_to_source)
    items_html, item_count = _render_synthesis_sections(rest)

    return _page_shell(
        page_date,
        item_count=item_count,
        takeaways_html=takeaways_html,
        body_html=items_html,
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def gather(days: int, hn_min_points: int, max_per_source: int = 3) -> list[Item]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    items: list[Item] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for src, url in RSS_SOURCES:
            futures.append(pool.submit(fetch_rss, src, url, since))
        for q in HN_QUERIES:
            futures.append(pool.submit(fetch_hn, q, since, hn_min_points))
        for fut in as_completed(futures):
            try:
                items.extend(fut.result())
            except Exception as exc:
                print(f"[warn] fetcher failed: {exc}", file=sys.stderr)

    for it in items:
        it.score = score_item(it)

    # Drop items with no keyword signal (pure noise).
    items = [it for it in items if keyword_score(f"{it.title} {it.summary}") > 0]
    return apply_source_cap(dedupe(items), max_per_source=max_per_source)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic AI news digest CLI")
    parser.add_argument("--days", type=int, default=2,
                        help="Look-back window in days (default 2)")
    parser.add_argument("--top", type=int, default=25,
                        help="Number of items in plain output (default 25)")
    parser.add_argument("--hn-min-points", type=int, default=50,
                        help="HN minimum points threshold (default 50)")
    parser.add_argument("--max-per-source", type=int, default=3,
                        help="Cap items per source for diversity (default 3, "
                             "0 disables)")
    parser.add_argument("--no-summarize", action="store_true",
                        help="Skip Claude synthesis, dump ranked list")
    parser.add_argument("--format", choices=["markdown", "html"], default="markdown",
                        help="Output format for non-summarised mode (default markdown)")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="Anthropic model id for synthesis")
    parser.add_argument("--out", default="-",
                        help="Output path or '-' for stdout (default '-')")
    args = parser.parse_args()

    print(f"[info] gathering last {args.days}d from "
          f"{len(RSS_SOURCES)} feeds + {len(HN_QUERIES)} HN queries...",
          file=sys.stderr)

    items = gather(args.days, args.hn_min_points, max_per_source=args.max_per_source)
    print(f"[info] {len(items)} relevant items after filtering", file=sys.stderr)

    if not items:
        print("No relevant items found in window. Try --days 7.", file=sys.stderr)
        return 1

    page_date = today_hkt()

    if args.no_summarize:
        if args.format == "html":
            output = render_html(items, top_n=args.top, page_date=page_date)
        else:
            output = render_plain(items, top_n=args.top)
    else:
        md_output = synthesize_with_claude(items, model=args.model)
        if args.format == "html":
            output = wrap_synthesis_html(md_output, page_date=page_date)
        else:
            output = md_output

    if args.out == "-":
        print(output)
    else:
        with open(args.out, "w") as f:
            f.write(output)
        print(f"[info] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
