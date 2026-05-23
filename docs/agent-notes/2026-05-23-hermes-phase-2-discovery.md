# Agent Note: Hermes Phase 2 Discovery

## Goal

Use Hermes as a controlled daily research assistant that extends Content Finder's discovery reach with Exa neural search and Perplexity Sonar, without turning the system into an open-ended web-browsing agent.

Phase 2 is discovery only. The local LLM wiki remains manually curated through Obsidian Web Clipper. Hermes can recommend what is worth clipping, explain why, and prepare source notes, but it should not write directly into the wiki yet.

## Current Baseline

Content Finder already provides the cheap deterministic layer:

- Curated RSS sources and Hacker News queries.
- Keyword, source-trust, recency, and HN-point scoring.
- Cross-day deduplication state.
- Daily HTML digest and archive.
- Per-run JSON logs in `docs/logs/`.
- Review pages and judge outputs for false-positive / false-negative inspection.

Hermes now provides the always-on agent layer:

- Railway-hosted `hermes-gateway`, no longer sleeping.
- OpenAI-compatible API endpoint for Open WebUI.
- `EXA_API_KEY` available in the Railway container.
- `PERPLEXITY_API_KEY` available as a custom provider for Sonar-backed research.

## Operating Principle

Content Finder decides what is probably interesting. Hermes decides what deserves extra investigation.

External search is only allowed when attached to a specific candidate item, watchlist question, or explicit user request. No broad "go research agentic AI" daily browse.

## Non-Goals

- No automatic writes to the local Obsidian / LLM wiki.
- No unattended mass clipping.
- No vector database or RAG infrastructure in this phase.
- No full rewrite of Content Finder around LLM search.
- No expensive multi-agent swarm for a daily digest.
- No internal or bank-sensitive data sent to Exa, Perplexity, or any model provider.

## Daily Flow

1. Content Finder runs its existing daily job.
2. Hermes reads the latest `docs/logs/YYYY-MM-DD.json` and matching judge file if present.
3. Hermes builds a short candidate set:
   - Top 3 final items by score.
   - Up to 3 judge-suspected false negatives.
   - Any item matching a Phase 2 watchlist.
   - Any source from a primary vendor, standards body, research lab, or regulator.
4. Hermes applies a cheap triage rubric without calling Exa or Sonar.
5. Hermes selects at most 3 items for Exa expansion.
6. Hermes uses Perplexity Sonar for at most 1 freshness / citation check.
7. Hermes outputs a daily "clip queue" for manual Obsidian review.

## Watchlists

Phase 2 should bias toward agentic engineering patterns that matter in regulated enterprise AI:

- Agent orchestration and planning loops.
- Tool-use contracts, permissioning, and sandboxing.
- MCP adoption and tool interoperability.
- Agent memory, session continuity, and context compaction.
- Evaluation, observability, and replay for agents.
- Human-in-the-loop controls and approval gates.
- Audit trails, governance, and change-management evidence.
- Cost controls, rate limits, fallbacks, and reliability engineering.
- AI coding agent ROI, maintenance burden, and SDLC integration.
- Retrieval, synthesis, and local knowledge-base maintenance patterns.

## Cheap Triage Rubric

Before using Exa or Sonar, Hermes should score each candidate from 0 to 3 on:

- Relevance to agentic engineering practice.
- Relevance to regulated enterprise AI / banking constraints.
- Freshness or evidence of a new change.
- Primary-source proximity.
- Potential to become a durable wiki page rather than a one-day headline.

Only candidates with a total score of 8 or higher should receive Exa expansion. Sonar is reserved for uncertain or fast-moving claims.

## Exa Usage

Exa is for discovery expansion, not summarization.

Daily cap:

- Maximum 3 Exa searches per daily run.
- Maximum 5 returned links per Exa search.
- Maximum 1 follow-up Exa search if the first result set is obviously poor.

Preferred Exa query patterns:

- Primary-source search: find the original announcement, paper, docs, release notes, or repo.
- Implementation search: find concrete examples, code, diagrams, or engineering writeups.
- Counterpoint search: find credible disagreement, caveats, or failed adoption reports.

Hermes should record why each Exa search was run:

```text
Query:
Reason:
Candidate item:
Expected value:
Results kept:
Results discarded:
```

## Perplexity Sonar Usage

Sonar is for freshness verification and sourced synthesis when the daily candidate is ambiguous.

Daily cap:

- Maximum 1 Sonar call per daily run.
- Skip Sonar if Content Finder already has a primary source and no conflicting claims.
- Prefer no Sonar on quiet days.

Use Sonar when:

- A story is developing across multiple sources.
- The candidate is from an aggregator and needs primary confirmation.
- A model, API, regulation, or vendor capability may have changed in the last 7 days.
- The user explicitly asks for a current briefing.

Required Sonar output:

```text
Confirmed facts:
Unconfirmed / speculative claims:
Primary sources:
Useful secondary sources:
Why this matters for agentic engineering:
Clip recommendation:
```

