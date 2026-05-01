#!/usr/bin/env python3
"""Rebuild docs/archive.html from the dated digests in docs/archive/."""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime
from pathlib import Path


DOCS = Path(__file__).parent / "docs"
ARCHIVE_DIR = DOCS / "archive"


CSS = """
:root {
  --bg: #fafafa; --fg: #1a1a1a; --muted: #666;
  --accent: #0066cc; --border: #e0e0e0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f0f10; --fg: #e8e8e8; --muted: #9a9a9a;
    --accent: #7aa2ff; --border: #232325;
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
header h1 { margin: 0 0 .25rem; font-size: 1.4rem; }
header nav { margin-top: .75rem; font-size: .9rem; }
header nav a { color: var(--accent); text-decoration: none; }
ul.digests { list-style: none; padding: 0; margin: 0; }
ul.digests li {
  border-top: 1px solid var(--border);
  padding: 1rem 0;
}
ul.digests a {
  color: var(--fg); text-decoration: none;
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 1rem;
}
ul.digests a:hover { color: var(--accent); }
ul.digests .date { font-size: 1rem; font-weight: 500; }
ul.digests .day { color: var(--muted); font-size: .85rem; }
"""


def main() -> int:
    if not ARCHIVE_DIR.exists():
        print(f"[warn] {ARCHIVE_DIR} does not exist; nothing to index", file=sys.stderr)
        return 0

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

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><text y=\'.9em\' font-size=\'90\'>📡</text></svg>">',
        "<title>AI Digest — Archive</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        "<header>",
        "<h1>AI Digest archive</h1>",
        '<nav><a href="index.html">← latest digest</a></nav>',
        "</header>",
        '<ul class="digests">',
    ]
    if not entries:
        parts.append("<li>No archived digests yet.</li>")
    for d, name in entries:
        parts.append(
            f'<li><a href="archive/{html.escape(name)}">'
            f'<span class="date">{d.strftime("%d %b %Y")}</span>'
            f'<span class="day">{d.strftime("%A")}</span>'
            f"</a></li>"
        )
    parts.append("</ul></body></html>")

    out = DOCS / "archive.html"
    out.write_text("\n".join(parts))
    print(f"[info] wrote {out} ({len(entries)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
