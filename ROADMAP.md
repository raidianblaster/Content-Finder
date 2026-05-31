# Content Finder — Roadmap

> **This is the single source of truth.** It supersedes and consolidates the
> three prior roadmaps:
> - `ROADMAP.md` (v1) — product value (a more useful daily digest)
> - `ROADMAP-v2.md` — a six-rung agentic-engineering learning ladder
> - `ROADMAP-v3.md` — making the system self-improving
>
> Nothing was dropped silently — §10 (Coverage Map) shows where every item from
> all three landed. The three prior roadmaps are archived under `roadmap-archive/`
> (`ROADMAP-v1.md`, `ROADMAP-v2.md`, `ROADMAP-v3.md`).

---

## 1. Vision & North Star

**Content Finder is a personal agentic-AI news analyst that is also a hands-on lab
for building agentic, self-improving systems.**

It serves two goals at once, and refuses to trade one for the other:

1. **Keep an AI PM current** on agentic-AI / LLM news, at PM/strategy altitude,
   in a regulated corporate environment.
2. **Teach agentic AI engineering by building it** — each step puts one concept
   under your hands and makes the system measurably more autonomous.

The two goals are unified by one rule (the **do-no-harm gate**, §3): every change
must leave the daily digest at least as useful as it found it. You never burn your
news utility to chase a learning exercise — the learning *rides on top of* a digest
that stays good.

### The 1.0 end-state

A system that, with a human holding every promotion gate:
- **learns your taste** from the keep/drop feedback you already collect,
- **researches** the day's top story with a multi-step agent (Exa-backed),
- **expands its own sources** by discovering and proposing new feeds,
- **evolves its own prompts**, drafting and eval-testing candidates,
- **remembers and connects** stories across time (episodic + semantic memory),
- **serves an agentic RAG endpoint** at the edge, and
- **reviews itself** weekly and proposes its own next steps.

Everything below is the path from where the project is today to that end-state.

---

## Current Checkpoint

**Landed in code:** Milestone 0.1 tracing/cost ledger, Milestone 0.2 score-feature
logging, and Milestone 0.3 CI/do-no-harm gate.

**Current task:** fix the quarantined archive "today" test so CI can run the full
suite without a deselect.

**Next trunk task:** Milestone 1.1 — build the eval harness and frozen gold set.
After that, Milestone 2.1 can train the first self-tuning scorer from the feedback
stream.

**Active metric:** a PR touching scoring, prompts, or source config should be able
to show both deterministic test status and an eval delta.

---

## 2. How to read this roadmap

The plan is a **trunk** with optional **branches**.

- **The Trunk (§6)** is the main quest: an ordered critical path, Milestones 0–5.
  Each milestone produces an artifact the next one consumes. Do these in order.
- **Side Quests (§7)** are optional branches: product polish, extra delivery
  channels, role-specific tools. They hang off the trunk, never block it, and can
  be picked up any time the mood strikes.

Every **trunk** item carries a one-line annotation:

> *agency level · concept taught · news value · effort · cost · constraint touched · success metric*

**Agency ladder** (the autonomy axis the trunk climbs):
`L0` scripted · `L1` LLM-in-the-loop · `L2` tool-using agent · `L3` self-evaluating ·
`L4` self-improving (human-gated).

"More agentic and self-learning" = climb toward **L4 with a human at the promotion
gate**. The gate is non-negotiable in a regulated context.

---

## 3. Principles (load-bearing)

1. **Do-no-harm-to-the-daily gate.** `python content_finder.py --no-summarize`
   stays green in CI as a regression test — it's your guaranteed-free news utility.
   New agentic features are **additive / opt-in** until their eval beats baseline.
2. **TDD for deterministic code, EDD for probabilistic code.** Keep the repo's
   test discipline. Add **Eval-Driven Development**: no scoring or prompt change
   merges without an eval delta (§6, Milestone 1). "Vibe-checked it" is not a merge
   criterion.
3. **Human-gated autonomy.** Self-tuning, prompt promotion, source additions, and
   the self-review agent all stop at a PR / approval. L4 means *human-gated*
   self-improvement — never auto-merge to `main`.