## Daily Output Contract

Hermes should produce one Markdown note per day, either in chat or as a file if/when automation is added:

```text
# Hermes Discovery Queue: YYYY-MM-DD

## Budget Used

- Exa searches: 0-3
- Sonar calls: 0-1
- Estimated LLM calls: N

## Clip Queue

### 1. Title

- Source:
- URL:
- Why clip:
- Wiki destination suggestion:
- Related existing wiki pages to check manually:
- Exa additions:
- Sonar verification:
- Suggested Obsidian tags:

## Watchlist Signals

- New patterns:
- Repeated patterns:
- Governance / risk signals:

## Skip List

- Item:
- Reason skipped:
```

## Manual Wiki Workflow

The user remains the curator.

Recommended loop:

1. Read the Hermes Discovery Queue in the morning.
2. Open only the 1-5 recommended links.
3. Use Obsidian Web Clipper for sources that are genuinely worth keeping.
4. File clipped sources into the local wiki's raw/source layer.
5. Ask the local wiki agent to ingest only the clipped sources.

Hermes may suggest wiki destinations and cross-links, but the clipping decision stays manual.

## Cost Controls

Start with conservative defaults:

- Daily run frequency: once per day.
- Exa: max 3 searches/day.
- Sonar: max 1 call/day, and allowed to skip.
- Hermes synthesis: one compact daily queue, not a long report.
- No recursive browsing.
- No multi-agent delegation unless manually requested.
- No reprocessing old archive days unless explicitly requested.

Escalation rules:

- If a day has fewer than 2 strong candidates, use zero Exa and zero Sonar.
- If Content Finder finds a primary source directly, do not use Sonar.
- If Exa results are low quality twice in a row, stop expansion for that item.
- If weekly token/API spend feels high, reduce Exa to 1 search/day and Sonar to 2 calls/week.

## Suggested Implementation Steps

### Step 1: Define the handoff

Add a stable machine-readable handoff file generated by Content Finder:

```text
docs/logs/latest.json
```

It can be a copy of the latest dated run log. This avoids Hermes needing to infer the latest file name from archive state.

### Step 2: Add a Hermes prompt template

Create:

```text
prompts/hermes_discovery_queue.md
```

The prompt should define:

- The Phase 2 boundary.
- The watchlists.
- The daily caps.
- The required output contract.
- The rule that wiki writes are out of scope.

### Step 3: Run manually for one week

For the first week, do not automate Hermes.

Manual command/request pattern:

```text
Read Content-Finder's latest run log and judge file. Produce today's Hermes Discovery Queue. Use at most 3 Exa searches and at most 1 Perplexity Sonar call. Do not write to my local wiki.
```

Track:

- Number of recommended clips.
- Number actually clipped.
- Exa searches used.
- Sonar calls used.
- Whether any recommendation felt wasteful.

### Step 4: Add a lightweight usage ledger

Create:

```text
feedback/hermes-discovery-usage.jsonl
```

Each run appends:

```json
{"date":"YYYY-MM-DD","exa_searches":0,"sonar_calls":0,"clips_recommended":0,"clips_taken":0,"notes":"..."}
```

This keeps spend and usefulness visible before adding automation.

### Step 5: Automate only the queue generation

After one week of manual runs, add a Hermes-side daily job only if the queue is consistently useful.

The job should:

- Read latest Content Finder output.
- Produce the Discovery Queue.
- Send it to Open WebUI or the preferred Hermes channel.
- Avoid writing to Content Finder or the local wiki by default.

### Step 6: Review after two weeks

Evaluate:

- Did Hermes surface sources the base digest would have missed?
- Did Exa find better primary sources?
- Did Sonar reduce uncertainty enough to justify its use?
- How many recommended clips made it into Obsidian?
- Which watchlists are over-triggering?
- Which topics need better source coverage?

Only after this review should Phase 3 consider deeper wiki integration.

## Success Criteria

Phase 2 is working if:

- Daily review takes less than 10 minutes.
- Hermes recommends 1-5 high-quality clip candidates.
- At least 30 percent of recommended clips are actually worth saving.
- Exa usage regularly improves source quality.
- Sonar usage is rare but valuable.
- Token and API spend remain predictable.
- The local wiki remains human-curated.

## Failure Signals

Pause or reduce scope if:

- Hermes recommends too many links.
- The queue feels like a second newsletter.
- Exa mostly returns sources already in the digest.
- Sonar becomes a default summarizer instead of a verification tool.
- The user stops clipping because the review burden is too high.
- The system starts optimizing for novelty over durable wiki value.

## Phase 3 Trigger

Do not move to automated wiki ingestion until Phase 2 produces a stable pattern:

- At least two weeks of daily queues.
- A usage ledger showing acceptable spend.
- A clear list of recurring wiki destinations.
- User confidence that Hermes' clip recommendations are usually worth attention.

Phase 3 can then explore source-note templates, Obsidian-ready frontmatter, and assisted ingest prompts while still preserving manual approval.
