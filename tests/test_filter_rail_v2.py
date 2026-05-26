"""V2 filter rail markup tests.

The V2 redesign replaces the inline `.chips` row with a sticky `.rail`:

  <div class="rail">
    <div class="wrap rail-inner">
      <button class="chip" data-tag="all" aria-pressed="true">
        <span>All</span><span class="n">10</span>
      </button>
      ...one chip per taxonomy tag...
    </div>
  </div>

The count moves out of the chip's text into a dedicated `<span class="n">`
badge, and active state uses `aria-pressed="true"` instead of `.is-active`.
"""
from __future__ import annotations

import re
from datetime import date

import content_finder as cf


COUNTS = {"Models": 3, "Agents": 5, "Tooling": 2,
          "Regulation": 1, "Enterprise": 0, "Research": 0}


def test_rail_wraps_chip_row():
    bar = cf.render_chip_bar(counts=COUNTS)
    assert '<div class="rail">' in bar, "missing sticky .rail wrapper"
    assert 'class="rail-inner"' in bar or 'rail-inner' in bar, \
        "missing .rail-inner scroll container"


def test_rail_emits_seven_chips_with_data_tag():
    bar = cf.render_chip_bar(counts=COUNTS)
    chips = re.findall(r'<button[^>]*class="chip[^"]*"[^>]*data-tag="([^"]+)"', bar)
    assert chips[0] == "all"
    assert set(chips[1:]) == {"Models", "Agents", "Tooling",
                              "Regulation", "Enterprise", "Research"}
    assert len(chips) == 7


def test_rail_chips_use_aria_pressed_for_active_state():
    bar = cf.render_chip_bar(counts=COUNTS)
    # The "All" chip is pressed by default
    assert re.search(
        r'<button[^>]*data-tag="all"[^>]*aria-pressed="true"',
        bar,
    ), "All chip should be aria-pressed=true by default"
    # Every other chip is aria-pressed="false"
    others = re.findall(r'<button[^>]*data-tag="(Models|Agents|Tooling|Regulation|Enterprise|Research)"[^>]*aria-pressed="false"', bar)
    assert len(others) == 6


def test_rail_chip_count_lives_in_n_badge():
    """V2 moves the count out of the chip's text into a <span class="n"> badge,
    so the active-state colour shift can target the badge separately."""
    bar = cf.render_chip_bar(counts=COUNTS)
    # Models = 3 should appear inside a .n badge, not as "(3)" suffix
    assert re.search(
        r'<button[^>]*data-tag="Models"[^>]*>.*?<span class="n">3</span>',
        bar, re.DOTALL,
    ), "Models chip missing its .n count badge"
    # Old "(N)" parenthetical format must be gone
    assert ">Models (3)<" not in bar
    assert "(3)" not in bar


def test_rail_all_chip_shows_total_count():
    """All chip's badge shows the total item count (sum of counts ignoring
    multi-tag double-counting is misleading; instead spec uses STORIES.length).
    """
    bar = cf.render_chip_bar(counts=COUNTS, total=11)
    assert re.search(
        r'<button[^>]*data-tag="all"[^>]*>.*?<span class="n">11</span>',
        bar, re.DOTALL,
    )


def test_rail_omits_count_badges_when_no_counts_passed():
    """The no-summarize path can't tag items, so chip counts would all be 0.
    In that case the rail still renders but without the .n badges (a row of
    'All / Models / Agents / …' with no zeroes)."""
    bar = cf.render_chip_bar()
    assert "rail" in bar
    assert "class=\"n\"" not in bar


def test_rail_css_present():
    css = cf.HTML_CSS
    assert ".rail" in css
    assert ".rail-inner" in css
    assert ".chip" in css
    assert '.chip[aria-pressed="true"]' in css
    assert ".chip .n" in css


def test_rail_filter_js_uses_aria_pressed():
    """JS toggle must sync aria-pressed (not the legacy is-active class)."""
    out = cf.wrap_synthesis_html(
        "## Key takeaways\n- a\n- b\n- c\n", page_date=date(2026, 5, 26),
    )
    assert "aria-pressed" in out
    # The applyFilter handler manipulates aria-pressed on each chip
    assert "setAttribute('aria-pressed'" in out or 'setAttribute("aria-pressed"' in out
