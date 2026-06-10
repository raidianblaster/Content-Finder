#!/usr/bin/env python3
"""Content Finder — credible agentic-AI news digest for AI product managers.

Pulls from a curated set of RSS feeds plus Hacker News, scores items for
relevance to agentic engineering / LLM industry trends, and prints a digest
to stdout (optionally synthesised by Claude into a themed brief).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import feedparser
import httpx
import yaml


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
# Source configuration — loaded from sources.yml
# --------------------------------------------------------------------------- #

@dataclass
class SourceConfig:
    rss_sources: list[tuple[str, str]]    # (name, url)
    hn_queries: list[str]
    keyword_weights: dict[int, list[str]]
    trusted_weights: dict[str, int]        # source_name → credibility bonus


def load_sources(path: "Path | None" = None) -> SourceConfig:
    """Load and validate sources.yml.  Raises FileNotFoundError or ValueError on bad input."""
    from pathlib import Path as _Path

    if path is None:
        path = _Path(__file__).resolve().parent / "sources.yml"

    path = _Path(path)
    if not path.exists():
        raise FileNotFoundError(f"sources.yml not found at {path}")

    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    # --- required top-level keys ---
    for key in ("rss_sources", "hn_queries", "keyword_weights"):
        if key not in raw:
            raise ValueError(f"sources.yml missing required key: '{key}'")

    # --- rss_sources ---
    rss_raw = raw["rss_sources"]
    if not isinstance(rss_raw, list) or len(rss_raw) == 0:
        raise ValueError("rss_sources must be a non-empty list")

    rss_sources: list[tuple[str, str]] = []
    trusted_weights: dict[str, int] = {}
    seen_names: set[str] = set()

    for i, entry in enumerate(rss_raw):
        if not isinstance(entry, dict):
            raise ValueError(f"rss_sources[{i}] must be a mapping, got {type(entry).__name__}")
        if "name" not in entry:
            raise ValueError(f"rss_sources[{i}] missing required field 'name'")
        if "url" not in entry:
            raise ValueError(f"rss_sources[{i}] missing required field 'url'")

        name = str(entry["name"]).strip()
        url = str(entry["url"]).strip()
        trust = int(entry.get("trust", 0))

        if not name:
            raise ValueError(f"rss_sources[{i}] 'name' must not be empty")
        if name in seen_names:
            raise ValueError(f"Duplicate source name in rss_sources: {name!r}")
        if not url.startswith("https://"):
            raise ValueError(
                f"rss_sources entry {name!r} url must start with https://, got {url!r}"
            )
        if not (0 <= trust <= 5):
            raise ValueError(
                f"rss_sources entry {name!r} trust={trust} is out of range 0-5"
            )

        seen_names.add(name)
        rss_sources.append((name, url))
        if trust > 0:
            trusted_weights[name] = trust

    # --- hn_queries ---
    hn_raw = raw["hn_queries"]
    if not isinstance(hn_raw, list) or len(hn_raw) == 0:
        raise ValueError("hn_queries must be a non-empty list")
    hn_queries: list[str] = []
    for i, q in enumerate(hn_raw):
        if not isinstance(q, str) or not q.strip():
            raise ValueError(f"hn_queries[{i}] must be a non-empty string, got {q!r}")
        hn_queries.append(q)

    # --- keyword_weights ---
    kw_raw = raw["keyword_weights"]
    if not isinstance(kw_raw, dict) or len(kw_raw) == 0:
        raise ValueError("keyword_weights must be a non-empty mapping")
    keyword_weights: dict[int, list[str]] = {}
    for k, terms in kw_raw.items():
        if not isinstance(k, int) or k <= 0:
            raise ValueError(
                f"keyword_weights key must be a positive integer, got {k!r}"
            )
        if not isinstance(terms, list):
            raise ValueError(f"keyword_weights[{k}] must be a list, got {type(terms).__name__}")
        keyword_weights[k] = [str(t) for t in terms]

    return SourceConfig(
        rss_sources=rss_sources,
        hn_queries=hn_queries,
        keyword_weights=keyword_weights,
        trusted_weights=trusted_weights,
    )


# Load once at import time so module-level constants stay backward-compatible.
_SOURCE_CFG: SourceConfig = load_sources()

RSS_SOURCES: list[tuple[str, str]] = _SOURCE_CFG.rss_sources
HN_QUERIES: list[str] = _SOURCE_CFG.hn_queries
KEYWORD_WEIGHTS: dict[int, list[str]] = _SOURCE_CFG.keyword_weights
_TRUSTED_WEIGHTS: dict[str, int] = _SOURCE_CFG.trusted_weights


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
    first_seen: "date | None" = None

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
# Derived fields for the V2 masthead
# --------------------------------------------------------------------------- #

_ARCHIVE_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.html$")


def count_archived_issues(archive_dir: "Path | str") -> int:
    p = Path(archive_dir)
    if not p.is_dir():
        return 0
    return sum(1 for entry in p.iterdir() if entry.is_file() and _ARCHIVE_FILE_RE.match(entry.name))


def distinct_sources(items: "list[Item]") -> int:
    return len({it.source for it in items if it.source})


def estimated_read_minutes(items: "list[Item]") -> int:
    words = sum(len((it.title + " " + it.summary).split()) for it in items)
    # 250 wpm reading speed; never report below "1 min read"
    return max(1, round(words / 250))


@dataclass
class FilterLog:
    """Structured record of every filtering decision made during a single gather() run."""
    date: str
    prompt_version: str
    fetched: int = 0
    after_keyword: int = 0
    after_dedupe: int = 0
    after_ttl: int = 0
    after_source_cap: int = 0
    dropped_keyword: list = field(default_factory=list)
    dropped_dedupe: list = field(default_factory=list)
    dropped_ttl: list = field(default_factory=list)
    dropped_source_cap: list = field(default_factory=list)
    final: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "prompt_version": self.prompt_version,
            "pipeline": {
                "fetched": self.fetched,
                "after_keyword_filter": self.after_keyword,
                "after_dedupe": self.after_dedupe,
                "after_ttl_filter": self.after_ttl,
                "after_source_cap": self.after_source_cap,
            },
            "dropped_keyword": self.dropped_keyword,
            "dropped_dedupe": self.dropped_dedupe,
            "dropped_ttl": self.dropped_ttl,
            "dropped_source_cap": self.dropped_source_cap,
            "final": self.final,
        }


def _item_log_dict(it: "Item") -> dict:
    d = {
        "title": it.title,
        "summary": it.summary,                       # #9: the text the scorer saw
        "url": it.url,
        "source": it.source,
        "score": round(it.score, 2),
        "score_components": score_components(it),     # #9: per-term feature breakdown
        "age_days": round(it.age_hours / 24, 1),
    }
    if it.first_seen is not None:
        d["first_seen"] = it.first_seen.isoformat()
    return d


def write_filter_log(log: FilterLog, out_dir: Path) -> None:
    """Write log as JSON to <out_dir>/logs/YYYY-MM-DD.json.

    Also writes <out_dir>/logs/latest.json as a stable handoff for
    downstream consumers (e.g. the Hermes Discovery Queue skill) that
    fetch via raw.githubusercontent.com and don't want to guess today's
    filename.
    """
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(log.to_dict(), indent=2)
    (log_dir / f"{log.date}.json").write_text(payload)
    (log_dir / "latest.json").write_text(payload)


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
        r = httpx.get(url, headers={"User-Agent": "ContentFinder/1.0"}, timeout=15)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
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


def score_components(item: Item) -> dict:
    """Per-term breakdown behind score_item, logged for #9 / the self-tuning
    scorer (roadmap M2.1).

    ``total`` is computed unrounded and is exactly ``score_item(item)``; the
    other fields are rounded for human-readable logs.
    """
    base = keyword_score(f"{item.title} {item.summary}")

    # Recency bonus: fresher = higher (0..1, linear decay over 7 days).
    recency = max(0.0, 7 - item.age_hours / 24) / 7

    # Source-credibility bonus (loaded from sources.yml).
    src_bonus = _TRUSTED_WEIGHTS.get(item.source, 0)

    # HN points contribute lightly (caps to avoid drowning the rest).
    hn_bonus = 0.0
    if item.source == "Hacker News":
        hn_bonus = min(item.extra.get("points", 0) / 100.0, 4.0)

    recency_term = 2 * recency
    return {
        "keyword": base,
        "recency": round(recency, 4),
        "recency_term": round(recency_term, 4),
        "src_bonus": src_bonus,
        "hn_bonus": round(hn_bonus, 4),
        "total": base + recency_term + src_bonus + hn_bonus,
    }


def score_item(item: Item) -> float:
    return score_components(item)["total"]


# --------------------------------------------------------------------------- #
# Cross-day dedup state (dedup-state.json)
# --------------------------------------------------------------------------- #

DEDUP_STATE_PATH = Path("dedup-state.json")
DEDUP_STATE_VERSION = 1
DEDUP_TTL_DAYS = 5
DEDUP_MAX_AGE_DAYS = 30
MIN_RENDERED_ITEMS = 10


def load_dedup_state(path: "Path | str") -> dict[str, str]:
    """Load the cross-day dedup state file.

    Returns a flat {canonical_url: ISO_first_seen_date} map. Missing,
    malformed, or unknown-version files return {} so the daily cron is
    never broken by state-file corruption.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] dedup-state load failed ({exc}); proceeding with empty state",
              file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("version") != DEDUP_STATE_VERSION:
        return {}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}
    return {str(k): str(v) for k, v in entries.items()}


