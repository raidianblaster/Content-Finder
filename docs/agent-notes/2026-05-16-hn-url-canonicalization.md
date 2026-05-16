# Agent Note: Hacker News URL Canonicalization

## What changed

- Changed `canonical_url()` to preserve `id` for `https://news.ycombinator.com/item?id=...` URLs.
- Continued stripping non-identity query parameters, including HN tracker params.
- Added regression coverage that within-run dedupe keeps distinct HN discussion URLs.

## Why

Hacker News item URLs store their stable story identity in the query string. Stripping all query parameters collapsed every discussion-only HN URL into `https://news.ycombinator.com/item`, causing within-run dedupe and cross-day dedup state to treat unrelated stories as the same item.

## Future work

If more sources use query parameters as canonical IDs, add source-specific cases here rather than globally preserving all query strings.
