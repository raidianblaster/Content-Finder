# Content Finder — Roadmap v3 (Agentic & Self-Improving Route)

> **This roadmap refines [ROADMAP-v2.md](ROADMAP-v2.md); it does not replace it.**
>
> - `ROADMAP.md` (v1) optimizes **product value** — a cleaner daily digest.
> - `ROADMAP-v2.md` optimizes **learning value** as a six-rung concept ladder
>   ending in an edge function.
> - `ROADMAP-v3.md` (this file) keeps every v2 rung but changes the **spine**:
>   instead of "one agentic concept per rung," it organizes the work around the
>   **agent loop** (perceive → reason → act → evaluate → **learn**) and makes
>   *the system itself* progressively more autonomous and self-improving.
>
> The bet: building a system that *measures and improves itself* is the most
> advanced agentic-engineering skill there is — so it serves both readings of
> "self-learning" at once: **you** learn by building it, and **the system**
> learns from the data you're already collecting.

---

## 0. What changes vs v2 (read this first)

v2 is good. Five refinements turn it from a concept tour into a self-improving lab:

1. **A self-learning flywheel becomes the spine, not a footnote.** You already
   collect `feedback/<date>.jsonl` (keep/drop/unsure), a Haiku judge writes
   `suspect_drops`/`suspect_keeps`, and `dedup-state.json` persists run state.
   v2 builds an eval harness (Rung 1) but never *closes the loop* — it doesn't
   fit weights from your labels or evolve prompts automatically. v3 does. This
   is the biggest gap and the highest-leverage change.

2. **Observability is Rung 0, not optional.** You cannot improve agents you
   cannot see. Both v1 and v2 are silent on tracing. Every LLM call should emit
   a structured trace (inputs, outputs, tokens, cost, latency, model,
   `prompt_version`). This is cross-cutting and comes *first* because every
   later rung debugs through it — and LLM observability/evals is one of the most
   employable agentic-engineering skills right now.

3. **A real multi-step agent loop is missing.** v2's rungs are mostly
   single-pass LLM calls in a pipeline. None of them *plan, call tools, observe,
   and self-correct in a loop*. The **deep-research agent** (§4, Act track) adds
   the canonical ReAct-style loop — the single most "agentic" feature on the board.

4. **The v1↔v2 conflict is dissolved with one rule.** v2's preamble admits it
   will sometimes make the digest *worse*. That's an unforced error given your
   second goal is *keeping up with news*. v3 adopts a **do-no-harm-to-the-daily
   gate** (§2): the key-free daily path stays green in CI, and every agentic
   feature is additive/opt-in until its eval proves it beats baseline. You keep
   your news utility while you learn.

5. **The work compounds into a portfolio.** Each rung gets a **success metric**
   (a number, not "build it") and a one-page **learning log**. By the end the
   repo is an interview-ready demonstration of evals, memory, multi-agent
   orchestration, and edge deployment — not just a feed reader.

---

## 1. Where the project actually is (landed inventory)

Refining a roadmap means first marking what's *done*, so the plan stops listing
solved problems as future work:

| Capability | Status | Evidence |
|---|---|---|
| Cross-day dedup | **Landed** | `dedup-state.json` (url→last-seen, TTL 5d), `canonical_url()`, `filter_unseen()` |
| `sources.yml` config | **Landed** | `load_sources()`, mobile-editable |
| Filter log per run | **Landed** | `docs/logs/<date>.json` + `latest.json` |
| Review/labelling page | **Landed** | `review.py`, PAT auto-save → `feedback/<date>.jsonl` |
| Haiku judge triage | **Landed + in CI** | `judge.py` (`claude-haiku-4-5`), runs in `daily.yml` |
| Source diversity cap | **Landed** | `apply_source_cap()` (default 3) |
| Tags + chip filter bar | **Landed** | `TAG_TAXONOMY`, chip JS |
| LLM synthesis (opt-in) | **Landed** | `synthesize_with_claude()` (`claude-sonnet-4-6`), `PROMPT_VERSION="v1"` |
| Skill handoff seam | **Landed** | `latest.json`/`latest.judge.json` feed the *Hermes Discovery Queue* skill |

**The unrealized asset:** you have a labelled preference stream growing daily and
a judge that flags mistakes — but nothing reads them back into the pipeline. The
flywheel is built and *not spinning*. v3 spins it.