def save_dedup_state(path: "Path | str", state: dict[str, str]) -> None:
    """Atomically write the dedup state to disk (write-temp + rename)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": DEDUP_STATE_VERSION, "entries": dict(state)}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                              sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def update_seen_state(
    state: dict[str, str],
    items: list["Item"],
    *,
    today: date,
    max_age_days: int,
) -> dict[str, str]:
    """Return a new state map with today's items added and old entries pruned.

    Semantics:
    - Items not in state get today's date.
    - Items already in state keep their (earlier) first_seen date.
    - Entries older than max_age_days (inclusive boundary kept) are dropped.
    - Entries with corrupt date strings are dropped (defensive).
    """
    out: dict[str, str] = {}
    cutoff = today - timedelta(days=max_age_days)
    for url, raw in state.items():
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        if d >= cutoff:
            out[url] = raw
    today_iso = today.isoformat()
    for it in items:
        canon = canonical_url(it.url)
        out.setdefault(canon, today_iso)
    return out


def topup_to_minimum(
    *,
    fresh: list["Item"],
    filtered_out: list["Item"],
    minimum: int,
) -> list["Item"]:
    """If `fresh` has fewer than `minimum` items, top up from `filtered_out`
    by score (highest first). Topped-up items retain their first_seen flag
    so the renderer can show the resurfacing badge. Source cap is applied
    later in the pipeline.
    """
    if len(fresh) >= minimum:
        return list(fresh)
    needed = minimum - len(fresh)
    topup = sorted(filtered_out, key=lambda x: x.score, reverse=True)[:needed]
    return list(fresh) + topup


def annotate_first_seen(items: list["Item"], state: dict[str, str]) -> None:
    """Set Item.first_seen on every item whose canonical URL is in state."""
    for it in items:
        canon = canonical_url(it.url)
        raw = state.get(canon)
        if not raw:
            continue
        try:
            it.first_seen = date.fromisoformat(raw)
        except ValueError:
            continue


def filter_unseen(
    items: list["Item"], *, today: date, ttl_days: int
) -> list["Item"]:
    """Drop items first seen within `ttl_days` of today (inclusive boundary).

    Items with no first_seen always pass through. ttl_days <= 0 disables
    filtering entirely (used by --dedup-ttl-days 0).
    """
    if ttl_days <= 0:
        return list(items)
    out: list[Item] = []
    for it in items:
        if it.first_seen is None:
            out.append(it)
            continue
        age_days = (today - it.first_seen).days
        if age_days > ttl_days:
            out.append(it)
    return out


def canonical_url(url: str) -> str:
    """Strip query string and trailing slash for cross-run URL comparison.

    The same canonicalization is used by within-run dedup() and by the
    cross-day dedup-state filter, so a URL with a tracker tomorrow still
    matches the bare URL stored today.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    host = parsed.netloc.replace("www.", "")

    query = ""
    if host == "news.ycombinator.com" and path == "/item":
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key == "id" and value:
                query = urlencode({"id": value})
                break

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        "",
        query,
        "",
    ))


