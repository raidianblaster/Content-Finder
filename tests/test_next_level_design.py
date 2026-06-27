"""Next-Level design deltas (the "Content Finder - Next Level" build sheet).

Eight incremental enhancements layered on the shipped V2 layout:
  1. Saturated/unified category palette + accent
  2. Brighter body text
  3. Serif display headlines (Newsreader)
  4. Hero glow + grain
  5. Today's pulse strip
  6. Ghost section numbers
  7. Wider takeaways (2-col)
  8. Live-filter glow on active chip

Each block below is the red→green test for one delta. Targets HTML_CSS,
_page_shell / wrap_synthesis_html, render_chip_bar, render_pulse_strip,
_render_synthesis_sections.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import content_finder as cf


# ---------------------------------------------------------------------------
# 1. Saturated/unified category palette + accent
# ---------------------------------------------------------------------------

# The Next-Level palette: one saturated hue per category, shared by chips
# (.chip[data-tag]) and story tags (.tag[data-cat]) via the same --cat-* token.
NEXT_LEVEL_CATS = {
    "models": "#8ab4ff",
    "agents": "#e3ab5f",
    "tooling": "#79c89a",
    "regulation": "#e58fa6",
    "enterprise": "#b69ce8",
    "research": "#6fc2cf",
}


def test_category_tokens_use_next_level_saturated_hues():
    css = cf.HTML_CSS
    for name, hex_val in NEXT_LEVEL_CATS.items():
        assert re.search(rf"--cat-{name}:\s*{hex_val}", css, re.IGNORECASE), \
            f"--cat-{name} should be bound to the Next-Level hue {hex_val}"


def test_accent_token_bumped_to_next_level_amber():
    css = cf.HTML_CSS
    assert re.search(r"--accent:\s*#e8b14f", css), \
        "--accent should be bound to the Next-Level amber #e8b14f"
    # The old V2 amber must be fully gone (no stragglers in derived tokens).
    assert "#e8b765" not in css, "legacy V2 amber #e8b765 still present"


def test_accent_soft_and_line_track_the_new_amber():
    """The rgba accent-soft / accent-line tints must use the new amber's
    RGB channels (232,177,79), not the old (232,183,101)."""
    css = cf.HTML_CSS
    assert "232, 177, 79" in css or "232,177,79" in css, \
        "accent rgba tints should track the new amber channels"
    assert "183, 101" not in css, "old amber rgba channels still present"


# ---------------------------------------------------------------------------
# 2. Brighter body text
# ---------------------------------------------------------------------------

def _hex_channels(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def test_body_text_token_is_brighter_than_v2():
    """--fg-2 drives dek/summary/take-body. Next-Level lifts its contrast for
    comfortable reading: every channel at least as bright as the old #b3aea1,
    and strictly brighter overall."""
    css = cf.HTML_CSS
    m = re.search(r"--fg-2:\s*(#[0-9a-fA-F]{6})", css)
    assert m, "--fg-2 token missing"
    new = _hex_channels(m.group(1))
    old = _hex_channels("#b3aea1")
    assert all(n >= o for n, o in zip(new, old)), \
        f"--fg-2 {m.group(1)} dimmer on some channel than old #b3aea1"
    assert sum(new) > sum(old), "--fg-2 should be brighter overall than #b3aea1"


# ---------------------------------------------------------------------------
# 3. Serif display headlines (Newsreader)
# ---------------------------------------------------------------------------

def test_newsreader_serif_loaded_via_google_fonts():
    out = cf.wrap_synthesis_html(
        "## Key takeaways\n- a\n- b\n- c\n", page_date=date(2026, 5, 2)
    )
    assert "fonts.googleapis.com" in out
    assert "Newsreader" in out
    # Existing body + mono families must still load alongside it.
    assert "Hanken+Grotesk" in out
    assert "JetBrains+Mono" in out


def test_display_font_token_is_a_serif_stack():
    css = cf.HTML_CSS
    m = re.search(r"--font-display:\s*([^;]+);", css)
    assert m, "--font-display token missing"
    stack = m.group(1)
    assert "Newsreader" in stack
    assert "serif" in stack


def test_display_headlines_use_serif_display_font():
    """Masthead title + section headings + story/take headlines render in the
    editorial serif display face (italic for the editorial feel)."""
    css = cf.HTML_CSS
    for selector in [".mast-title", ".sec-title", ".story-title", ".take-head"]:
        m = re.search(rf"{re.escape(selector)}\s*\{{[^}}]*\}}", css)
        assert m, f"{selector} rule missing"
        assert "var(--font-display)" in m.group(0), \
            f"{selector} should use the serif display font"
    # The masthead title carries the italic editorial styling.
    mast = re.search(r"\.mast-title\s*\{[^}]*\}", css).group(0)
    assert "font-style: italic" in mast


# ---------------------------------------------------------------------------
# 4. Hero glow + grain
# ---------------------------------------------------------------------------

def test_masthead_has_film_grain_layer():
    """The hero gets a subtle SVG-noise film grain, rendered as a decorative,
    non-interactive ::before so it never intercepts clicks or screen readers."""
    css = cf.HTML_CSS
    assert "feTurbulence" in css or "fractalNoise" in css, \
        "grain SVG noise filter missing"
    m = re.search(r"\.masthead::before\s*\{[^}]*\}", css)
    assert m, ".masthead::before grain layer missing"
    grain = m.group(0)
    assert "pointer-events: none" in grain, "grain layer must be non-interactive"
    # Masthead is a positioned container so the grain/glow can absolutely fill it.
    mast = re.search(r"\.masthead\s*\{[^}]*\}", css).group(0)
    assert "position: relative" in mast


def test_masthead_has_radial_glow_layer():
    css = cf.HTML_CSS
    m = re.search(r"\.masthead::after\s*\{[^}]*\}", css)
    assert m, ".masthead::after glow layer missing"
    glow = m.group(0)
    assert "radial-gradient" in glow
    assert "pointer-events: none" in glow


# ---------------------------------------------------------------------------
# 5. Today's pulse strip
# ---------------------------------------------------------------------------

PULSE_FIXTURE_MD = """## Key takeaways
- One takeaway. [Ref](https://example.com/a)
- Two takeaway.

## Top story
- **Top thing** — body. **So what:** matters. [Simon Willison](https://example.com/top) {tags: Models, Regulation}

## Models & capability releases
- **Model A** — body. **So what:** matters. [A](https://example.com/m1) {tags: Models}
- **Model B** — body. **So what:** matters. [B](https://example.com/m2) {tags: Models, Enterprise}
"""


def test_render_pulse_strip_segment_per_nonzero_category_proportional():
    counts = {"Models": 5, "Agents": 5, "Tooling": 1,
              "Regulation": 6, "Enterprise": 4, "Research": 5}
    out = cf.render_pulse_strip(counts)
    assert 'class="pulse"' in out
    assert '<div class="pulse-bar">' in out
    # Segments are empty divs, so scan the whole strip rather than a naive
    # non-greedy capture of the bar container.
    segs = re.findall(
        r'<div class="pulse-seg"[^>]*data-cat="([^"]+)"[^>]*'
        r'style="[^"]*flex-grow:\s*(\d+)',
        out,
    )
    assert {c: int(n) for c, n in segs} == counts, \
        "each category needs a proportional (flex-grow=count) segment"


def test_render_pulse_strip_omits_zero_categories():
    counts = {"Models": 3, "Agents": 0, "Tooling": 0,
              "Regulation": 2, "Enterprise": 0, "Research": 0}
    out = cf.render_pulse_strip(counts)
    cats = re.findall(r'class="pulse-seg"[^>]*data-cat="([^"]+)"', out)
    assert cats == ["Models", "Regulation"], "zero-count categories must be omitted"
    assert "Agents" not in out


def test_render_pulse_strip_empty_without_counts():
    assert cf.render_pulse_strip(None) == ""
    assert cf.render_pulse_strip({"Models": 0, "Agents": 0}) == ""


def test_render_pulse_legend_shows_name_and_count():
    out = cf.render_pulse_strip({"Models": 3, "Regulation": 2})
    legend_m = re.search(r'<div class="pulse-legend">(.*?)</div>\s*</section>', out, re.DOTALL)
    assert legend_m, "missing .pulse-legend"
    legend = legend_m.group(1)
    assert "Models 3" in re.sub(r"<[^>]+>", " ", legend)
    assert "Regulation 2" in re.sub(r"<[^>]+>", " ", legend)
    # each legend item carries a category-tinted dot
    assert 'class="pulse-dot" data-cat="Models"' in legend


def test_pulse_strip_in_synthesis_page_between_rail_and_takeaways():
    out = cf.wrap_synthesis_html(PULSE_FIXTURE_MD, page_date=date(2026, 5, 2))
    assert 'class="pulse"' in out
    assert out.index('class="rail"') < out.index('class="pulse"') < out.index('id="takeaways"')


def test_pulse_strip_absent_on_no_summarize_path():
    """The ranked --no-summarize path has no tags, so (like the chip counts)
    the pulse strip is suppressed rather than rendered all-zero."""
    items = [
        cf.Item(title="T", url="https://example.com/x", source="Simon Willison",
                published=datetime(2026, 5, 1, tzinfo=timezone.utc), summary="agentic llm"),
    ]
    items[0].score = 9.0
    out = cf.render_html(items, top_n=1, page_date=date(2026, 5, 2))
    assert 'class="pulse"' not in out


def test_pulse_bar_css_rule_present():
    css = cf.HTML_CSS
    assert re.search(r"\.pulse-bar\s*\{", css), ".pulse-bar CSS rule missing"
    assert re.search(r'\.pulse-seg\[data-cat="Models"\]', css), \
        "per-category pulse-seg tint missing"


# ---------------------------------------------------------------------------
# 6. Ghost section numbers
# ---------------------------------------------------------------------------

def test_story_sections_carry_ghost_numbers():
    """Each story section gets a giant low-opacity numeral matching its
    zero-padded section number. The takeaways block does not."""
    out = cf.wrap_synthesis_html(PULSE_FIXTURE_MD, page_date=date(2026, 5, 2))
    ghosts = re.findall(r'<div class="sec-ghost"[^>]*>([^<]+)</div>', out)
    # PULSE_FIXTURE_MD → Top story (01) + Models & Capabilities (02)
    assert ghosts == ["01", "02"]
    take = re.search(
        r'<section class="block" id="takeaways">.*?</section>', out, re.DOTALL
    ).group(0)
    assert "sec-ghost" not in take, "takeaways block should not carry a ghost numeral"


def test_sec_ghost_is_decorative_and_faint():
    css = cf.HTML_CSS
    m = re.search(r"\.sec-ghost\s*\{[^}]*\}", css)
    assert m, ".sec-ghost CSS rule missing"
    rule = m.group(0)
    assert "position: absolute" in rule
    assert "pointer-events: none" in rule
    # Low opacity so it reads as a watermark, not foreground text.
    op = re.search(r"opacity:\s*([0-9.]+)", rule)
    assert op and float(op.group(1)) <= 0.1
    # The section is a positioned container for the absolute numeral.
    block = re.search(r"section\.block\s*\{[^}]*\}", css).group(0)
    assert "position: relative" in block


# ---------------------------------------------------------------------------
# 7. Wider takeaways (2-col)
# ---------------------------------------------------------------------------

def test_takeaways_grid_widens_to_two_columns():
    """The desktop takeaways grid drops from 3 cramped columns to 2 wider ones
    (fixes the 4-word measure). Single-column mobile base is unchanged."""
    css = cf.HTML_CSS
    assert "1fr 1fr 1fr" not in css, "3-column takeaways grid should be gone"
    assert re.search(r"\.takes\s*\{\s*grid-template-columns:\s*1fr 1fr\s*;", css), \
        "desktop .takes should be a 2-column grid"


# ---------------------------------------------------------------------------
# 8. Live-filter glow on active chip
# ---------------------------------------------------------------------------

def test_active_category_chip_has_hue_glow():
    """When a category filter is active, its chip glows in its own hue
    (per-category box-shadow), not just a flat fill."""
    css = cf.HTML_CSS
    for cat in ["Models", "Agents", "Tooling", "Regulation", "Enterprise", "Research"]:
        m = re.search(
            rf'\.chip\[data-tag="{cat}"\]\[aria-pressed="true"\]\s*\{{[^}}]*\}}', css
        )
        assert m, f"active rule for {cat} missing"
        rule = m.group(0)
        assert "box-shadow" in rule, f"active {cat} chip should glow"
        assert f"--cat-{cat.lower()}" in rule, f"{cat} glow should use its own hue"
