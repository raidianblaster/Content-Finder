# Content Finder

CLI + GitHub Pages digest of credible agentic-AI / LLM news for an AI PM in a regulated corporate environment. Source quality is the #1 axis — adding sources is fine; lowering the credibility bar is not.

Live page: https://raidianblaster.github.io/Content-Finder/

## Layout

- `content_finder.py` — single-file pipeline (~2300 lines). Sections, in order: sources/keywords → `Item` dataclass → fetchers (`fetch_rss`, `fetch_hn`) → scoring/dedupe (`score_components` — per-feature breakdown: keyword/recency/recency_term/src_bonus/hn_bonus/total, feeding the filter log for #9/M2.1 self-tuning groundwork; `score_item`, `dedupe`, `apply_source_cap`) → renderers (`render_plain`, `render_html`, chip bar, card builders) → `synthesize_with_claude` → `gather` → `main`. Also writes a per-run **filter log** to `docs/logs/<date>.json` (every item the pipeline saw + the stage that decided its fate) — this is the substrate the review/judge tooling reads.
- `render_index.py` — rebuilds `docs/archive.html` from files in `docs/archive/`.
- **M0 harness (landed — not future):** the tracing/review/judge loop is real code, not roadmap:
  - `review.py` — `build <date>` emits the labelable `docs/review/<date>.html` from the filter log; `build-index` rebuilds `docs/review/index.html`. Verdicts persist to `feedback/<date>.jsonl`.
  - `judge.py` — `run <date>` sends a curated subset of filter decisions to Claude Haiku and writes `docs/review/<date>.judge.json`, inlined into the review HTML to flag suspect keeps/drops. Opt-in (needs a key); failures are swallowed so the digest still ships.
  - `tracing.py` / `traces.py` — every Claude call appends one row to `docs/logs/traces.jsonl` (tokens, cost, latency, model, prompt_version). `python traces.py` rolls it up. Tracing must never break the pipeline.
- `prompts/synthesis_system.md` — the synthesis system prompt lives **here**, not inline. `content_finder.py` reads it at import (`SYSTEM_PROMPT`) and stamps `PROMPT_VERSION` ("v2") into traces. Bump the version when the prompt changes.
- `.github/workflows/daily.yml` — cron `7 22 * * *` UTC ≈ 06:07 HKT (off-peak; lands ~06:15–06:25). Steps run in order: digest → `render_index.py` → `review.py build` → `judge.py run` → rebuild review → refresh `latest.html` alias → `review.py build-index`. Uses `actions/checkout@v6` and `actions/setup-python@v6` (both bundle Node 24). Do **not** downgrade these to v4/v5 — that's what triggered the prior "Node.js 20 deprecated" warning. Node 20 is fully removed from runners September 2026.
- `docs/` — GitHub Pages root. `index.html` is overwritten daily; `archive/YYYY-MM-DD.html` is preserved. `docs/logs/` (filter logs + trace ledger) and `docs/review/` (review pages + judge JSON) are generated, not hand-edited.
- `tests/` — pytest. Tests are tightly coupled to the rendered HTML (chip bar, cards, tags, source cap). Run before any rendering change.
- `AGENTS.md` is a parallel copy of this file for Codex/other agents — **keep the two in sync** when you change shared facts here.

## Constraints (load-bearing)

- **PWA + GitHub Pages is the deliberate ceiling.** No backend service, no native app, no user accounts.
- **No Anthropic API key in regular use.** Code must work end-to-end with `--no-summarize` / no key set. The `synthesize_with_claude` path is opt-in only.
- **Dates anchor on HKT, not UTC.** GH Actions runs at 22:30 UTC, which is the *next* HKT day. Use `today_hkt()` for any user-visible date; never `datetime.now().date()`.
- **Regulated env.** Pipeline only handles public news. Don't introduce anything that ships internal/private data outbound.
- **Trend-tracking framing.** User doesn't have hands-on access to bleeding-edge tools — phrase commentary at PM/strategy level, not "I ran this and...".
- **Newsletter consolidation is the product north star.** A feature is worth building if it moves a newsletter the user currently subscribes to into the "unsubscribe-able" column. Capability for capability's sake doesn't pass the bar.

## Conventions

- Source-trust weights live in `sources.yml` (`trust: 0–5` per source), parsed by `load_sources()` into `_TRUSTED_WEIGHTS` and consumed by `score_item()` — not hardcoded.
- Tag taxonomy is fixed: `Models · Agents · Tooling · Regulation · Enterprise · Research`. Defined once as `TAG_TAXONOMY` and consumed by both the LLM prompt and the chip filter bar — keep them in sync.
- Per-source cap defaults to 3 (`apply_source_cap`) to stop a hot day on one outlet from crowding out diversity.
- No emojis in generated digests except the existing chip/section UI.
- **Per-item LLM summary schema is fixed:** `{tldr, what_changed, why_it_matters, claims[], code_or_api_changes[], numbers[], governance_signals[], open_questions[]}`. Any LLM-driven feature (per-item annotation, weekly rollup, citations) reads/writes this shape. Don't drift the field set without updating every consumer.
- **Synthesis prompt is versioned and externalized.** It lives in `prompts/synthesis_system.md`; `PROMPT_VERSION` in `content_finder.py` is stamped into every trace row. Per EDD (below), a prompt change is a probabilistic change — bump the version and ship an eval delta, don't just edit the text.
- **Review-page auto-save uses a browser-side PAT.** Labels persist back to `feedback/<date>.jsonl` via the GitHub Contents API directly from the review page (no backend). Each device stores its own fine-grained PAT in localStorage under `cf-review::__pat__`; iCloud Keychain handles autofill across Apple Safaris. Cross-device merge is *not* implemented — last-write-wins between devices.

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

### Eval-Driven Development (EDD) — the partner to TDD

Deterministic code is guarded by **unit tests** (above). Probabilistic / LLM
behaviour (scoring weights, the synthesis and judge prompts) is guarded by
**evals**: a change there should ship with an **eval delta** the same way a
deterministic change ships with a test. Until the eval harness lands
(`ROADMAP.md` Milestone 1), at minimum keep the key-free digest green — the
do-no-harm gate in `.github/workflows/ci.yml` runs `pytest` plus a no-key
`--no-summarize` render on every PR. "Vibe-checked the output" is not a merge
criterion.

## Session start checklist

Before writing any code, always run:

```bash
git pull origin main
```

`docs/index.html` is overwritten by a nightly cron — local copies go stale fast. Skipping the pull risks a merge conflict when pushing, and the cron's version of the file is always the one that should be preserved.

## Common commands

```bash
# Local plain run (no API key)
.venv/bin/python content_finder.py --no-summarize --days 2

# Local HTML preview matching the live page
.venv/bin/python content_finder.py --no-summarize --format html --days 7 --top 25 --out docs/index.html
open docs/index.html

# Tests
.venv/bin/python -m pytest -q

# Review/judge harness (operates on docs/logs/<date>.json written by a run)
.venv/bin/python review.py build 2026-05-31      # → docs/review/2026-05-31.html
.venv/bin/python judge.py run 2026-05-31         # → .judge.json (needs ANTHROPIC_API_KEY)
.venv/bin/python review.py build-index           # → docs/review/index.html

# LLM cost/latency ledger
.venv/bin/python traces.py                        # rollup of docs/logs/traces.jsonl

# Manually trigger the daily workflow
# https://github.com/raidianblaster/Content-Finder/actions → Daily AI digest → Run workflow
```

The shell alias `aidigest` runs the venv Python against `content_finder.py`.

### Review-page first-run setup (per device)

Once per device/browser, to enable auto-save of keep/drop/unsure verdicts:

1. github.com → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Repository access → **Only select repositories: Content-Finder**.
3. Repository permissions → **Contents: Read and write** (everything else stays "No access").
4. Generate, copy the `github_pat_…` string.
5. Open any review page (e.g. https://raidianblaster.github.io/Content-Finder/review/latest.html), tap the ⚙ in the footer, paste the token, **Test connection** → **Save**.

After that, every click on a keep/drop/unsure button schedules a debounced commit to `feedback/<date>.jsonl` ~10s later. The status pill in the footer reflects state (`ready` / `unsaved · saving in 10s` / `saving…` / `saved HH:MM` / `error: … · click to retry`). Token is stored in `localStorage` under the key `cf-review::__pat__`; on iOS Safari, iCloud Keychain prompts to save it and the other Apple Safaris will autofill on first paste.

## Roadmap

`ROADMAP.md` is the source of truth — a single **unified** roadmap (vision, a
six-milestone trunk, and optional side quests). The three prior roadmaps (v1
product, v2 learning ladder, v3 self-improving) are consolidated there and archived
under `roadmap-archive/` for provenance.

Trunk: **M0** Foundations (tracing, log score features / issue #9, CI do-no-harm
gate) → **M1** eval harness + gold set → **M2** self-learning core (self-tuning
scorer, structured-output synthesis, eval-gated prompts) → **M3** memory
(episodic; optional knowledge graph) → **M4** agentic core (deep-research agent,
multi-agent rollup, source-scout, MCP server) → **M5** self-improving + edge
capstone.

Current checkpoint: **M0.1–M0.3 are landed in code** — the tracing ledger and the
review/judge harness are real modules now (see Layout). The next move is **M0.4**
(fix the quarantined archive "today" test and remove the CI deselect), then **M1
eval harness**, then **M2.1 self-tuning scorer**.

Both former Phase 1 "now" items (cross-day dedup; `sources.yml`) are **landed**.

Note: `ROADMAP.md` §3 defines where two constraints below intentionally bend *later* —
the Anthropic-key path (key-free stays the CI gate + fallback) and the no-backend
ceiling (relaxed only at the M5 edge capstone). Those constraints remain in force
until that work ships.

Anti-features (deliberately out of scope): native mobile app, multi-user, comments,
real-time push. The full merged anti-feature list lives in `ROADMAP.md` §9.