def dedupe(items: list[Item]) -> list[Item]:
    """Drop near-duplicate titles / same URLs across sources."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[Item] = []
    for it in sorted(items, key=lambda x: x.score, reverse=True):
        u = canonical_url(it.url)
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
  /* V2 — warm-amber on deep neutral. Spec: Content Finder V2 handoff. */
  --bg:          #0a0a0e;
  --bg-soft:     #0f0f15;
  --surface:     #14141c;
  --surface-2:   #1a1a24;
  --line:        rgba(255, 255, 255, 0.08);
  --line-strong: rgba(255, 255, 255, 0.16);

  --fg:    #f3f1ec;
  --fg-2:  #b3aea1;
  --fg-3:  #7a766c;
  --fg-4:  #54514a;

  --accent:      #e8b765;
  --accent-soft: rgba(232, 183, 101, 0.12);
  --accent-line: rgba(232, 183, 101, 0.32);
  --accent-ink:  #0a0a0e;
  --accent-bg:   var(--accent-soft);
  --accent-border: var(--accent-line);

  /* Category-chip tints — pastel on dark, used as tag text + border */
  --cat-models:     #c7d2fe;
  --cat-agents:     #fcd5b5;
  --cat-tooling:    #b9e4c9;
  --cat-regulation: #f7c0c8;
  --cat-enterprise: #d6c7f0;
  --cat-research:   #b9d7e8;

  --col:       920px;
  --pad:       28px;
  --radius:    14px;
  --radius-sm: 10px;

  color-scheme: dark;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: var(--bg); color: var(--fg); }
body {
  font-family: "Hanken Grotesk", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 18px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  min-height: 100vh;
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(232,183,101,0.04), transparent 60%),
    var(--bg);
}
.page {
  max-width: var(--col);
  margin: 0 auto;
  min-height: 100vh;
}
.wrap {
  max-width: var(--col);
  margin: 0 auto;
  padding: 0 var(--pad);
}

/* Skip link (keyboard users) */
.skip-link {
  position: absolute;
  left: 12px;
  top: 10px;
  z-index: 100;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--fg);
  color: var(--bg);
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transform: translateY(-140%);
  transition: transform 160ms ease;
}
.skip-link:focus { transform: translateY(0); }

/* Top bar — sticky, blurred, brand + nav */
.topbar {
  position: sticky; top: 0; z-index: 50;
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  background: color-mix(in oklab, var(--bg) 78%, transparent);
  border-bottom: 1px solid var(--line);
}
.topbar-inner {
  display: flex; align-items: center; justify-content: space-between;
  height: 60px; gap: 16px;
}
.brand {
  display: flex; align-items: center; gap: 12px;
  font-weight: 600; font-size: 16px; letter-spacing: -0.005em;
  color: var(--fg); text-decoration: none;
}
.brand-mark {
  width: 24px; height: 24px; border-radius: 7px;
  background: var(--accent);
  display: grid; place-items: center;
  color: var(--accent-ink);
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-weight: 600; font-size: 12px;
}
.topnav { display: flex; gap: 6px; align-items: center; }
.topnav a {
  color: var(--fg-2); text-decoration: none;
  font-size: 14.5px; font-weight: 500;
  padding: 8px 12px; border-radius: 8px;
  transition: background 120ms ease, color 120ms ease;
}
.topnav a:hover { color: var(--fg); background: rgba(255,255,255,0.04); }
.topnav a.active { color: var(--fg); background: rgba(255,255,255,0.06); }

/* Masthead */
.masthead { padding: 72px 0 40px; }
.kicker {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--fg-3);
  display: inline-flex; align-items: center; gap: 10px;
}
.kicker .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.mast-title {
  font-weight: 700;
  font-size: clamp(40px, 5.5vw, 60px);
  line-height: 1.05;
  letter-spacing: -0.025em;
  margin: 16px 0 18px;
  color: var(--fg);
  text-wrap: balance;
}
.mast-title .accent { color: var(--accent); }
.mast-sub {
  color: var(--fg-2);
  font-size: 19px;
  max-width: 58ch;
  line-height: 1.5;
  text-wrap: pretty;
}
.mast-meta {
  display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: center;
  margin-top: 32px;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12.5px;
  color: var(--fg-3); letter-spacing: 0.04em;
}
.mast-meta b { color: var(--fg-2); font-weight: 500; }
.mast-meta .pill {
  border: 1px solid var(--line);
  padding: 5px 11px; border-radius: 999px;
  color: var(--fg-2);
}

/* Dateline (prominent date row above kicker) */
.mast-dateline {
  display: flex; align-items: baseline; gap: 14px;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 16px; letter-spacing: 0.02em;
  border-bottom: 1px solid var(--line);
  padding-bottom: 14px; margin-bottom: 28px;
}
.mast-dateline-day {
  text-transform: uppercase;
  letter-spacing: 0.16em; font-size: 0.7em; font-weight: 500;
  color: var(--accent);
  padding: 4px 8px;
  border: 1px solid var(--accent-line);
  background: var(--accent-soft);
  border-radius: 6px;
}
.mast-dateline-date {
  font-weight: 500; color: var(--fg); font-variant-numeric: tabular-nums;
}

/* Compact density + prominent date (today page) */
[data-mast="compact"] .masthead { padding: 36px 0 24px; }
[data-mast="compact"] .mast-title {
  font-size: clamp(26px, 3.2vw, 34px);
  margin: 10px 0 10px;
}
[data-mast="compact"] .mast-meta { margin-top: 18px; }

/* Footer */
footer.site-footer {
  padding: 48px 0 56px;
  border-top: 1px solid var(--line);
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12.5px;
  color: var(--fg-3); letter-spacing: 0.04em;
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px 24px;
}
footer.site-footer a { color: var(--fg-2); text-decoration: none; }
footer.site-footer a:hover { color: var(--accent); }

/* ===== V2 story card ===== */
.article-list, .stories { display: flex; flex-direction: column; gap: 12px; }
.story {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 160ms ease, background 160ms ease;
}
.story:hover { border-color: var(--line-strong); }
.story.open { border-color: var(--accent-line); background: var(--surface-2); }
.story-head {
  display: grid; grid-template-columns: 1fr auto;
  gap: 20px; padding: 24px 26px;
  cursor: pointer; align-items: start;
}
.story-head:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 6px;
}
.story-meta-row {
  display: flex; flex-wrap: wrap; align-items: center;
  gap: 8px; margin-bottom: 12px;
}
.tag {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11.5px; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 4px 9px; border-radius: 5px;
  color: var(--fg-2);
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--line);
}
.tag[data-cat="Models"]     { color: var(--cat-models);     border-color: color-mix(in oklab, var(--cat-models) 28%, transparent); }
.tag[data-cat="Agents"]     { color: var(--cat-agents);     border-color: color-mix(in oklab, var(--cat-agents) 28%, transparent); }
.tag[data-cat="Tooling"]    { color: var(--cat-tooling);    border-color: color-mix(in oklab, var(--cat-tooling) 28%, transparent); }
.tag[data-cat="Regulation"] { color: var(--cat-regulation); border-color: color-mix(in oklab, var(--cat-regulation) 28%, transparent); }
.tag[data-cat="Enterprise"] { color: var(--cat-enterprise); border-color: color-mix(in oklab, var(--cat-enterprise) 28%, transparent); }
.tag[data-cat="Research"]   { color: var(--cat-research);   border-color: color-mix(in oklab, var(--cat-research) 28%, transparent); }
.src {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11.5px; letter-spacing: 0.04em;
  color: var(--fg-3);
  display: inline-flex; align-items: center; gap: 8px;
  margin-left: auto;
}
.src::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--fg-4);
}
.story-title {
  font-weight: 600;
  font-size: 22px;
  line-height: 1.28;
  color: var(--fg);
  letter-spacing: -0.018em;
  text-wrap: balance;
  margin: 0;
}
.story-summary {
  color: var(--fg-2);
  font-size: 17px;
  line-height: 1.55;
  margin-top: 10px;
  max-width: 64ch;
  text-wrap: pretty;
}
.chev {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: 1px solid var(--line);
  color: var(--fg-3);
  display: grid; place-items: center;
  transition: transform 240ms cubic-bezier(.2,.7,.2,1),
              color 160ms ease, background 160ms ease, border-color 160ms ease;
  user-select: none;
  flex-shrink: 0;
}
.story.open .chev {
  transform: rotate(180deg);
  color: var(--accent-ink);
  background: var(--accent);
  border-color: var(--accent);
}
.story-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 320ms cubic-bezier(.2,.7,.2,1);
}
.story.open .story-body { grid-template-rows: 1fr; }
.story-body > .inner { overflow: hidden; min-height: 0; }
.story-inner-pad {
  padding: 0 26px 24px;
  display: flex; flex-direction: column; gap: 18px;
}
.sowhat {
  padding: 16px 20px;
  background: var(--accent-soft);
  border-left: 2px solid var(--accent);
  border-radius: 6px;
  color: var(--fg);
  font-size: 17px;
  line-height: 1.55;
}
.sowhat-label {
  display: block;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 10px;
}
.sowhat-body {
  margin: 0;
  font-size: 17px;
  line-height: 1.55;
  color: var(--fg);
  text-wrap: pretty;
}
.story-actions {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap;
}
.read {
  display: inline-flex; align-items: center; gap: 10px;
  font-size: 14.5px; font-weight: 600;
  color: var(--fg);
  background: transparent;
  border: 1px solid var(--line-strong);
  padding: 9px 16px;
  border-radius: 999px;
  text-decoration: none;
  transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
}
.read:hover { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.read .arrow { font-family: "JetBrains Mono", ui-monospace, monospace; transition: transform 160ms ease; }
.read:hover .arrow { transform: translateX(3px); }
.src-full {
  font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 12px;
  color: var(--fg-3); letter-spacing: 0.04em;
}
.meta-age {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11.5px; letter-spacing: 0.04em;
  color: var(--fg-3);
}
@media (max-width: 640px) {
  .story-head { padding: 20px; gap: 14px; }
  .story-inner-pad { padding: 0 20px 20px; }
  .story-title { font-size: 19.5px; }
  .story-summary { font-size: 16px; }
}

/* ===== V2 filter rail (sticky chip bar) ===== */
.rail {
  position: sticky; top: 60px; z-index: 40;
  background: color-mix(in oklab, var(--bg) 80%, transparent);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border-bottom: 1px solid var(--line);
}
.rail-inner {
  display: flex; align-items: center; gap: 8px;
  padding: 14px 0;
  overflow-x: auto; scrollbar-width: none;
}
.rail-inner::-webkit-scrollbar { display: none; }
.chip {
  display: inline-flex; align-items: center; gap: 9px;
  padding: 8px 14px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--fg-2);
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  border-radius: 999px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
}
.chip:hover { color: var(--fg); border-color: var(--line-strong); }
.chip:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.chip[aria-pressed="true"] {
  background: var(--fg);
  color: var(--bg);
  border-color: var(--fg);
}
.chip .n {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11px;
  color: var(--fg-3);
  padding: 1px 7px; border-radius: 999px;
  background: rgba(255,255,255,0.05);
  min-width: 20px; text-align: center;
}
.chip[aria-pressed="true"] .n {
  color: var(--bg); background: rgba(0,0,0,0.1);
}
/* Category tints — mirror the per-item .tag colours onto the filter chips so
   the nav rail reads in the same colour language. Resting state tints the
   text + border; the combined [aria-pressed="true"] selector fills with the
   pastel (needs both attrs to outrank the generic active rule above). The
   "All" chip is data-tag="all" and matches none of these, so it stays neutral. */
.chip[data-tag="Models"]     { color: var(--cat-models);     border-color: color-mix(in oklab, var(--cat-models) 28%, transparent); }
.chip[data-tag="Agents"]     { color: var(--cat-agents);     border-color: color-mix(in oklab, var(--cat-agents) 28%, transparent); }
.chip[data-tag="Tooling"]    { color: var(--cat-tooling);    border-color: color-mix(in oklab, var(--cat-tooling) 28%, transparent); }
.chip[data-tag="Regulation"] { color: var(--cat-regulation); border-color: color-mix(in oklab, var(--cat-regulation) 28%, transparent); }
.chip[data-tag="Enterprise"] { color: var(--cat-enterprise); border-color: color-mix(in oklab, var(--cat-enterprise) 28%, transparent); }
.chip[data-tag="Research"]   { color: var(--cat-research);   border-color: color-mix(in oklab, var(--cat-research) 28%, transparent); }
.chip[data-tag="Models"][aria-pressed="true"]     { background: var(--cat-models);     border-color: var(--cat-models);     color: var(--bg); }
.chip[data-tag="Agents"][aria-pressed="true"]     { background: var(--cat-agents);     border-color: var(--cat-agents);     color: var(--bg); }
.chip[data-tag="Tooling"][aria-pressed="true"]    { background: var(--cat-tooling);    border-color: var(--cat-tooling);    color: var(--bg); }
.chip[data-tag="Regulation"][aria-pressed="true"] { background: var(--cat-regulation); border-color: var(--cat-regulation); color: var(--bg); }
.chip[data-tag="Enterprise"][aria-pressed="true"] { background: var(--cat-enterprise); border-color: var(--cat-enterprise); color: var(--bg); }
.chip[data-tag="Research"][aria-pressed="true"]   { background: var(--cat-research);   border-color: var(--cat-research);   color: var(--bg); }

/* ===== V2 sections (used by takeaways + future named sections) ===== */
section.block { padding: 56px 0; border-bottom: 1px solid var(--line); }
section.block:last-of-type { border-bottom: 0; }
.sec-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 32px; gap: 16px;
}
.sec-title {
  font-weight: 700; font-size: 30px; letter-spacing: -0.02em;
  color: var(--fg);
  margin: 0;
}
.sec-meta {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12px;
  color: var(--fg-3); letter-spacing: 0.1em; text-transform: uppercase;
}

/* ===== V2 takeaways grid (3-col card row) ===== */
.takes { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 760px) { .takes { grid-template-columns: 1fr 1fr 1fr; } }
.take {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 26px 22px 22px;
  display: flex; flex-direction: column;
  min-height: 220px;
  transition: border-color 160ms ease;
}
.take:hover { border-color: var(--accent-line); }
.take-num {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-weight: 500; font-size: 13px; letter-spacing: 0.1em;
  color: var(--accent);
  margin-bottom: 14px;
}
.take-head {
  font-weight: 700;
  font-size: 18.5px;
  line-height: 1.3;
  letter-spacing: -0.01em;
  color: var(--fg);
  margin-bottom: 10px;
  text-wrap: pretty;
}
.take-body {
  font-size: 16px;
  line-height: 1.5;
  letter-spacing: -0.005em;
  color: var(--fg-2);
  flex: 1;
  text-wrap: pretty;
}
.take-foot {
  margin-top: 18px; display: flex; gap: 16px; flex-wrap: wrap;
}
.take-link {
  font-size: 13.5px; font-weight: 500;
  color: var(--fg-3); text-decoration: none;
  border-bottom: 1px solid var(--line);
  padding-bottom: 2px;
  transition: color 120ms ease, border-color 120ms ease;
}
.take-link:hover { color: var(--accent); border-color: var(--accent-line); }
@media (max-width: 640px) {
  .take { padding: 22px 20px 20px; min-height: 0; }
  .take-head { font-size: 17px; }
  .take-body { font-size: 15px; }
  .sec-title { font-size: 25px; }
  section.block { padding: 40px 0; }
}

/* Article list — wraps the per-section <section class="block"> groups */
.article-list { padding-bottom: 24px; }

/* Score pill + resurfacing badge — used by the no-summarize --no-summarize path */
.score-pill {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--fg-3);
  background: rgba(255,255,255,0.04);
}
.score-pill.score-high { color: var(--accent); border-color: var(--accent-line); background: var(--accent-soft); }
.score-pill.score-mid  { color: var(--fg-2); }
.score-pill.score-low  { color: var(--fg-4); }
.resurfacing {
  font-size: 12px; color: var(--fg-3);
  cursor: help; user-select: none;
}

.is-hidden { display: none !important; }

@media (prefers-reduced-motion: reduce) {
  html:focus-within { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
"""


