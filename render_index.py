#!/usr/bin/env python3
"""Rebuild docs/archive.html from the dated digests in docs/archive/.

V2 layout: focused 760px-wide column. Masthead (kicker + accented title
+ subtitle + topline row) above a flat list of dated rows. Today's row
(the newest, when present) gets an amber tint + Today pill.

The archive embeds the homepage's HTML_CSS so design tokens stay in sync.
Archive-specific styles (the narrower column, list rows, today highlight)
live in ARCHIVE_LIST_CSS below.
"""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime, date
from pathlib import Path

from content_finder import HTML_CSS, today_hkt


DOCS = Path(__file__).parent / "docs"
ARCHIVE_DIR = DOCS / "archive"


# V2 archive-specific CSS. Overrides --col to 760px (vs the homepage's 920px)
# so the dated list reads as a focused single column.
ARCHIVE_LIST_CSS = """
body.archive { --col: 760px; }
.arch-list { padding: 8px 0 24px; }
.arch-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 24px;
  align-items: center;
  padding: 18px 4px;
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  color: inherit;
  position: relative;
  transition: background 140ms ease;
}
.arch-row::after {
  content: '';
  position: absolute; left: -12px; right: -12px; top: 0; bottom: 0;
  border-radius: 10px; pointer-events: none;
  background: transparent; transition: background 140ms ease;
  z-index: -1;
}
.arch-row:hover::after { background: rgba(255,255,255,0.025); }
.arch-row:hover .arch-date { color: var(--accent); }
.arch-row:hover .arch-arrow { color: var(--accent); transform: translateX(4px); }
.arch-row:last-child { border-bottom: 0; }
.arch-date {
  font-size: 19px;
  font-weight: 500;
  color: var(--fg);
  letter-spacing: -0.012em;
  transition: color 140ms ease;
}
.arch-day {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12.5px;
  color: var(--fg-3);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: right;
  min-width: 90px;
}
.arch-arrow {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  color: var(--fg-4);
  transition: transform 160ms ease, color 140ms ease;
  min-width: 16px; text-align: right;
}
.arch-row.is-today { border-bottom-color: var(--accent-line); }
.arch-row.is-today::after { background: var(--accent-soft); }
.arch-row.is-today .arch-arrow { color: var(--accent); }
.today-pill {
  display: inline-flex;
  margin-left: 12px;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 10.5px; font-weight: 600;
  letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--accent-ink);
  background: var(--accent);
  padding: 3px 8px; border-radius: 4px;
  vertical-align: middle;
}

/* Topline row: latest link + count */
.topline {
  margin-top: 30px;
  padding: 16px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
}
.latest-link {
  display: inline-flex; align-items: center; gap: 10px;
  text-decoration: none; color: var(--fg-2);
  font-size: 14.5px; font-weight: 500;
  padding: 6px 0;
  transition: color 140ms ease;
}
.latest-link:hover { color: var(--accent); }
.latest-link .back { font-family: "JetBrains Mono", ui-monospace, monospace; transition: transform 160ms ease; }
.latest-link:hover .back { transform: translateX(-3px); }
.count {
  font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 12px;
  color: var(--fg-3); letter-spacing: 0.1em; text-transform: uppercase;
}
.count b { color: var(--fg); font-weight: 500; }

.arch-empty {
  padding: 36px 4px; color: var(--fg-3); font-size: 15px;
  text-align: center;
  border-bottom: 1px solid var(--line);
}

@media (max-width: 640px) {
  .arch-row {
    grid-template-columns: 1fr auto;
    gap: 14px;
    padding: 16px 4px;
  }
  .arch-arrow { display: none; }
  .arch-date { font-size: 17.5px; }
  .arch-day { font-size: 11.5px; min-width: 72px; }
  .arch-row.is-today .today-pill { font-size: 10px; padding: 2px 6px; }
}
"""


