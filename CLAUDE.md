# Content Finder

CLI + GitHub Pages digest of credible agentic-AI / LLM news for an AI PM in a regulated corporate environment. Source quality is the #1 axis — adding sources is fine; lowering the credibility bar is not.

Live page: https://raidianblaster.github.io/Content-Finder/

## Layout

- `content_finder.py` — single-file pipeline (~1500 lines). Sections, in order: sources/keywords → `Item` dataclass → fetchers (`fetch_rss`, `fetch_hn`) → scoring/dedupe (`score_item`, `dedupe`, `apply_source_cap`) → renderers (`render_plain`, `render_html`, chip bar, card builders) → `synthesize_with_claude` → `gather` → `main`.
- `render_index.py` — rebuilds `docs/archive.html` from files in `docs/archive/`.
- `.github/workflows/daily.yml` — cron `30 22 * * *` UTC = 06:30 HKT. Uses `actions/checkout@v6` and `actions/setup-python@v6` (both bundle Node 24). Do **not** downgrade these to v4/v5 — that's what triggered the prior "Node.js 20 deprecated" warning. Node 20 is fully removed from runners September 2026.
- `docs/` — GitHub Pages root. `index.html` is overwritten daily; `archive/YYYY-MM-DD.html` is preserved.
- `tests/` — pytest. Tests are tightly coupled to the rendered HTML (chip bar, cards, tags, source cap). Run before any rendering change.

## Constraints (load-bearing)

- **PWA + GitHub Pages is the deliberate ceiling.** No backend service, no native app, no user accounts.
- **No Anthropic API key in regular use.** Code must work end-to-end with `--no-summarize` / no key set. The `synthesize_with_claude` path is opt-in only.
- **Dates anchor on HKT, not UTC.** GH Actions runs at 22:30 UTC, which is the *next* HKT day. Use `today_hkt()` for any user-visible date; never `datetime.now().date()`.
- **Regulated env.** Pipeline only handles public news. Don't introduce anything that ships internal/private data outbound.
- **Trend-tracking framing.** User doesn't have hands-on access to bleeding-edge tools — phrase commentary at PM/strategy level, not "I ran this and...".
- **Newsletter consolidation is the product north star.** A feature is worth building if it moves a newsletter the user currently subscribes to into the "unsubscribe-able" column. Capability for capability's sake doesn't pass the bar.

## Conventions

- Source-trust weights live inside `score_item()` (not in a config file yet — see roadmap).
- Tag taxonomy is fixed: `Models · Agents · Tooling · Regulation · Enterprise · Research`. Defined once as `TAG_TAXONOMY` and consumed by both the LLM prompt and the chip filter bar — keep them in sync.
- Per-source cap defaults to 3 (`apply_source_cap`) to stop a hot day on one outlet from crowding out diversity.
- No emojis in generated digests except the existing chip/section UI.
- **Per-item LLM summary schema is fixed:** `{tldr, what_changed, why_it_matters, claims[], code_or_api_changes[], numbers[], governance_signals[], open_questions[]}`. Any LLM-driven feature (per-item annotation, weekly rollup, citations) reads/writes this shape. Don't drift the field set without updating every consumer.

## Development workflow (TDD — required)

Every feature and bugfix in this repo follows test-driven development. Not negotiable, not "where convenient" — the existing test suite is tightly coupled to behavior (HTML rendering, scoring, source cap, tags) precisely because we work this way. Skipping tests once erodes the suite's value for everyone after.

**The loop, every session:**

1. **Plan first.** Write down the feature's observable behavior before touching code — inputs, outputs, edge cases. If you can't list them, the feature isn't scoped enough yet.
2. **Red.** Add or extend a test in `tests/` that asserts the new behavior. Run `pytest -q` and confirm it fails for the *right* reason (not an import error). For pure functions, test the function directly. For rendering changes, assert against the rendered HTML in the style of `test_design.py` / `test_card_robustness.py`.
3. **Green.** Write the minimum code in `content_finder.py` (or sibling) that makes the new test pass. Resist adding adjacent improvements — they go in a follow-up commit with their own tests.
4. **Refactor.** Only after green. Tests must stay green throughout.
5. **Full suite.** `.venv/bin/python -m pytest -q` must pass before commit. No `-k` shortcuts at commit time.
6. **End-of-session note.** Before stopping, summarize what landed, what's still red, and the next test to write.

**What counts as a test:**

- Pure-function changes (scoring, dedup, tagging, URL canonicalization, reading-time, date math): unit test with explicit inputs/outputs.
- Rendering changes (chips, cards, sections, tags): assert against the HTML string the way existing render tests do.
- Config/source changes (`sources.yml`, keyword weights): a parsing/loading test, plus a smoke test that the loaded config feeds the pipeline.
- LLM-touching code (`synthesize_with_claude` and successors): test the prompt construction and the JSON-schema parsing — never the network call. Mock at the boundary.

**Exemptions (rare):**

- One-line typo fixes in user-facing strings.
- Doc-only changes (`*.md`).
- Anything else: write the test.

If a test is genuinely hard to write, that's a design signal — pause and ask whether the code under test should be restructured (extract a pure function, push I/O to the edge), not whether the test can be skipped.

## Common commands

```bash
# Local plain run (no API key)
.venv/bin/python content_finder.py --no-summarize --days 2

# Local HTML preview matching the live page
.venv/bin/python content_finder.py --no-summarize --format html --days 7 --top 25 --out docs/index.html
open docs/index.html

# Tests
.venv/bin/python -m pytest -q

# Manually trigger the daily workflow
# https://github.com/raidianblaster/Content-Finder/actions → Daily AI digest → Run workflow
```

The shell alias `aidigest` runs the venv Python against `content_finder.py`.

## Roadmap

`ROADMAP.md` is the source of truth. Phase 1 ("now") items still open:
1. Cross-day deduplication via a `seen.json` state file (today's hot story shouldn't resurface for 5 days).
2. Move `RSS_SOURCES` / `HN_QUERIES` / `KEYWORD_WEIGHTS` into a `sources.yml` so they're editable from the GitHub mobile web UI on iPad without a Python edit.

Anti-features (deliberately out of scope): native mobile app, multi-user, comments, real-time push.
