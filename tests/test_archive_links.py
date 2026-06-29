"""Relative-link rewriting for digests copied into docs/archive/.

A digest copied from docs/index.html into docs/archive/<date>.html lives one
directory deeper, so its root-relative topbar links must gain a ../ prefix.
Before this fix the workflow only rewrote the Archive link, leaving the CF
brand and the "Today" nav link pointing at docs/archive/index.html (404).
"""
from __future__ import annotations

import content_finder as cf


def _sample_topbar() -> str:
    return (
        '<a class="brand" href="index.html"><div class="brand-mark">CF</div></a>'
        '<nav class="topnav">'
        '<a href="index.html" class="active">Today</a>'
        '<a href="archive.html">Archive</a>'
        '</nav>'
    )


def test_relativize_rewrites_index_links():
    out = cf.relativize_archived_links(_sample_topbar())
    # Both the brand and the Today nav link must now climb out of /archive/.
    assert out.count('href="../index.html"') == 2
    # No bare index.html link survives.
    assert 'href="index.html"' not in out


def test_relativize_rewrites_archive_link():
    out = cf.relativize_archived_links(_sample_topbar())
    assert 'href="../archive.html"' in out
    assert 'href="archive.html"' not in out


def test_relativize_is_idempotent():
    once = cf.relativize_archived_links(_sample_topbar())
    twice = cf.relativize_archived_links(once)
    assert once == twice


def test_relativize_leaves_external_and_anchor_links_untouched():
    src = (
        '<a href="#takeaways">Takeaways</a>'
        '<a href="https://github.com/raidianblaster/Content-Finder">repo</a>'
    )
    out = cf.relativize_archived_links(src)
    assert out == src