# --------------------------------------------------------------------------- #
# Tag post-processing + chip filter
# --------------------------------------------------------------------------- #

_TAG_ELEMENT_RE = re.compile(
    r'^(<li([^>]*)>)(.*?)(</li>)\s*$',
    re.DOTALL,
)
# Match the {tags: ...} literal at the tail of a bullet, tolerating an
# optional closing </p> tag (markdown wraps loose-list items in <p>).
_TAG_SUFFIX_RE = re.compile(r'\s*\{tags:\s*([^}]*)\}\s*(</p>)?\s*$')
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
        # Re-attach the closing </p> if the suffix consumed it, so the LI
        # stays well-formed for the structured card parser downstream.
        closing = suffix.group(2) or ""
        content = content[: suffix.start()].rstrip() + closing
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


def render_chip_bar(
    counts: dict[str, int] | None = None,
    *,
    total: int | None = None,
) -> str:
    """V2 filter rail: sticky `.rail` row of `.chip` buttons with mono `.n` count badges.

    - When `counts` is None (no-summarize path), the .n badges are omitted entirely.
    - When `counts` is provided, each chip gets a `<span class="n">N</span>` badge.
    - The All chip's badge uses `total` if given (caller-computed item count),
      otherwise falls back to the sum of `counts` values (correct only when items
      carry exactly one tag).
    """
    has_counts = counts is not None
    parts = ['<div class="rail">', '<div class="wrap rail-inner" role="tablist">']

    def _badge(n: int) -> str:
        return f'<span class="n">{n}</span>'

    if has_counts:
        total_n = total if total is not None else sum(counts.values())
        parts.append(
            '<button type="button" class="chip" role="tab" '
            'data-tag="all" aria-pressed="true">'
            f'<span>All</span>{_badge(total_n)}</button>'
        )
    else:
        parts.append(
            '<button type="button" class="chip" role="tab" '
            'data-tag="all" aria-pressed="true"><span>All</span></button>'
        )

    for tag in TAG_TAXONOMY:
        if has_counts:
            badge = _badge(counts.get(tag, 0))
            parts.append(
                f'<button type="button" class="chip" role="tab" '
                f'data-tag="{tag}" aria-pressed="false">'
                f'<span>{tag}</span>{badge}</button>'
            )
        else:
            parts.append(
                f'<button type="button" class="chip" role="tab" '
                f'data-tag="{tag}" aria-pressed="false">'
                f'<span>{tag}</span></button>'
            )

    parts.append('</div></div>')
    return "".join(parts)


_ARTICLE_DATA_TAGS_RE = re.compile(
    r'<article\b[^>]*\bdata-tags="([^"]*)"', re.IGNORECASE
)