4. **Three memory types.** The memory work spans the full taxonomy:
   *episodic* (what happened — Milestone 3.1), *semantic* (facts & relations —
   3.2), *procedural* (how to judge — the self-tuning scorer, 2.1).
5. **Retrieval tools ≠ model swaps.** Search/retrieval APIs (Exa: neural search,
   `find_similar`, content fetch) are **tools** and are allowed. Non-Anthropic
   *answer engines* (Perplexity Sonar) are allowed **only** as scoped research
   tools whose output Claude consumes, or as eval comparisons — **never** as the
   synthesis/reasoning layer. This preserves the Anthropic-only synthesis rule
   while still letting you learn from other retrieval paradigms.
6. **No agent frameworks.** Use the Anthropic SDK tool-use directly. LangChain /
   CrewAI / AutoGen hide the exact mechanics this roadmap teaches.

### Constraints — which bend, which don't

| Constraint (from `CLAUDE.md`) | Stance |
|---|---|
| "No backend / PWA is the ceiling." | **Relaxed only at the edge capstone** (Milestone 5.2). Pages remains the daily home; the Worker is additive. |
| "No Anthropic key in regular use." | **Key-free path stays as CI gate + fallback.** New features assume a key; the daily cron never breaks if the key is revoked. |
| "Regulated env — only public news, nothing private outbound." | **Inviolate.** Every loop here touches only public RSS/HN/web + your own keep/drop labels. Exa/Sonar queries are public-topic, no private data. |

---

## 4. Status — what's already landed

Start from reality. These are done; the roadmap does not re-list them as future work.