**The one cheap prerequisite:** open issue **#9** (log the `summary` text + score
components into the filter log and JSONL). Right now a feedback row knows the
verdict and the final `score`, but not the *features the model saw*. You can't
learn weights from labels without the features. Land #9 first — it's an hour and
it unblocks the entire Learn track.

---

## 2. Guiding principles (the framing refinements)

These replace v2's "pick one loss function and accept the digest gets worse."

### 2.1 The agency ladder (how to answer "is this more agentic?")

Tag every feature with its autonomy level. The roadmap's north star is to move
features *up* this ladder:

- **L0 — Scripted.** Deterministic code. (`score_item`, dedup, rendering.)
- **L1 — LLM-in-the-loop.** One model call, human reads output. (today's synthesis.)
- **L2 — Tool-using agent.** Model plans and calls tools in a loop, then stops.
- **L3 — Self-evaluating.** System scores its own output against a rubric/gold set.
- **L4 — Self-improving (human-gated).** System proposes changes to its own
  config/prompts; a human approves promotion.

"The more agentic and self-learning the better" = **climb toward L4, with a human
holding the promotion gate.** The gate is non-negotiable in a regulated context.

### 2.2 Do-no-harm-to-the-daily gate

Every change must leave the key-free daily digest **at least as useful**:
- `python content_finder.py --no-summarize` must stay green in CI as a
  regression test (it's your guaranteed-free news utility).
- New agentic features are **additive and opt-in** until their eval beats
  baseline. A feature that improves *learning* but regresses the *digest* ships
  behind a flag, never on the default path.

This is what lets "keep up with news" and "learn agentic engineering" stop fighting.

### 2.3 Eval-Driven Development (EDD), the partner to TDD

The repo's TDD discipline is excellent. Extend it, don't fork it:
- **Deterministic code → unit test** (as today).
- **Probabilistic / LLM code → eval** against a frozen gold set.
- **Rule:** no scoring or prompt change merges without an eval delta posted on
  the PR. "Vibe-checked the output" is not a merge criterion.

### 2.4 The three memory types (a map for the memory work)

Naming the taxonomy makes the roadmap legible and shows it covers the whole space:
- **Episodic** — *what happened, when.* (v2 Rung 2: embedded archive / story memory.)
- **Semantic** — *facts and relations.* (v2 Rung 2.5: the knowledge graph.)
- **Procedural** — *how to judge.* (**new** §4 Learn track: the self-tuned scorer.)

v2 has episodic and semantic; it's missing procedural — which is exactly the
"system learns your preferences" piece.

### 2.5 Constraints (which bend, which don't)

| CLAUDE.md constraint | v3 stance |
|---|---|
| "No backend / PWA is the ceiling." | Relaxed only at the **edge capstone** (Act track), exactly as v2. |
| "No API key in regular use." | The key-free daily path stays as the **fallback + CI gate** (§2.2). New features assume a key. |
| "Regulated env — only public news, nothing private outbound." | **Inviolate.** Every loop here only ever touches public RSS/HN + your own keep/drop labels. The self-review agent reads repo state, never private data. |

---

## 3. The agent-loop map

v3's items, arranged by which part of the loop they exercise. This is the
conceptual index; §4 gives the detail and §5 the order.

```
                ┌─────────────────────────────────────────────┐
   FOUNDATIONS  │ tracing • EDD • do-no-harm gate • #9 •        │
                │ structured-output synthesis (tool-use schema) │
                └─────────────────────────────────────────────┘
        PERCEIVE            REASON & ACT             EVALUATE            LEARN
   ┌───────────────┐   ┌──────────────────┐   ┌────────────────┐  ┌────────────────┐
   │ source-scout  │   │ deep-research    │   │ eval harness   │  │ self-tuning    │
   │ agent (L2)    │   │ agent (L2)       │   │ + gold set     │  │ scorer (L4)    │
   │ episodic mem  │   │ multi-agent      │   │ LLM-as-judge   │  │ eval-gated     │
   │ semantic/KG   │   │ rollup +reflect  │   │ provenance     │  │ prompt evo +   │
   │               │   │ agentic RAG/edge │   │ validator      │  │ optimizer (L4) │
   │               │   │ MCP + routing    │   │                │  │ actions/drills │
   └───────────────┘   └──────────────────┘   └────────────────┘  └────────────────┘
                                 └────────────── META ──────────────┘
                          self-review agent maintains this roadmap (L4)
```

---

## 4. The rungs (grouped by track)

Each item is annotated: **[agency level] · concept taught · news value · cost ·
constraint touched · success metric.** Items that reposition v2 are marked.

### FOUNDATIONS — do these first; everything else debugs through them

**F1 · Tracing & cost ledger** — **[L0→observability]**
Emit one JSONL trace row per LLM call: `{ts, call_site, model, prompt_version,
input_tokens, output_tokens, cost_usd, latency_ms, ok}` to `docs/logs/traces.jsonl`.
Add a tiny `traces` CLI that prints a daily cost/latency rollup.
- *Concept:* LLM observability — the substrate of all agent debugging.
- *News value:* indirect (keeps the daily cheap and diagnosable).
- *Cost:* ~$0. *Constraint:* none.
- *Metric:* every model call in `judge.py` + `synthesize_with_claude` appears in
  the ledger; daily cost is one `grep`/rollup away.

**F2 · Land issue #9 (log summaries + score features)** — **[L0]**
Add `summary` and the per-component score breakdown (`keyword_score`, `recency`,
`src_bonus`, `hn_bonus`) to `_item_log_dict()` and propagate to the JSONL.
- *Concept:* you can't learn from labels without the features behind them.
- *Metric:* a feedback row is sufficient to reconstruct the exact feature vector
  the scorer saw. **This unblocks the entire Learn track.**

**F3 · Structured-output synthesis via tool-use** — **[L1, schema-enforced]**
Move `synthesize_with_claude` from free markdown to the fixed per-item JSON
schema already specified in `CLAUDE.md` (`tldr, what_changed, why_it_matters,
claims[], …`), enforced with Anthropic tool-use. Render markdown *from* the JSON.
- *Concept:* structured output / schema enforcement — the backbone every
  downstream feature (citations, graph, weekly rollup, edge `/ask`) reads from.
- *News value:* high — unlocks the "PM angle" per-item annotation (v1 §5).
- *Cost:* ~$2–5/mo at this volume. *Constraint:* relaxes "no key in regular use"
  (gated; key-free path still renders the ranked list).
- *Metric:* 100% of synthesized items validate against the schema; markdown
  output is byte-stable given the same JSON.

---

### EVALUATE — build the ruler before you measure improvement

**E1 · Eval harness + frozen gold set** — **[L3]** *(v2 Rung 1, kept first)*
`evals/gold.jsonl`: ~30 hand-labelled items pulled from the archive, each with
`expected_verdict`, `expected_tags`, and a one-line "why it matters." A
`content_finder.py eval` command scores the current pipeline against it
(ranking agreement, tag accuracy, dedup precision/recall) and writes a baseline.
- *Concept:* designing a labelled eval set when you're the only labeller;
  reference-based + LLM-as-judge evaluation.
- *Cost:* ~$1 to build, ~$0.10/run.
- *Metric:* baseline report exists; a CI workflow posts an eval **delta** on any
  PR touching `score_item`, `sources.yml`, or `prompts/`.

**E2 · Provenance validator** — **[L3]** *(absorbs v2 Rung 3's citation idea)*
A pure post-processing step that fails any synthesized brief containing a citation
token (`[c12]`, `[e:org:anthropic]`) that doesn't resolve to a real cluster/entity.
- *Concept:* trust + verification; the gate that makes the v1 "unsubscribe"
  milestone honest (every claim traceable).
- *Metric:* a brief with an unresolvable citation fails the run, not the reader.

---

### LEARN — the self-learning flywheel (the headline of v3)

**L1 · Self-tuning scorer (procedural memory)** — **[L4]** *(fuses v1 §1
"personalised weights" + "source credibility v1" + v2 Rung 1)*
Today `score_item` is hand-tuned: `keyword_score + 2·recency + src_bonus +
hn_bonus`. That's a **linear model with hand-set coefficients.** Fit it instead:
features `[keyword_score, recency, per-source trust, hn_points, tag one-hots,
age_days]`, label `keep=1 / drop=0` from `feedback/*.jsonl` (drop `unsure` or
weight 0.5). Logistic regression — **no ML framework, just numpy** — yields
learned coefficients that *stay interpretable* (you can read the learned
per-source trust and compare it to your hand-set integers).
- *Promotion gate (L4):* the learned scorer ships only if it **beats** the
  heuristic on held-out days (precision@N, ranking agreement) in E1, and you
  click approve. Static weights remain the seed/fallback.
- *Concept:* feature engineering, offline eval, train/test discipline, and the
  "bitter lesson" tension — *does* learned beat heuristic at 10–25 items/day?
  Maybe not. **That's a finding, not a failure** (v2 says the same about Rung 1).
- *News value:* high — the digest ranks by *your* revealed preferences.
- *Cost:* ~$0 (local fit). *Constraint:* none (uses only public items + your labels).
- *Metric:* learned scorer's precision@10 vs heuristic on the last 14 days, reported.

**L2 · Eval-gated prompt evolution** — **[L3→L4]** *(automates v1 Stage-3 replay)*
v1 specs a *manual* side-by-side prompt comparison. Automate it: an LLM-judge
scores candidate `prompts/synthesis_system_<name>.md` against the gold set + your
labels and ranks them. A candidate **auto-promotes only on a win margin + your
approval** (bump `PROMPT_VERSION`, commit).
- *Concept:* LLM-as-judge, regression gating, and the danger of **reward-hacking
  your own judge** (watch for the model learning to please the rubric).
- *Metric:* prompt promotions are backed by a logged eval win, never a vibe.

**L3 · Prompt-optimizer agent** — **[L4]** *(new — the system writes its own prompts)*
Go one rung more agentic: an agent reads recent `suspect_keeps`/`suspect_drops`
from `judge.py` plus your `note` fields, diagnoses the failure pattern, and
*drafts* the next candidate prompt itself. It then runs L2 to prove the draft
wins. Human still gates promotion.
- *Concept:* automated prompt optimization (the idea behind DSPy/APE, hand-built
  so you see the mechanics), agent-as-engineer patterns.
- *Metric:* ≥1 agent-drafted prompt beats the incumbent in a real eval.

**L4 · Actions & drills (the doing layer)** — **[L1/L2]** *(v2 Rung 6, kept)*
"What to try next" actions appended to each brief (a prompt to run, a repo to
clone, a paper to read), each citing its cluster; plus optional 5-minute drills
on a Leitner schedule. Build **actions first**; gate drills on whether you use them.
- *Concept:* action-extraction with guardrails (no "spin up a GPU cluster" — must
  respect the regulated-env user context); spaced repetition.
- *News value:* turns passive reading into practice — directly serves your learning goal.
- *Metric:* you complete ≥1 suggested action/week for a month.

---

### PERCEIVE — make the news intake itself agentic

**P1 · Episodic memory + embeddings** — **[L1]** *(v2 Rung 2, kept)*
Embed item title+summary into SQLite + `sqlite-vec`; cluster recurring narratives
("MCP adoption") so one story *updates* rather than resurfacing five times.
- *Metric:* a tracked narrative shows as one updating entry across ≥3 days.

**P2 · Source-scout agent** — **[L2]** *(new — proactive coverage; reuses v1 §3/§9)*
A weekly agent that searches for *emerging* AI sources (new lab blogs, substacks,
researchers), auto-discovers their feed, validates it (parses + ≥1 item in 60d),
scores candidate quality against your existing sources, and opens a **PR to
`sources.yml`** with pending entries + rationale. Implementable as a skill, like
the existing *Hermes Discovery Queue*.
- *Concept:* tool-use loop (web search + fetch + validate as tools), self-expanding
  knowledge sources, guardrails against junk.
- *News value:* **high** — your coverage grows without you hunting for feeds.
- *Constraint:* public sources only (inviolate rule respected).
- *Metric:* ≥1 high-quality source added via agent PR that later lands in a digest.

**P3 · Semantic memory / knowledge graph** — **[L1]** *(v2 Rung 2.5, kept but
**explicitly optional/parallel**)*
Extend the per-item schema with `entities[]`/`relations[]` over a closed
vocabulary; persist to SQLite tables; resolve hints via an alias table + review
queue. This is the **heaviest rung for the least immediate payoff** — gate it on
real demand: build it once P5 (research agent) or the edge `/ask` needs to
traverse "X said Y about Z." Until then it's learning-for-its-own-sake (which is
fine, just sequence it honestly).
- *Metric:* `kg query` answers a "who released what when" question the vector
  index can't.

---

### REASON & ACT — the agentic core

**A1 · Deep-research agent for the top story** — **[L2]** *(new — the flagship loop)*
For the day's #1 item, a multi-step agent: plans what it needs → follows the
primary link → searches for corroborating/contradicting coverage → reads the
actual paper/release notes → writes a deeper, citation-backed brief with a
**"Contested"** sub-section when sources disagree → validates citations (E2) →
stops on a budget. This is the canonical ReAct loop — the most "agentic" thing here.
- *Concept:* tool design, plan→act→observe loops, stopping criteria, token-budget
  discipline, self-verification.
- *News value:* **highest single feature** — real depth on the thing that matters most.
- *Cost:* ~$0.10–0.30 per top story. *Constraint:* relaxes "no key"; gated.
- *Metric:* the agent's brief surfaces ≥1 corroborating/contradicting source the
  one-shot synthesis missed, on a majority of spot-checked days.

**A2 · Multi-agent weekly rollup with reflection** — **[L2]** *(v2 Rung 3, deepened)*
Researcher → Critic → Writer, but upgrade the critic into a real **reflexion
loop**: the writer revises against critic notes with a bounded retry budget, and
the **provenance validator (E2) is the stopping gate.** Run the with/without-critic
comparison as an **eval (E1)**, not a vibe.
- *Concept:* role separation, reflection loops, passing structured state between
  agents, when a critic helps vs just hedges.
- *News value:* the shareable weekly artefact (v1 §7) — the org-credibility piece.
- *Metric:* critic-on vs critic-off measured on real weeks; keep the critic only
  if it wins.

**A3 · MCP server + model routing** — **[L2]** *(v2 Rung 4, kept + extended)*
Expose the embedded archive + graph as a local MCP server (`search_archive`,
`get_story_timeline`, `weekly_brief`, `query_graph`) attached to Claude Desktop.
Add **model routing** as a first-class concept: route trivial items to Haiku,
high-signal items to Sonnet, and measure the cost/quality tradeoff in the ledger (F1).
- *Concept:* MCP tool-schema design; cost-aware orchestration / model routing.
- *Metric:* tools are legible enough that Claude Desktop calls them unaided; routing
  cuts cost ≥30% at equal eval score.

**A4 · Agentic RAG at the edge (capstone)** — **[L2→L3]** *(v2 Rung 5 ⊕ v1 §5 Q&A)*
A Cloudflare Worker hosting an **agentic** `/ask` endpoint over the archive — not
static "embed→top-k→answer," but an agent that *decides what to retrieve*,
reformulates queries, retrieves across **both** the vector index and the graph,
and **verifies its answer against sources** before streaming it back.
- *Concept:* the difference between RAG and *agentic* RAG; edge runtime
  constraints (no Node APIs, CPU caps), streaming, auth without accounts
  (Turnstile/rate-limit), public-endpoint abuse control.
- *Constraint:* the one place "no backend" is relaxed — gate explicitly (real
  money, public surface).
- *Metric:* a cold `/ask` returns a verified, citation-backed answer in <X s within
  the free tier.

---

### META — the system maintains itself

**M1 · Weekly self-review agent** — **[L4]** *(new — the system maintains this roadmap)*
Once F1 (traces) and E1 (evals) exist, a weekly agent reads the trace ledger, eval
deltas, `feedback/*.jsonl`, judge findings, and open issues, then writes
`docs/learning/self-review-<week>.md`: what improved, what regressed, what the
data suggests building next — and can open **draft** GitHub issues. You review and
decide.
- *Concept:* closing the *outer* loop; agent-as-maintainer; keeping a human in command.
- *News value:* meta, but it's the purest expression of "self-learning."
- *Metric:* a self-review note that proposes a change you actually adopt.

---

## 5. Recommended sequence

Substrate first (you can't learn from data you can't see or measure), then close
the cheapest loop, then climb agency. Tracks can interleave, but this order keeps
each step feeding the next.

| Phase | Item | Track | Agency | Effort | Cost | Why here |
|---|---|---|---|---|---|---|
| **0a** | F1 tracing ledger | Foundations | L0 | ~2h | $0 | Debug everything downstream |
| **0b** | F2 land #9 (features) | Foundations | L0 | ~1h | $0 | Unblocks the Learn track |
| **1** | E1 eval harness + gold | Evaluate | L3 | ~4h | ~$1 | The ruler for all later work |
| **2** | **L1 self-tuning scorer** | **Learn** | **L4** | ~4h | $0 | Cheapest, highest self-learning payoff; uses data you have |
| **3** | F3 structured-output synthesis | Foundations | L1 | ~3h | ~$3/mo | Backbone schema for everything downstream |
| **4** | P1 episodic memory | Perceive | L1 | ~6h | ~$0.50 once | Substrate for research agent + RAG |
| **5** | L2 eval-gated prompt evo | Learn | L3→L4 | ~4h | ~$0.20/run | Stop vibe-promoting prompts |
| **6** | **A1 deep-research agent** | **Act** | **L2** | ~6h | ~$0.20/day | The flagship agentic loop |
| **7** | A2 multi-agent rollup + reflection | Act | L2 | ~4h | ~$0.30/wk | Shareable weekly artefact |
| **8** | P2 source-scout agent | Perceive | L2 | ~4h | ~$0.10/wk | Coverage grows itself |
| **9** | L3 prompt-optimizer agent | Learn | L4 | ~4h | ~$0.30/run | System writes its own prompts |
| **10** | A3 MCP server + routing | Act | L2 | ~3h | $0 | Your data as tools; cost control |
| **11** | P3 knowledge graph *(optional)* | Perceive | L1 | ~5h | +$0.15/run | Build when RAG/research needs it |
| **12** | A4 agentic RAG at edge | Act | L2→L3 | ~8h | free tier + per-req | Capstone public surface — go/no-go gate |
| **13** | L4 actions & drills | Learn | L1/L2 | ~3h | ~$0.20/day | Reading → practice |
| **14** | M1 self-review agent | Meta | L4 | ~3h | ~$0.10/wk | System maintains its own roadmap |

**If you only do three things:** F2 (#9) → E1 (eval harness) → **L1 (self-tuning
scorer).** That trio turns your existing-but-idle feedback stream into a system
that measurably learns your taste — the smallest end-to-end self-learning loop,
all local, ~$1 total.

---

## 6. Make it compound — metrics & learning log

- **Per-rung success metric.** Every item above carries one (a number). "Built it"
  is not "done"; "moved precision@10 from 0.7→0.8" is.
- **Learning log.** `docs/learning/<rung>.md`, one page each: *what I built, the
  one concept that clicked, what surprised me, what I'd do differently.* This is
  what turns the repo into a portfolio and compounds the learning — and it's good
  shareable content (your second goal) in its own right.
- **Generate a public build-log page** from those notes once there are a few.

---

## 7. Anti-features (extends v1 + v2's lists)

Keep all of v1's and v2's anti-features (no LangChain/CrewAI/AutoGen, no vector DB
before Rung 2 proves need, SQLite only, single-file until ~3000 LOC, Anthropic-only,
no graph DB). Add:

- **No autonomous writes without a human gate.** Self-tuning, prompt promotion,
  source-scout, and the self-review agent all stop at a PR/approval. L4 means
  *human-gated* self-improvement — never auto-merge to `main`.
- **Don't optimize the scorer against the same judge that grades it.** Keep the
  gold set (human labels) separate from the LLM-judge, or you'll reward-hack yourself.
- **No agent framework for the research/multi-agent loops.** Use the Anthropic SDK
  tool-use directly — the mechanics are the lesson (v2's rule, reaffirmed).
- **Don't build the knowledge graph (P3) before something queries it.** It's the
  most over-engineered-by-default rung; gate on real demand.
- **No self-review agent before traces + evals exist.** It has nothing to read until F1/E1 land.

---

## 8. The next move

1. **Decide v3 is primary** (or a side-track). If primary, update `CLAUDE.md`:
   relax "no key in regular use" to "key-free path is the CI gate + fallback,"
   add the do-no-harm gate and EDD rule, and keep the regulated-env rule inviolate.
2. **Set an Anthropic monthly cap** before any keyed rung (~$5–15/mo steady state;
   the edge rung is variable).
3. **Land F2 (#9) this week.** One hour, no key, unblocks everything. Then E1, then L1.
   You'll have a self-learning loop running locally for ~$1 — and a real answer to
   "does learned beat heuristic at my volume?" within a week of labelling.
