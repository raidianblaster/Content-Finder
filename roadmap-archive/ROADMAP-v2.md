# Content Finder — Roadmap v2 (Learning-Optimized Route)

> **This roadmap optimizes a different loss function than [ROADMAP.md](ROADMAP.md).**
>
> - `ROADMAP.md` (v1) optimizes **product value** — make the daily digest more
>   useful to read.
> - `ROADMAP-v2.md` (this file) optimizes **learning value** — make the project
>   a hands-on lab for agentic engineering concepts, ending in a deployed edge
>   function.
>
> These goals overlap but conflict at the edges. v2 will sometimes ship
> features that make the digest *worse* (more LLM weirdness, higher cost,
> more failure modes) before they make it better. That is the deal.
>
> Pick one as the primary at any given time. v1 stays as the fallback if the
> learning path stalls — none of v2's rungs delete v1's foundations.

---

## Constraints this route relaxes

The following are written as load-bearing in `CLAUDE.md`. v2 consciously
rewrites them rather than drifting past:

| CLAUDE.md constraint (v1) | v2 stance |
|---|---|
| "PWA + GitHub Pages is the deliberate ceiling. No backend service." | **Relaxed at rung 5.** Edge function (Cloudflare Worker) is the explicit endpoint. Pages remains the daily-digest home; the Worker is an additive surface, not a replacement. |
| "No Anthropic API key in regular use. Code must work end-to-end with `--no-summarize`." | **Relaxed from rung 1.** Key-required paths are first-class. The `--no-summarize` path is preserved as a fallback so the daily cron never breaks if the key is revoked, but new features assume a key exists. |
| "Regulated env. Pipeline only handles public news. Don't introduce anything that ships internal/private data outbound." | **Unchanged.** This is the one constraint that doesn't bend. Edge function only ever sees public RSS/HN content and the archive — no user accounts, no private data ingress. |

If/when this roadmap is adopted as the primary direction, update `CLAUDE.md`
to match — don't leave the old constraints standing as live documentation.

---

## The five rungs

Each rung picks one agentic-engineering concept and chooses a feature that
**forces** the user to exercise it. Rungs are ordered so each produces an
artifact the next rung consumes — by rung 5 the edge function has something
real to serve.

### Rung 1 — Structured output + evaluation loops

**Concept under your hands:** how to know if your agent got better.

**Feature:** replace the heuristic in `score_item()` with a Haiku-judged
scorer that returns a structured score + 1-line rationale per item. Build a
small eval harness (~30 hand-labeled gold items pulled from the existing
archive — large enough to detect regressions, small enough that you'll
actually finish labelling) that compares heuristic vs LLM scoring on
agreement, ordering, and tag accuracy.

**Concrete eval-harness shape:**
- `evals/gold.jsonl` — frozen 30-item set with hand-written `expected_score`,
  `expected_tags`, and a 1-sentence "why it matters" used by the LLM judge.
- `content_finder.py eval` runs the current pipeline against the frozen
  inputs, produces a baseline report (summary fidelity via LLM-as-judge with
  rubric, dedup precision/recall, tag accuracy).
- A GitHub Actions workflow runs evals on PRs touching scoring or synthesis
  prompts and posts a delta vs baseline. Without this, every prompt change
  is a vibe call.
- The eval harness is the test suite for every later rung that touches
  prompts.

**You will learn:**
- Structured output / JSON schema enforcement against a small model.
- How to design a labeled eval set when you're the only labeler.
- The shape of cost-vs-quality curves at digest-volume token counts.
- When the heuristic is already good enough (this is a real possible outcome).

**Likely surprise:** at 10–25 items/day, the heuristic may win on
cost-adjusted quality. That's a useful, ship-shaped finding — not a failure.

**Stays local. No infra. ~$0.10/run with Haiku.**

---

### Rung 2 — Memory and embeddings

**Concept under your hands:** stateful retrieval across runs.

**Feature:** upgrade the planned `seen.json` (v1, Phase 1) into a proper
*story memory*. Embed each item title+summary, cluster across days, and
treat a recurring narrative ("MCP adoption", "EU AI Act enforcement") as
one entry that *updates* rather than five separate daily items.

