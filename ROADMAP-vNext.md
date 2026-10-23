# Content Finder — ROADMAP-vNext

> **A news-driven re-prioritisation layer on top of `ROADMAP.md`.** It does not
> replace the trunk — it re-orders and extends it using six weeks of evidence
> from the digest itself: **51 digests, 150 daily takeaways, 281 story cards**
> (2026-05-09 → 2026-06-21). Every item cites the trunk milestone (M0–M5) it
> builds on. **Items marked `[NEW]`** were added because the news surfaced a gap
> the current trunk under-weights.
>
> Slots into the lineage: `ROADMAP-v1` (product value) → `v2` (learning ladder)
> → `v3` (self-improving) → `ROADMAP.md` (consolidated trunk) → **this** (the
> evidence-prioritised learning track).

---

## 0. Why a vNext

The trunk is sound. What six weeks of the digest add is **proof of where to spend
learning effort first.** The field's centre of gravity moved decisively from
*"can agents do it?"* (capability) to *"how do we deploy, cost-control, secure,
and govern agents in regulated enterprises?"* (productionisation + governance) —
which is exactly the intersection this project, and its owner, occupy.

So vNext does three things: **(1) front-load measurement**, **(2) make every
agentic step earn its place with an eval**, and **(3) add the guardrail
capabilities the field discovered the hard way.**

---

## 1. The direction of travel (evidence)

**Theme tag share since inception** (of 1,018 tag mentions):
Agents 23.3% · Enterprise 22.2% · Regulation 16.1% · Models 15.2% · Tooling 13.2% · Research 10.0%.

**The arc:** the *Agents* (raw capability) theme peaked at ~30% in mid-May and
cooled to ~16%; *Enterprise*, *Regulation*, and *Research* rose. The
OpenAI/Anthropic duopoly (113 vs 107 mentions; everyone else in the teens) makes
export bans and pricing shocks read as **supply-chain risk**.

**What the corpus is actually about** (concept mentions across takeaways +
"so what"s): enterprise deployment (329) · regulation/law (240) ·
governance/policy (169) · cost/efficiency (106) · security/cyber (99) ·
evals/benchmarking (97) · reliability/safety (88) · MCP (46) ·
multi-agent (45). Capability and research terms sit at the bottom.

**Implication:** the highest-learning, most career-relevant work is now
operational — measurement, reliability, cost, security, governance — not raw
capability chasing.

---

## 2. How to read vNext

Six **phases** map onto the trunk's **M0–M5** and climb the same agency ladder
(`L0` scripted → `L1` in-loop → `L2` tool-agent → `L3` self-evaluating →
`L4` self-improving, human-gated). Each module is annotated:

> *concept taught · why now (dated signal) · build · maps-to-trunk · success metric*

The **do-no-harm gate** is non-negotiable: `--no-summarize` stays green in CI;
new agentic features are additive until their eval beats baseline.

---

## 3. The learning-prioritised phases

### Phase 0 — Foundations: "See & Measure" *(mostly landed)*
- **M0.1–0.3 — tracing/cost ledger · score-feature logging · do-no-harm CI gate.** *Landed.* Cost & reliability are the corpus's loudest themes; this is the substrate for both.
- **M0.4 — remove the archive-test quarantine.** *L0 · do now · pin the wall-clock `today` value, drop the CI `--deselect` · maps M0.4 · metric: full pytest suite runs, zero deselected tests.*

### Phase 1 — Measurement & Truth: "the Ruler, deepened" *(TOP PRIORITY)*
- **M1.1 — eval harness + frozen gold set.** *L3 · reference-based + LLM-as-judge · `evals/gold.jsonl` (~30 labelled archive items) + `content_finder.py eval` + CI delta · maps M1.1 · metric: baseline exists; PR deltas post.*
- **`[NEW]` M1.2 — judge-reliability instrumentation.** *L3 · measuring your evaluator's own variance · Jun 16: LLM-as-judge shows coin-flip-level variance · run each judge call k times, log variance, use median/quorum, refuse promotions inside the noise band · hardens M1.1/M2.3 · metric: every eval reports judge variance.*
- **`[NEW]` M1.3 — eval across deployment configs.** *L3 · the scaffold, not the model, is the unit of evaluation · Jun 5: scores don't transfer across agentic configs · parametrise the harness over prompt-version × context-budget × judge-on/off · extends M1.1 · metric: a score matrix per config, not one number.*

