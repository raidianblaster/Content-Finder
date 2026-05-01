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
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlparse

import feedparser
import httpx


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
        "Techmeme": 1,
        "The Pragmatic Engineer": 1,
        "Hugging Face Blog": 1,
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
  --bg: #fafafa; --fg: #1a1a1a; --muted: #666;
  --accent: #0066cc; --border: #e0e0e0; --card: #fff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f0f10; --fg: #e8e8e8; --muted: #9a9a9a;
    --accent: #7aa2ff; --border: #232325; --card: #18181a;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--fg);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  max-width: 720px; margin: 0 auto; padding: 1.5rem 1rem 4rem;
}
header { margin-bottom: 1.5rem; }
header h1 { margin: 0 0 .25rem; font-size: 1.4rem; line-height: 1.25; }
header .meta { color: var(--muted); font-size: .9rem; }
header nav { margin-top: .75rem; font-size: .9rem; }
header nav a { color: var(--accent); text-decoration: none; margin-right: 1rem; }
article {
  border-top: 1px solid var(--border);
  padding: 1.1rem 0;
}
article h2 {
  margin: 0 0 .35rem; font-size: 1.05rem; line-height: 1.35;
}
article h2 a { color: var(--fg); text-decoration: none; }
article h2 a:hover { color: var(--accent); }
article .meta { color: var(--muted); font-size: .82rem; margin-bottom: .55rem; }
article .summary { font-size: .94rem; color: var(--fg); }
article .read-more {
  display: inline-block; margin-top: .55rem;
  font-size: .82rem; color: var(--accent); text-decoration: none;
}
.score-pill {
  display: inline-block; padding: 0 .4rem; border-radius: 3px;
  background: var(--border); color: var(--muted); font-size: .75rem;
}
footer {
  margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
  color: var(--muted); font-size: .78rem; text-align: center;
}
footer a { color: var(--muted); }
"""


def render_html(items: list[Item], top_n: int, *, page_date: datetime | None = None) -> str:
    page_date = page_date or datetime.now()
    title = f"AI Digest — {page_date.strftime('%a %d %b %Y')}"
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="theme-color" content="#0f0f10">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{HTML_CSS}</style>",
        "</head><body>",
        "<header>",
        f"<h1>{html.escape(title)}</h1>",
        f'<div class="meta">{len(items)} items · top {min(top_n, len(items))} shown · agentic AI &amp; LLM trends</div>',
        '<nav><a href="archive.html">← previous digests</a></nav>',
        "</header>",
    ]
    for it in items[:top_n]:
        age = f"{int(it.age_hours)}h ago" if it.age_hours < 48 else f"{int(it.age_hours / 24)}d ago"
        parts.append("<article>")
        parts.append(
            f'<h2><a href="{html.escape(it.url)}" rel="noopener" target="_blank">'
            f"{html.escape(it.title)}</a></h2>"
        )
        parts.append(
            f'<div class="meta">{html.escape(it.source)} · '
            f"{html.escape(it.domain)} · {age} · "
            f'<span class="score-pill">score {it.score:.1f}</span></div>'
        )
        if it.summary:
            parts.append(f'<div class="summary">{html.escape(it.summary)}</div>')
        parts.append(
            f'<a class="read-more" href="{html.escape(it.url)}" '
            f'rel="noopener" target="_blank">Read on {html.escape(it.domain)} →</a>'
        )
        parts.append("</article>")
    parts.append(
        '<footer>Generated by <a href="https://github.com/raidianblaster/Content-Finder">'
        "Content Finder</a></footer></body></html>"
    )
    return "\n".join(parts)


SYSTEM_PROMPT = """You are a research analyst writing a daily news brief for an
AI Product Manager who works in a large, highly regulated corporation. They
have limited access to bleeding-edge models and tools, so they rely on this
brief to track industry trends.

Given a list of articles (titles, sources, URLs, snippets), produce a concise
markdown digest with these sections, in this order:

1. **Top story** — the single most important development today, 2–3 sentences
   on what happened and why it matters for an AI PM.
2. **Models & capability releases** — bullets, one line each, link inline.
3. **Agentic engineering & tooling** — agents, frameworks, MCP, dev tools.
4. **Enterprise, regulation & governance** — adoption, policy, safety, risk.
5. **Worth a deeper read** — 2–4 longform / analysis pieces.

Rules:
- Skip any section that has no relevant items rather than padding.
- Each bullet: "**Headline** — one-sentence why-it-matters [Source](url)".
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


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def gather(days: int, hn_min_points: int) -> list[Item]:
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
    return dedupe(items)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic AI news digest CLI")
    parser.add_argument("--days", type=int, default=2,
                        help="Look-back window in days (default 2)")
    parser.add_argument("--top", type=int, default=25,
                        help="Number of items in plain output (default 25)")
    parser.add_argument("--hn-min-points", type=int, default=50,
                        help="HN minimum points threshold (default 50)")
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

    items = gather(args.days, args.hn_min_points)
    print(f"[info] {len(items)} relevant items after filtering", file=sys.stderr)

    if not items:
        print("No relevant items found in window. Try --days 7.", file=sys.stderr)
        return 1

    if args.no_summarize:
        if args.format == "html":
            output = render_html(items, top_n=args.top)
        else:
            output = render_plain(items, top_n=args.top)
    else:
        output = synthesize_with_claude(items, model=args.model)

    if args.out == "-":
        print(output)
    else:
        with open(args.out, "w") as f:
            f.write(output)
        print(f"[info] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
