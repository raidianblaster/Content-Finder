# Agent Note: Synthesis HTML Sanitization

## What changed

- Added regression coverage for untrusted HTML in synthesized card title, body, and "So what" text.
- Added regression coverage that non-HTTP source URLs, such as `javascript:...`, are not rendered as clickable article links.
- Centralized synthesis-card text escaping in `_build_card_html()` via `_html_text()`.
- Added `_safe_http_url()` so rendered article links are limited to `http` and `https` URLs.

## Why

`wrap_synthesis_html()` renders Markdown produced from external feed content and optional LLM synthesis. Raw HTML from that path could previously survive into the published GitHub Pages digest.

## Future work

If richer inline formatting is ever needed inside card snippets, add an explicit HTML sanitizer allowlist instead of bypassing `_html_text()`.
