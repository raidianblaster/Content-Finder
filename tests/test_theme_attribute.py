"""Both rendered pages must declare an explicit dark theme on <html>.

Locking down `data-theme="dark"` gives a single attribute hook for any
future CSS-only theming switch — and pins the invariant that the homepage
and archive ship the same theme declaration.

Note: both the homepage and the archive <html> tag carry data-mast="compact"
/ data-date="prominent" so their mastheads render at the same density. The
shared invariant pinned here is data-theme="dark" on the element itself.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import content_finder as cf
import render_index as ri


def test_homepage_html_tag_declares_dark_theme():
    out = cf.render_html([], top_n=0, page_date=date(2026, 5, 7))
    # data-theme="dark" must live on the <html> element itself, not buried in a child.
    assert re.search(r'<html\b[^>]*data-theme="dark"[^>]*>', out), \
        "homepage <html> tag must carry data-theme=\"dark\""


def test_archive_html_tag_declares_dark_theme():
    out = ri.render_archive_html(
        [(datetime(2026, 5, 7), "2026-05-07.html")]
    )
    assert re.search(r'<html\b[^>]*data-theme="dark"[^>]*>', out), \
        "archive <html> tag must carry data-theme=\"dark\""


def test_homepage_and_archive_both_declare_dark_theme():
    """Both pages carry data-theme="dark" on <html>; extra attributes may differ."""
    home = cf.render_html([], top_n=0, page_date=date(2026, 5, 7))
    arch = ri.render_archive_html([])
    assert re.search(r'<html\b[^>]*data-theme="dark"[^>]*>', home)
    assert re.search(r'<html\b[^>]*data-theme="dark"[^>]*>', arch)