**You will learn:**
- Embedding choice and storage shape for small corpora (SQLite + sqlite-vec
  is enough; don't reach for a vector DB).
- Similarity thresholds — when two items are "the same story" vs adjacent.
- The difference between dedup (string-ish) and clustering (semantic).
- How memory turns a feed reader into something that has a *view* on a topic.

**Artifact this produces for later rungs:** the embedded archive becomes
the index that rung 4's MCP server and rung 5's edge function query.

**Stays local. SQLite file checked into the repo (or `.gitignore`'d if it
gets big).**

---

### Rung 2.5 — Knowledge graph (entities + relations)

**Concept under your hands:** structured extraction and graph traversal as a
complement to embeddings. Embeddings give "similar"; the graph gives
"related-by-fact."

**Feature:** extend the per-item LLM summary schema with `entities[]` and
`relations[]` arrays. Persist them in two new tables in the same SQLite
file as Rung 2. The graph is queried by Rung 3 (citation provenance), Rung
4 (`get_entity_timeline`, `find_related` MCP tools), and Rung 6 (drill
generation grounded in graph facts).

**Why before Rung 3:** the writer in Rung 3 needs *resolvable* citation
targets. Cluster IDs alone aren't legible to a human reader; entity names
("EU AI Act", "GPT-5") are. Building the graph here means Rung 3's
provenance system has something to point at.

**Schema — extension to the per-item summary JSON (additive, no breaking
changes):**

```jsonc
{
  // ...existing fixed fields (tldr, what_changed, why_it_matters,
  // claims, code_or_api_changes, numbers, governance_signals,
  // open_questions) stay exactly as defined in CLAUDE.md...

  "entities": [
    {
      "id_hint": "org:openai",       // type:slug — LLM proposes; resolver canonicalises
      "name": "OpenAI",              // surface form as it appeared in the item
      "type": "org"                  // one of the fixed types below
    }
  ],
  "relations": [
    {
      "src_hint": "org:openai",
      "rel": "released",             // one of the fixed verbs below
      "dst_hint": "model:gpt-5",
      "confidence": 0.9              // LLM-assigned 0-1; used for filtering, not truth
    }
  ]
}
```

The `_hint` suffix is load-bearing: the LLM never writes to the canonical
graph directly. A pure `resolve_entities()` step matches hints against the
existing entities table (by id, name, or alias) and either reuses an
existing row, attaches to a `pending_entities` review queue, or auto-promotes
after N independent mentions across distinct sources. This avoids the
"Claude the model family vs Claude Sonnet 4.6" silent-merge trap.

**Fixed entity types (closed set, like `TAG_TAXONOMY`):**

| Type | Examples |
|---|---|
| `org` | Anthropic, OpenAI, EU Commission, NIST, METR |
| `model` | claude-sonnet-4-6, gpt-5, gemini-3 |
| `product` | Claude Code, ChatGPT, Cursor, Copilot |
| `person` | Dario Amodei, Sam Altman, Demis Hassabis |
| `regulation` | EU AI Act, NIST AI RMF, EO 14110 |
| `concept` | MCP, RAG, agentic, computer-use, RLHF |

**Fixed relation verbs (closed set):**

| Verb | Domain → Range | Notes |
|---|---|---|
| `released` | org → model \| product | Includes minor versions |
| `announced` | org → * | Catch-all for non-release news |
| `criticized` | * → * | Carries `confidence`; pairs well with `governance_signals` |
| `regulates` | org → concept \| product | Regulator-side actions |
| `complies_with` | org \| product → regulation | Vendor-side claims |
| `integrates_with` | product → product \| concept | e.g. Claude Code ↔ MCP |
| `competes_with` | * ↔ * | Symmetric; store once with lex-min src |
| `succeeds` | model → model | Version chain (claude-4-7 succeeds claude-4-6) |
| `partnered_with` | org ↔ org | Symmetric |
| `affiliated_with` | person → org | Drives "who works where" queries |

Closed sets are non-negotiable and live in `content_finder.py` next to
`TAG_TAXONOMY` so the LLM prompt and the resolver share one source of truth.
A relation outside the set fails the resolver — the LLM is told to pick the
nearest verb or omit, never invent.

**SQLite tables (added to the Rung 2 DB):**

```sql
CREATE TABLE entities (
  id              TEXT PRIMARY KEY,        -- "type:slug", e.g. "org:anthropic"
  name            TEXT NOT NULL,           -- canonical display name
  type            TEXT NOT NULL,           -- one of the fixed entity types
  aliases         TEXT NOT NULL DEFAULT '[]',  -- JSON array of surface forms
  first_seen      DATE NOT NULL,
  last_seen       DATE NOT NULL,
  mention_count   INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'active'  -- 'active' | 'pending' | 'merged'
);

CREATE TABLE edges (
  src                 TEXT NOT NULL REFERENCES entities(id),
  rel                 TEXT NOT NULL,       -- one of the fixed relation verbs
  dst                 TEXT NOT NULL REFERENCES entities(id),
  evidence_item_ids   TEXT NOT NULL,       -- JSON array of archive item ids
  first_seen          DATE NOT NULL,
  last_seen           DATE NOT NULL,
  confidence          REAL NOT NULL,       -- max() across mentions
  PRIMARY KEY (src, rel, dst)
);

CREATE INDEX idx_edges_src ON edges(src);
CREATE INDEX idx_edges_dst ON edges(dst);
CREATE INDEX idx_edges_rel ON edges(rel);
```

`evidence_item_ids` is the bridge back to the archive — every edge can be
explained by clicking through to source items. This is what makes the
graph trustworthy enough for Rung 3's citation system.

**TDD-friendly seams (per CLAUDE.md):**

- `extract_entities_relations(item) → (entities, relations)` — pure, mocked
  LLM call at the boundary. Test with frozen item fixtures + canned LLM JSON.
- `resolve_entity(hint, db) → canonical_id | "pending"` — pure given a DB
  snapshot. Test alias matching, pending promotion, ambiguity surfacing.
- `merge_into_kg(db, entities, relations)` — pure SQL writes. Test
  upsert behavior (mention_count increments, last_seen advances, evidence
  list deduplicates).
- The `kg query` CLI subcommand asserts against rendered output the way
  existing render tests do.

**You will learn:**
- Closed-vocabulary structured extraction at scale, and the cost of letting
  the LLM widen the schema (it will try).
- Entity resolution without ML — alias tables, fuzzy match, manual review
  queue. The "right" answer is mostly bookkeeping, not intelligence.
- When a graph beats vector search and when it loses (hint: counts, dates,
  and "X said Y about Z" win on graph; "what's similar to this" wins on
  embeddings).
- The audit value of a graph as a source-bias detector — "no edges from
  org:deepseek in 60 days" tells you whether the lab is quiet or your
  feeds are blind.

**Likely surprise:** the resolver's pending-review queue is the part that
matters most and the part that's easiest to skip. Without it, the graph
silently degrades within a month as "Claude" / "Claude 4" / "claude-4-7"
fragment into three nodes that should have been one.

**Anti-features for this rung:**
- No graph DB (Neo4j, etc.) — SQLite handles this corpus for years.
- No graph visualization UI before a CLI query subcommand earns its keep.
- No automatic entity merging across types (an `org:openai` and a
  `product:openai-platform` are not the same node, ever).

**Stays local. Adds ~10–20¢/run to LLM cost (one extra Haiku JSON field per
item). SQLite file already exists from Rung 2.**

---

### Rung 3 — Multi-agent orchestration

**Concept under your hands:** role separation in prompt pipelines.

**Feature:** rebuild the weekly rollup (v1, Phase 2.5) as a three-stage
pipeline instead of one prompt:
1. **Researcher** — given the week's items, drafts theme clusters and picks
   exemplars.
2. **Critic** — reads the researcher's draft, flags weak claims, hype, or
   missing context. Returns structured critique.
3. **Writer** — given researcher draft + critic notes, writes the final
   newsletter prose in the PM-in-regulated-industry voice.

**You will learn:**
- Where role separation actually helps vs adds latency and cost for nothing.
- How to pass structured state between agents without losing fidelity.
- Critic-loop design: when does a critic improve output, when does it just
  add hedging?
- Token-budget discipline across a chain.

**Likely surprise:** the critic stage is the one most people add and the
one most likely to be cargo-culted. Worth running A/B (with vs without
critic) on the same week's input.

**Provenance requirement (load-bearing):** the writer's output must carry
inline citation tokens like `[c12]` mapping to cluster ids from rung 2 and
`[e:org:anthropic]` mapping to entity ids from rung 2.5. A post-processing
validator fails the run if any token is unresolvable. When
sources within a cluster disagree on numbers, dates, or claims, surface a
"Contested" sub-section per theme. This is the trust feature that lets the
v1 unsubscribe milestone (ROADMAP §9) actually happen — every claim
traceable to a source.

**Stays local. Runs in the existing daily/weekly GitHub Action.**

---

### Rung 4 — MCP server

**Concept under your hands:** the protocol you'll host at the edge.

**Feature:** expose the archive (now embedded, from rung 2) as a local MCP
server. Attach it to Claude Desktop and/or Claude Code. Tools it exposes:
- `search_archive(query, date_range)` — semantic search over past digests.
- `get_story_timeline(topic)` — uses rung 2's clustering.
- `weekly_brief(week)` — runs rung 3's pipeline on demand.

**You will learn:**
- MCP server scaffolding (the Python SDK, transport choice).
- Tool schema design — what makes a tool legible to an LLM caller.
- Where MCP shines (composable read access) vs where it struggles
  (long-running jobs, streaming).
- Same protocol you'll later wrap in a Worker — rung 5 becomes "host this."

**Stays local. Runs from your laptop, attached to Claude Desktop.**

---

### Rung 5 — Edge function

**Concept under your hands:** deploying agentic services on serverless
edge runtime.

**Feature:** Cloudflare Worker (or Deno Deploy / Vercel Edge — pick one and
commit). Two candidate shapes:

- **Option A — Public MCP endpoint.** Host rung 4's MCP server on the edge
  so you (or anyone) can attach to it from Claude Desktop without your
  laptop being on. Teaches: MCP over HTTP transport, auth at the edge,
  cold-start behavior.
- **Option B — `/ask` endpoint.** Public RAG endpoint over the archive.
  User sends a question, edge function does vector search (Cloudflare
  Vectorize or D1 + sqlite-vec), calls Claude, streams answer back.
  Teaches: vector search at the edge, streaming responses, request-level
  cost control, abuse prevention on a public endpoint.

**Recommendation:** Option B first. It's a more honest forcing function for
the "edge" part — Option A is mostly "MCP that happens to be hosted." B
makes you confront streaming, vector storage, rate limiting, and public-
endpoint abuse, which are the actually-edgy parts of edge.

**You will learn:**
- Workers runtime constraints (no Node APIs, CPU-time caps, sub-request
  limits).
- Vector storage at the edge (Vectorize) vs shipping embeddings in KV.
- Streaming Claude responses through a Worker without buffering.
- Cost ceilings on a public endpoint — Cloudflare's free tier is
  surprisingly generous but a single bot can blow it.
- Auth without user accounts (Turnstile, IP rate limit, or signed
  per-session tokens).

**This is the first rung that costs real money and exposes a public surface.
Worth a separate "go/no-go" gate before starting.**

---

### Rung 6 — Actions and drills (the doing layer)

**Concept under your hands:** turning passive reading into active practice
— the loss function v2 is actually optimising for.

**Feature:** two additions to the daily brief, both consuming the
structured JSON summary schema (`CLAUDE.md` Conventions):

1. **"What to try next" actions.** 3–5 concrete actions appended to each
   brief, generated from the day's structured summaries: a prompt to run, a
   repo to clone, a paper to read, an eval to write. Each action cites the
   cluster it came from. Tracked as todo items in a small store; `todo`
   subcommand to mark done / drop.
2. **Drills.** From high-signal items, generate optional 5-minute drills:
   reading-comprehension Qs, "predict the benchmark number," tiny
   implementation challenges. Schedule via Leitner-style spaced repetition
   (5 boxes, 1/2/4/8/16 day intervals). `drill` subcommand serves the next
   due card.

**You will learn:**
- Action-extraction prompts: how to keep the model from suggesting things
  the user can't actually do in a regulated env (no "spin up a GPU
  cluster" — must respect the user-context memory).
- Spaced-repetition scheduler basics — Leitner box transitions, due-date
  computation, what "lapse" means.
- The eval question: do drills actually correlate with you remembering
  things 30 days later? Build the measurement before assuming yes.

**Likely surprise:** the actions feature is more valuable than the drills
feature. Drills assume time you may not have on a workday; actions slot
into existing PM workflows. Build actions first, gate drills on whether
you actually use them.

**Stays local. Runs in the existing daily Action; todo/drill stores are
small JSON files in the repo.**

---

## Suggested phasing

| Phase | Rung | Effort | Cost | Reversibility |
|---|---|---|---|---|
| Now | Rung 1 — eval harness + Haiku scorer | ~4 hrs | ~$1 to build labels, ~$0.10/run | Fully reversible |
| Next | Rung 2 — story memory + embeddings | ~6 hrs | one-time embedding pass ~$0.50 | Reversible (SQLite file) |
| 2.5 | Rung 2.5 — knowledge graph (entities + relations) | ~5 hrs | +$0.10–0.20/run on Haiku | Reversible (additive tables; drop to disable) |
| 3 | Rung 3 — multi-agent weekly rollup | ~4 hrs | ~$0.30/week | Reversible (prompt-only) |
| 4 | Rung 4 — local MCP server | ~3 hrs | $0 | Reversible (separate process) |
| 5 | Rung 5 — edge function | ~6–10 hrs | Cloudflare free tier + Claude API per request | Adds a public surface — gate explicitly |
| 6 | Rung 6 — actions + drills | ~3 hrs actions, +2 hrs drills | ~$0.20/day at Haiku rates | Reversible (additive section in brief) |

---

## What this roadmap deliberately drops or defers

To stay honest about the loss function, several v1 items get pushed back
or skipped under the v2 ordering:

- **og:image previews, reading-time, dark mode toggle** — pure UI polish.
  No agentic concept attached. Defer indefinitely.
- **Telegram/Signal bots, iOS Shortcut, Readwise export** — multi-channel
  delivery is a product win, not a learning win. Defer.
- **Source diversity cap, `sources.yml` config** — already partially done
  or trivially mechanical. Keep doing them as quality-of-life work but
  they're not roadmap rungs under v2.
- **Click-feedback loop** — would be interesting under v2 (turns the digest
  into a true RLHF-style preference dataset), but only meaningful after
  rung 5 exists to capture clicks server-side. Park until then.

---

## Anti-features (v2-specific, in addition to v1's list)

- **Don't build agent frameworks.** Use the Anthropic SDK directly. LangChain,
  CrewAI, AutoGen all hide the exact mechanics this roadmap is trying to
  teach.
- **Don't add a vector DB before rung 2 proves you need one.** SQLite +
  sqlite-vec covers a corpus this size for years.
- **Don't multi-model.** Stick to Anthropic across all rungs. Comparing
  providers is a different learning project.
- **Don't add a UI for the edge function before it works headlessly.** A
  curl-able endpoint is the deliverable; a chat UI is a different rung you
  haven't planned.

---

## Recommended decision point

Before starting rung 1, decide:

1. **Is this the primary roadmap, or a side track?** If primary, update
   `CLAUDE.md` to match (relax the two constraints listed above). If side
   track, keep v1 as the source of truth and treat v2 work as opportunistic.
2. **API key budget.** Even at Haiku rates, rungs 1–4 will run ~$5–15/month
   in steady use. Rung 5 is variable. Set a monthly cap in the Anthropic
   console before rung 1.
3. **Time-box rung 1.** If after rung 1 the eval shows the heuristic is
   already good enough, that is a *finding*, not a failure — but decide in
   advance whether the finding kills the roadmap or whether you proceed
   anyway because the *learning* was the point.
