"""Archive index page must share the homepage's dark visual identity.

Before this, render_index.py defined its own light/dark CSS via
prefers-color-scheme, so on a light-mode browser the archive looked nothing
like the (always-dark) homepage. These tests pin the parity.
"""
from __future__ import annotations

from datetime import datetime

import content_finder as cf
import render_index as ri


def _sample_entries():
    return [
        (datetime(2026, 5, 7), "2026-05-07.html"),
        (datetime(2026, 5, 6), "2026-05-06.html"),
    ]


# ---------------------------------------------------------------------------
# Shared design tokens — single source of truth
# ---------------------------------------------------------------------------

def test_archive_reuses_homepage_css_tokens():
    """The archive must embed the same HTML_CSS as the homepage so tokens
    (--bg-0, --purple, --fg, etc.) cannot drift between the two pages."""
    out = ri.render_archive_html(_sample_entries())
    # Sentinel substrings unique to the homepage CSS spec.
    assert "#0a0a0d" in out
    assert "#111116" in out
    assert "--purple" in out
    assert "--fg-dim" in out
    # The cheapest guarantee: the homepage CSS string itself is present.
    assert cf.HTML_CSS in out


def test_archive_does_not_use_prefers_color_scheme():
    """The homepage is dark always; the archive must not flip to light on a
    light-mode browser. No media-query-driven palette swap is allowed."""
    out = ri.render_archive_html(_sample_entries())
    assert "prefers-color-scheme" not in out


def test_archive_loads_dm_sans_and_dm_mono():
    out = ri.render_archive_html(_sample_entries())
    assert "fonts.googleapis.com" in out
    assert "DM+Sans" in out
    assert "DM+Mono" in out


def test_archive_has_dark_theme_color_meta():
    out = ri.render_archive_html(_sample_entries())
    assert '<meta name="theme-color" content="#0a0a0d">' in out


# ---------------------------------------------------------------------------
# Page shell parity
# ---------------------------------------------------------------------------

def test_archive_uses_page_shell_and_topbar():
    out = ri.render_archive_html(_sample_entries())
    assert '<div class="page">' in out
    assert 'class="topbar"' in out
    assert 'class="topbar-title"' in out
    assert "AI Digest" in out


def test_archive_topbar_links_back_to_latest():
    out = ri.render_archive_html(_sample_entries())
    # Some clickable nav back to the latest digest.
    assert 'href="index.html"' in out


def test_archive_title_is_archive_specific():
    out = ri.render_archive_html(_sample_entries())
    assert "<title>AI Digest — Archive</title>" in out


# ---------------------------------------------------------------------------
# Content rendering — must keep working through the redesign
# ---------------------------------------------------------------------------

def test_archive_lists_entries_with_date_and_day():
    out = ri.render_archive_html(_sample_entries())
    # Date strings (formatted) and weekdays both render.
    assert "07 May 2026" in out
    assert "Thursday" in out
    assert "06 May 2026" in out
    assert "Wednesday" in out
    # Each entry links into the dated archive file.
    assert 'href="archive/2026-05-07.html"' in out
    assert 'href="archive/2026-05-06.html"' in out


def test_archive_handles_empty_archive():
    out = ri.render_archive_html([])
    assert "No archived digests yet." in out
    # Shell must still be present even with no entries.
    assert '<div class="page">' in out
    assert cf.HTML_CSS in out


def test_archive_escapes_filenames():
    out = ri.render_archive_html(
        [(datetime(2026, 5, 7), '2026-05-07"<bad>.html')]
    )
    assert '"<bad>' not in out  # raw injection must be escaped
    assert "&quot;&lt;bad&gt;" in out or "&#34;&lt;bad&gt;" in out
