# Content Finder

A small CLI that builds a daily digest of credible **agentic AI / LLM** news
for an AI product manager working in a regulated corporate environment.

It pulls from a curated mix of RSS feeds (Simon Willison, Anthropic, Hugging
Face, Techmeme, Latent Space, Import AI, Ethan Mollick, Interconnects, AI
Snake Oil, Pragmatic Engineer) plus Hacker News stories matching agentic-AI
queries, scores everything for relevance + recency + source trust, dedupes,
and either prints the ranked list or asks Claude to synthesise a themed brief.

Live page: https://raidianblaster.github.io/Content-Finder/

## Setup

```bash
cd Content-Finder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional, for Claude-synthesised digests
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

Plain ranked list (no API key needed):

```bash
python3 content_finder.py --no-summarize --days 2
```

Claude-synthesised brief (requires `ANTHROPIC_API_KEY`):

```bash
python3 content_finder.py --days 2
```

Save to a file:

```bash
python3 content_finder.py --days 2 --out digest-$(date +%F).md
```

## Sections in the synthesised brief

1. **Top story** — single most important development.
2. **Models & capability releases**
3. **Agentic engineering & tooling**
4. **Enterprise, regulation & governance**
5. **Worth a deeper read**

Sections with no relevant items are skipped rather than padded.

## Tweaking sources

Edit `sources.yml` to change RSS feeds, Hacker News queries, keyword weights,
and per-source trust bonuses. The loader validates HTTPS feed URLs, duplicate
source names, trust ranges, and required top-level keys.

## Roadmap status

`ROADMAP.md` is the source of truth. Milestone 0.1 tracing, 0.2 score-feature
logging, and 0.3 CI/do-no-harm gate are landed in code. The current trunk path is:
fix the quarantined archive test, build the eval harness, then train the first
self-tuning scorer from feedback labels.

## Schedule it

Add to `cron` for a 7am local digest:

```
0 7 * * * cd ~/00-Claudecode-projects/Content-Finder && \
  .venv/bin/python content_finder.py --days 1 \
  --out ~/Documents/ai-digest-$(date +\%F).md
```
