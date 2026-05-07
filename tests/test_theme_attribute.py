"""Both rendered pages must declare an explicit dark theme on <html>.

Locking down `data-theme="dark"` gives a single attribute hook for any
future CSS-only theming switch — and pins the invariant that the homepage
and archive ship the same theme declaration.
"""
from __future__ import annotations

from datetime import date, datetime

import content_finder as cf
import render_index as ri


def test_homepage_html_tag_declares_dark_theme():
    out = cf.render_html([], top_n=0, page_date=date(2026, 5, 7))
    assert 'data-theme="dark"' in out
    # Must live on the <html> element itself, not buried in a child.
    assert '<html lang="en" data-theme="dark">' in out


def test_archive_html_tag_declares_dark_theme():
    out = ri.render_archive_html(
        [(datetime(2026, 5, 7), "2026-05-07.html")]
    )
    assert 'data-theme="dark"' in out
    assert '<html lang="en" data-theme="dark">' in out


def test_homepage_and_archive_use_identical_html_tag():
    """If they ever drift, the parity story is broken."""
    home = cf.render_html([], top_n=0, page_date=date(2026, 5, 7))
    arch = ri.render_archive_html([])
    needle = '<html lang="en" data-theme="dark">'
    assert needle in home
    assert needle in arch
