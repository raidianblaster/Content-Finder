"""V2 archive page markup tests.

The V2 redesign turns the archive into a focused flat list:

  <section class="masthead">
    <div class="kicker">● AI Digest Archive</div>
    <h1 class="mast-title">All past <span class="accent">digests.</span></h1>
    <p class="mast-sub">…</p>
    <div class="topline">
      <a class="latest-link">← Latest digest</a>
      <span class="count"><b>N</b> archived digests</span>
    </div>
  </section>

  <div class="arch-list">
    <a class="arch-row is-today" href="archive/YYYY-MM-DD.html">
      <span class="arch-date">26 May 2026 <span class="today-pill">Today</span></span>
      <span class="arch-day">Tuesday</span>
      <span class="arch-arrow">→</span>
    </a>
    …
  </div>
"""
from __future__ import annotations

import re
from datetime import datetime, date

import render_index as ri


def _entries(n: int = 5):
    """Generate n entries newest-first ending on 26 May 2026."""
    out = []
    base = date(2026, 5, 26)
    for i in range(n):
        d = datetime(base.year, base.month, base.day - i)
        out.append((d, f"{d.strftime('%Y-%m-%d')}.html"))
    return out


# ---------------------------------------------------------------------------
# Topbar + nav (Archive active)
# ---------------------------------------------------------------------------

def test_archive_topbar_marks_archive_link_active():
    out = ri.render_archive_html(_entries(3))
    assert 'class="topbar"' in out
    # Both Today and Archive links present in the topnav
    assert ">Today</a>" in out
    # Archive link carries the active class
    assert re.search(r'<a [^>]*class="active"[^>]*>Archive</a>', out)


# ---------------------------------------------------------------------------
# Masthead — kicker + accented title + subtitle
# ---------------------------------------------------------------------------

def test_archive_masthead_kicker_says_ai_digest_archive():
    out = ri.render_archive_html(_entries(3))
    assert '<div class="kicker">' in out
    assert "AI Digest Archive" in out
    assert '<span class="dot"></span>' in out


def test_archive_masthead_title_has_accent_span_on_digests():
    out = ri.render_archive_html(_entries(3))
    assert '<h1 class="mast-title">All past <span class="accent">digests.</span></h1>' in out


def test_archive_masthead_subtitle_present():
    out = ri.render_archive_html(_entries(3))
    assert '<p class="mast-sub">' in out
    assert "newest first" in out.lower()


# ---------------------------------------------------------------------------
# Topline row — latest link + count
# ---------------------------------------------------------------------------

def test_archive_topline_has_latest_link_and_count():
    entries = _entries(7)
    out = ri.render_archive_html(entries)
    topline = re.search(r'<div class="topline">(.*?)</div>', out, re.DOTALL)
    assert topline, "missing .topline row"
    body = topline.group(1)
    # Back-arrow link to today's digest
    assert re.search(r'<a class="latest-link"[^>]*href="index\.html"', body)
    assert "←" in body
    assert "Latest digest" in body
    # Count line: "<b>7</b> archived digests"
    assert re.search(r'<span class="count">\s*<b[^>]*>7</b>\s*archived digests', body)


# ---------------------------------------------------------------------------
# Flat list of dated rows
# ---------------------------------------------------------------------------

def test_archive_list_renders_one_row_per_entry():
    out = ri.render_archive_html(_entries(5))
    rows = re.findall(r'<a class="arch-row[^"]*"[^>]*href="archive/[^"]+\.html"', out)
    assert len(rows) == 5


def test_archive_row_shows_date_weekday_and_arrow():
    out = ri.render_archive_html(_entries(3))
    # First row = today (26 May 2026, Tuesday)
    assert "26 May 2026" in out
    assert "Tuesday" in out
    # Arrow glyph (hidden on mobile via CSS, still in markup)
    assert re.search(r'<span class="arch-arrow">[→]+</span>', out)


def test_archive_row_links_to_dated_html_files():
    out = ri.render_archive_html(_entries(3))
    assert 'href="archive/2026-05-26.html"' in out
    assert 'href="archive/2026-05-25.html"' in out
    assert 'href="archive/2026-05-24.html"' in out


# ---------------------------------------------------------------------------
# Today highlight
# ---------------------------------------------------------------------------

def test_archive_first_row_has_today_modifier_and_pill():
    """First entry is the newest = today, gets .is-today + a Today pill."""
    out = ri.render_archive_html(_entries(3))
    # First row carries .is-today
    first_row = re.search(
        r'(<a class="arch-row[^"]*"[^>]*href="archive/2026-05-26\.html"[^>]*>.*?</a>)',
        out, re.DOTALL,
    )
    assert first_row, "first row not found"
    first = first_row.group(1)
    assert "is-today" in first
    assert '<span class="today-pill">Today</span>' in first


def test_archive_non_today_rows_omit_today_pill():
    out = ri.render_archive_html(_entries(3))
    # The second row (25 May) must NOT carry the Today pill
    second_row_m = re.search(
        r'<a class="arch-row[^"]*"[^>]*href="archive/2026-05-25\.html"[^>]*>(.*?)</a>',
        out, re.DOTALL,
    )
    assert second_row_m
    assert "today-pill" not in second_row_m.group(1)
    assert "is-today" not in second_row_m.group(0)


# ---------------------------------------------------------------------------
# Container width override — archive uses 760px, not the 920px page col
# ---------------------------------------------------------------------------

def test_archive_overrides_col_width_to_760():
    out = ri.render_archive_html(_entries(3))
    # The archive narrows --col so the list reads as a focused column.
    assert "760px" in out


# ---------------------------------------------------------------------------
# Empty + escaping
# ---------------------------------------------------------------------------

def test_archive_empty_state_still_renders_shell():
    out = ri.render_archive_html([])
    assert '<section class="masthead">' in out
    assert "No archived digests yet" in out or "0 archived" in out


def test_archive_escapes_dangerous_filenames():
    out = ri.render_archive_html(
        [(datetime(2026, 5, 7), '2026-05-07"<bad>.html')]
    )
    assert '"<bad>' not in out
    assert "&quot;&lt;bad&gt;" in out or "&#34;&lt;bad&gt;" in out