def _count_tags_in_body(body_html: str) -> dict[str, int]:
    """Count taxonomy tags across rendered ``<article data-tags="…">`` cards.

    Items with multiple tags increment each tag — the chip count is "items
    matching this filter," not a partition.
    """
    counts: dict[str, int] = {tag: 0 for tag in TAG_TAXONOMY}
    for match in _ARTICLE_DATA_TAGS_RE.finditer(body_html):
        for tag in match.group(1).split():
            if tag in counts:
                counts[tag] += 1
    return counts


def _chip_counts_for_body(body_html: str) -> dict[str, int] | None:
    """Return tag counts to render on chips, or ``None`` to render plain.

    The ``--no-summarize`` ranked-list path doesn't assign tags, so every
    count would be ``0`` — a chip bar full of ``(0)`` is worse than no
    counts at all. Suppress in that case.
    """
    counts = _count_tags_in_body(body_html)
    return counts if any(counts.values()) else None


INTERACTIONS_JS = """
<script>
(function () {
  // Topic filter chips — V2 uses aria-pressed for active state.
  var chips = document.querySelectorAll('.chip');
  function applyFilter(tag) {
    chips.forEach(function (c) {
      c.setAttribute('aria-pressed', c.dataset.tag === tag ? 'true' : 'false');
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

  // V2 story expand/collapse: clicking the head (or pressing Enter/Space
  // when focused) toggles a `.open` class on the .story article, which the
  // CSS animates via grid-template-rows 0fr → 1fr.
  function toggleStory(head) {
    var story = head.closest('.story');
    if (!story) return;
    var open = story.classList.toggle('open');
    head.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  document.querySelectorAll('.story-head').forEach(function (head) {
    head.addEventListener('click', function () { toggleStory(head); });
    head.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        toggleStory(head);
      }
    });
  });

  // Takeaways collapsible
  // Takeaway → story navigation (V2). Each .take-link is a normal <a>
  // with both href="<article-url>" and data-item-url. Default click would
  // open the article in a new tab; we intercept when there's a matching
  // in-page .story card and expand it instead. JS-off / unmatched falls
  // back to following the href.
  function navigateToItem(itemUrl) {
    if (!itemUrl) return;
    var safe = itemUrl.replace(/"/g, '\\\\"');
    var matchLink = document.querySelector('.story .read[href="' + safe + '"]');
    var story = matchLink ? matchLink.closest('.story') : null;
    if (!story) {
      window.open(itemUrl, '_blank', 'noopener');
      return;
    }
    applyFilter('all');
    document.querySelectorAll('.story.open').forEach(function (el) {
      if (el !== story) {
        el.classList.remove('open');
        var h = el.querySelector('.story-head');
        if (h) h.setAttribute('aria-expanded', 'false');
      }
    });
    story.classList.add('open');
    var head = story.querySelector('.story-head');
    if (head) head.setAttribute('aria-expanded', 'true');
    setTimeout(function () {
      story.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  }
  window.navigateToItem = navigateToItem;
  document.querySelectorAll('.take-link').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      // If the matching story exists on this page, intercept. Otherwise
      // let the browser follow the href (article URL in new tab via the
      // anchor's default behaviour — handled by markup attrs in HTML).
      var safe = (a.dataset.itemUrl || '').replace(/"/g, '\\\\"');
      if (safe && document.querySelector('.story .read[href="' + safe + '"]')) {
        ev.preventDefault();
        navigateToItem(a.dataset.itemUrl);
      }
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
    """V2 tag chips: <span class="tag" data-cat="Models">Models</span>.

    Returns inline spans for use inside .story-meta-row. The legacy
    .tags wrapper div is no longer emitted; the wrapper is now
    .story-meta-row which also contains the source label.
    """
    if not data_tags:
        return ""
    return "".join(
        f'<span class="tag" data-cat="{html.escape(t)}">{html.escape(t)}</span>'
        for t in data_tags.split() if t
    )


CHEVRON_SVG = (
    '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">'
    '<path d="M2.5 4.5 L6 8 L9.5 4.5" stroke="currentColor" '
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


_LI_OUTER_RE = re.compile(r'<li([^>]*)>(.*)</li>', re.DOTALL)
_LI_TITLE_RE = re.compile(r'\s*<strong>(.*?)</strong>\s*[—–-]?\s*', re.DOTALL)
_LI_SO_WHAT_RE = re.compile(r'<strong>\s*So what:?\s*</strong>\s*', re.IGNORECASE)
_LI_LINK_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
# Markdown link literal that survives if the markdown extension somehow misses it.
_RAW_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')


def _strip_p_wrapper(content: str) -> str:
    """Drop a leading ``<p>`` and trailing ``</p>`` if the LI is loose-list shaped.

    Python markdown wraps each ``<li>`` content in ``<p>...</p>`` whenever the
    source markdown has blank lines between bullets. The card parser keys on
    the raw inline HTML, so we normalise both shapes here.
    """
    s = content.strip()
    s = re.sub(r'^<p>\s*', '', s)
    s = re.sub(r'\s*</p>\s*$', '', s)
    return s


def _convert_raw_md_links(content: str) -> str:
    """Last-resort: convert ``[label](url)`` literals to real ``<a>`` tags.

    Only fires if some markdown link slipped past the renderer (e.g. nested
    in a way the ``extra`` extension doesn't expand). Keeps the page clean.
    """
    def repl(m: re.Match) -> str:
        label = html.escape(m.group(1).strip())
        href = html.escape(m.group(2))
        return f'<a href="{href}">{label}</a>'
    return _RAW_MD_LINK_RE.sub(repl, content)


def _html_text(value: str) -> str:
    """Render untrusted Markdown-derived fragments as inert text."""
    return html.escape(html.unescape(value), quote=False)


def _safe_http_url(url: str) -> str:
    """Return a link URL only when it is safe to render as an article href."""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _parse_synthesis_li(li_html: str, item_id: int) -> str:
    """Convert a `<li>` carrying a structured synthesis bullet into a card.

    Handles both tight-list (`<li><strong>...`) and loose-list
    (`<li><p><strong>...`) shapes, and tolerates Claude moving the source
    link before/after the ``**So what:**`` clause.
    """
    outer = _LI_OUTER_RE.match(li_html)
    if not outer:
        return li_html
    attrs, content = outer.group(1), outer.group(2)
    data_tags_match = re.search(r'data-tags="([^"]*)"', attrs)
    data_tags = data_tags_match.group(1) if data_tags_match else ""

    # Normalise both list shapes and rescue any literal markdown links.
    content = _convert_raw_md_links(_strip_p_wrapper(content))

    title_m = _LI_TITLE_RE.match(content)
    if not title_m:
        # Fallback: no leading <strong> headline. Take the first sentence
        # (text before the em-dash) as the headline; if no em-dash, take
        # the first ~80 chars. Still honour any source link found in the
        # bullet so the card stays usable.
        plain = re.sub(r'<[^>]+>', '', content).strip()
        # Drop any trailing {tags:...} literal that escaped earlier passes.
        plain = re.sub(r'\s*\{tags:[^}]*\}\s*$', '', plain).strip()
        if "—" in plain:
            headline, _, body_text = plain.partition("—")
        elif " - " in plain:
            headline, _, body_text = plain.partition(" - ")
        else:
            headline = plain[:80].rstrip(".") + ("…" if len(plain) > 80 else "")
            body_text = plain[80:].strip()
        url, source_name = "", ""
        link_m = _LI_LINK_RE.search(content)
        if link_m:
            url = link_m.group(1)
            source_name = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
        return _build_card_html(
            item_id=item_id,
            data_tags=data_tags,
            title=headline.strip(),
            snippet=body_text.strip() if body_text.strip() else "",
            so_what="",
            url=url,
            source_name=_resolve_source_name(source_name, url),
        )

    title = title_m.group(1).strip()
    rest = content[title_m.end():]
    # Strip any trailing {tags:...} literal that escaped earlier passes.
    rest = re.sub(r'\s*\{tags:[^}]*\}\s*$', '', rest).strip()

    sw_m = _LI_SO_WHAT_RE.search(rest)
    if sw_m:
        snippet_html = rest[:sw_m.start()]
        after_sw = rest[sw_m.end():]
    else:
        snippet_html = rest
        after_sw = ""

    # Source link can appear before OR after "So what:" — search the whole
    # bullet and use the LAST <a> as the citation. That tolerates Claude
    # putting the link wherever feels natural in the prose.
    all_links = list(_LI_LINK_RE.finditer(rest))
    if all_links:
        link_m = all_links[-1]
        url = link_m.group(1)
        source_name = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
        # Strip the source-link span out of whichever slice it landed in.
        link_slice_start, link_slice_end = link_m.span()
        if sw_m and link_slice_start >= sw_m.end():
            local_start = link_slice_start - sw_m.end()
            local_end = link_slice_end - sw_m.end()
            after_sw = (after_sw[:local_start] + after_sw[local_end:]).strip()
        else:
            local_start = link_slice_start
            local_end = link_slice_end
            snippet_html = (snippet_html[:local_start] + snippet_html[local_end:]).strip()
    else:
        url, source_name = "", ""

    snippet = snippet_html.strip().rstrip(" .").rstrip()
    so_what = after_sw.strip().rstrip(" .").rstrip()

    return _build_card_html(
        item_id=item_id,
        data_tags=data_tags,
        title=title,
        snippet=snippet,
        so_what=so_what,
        url=url,
        source_name=_resolve_source_name(source_name, url),
    )


def _build_card_html(
    *,
    item_id: int,
    data_tags: str,
    title: str,
    snippet: str,
    so_what: str,
    url: str,
    source_name: str,
) -> str:
    """Assemble a synthesis-card ``<article>``. Both structured and fallback
    code paths render through here so the markup stays consistent."""
    # Skip rule: a card with no body, no so-what, no link, and no source is
    # render-noise (e.g. a bullet that lost its source link upstream). The
    # title alone gives the reader nothing to do.
    if not (snippet or so_what or url or source_name):
        return ""
    # Title scrub: strip stray `**` markdown markers (unclosed bold from
    # truncated upstream content). Real headlines never contain literal `**`.
    title = _html_text(title.replace("**", ""))
    snippet = _html_text(snippet)
    so_what = _html_text(so_what)
    safe_url = _safe_http_url(url)
    escaped_source = html.escape(source_name) if source_name else ""

    # --- Head (always visible) -------------------------------------------- #
    meta_row_parts = []
    tag_chips = _render_tag_chips(data_tags)
    if tag_chips:
        meta_row_parts.append(tag_chips)
    if escaped_source:
        meta_row_parts.append(f'<span class="src">{escaped_source}</span>')
    head_inner = ['<div>']
    if meta_row_parts:
        head_inner.append(
            f'<div class="story-meta-row">{"".join(meta_row_parts)}</div>'
        )
    head_inner.append(f'<h3 class="story-title">{title}</h3>')
    if snippet:
        head_inner.append(f'<p class="story-summary">{snippet}</p>')
    head_inner.append('</div>')
    head_inner.append(f'<span class="chev">{CHEVRON_SVG}</span>')

    # --- Body (collapsible) ----------------------------------------------- #
    body_blocks = []
    if so_what:
        body_blocks.append(
            '<div class="sowhat">'
            '<div class="sowhat-label">So what</div>'
            f'<p class="sowhat-body">{so_what}</p>'
            '</div>'
        )
    action_parts = []
    if safe_url:
        action_parts.append(
            f'<a class="read" href="{html.escape(safe_url, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">'
            'Read the article&nbsp;&nbsp;<span class="arrow">→</span></a>'
        )
    if escaped_source:
        action_parts.append(f'<span class="src-full">{escaped_source}</span>')
    if action_parts:
        body_blocks.append(
            f'<div class="story-actions">{"".join(action_parts)}</div>'
        )

    body_html_inner = ""
    if body_blocks:
        body_html_inner = (
            '<div class="inner"><div class="story-inner-pad">'
            f'{"".join(body_blocks)}'
            '</div></div>'
        )

    parts = [
        f'<article class="story" data-tags="{html.escape(data_tags)}" '
        f'id="story-{item_id}">',
        f'<div class="story-head" role="button" tabindex="0" aria-expanded="false" '
        f'aria-controls="story-body-{item_id}">',
        "".join(head_inner),
        '</div>',
        f'<div class="story-body" id="story-body-{item_id}">{body_html_inner}</div>',
        '</article>',
    ]
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

        {"headline": "...", "text": "...", "links": [{"href": ..., "label": ...}, ...]}

    ``headline`` is the leading ``**bold hook**`` (mirrors the Top-story bullet
    convention); it is ``""`` when the bullet has no bold lead, in which case the
    card degrades to body-only — the same look as before this feature landed.
    """
    sections = _split_synthesis_sections(body_html)
    takeaways: list[dict] = []
    rest: list[tuple[str, str]] = []
    for title, content in sections:
        if title.strip().lower() == "key takeaways":
            for li in _BODY_LI_OUTER_RE.finditer(content):
                inner = re.sub(r'^<li[^>]*>', '', li.group(0))
                inner = re.sub(r'</li>\s*$', '', inner)
                inner = _strip_p_wrapper(inner)

                # Peel a leading bold hook headline if present (reuses the same
                # regex the Top-story card parser uses). No leading <strong> →
                # headline stays "" and the whole bullet renders as the body.
                headline = ""
                title_m = _LI_TITLE_RE.match(inner)
                if title_m:
                    headline = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
                    inner = inner[title_m.end():]

                links: list[dict] = []
                for link_m in _LI_LINK_ITER_RE.finditer(inner):
                    label = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
                    if not label:
                        continue
                    links.append({"href": link_m.group(1), "label": label})
                text_html = _LI_LINK_ITER_RE.sub('', inner)
                text = re.sub(r'<[^>]+>', '', text_html).strip().rstrip(" .")
                takeaways.append({"headline": headline, "text": text, "links": links})
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


# Built once: domain → display source name, derived from RSS_SOURCES so the
# fallback name table stays in lockstep with what we actually fetch. New feeds
# added to RSS_SOURCES get a sensible fallback automatically.
_DOMAIN_TO_SOURCE: dict[str, str] = {
    urlparse(_url).netloc.replace("www.", ""): _name
    for _name, _url in RSS_SOURCES
}

# Generic link labels Claude sometimes emits when it copies the prompt's shape
# placeholder verbatim instead of substituting a real publication name.
_GENERIC_SOURCE_LABELS: frozenset[str] = frozenset({
    "source", "read more", "read", "link", "article", "here", "more",
})


def _prettify_source_from_url(url: str) -> str:
    """Best-effort source name derived from a URL. Used as a fallback when the
    LLM emitted a generic link label instead of a real publication name.
    """
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url
    if not host:
        return url
    if host in _DOMAIN_TO_SOURCE:
        return _DOMAIN_TO_SOURCE[host]
    if host == "arxiv.org" or host.endswith(".arxiv.org"):
        m = re.search(r"/(?:abs|pdf)/(\d+\.\d+)", url)
        return f"arXiv {m.group(1)}" if m else "arXiv"
    if host in {"news.ycombinator.com", "ycombinator.com"}:
        return "Hacker News"
    return host


def _resolve_source_name(source_name: str, url: str) -> str:
    """If the LLM emitted a generic link label, derive a real source name
    from the URL. Otherwise return the LLM's label unchanged.
    """
    if source_name and source_name.strip().lower() not in _GENERIC_SOURCE_LABELS:
        return source_name
    fallback = _prettify_source_from_url(url)
    return fallback or source_name


def render_takeaways_section(
    takeaways: list[dict],
    url_to_source: dict[str, str] | None = None,
) -> str:
    """V2 Key Takeaways grid.

    Renders as <section class="block" id="takeaways"> with:
    - .sec-head containing the title + mono count badge ("03 · The shortlist")
    - .takes 3-column grid of .take cards
    - Each .take: .take-num (mono "01"), an optional .take-head (bold hook
      headline, omitted when the takeaway has no bold lead), .take-body (the
      supporting line), .take-foot with .take-link anchors (real <a href="...">
      + data-item-url so navigateToItem can intercept and expand the matching
      story in-page)
    """
    if not takeaways:
        return ""
    url_to_source = url_to_source or {}
    count = len(takeaways)

    parts = [
        '<section class="block" id="takeaways">',
        '<div class="sec-head">',
        '<h2 class="sec-title">Key takeaways</h2>',
        f'<span class="sec-meta">{count:02d} · The shortlist</span>',
        '</div>',
        '<div class="takes">',
    ]

    for i, t in enumerate(takeaways, 1):
        # Link normalisation: accept new `links: [...]` or legacy single-link shape
        link_items = list(t.get("links") or [])
        if not link_items and t.get("href"):
            link_items = [{"href": t["href"], "label": t.get("label") or "Source"}]

        parts.append('<article class="take">')
        parts.append(f'<div class="take-num">{i:02d}</div>')
        headline = (t.get("headline") or "").strip()
        if headline:
            parts.append(f'<div class="take-head">{html.escape(headline)}</div>')
        parts.append(f'<div class="take-body">{html.escape(t["text"])}</div>')

        if link_items:
            parts.append('<div class="take-foot">')
            for lnk in link_items:
                href = lnk.get("href") or ""
                label = lnk.get("label") or "Source"
                safe_href = html.escape(href, quote=True)
                # data-item-url preserved so navigateToItem can expand the
                # matching story in-page. href falls back to the article URL
                # so JS-off / unmatched cases still work.
                parts.append(
                    f'<a class="take-link" href="{safe_href}" '
                    f'data-item-url="{safe_href}">'
                    f'{html.escape(label)} →</a>'
                )
            parts.append('</div>')

        parts.append('</article>')

    parts.append('</div></section>')
    return "".join(parts)


def _render_synthesis_sections(rest_sections: list[tuple[str, str]]) -> tuple[str, int]:
    """V2: each topical section is its own <section class="block"> with the
    same .sec-head + .sec-title + .sec-meta pattern Key takeaways uses.

    sec-meta shows a zero-padded section number + count of stories
    ("01 · 1 story", "02 · 3 stories") for visual rhythm.
    """
    parts: list[str] = ['<div class="article-list">']
    item_id = 0
    sec_no = 0
    for title, content in rest_sections:
        label = _section_display_label(title)
        # Parse cards for this section first so we know the count.
        section_cards: list[str] = []
        for li_m in _BODY_LI_OUTER_RE.finditer(content):
            item_id += 1
            section_cards.append(_parse_synthesis_li(li_m.group(0), item_id))
        if not section_cards:
            continue
        sec_no += 1
        n = len(section_cards)
        sec_meta = f"{sec_no:02d} · {n} stor{'y' if n == 1 else 'ies'}"
        parts.append('<section class="block">')
        parts.append('<div class="sec-head">')
        parts.append(f'<h2 class="sec-title">{html.escape(label)}</h2>')
        parts.append(f'<span class="sec-meta">{sec_meta}</span>')
        parts.append('</div>')
        parts.append('<div class="stories">')
        parts.extend(section_cards)
        parts.append('</div>')
        parts.append('</section>')
    parts.append('</div>')
    return "".join(parts), item_id


def _render_ranked_card(item: Item, item_id: int) -> str:
    """V2 card for the no-summarize ranked path.

    The no-API path has no LLM-derived tags or so-what, so this card is
    leaner: title + summary + source in head, score pill + recurrence badge
    in the meta row, "Read the article" pill in the body, no So-what callout.
    """
    age = _format_age(item.age_hours)
    tier = _score_tier(item.score)
    title = html.escape(item.title)
    snippet = html.escape(item.summary) if item.summary else ""
    source = html.escape(item.source) if item.source else ""

    meta_row_parts = []
    if source:
        meta_row_parts.append(f'<span class="src">{source}</span>')
    meta_row_parts.append(f'<span class="meta-age">{age}</span>')
    meta_row_parts.append(
        f'<span class="score-pill score-{tier}">{item.score:.1f}</span>'
    )
    if item.first_seen is not None:
        meta_row_parts.append(
            '<span class="resurfacing" '
            f'title="First seen {item.first_seen.isoformat()}">↻</span>'
        )

    head_inner = [
        '<div>',
        f'<div class="story-meta-row">{"".join(meta_row_parts)}</div>',
        f'<h3 class="story-title">{title}</h3>',
    ]
    if snippet:
        head_inner.append(f'<p class="story-summary">{snippet}</p>')
    head_inner.append('</div>')
    head_inner.append(f'<span class="chev">{CHEVRON_SVG}</span>')

    body_inner = (
        '<div class="inner"><div class="story-inner-pad">'
        '<div class="story-actions">'
        f'<a class="read" href="{html.escape(item.url, quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
        'Read the article&nbsp;&nbsp;<span class="arrow">→</span></a>'
        f'{f"<span class=\"src-full\">{source}</span>" if source else ""}'
        '</div></div></div>'
    )

    return (
        f'<article class="story" id="story-{item_id}">'
        f'<div class="story-head" role="button" tabindex="0" aria-expanded="false" '
        f'aria-controls="story-body-{item_id}">'
        f'{"".join(head_inner)}'
        '</div>'
        f'<div class="story-body" id="story-body-{item_id}">{body_inner}</div>'
        '</article>'
    )


def _render_masthead(
    page_date: date,
    *,
    item_count: int,
    source_count: int | None,
    read_minutes: int | None,
    issue_number: int | None,
) -> str:
    day_chip = page_date.strftime("%a")        # e.g. "Tue"
    full_date = page_date.strftime("%d %b %Y") # e.g. "26 May 2026"
    kicker_label = "AI Digest"
    if issue_number is not None:
        kicker_label = f"AI Digest · Issue {issue_number}"
    counts_bits = [f"{item_count} items"]
    if source_count is not None:
        counts_bits.append(f"{source_count} sources")
    meta_parts = [f"<span>{html.escape(' · '.join(counts_bits))}</span>"]
    if read_minutes is not None:
        meta_parts.append(f'<span class="pill">~{read_minutes} min read</span>')
    return (
        '<section class="masthead">'
        f'<div class="mast-dateline">'
        f'<span class="mast-dateline-day">{html.escape(day_chip)}</span>'
        f'<span class="mast-dateline-date">{html.escape(full_date)}</span>'
        f'</div>'
        f'<div class="kicker"><span class="dot"></span>{html.escape(kicker_label)}</div>'
        '<h1 class="mast-title">What moved in AI '
        '<span class="accent">today.</span></h1>'
        f'<div class="mast-meta">{"".join(meta_parts)}</div>'
        '</section>'
    )


def _page_shell(
    page_date: date,
    item_count: int,
    *,
    takeaways_html: str = "",
    body_html: str = "",
    sub_label: str | None = None,
    archive_href: str = "archive.html",
    source_count: int | None = None,
    read_minutes: int | None = None,
    issue_number: int | None = None,
    nav_active: str = "today",
) -> str:
    title = f"AI Digest — {page_date.strftime('%a %d %b %Y')}"
    short_date = page_date.strftime("%a %d %b %Y")
    nav_today_cls = ' class="active"' if nav_active == "today" else ""
    nav_archive_cls = ' class="active"' if nav_active == "archive" else ""
    masthead_html = _render_masthead(
        page_date,
        item_count=item_count,
        source_count=source_count,
        read_minutes=read_minutes,
        issue_number=issue_number,
    )
    return "\n".join([
        "<!doctype html>",
        '<html lang="en" data-theme="dark" data-mast="compact" data-date="prominent"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="theme-color" content="#0a0a0e">',
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><text y=\'.9em\' font-size=\'90\'>📡</text></svg>">',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link href="https://fonts.googleapis.com/css2?'
        'family=Hanken+Grotesk:wght@400;500;600;700&'
        'family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{HTML_CSS}</style>",
        "</head><body>",
        '<a class="skip-link" href="#content">Skip to content</a>',
        '<header class="topbar">',
        '<div class="wrap topbar-inner">',
        '<a class="brand" href="index.html">'
        '<div class="brand-mark">CF</div>'
        '<span>Content Finder</span>'
        '</a>',
        '<nav class="topnav">',
        f'<a href="index.html"{nav_today_cls}>Today</a>',
        f'<a href="{html.escape(archive_href)}"{nav_archive_cls}>Archive</a>',
        '<a href="#takeaways">Takeaways</a>',
        '</nav>',
        '</div>',
        '</header>',
        '<main class="wrap" id="content">',
        masthead_html,
        # V2 rail goes BETWEEN the masthead and the takeaways section so it
        # stays sticky right under the topbar as the user scrolls.
        render_chip_bar(
            counts=_chip_counts_for_body(body_html),
            total=item_count,
        ),
        takeaways_html or "",
        body_html,
        '<footer class="site-footer">',
        '<span>Generated by '
        '<a href="https://github.com/raidianblaster/Content-Finder">'
        'Content Finder</a></span>',
        f'<span>{html.escape(short_date)}</span>',
        '</footer>',
        '</main>',
        INTERACTIONS_JS,
        "</body></html>",
    ])


def render_html(
    items: list[Item],
    top_n: int,
    *,
    page_date: date | None = None,
    issue_number: int | None = None,
) -> str:
    """No-summarize ranked list, rendered with the V2 layout."""
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
        source_count=distinct_sources(shown),
        read_minutes=estimated_read_minutes(shown),
        issue_number=issue_number,
    )