### Phase 2 — The Self-Learning Flywheel *(the headline)*
- **M2.1 — self-tuning scorer (procedural memory).** *L4 · feature engineering, offline eval · fit `score_item` from `feedback/*.jsonl` with plain numpy logistic regression; promote only if it beats the heuristic on held-out days · maps M2.1 · metric: learned precision@10 vs heuristic over 14 days.*
- **M2.2 — structured-output synthesis via tool-use.** *L1 · schema enforcement · move synthesis to the fixed per-item JSON schema; render markdown from JSON · maps M2.2 · metric: 100% of items validate.*
- **M2.3 — eval-gated prompt evolution.** *L3→L4 · LLM-as-judge + regression gating + the reward-hacking trap · auto-score candidate prompts vs gold+labels; auto-promote only on margin + approval; keep the gold set separate from the LLM judge · maps M2.3 · metric: every promotion backed by a logged eval win.*

### Phase 3 — Context Engineering & Memory *(elevated by the news)*
- **`[NEW]` M3.1\* — context engineering as a first-class skill.** *L1 · selection, ordering, compaction, token budget — as decisive as model choice · Jun 11: context is the reliability lever (you already lived the 2,000-token truncation fix) · instrument the synthesis context, add `context_tokens` to the ledger · underpins M2.2/M4.1 · metric: zero truncation dropouts; tokens/story tracked.*
- **M3.2 — episodic memory + embeddings.** *L1 · embeddings & clustering for small corpora · SQLite + `sqlite-vec`; cluster recurring narratives (the export-ban saga ran Jun 14→19) so one story updates across days · maps M3.1 · metric: a tracked narrative shows as one updating entry across ≥3 days.*
- **M3.3 — semantic memory / KG** *(optional fork).* *L1 · closed-vocab extraction, entity resolution without ML · build only when 4.1/5.3 needs to traverse "who said what about whom" · maps M3.2.*

### Phase 4 — The Agentic Core, with guardrails
- **M4.1 — deep-research agent for the top story.** *L2 · tool design, plan→act→observe, stopping criteria, token budgets · Exa-backed brief with a "Contested" section + citation validation + budget stop; the **Hermes Phase-2** design already specs caps/triage/ledger · maps M4.1 · metric: surfaces ≥1 source the one-shot missed.*
- **`[NEW]` M4.2 — budget circuit-breaker / cost guardrail.** *L2 · hard runtime stops; cost as a reliability primitive · Jun 13: an agent bankrupted its operator via runaway calls; Jun 4: Uber's hard cap · per-run + per-day token/$ caps with a hard abort + ledger row; default-deny beyond cap · elevates M4.1 detail · metric: a runaway test run is halted at the cap.*
- **`[NEW]` M4.3 — injection defense on the research/fetch surface.** *L2 · treat fetched web/tool content as untrusted; provenance · Jun 11 €0.01 banking-agent drain; May 27 MCP tool-poisoning · extend the existing feed-HTML sanitisation to the Exa-contents path; never let fetched text alter tool-routing · hardens M4.1/M4.7 · metric: a planted "ignore your instructions" payload changes nothing (regression test).*
- **M4.4 — multi-agent weekly rollup + reflexion + provenance.** *L2 · role separation, reflection loops, provenance as stopping gate · Researcher→Critic→Writer with bounded reflexion; any unresolved citation token fails the run; Jun 6: more agents ≠ better, so run with/without-critic **as an eval** · maps M4.2 · metric: critic-on vs critic-off measured on real weeks; keep only if it wins.*
- **`[NEW]` M4.5 — trajectory / intermediate-step evaluation.** *L3 · evaluate the steps, not just the output · May 26: hidden failures in intermediate reasoning are the real audit risk; Jun 3: POIROT/ASSERT/EAPO · log plan/tool-calls/observations as a trajectory; eval for tool-call necessity, redundancy, dead-ends · extends M1 onto M4 · metric: the eval flags an injected redundant/dead-end tool call.*
- **M4.6 — source-scout agent.** *L2 · self-expanding sources with junk guardrails · Exa `find_similar` vs trusted feeds → validate → PR to `sources.yml` · maps M4.3 · metric: ≥1 agent-found source later lands in a digest.*
- **M4.7 — MCP server + model routing.** *L2 · MCP tool-schema design + tool security + cost-aware routing · May 23: LLMs fail realistic multi-step MCP flows; Jun 6: MCP fault taxonomy — the learning is the security, not the plumbing · expose the archive as a local MCP server; Haiku/Sonnet routing in the ledger · maps M4.4 · metric: Claude Desktop calls tools unaided; routing cuts cost ≥30% at equal eval score.*

