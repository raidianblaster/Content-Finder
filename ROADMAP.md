# Content Finder — Roadmap

Brainstormed feature plan for the agentic-AI digest tool. Organised by
category, then phased by suggested order of work.

---

## 1. Ranking & relevance

Current scorer: keyword match + recency + source-trust + HN points.

- **Cross-day deduplication.** Today's Stratechery piece resurfaces for days as feeds catch up. Two-stage check inside a 72-hour window:
  1. **Canonical URL match** — strip UTM params, fragments, mobile prefixes (`m.`, `amp.`), trailing slashes; compare normalised URLs.
  2. **SimHash over title + summary** — catches the same story rewritten by aggregators. Configurable Hamming-distance threshold; log dedup metrics in the run summary.
  State lives in `seen.json` (or a single sqlite file with hand-written DDL once it grows past trivial).
- **Source diversity cap.** Limit each source to N items per digest so one hot day on Simon Willison doesn't take 7 of the top 10.
- **Cluster detection.** When N sources cover the same news, merge into one entry with all source links. Trending sub-section uses **z-score on rolling 7- and 30-day theme frequency** to flag heating-up vs cooling-down topics — not just "multiple sources today."
- **Personalised weights.** A `weights.local.yml` you tune over time ("boost regulation +2, demote AI coding tools -1"). No ML, just config.
- **Source credibility scoring v1.** Replace the static `+3/+2/+1` trust weights with computed per source: **timeliness** (lead vs lag on stories that later cluster), **originality** (broke vs aggregated), **signal density** (claims per token in structured summaries), **feedback-weighted accuracy** (from §5 hype-filter agreement). Use scores to weight items in synthesis. Static weights stay as the seed/fallback.
- **Click-feedback loop.** Track which items you actually open, learn from it. (Needs frontend instrumentation; later.)
- **Filter-log review harness — 3 stages.** A semi-automated loop for catching filtering mistakes and iterating on the synthesis prompt.
  - **Stage 1 (landed, PR #7).** Per-run filter log at `docs/logs/<date>.json` plus a labelable HTML page at `docs/review/<date>.html` (built by `review.py`). Verdicts persist in localStorage and export as `feedback/<date>.jsonl`.
  - **Stage 2 (landed, PRs #8 + #10).** Haiku judge in `judge.py` triages the long tail and writes `docs/review/<date>.judge.json`; suspect cards get highlighted server-side in the review HTML. Surfaces likely false-negatives (good items dropped by keyword/source-cap) and likely false-positives (low-quality items in `final`).
  - **Stage 3 (pending — see below).** Side-by-side prompt-replay comparing versions of `prompts/synthesis_system.md` against labelled `final` items.
  - **Blocked on data, not code.** Stage 3 needs a labelled golden set to compare prompts against. Use the harness first; label ≥30 items across a week before building. Issue [#9](https://github.com/raidianblaster/Content-Finder/issues/9) (logging item summaries) is the one cheap prep-work item to land in parallel so feedback rows carry the full text the synthesis prompt would see.

### Stage 3 spec — prompt-replay (next implementation)

New file `compare_prompts.py`. CLI: `python compare_prompts.py <date> <promptA.md> <promptB.md>`.

- Reads `docs/logs/<date>.json` and `feedback/<date>.jsonl` (if present).
- Loads both prompt files. Bumps `PROMPT_VERSION` only on user-accepted promotion — comparisons are tagged with a transient version string (`v1`, `v1+exp`) so they don't pollute attribution in past digests.
- Re-runs `synthesize_with_claude()` against that day's `final` items twice, once per prompt. The model is Sonnet/Haiku — same as production synthesis, not Haiku-the-judge.
- Writes `experiments/<date>/<promptA>_vs_<promptB>.html` with two-column layout, per-bullet 👍/👎/skip buttons backed by localStorage.
- Verdicts export to `feedback/prompts.jsonl` (separate stream from the item feedback). Each line: `{date, prompt_a, prompt_b, bullet_id, item_url, preferred: "a"|"b"|"neither", note, labelled_at}`.
- Acceptance: side-by-side renders for a real day, both columns are clearly attributed to their prompt version, verdicts round-trip through localStorage.

Defer (Stage 3.5, optional): aggregating `feedback/prompts.jsonl` into a "which prompt wins" report; auto-promoting a new prompt to `synthesis_system.md` after N wins.

#### How to use Stage 3 (once built)

This is the prompt-iteration loop you'll come back to whenever you want to improve `prompts/synthesis_system.md`. Built around the same labelling muscle as the review harness — you read two outputs side by side and click which is better.

**When to reach for it:** you've read a week of digests and noticed the per-item bullets miss something specific (e.g. governance signals are too vague, or claims aren't being challenged). Open `synthesis_system.md`, draft a candidate edit, save it next to the original.

**Prerequisites:**
- Anthropic API key in env (`ANTHROPIC_API_KEY`) — this runs Claude twice per day's items, so it costs ~$0.10–0.30 per comparison day. Not free, not expensive.
- Run from the laptop, not phone — API key isn't on mobile.
- At least one day's worth of `final` items (i.e. a normal `docs/logs/<date>.json` exists).
- Two prompt files to compare. Convention: keep candidates as `prompts/synthesis_system_<short-name>.md` (e.g. `synthesis_system_v2-claims-led.md`).

**Run:**

```bash
.venv/bin/python compare_prompts.py 2026-05-21 \
  prompts/synthesis_system.md \
  prompts/synthesis_system_v2-claims-led.md
```

Writes `experiments/2026-05-21/synthesis_system_vs_v2-claims-led.html`.

**Label:** open the HTML in a browser. For each item, two bullets are shown side by side, A on the left and B on the right. Three buttons per row: 👍 A · 👍 B · skip. Click whichever is better, or skip if they're equivalent / both bad. Verdicts auto-save to `feedback/prompts.jsonl` via the same PAT mechanism as the review page (one-time settings setup if you haven't done it on this device).

**Decide:**
- Run the comparison on 3–5 different days, not just one — picks vary with item mix.
- Tally the result. If B wins ≥60% of non-skipped rows across the days, promote it: `cp prompts/synthesis_system_v2-claims-led.md prompts/synthesis_system.md`, bump `PROMPT_VERSION` in `content_finder.py`, commit.
- If it's close (50/50), the diff isn't doing what you thought. Re-read the bullets where A won and ask why — usually the prompt change had a side-effect.
- If B loses, archive the candidate file (don't delete — `git log` is your prompt-experiment history).

**Output shape locked.** Both prompts must read/write the per-item summary schema in CLAUDE.md (`{tldr, what_changed, why_it_matters, claims[], code_or_api_changes[], numbers[], governance_signals[], open_questions[]}`). The side-by-side renders the same field for both, so a meaningful comparison requires both prompts populate the same fields.

**Stage 3.5 makes this faster** — once `feedback/prompts.jsonl` has ~50+ rows, a small aggregator will rank candidates without your having to count by hand.

## 2. Tags & topic sorting

Three tiers:

- **Tier 1 (cheap, no LLM):** keyword-table auto-tagging. Categories: `Models · Agents · Tooling · Regulation · Enterprise · Research · Hot-take`.
- **Tier 2 (with LLM):** Claude assigns 1–3 tags from a fixed taxonomy. Better quality, ~$0.001/item.
- **Tier 3:** filter chips at the top of the HTML page (CSS+JS, no backend). Per-tag RSS feeds for power users.

## 3. Easier source management

- Move `RSS_SOURCES`, `HN_QUERIES`, `KEYWORD_WEIGHTS` from Python into a `sources.yml` config. Editable from the GitHub mobile web UI on iPad.
- A `--add-source <URL>` command that auto-discovers the feed, validates it, appends to `sources.yml`, and commits.
- A weekly health-check job that flags feeds returning errors or zero items in 14 days. Concrete shape: per-source `last_success_at`, `consecutive_failures`, ETag/`Last-Modified` for conditional GETs, and a green/yellow/red flag surfaced in the run summary. Required input for the unsubscribe dashboard (Phase 9).
- **Suggested additions** to evaluate: arXiv cs.AI, Dwarkesh Podcast, Stratechery (headlines), Last Week in AI, Ben's Bites, NIST AI RMF blog, EU AI Office, GitHub release feeds for `anthropics/`, `openai/`, `langchain-ai/`.

## 4. Frontend

Ranked by impact per hour of effort:

- **Filter chips for tags** — biggest UX upgrade once tags exist.
- **Search across archive** — pure client-side JS over a JSON index.
- **Reading-time estimate** on each item.
- **og:image previews** — pulled thumbnails; makes the page feel like a feed reader.
- **PWA manifest** — installs as a real app on iOS/iPadOS with offline caching of last 7 digests.
- **Sticky filter bar + keyboard nav** (j/k) for iPad keyboard.
- **"Trending" section** at top — items where multiple sources converged today.
- **Dark mode toggle** (currently auto-only) + font-size control.

## 5. LLM annotation layer (the killer feature)

Requires Anthropic API key (~$2–5/month at this volume).

- **Per-item "PM angle"** — one-line synthesis: *"Why this matters: signals enterprise vendors are bundling agent infra — relevant to your buy-vs-build evaluation."* For a PM who can't play with tools firsthand, this annotation is the product. Without it the tool is yet another feed reader; with it, it's a personal AI industry analyst.
  - **Output shape is locked.** Use Anthropic tool-use to enforce a JSON schema per item: `{tldr, what_changed, why_it_matters, claims[], code_or_api_changes[], numbers[], governance_signals[], open_questions[]}`. Stored alongside the item; rendered as the "PM angle" line plus collapsible detail. Free-form text is a dead end — every later feature (citations, trends, credibility scoring, weekly rollup) reads from this shape.
- **Hype filter** — Claude badges vendor PR / overhype vs substantive reporting (🎙️ marketing vs 🔬 substantive).
- **Weekly exec summary** every Friday — 5-bullet "what changed in agentic AI this week," shareable in team chat / LinkedIn.
- **Q&A over the archive** — "What's happened with MCP adoption since January?" — answers from indexed past digests.

## 6. Multi-channel delivery

- **Email digest** (parallel) — morning inbox delivery, no bookmark needed.
- **Telegram / Signal bot** for breaking-news threshold (score > 25).
- **iOS Shortcut + Widget** — home-screen widget with today's top 3 headlines.
- **Export to Readwise / Notion** for starred items.

## 7. Weekly rollup layer (Simon Willison `monthly/` pattern)

Inspired by the `monthly/` Django app in `simonw/simonwillisonblog`. Simon
runs two layers of content at different cadences:

| Layer | Cadence | Form | Audience use |
|---|---|---|---|
| Blog entries | Many per day | Atomic, raw | Power readers, RSS, search |
| Monthly newsletter | Once a month | Curated, narrative | Casual readers, inbox, sharing |

The newsletter isn't a separate system — it's a periodic rollup of the same
content, stored as `(subject, body_markdown, sent_at)` with a public archive.

### Why this matters for Content Finder

The daily digest helps the user stay current. A weekly rollup does two
additional jobs the daily can't:

1. **Synthesis.** Reduces a week of activity into "here's what mattered."
2. **Shareability.** A polished weekly doc can be forwarded inside the org,
   posted on LinkedIn, or dropped in a team chat — a feed-reader page never
   is. For an AI PM in a regulated environment, this is a credibility
   artefact, not just a personal info source.

### Proposed shape

```
docs/
├── index.html              ← daily digest (existing)
├── archive/                ← daily archive (existing)
├── weekly/                 ← NEW
│   ├── index.html          ← list of past weekly editions
│   └── 2026-W18.html       ← each weekly rollup, ISO-week named
└── archive.html
```

- Second GitHub Action runs **Sundays 07:00 HKT** (`0 23 * * 6` UTC).
- Scans the last 7 days of `docs/archive/*.html`, extracts all items.
- Two output modes:
  - **Heuristic (no API key):** clusters by tag, picks top-N per cluster, structured "this week in agentic AI" page. Predictable but list-shaped.
  - **LLM (with API key):** feeds the week's items to Claude with a "newsletter for an AI PM in regulated industry" prompt. Genuine narrative prose — the unlock.
- Optional email-out via Resend / Gmail. Newsletter format reads far better in inbox than a feed page.

### Why this collapses several roadmap items

This feature naturally absorbs three items previously in separate phases:

- "Weekly exec summary" (was Phase 3)
- "Email channel" (was Phase 4)
- "Talking-points generator" (was Phase 4)

…all become outputs of the same weekly job, leaning on the daily archive
already accumulating in the repo. The longer the daily runs, the better the
weekly rollup gets — no rework.

### Trigger condition

The heuristic-only version is mostly a longer daily digest — not actually
more shareable. The Claude-narrated version is the unlock. **This feature is
the natural trigger for getting an Anthropic API key**, since the daily can
remain key-free indefinitely but the weekly's value is mostly in synthesis.

---

## 8. Role-specific bonuses (AI PM in regulated industry)

- **Regulation tracker page** — separate sub-page only watching AI policy (EU AI Act, NIST RMF, HK PCPD, MAS). Different sources, weekly cadence.
- **Vendor capability log** — append-only timeline: "2026-04-15 Anthropic ships X." Useful for vendor evaluation decks.
- **Self-building glossary** — new acronyms (MCP, GRPO, etc.) get auto-added with definitions on first appearance.
- **Talking-points generator** — for each top story, 3 bullets you could use in a meeting. Differentiates "read it" from "internalised it."

---

## 9. Newsletter consolidation (the unsubscribe goal)

The product north star from `CLAUDE.md` operationalised. The user is paying time-tax on a stack of AI/PM newsletters — Substacks, Last Week in AI, Ben's Bites, etc. This phase makes Content Finder good enough to *replace* those subscriptions, then proves it source-by-source.

Don't start until §5 (LLM annotation, JSON schema) is solid — synthesis quality has to be high enough that you'd actually trust it as a replacement.

### 9.1 — Source registry import

`content_finder.py sources import <file>` takes a list of newsletter names or URLs (one per line) and creates `pending` entries. Idempotent on re-import. List/show/delete subcommands.

### 9.2 — Feed auto-discovery

For each pending source, try in order:
1. `<name>.substack.com/feed` (most newsletters live here).
2. Fetch the homepage and look for `<link rel="alternate" type="application/rss+xml">`.
3. Common paths: `/feed`, `/rss`, `/feed.xml`, `/atom.xml`.

Each candidate is fetched and validated: must parse, must contain ≥1 item from the last 60 days. Per-strategy unit tests with recorded fixtures.

### 9.3 — Mapping confidence + manual confirmation

Each candidate gets a confidence score (0–1) from: domain match with input, recency of items, title overlap with the user-provided name. `content_finder.py sources confirm` walks the user through pending sources showing the top candidate and recent titles, prompts `[y/n/skip/manual]`. Confirmed → `active`; ambiguous → `needs_fallback`.

### 9.4 — Unsubscribe dashboard

`content_finder.py unsubscribe` (or a static HTML page) listing each source with: status pill, 14-day capture rate, items synthesized in last 7 days, recommendation, and the unsubscribe URL if found in feed metadata.

Recommendation logic:
- `safe_to_unsubscribe` — 14 days green health AND ≥3 items captured AND items appeared in synthesised digest.
- `keep_email` — green health but capture below threshold (the newsletter has signal you'd lose).
- `needs_fallback` — auto-discovery failed or feed is incomplete vs. email version.

This is the surface that closes the loop. Without it, "I aggregate your newsletters" is a claim; with it, it's a defended decision.

### 9.5 — Forwarding-alias fallback (optional, may skip)

For `needs_fallback` sources only — and only if there are any newsletters the user actually cares about that lack a usable feed. Setup: Cloudflare Email Routing → dedicated mailbox → IMAP poller parses incoming HTML emails into items, tagged `source-forwarded`.

⚠️ **Conflicts with the "PWA + GitHub Pages is the ceiling" constraint** — an IMAP poller can't run inside the GH Actions cron the same way. Defer until Phase 9.4 surfaces a real list of `needs_fallback` sources worth the infra cost. For most newsletters (Substack, Beehiiv, Ghost), 9.2 will succeed and this stage isn't needed.

---

## Suggested phasing

| Phase | Theme | Items | Effort | Unlocks |
|---|---|---|---|---|
| **Now (this week)** | Reduce noise, look better | Cross-day dedup · source diversity cap · `sources.yml` config · og:image previews · reading-time | ~2–3 hrs | Cleaner daily digests immediately |
| **Next (week 2)** | Tags & navigation | Keyword auto-tagging · filter chips · client-side archive search · PWA install | ~3–4 hrs | iPad feels like a real app, fast topic filtering |
| **2.5 (week 3)** | **Weekly rollup layer** | Sunday cron · `docs/weekly/` archive · heuristic rollup first, LLM rollup once API key arrives · optional email | ~3 hrs heuristic · +1 hr LLM | Shareable artefact for org / LinkedIn; trigger for API key |
| **Then (week 4+)** | LLM intelligence layer | Anthropic key · per-item PM angle (JSON schema) · narrated weekly · hype filter | ~2 hrs + ongoing API cost | Tool becomes irreplaceable |
| **Unsubscribe milestone** | Newsletter consolidation (§9) | Source import · auto-discovery · confidence-scored confirm · unsubscribe dashboard | ~3–4 hrs | One-by-one defended unsubscribes — the product north star |
| **Later** | Role-specific extensions | Regulation tracker page · vendor capability log · Telegram alerts · talking-points generator · source credibility v1 | varies | Personal AI-strategy ops platform |

---

## Recommended order of work

1. **This week:** cross-day dedup + `sources.yml` config. (Highest payback per hour, no dependencies.)
2. **Read it for 3–5 days.** Real use will reorder the roadmap.
3. **Then commit to the API key** if the noise/value ratio is still off — LLM annotations fix it more cheaply than any heuristic could.

## Anti-features (deliberately out of scope)

- Native mobile app (PWA covers it).
- User accounts / multi-user.
- Comments / social.
- Real-time push (daily cadence is the point).
- **Modularising `content_finder.py` into a `contentfinder/` package.** Single-file is the deliberate identity at current scale (~1500 LOC). Reconsider only if the file passes ~3000 lines.
- **ORM + migration runner.** A flat `seen.json` or single sqlite file with hand-written DDL is enough until the corpus crosses ~100k items.
- **Pluggable `SourceAdapter` protocol.** Premature abstraction for ~15 sources. The two existing fetchers (`fetch_rss`, `fetch_hn`) plus a Substack-aware shim cover the planned newsletter expansion.
- **Vector DB.** sqlite-vec / sqlite-vss covers the corpus for years. Don't reach for Pinecone/Weaviate/pgvector.