PROMPT_VERSION = "v2"
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "synthesis_system.md").read_text()


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

    from tracing import traced_message
    client = Anthropic()
    resp = traced_message(
        client,
        call_site="synthesis",
        prompt_version=PROMPT_VERSION,
        model=model,
        # The full brief (key takeaways + ~9 stories, each with a So-what) runs
        # past 2000 output tokens; that cap truncated the final bullet before its
        # source link, so the last card rendered with no "Read the article" link.
        max_tokens=4000,
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

def gather(
    days: int,
    hn_min_points: int,
    max_per_source: int = 3,
    *,
    dedup_state: "dict[str, str] | None" = None,
    today: "date | None" = None,
    ttl_days: int = DEDUP_TTL_DAYS,
    minimum_items: int = MIN_RENDERED_ITEMS,
) -> "tuple[list[Item], FilterLog]":
    run_date = today or today_hkt()
    log = FilterLog(date=str(run_date), prompt_version=PROMPT_VERSION)

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

    log.fetched = len(items)

    # Drop items with no keyword signal (pure noise).
    by_url_pre = {it.url: it for it in items}
    items = [it for it in items if keyword_score(f"{it.title} {it.summary}") > 0]
    after_keyword_urls = {it.url for it in items}
    log.dropped_keyword = [
        _item_log_dict(it) for url, it in by_url_pre.items()
        if url not in after_keyword_urls
    ]
    log.after_keyword = len(items)

    by_url_pre = {it.url: it for it in items}
    items = dedupe(items)
    after_dedupe_urls = {it.url for it in items}
    log.dropped_dedupe = [
        _item_log_dict(it) for url, it in by_url_pre.items()
        if url not in after_dedupe_urls
    ]
    log.after_dedupe = len(items)

    # Cross-day dedup: annotate with first_seen, filter by TTL, top up if needed.
    if dedup_state is not None:
        annotate_first_seen(items, dedup_state)
        today = today or today_hkt()
        fresh = filter_unseen(items, today=today, ttl_days=ttl_days)

        pre_ttl_urls = {it.url for it in items}
        fresh_urls = {it.url for it in fresh}
        ttl_dropped_map = {it.url: it for it in items if it.url not in fresh_urls}

        if len(fresh) < minimum_items:
            fresh_set = {id(it) for it in fresh}
            filtered_out = [it for it in items if id(it) not in fresh_set]
            items = topup_to_minimum(
                fresh=fresh, filtered_out=filtered_out, minimum=minimum_items
            )
        else:
            items = fresh

        # Items TTL-filtered and not rescued by topup
        final_urls_after_ttl = {it.url for it in items}
        log.dropped_ttl = [
            _item_log_dict(it) for url, it in ttl_dropped_map.items()
            if url not in final_urls_after_ttl
        ]
        log.after_ttl = len(items)
    else:
        log.after_ttl = len(items)

    pre_cap = {it.url: it for it in items}
    final_items = apply_source_cap(items, max_per_source=max_per_source)
    final_urls = {it.url for it in final_items}
    log.dropped_source_cap = [
        _item_log_dict(it) for url, it in pre_cap.items()
        if url not in final_urls
    ]
    log.after_source_cap = len(final_items)
    log.final = [_item_log_dict(it) for it in final_items]

    return final_items, log


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
    parser.add_argument("--no-dedup-state", action="store_true",
                        help="Skip cross-day dedup state load + save")
    parser.add_argument("--dedup-state-path", default=str(DEDUP_STATE_PATH),
                        help=f"Path to cross-day dedup state file "
                             f"(default {DEDUP_STATE_PATH})")
    parser.add_argument("--dedup-ttl-days", type=int, default=DEDUP_TTL_DAYS,
                        help=f"Days an item stays banned after first seen "
                             f"(default {DEDUP_TTL_DAYS}, 0 disables filter "
                             f"but still records state)")
    args = parser.parse_args()

    print(f"[info] gathering last {args.days}d from "
          f"{len(RSS_SOURCES)} feeds + {len(HN_QUERIES)} HN queries...",
          file=sys.stderr)

    page_date = today_hkt()
    state_path = Path(args.dedup_state_path)
    dedup_state = None if args.no_dedup_state else load_dedup_state(state_path)

    items, filter_log = gather(
        args.days,
        args.hn_min_points,
        max_per_source=args.max_per_source,
        dedup_state=dedup_state,
        today=page_date,
        ttl_days=args.dedup_ttl_days,
    )
    print(f"[info] {len(items)} relevant items after filtering", file=sys.stderr)

    if not items:
        print("No relevant items found in window. Try --days 7.", file=sys.stderr)
        return 1

    # Issue number = (count of archived dated files) + 1 for today's new issue.
    # Tomorrow's archived copy is written by the same workflow that moves
    # today's index.html into docs/archive/, so today's run hasn't been
    # archived yet at render time.
    archive_dir = Path(args.out).parent / "archive" if args.out != "-" else None
    issue_no = (count_archived_issues(archive_dir) + 1) if archive_dir else None

    if args.no_summarize:
        if args.format == "html":
            output = render_html(
                items, top_n=args.top, page_date=page_date, issue_number=issue_no,
            )
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
        out_path = Path(args.out)
        with open(out_path, "w") as f:
            f.write(output)
        print(f"[info] wrote {args.out}", file=sys.stderr)
        write_filter_log(filter_log, out_path.parent)

    # Update dedup state only after a successful render — items must have been
    # visible to the user before being banned.
    if dedup_state is not None:
        rendered = items[:args.top]
        new_state = update_seen_state(
            dedup_state, rendered,
            today=page_date, max_age_days=DEDUP_MAX_AGE_DAYS,
        )
        save_dedup_state(state_path, new_state)
        print(f"[info] dedup-state: {len(new_state)} entries "
              f"({len(rendered)} rendered today)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