### Phase 5 — Self-Improving, Governance & Capstone
- **`[NEW]` M5.1 — runtime governance / deontic policy layer.** *L4 · encode the human-gate + allow/deny as explicit, testable policy · Jun 20 (today): deontic runtime policies; Jun 9: enforcement in architecture; Jun 16: authz unsolved · a declarative policy file checked before any write/promotion/external call; log every decision · formalises Principle §3.3 across M2/M4/M5 · metric: every autonomous action is allowed/denied by a logged rule; a forbidden action is blocked in a test.*
- **M5.2 — prompt-optimizer agent.** *L4 · agent-as-engineer, human-gated · reads judge `suspect_keeps/drops` + your notes, drafts the next candidate prompt, runs M2.3 to prove it wins · maps M5.1 · metric: ≥1 agent-drafted prompt beats the incumbent in a real eval.*
- **M5.3 — agentic RAG at the edge (capstone).** *L2→L3 · RAG vs agentic RAG, edge limits, verify-before-answer · Cloudflare Worker `/ask` that decides what to retrieve (vector + graph), reformulates, verifies before streaming; explicit go/no-go gate (the one place "no backend" relaxes) · maps M5.2 · metric: a cold `/ask` returns a verified, citation-backed answer in the free tier.*
- **M5.4 — actions & drills.** *L1/L2 · action-extraction with guardrails; spaced repetition · "what to try next" per brief (a prompt to run, a repo to clone, a paper to read), each citing its cluster · maps M5.3 · metric: you complete ≥1 suggested action/week for a month.*
- **M5.5 — meta self-review agent.** *L4 · closing the outer loop; agent-as-maintainer, human-in-command · weekly, reads the ledger + eval deltas + feedback + judge findings, writes `docs/learning/self-review-<week>.md`, opens draft issues · maps M5.4 · metric: a self-review note proposes a change you adopt.*

### Cross-cutting — model-agnostic eval baseline `[NEW]`
*Vendor concentration is now a documented risk (export bans Jun 14–19; vendor-diversification urged Jun 17; open-weights closing the gap — GLM-5.2 MIT 753B Jun 19). Learn the tradeoff **without** breaking the Anthropic-only synthesis rule by adding an open-weights/local model as an **eval-comparison baseline only** (allowed by Principle §3.5). Pairs with the Retrieval bake-off side quest. Metric: the harness reports a Claude-vs-open-weights delta on the gold set.*

---

## 4. The eight news-driven gaps

| Gap / new capability | News signal | Evidence | Slots into |
|---|---|---|---|
| Judge-reliability instrumentation | LLM-as-judge coin-flip variance | Jun 16 | Phase 1 (M1.2) |
| Eval across deployment configs | Scores don't transfer across scaffolds | Jun 5 | Phase 1 (M1.3) |
| Context engineering as first-class | Context is the reliability lever | Jun 11 | Phase 3 (M3.1\*) |
| Budget circuit-breaker | Agent bankrupts operator; hard caps appear | Jun 13 / Jun 4 | Phase 4 (M4.2) |
| Injection defense on fetch surface | €0.01 drains a banking agent; tool poisoning | Jun 11 / May 27 | Phase 4 (M4.3) |
| Trajectory / step-level eval | Intermediate-step failures are the audit risk | May 26 / Jun 3 | Phase 4 (M4.5) |
| Runtime governance / deontic policy | Policy-as-architecture; authz unsolved | Jun 20 / Jun 16 | Phase 5 (M5.1) |
| Open-weights / local eval baseline | Vendor concentration; open-weights close gap | Jun 17–19 | Cross-cutting |

---

## 5. If you only do three things next

1. **M0.4** — remove the archive-test quarantine (~20m). A clean measurement surface.
2. **M1.1 + M1.2** — the eval harness + a ruler that measures its own variance (~5h).
3. **M2.1** — train the self-tuning scorer from `feedback/*.jsonl`; promote only if it beats the heuristic (~4h).

All local, ~$1 total — and it teaches the three skills the corpus ranks highest:
trustworthy measurement, the learning loop, and feature/eval engineering.

---

## 6. Constraints that don't bend

- **Anthropic-only synthesis** — open-weights/Sonar enter as eval comparisons or scoped tools only, never the reasoning layer.
- **No agent frameworks** — SDK tool-use directly.
- **Human at every gate** — self-tuning, prompt promotion, source-scout, self-review all stop at a PR/approval. L4 = human-gated.
- **Do-no-harm to the daily** — `--no-summarize` stays green in CI.
- **Public news only** — nothing private outbound (regulated-env discipline).
- **Single-file `content_finder.py` until ~3000 LOC; SQLite + hand-DDL; no ORM/vector-DB.**

*— generated from a full parse of the Content-Finder archive, run logs, agent-notes, feedback stream, and the ROADMAP lineage. Built as a parallel working copy; merge to the repo when ready.*