def _render_arch_row(d: datetime, name: str, *, is_today: bool) -> str:
    """Build a single <a class="arch-row"> for the archive list."""
    cls = "arch-row is-today" if is_today else "arch-row"
    pill = '<span class="today-pill">Today</span>' if is_today else ""
    return (
        f'<a class="{cls}" href="archive/{html.escape(name, quote=True)}">'
        f'<span class="arch-date">{d.strftime("%d %b %Y")}{(" " + pill) if pill else ""}</span>'
        f'<span class="arch-day">{d.strftime("%A")}</span>'
        f'<span class="arch-arrow">→</span>'
        f'</a>'
    )


def render_archive_html(
    entries: list[tuple[datetime, str]],
    *,
    today: date | None = None,
) -> str:
    """Render the V2 archive index as a single HTML string.

    Pure function: takes the list of (date, filename) entries already sorted
    in display order (newest first) and returns the full document.
    """
    # Archive UX: the newest digest in the list should be highlighted as
    # "Today" regardless of the machine clock that generated the page.
    #
    # Why: GitHub Pages hosts static HTML; readers interpret "Today" as
    # "newest issue in this archive list", not "matches my local date".
    # We still accept an explicit `today=` override for callers/tests that
    # want calendar matching.
    today_value = today
    count = len(entries)

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en" data-theme="dark" data-mast="compact" '
        'data-date="prominent"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="theme-color" content="#0a0a0e">',
        '<link rel="icon" href="data:image/svg+xml,'
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<text y='.9em' font-size='90'>📡</text></svg>\">",
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link href="https://fonts.googleapis.com/css2?'
        'family=Hanken+Grotesk:wght@400;500;600;700&'
        'family=JetBrains+Mono:wght@400;500&'
        'family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;'
        '1,6..72,400;1,6..72,500&display=swap" rel="stylesheet">',
        "<title>Archive · Content Finder</title>",
        f"<style>{HTML_CSS}{ARCHIVE_LIST_CSS}</style>",
        "</head><body class=\"archive\">",
        '<header class="topbar">',
        '<div class="wrap topbar-inner">',
        '<a class="brand" href="index.html">'
        '<div class="brand-mark">CF</div>'
        '<span>Content Finder</span>'
        '</a>',
        '<nav class="topnav">',
        '<a href="index.html">Today</a>',
        '<a href="archive.html" class="active">Archive</a>',
        '</nav>',
        '</div>',
        '</header>',
        '<main class="wrap">',
        '<section class="masthead">',
        '<div class="kicker"><span class="dot"></span>AI Digest Archive</div>',
        '<h1 class="mast-title">All past <span class="accent">digests.</span></h1>',
        '<p class="mast-sub">Every issue, newest first. Click any date to read its digest.</p>',
        '<div class="topline">',
        '<a class="latest-link" href="index.html">'
        '<span class="back">←</span>'
        '<span>Latest digest</span>'
        '</a>',
        f'<span class="count"><b>{count}</b> archived '
        f'digest{"s" if count != 1 else ""}</span>',
        '</div>',
        '</section>',
        '<div class="arch-list">',
    ]

    if not entries:
        parts.append(
            '<div class="arch-empty">No archived digests yet.</div>'
        )
    else:
        for i, (d, name) in enumerate(entries):
            is_today = (i == 0) if today_value is None else (d.date() == today_value)
            parts.append(_render_arch_row(d, name, is_today=is_today))

    parts.extend([
        '</div>',  # /.arch-list
        '<footer class="site-footer">',
        '<span>Generated by '
        '<a href="https://github.com/raidianblaster/Content-Finder">'
        "Content Finder</a></span>",
        f'<span>{count} issue{"s" if count != 1 else ""}</span>',
        '</footer>',
        '</main>',
        "</body></html>",
    ])
    return "\n".join(parts)


def _collect_entries() -> list[tuple[datetime, str]]:
    files = sorted(ARCHIVE_DIR.glob("*.html"), reverse=True)
    entries: list[tuple[datetime, str]] = []
    for f in files:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", f.stem)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        entries.append((d, f.name))
    return entries


def main() -> int:
    if not ARCHIVE_DIR.exists():
        print(f"[warn] {ARCHIVE_DIR} does not exist; nothing to index", file=sys.stderr)
        return 0

    entries = _collect_entries()
    out = DOCS / "archive.html"
    out.write_text(render_archive_html(entries))
    print(f"[info] wrote {out} ({len(entries)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