| Capability | Status | Evidence |
|---|---|---|
| Cross-day dedup | **Landed** | `dedup-state.json`, `canonical_url()`, `filter_unseen()` |
| `sources.yml` config | **Landed** | `load_sources()`, mobile-editable |
| Source diversity cap | **Landed** | `apply_source_cap()` (default 3) |
| Filter log per run | **Landed** | `docs/logs/<date>.json` + `latest.json` |
| Review / labelling page | **Landed** | `review.py`, PAT auto-save → `feedback/<date>.jsonl` |
| Haiku judge triage | **Landed + scheduled** | `judge.py`, runs best-effort in `daily.yml` |
| Tags + chip filter bar | **Landed** | `TAG_TAXONOMY`, chip JS |
| Reading-time estimate | **Partial** | `estimated_read_minutes()` exists; UI display is a side quest |
| LLM synthesis (opt-in) | **Landed** | `synthesize_with_claude()` (`claude-sonnet-4-6`), `PROMPT_VERSION="v1"` |
| Skill handoff seam | **Landed** | `latest.json` / `latest.judge.json` feed the *Hermes Discovery Queue* skill |
| LLM trace/cost ledger | **Landed** | `tracing.py`, `traces.py`, traced synthesis + judge calls |
| Score-feature logging (#9) | **Landed in code** | `_item_log_dict()` writes `summary` + `score_components`; daily artifacts refresh on the next run |
| CI do-no-harm gate | **Landed with one quarantine** | `.github/workflows/ci.yml` runs tests + key-free smoke; archive today test is deselected pending fix |

**The unrealized asset:** you collect a labelled preference stream daily and a judge
flags mistakes — but nothing reads them back into the pipeline. The flywheel is
built and *not spinning*. The trunk spins it.

**The remaining cheap cleanup:** remove the CI quarantine by fixing the
time-dependent archive test. After that, the next meaningful trunk work is the
Milestone 1 eval harness.

---

## 5. Tech tree

```
            ┌──────────────────────────────────────────────────────────────┐
 FOUNDATION │  M0 See & Measure ──▶ M1 The Ruler ──▶ M2 Self-Learning Core  │
            └──────────────────────────────────────────────────────────────┘
                                                              │
                          (M2 = minimal first loop: #9 ▶ eval harness ▶ self-tuning scorer)
                                                              ▼
            ┌──────────────────────────────────────────────────────────────┐
   MEMORY   │  M3 Memory: episodic ──┬── (optional fork) semantic / KG       │
            └────────────────────────┼─────────────────────────────────────┘
                                      ▼
            ┌──────────────────────────────────────────────────────────────┐
   AGENTIC  │  M4 Agentic Core:                                              │
    CORE    │   research agent (Exa) · weekly rollup+reflection · source-    │
            │   scout (Exa) · MCP server+routing · [opt] Exa discovery fetch │
            └──────────────────────────────────────────────────────────────┘
                                      ▼
            ┌──────────────────────────────────────────────────────────────┐
 SELF-IMPR  │  M5 Self-Improving & Capstone:                                 │
 & CAPSTONE │   prompt-optimizer · agentic RAG @ edge · actions/drills ·     │
            │   meta self-review agent                                       │
            └──────────────────────────────────────────────────────────────┘

  OPTIONAL BRANCHES (pick anytime, never block the trunk):
   ├─ Product/UX ........ og:image · search · dark mode · PWA · keyboard · trending
   ├─ Delivery .......... email · Telegram/Signal alert · iOS widget · Readwise/Notion
   ├─ Newsletter consol.. import · feed health · confidence-confirm · unsubscribe dash
   │                       (consumes M4 source-scout)
   ├─ Role-specific ..... regulation tracker · vendor log · glossary · talking points
   └─ Retrieval bake-off  Exa neural vs HN keyword vs Sonar (uses M1 harness)
```

---

## 6. The Trunk — main progression

### Milestone 0 — Foundations: "See & Measure"
*Goal: be able to observe the system and prove you didn't regress it — before changing anything.*

**0.1 · Tracing & cost ledger — Landed**
One JSONL trace row per LLM call (`docs/logs/traces.jsonl`): `ts, call_site, model,
prompt_version, input_tokens, output_tokens, cost_usd, latency_ms, ok`. A `traces`
CLI prints a daily cost/latency rollup.
> *L0 · LLM observability · news: indirect · ~2h · ~$0 · constraint: none · metric: every `judge.py` + `synthesize_with_claude` call appears in the ledger.*

**0.2 · Log score features (issue #9) — Landed in code**
Add `summary` + the per-component score breakdown (`keyword_score`, `recency`,
`src_bonus`, `hn_bonus`) to `_item_log_dict()`; propagate to the JSONL.
> *L0 · feature logging for learning · news: indirect · ~1h · ~$0 · constraint: none · metric: a feedback row reconstructs the exact feature vector the scorer saw. **Unblocks the entire Learn track.***

**0.3 · Adopt the gate + EDD — Landed, with one quarantined test**
Wire `--no-summarize` into CI as the do-no-harm regression test; establish the
"no scoring/prompt change without an eval delta" rule.
> *L0 · engineering discipline · news: protects it · ~1h · ~$0 · constraint: formalizes the key-free fallback · metric: CI fails if the key-free daily path breaks.*

**0.4 · Remove the archive-test quarantine**
Fix `test_archive_first_row_has_today_modifier_and_pill` so it passes a pinned
`today` value instead of depending on the wall-clock date, then remove the CI
`--deselect`.
> *L0 · test reliability · news: protects it · ~20m · ~$0 · constraint: none · metric: CI runs the full pytest suite with no deselected tests.*

---

### Milestone 1 — "The Ruler"
*Goal: a way to measure better-vs-worse, so every later change is decidable.*

**1.1 · Eval harness + frozen gold set**
`evals/gold.jsonl`: ~30 hand-labelled archive items with `expected_verdict`,
`expected_tags`, a one-line "why it matters." `content_finder.py eval` scores the
pipeline against it (ranking agreement, tag accuracy, dedup precision/recall) and
writes a baseline. A CI workflow posts an eval **delta** on any PR touching
`score_item`, `sources.yml`, or `prompts/`.
> *L3 · eval-set design, reference-based + LLM-as-judge · news: indirect · ~4h · ~$1 build + ~$0.10/run · constraint: none · metric: baseline report exists; PR deltas post automatically.*

*Pairs with the optional **Retrieval bake-off** side quest (§7).*

---

### Milestone 2 — Self-Learning Core (the flywheel)
*Goal: the system starts learning your taste and improving its own outputs.*
*This is the headline of the whole roadmap.*

**2.1 · Self-tuning scorer (procedural memory)** — *the quick win*
`score_item` today is a hand-tuned linear model: `keyword_score + 2·recency +
src_bonus + hn_bonus`. Fit it instead from `feedback/*.jsonl` — v1 features are
`[keyword_score, recency, per-source trust, hn_points, age_days]`; add tag one-hots
after 2.2 makes tags schema-backed. Use **plain numpy logistic regression** (no ML
framework). Learned coefficients stay interpretable (read off the learned
per-source trust vs your hand-set integers). **Promotes only if it beats the
heuristic** on held-out days in the §1 harness, and you approve. Static weights stay
the seed/fallback.
> *L4 · feature engineering, offline eval, the "does learned beat heuristic at this scale?" question · news: high (ranks by your taste) · ~4h · ~$0 (local) · constraint: none · metric: learned scorer's precision@10 vs heuristic over the last 14 days.*

**2.2 · Structured-output synthesis via tool-use** — *the backbone*
Move `synthesize_with_claude` from free markdown to the fixed per-item JSON schema
in `CLAUDE.md` (`tldr, what_changed, why_it_matters, claims[], …`), enforced with
Anthropic tool-use; render markdown *from* the JSON. Folds in the v1 "per-item PM
angle," "hype filter" badge, and LLM tag assignment as fields of the same schema.
> *L1 (schema-enforced) · structured output / schema enforcement · news: high (the "PM angle" annotation) · ~3h · ~$2–5/mo · constraint: relaxes "no key" (gated; key-free path still renders the list) · metric: 100% of synthesized items validate against the schema.*

**2.3 · Eval-gated prompt evolution**
Automate v1's manual Stage-3 prompt-replay: an LLM-judge scores candidate
`prompts/synthesis_system_<name>.md` against the gold set + your labels and ranks
them. A candidate **auto-promotes only on a win margin + your approval** (bump
`PROMPT_VERSION`, commit).
> *L3→L4 · LLM-as-judge, regression gating, the reward-hacking risk · news: medium · ~4h · ~$0.20/run · constraint: none · metric: every prompt promotion is backed by a logged eval win.*

> **If you only do three things from here:** 0.4 (remove the test quarantine) → 1.1
> (eval harness) → 2.1 (self-tuning scorer). That trio turns your idle feedback
> stream into a system that measurably learns your taste — all local, ~$1 total —
> and answers "does learned beat my heuristic at 10–25 items/day?" within a week of
> labelling.

---

### Milestone 3 — Memory
*Goal: the digest remembers and connects stories instead of treating each day as new.*

**3.1 · Episodic memory + embeddings**
Embed item title+summary into SQLite + `sqlite-vec`; cluster recurring narratives
("MCP adoption", "EU AI Act enforcement") so one story *updates* across days rather
than resurfacing five times. Absorbs v1's "cluster detection" (incl. z-score
trending) and v2's Rung 2.
> *L1 · embeddings & clustering for small corpora, dedup-vs-clustering distinction · news: high (kills repetition; powers "trending") · ~6h · ~$0.50 one-time · constraint: none · metric: a tracked narrative shows as one updating entry across ≥3 days.*

**3.2 · Semantic memory / knowledge graph** *(optional fork)*
Extend the per-item schema with `entities[]` / `relations[]` over a closed
vocabulary; persist to SQLite tables; resolve hints via an alias table + review
queue. **The heaviest build for the least immediate payoff** — gate it on real
demand: it shines once 4.1 (research agent) or 5.2 (edge RAG) needs to traverse
"X said Y about Z." Build it then; skip it until.
> *L1 · closed-vocab extraction, entity resolution without ML, graph-vs-vector tradeoffs · news: medium · ~5h · +$0.10–0.20/run · constraint: none · metric: `kg query` answers a "who released what when" question vector search can't.*

---

### Milestone 4 — The Agentic Core
*Goal: real multi-step agents do the work — the most "agentic" part of the roadmap.*

**4.1 · Deep-research agent for the top story** — *the flagship loop*
For the day's #1 item, a multi-step agent: plans what it needs → calls tools →
writes a deeper, citation-backed brief with a **"Contested"** sub-section when
sources disagree → validates citations → stops on a budget.
**Tools:** `exa_search` (neural search for corroborating/contradicting coverage),
`exa_contents` (read primary sources), optional `exa_find_similar`; optional
`sonar_ask` as a scoped sourced-answer sub-tool (per Principle §3.5 — Claude still
writes the brief).
> *L2 · tool design, plan→act→observe loops, neural-vs-keyword-vs-answer-engine comparison, stopping criteria, token budgets · news: highest single feature · ~6h · ~$0.10–0.30/day + Exa/Sonar API · constraint: relaxes "no key"; public-topic queries only · metric: surfaces ≥1 corroborating/contradicting source the one-shot synthesis missed, on most spot-checked days.*

**4.2 · Multi-agent weekly rollup + reflection (+ provenance validator)**
Researcher → Critic → Writer, with the critic upgraded to a real **reflexion loop**
(bounded retries) and a **provenance validator** as the stopping gate: any citation
token (`[c12]`, `[e:org:anthropic]`) that doesn't resolve fails the run. Run the
with/without-critic question as an **eval (§1)**, not a vibe. Absorbs v1's weekly
exec summary + talking-points-as-output and v2's Rung 3.
> *L2 · role separation, reflection loops, structured state hand-off, trust/provenance · news: high (the shareable org-credibility artefact) · ~4h · ~$0.30/wk · constraint: relaxes "no key" · metric: critic-on vs critic-off measured on real weeks; keep the critic only if it wins.*

**4.3 · Source-scout agent**
A weekly agent that discovers *emerging* AI sources via **Exa `find_similar`**
against your trusted feeds (e.g. "more like Interconnects / Simon Willison"),
auto-discovers + validates each feed (parses, ≥1 item in 60d), scores candidate
quality, and opens a **PR to `sources.yml`** with rationale. Harmonizes v1's
`--add-source` + auto-discovery. Implementable as a skill, like *Hermes Discovery Queue*.
> *L2 · tool-use loop, self-expanding sources, junk guardrails · news: high (coverage grows itself) · ~4h · ~$0.10/wk + Exa · constraint: public sources only (inviolate rule respected) · metric: ≥1 agent-found source that later lands in a digest.*

**4.4 · MCP server + model routing**
Expose the embedded archive (+ graph, if 3.2 is built) as a local MCP server
(`search_archive`, `get_story_timeline`, `weekly_brief`, `query_graph`) attached to
Claude Desktop / Code. Add **model routing**: Haiku for trivial items, Sonnet for
high-signal, measured in the §0.1 ledger.
> *L2 · MCP tool-schema design, cost-aware orchestration · news: medium (your data as tools — value conditional on using an MCP client) · ~3h · ~$0 · constraint: relaxes "no backend"? no — stays local · metric: Claude Desktop calls the tools unaided; routing cuts cost ≥30% at equal eval score.*

**4.x · Exa discovery fetcher** *(optional, pairs here)*
A third fetcher alongside `fetch_rss`/`fetch_hn`: neural-search for fresh
agentic-AI content, routed through the **same** scoring + judge + source-cap so it
widens coverage without flooding. Can be done any time after Milestone 1 (the
harness proves it doesn't degrade quality).
> *L1 · neural search as ingestion, quality-gating a firehose · news: high (widens intake) · ~3h · Exa API · constraint: public-topic queries only · metric: Exa-sourced items clear the judge at a rate within 10% of curated RSS.*

---

### Milestone 5 — Self-Improving & Capstone
*Goal: the system improves itself and goes public — with a human at every gate.*

**5.1 · Prompt-optimizer agent**
An agent reads recent `suspect_keeps` / `suspect_drops` from `judge.py` plus your
`note` fields, diagnoses the failure pattern, and **drafts the next candidate
prompt itself** — then runs 2.3 to prove it wins. Human still gates promotion.
> *L4 · automated prompt optimization (DSPy/APE ideas, hand-built), agent-as-engineer · news: medium · ~4h · ~$0.30/run · constraint: human-gated promotion · metric: ≥1 agent-drafted prompt beats the incumbent in a real eval.*

**5.2 · Agentic RAG at the edge (capstone)**
A Cloudflare Worker hosting an **agentic** `/ask` endpoint over the archive — not
static "embed→top-k→answer," but an agent that decides what to retrieve,
reformulates queries, retrieves across **both** the vector index and the graph, and
**verifies its answer against sources** before streaming. Absorbs v1's "Q&A over the
archive." *Optional fork:* hybrid **live-web augmentation** via Exa/Sonar (flagged:
added cost, latency, and public-endpoint abuse surface).
> *L2→L3 · RAG vs agentic RAG, edge runtime limits, streaming, auth without accounts (Turnstile/rate-limit) · news: high (public, shareable) · ~6–10h · free tier + per-request · constraint: **the one place "no backend" is relaxed — explicit go/no-go gate** · metric: a cold `/ask` returns a verified, citation-backed answer within the free tier.*

**5.3 · Actions & drills**
"What to try next" actions appended to each brief (a prompt to run, a repo to
clone, a paper to read), each citing its cluster; plus optional 5-minute drills on a
Leitner schedule. Build **actions first**; gate drills on whether you use them.
v2's Rung 6.
> *L1/L2 · action-extraction with guardrails (respect the regulated-env context), spaced repetition · news: high (reading → practice — directly serves your learning goal) · ~3h actions / +2h drills · ~$0.20/day · constraint: none · metric: you complete ≥1 suggested action/week for a month.*

**5.4 · Meta self-review agent**
Weekly, an agent reads the trace ledger, eval deltas, `feedback/*.jsonl`, judge
findings, and open issues, then writes `docs/learning/self-review-<week>.md`: what
improved, what regressed, what to build next — and can open **draft** issues. You
review and decide.
> *L4 · closing the outer loop, agent-as-maintainer, human-in-command · news: meta (the purest "self-learning") · ~3h · ~$0.10/wk · constraint: reads repo state only, never private data · metric: a self-review note that proposes a change you actually adopt.*

---

## 7. Side Quests — optional branches

Non-blocking; pick any time. Each is tagged with the trunk milestone it pairs with.

### Product / UX branch *(from v1 §4)*
- **Archive search** (client-side JS over a JSON index) · **og:image previews** ·
  **dark-mode toggle** + font-size · **PWA install** (offline last-7 digests) ·
  **sticky filter bar + keyboard nav** (j/k) · **reading-time display** (logic
  already exists) · **"Trending" section** *(pairs with 3.1 clustering)*.
- *Why optional:* pure presentation; no agentic concept attached.

### Delivery branch *(from v1 §6)*
- **Email digest** (morning inbox) · **Telegram / Signal breaking-news alert**
  (fires when `score > ~25`) · **iOS Shortcut + home-screen widget** ·
  **Readwise / Notion export** for starred items.
- *Why optional:* multi-channel reach is a product win, not a learning win.

### Newsletter-consolidation branch — the "unsubscribe" goal *(from v1 §9)*
- **Source registry import** (`sources import <file>`) · **feed health-check**
  (per-source `last_success_at`, consecutive failures, conditional GETs) ·
  **confidence-scored confirm** · **unsubscribe dashboard** (status, 14-day capture
  rate, recommendation). *Consumes the trunk's 4.3 source-scout for discovery.*
- *Why optional:* a strong product milestone, but downstream of synthesis quality
  (do it once the trunk's synthesis is trustworthy). Forwarding-alias/IMAP fallback
  stays out (conflicts with the no-backend ceiling).

### Role-specific branch *(from v1 §8)*
- **Regulation-tracker sub-page** (EU AI Act, NIST RMF, HK PCPD, MAS) ·
  **vendor-capability log** (append-only timeline) · **self-building glossary**
  (new acronyms auto-defined on first appearance) · **talking-points generator**.
- *Why optional:* high personal value, but specific to your role rather than to the
  agentic-engineering curriculum.

### Retrieval bake-off *(learning side quest; pairs with Milestone 1)*
- An eval comparing **Exa neural search vs HN keyword vs Perplexity Sonar** on
  recall of relevant items for a fixed query set. Pure learning on retrieval
  paradigms; uses the harness you'll already have.

---

## 8. Suggested pacing

| Phase | Trunk milestone | ~Effort | ~Cost | Note |
|---|---|---|---|---|
| Now | M0.4 | ~20m | $0 | Remove the archive-test quarantine so CI measures the full suite |
| Next | M1 (1.1) | ~4h | ~$1 | The ruler |
| **Then** | **M2 (2.1→2.2→2.3)** | ~11h | ~$3/mo | **The self-learning flywheel — the payoff** |
| | M3 (3.1; 3.2 optional) | ~6h (+5h) | ~$0.50 (+) | Memory substrate for the agentic core |
| | M4 (4.1→4.2→4.3→4.4; 4.x opt) | ~17h | ~$10–15/mo | The agentic core; Exa enters here |
| | M5 (5.1→5.2→5.3→5.4) | ~16–20h | variable | Self-improving + edge capstone (go/no-go gate before 5.2) |

Read the digest for ~3–5 days between milestones — real use reorders priorities,
and labelling feeds 2.1.

---

## 9. Anti-features (merged from v1 + v2 + v3)

**Scope ceilings**
- Native mobile app (PWA covers it) · user accounts / multi-user · comments / social
  · real-time push (daily cadence is the point).

**Architecture**
- **No modularising `content_finder.py`** into a package until it passes ~3000 LOC
  (single-file is the deliberate identity; it's ~2.2k now).
- **No ORM / migration runner** — flat `seen.json` or single SQLite with hand-DDL
  until the corpus crosses ~100k items.
- **No pluggable `SourceAdapter` protocol** — premature for ~15 sources +
  Substack shim.
- **No vector DB** (Pinecone/Weaviate/pgvector) — `sqlite-vec` covers this corpus
  for years. **No graph DB** (Neo4j) — SQLite handles 3.2.

**Agentic discipline**
- **No agent frameworks** (LangChain/CrewAI/AutoGen) — SDK tool-use directly.
- **No multi-model for *synthesis/reasoning*** — Anthropic only. Exa is a tool;
  Sonar is tool-/eval-scoped only (Principle §3.5).
- **No autonomous writes without a human gate** — self-tuning, prompt promotion,
  source-scout, self-review all stop at a PR/approval.
- **Don't optimize the scorer against the same judge that grades it** — keep the
  human gold set separate from the LLM-judge, or you'll reward-hack yourself.
- **No knowledge graph (3.2) before something queries it.** No self-review agent
  (5.4) before traces (0.1) + evals (1.1) exist. No edge UI before the endpoint
  works headlessly.

**Deferred (not dropped)**
- **Click-feedback loop** (v1 §1) — would turn the digest into a true preference
  dataset, but only meaningful once 5.2 (edge) can capture clicks server-side. Park
  until then.

---

## 10. Coverage map — where every prior item went

Proof the merge is lossless. `L` = already landed (§4).

### From `ROADMAP.md` (v1)
| v1 item | Destination |
|---|---|
| Cross-day deduplication | **L** (§4) |
| Source diversity cap | **L** (§4) |
| Cluster detection / z-score trending | Trunk **3.1**; UI in Product/UX "Trending" |
| Personalised weights | Trunk **2.1** |
| Source credibility scoring v1 | Trunk **2.1** |
| Click-feedback loop | §9 Deferred (post-5.2) |
| Filter-log harness Stage 1 & 2 | **L** (§4) |
| Filter-log harness Stage 3 (prompt-replay) | Trunk **2.3** |
| Tier-1 keyword auto-tagging / Tier-3 chips | **L** (§4); per-tag RSS → Product/UX |
| Tier-2 LLM tagging | Trunk **2.2** (schema field) |
| `sources.yml` migration | **L** (§4) |
| `--add-source` auto-discovery | Trunk **4.3** (source-scout) |
| Weekly feed health-check | Side quest: Newsletter consolidation |
| Suggested source additions | **L** (mostly added to `sources.yml`) |
| Archive search · og:image · reading-time · PWA · keyboard nav · dark mode | Side quest: Product/UX |
| Per-item "PM angle" (JSON schema) | Trunk **2.2** |
| Hype filter badge | Trunk **2.2** (schema field) |
| Weekly exec summary | Trunk **4.2** |
| Q&A over the archive | Trunk **5.2** |
| Multi-channel delivery (email, Telegram, iOS, Readwise) | Side quest: Delivery |
| Weekly rollup layer (§7) | Trunk **4.2** |
| Role-specific bonuses (§8) | Side quest: Role-specific |
| Newsletter consolidation (§9) | Side quest: Newsletter consolidation (+ 4.3) |

### From `ROADMAP-v2.md`
| v2 rung | Destination |
|---|---|
| Rung 1 — structured output + evals | Split: **1.1** (eval harness) + **2.1** (scorer) + **2.2** (structured output) |
| Rung 2 — memory + embeddings | Trunk **3.1** |
| Rung 2.5 — knowledge graph | Trunk **3.2** (optional fork) |
| Rung 3 — multi-agent weekly rollup | Trunk **4.2** |
| Rung 4 — MCP server | Trunk **4.4** |
| Rung 5 — edge function | Trunk **5.2** |
| Rung 6 — actions + drills | Trunk **5.3** |
| Constraints-relaxed table | §3 (Principles / Constraints) |

### From `ROADMAP-v3.md`
| v3 item | Destination |
|---|---|
| F1 tracing ledger | Trunk **0.1** |
| F2 issue #9 features | Trunk **0.2** |
| F3 structured-output synthesis | Trunk **2.2** |
| E1 eval harness + gold set | Trunk **1.1** |
| E2 provenance validator | Trunk **4.2** |
| L1 self-tuning scorer | Trunk **2.1** |
| L2 eval-gated prompt evolution | Trunk **2.3** |
| L3 prompt-optimizer agent | Trunk **5.1** |
| L4 actions & drills | Trunk **5.3** |
| P1 episodic memory | Trunk **3.1** |
| P2 source-scout | Trunk **4.3** |
| P3 knowledge graph | Trunk **3.2** |
| A1 deep-research agent | Trunk **4.1** |
| A2 multi-agent rollup + reflection | Trunk **4.2** |
| A3 MCP + routing | Trunk **4.4** |
| A4 agentic RAG at edge | Trunk **5.2** |
| M1 self-review agent | Trunk **5.4** |
| Agency ladder · do-no-harm gate · EDD · 3 memory types | §2–§3 |

### New in this consolidation
| Item | Destination |
|---|---|
| Exa as research-agent tool | Trunk **4.1** |
| Exa `find_similar` for source discovery | Trunk **4.3** |
| Exa discovery fetcher | Trunk **4.x** (optional) |
| Perplexity Sonar (scoped) | Trunk **4.1** sub-tool + Retrieval bake-off |
| "Retrieval tools ≠ model swaps" principle | §3.5 |
| Retrieval bake-off | Side quest (pairs with **1.1**) |

---

## 11. The next move

1. **Clean up M0.4:** fix the quarantined archive "today" test and remove the CI
   deselect.
2. **Build Milestone 1.1:** create `evals/gold.jsonl`, an eval CLI/report, and the
   first baseline. This is now the trunk's real next move.
3. **Then build Milestone 2.1:** train the first self-tuning scorer from the
   feedback stream and promote it only if it beats the heuristic on held-out days.
4. **Before keyed milestones:** set an Anthropic monthly cap (~$5–15/mo steady; the
   edge rung is variable). The key-free path and no-backend ceiling stay in force
   until the roadmap explicitly relaxes them.
