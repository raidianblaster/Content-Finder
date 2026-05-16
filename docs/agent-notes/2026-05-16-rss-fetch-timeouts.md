# Agent Note: RSS Fetch Timeouts

## What changed

- Added fetcher coverage proving RSS requests go through `httpx.get()` with a 15-second timeout.
- `fetch_rss()` now fetches feed bytes with `httpx`, calls `raise_for_status()`, and then parses the response body with `feedparser.parse()`.

## Why

`feedparser.parse(url)` owns the network call and does not expose the explicit timeout behavior this digest needs. One slow or wedged feed could otherwise hold the whole daily run until the GitHub Actions job timeout.

## Future work

Consider making the RSS timeout configurable if feed reliability varies, but keep a finite default so scheduled runs fail fast enough to leave useful logs.
