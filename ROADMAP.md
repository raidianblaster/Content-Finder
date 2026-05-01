# Content Finder — Roadmap

Brainstormed feature plan for the agentic-AI digest tool. Organised by
category, then phased by suggested order of work.

---

## 1. Ranking & relevance

Current scorer: keyword match + recency + source-trust + HN points.

- **Cross-day deduplication.** Today's Stratechery piece resurfaces for days as feeds catch up. Add a `seen.json` state file tracking item URLs/titles across runs.
- **Source diversity cap.** Limit each source to N items per digest so one hot day on Simon Willison doesn't take 7 of the top 10.
- **Cluster detection.** When N sources cover the same news, merge into one entry with all source links. Avoids duplicate noise.
- **Personalised weights.** A `weights.local.yml` you tune over time ("boost regulation +2, demote AI coding tools -1"). No ML, just config.
- **Click-feedback loop.** Track which items you actually open, learn from it. (Needs frontend instrumentation; later.)

## 2. Tags & topic sorting

Three tiers:

- **Tier 1 (cheap, no LLM):** keyword-table auto-tagging. Categories: `Models · Agents · Tooling · Regulation · Enterprise · Research · Hot-take`.
- **Tier 2 (with LLM):** Claude assigns 1–3 tags from a fixed taxonomy. Better quality, ~$0.001/item.
- **Tier 3:** filter chips at the top of the HTML page (CSS+JS, no backend). Per-tag RSS feeds for power users.

## 3. Easier source management

- Move `RSS_SOURCES`, `HN_QUERIES`, `KEYWORD_WEIGHTS` from Python into a `sources.yml` config. Editable from the GitHub mobile web UI on iPad.
- A `--add-source <URL>` command that auto-discovers the feed, validates it, appends to `sources.yml`, and commits.
- A weekly health-check job that flags feeds returning errors or zero items in 14 days.
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

## Suggested phasing

| Phase | Theme | Items | Effort | Unlocks |
|---|---|---|---|---|
| **Now (this week)** | Reduce noise, look better | Cross-day dedup · source diversity cap · `sources.yml` config · og:image previews · reading-time | ~2–3 hrs | Cleaner daily digests immediately |
| **Next (week 2)** | Tags & navigation | Keyword auto-tagging · filter chips · client-side archive search · PWA install | ~3–4 hrs | iPad feels like a real app, fast topic filtering |
| **2.5 (week 3)** | **Weekly rollup layer** | Sunday cron · `docs/weekly/` archive · heuristic rollup first, LLM rollup once API key arrives · optional email | ~3 hrs heuristic · +1 hr LLM | Shareable artefact for org / LinkedIn; trigger for API key |
| **Then (week 4+)** | LLM intelligence layer | Anthropic key · per-item PM angle · narrated weekly · hype filter | ~2 hrs + ongoing API cost | Tool becomes irreplaceable |
| **Later** | Role-specific extensions | Regulation tracker page · vendor capability log · Telegram alerts · talking-points generator | varies | Personal AI-strategy ops platform |

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
